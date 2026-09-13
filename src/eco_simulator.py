"""
ECO(Engineering Change Order) 시뮬레이터 — 부품 단종(EOL)/규제대응 시나리오에서
대체 부품(substitute part)을 적용하면 MRP 결과가 어떻게 바뀌는지 시뮬레이션한다.

이 모듈은 scm-질문로그.md 20~21번 항목에서 정리한 실무 워크플로우를 그대로 코드로 옮긴 것:

  1) 단종/규제 감지 (Z2Data/SiliconExpert류 툴)        -> ECO_SCENARIOS[*]["trigger"]
  2) Where-Used 조회 (PLM)                            -> where_used()
  3) 대체품 탐색 + Drop-in 등급 (Z2Data/SiliconExpert)  -> ECO_SCENARIOS[*]["substitutes"]
  4) CCB 승인                                          -> 사람이 함. 이 시뮬레이터는 판단 재료(비용/
                                                          일정/등급별 트레이드오프)만 계산해서 보여준다.
  5) ECO 반영 -> 부품마스터 갱신 -> MRP 재계산           -> simulate_substitute() / build_eco_report()

주의: 재고(on_hand)는 그대로 둔다. 실무에서도 기존 재고는 소진될 때까지 쓰고, 신규 발주분부터
대체품 스펙(리드타임·단가)이 적용되는 것이 일반적이라 이 단순화가 큰 왜곡을 만들지 않는다.
반대로 리드타임·단가는 대체품 스펙으로 완전히 교체해서 향후 발주 계획에 반영한다.
"""
import math

import pandas as pd

from bom import bom_dataframe, PRODUCT_ID, PRODUCT_NAME
from part_master import part_master_df
from mrp_engine import run_mrp, first_action_per_part

DROP_IN_GRADE_DESC = {
    "A": "Drop-in A · Form/Fit/Function 동일 — 재인증 없이 즉시 대체 가능",
    "B": "Drop-in B · 경미한 차이 — 보정/조정 등 축소 검토 필요",
    "C": "Drop-in C · 주요 사양 상이 — 전체 재인증(requalification) 필요",
}

ECO_SCENARIOS = [
    {
        "eco_id": "ECO-2027-001",
        "part_id": "PRT-TMP",
        "trigger": "공급업체 EOL(단종) 공지 — VacuTech Global, 구형 라인업 단종 예정",
        "substitutes": [
            {"alt_id": "TMP-ALT-A", "alt_name": "VacuTech TMP-950X (동일 공급업체 후속모델)",
             "grade": "A", "cost_delta_pct": 4, "lead_time_weeks": 11,
             "note": "동일 풋프린트·인터페이스, 성능 스펙 동일. 후속모델로 사실상 자동 승계"},
            {"alt_id": "TMP-ALT-B", "alt_name": "Ebara ET-1200",
             "grade": "B", "cost_delta_pct": -8, "lead_time_weeks": 9,
             "note": "장착 브라켓 경미 수정 + 진동 스펙 재검토 필요"},
            {"alt_id": "TMP-ALT-C", "alt_name": "Pfeiffer HiPace 2300",
             "grade": "C", "cost_delta_pct": -15, "lead_time_weeks": 16,
             "note": "제어 인터페이스(통신 프로토콜) 상이 — 펌웨어 통합 + 전체 재인증 필요"},
        ],
    },
    {
        "eco_id": "ECO-2027-002",
        "part_id": "PRT-RFA",
        "trigger": "핵심 GaN 트랜지스터 단종에 따른 부품 EOL",
        "substitutes": [
            {"alt_id": "RFA-ALT-A", "alt_name": "RF Dynamics RFA-500N (개정판, 동일 공급업체)",
             "grade": "A", "cost_delta_pct": 2, "lead_time_weeks": 12,
             "note": "동일 공급업체가 대체 트랜지스터로 개정, 출력 스펙 동일"},
            {"alt_id": "RFA-ALT-B", "alt_name": "Advanced RF Systems ARF-9000",
             "grade": "B", "cost_delta_pct": -5, "lead_time_weeks": 10,
             "note": "출력 보정(calibration) 절차 추가 필요"},
            {"alt_id": "RFA-ALT-C", "alt_name": "MKS Instruments RFPA-X",
             "grade": "C", "cost_delta_pct": -12, "lead_time_weeks": 18,
             "note": "폼팩터 상이 — 섀시 설계 변경 + 전체 재인증 필요"},
        ],
    },
    {
        "eco_id": "ECO-2027-003",
        "part_id": "PRT-ESC",
        "trigger": "환경규제(RoHS) 대응 — 기존 세라믹 소재 특정물질 사용 제한",
        "substitutes": [
            {"alt_id": "ESC-ALT-A", "alt_name": "CeramTech Korea ESC-2 (RoHS 대응, 동일 공급업체)",
             "grade": "A", "cost_delta_pct": 6, "lead_time_weeks": 10,
             "note": "동일 공급업체의 RoHS 대응 버전, 클램핑 스펙 동일"},
            {"alt_id": "ESC-ALT-B", "alt_name": "NGK ESC Advanced",
             "grade": "B", "cost_delta_pct": -3, "lead_time_weeks": 9,
             "note": "클램핑 전압 재보정(recalibration) 필요"},
            {"alt_id": "ESC-ALT-C", "alt_name": "Kyocera ESC-Pro",
             "grade": "C", "cost_delta_pct": 15, "lead_time_weeks": 13,
             "note": "세라믹 조성 상이 — 공정 전체 재인증 필요"},
        ],
    },
]


