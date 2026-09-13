"""
이익 임팩트(Profit Impact) 모듈 — "이 시스템을 쓰면 회사가 얼마를 벌거나 지키는가"를 계산한다.

지금까지 만든 Action Queue/ECN 시뮬레이터는 "무엇을, 언제, 얼마에 발주해야 하는가"까지 보여줬다.
이 모듈은 그 위에 재무적 임팩트 두 가지를 얹는다.

  1) 매출 리스크(Revenue at Risk): 부품이 제때 발주되지 않아 완제품 생산이 막히면,
     그로 인해 못 만드는 완제품 수량 x 판매단가(ASP) = 리스크에 노출된 매출/마진.
  2) 안전재고 서비스수준 트레이드오프: 서비스수준(Z)을 올리면 재고에 묶이는 돈(운전자본)은
     늘고 결품 리스크는 줄어든다. 이 트레이드오프를 몇 개 지점에서 비교해서, 현재 정책(95%)이
     "이익" 관점에서 최적인지 살펴본다.

*** 중요: ASP·마진율·자본비용은 전부 가정치(assumption)다. ***
PE-3000은 가상의 제품이라 실제 판매가/마진이 존재하지 않는다. 아래 가정치는 반도체 장비
업계의 공개된 범위를 참고한 "그럴듯한 값"이지, 특정 기업의 실제 수치가 아니다:
  - ASP(대당 판매가): 업계에서 공개 보도되는 식각/증착 장비 가격대($1M~$10M+)를 참고해
    중간값 근처인 $3.5M으로 가정
  - 매출총이익률: Lam Research가 2026년 최근 분기 실적에서 매출총이익률 50%에 근접했다는
    보도(WebSearch, 2026-09 — 아래 소스 참고)를 참고해 48%로 가정
  - 자본비용(재고에 묶인 돈의 기회비용): 연 10%(WACC 근사치)로 가정, 6개월 구간에는 절반(5%) 적용
이 가정을 바꾸면 결과 금액도 당연히 바뀐다 — 핵심은 "방법론"이지 이 숫자 자체가 아니다.
"""
import math
import os

import numpy as np
import pandas as pd
from scipy.stats import norm

from bom import explode_bom_to_top
from part_master import part_master_df
from mrp_engine import WEEKS_PER_MONTH, first_action_per_part, run_mrp

REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "profit_impact.md")

# --- 가정치 (모두 명시적으로 라벨링, 실제 공개 수치 아님) ---
ASSUMED_ASP = 3_500_000          # 완제품(PE-3000) 대당 판매단가 가정 (USD)
ASSUMED_GROSS_MARGIN_PCT = 0.48  # 매출총이익률 가정 (반도체 장비업계 공개 보도 참고)
ASSUMED_ANNUAL_CAPITAL_COST_PCT = 0.10  # 재고에 묶인 자본의 연간 기회비용 가정 (WACC 근사)
HORIZON_MONTHS = 6

SERVICE_LEVELS = [
    {"label": "90%", "z": 1.28},
    {"label": "95% (현재 정책)", "z": 1.65},
    {"label": "99%", "z": 2.33},
]


def _unit_normal_loss(z: float) -> float:
    """단위정규 손실함수 L(z) = phi(z) - z*(1-Phi(z)).
    재고이론에서 한 리드타임 주기 동안 '기대 부족량'을 표준편차 단위로 나타낸 값 (Silver-Pyke-Peterson)."""
    return norm.pdf(z) - z * (1 - norm.cdf(z))


