# -*- coding: utf-8 -*-
"""페트로넷(한국석유공사) 수집기.

두 개의 경로를 쓴다.
  1) main2.jsp 메인 페이지 - Chart.js 데이터셋에 22영업일치 시계열이 박혀 있다.
     최초 실행 시 히스토리 시딩용.
  2) /v4/sub.jsp POST - 최근 7영업일 상세 테이블. 8개 유종 전부 나온다.
     매일 갱신용. (기간 지정은 정보회원 전용이라 익명 요청은 최근 구간만 반환)
"""
import re
import warnings
from datetime import datetime

import requests

import config

warnings.filterwarnings("ignore")

MAIN_URL = "https://www.petronet.co.kr/main2.jsp"
SUB_URL = "https://www.petronet.co.kr/v4/sub.jsp"
HEADERS = {"User-Agent": config.UA, "Referer": MAIN_URL}

MENU_PRODUCT = {
    "pageType": "list", "fmuId": "KDFQSTAT", "smuId": "KDFQ01", "tmuId": "KDFQ0200",
    "fmuOrd": "03", "smuOrd": "03_01", "tmuOrd": "03_01_02",
}
MENU_CRUDE = {
    "pageType": "list", "fmuId": "KDFQSTAT", "smuId": "KDFQ01", "tmuId": "KDFQ0100",
    "fmuOrd": "03", "smuOrd": "03_01", "tmuOrd": "03_01_01",
}


def _session():
    s = requests.Session()
    s.get(MAIN_URL, headers=HEADERS, timeout=config.TIMEOUT, verify=False)
    return s


def _text(html):
    x = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    x = re.sub(r"<style.*?</style>", "", x, flags=re.S | re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    x = x.replace("&nbsp;", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", x)


# ── 1) 메인 페이지 차트에서 시계열 시딩 ──────────────────────────


def _chart_block(html, var_name):
    i = html.find(var_name)
    return html[i:i + 8000] if i >= 0 else ""


def _parse_chart(block):
    """Chart.js 옵션 블록에서 labels와 datasets를 뽑는다."""
    m = re.search(r"labels\s*:\s*\[(.*?)\]", block, re.S)
    if not m:
        return [], {}
    labels = re.findall(r"'([^']+)'", m.group(1))
    series = {}
    for mm in re.finditer(r'label\s*:\s*"(.*?)".*?data\s*:\s*\[(.*?)\]', block, re.S):
        name = mm.group(1).strip()
        vals = []
        for v in mm.group(2).split(","):
            v = v.strip()
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(None)  # NaN
        series[name] = vals
    return labels, series


def _label_to_date(label, today=None):
    """'7.17' -> date. 연도는 오늘 기준으로 추정(연말 경계 처리 포함)."""
    today = today or datetime.today().date()
    mm, dd = label.split(".")
    year = today.year
    try:
        d = datetime(year, int(mm), int(dd)).date()
    except ValueError:
        return None
    if (d - today).days > 180:      # 작년 12월 데이터를 올해로 잘못 읽은 경우
        d = datetime(year - 1, int(mm), int(dd)).date()
    return d


def fetch_history_from_main():
    """메인 페이지 차트에서 22영업일치 원유/제품 가격을 뽑는다.

    반환: {date: {컬럼: 값}}
    """
    html = requests.get(MAIN_URL, headers=HEADERS, timeout=config.TIMEOUT,
                        verify=False).content.decode("utf-8")

    name_map = {
        "Dubai": "dubai", "WTI (NYMEX)": "wti", "Brent (ICE)": "brent",
        "휘발유": "gasoline92", "등유": "kerosene", "경유": "diesel0001",
    }

    rows = {}
    for var in ("interOilPriceChartOpt", "interProdPriceChartOpt"):
        labels, series = _parse_chart(_chart_block(html, var))
        dates = [_label_to_date(l) for l in labels]
        for label, vals in series.items():
            col = name_map.get(label)
            if not col:
                continue
            for d, v in zip(dates, vals):
                if d is None or v is None:
                    continue
                rows.setdefault(d, {})[col] = v
    return rows


# ── 2) 상세 테이블에서 최근 구간 수집 ────────────────────────────


def _parse_table(text, columns, marker, year=None):
    """'07월 09일  97.22 94.64 ...' 형태의 행들을 파싱.

    year를 주면 그 연도로 확정한다(백필용). 없으면 오늘 기준으로 추정한다.
    """
    i = text.find(marker)
    if i < 0:
        return {}
    seg = text[i:]
    # 합계/비교 행(전일비 등)이 시작되면 중단.
    # 이 컷이 없으면 푸터의 '2026년 07월 17일 까지 입력된...' 문구까지 행으로 잡힌다.
    stop = min([p for p in [seg.find("전일비"), seg.find("평균")] if p > 0] or [len(seg)])
    seg = seg[:stop]

    out = {}
    today = datetime.today().date()
    fixed = year is not None
    base_year = year if fixed else today.year
    # 값은 반드시 소수점을 포함한다. 정수를 허용하면 다음 행의 '07월'에서
    # '07'을 값으로 먹어버려 행이 격일로 누락된다.
    pat = re.compile(r"(\d{2})월\s*(\d{2})일((?:\s+-?\d+\.\d+)+)")
    for m in pat.finditer(seg):
        mm, dd = int(m.group(1)), int(m.group(2))
        nums = [float(v) for v in m.group(3).split()]
        if len(nums) < len(columns):
            continue
        try:
            d = datetime(base_year, mm, dd).date()
        except ValueError:
            continue
        if not fixed and (d - today).days > 180:
            d = datetime(base_year - 1, mm, dd).date()
        out[d] = dict(zip(columns, nums[:len(columns)]))
    return out


def _parse_table_year(text, columns, marker, year):
    """연도를 확정해 파싱(백필용)."""
    return _parse_table(text, columns, marker, year=year)


def fetch_products():
    """최근 영업일 구간의 제품가격 8종."""
    s = _session()
    data = dict(MENU_PRODUCT)
    r = s.post(SUB_URL, data=data, headers=HEADERS, timeout=config.TIMEOUT, verify=False)
    text = _text(r.content.decode("utf-8", "replace"))
    return _parse_table(text, config.PROD_COLUMNS, "일일국제제품가격 목록")


def fetch_crude():
    """최근 영업일 구간의 원유가격 (Dubai/WTI/Brent)."""
    s = _session()
    r = s.post(SUB_URL, data=dict(MENU_CRUDE), headers=HEADERS,
               timeout=config.TIMEOUT, verify=False)
    text = _text(r.content.decode("utf-8", "replace"))
    return _parse_table(text, config.CRUDE_COLUMNS, "일일국제원유가격 목록")


if __name__ == "__main__":
    print("[메인 차트 시딩]")
    h = fetch_history_from_main()
    for d in sorted(h)[-3:]:
        print(" ", d, h[d])
    print("  총", len(h), "일")

    print("\n[제품가격 테이블]")
    p = fetch_products()
    for d in sorted(p):
        print(" ", d, p[d])

    print("\n[원유가격 테이블]")
    c = fetch_crude()
    for d in sorted(c):
        print(" ", d, c[d])
