# -*- coding: utf-8 -*-
"""윤활유 수출 단가 (페트로넷 제품수출 통계).

기유(base oil) 현물가는 Argus/ICIS 유료 구독이 사실상 유일한 소스다.
대신 페트로넷 '제품수출(제품별)'이 윤활유의 물량(천 Bbl)과 금액(천 $)을
월별로 공개하므로, 여기서 실현 수출 단가를 얻을 수 있다.

주의할 점:
  - '윤활유'는 기유보다 넓은 분류다. 정확히 같은 지표가 아니라 프록시다.
  - 무역통계라 2~3개월 시차가 있다 (오늘이 7월이면 5월치가 최신).
  - 현물 호가가 아니라 '실제로 팔린 평균 단가'다. 그래서 오히려
    분기 실적과의 연결은 더 직접적이다.

하나증권이 2026-07-07 리포트에서 말한 '한국 수출 판가 2배 급등'은
이 계열로 확인된다 (2026-02 114.45 -> 2026-05 246.33).
"""
import re
import warnings
from datetime import date

import requests

import config
import store

warnings.filterwarnings("ignore")

URL = "https://www.petronet.co.kr/v4/sub.jsp"
MAIN = "https://www.petronet.co.kr/main2.jsp"
HEADERS = {"User-Agent": config.UA, "Referer": URL,
           "Origin": "https://www.petronet.co.kr"}

MENU = {"pageType": "list", "fmuId": "KDDQSTAT", "smuId": "KDXQ01",
        "tmuId": "KDXQ1900", "fmuOrd": "04", "smuOrd": "04_05", "tmuOrd": "04_05_06"}

CODE = "M0"          # 윤활유. B0휘발유 C0등유 D0경유 ... L0아스팔트 M0윤활유
PRICE_FOB = "1"      # 1=FOB, 2=C&F, 3=CIF


def _clean(t):
    x = re.sub(r"<script.*?</script>", "", t, flags=re.S | re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"[ \t]+", " ", x.replace("&nbsp;", " ").replace("\xa0", " "))


def fetch(frm, to, code=CODE):
    """frm/to 는 'YYYYMM'. {date: {volume, value, price}} 반환."""
    s = requests.Session()
    s.get(MAIN, headers=HEADERS, timeout=config.TIMEOUT, verify=False)
    s.post(URL, data=dict(MENU), headers=HEADERS, timeout=60, verify=False)  # 세션 예열

    param = (":Busisec='1',:PriceCD='%s',:FromDate='%s',:ToDate='%s',"
             ":ProdCD='\\'%s\\' '" % (PRICE_FOB, frm, to, code))
    items = list(MENU.items()) + [
        ("Parameter", param), ("InitialLoadFile", ""),
        ("ProdCDList", code), ("PriceCD", PRICE_FOB), ("term", "m"),
        ("by", frm[:4]), ("bq", "1"), ("bm", frm[4:]),
        ("ay", to[:4]), ("aq", "2"), ("am", to[4:]),
        ("ProdCd", code),
    ]
    r = s.post(URL, data=items, headers=HEADERS, timeout=180, verify=False)
    text = _clean(r.content.decode("utf-8", "replace"))

    i = text.find("제품수출(제품별) 목록")
    if i < 0:
        return {}
    seg = text[i:]
    stop = seg.find("합계")
    if stop > 0:
        seg = seg[:stop]
    seg = re.sub(r"\s*\n\s*", " ", seg)

    out, year = {}, None
    # 연도는 '24년 01월' 에서 한 번 나오고 이후 줄은 '02월' 처럼 월만 나온다
    pat = re.compile(r"(?:(\d{2})년\s*)?(\d{2})월\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)")
    for m in pat.finditer(seg):
        if m.group(1):
            year = 2000 + int(m.group(1))
        if year is None:
            continue
        out[date(year, int(m.group(2)), 1)] = {
            "lube_volume": int(m.group(3).replace(",", "")),
            "lube_value": int(m.group(4).replace(",", "")),
            "lube_price": float(m.group(5)),
        }
    return out


def update(start="201501"):
    """수집해 data/lube.csv 에 누적 저장."""
    today = date.today()
    # 무역통계는 시차가 있어 미래를 요청하면 빈 결과가 온다. 넉넉히 당월까지.
    to = "%04d%02d" % (today.year, today.month)
    rows = fetch(start, to)
    if not rows:
        return None
    return store.upsert(config.DATA / "lube.csv", rows)


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
        print(df.tail(15).to_string())