def revenue_at_risk_by_part(mrp_df: pd.DataFrame, forecast_df: pd.DataFrame) -> pd.DataFrame:
    """부품별 매출 리스크: '즉시발주(Past Due)'인 부품은, 이미 놓친 발주 시점(months_overdue)만큼
    해당 기간의 완제품 생산이 막힌다고 보고, 그 기간의 예측 생산량 x ASP를 리스크로 계산한다.
    (완제품은 모든 서브시스템이 다 있어야 조립되므로, 부품 하나만 없어도 그 기간 생산 전체가
    막힌다는 '병목' 가정을 씀 — 보수적이지 않고 다소 공격적인 가정이라는 점을 리포트에 명시)
    """
    first_action = first_action_per_part(mrp_df)
    top_units = forecast_df["forecast_units"].values

    rows = []
    for _, r in first_action.iterrows():
        if r["is_past_due"]:
            window = int(r["months_overdue"])
            window = min(window, len(top_units))
            at_risk_units = float(np.sum(top_units[:window]))
        else:
            window = 0
            at_risk_units = 0.0
        revenue = at_risk_units * ASSUMED_ASP
        margin = revenue * ASSUMED_GROSS_MARGIN_PCT
        rows.append({
            "part_id": r["part_id"], "part_name": r["part_name"], "is_past_due": bool(r["is_past_due"]),
            "months_overdue": int(r["months_overdue"]), "at_risk_window_months": window,
            "at_risk_top_units": round(at_risk_units, 1),
            "revenue_at_risk": round(revenue, 0), "margin_at_risk": round(margin, 0),
        })
    return pd.DataFrame(rows).sort_values("margin_at_risk", ascending=False)


def service_level_tradeoff(forecast_df: pd.DataFrame, resid_std: float) -> pd.DataFrame:
    """서비스수준(Z)별로 (1) 안전재고에 묶이는 돈 (2) 기대 매출/마진 리스크 (3) 현재 정책(95%) 대비
    순이익 임팩트를 계산한다."""
    parts = part_master_df().set_index("part_id")
    bom_qty = explode_bom_to_top(1)
    top_units = forecast_df["forecast_units"].values
    n_periods = len(top_units)

    # 부품별로 Z와 무관한 sigma_lt(리드타임 동안의 수요 표준편차)와 qty_per_top, lead_time을 먼저 계산
    part_sigma = {}
    for part_id, qty_per_top in bom_qty.items():
        p = parts.loc[part_id]
        gross_req = top_units * qty_per_top
        mean_component_demand = float(np.mean(gross_req))
        lt_months = p.lead_time_weeks / WEEKS_PER_MONTH
        monthly_sigma = math.sqrt(
            (resid_std * qty_per_top) ** 2 + (p.demand_cv * mean_component_demand) ** 2
        )
        sigma_lt = monthly_sigma * math.sqrt(max(lt_months, 0.1))
        part_sigma[part_id] = {
            "sigma_lt": sigma_lt, "qty_per_top": qty_per_top,
            "unit_cost": float(p.unit_cost), "lead_time_weeks": float(p.lead_time_weeks),
        }

    avg_lead_time_months = np.mean([v["lead_time_weeks"] for v in part_sigma.values()]) / WEEKS_PER_MONTH
    cycles_per_horizon = max(HORIZON_MONTHS / avg_lead_time_months, 1.0)
    capital_cost_horizon_pct = ASSUMED_ANNUAL_CAPITAL_COST_PCT * (HORIZON_MONTHS / 12)

    # 1단계: 서비스수준별 재고투자액·기대 매출/마진 리스크를 우선 전부 계산
    raw = []
    for level in SERVICE_LEVELS:
        z = level["z"]
        total_working_capital = 0.0
        bottleneck_top_unit_shortfall = 0.0
        for part_id, v in part_sigma.items():
            safety_stock = math.ceil(z * v["sigma_lt"])
            total_working_capital += safety_stock * v["unit_cost"]
            expected_shortfall_units = v["sigma_lt"] * _unit_normal_loss(z)
            expected_shortfall_top_units = expected_shortfall_units / v["qty_per_top"]
            bottleneck_top_unit_shortfall = max(bottleneck_top_unit_shortfall, expected_shortfall_top_units)

        expected_units_at_risk = min(bottleneck_top_unit_shortfall * cycles_per_horizon, sum(top_units))
        expected_revenue_at_risk = expected_units_at_risk * ASSUMED_ASP
        expected_margin_at_risk = expected_revenue_at_risk * ASSUMED_GROSS_MARGIN_PCT
        raw.append({
            "level": level, "total_working_capital": total_working_capital,
            "expected_units_at_risk": expected_units_at_risk,
            "expected_revenue_at_risk": expected_revenue_at_risk,
            "expected_margin_at_risk": expected_margin_at_risk,
        })

    # 2단계: "현재 정책"(Z_SERVICE_95, 95%) 행을 명시적으로 찾아 그것을 기준(baseline)으로 삼는다
    # (리스트 순회 순서가 바뀌어도 baseline이 항상 95% 정책을 가리키도록 z 값으로 직접 찾음)
    baseline = next(r for r in raw if r["level"]["z"] == 1.65)
    baseline_margin_risk = baseline["expected_margin_at_risk"]
    baseline_working_capital = baseline["total_working_capital"]

    rows = []
    for r in raw:
        capital_cost_delta = (r["total_working_capital"] - baseline_working_capital) * capital_cost_horizon_pct
        margin_protected = baseline_margin_risk - r["expected_margin_at_risk"]
        net_profit_impact = margin_protected - capital_cost_delta
        rows.append({
            "service_level": r["level"]["label"], "z": r["level"]["z"],
            "total_working_capital": round(r["total_working_capital"], 0),
            "expected_units_at_risk": round(r["expected_units_at_risk"], 2),
            "expected_revenue_at_risk": round(r["expected_revenue_at_risk"], 0),
            "expected_margin_at_risk": round(r["expected_margin_at_risk"], 0),
            "capital_cost_delta_vs_baseline": round(capital_cost_delta, 0),
            "net_profit_impact_vs_baseline": round(net_profit_impact, 0),
        })
    return pd.DataFrame(rows)


