# -*- coding: utf-8 -*-
"""하나증권 참조표(data/hana_reference.csv)를 prices.csv에 병합한다.

페트로넷 상세 테이블은 최근 7영업일만 주므로 그 이전 날짜는 나프타·중유가
비어 마진을 계산할 수 없다. 하나증권 표에 크랙이 실려 있으므로 이를 채워
넣으면 마진 시계열을 앞으로 연장할 수 있다.

크랙 + Dubai 로 제품가도 복원한다(원표가 소수 첫째자리 반올림이라
소수점 이하 오차가 있을 수 있음).
"""
import pandas as pd

import config
import margin
import store

# 하나증권 표 컬럼 -> 내부 컬럼
CRACK_MAP = {
    "crack_naphtha":  "crack_naphtha",
    "crack_gasoline": "crack_gasoline95",
    "crack_kerosene": "crack_kerosene",
    "crack_diesel":   "crack_diesel005",
    "crack_bc":       "crack_hsfo180",
}
PRICE_OF = {
    "crack_naphtha":    "naphtha",
    "crack_gasoline95": "gasoline95",
    "crack_kerosene":   "kerosene",
    "crack_diesel005":  "diesel005",
    "crack_hsfo180":    "hsfo180",
}

REF = config.DATA / "hana_reference.csv"


def main():
    if not REF.exists():
        print("참조 파일 없음: %s" % REF)
        return

    ref = pd.read_csv(REF, parse_dates=["date"]).set_index("date")
    existing = store.load(config.PRICES_CSV)

    rows = {}
    for d, r in ref.iterrows():
        day = d.date()
        row = {"dubai": r["dubai"]}

        for src, dst in CRACK_MAP.items():
            if pd.notna(r.get(src)):
                row[dst] = float(r[src])
                row[PRICE_OF[dst]] = round(float(r[src]) + float(r["dubai"]), 2)

        # 하나증권 공표값을 마진의 정본으로 삼는다(자체 산출보다 우선)
        if pd.notna(r.get("complex_crack")):
            row["complex_margin"] = float(r["complex_crack"])
        if pd.notna(r.get("simple_crack")):
            row["simple_margin"] = float(r["simple_crack"])
        if pd.notna(r.get("osp_arab_light")):
            row["osp_arab_light"] = float(r["osp_arab_light"])
        if pd.notna(r.get("osp_arab_medium")):
            row["osp_arab_medium"] = float(r["osp_arab_medium"])

        rows[day] = row

    # 페트로넷 실측이 있는 날짜는 그쪽이 정밀하므로 덮어쓰지 않는다.
    # (store.upsert는 new가 우선이므로, 이미 값이 있는 칸은 제거)
    if not existing.empty:
        for day, row in rows.items():
            ts = pd.Timestamp(day)
            if ts not in existing.index:
                continue
            for col in list(row):
                if col in ("complex_margin", "simple_margin",
                           "osp_arab_light", "osp_arab_medium"):
                    continue  # 마진/OSP는 하나증권 값을 우선
                if col in existing.columns and pd.notna(existing.at[ts, col]):
                    del row[col]

    df = store.upsert(config.PRICES_CSV, rows)
    print("병합 완료: %d행 x %d열" % (len(df), len(df.columns)))
    cols = [c for c in ["dubai", "osp_arab_light", "crack_kerosene",
                        "crack_diesel005", "simple_margin", "complex_margin"]
            if c in df.columns]
    print(df[cols].to_string())


if __name__ == "__main__":
    main()
