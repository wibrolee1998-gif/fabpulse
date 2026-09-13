"""
MRP (Material Requirements Planning) 엔진.

흐름: 완제품 수요예측 -> BOM 전개(부품별 총소요량) -> 안전재고 계산 -> 넷팅(가용재고 차감)
      -> 로트사이징(MOQ 반영) -> 리드타임 오프셋(발주시점 역산)

용어는 reports/scm_concepts.md 참고.
"""
import math
import numpy as np
import pandas as pd

from bom import explode_bom_to_top
from part_master import part_master_df

Z_SERVICE_95 = 1.65  # 서비스 수준 95% 기준 안전계수
WEEKS_PER_MONTH = 4.345

# 조달 리드타임이 긴 부품 일부는 이미 발주가 나가 있다고 가정한 입고예정(scheduled receipt) 데이터
# (실무에서는 open PO 데이터로 대체됨. 여기서는 시연을 위한 합성 값)
SCHEDULED_RECEIPTS = {
    "PRT-TMP": {0: 1},   # Turbo Pump 1대, 첫 번째 계획 기간에 입고 예정
    "PRT-RFA": {0: 1},   # RF Power Amplifier 1대
    "PRT-ESC": {0: 1},   # Electrostatic Chuck 1대
}


def _safety_stock(mean_monthly_component_demand: float, demand_cv: float,
                   top_resid_std: float, qty_per_top: float, lead_time_weeks: float) -> float:
    """부품별 안전재고 = Z * 리드타임 동안의 수요 표준편차.

    표준편차는 두 요인을 합성한다:
      1) 완제품 수요예측 오차가 BOM 배수만큼 전파된 부분 (top_resid_std * qty_per_top)
      2) 부품 자체의 추가 변동성 (스크랩/여분 소요 등, demand_cv * 평균수요)
    두 요인은 서로 독립이라고 가정하고 분산을 더해(RSS) 월간 표준편차를 구한 뒤,
    리드타임(개월) 동안 누적되는 변동성을 sqrt(리드타임개월)로 반영한다.
    """
    lt_months = lead_time_weeks / WEEKS_PER_MONTH
    monthly_sigma = math.sqrt(
        (top_resid_std * qty_per_top) ** 2 + (demand_cv * mean_monthly_component_demand) ** 2
    )
    sigma_lt = monthly_sigma * math.sqrt(max(lt_months, 0.1))
    return Z_SERVICE_95 * sigma_lt


def run_mrp(forecast_df: pd.DataFrame, resid_std: float, parts_df: pd.DataFrame = None) -> pd.DataFrame:
    """forecast_df: columns [period, forecast_units] (향후 N개월 완제품 수요예측)
    resid_std: 완제품 수요예측 모델의 잔차 표준편차 (안전재고 계산용)
    parts_df: 부품마스터를 대체할 DataFrame (미지정 시 기본 part_master_df() 사용).
              ECO(설계변경) 시뮬레이션에서 특정 부품의 리드타임/단가를 바꿔서
              MRP를 재계산할 때 사용한다 (eco_simulator.py 참고).
    """
    periods = list(forecast_df["period"])
    n_periods = len(periods)
    top_units = forecast_df["forecast_units"].values

    parts = (parts_df if parts_df is not None else part_master_df()).set_index("part_id")
    bom_qty = explode_bom_to_top(1)  # 완제품 1대당 부품별 필요 수량

    rows = []
    for part_id, qty_per_top in sorted(bom_qty.items()):
        p = parts.loc[part_id]
        gross_req = top_units * qty_per_top
        mean_component_demand = float(np.mean(gross_req))
        safety_stock = _safety_stock(
            mean_component_demand, p.demand_cv, resid_std, qty_per_top, p.lead_time_weeks
        )
        safety_stock = math.ceil(safety_stock)

        lt_months = p.lead_time_weeks / WEEKS_PER_MONTH
        lt_periods = math.ceil(lt_months)

        sched = SCHEDULED_RECEIPTS.get(part_id, {})

        projected_on_hand = p.on_hand
        for t in range(n_periods):
            scheduled_receipt = sched.get(t, 0)
            available = projected_on_hand + scheduled_receipt
            shortfall = safety_stock - (available - gross_req[t])
            net_req = max(0.0, shortfall)

            if net_req > 0:
                order_qty = max(net_req, p.moq)  # 로트사이징: MOQ 반영 (lot-for-lot + MOQ)
            else:
                order_qty = 0.0

            release_period = t - lt_periods
            has_order = order_qty > 0

            projected_on_hand = available - gross_req[t] + order_qty

            # 발주가 없는(order_qty=0) 기간은 release_period/past-due 라벨도 의미가 없으므로 "-"로 둔다.
            if not has_order:
                release_period_label = "-"
            elif 0 <= release_period < n_periods:
                release_period_label = periods[release_period]
            else:
                release_period_label = "즉시발주(Past Due)"

            rows.append({
                "part_id": part_id,
                "part_name": p.part_name,
                "supplier": p.supplier,
                "period": periods[t],
                "period_index": t,
                "gross_requirement": round(gross_req[t], 1),
                "scheduled_receipt": scheduled_receipt,
                "safety_stock": safety_stock,
                "projected_on_hand": round(projected_on_hand, 1),
                "net_requirement": round(net_req, 1),
                "order_qty": math.ceil(order_qty) if has_order else 0,
                "unit_cost": p.unit_cost,
                "order_value": round(math.ceil(order_qty) * p.unit_cost, 0) if has_order else 0,
                "lead_time_weeks": p.lead_time_weeks,
                "planned_release_period_index": release_period if has_order else None,
                "planned_release_period": release_period_label,
                "moq": p.moq,
            })

    return pd.DataFrame(rows)


