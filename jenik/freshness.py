# -*- coding: utf-8 -*-
"""데이터 소스별 최신성 점검.

자동 수집이 불가능한 소스(아마존 순위, 검색량)는 사람이 갱신해야 한다.
갱신을 잊는 게 이 프로젝트의 가장 현실적인 실패 모드라서, **언제 갱신할지를
자동으로 알려주는 것**까지가 자동화 범위다.

각 소스마다 기대 주기(days)를 두고 그 두 배를 넘기면 경고로 올린다.
status.json으로도 떨어뜨려 외부에서 확인할 수 있게 한다.
"""
import json
from datetime import date, datetime

import pandas as pd

import config
import store


def _age(d):
    if d is None:
        return None
    if isinstance(d, str):
        d = pd.to_datetime(d)
    if isinstance(d, (pd.Timestamp, datetime)):
        d = d.date()
    return (date.today() - d).days


def check():
    """[{name, auto, last, age, period, stale, note}] 반환."""
    out = []

    def add(name, auto, last, period, note=""):
        age = _age(last)
        out.append({
            "name": name, "auto": auto,
            "last": None if last is None else str(
                last.date() if hasattr(last, "date") else last),
            "age": age, "period": period,
            "stale": age is not None and age > period * 2,
            "note": note,
        })

    # ── 자동 ──────────────────────────────────────────────────────
    ex = store.load(config.EXPORTS_CSV)
    # 관세청은 매월 15일경 전월치를 넣는다. 기준월 자체가 한 달 뒤처지는 게 정상이라
    # '수집 시점'이 아니라 '기준월'로 본다.
    add("마스크팩 수출 (관세청)", True,
        ex.index.max() if not ex.empty else None, 45,
        "매월 15일경 전월 확정")

    px = store.load(config.PRICE_CSV)
    add("주가 (네이버)", True,
        px.index.max() if not px.empty else None, 1, "매 실행")

    fin = config.DATA / "financials.csv"
    if fin.exists():
        f = pd.read_csv(fin)
        add("실적·컨센서스 (네이버)", True,
            f.fetched.max() if "fetched" in f else None, 1, "매 실행")

    # ── 수동 ──────────────────────────────────────────────────────
    import amazon
    az = amazon.for_node()
    add("아마존 순위", False,
        az.date.max() if not az.empty else None, 30,
        "capture.js → amazon.py --ingest")

    import searches
    sc = searches.actual()
    add("바이오던스 검색량", False,
        sc.date.max() if not sc.empty else None, 30,
        "Exploding Topics 내보내기 → searches.py --ingest")

    return out


def write_status(path=None):
    rows = check()
    path = path or (config.SITE / "status.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "sources": rows,
        "stale": [r["name"] for r in rows if r["stale"]],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    for r in check():
        flag = "  경고" if r["stale"] else ""
        print("%-24s %s  최신 %-12s %3s일 전%s"
              % (r["name"], "자동" if r["auto"] else "수동",
                 r["last"] or "-", r["age"] if r["age"] is not None else "-", flag))
