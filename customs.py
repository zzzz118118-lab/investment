# -*- coding: utf-8 -*-
"""윤활기유 수출단가 (관세청 품목별 수출입실적 API).

HS 2710195020 = '윤활유 기유(基油)'. 페트로넷의 '윤활유'(더 넓은 분류)보다
정확하고, 무엇보다 빠르다. 관세청은 매월 15일경 전월 자료를 반영하므로
7월 중순이면 6월치가 이미 나와 있다. 페트로넷 확정치는 2개월 늦다.

단가 = 수출금액(USD) / 수출중량(kg) * 1000  ->  $/ton
증권사 리포트가 쓰는 단위와 같아 바로 대조된다.

인증키:
  로컬  .env 의 DATA_GO_KR_KEY
  CI    환경변수 DATA_GO_KR_KEY (GitHub 시크릿)

API 제약:
  - hsSgn 은 6자리까지만 먹는다. 10자리를 넣으면 빈 결과가 온다.
    271019로 조회한 뒤 hsCode == 2710195020 인 행만 골라낸다.
  - 조회 구간이 길면 빈 결과가 온다. 연 단위로 끊어 요청한다.
"""
import os
import re
import warnings
from datetime import date
from pathlib import Path

import requests

import config
import store

warnings.filterwarnings("ignore")

URL = "http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
HS6 = "271019"
HS10 = "2710195020"          # 윤활유 기유(基油)
CSV = config.DATA / "baseoil.csv"


def _key():
    k = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if k:
        return k
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").split("\n"):
            if line.startswith("DATA_GO_KR_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _tag(block, name):
    m = re.search(r"<%s>(.*?)</%s>" % (name, name), block, re.S)
    return m.group(1).strip() if m else ""


def fetch_year(year, key=None):
    """한 해치를 조회해 {date: {...}} 반환."""
    key = key or _key()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY 없음")
    r = requests.get(URL, timeout=120, verify=False, params={
        "serviceKey": key, "strtYymm": "%d01" % year,
        "endYymm": "%d12" % year, "hsSgn": HS6})
    out = {}
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        if _tag(it, "hsCode") != HS10:
            continue
        ym = _tag(it, "year")            # '2026.05'
        m = re.match(r"(\d{4})\.(\d{2})", ym)
        if not m:
            continue
        try:
            val = float(_tag(it, "expDlr") or 0)
            wgt = float(_tag(it, "expWgt") or 0)
        except ValueError:
            continue
        if wgt <= 0:
            continue
        out[date(int(m.group(1)), int(m.group(2)), 1)] = {
            "baseoil_value": val,
            "baseoil_weight": wgt,
            "baseoil_usd_ton": round(val / wgt * 1000, 1),
        }
    return out


def update(start_year=2015):
    """start_year부터 올해까지 수집해 CSV에 누적."""
    rows = {}
    for y in range(start_year, date.today().year + 1):
        try:
            rows.update(fetch_year(y))
        except Exception as e:
            print("    %d년 실패: %s" % (y, str(e)[:60]))
    if not rows:
        return None
    return store.upsert(CSV, rows)


if __name__ == "__main__":
    import sys
    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    df = update()
    if df is None:
        print("수집 실패")
    else:
        print("%d개월  %s ~ %s" % (len(df), df.index.min().date(), df.index.max().date()))
        print(df.tail(14)[["baseoil_usd_ton"]].to_string())
