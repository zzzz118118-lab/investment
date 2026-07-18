# -*- coding: utf-8 -*-
"""일별 시계열을 주/월/연 평균으로 집계."""
import pandas as pd

import config
import store

# 집계 대상 (크랙/마진 위주. 가격 원계열도 필요하면 추가)
COLS = ["dubai", "brent", "wti", "oman",
        "gasoline95", "kerosene", "diesel005", "hsfo180", "naphtha",
        "crack_gasoline95", "crack_kerosene", "crack_diesel005",
        "crack_hsfo180", "crack_naphtha",
        "simple_margin", "complex_margin"]

# 집계 구간에 최소 이만큼 관측이 있어야 평균을 낸다(부분 구간 왜곡 방지)
MIN_OBS = {"W": 3, "M": 10, "Y": 100}


def _agg(df, rule, min_obs):
    cols = [c for c in COLS if c in df.columns]
    g = df[cols].resample(rule)
    mean = g.mean()
    count = g.count().max(axis=1)
    return mean[count >= min_obs]


def weekly(df, weeks=52):
    """주 평균(금요일 기준). 최근 weeks개."""
    return _agg(df, "W-FRI", MIN_OBS["W"]).tail(weeks)


def monthly(df, months=24):
    return _agg(df, "ME", MIN_OBS["M"]).tail(months)


def yearly(df, years=20):
    return _agg(df, "YE", MIN_OBS["Y"]).tail(years)


def load_all(weeks=52, months=24, years=20):
    df = store.load(config.PRICES_CSV)
    return {
        "daily": df,
        "weekly": weekly(df, weeks),
        "monthly": monthly(df, months),
        "yearly": yearly(df, years),
    }


if __name__ == "__main__":
    a = load_all()
    show = ["dubai", "crack_kerosene", "crack_diesel005", "simple_margin", "complex_margin"]

    print("=== 연 평균 (최근 20년) ===")
    y = a["yearly"][show].copy()
    y.index = y.index.year
    print(y.round(1).to_string())

    print("\n=== 월 평균 (최근 24개월) ===")
    m = a["monthly"][show].copy()
    m.index = m.index.strftime("%Y-%m")
    print(m.round(1).to_string())

    print("\n=== 주 평균 (최근 8주만 표시 / 총 %d주) ===" % len(a["weekly"]))
    w = a["weekly"][show].tail(8).copy()
    w.index = w.index.strftime("%Y-%m-%d")
    print(w.round(1).to_string())
