# -*- coding: utf-8 -*-
"""CSV 누적 저장. 같은 날짜는 새 값으로 덮어쓴다(upsert)."""
import pandas as pd

import config


def upsert(csv_path, rows):
    """rows: {date: {col: val}} 를 csv에 병합 저장하고 전체 DataFrame 반환."""
    new = pd.DataFrame.from_dict(rows, orient="index")
    if new.empty:
        return load(csv_path)
    new.index = pd.to_datetime(new.index)
    new.index.name = "date"

    if csv_path.exists():
        old = pd.read_csv(csv_path, index_col="date", parse_dates=True)
        # 새 값이 우선하되, 새 프레임에 없는 컬럼/날짜는 보존
        merged = new.combine_first(old)
        merged = merged.reindex(columns=sorted(set(old.columns) | set(new.columns)))
    else:
        merged = new.reindex(columns=sorted(new.columns))

    merged = merged.sort_index()
    merged.to_csv(csv_path, float_format="%.2f")
    return merged


def load(csv_path):
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path, index_col="date", parse_dates=True).sort_index()


def latest_two(df, col):
    """(최신값, 직전값). 결측은 건너뛴다."""
    if df.empty or col not in df.columns:
        return None, None
    s = df[col].dropna()
    if len(s) == 0:
        return None, None
    if len(s) == 1:
        return s.iloc[-1], None
    return s.iloc[-1], s.iloc[-2]
