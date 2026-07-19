# -*- coding: utf-8 -*-
"""네이버 실적·컨센서스 누적 저장.

    python financials.py        # 수집 + 저장 + 요약

price.py가 매번 새로 긁어 쓰기만 하던 걸 CSV로 쌓는다. 두 가지를 얻는다:

1. **분기 실적이 자동으로 늘어난다.** 네이버는 최근 6분기만 보여주고 창이
   밀리므로, 쌓아두지 않으면 과거 분기를 영영 잃는다. 동행 차트가 1Q24까지
   거슬러 가려면 하드코딩이 필요했는데 이제 쌓인 값이 이를 대체한다.
   2Q26 실적이 발표되면 **아무것도 안 해도** 차트가 늘어난다.

2. **컨센서스 변화를 추적한다.** 추정치가 바뀔 때만 한 줄 남긴다.
   상향/하향 자체가 신호라서 값보다 변화 이력이 중요하다.
"""
import sys
from datetime import date

import pandas as pd

import config
import price

CSV = config.DATA / "financials.csv"
CONSENSUS_CSV = config.DATA / "consensus_history.csv"

COLS = ["period", "kind", "is_estimate", "revenue", "op", "np",
        "op_margin", "np_margin", "eps", "bps", "per", "pbr", "roe", "fetched"]


def _rows(df, kind):
    out = []
    for idx in df.index:
        p = price.parse_period(idx)
        if not p:
            continue
        y, m, is_est = p
        r = {"period": "%d.%02d" % (y, m), "kind": kind,
             "is_estimate": is_est, "fetched": date.today().isoformat()}
        for c in ["revenue", "op", "np", "op_margin", "np_margin",
                  "eps", "bps", "per", "pbr", "roe"]:
            v = df.at[idx, c] if c in df.columns else None
            r[c] = None if v is None or pd.isna(v) else float(v)
        out.append(r)
    return out


def load():
    if not CSV.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(CSV, dtype={"period": str})


def update():
    d = price.fetch_all()
    new = pd.DataFrame(_rows(d["annual"], "annual") +
                       _rows(d["quarterly"], "quarterly"))
    if new.empty:
        return None, 0
    new = new.reindex(columns=COLS)

    old = load()
    # 컨센서스 변화 감지 — 값이 바뀐 추정치만 이력에 남긴다
    changes = 0
    if not old.empty:
        prev = old.set_index(["period", "kind"])
        hist = []
        for _, r in new[new.is_estimate].iterrows():
            key = (r.period, r.kind)
            if key not in prev.index:
                continue
            p = prev.loc[key]
            p = p.iloc[-1] if isinstance(p, pd.DataFrame) else p
            for c in ["revenue", "op", "eps"]:
                a, b = p.get(c), r.get(c)
                if pd.notna(a) and pd.notna(b) and abs(float(a) - float(b)) > 1e-9:
                    hist.append({"date": date.today().isoformat(),
                                 "period": r.period, "kind": r.kind,
                                 "metric": c, "before": float(a), "after": float(b)})
                    changes += 1
        if hist:
            h = pd.DataFrame(hist)
            if CONSENSUS_CSV.exists():
                h = pd.concat([pd.read_csv(CONSENSUS_CSV), h], ignore_index=True)
            h.to_csv(CONSENSUS_CSV, index=False, encoding="utf-8")

    # 확정 실적은 덮어쓰지 않는다. 네이버가 창을 밀어도 과거가 남는다.
    merged = new if old.empty else pd.concat([old, new], ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "kind"], keep="last")
    merged = merged.sort_values(["kind", "period"])
    merged.to_csv(CSV, index=False, encoding="utf-8")
    return merged, changes


def quarterly_revenue():
    """(year, quarter) -> 매출(억원). 확정 실적만.

    쌓인 CSV를 우선하고, CSV보다 앞선 과거는 config의 리포트 값으로 채운다.
    """
    out = dict(config.QUARTERLY_REVENUE)
    df = load()
    if df.empty:
        return out
    q = df[(df.kind == "quarterly") & (~df.is_estimate.astype(bool))]
    for _, r in q.iterrows():
        if pd.isna(r.revenue):
            continue
        y, m = str(r.period).split(".")
        out[(int(y), (int(m) + 2) // 3)] = float(r.revenue)
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    df, changes = update()
    if df is None:
        raise SystemExit("수집 실패")
    print("저장: %d행 (연간 %d, 분기 %d)"
          % (len(df), (df.kind == "annual").sum(), (df.kind == "quarterly").sum()))
    if changes:
        print("컨센서스 변경 %d건 — %s 참조" % (changes, CONSENSUS_CSV.name))
    qr = quarterly_revenue()
    print("\n[분기 매출 (억원)]")
    for k in sorted(qr):
        print("  %dQ%02d  %s" % (k[1], k[0] % 100, "{:,.0f}".format(qr[k])))
