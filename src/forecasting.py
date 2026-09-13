"""
AI 수요예측 모듈.

두 모델을 비교한다.
  1) Holt-Winters 지수평활법 (추세+계절성만 사용하는 고전적 통계 모델, baseline)
  2) SARIMAX + Book-to-Bill Ratio 외부변수 (반도체 장비 업계 실제 선행지표를 반영한 모델)

SARIMAX 모델은 Book-to-Bill Ratio를 B2B_LEAD_MONTHS(3개월) 만큼 지연시켜 설명변수로 사용한다.
B2B는 실제로 수주/출하 사이클을 선행하는 지표이기 때문에, 이미 관측된 과거 B2B 값만으로
향후 몇 개월의 수요 변화를 더 정확히 예측할 수 있다는 것이 이 모델의 핵심 아이디어다.
(단, 예측 지평이 리드타임(3개월)을 넘어가는 구간은 최신 B2B 값을 그대로 이월(carry-forward)한다는
전망치 부재 가정을 둔다 — 이는 report.md에 한계로 명시한다.)

두 모델 모두 naive 계절 예측(작년 동월 값)과 비교해서 MAPE 개선폭을 확인한다.
"""
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from demand_data import generate_history, FORECAST_HORIZON, B2B_LEAD_MONTHS


def _mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)


def _build_series(history: pd.DataFrame):
    idx = pd.PeriodIndex(history["period"], freq="M")
    y = pd.Series(history["units_shipped"].astype(float).values, index=idx)
    b2b = pd.Series(history["book_to_bill"].astype(float).values, index=idx)
    return y, b2b


def _exog_for_periods(b2b: pd.Series, periods: pd.PeriodIndex, lead: int = B2B_LEAD_MONTHS) -> pd.Series:
    """periods 각 시점 t에 대해 b2b[t - lead] 값을 반환. 없으면(미래 B2B 미관측) 마지막 관측값으로 이월."""
    last_known = b2b.iloc[-1]
    vals = []
    for p in periods:
        src = p - lead
        vals.append(b2b.get(src, last_known))
    return pd.Series(vals, index=periods)


def backtest(history: pd.DataFrame, holdout: int = 6) -> dict:
    y, b2b = _build_series(history)
    y_train, y_test = y.iloc[:-holdout], y.iloc[-holdout:]

    # 1) Holt-Winters
    hw_model = ExponentialSmoothing(
        y_train, trend="add", seasonal="add", seasonal_periods=12, initialization_method="estimated"
    ).fit()
    hw_pred = hw_model.forecast(holdout)

    # 2) SARIMAX + B2B 선행지표 (동일 36개월 이력 내 backtest이므로 실제 관측된 과거 B2B 사용 -> 룩어헤드 없음)
    exog_train = _exog_for_periods(b2b, y_train.index)
    exog_test = _exog_for_periods(b2b, y_test.index)
    sarimax_model = SARIMAX(
        y_train, exog=exog_train.values.reshape(-1, 1),
        order=(1, 1, 1), seasonal_order=(1, 0, 0, 12),
        enforce_stationarity=False, enforce_invertibility=False,
    ).fit(disp=False)
    sarimax_pred = sarimax_model.forecast(holdout, exog=exog_test.values.reshape(-1, 1))

    # 3) naive 계절 baseline
    naive_pred = y_train.iloc[-12:-12 + holdout].values if len(y_train) >= 12 + holdout else y_train.iloc[-holdout:].values

    return {
        "periods": [str(p) for p in y_test.index],
        "test_actual": y_test.tolist(),
        "hw_pred": [round(v, 1) for v in hw_pred.tolist()],
        "sarimax_pred": [round(v, 1) for v in sarimax_pred.tolist()],
        "naive_pred": [round(float(v), 1) for v in naive_pred],
        "hw_mape": round(_mape(y_test.values, hw_pred.values), 1),
        "sarimax_mape": round(_mape(y_test.values, sarimax_pred.values), 1),
        "naive_mape": round(_mape(y_test.values, naive_pred), 1),
    }


def forecast_future(history: pd.DataFrame, horizon: int = FORECAST_HORIZON) -> tuple[pd.DataFrame, dict]:
    """전체 이력으로 재학습해서 향후 horizon개월을 예측 (신뢰구간 포함). 성능이 더 좋은 모델을 채택."""
    y, b2b = _build_series(history)
    bt = backtest(history, holdout=6)
    use_sarimax = bt["sarimax_mape"] <= bt["hw_mape"]

    future_periods = pd.period_range(y.index[-1] + 1, periods=horizon, freq="M")

    if use_sarimax:
        exog_all = _exog_for_periods(b2b, y.index)
        exog_future = _exog_for_periods(b2b, future_periods)
        model = SARIMAX(
            y, exog=exog_all.values.reshape(-1, 1),
            order=(1, 1, 1), seasonal_order=(1, 0, 0, 12),
            enforce_stationarity=False, enforce_invertibility=False,
        ).fit(disp=False)
        pred = model.get_forecast(horizon, exog=exog_future.values.reshape(-1, 1))
        mean = pred.predicted_mean.values
        ci = pred.conf_int(alpha=0.10)  # 90% CI
        lower, upper = ci.iloc[:, 0].values, ci.iloc[:, 1].values
        resid_std = float(np.std(model.resid[12:]))  # 초기 계절 워밍업 구간 제외
        model_name = "SARIMAX + Book-to-Bill Ratio"
    else:
        model = ExponentialSmoothing(
            y, trend="add", seasonal="add", seasonal_periods=12, initialization_method="estimated"
        ).fit()
        mean = model.forecast(horizon).values
        resid_std = float(np.std(model.resid))
        z90 = 1.645
        lower = np.clip(mean - z90 * resid_std, 0, None)
        upper = mean + z90 * resid_std
        model_name = "Holt-Winters"

    df = pd.DataFrame({
        "period": future_periods.astype(str),
        "forecast_units": np.round(mean, 1),
        "lower_90": np.round(np.clip(lower, 0, None), 1),
        "upper_90": np.round(upper, 1),
    })
    meta = {
        "chosen_model": model_name,
        "resid_std": round(resid_std, 2),
        "backtest": bt,
    }
    return df, meta


if __name__ == "__main__":
    hist = generate_history()
    bt = backtest(hist)
    print("=== Backtest (최근 6개월 홀드아웃) ===")
    print(f"Naive(작년 동월) MAPE:              {bt['naive_mape']}%")
    print(f"Holt-Winters MAPE:                  {bt['hw_mape']}%")
    print(f"SARIMAX + Book-to-Bill Ratio MAPE:  {bt['sarimax_mape']}%")
    print()
    fc, meta = forecast_future(hist)
    print(f"=== 향후 6개월 예측 (채택 모델: {meta['chosen_model']}) ===")
    print(fc.to_string(index=False))
    print(f"\n잔차 표준편차 (안전재고 계산에 사용): {meta['resid_std']:.2f}")
