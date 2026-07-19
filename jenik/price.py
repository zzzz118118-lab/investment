# -*- coding: utf-8 -*-
"""제닉(123330) 주가·컨센서스 수집 (네이버 금융)."""
import io
import re
import warnings
from datetime import date

import pandas as pd
import requests

import config
import store

warnings.filterwarnings("ignore")

URL = "https://finance.naver.com/item/main.naver?code=" + config.CODE
HEADERS = {"User-Agent": config.UA}

ROWS = {
    "매출액": "revenue", "영업이익": "op", "당기순이익": "np",
    "영업이익률": "op_margin", "순이익률": "np_margin",
    "EPS(원)": "eps", "BPS(원)": "bps", "PER(배)": "per", "PBR(배)": "pbr",
    "ROE(지배주주)": "roe",
}


def _page():
    return requests.get(URL, headers=HEADERS, timeout=config.TIMEOUT,
                        verify=False).content.decode("utf-8", "replace")


def fetch_price(html=None):
    h = html or _page()
    out = {}
    m = re.search(r'<p class="no_today">.*?<span class="blind">([\d,]+)</span>', h, re.S)
    if m:
        out["price"] = int(m.group(1).replace(",", ""))
    m = re.search(r'<p class="no_exday">(.*?)</p>', h, re.S)
    if m:
        seg = m.group(1)
        nums = re.findall(r'<span class="blind">([\d,.]+)</span>', seg)
        sign = -1 if ("ico down" in seg or "하락" in seg) else 1
        if len(nums) >= 2:
            out["change"] = sign * int(nums[0].replace(",", ""))
            out["change_pct"] = sign * float(nums[1])
    # 시가총액은 전용 id로 잡는다. '시가총액' 문자열 검색은 동일업종 비교표의
    # 다른 종목을 물 수 있다. 표기는 '1,869' (억) 또는 '1조 2,000' 형태.
    m = re.search(r'id="_market_sum"[^>]*>([^<]+)<', h)
    if m:
        s = m.group(1).replace(",", "").strip()
        mm = re.match(r"(?:(\d+)조)?\s*(\d+)?", s)
        if mm:
            out["mktcap"] = (int(mm.group(1)) if mm.group(1) else 0) * 10000 + \
                            (int(mm.group(2)) if mm.group(2) else 0)
    return out


def fetch_performance(html=None):
    """기업실적분석 표 -> (연간 df, 분기 df). 단위 억원/원/%."""
    h = html or _page()
    i = h.find("기업실적분석")
    m = re.search(r"<table.*?</table>", h[i:], re.S | re.I)
    if not m:
        raise RuntimeError("기업실적분석 표를 찾지 못했습니다")
    df = pd.read_html(io.StringIO(m.group(0)))[0]
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    df = df.set_index(df.columns[0])
    df.index = [str(x).strip() for x in df.index]

    ann, qtr = {}, {}
    for col in df.columns:
        target = ann if "연간" in col[0] else qtr
        vals = {}
        for name, key in ROWS.items():
            if name in df.index:
                v = df.at[name, col]
                vals[key] = None if pd.isna(v) or v == "-" else float(v)
        target[col[1]] = vals
    return pd.DataFrame(ann).T, pd.DataFrame(qtr).T


def parse_period(s):
    """'2025.12' -> (2025, 12, False) / '2026.12(E)' -> (2026, 12, True).

    네이버는 최근 3개년·6분기만 준다. 창이 밀리므로 컬럼명을 하드코딩하지 않는다.
    """
    m = re.match(r"(\d{4})\.(\d{1,2})\s*(\(E\))?", str(s).strip())
    return (int(m.group(1)), int(m.group(2)), bool(m.group(3))) if m else None


def update():
    """오늘자 주가를 price.csv에 누적하고 전체를 반환."""
    p = fetch_price()
    if "price" not in p:
        return None
    return store.upsert(config.PRICE_CSV, {date.today(): p})


def fetch_all():
    h = _page()
    ann, qtr = fetch_performance(h)
    return {"price": fetch_price(h), "annual": ann, "quarterly": qtr}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    d = fetch_all()
    print("[시세]", d["price"])
    print("\n[연간] (억원)\n%s" % d["annual"].to_string())
    print("\n[분기] (억원)\n%s" % d["quarterly"].to_string())