def where_used(part_id: str) -> dict:
    """PLM의 'Where-Used' 조회를 흉내낸다: 특정 Level2 부품이 어느 서브시스템/완제품에
    쓰이는지 역방향으로 조회 (부품 -> 상위 조립품 방향)."""
    df = bom_dataframe()
    row = df[df["child_id"] == part_id].iloc[0]
    sub_id, sub_name, qty_per_sub = row.parent_id, row.parent_name, row.qty_per
    top_row = df[df["child_id"] == sub_id].iloc[0]
    qty_per_top = top_row.qty_per
    return {
        "part_id": part_id,
        "subsystem_id": sub_id,
        "subsystem_name": sub_name,
        "qty_per_subsystem": int(qty_per_sub),
        "product_id": PRODUCT_ID,
        "product_name": PRODUCT_NAME,
        "qty_per_product": int(qty_per_sub * qty_per_top),
    }


def _part_result(part_id: str, mrp_df: pd.DataFrame, unit_cost: float, lead_time_weeks: float) -> dict:
    """특정 부품에 대한 MRP 재계산 결과를 대시보드에 필요한 요약 지표로 압축."""
    part_mrp = mrp_df[mrp_df["part_id"] == part_id]
    first_action = first_action_per_part(part_mrp)

    six_month_value = float(part_mrp["order_value"].sum())

    if first_action.empty:
        return {
            "unit_cost": unit_cost,
            "lead_time_weeks": lead_time_weeks,
            "is_past_due": False,
            "months_overdue": 0,
            "first_release_period": "발주 불필요",
            "safety_stock": int(part_mrp["safety_stock"].iloc[0]) if not part_mrp.empty else 0,
            "order_qty": 0,
            "order_value": 0,
            "six_month_total_order_value": round(six_month_value, 0),
        }

    row = first_action.iloc[0]
    return {
        "unit_cost": unit_cost,
        "lead_time_weeks": lead_time_weeks,
        "is_past_due": bool(row["is_past_due"]),
        "months_overdue": int(row["months_overdue"]),
        "first_release_period": row["planned_release_period"],
        "safety_stock": int(row["safety_stock"]),
        "order_qty": int(row["order_qty"]),
        "order_value": float(row["order_value"]),
        "six_month_total_order_value": round(six_month_value, 0),
    }