def summarize_orders(mrp_df: pd.DataFrame) -> pd.DataFrame:
    """부품별로 향후 계획기간 전체의 발주 필요 수량/금액을 합산."""
    orders = mrp_df[mrp_df["order_qty"] > 0]
    summary = orders.groupby(["part_id", "part_name", "supplier", "lead_time_weeks", "moq"]).agg(
        total_order_qty=("order_qty", "sum"),
        total_order_value=("order_value", "sum"),
        first_release=("planned_release_period_index", "min"),
    ).reset_index().sort_values("total_order_value", ascending=False)
    return summary


def first_action_per_part(mrp_df: pd.DataFrame) -> pd.DataFrame:
    """부품별 '지금 당장 취해야 할 첫 액션'만 추린 표.

    같은 부품이라도 리드타임이 길면 여러 기간에 걸쳐 순차적으로 발주가 필요할 수 있는데,
    실무에서 가장 먼저 봐야 할 건 '가장 이른 발주 필요 시점'이다. 이 표는 부품별로 그
    첫 번째 필요 발주 건만 남겨서, "지금 당장 발주해야 하는가 / 언제까지 발주하면 되는가"를
    한눈에 보여준다. (이후 기간의 추가 발주는 order_summary.csv의 total_order_qty에 포함되어 있음)
    """
    orders = mrp_df[mrp_df["order_qty"] > 0].copy()
    if orders.empty:
        return orders
    idx = orders.groupby("part_id")["period_index"].idxmin()
    first = orders.loc[idx].copy()
    first["is_past_due"] = first["planned_release_period"] == "즉시발주(Past Due)"
    first["months_overdue"] = first["planned_release_period_index"].apply(lambda x: max(0, -x))
    return first.sort_values(["is_past_due", "months_overdue"], ascending=[False, False])


if __name__ == "__main__":
    from demand_data import generate_history
    from forecasting import forecast_future

    hist = generate_history()
    fc, meta = forecast_future(hist)
    mrp = run_mrp(fc, meta["resid_std"])

    print(f"채택 예측 모델: {meta['chosen_model']} (잔차 표준편차 {meta['resid_std']})\n")
    print("=== 부품별 발주 계획 (앞 20행) ===")
    print(mrp.head(20).to_string(index=False))

    print("\n=== 부품별 발주 요약 (금액 큰 순) ===")
    summary = summarize_orders(mrp)
    print(summary.to_string(index=False))
    print(f"\n총 발주 예상 금액: ${summary['total_order_value'].sum():,.0f}")

    past_due = mrp[mrp["planned_release_period"] == "즉시발주(Past Due)"]
    if not past_due.empty:
        print(f"\n⚠ 즉시 발주가 필요한 부품 (리드타임이 길어 이미 발주 시점이 지남): "
              f"{sorted(past_due['part_id'].unique())}")
