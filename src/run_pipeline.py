"""
전체 파이프라인 실행: 데이터 생성 -> 수요예측 -> MRP -> 결과 파일 저장.

대시보드(HTML)와 리포트에서 쓸 수 있도록 data/ 폴더에 CSV/JSON으로 결과를 떨어뜨린다.
"""
import json
import os

import pandas as pd

from bom import bom_dataframe
from part_master import part_master_df
from demand_data import generate_history
from forecasting import forecast_future
from mrp_engine import run_mrp, summarize_orders, first_action_per_part
from eco_simulator import build_eco_report
import profit_impact
from profit_impact import revenue_at_risk_by_part, service_level_tradeoff

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    history = generate_history()
    history.to_csv(os.path.join(DATA_DIR, "demand_history.csv"), index=False)

    forecast_df, meta = forecast_future(history)
    forecast_df.to_csv(os.path.join(DATA_DIR, "demand_forecast.csv"), index=False)

    bom_df = bom_dataframe()
    bom_df.to_csv(os.path.join(DATA_DIR, "bom.csv"), index=False)

    parts_df = part_master_df()
    parts_df.to_csv(os.path.join(DATA_DIR, "part_master.csv"), index=False)

    mrp_df = run_mrp(forecast_df, meta["resid_std"])
    mrp_df.to_csv(os.path.join(DATA_DIR, "mrp_detail.csv"), index=False)

    order_summary = summarize_orders(mrp_df)
    order_summary.to_csv(os.path.join(DATA_DIR, "order_summary.csv"), index=False)

    first_action = first_action_per_part(mrp_df)
    first_action.to_csv(os.path.join(DATA_DIR, "first_action.csv"), index=False)

    eco_report = build_eco_report(forecast_df, meta["resid_std"], baseline_mrp_df=mrp_df)
    with open(os.path.join(DATA_DIR, "eco_scenarios.json"), "w", encoding="utf-8") as f:
        json.dump(eco_report, f, ensure_ascii=False, indent=2)

    rar_df = revenue_at_risk_by_part(mrp_df, forecast_df)
    rar_df.to_csv(os.path.join(DATA_DIR, "revenue_at_risk.csv"), index=False)
    tradeoff_df = service_level_tradeoff(forecast_df, meta["resid_std"])
    tradeoff_df.to_csv(os.path.join(DATA_DIR, "service_level_tradeoff.csv"), index=False)

    past_due_parts = sorted(first_action[first_action["is_past_due"]]["part_id"].unique().tolist())

    top_risk = rar_df.iloc[0] if not rar_df.empty else None
    baseline_row = tradeoff_df[tradeoff_df["z"] == 1.65].iloc[0]
    best_row = tradeoff_df.loc[tradeoff_df["net_profit_impact_vs_baseline"].idxmax()]

    summary = {
        "product_id": "PE-3000",
        "product_name": "Plasma Etcher PE-3000",
        "chosen_model": meta["chosen_model"],
        "resid_std": meta["resid_std"],
        "backtest": meta["backtest"],
        "total_order_value": float(order_summary["total_order_value"].sum()),
        "n_parts_past_due": len(past_due_parts),
        "past_due_parts": past_due_parts,
        "forecast_horizon_months": len(forecast_df),
        "history_months": len(history),
        "profit_impact": {
            "assumed_asp": profit_impact.ASSUMED_ASP,
            "assumed_gross_margin_pct": profit_impact.ASSUMED_GROSS_MARGIN_PCT,
            "assumed_annual_capital_cost_pct": profit_impact.ASSUMED_ANNUAL_CAPITAL_COST_PCT,
            "top_risk_part_name": top_risk["part_name"] if top_risk is not None else None,
            "top_risk_margin_at_risk": float(top_risk["margin_at_risk"]) if top_risk is not None else 0,
            "baseline_expected_margin_at_risk": float(baseline_row["expected_margin_at_risk"]),
            "best_service_level": best_row["service_level"],
            "best_net_profit_impact": float(best_row["net_profit_impact_vs_baseline"]),
        },
    }
    with open(os.path.join(DATA_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("파이프라인 실행 완료. data/ 폴더에 결과 저장됨:")
    for fname in os.listdir(DATA_DIR):
        print(" -", fname)
    print(f"\n채택 모델: {meta['chosen_model']}")
    print(f"백테스트 MAPE - naive: {meta['backtest']['naive_mape']}% / "
          f"HW: {meta['backtest']['hw_mape']}% / "
          f"SARIMAX+B2B: {meta['backtest']['sarimax_mape']}%")
    print(f"향후 {len(forecast_df)}개월 총 발주 예상 금액: ${summary['total_order_value']:,.0f}")
    print(f"즉시 발주(Past Due) 위험 부품 수: {summary['n_parts_past_due']}개 -> {past_due_parts}")
    print(f"ECN(설계변경/단종) 시뮬레이션 시나리오 {len(eco_report)}건 생성 -> "
          f"{[s['eco_id'] for s in eco_report]}")
    print(f"최대 매출 리스크 부품: {summary['profit_impact']['top_risk_part_name']} "
          f"(마진 리스크 ${summary['profit_impact']['top_risk_margin_at_risk']:,.0f}, 가정치 기반)")
    print(f"서비스수준 트레이드오프: 95%(현재) 대비 최선은 {summary['profit_impact']['best_service_level']} "
          f"(순이익 임팩트 ${summary['profit_impact']['best_net_profit_impact']:+,.0f}, 가정치 기반)")


if __name__ == "__main__":
    main()
