"""
PE-3000 완제품 월별 출하량 + Book-to-Bill Ratio(B2B, 선행지표) 합성 이력 데이터 생성.

반영한 반도체 장비 산업 특성 (실무에서 널리 쓰이는 패턴을 단순화):
  - 장기 성장 추세 (AI 반도체 투자 확대에 따른 CAPEX 증가)
  - 반도체 CAPEX 업다운 사이클 (약 24개월 주기의 붐/다운턴)
  - 분기말 밀어내기 수주 (3,6,9,12월에 소폭 집중되는 경향)
  - 랜덤 노이즈
  - SEMI Book-to-Bill Ratio: 반도체 장비 업계에서 실제로 발표되는 "수주액/출하액" 선행지표.
    이 값이 1.0을 넘으면 수주가 출하보다 많다는 뜻으로, 통상 2~3개월 뒤 출하 증가로 이어진다.
    이 프로젝트에서는 B2B가 향후 출하 사이클을 3개월 리드해서 반영하도록 합성했고,
    수요예측 모델에 외부 선행지표(exogenous feature)로 사용한다.
"""
import numpy as np
import pandas as pd

SEED = 42
N_HISTORY_MONTHS = 36
HISTORY_END = pd.Period("2026-08", freq="M")  # 마지막 실적월
FORECAST_HORIZON = 6  # 향후 6개월 예측
B2B_LEAD_MONTHS = 3  # Book-to-Bill이 출하 사이클을 선행하는 개월 수


def _cycle(t):
    return np.sin(2 * np.pi * t / 24 + 0.6)


def generate_history(n_months: int = N_HISTORY_MONTHS, end_period: pd.Period = HISTORY_END) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    periods = pd.period_range(end=end_period, periods=n_months, freq="M")
    t = np.arange(n_months)

    base_level = 14.0
    trend = 0.18 * t  # 완만한 우상향 (월간 대수 기준)
    capex_cycle = 4.5 * _cycle(t)  # 24개월 CAPEX 사이클
    quarter_end_bump = np.array([2.0 if (p.month in (3, 6, 9, 12)) else 0.0 for p in periods])
    noise = rng.normal(0, 1.3, size=n_months)

    units = base_level + trend + capex_cycle + quarter_end_bump + noise
    units = np.clip(units, 3, None)
    units = np.round(units).astype(int)

    # Book-to-Bill Ratio: t+LEAD 시점의 사이클을 3개월 먼저 반영 (선행지표), 자체 노이즈 추가
    b2b_noise = rng.normal(0, 0.05, size=n_months)
    b2b = 1.0 + 0.11 * _cycle(t + B2B_LEAD_MONTHS) + b2b_noise
    b2b = np.round(b2b, 2)

    df = pd.DataFrame({
        "period": periods.astype(str),
        "units_shipped": units,
        "book_to_bill": b2b,
    })
    return df


if __name__ == "__main__":
    df = generate_history()
    print(df.to_string(index=False))
    print("\n요약 통계:")
    print(df[["units_shipped", "book_to_bill"]].describe())