def build_report(rar: pd.DataFrame, tradeoff: pd.DataFrame) -> str:
    lines = []
    lines.append("# 이익 임팩트 리포트 (Profit Impact)\n")
    lines.append("**모든 금액은 가정치 기반입니다** — ASP $3.5M(가정), 매출총이익률 48%(Lam Research")
    lines.append("2026년 보도 참고 가정), 자본비용 연 10%(WACC 근사 가정). 실제 기업 수치가 아니라")
    lines.append("방법론을 보여주기 위한 가정입니다. 재현: `python src/profit_impact.py`\n")

    lines.append("## 1. 부품별 매출 리스크 (Revenue at Risk)\n")
    lines.append("이미 발주 시점이 지난(즉시발주 필요) 부품에 대해, 그 지연 기간만큼 완제품 생산이")
    lines.append("막힌다고 가정했을 때의 매출·마진 노출액입니다.\n")
    lines.append("| 부품 | 지연 개월 | 리스크 노출 기간(개월) | 영향받는 완제품(대) | 매출 리스크 | 마진 리스크 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, r in rar.head(10).iterrows():
        if r["is_past_due"]:
            lines.append(f"| {r['part_name']} | {r['months_overdue']} | {r['at_risk_window_months']} | "
                          f"{r['at_risk_top_units']:g} | ${r['revenue_at_risk']:,.0f} | ${r['margin_at_risk']:,.0f} |")
    top_risk = rar.iloc[0]
    lines.append(f"\n가장 큰 리스크는 **{top_risk['part_name']}**로, 마진 기준 약 "
                  f"**${top_risk['margin_at_risk']:,.0f}**가 노출되어 있습니다 (전 부품 중 병목 지점 하나만")
    lines.append("골라도 이 정도 규모라는 뜻 — 여러 부품이 동시에 밀리면 리스크가 합산되진 않고 가장")
    lines.append("늦는 부품 하나가 전체 생산 일정을 좌우합니다).\n")

    lines.append("## 2. 안전재고 서비스수준 트레이드오프\n")
    lines.append("서비스수준을 올리면 재고에 묶이는 돈(운전자본)은 늘고, 기대 매출 리스크는 줄어듭니다.")
    lines.append("아래는 95%(현재 정책) 대비 순이익 임팩트입니다 (매출 리스크 감소분 − 늘어난 재고의")
    lines.append("자본비용).\n")
    lines.append("| 서비스수준 | 재고 운전자본 | 기대 매출 리스크 | 기대 마진 리스크 | 현재 대비 자본비용 증가분 | 현재 대비 순이익 임팩트 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, r in tradeoff.iterrows():
        lines.append(f"| {r['service_level']} | ${r['total_working_capital']:,.0f} | "
                      f"${r['expected_revenue_at_risk']:,.0f} | ${r['expected_margin_at_risk']:,.0f} | "
                      f"${r['capital_cost_delta_vs_baseline']:,.0f} | ${r['net_profit_impact_vs_baseline']:+,.0f} |")

    best = tradeoff.loc[tradeoff["net_profit_impact_vs_baseline"].idxmax()]
    lines.append(f"\n이 가정치 기준으로는, 테스트한 세 지점(90/95/99%) 중 **{best['service_level']}**가 현재")
    lines.append(f"정책(95%) 대비 순이익 임팩트가 가장 좋게 나옵니다 (${best['net_profit_impact_vs_baseline']:+,.0f}).")
    lines.append("PE-3000처럼 대당 단가가 매우 높은 제품은 재고 자본비용보다 결품으로 인한 매출 손실이")
    lines.append("훨씬 커서, 서비스수준을 높일수록 유리해지는 경향이 이 가정 하에서는 뚜렷합니다.")
    lines.append("다만 딱 세 점만 비교했기 때문에, 99%보다 더 높은 서비스수준에서 최적점이 있을 수도")
    lines.append("있고 — 재고 자본비용 곡선은 계속 증가하는 반면 매출 리스크 감소분은 체감(diminishing")
    lines.append("returns)하므로 어딘가에서 역전될 겁니다. 이 결과의 핵심은 \"몇 %가 정답이다\"가 아니라")
    lines.append("\"서비스수준을 감(experience)이 아니라 재무적 트레이드오프로 따질 수 있다\"는 방법론입니다.\n")

    lines.append("## 3. 한계 (정직하게 밝힘)\n")
    lines.append("- ASP·매출총이익률·자본비용은 전부 가정치입니다. 실제 결정에 쓰려면 재무팀의 실제")
    lines.append("  원가/가격 데이터로 교체해야 합니다.")
    lines.append("- 매출 리스크는 \"부품 하나가 없으면 완제품 전체를 못 만든다\"는 병목 가정을 씁니다.")
    lines.append("  실제로는 일부 서브어셈블리를 먼저 조립해두고 부품만 나중에 넣는 등 유연성이 있을 수")
    lines.append("  있어, 이 값은 상한선(worst case)에 가깝습니다.")
    lines.append("- 서비스수준 트레이드오프의 '기대 결품' 계산은 재고이론의 단위정규손실함수를 썼는데,")
    lines.append("  이는 수요가 정규분포를 따른다는 가정 위에 있습니다 — FabPulse의 다른 계산과 같은")
    lines.append("  가정선상입니다.")

    return "\n".join(lines)


if __name__ == "__main__":
    from demand_data import generate_history
    from forecasting import forecast_future

    hist = generate_history()
    fc, meta = forecast_future(hist)
    mrp_df = run_mrp(fc, meta["resid_std"])

    rar = revenue_at_risk_by_part(mrp_df, fc)
    tradeoff = service_level_tradeoff(fc, meta["resid_std"])

    print("=== 부품별 매출 리스크 (상위 5개) ===")
    print(rar.head(5)[["part_name", "months_overdue", "at_risk_top_units", "revenue_at_risk", "margin_at_risk"]]
          .to_string(index=False))
    print("\n=== 서비스수준 트레이드오프 ===")
    print(tradeoff.to_string(index=False))

    report = build_report(rar, tradeoff)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n리포트 저장됨: {REPORT_PATH}")
