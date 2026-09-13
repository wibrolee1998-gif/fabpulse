"""data/ 밑의 산출물을 대시보드(HTML)에 그대로 embed할 수 있는 하나의 JSON으로 묶는다."""
import json
import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "dashboard_bundle.json")


def records(df: pd.DataFrame) -> list:
    """df.to_dict(orient='records')는 결측치(None)가 CSV 왕복 과정에서 NaN(float)으로 바뀌어
    json.dump가 유효하지 않은 'NaN' 토큰을 그대로 써버리는 문제가 있다 (JS JSON.parse가 못 읽음).
    to_json은 NaN을 표준 JSON의 null로 안전하게 직렬화하므로 이를 거쳐서 되읽는다."""
    return json.loads(df.to_json(orient="records"))


def main():
    history = pd.read_csv(os.path.join(DATA_DIR, "demand_history.csv"))
    forecast = pd.read_csv(os.path.join(DATA_DIR, "demand_forecast.csv"))
    bom = pd.read_csv(os.path.join(DATA_DIR, "bom.csv"))
    parts = pd.read_csv(os.path.join(DATA_DIR, "part_master.csv"))
    mrp = pd.read_csv(os.path.join(DATA_DIR, "mrp_detail.csv"))
    order_summary = pd.read_csv(os.path.join(DATA_DIR, "order_summary.csv"))
    first_action = pd.read_csv(os.path.join(DATA_DIR, "first_action.csv"))
    revenue_at_risk = pd.read_csv(os.path.join(DATA_DIR, "revenue_at_risk.csv"))
    service_level_tradeoff = pd.read_csv(os.path.join(DATA_DIR, "service_level_tradeoff.csv"))
    with open(os.path.join(DATA_DIR, "summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    with open(os.path.join(DATA_DIR, "eco_scenarios.json"), encoding="utf-8") as f:
        eco_scenarios = json.load(f)

    bundle = {
        "summary": summary,
        "history": records(history),
        "forecast": records(forecast),
        "bom": records(bom),
        "parts": records(parts),
        "mrp": records(mrp),
        "order_summary": records(order_summary),
        "first_action": records(first_action),
        "eco_scenarios": eco_scenarios,
        "revenue_at_risk": records(revenue_at_risk),
        "service_level_tradeoff": records(service_level_tradeoff),
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"저장됨: {OUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