def simulate_substitute(part_id: str, lead_time_weeks: float, cost_delta_pct: float,
                         forecast_df: pd.DataFrame, resid_std: float) -> dict:
    """part_id의 리드타임·단가를 대체품 스펙으로 바꿔서 MRP를 재계산한다."""
    parts_df = part_master_df().copy()
    mask = parts_df["part_id"] == part_id
    baseline_cost = float(parts_df.loc[mask, "unit_cost"].iloc[0])
    new_cost = round(baseline_cost * (1 + cost_delta_pct / 100), 0)

    parts_df.loc[mask, "unit_cost"] = new_cost
    parts_df.loc[mask, "lead_time_weeks"] = lead_time_weeks

    mrp_df = run_mrp(forecast_df, resid_std, parts_df=parts_df)
    return _part_result(part_id, mrp_df, new_cost, lead_time_weeks)


def build_eco_report(forecast_df: pd.DataFrame, resid_std: float,
                      baseline_mrp_df: pd.DataFrame = None) -> list:
    """ECO_SCENARIOS 전체에 대해 Where-Used + 기준(baseline) + 대체품별 시뮬레이션 결과를 조립."""
    if baseline_mrp_df is None:
        baseline_mrp_df = run_mrp(forecast_df, resid_std)

    parts = part_master_df().set_index("part_id")
    report = []
    for scenario in ECO_SCENARIOS:
        part_id = scenario["part_id"]
        p = parts.loc[part_id]
        baseline = _part_result(part_id, baseline_mrp_df, float(p.unit_cost), float(p.lead_time_weeks))

        substitutes = []
        for alt in scenario["substitutes"]:
            result = simulate_substitute(
                part_id, alt["lead_time_weeks"], alt["cost_delta_pct"], forecast_df, resid_std
            )
            result["safety_stock_delta"] = result["safety_stock"] - baseline["safety_stock"]
            result["months_overdue_delta"] = result["months_overdue"] - baseline["months_overdue"]
            result["six_month_value_delta"] = round(
                result["six_month_total_order_value"] - baseline["six_month_total_order_value"], 0
            )
            substitutes.append({
                "alt_id": alt["alt_id"],
                "alt_name": alt["alt_name"],
                "grade": alt["grade"],
                "grade_desc": DROP_IN_GRADE_DESC[alt["grade"]],
                "cost_delta_pct": alt["cost_delta_pct"],
                "note": alt["note"],
                "result": result,
            })

        report.append({
            "eco_id": scenario["eco_id"],
            "part_id": part_id,
            "part_name": p.part_name,
            "supplier": p.supplier,
            "trigger": scenario["trigger"],
            "where_used": where_used(part_id),
            "baseline": baseline,
            "substitutes": substitutes,
        })
    return report


if __name__ == "__main__":
    from demand_data import generate_history
    from forecasting import forecast_future

    hist = generate_history()
    fc, meta = forecast_future(hist)
    report = build_eco_report(fc, meta["resid_std"])

    for scenario in report:
        print(f"\n=== {scenario['eco_id']} — {scenario['part_name']} ({scenario['part_id']}) ===")
        print(f"트리거: {scenario['trigger']}")
        wu = scenario["where_used"]
        print(f"Where-Used: {wu['product_name']} > {wu['subsystem_name']} "
              f"(완제품 1대당 {wu['qty_per_product']}개)")
        b = scenario["baseline"]
        print(f"기준(현재 부품) 상태: past_due={b['is_past_due']} "
              f"({b['months_overdue']}개월 초과), 6개월 발주 예상액=${b['six_month_total_order_value']:,.0f}")
        for s in scenario["substitutes"]:
            r = s["result"]
            print(f"  [{s['grade']}] {s['alt_name']}: 리드타임 {r['lead_time_weeks']}주, "
                  f"단가 {s['cost_delta_pct']:+d}%, past_due={r['is_past_due']} "
                  f"({r['months_overdue']}개월), 6개월 발주액 delta=${r['six_month_value_delta']:+,.0f}")
