# -*- coding: utf-8 -*-
"""바이오던스 브랜드 검색량 (Exploding Topics 내보내기 CSV).

    python searches.py --ingest "C:/Users/sungh/Downloads/biodance-xxxx.csv"
    python searches.py                      # 적립 상태 요약

원본 CSV는 첫 행에만 메타데이터가 들어 있고 나머지 행은 Searches/Date 두 칸만
채워진 희소 포맷이다. 필요한 건 그 두 칸뿐이다.

**예측치 주의.** 파일은 미래 날짜까지 포함한다. 메타의 `Volume`이 '현재 월
검색량'이라 그 값과 일치하는 마지막 행이 실측 경계다. 그 이후는 예측이므로
`is_forecast` 플래그를 세워 대시보드에서 갈라 그린다.

**토픽 주의.** 이 CSV의 Description은 1960년대 롤란도 토로의 무용치료
'Biodance'를 설명한다. K뷰티 브랜드가 아니다. 다만 2023년 9월 이전 검색량이
0이고 그 뒤 폭증하는 형태라 실제 시계열은 브랜드 검색으로 보인다. 동음이의로
인한 오염 가능성은 남아 있다.
"""
import sys
from pathlib import Path

import pandas as pd

import config

CSV = config.DATA / "searches.csv"


def ingest(path):
    raw = pd.read_csv(path)
    if "Searches" not in raw.columns or "Date" not in raw.columns:
        raise SystemExit("Searches/Date 컬럼이 없습니다. 다른 포맷의 파일 같습니다.")

    df = raw[["Date", "Searches"]].dropna()
    df["date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    df["searches"] = pd.to_numeric(df["Searches"], errors="coerce")
    df = df[["date", "searches"]].dropna().sort_values("date").reset_index(drop=True)

    # 실측/예측 경계 — 메타의 Volume과 일치하는 마지막 행까지가 실측이다.
    # Volume이 없으면 보수적으로 전월까지만 실측으로 본다.
    vol = pd.to_numeric(raw.get("Volume"), errors="coerce").dropna()
    cutoff = None
    if len(vol):
        hit = df[df.searches == vol.iloc[0]]
        if not hit.empty:
            cutoff = hit.date.max()
    if cutoff is None:
        today = pd.Timestamp.today().normalize().replace(day=1)
        cutoff = today - pd.DateOffset(months=1)
        print("  [경고] Volume으로 경계를 못 찾아 %s까지를 실측으로 봅니다."
              % cutoff.date())

    df["is_forecast"] = df.date > cutoff
    df.to_csv(CSV, index=False, encoding="utf-8")
    return df, cutoff


def load():
    if not CSV.exists():
        return pd.DataFrame(columns=["date", "searches", "is_forecast"])
    df = pd.read_csv(CSV, parse_dates=["date"])
    df["is_forecast"] = df["is_forecast"].astype(bool)
    return df.sort_values("date")


def actual():
    df = load()
    return df[~df.is_forecast]


def quarterly(include_forecast=False):
    """분기 합계 (date 튜플 (year, quarter) -> 검색량). 부분 분기는 제외한다."""
    df = load()
    if not include_forecast:
        df = df[~df.is_forecast]
    if df.empty:
        return pd.Series(dtype=float)
    g = df.groupby([df.date.dt.year, df.date.dt.quarter])
    q = g.searches.sum()
    # 3개월이 다 차지 않은 분기는 합계가 왜곡되므로 뺀다
    return q[g.searches.count() == 3]


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if "--ingest" in sys.argv:
        df, cutoff = ingest(sys.argv[sys.argv.index("--ingest") + 1])
        n_act = (~df.is_forecast).sum()
        print("적립: %d개월 (실측 %d, 예측 %d) · 실측 경계 %s"
              % (len(df), n_act, df.is_forecast.sum(), cutoff.date()))
    else:
        df = load()
        if df.empty:
            raise SystemExit("적립된 검색량이 없습니다. --ingest 로 넣으세요.")

    a = actual()
    print("\n[실측 최근 12개월]")
    print(a.tail(12).assign(searches=lambda d: d.searches.map("{:,.0f}".format))
          [["date", "searches"]].to_string(index=False))
    print("\n[분기 합계]")
    print(quarterly().map("{:,.0f}".format).to_string())
