# -*- coding: utf-8 -*-
"""아마존 Best Sellers 순위 스냅샷 적립.

    python amazon.py --ingest snap.json    # 캡처 JSON을 CSV에 적립
    python amazon.py                       # 현재 적립 상태 요약

수집은 사람이 브라우저로 한다(capture.js). 자동 스크래핑을 하지 않는 이유는
README '왜 수동인가' 참조 — 아마존 ToS와 봇 차단 때문이다.

CSV는 long 포맷이다. 같은 (date, node, asin)이 다시 들어오면 덮어쓴다.
"""
import json
import sys
from pathlib import Path

import pandas as pd

import config

CSV = config.DATA / "amazon_rank.csv"
COLS = ["date", "node", "rank", "asin", "title", "rating", "reviews"]


def load():
    if not CSV.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(CSV, dtype={"node": str, "asin": str})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "node", "rank"])


def ingest(path):
    """capture.js 출력 JSON을 적립하고 (신규행수, 전체 df) 반환."""
    raw = Path(path).read_text(encoding="utf-8").strip()
    # 콘솔이 따옴표로 감싼 문자열을 뱉는 경우가 있어 한 번 더 푼다
    snap = json.loads(raw)
    if isinstance(snap, str):
        snap = json.loads(snap)

    items = snap.get("items", [])
    if len(items) < 20:
        print("  [경고] 항목이 %d개뿐입니다. 셀렉터가 깨졌을 수 있습니다." % len(items))

    new = pd.DataFrame(items)
    if new.empty:
        raise SystemExit("빈 스냅샷입니다.")
    new["date"] = pd.to_datetime(snap["date"])
    new["node"] = str(snap.get("node", ""))
    new = new.reindex(columns=COLS)

    old = load()
    # 빈 프레임을 concat하면 dtype 경고가 난다. 첫 적립이면 그냥 새 것을 쓴다.
    merged = new if old.empty else pd.concat([old, new], ignore_index=True)
    # 나중에 들어온 값이 이긴다
    merged = merged.drop_duplicates(subset=["date", "node", "asin"], keep="last")
    merged = merged.sort_values(["date", "node", "rank"])
    merged.to_csv(CSV, index=False, encoding="utf-8")
    return len(new), merged


def for_node(df=None, node=None):
    """현재 추적 노드의 행만. 노드가 바뀐 이력이 있어 반드시 걸러야 한다.

    같은 날 두 노드를 캡처하면 순위가 뒤섞인다 — 서로 다른 순위 체계다.
    """
    df = load() if df is None else df
    return df[df.node == (node or config.AMAZON_NODE)]


def latest(df=None, node=None):
    """가장 최근 스냅샷 한 장 (현재 노드 기준)."""
    df = for_node(df, node)
    if df.empty:
        return df
    return df[df.date == df.date.max()].sort_values("rank")


def history(asin, df=None, node=None):
    """한 ASIN의 순위 추이 (date -> rank). 순위 밖으로 나간 날은 결측."""
    df = for_node(df, node)
    if df.empty:
        return pd.Series(dtype=float)
    s = df[df.asin == asin].set_index("date")["rank"]
    return s.reindex(sorted(df.date.unique()))


def tracked(df=None):
    """추적 대상 ASIN — config.WATCH에 있거나 마스크 키워드가 잡히는 품목."""
    df = load() if df is None else df
    if df.empty:
        return []
    hit = set(config.WATCH_ASINS)
    for _, r in df.iterrows():
        t = str(r.title)
        if any(k in t for k in config.MASK_KEYWORDS):
            hit.add(r.asin)
    return sorted(hit)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if "--ingest" in sys.argv:
        n, df = ingest(sys.argv[sys.argv.index("--ingest") + 1])
        print("적립: %d행 → 누적 %d행, 스냅샷 %d장"
              % (n, len(df), df.date.nunique()))
    else:
        df = load()
        if df.empty:
            raise SystemExit("적립된 스냅샷이 없습니다. capture.js 참조.")
        print("스냅샷 %d장  %s ~ %s"
              % (df.date.nunique(), df.date.min().date(), df.date.max().date()))

    for nd, g in df.groupby("node"):
        tag = "현재" if nd == config.AMAZON_NODE else "과거 노드"
        print("  node %s (%s): %d장" % (nd, tag, g.date.nunique()))

    cur = latest(df)
    if cur.empty:
        raise SystemExit("현재 노드(%s)의 스냅샷이 없습니다." % config.AMAZON_NODE)
    print("\n[최신 TOP 20]")
    for _, r in cur.iterrows():
        mark = " ★" if r.asin in config.WATCH_ASINS else ""
        print("  #%-2d %s  %s%s" % (r["rank"], r.asin, str(r.title)[:52], mark))
