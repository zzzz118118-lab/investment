# -*- coding: utf-8 -*-
"""S-Oil 주가·재무 수집.

  - 현재가/시가총액: 네이버 금융
  - 연간·분기 실적: 네이버 '기업실적분석' (2023~2025 실적 + 컨센서스)
  - 2027F 이후, 3Q26F 이후: data/report_estimates.csv (증권사 리포트 인용)

네이버는 최근 3개년만 제공한다. 2021~2022년까지 넣으려면 DART가 필요하다.
"""
import io
import re
import warnings

import pandas as pd
import requests

import config

warnings.filterwarnings("ignore")

CODE = "010950"
URL = "https://finance.naver.com/item/main.naver?code=" + CODE
HEADERS = {"User-Agent": config.UA}

# 네이버 행 이름 -> 내부 키
ROWS = {
    "매출액": "revenue",
    "영업이익": "op",
    "당기순이익": "np",
    "영업이익률": "op_margin",
    "순이익률": "np_margin",
    "EPS(원)": "eps",
    "BPS(원)": "bps",
    "PER(배)": "per",
    "PBR(배)": "pbr",
    "ROE(지배주주)": "roe",
    "주당배당금(원)": "dps",
    "시가배당률(%)": "div_yield",
    "배당성향(%)": "payout",
}


def _page():
    return requests.get(URL, headers=HEADERS, timeout=config.TIMEOUT,
                        verify=False).content.decode("utf-8", "replace")


def fetch_price(html=None):
    """현재가 등 시세 정보."""
    h = html or _page()
    out = {}
    m = re.search(r'<p class="no_today">.*?<span class="blind">([\d,]+)</span>', h, re.S)
    if m:
        out["price"] = int(m.group(1).replace(",", ""))
    m = re.search(r'<p class="no_exday">(.*?)</p>', h, re.S)
    if m:
        seg = m.group(1)
        nums = re.findall(r'<span class="blind">([\d,.]+)</span>', seg)
        down = "ico down" in seg or "하락" in seg
        if len(nums) >= 2:
            out["change"] = (-1 if down else 1) * int(nums[0].replace(",", ""))
            out["change_pct"] = (-1 if down else 1) * float(nums[1])
    # 시가총액은 전용 id를 쓴다. '시가총액' 문자열로 찾으면 동일업종 비교표의
    # 다른 종목 값을 잡을 수 있다. 표기는 '16조 3,132' (조 + 억) 형태.
    m = re.search(r'id="_market_sum"[^>]*>([^<]+)<', h)
    if m:
        s = m.group(1).replace(",", "").strip()
        mm = re.match(r"(?:(\d+)조)?\s*(\d+)?", s)
        if mm:
            jo = int(mm.group(1)) if mm.group(1) else 0
            eok = int(mm.group(2)) if mm.group(2) else 0
            out["mktcap"] = jo * 10000 + eok
    return out


def fetch_performance(html=None):
    """기업실적분석 표를 (연간 df, 분기 df)로 반환. 단위: 억원 / 원 / %."""
    h = html or _page()
    i = h.find("기업실적분석")
    m = re.search(r"<table.*?</table>", h[i:], re.S | re.I)
    if not m:
        raise RuntimeError("기업실적분석 표를 찾지 못했습니다")

    df = pd.read_html(io.StringIO(m.group(0)))[0]
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    label = df.columns[0]
    df = df.set_index(label)
    df.index = [str(x).strip() for x in df.index]

    ann, qtr = {}, {}
    for col in df.columns:
        group, period = col[0], col[1]
        target = ann if "연간" in group else qtr
        vals = {}
        for name, key in ROWS.items():
            if name in df.index:
                v = df.at[name, col]
                vals[key] = None if pd.isna(v) or v == "-" else float(v)
        target[period] = vals
    return pd.DataFrame(ann).T, pd.DataFrame(qtr).T


def parse_period(s):
    """'2025.12' -> (2025, 12, False), '2026.12(E)' -> (2026, 12, True).

    네이버는 최근 3개년/6분기만 보여주고 시간이 가면 이 창이 밀린다.
    따라서 컬럼명을 하드코딩하지 말고 항상 여기서 해석해 쓴다.
    """
    m = re.match(r"(\d{4})\.(\d{1,2})\s*(\(E\))?", str(s).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), bool(m.group(3))


def load_estimates():
    """리포트 추정치 CSV."""
    p = config.DATA / "report_estimates.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, comment="#")


def fetch_all():
    h = _page()
    ann, qtr = fetch_performance(h)
    return {"price": fetch_price(h), "annual": ann, "quarterly": qtr,
            "estimates": load_estimates()}


if __name__ == "__main__":
    import sys
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    d = fetch_all()
    print("[시세]", d["price"])
    print("\n[연간] (억원)")
    print(d["annual"].to_string())
    print("\n[분기] (억원)")
    print(d["quarterly"].to_string())
    print("\n[리포트 추정치]")
    print(d["estimates"].to_string())
