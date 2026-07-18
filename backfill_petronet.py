# -*- coding: utf-8 -*-
"""페트로넷 과거 시계열 백필.

기간 지정 조회가 되려면 세 가지가 모두 맞아야 한다(하나라도 틀리면 빈 결과):
  1) 제품코드 구분자가 `\\,\\'` — 백슬래시 콤마다. 그냥 `,`면 실패한다.
  2) `:DISP1='...'` 를 Parameter 끝에 붙여야 한다.
  3) 메뉴 POST로 서브페이지를 한 번 로드해 세션을 예열한 뒤 조회해야 한다.
  4) 기간 2일 이상이면 InitialLoadFile을 `_EXT` 템플릿으로 바꿔야 한다.

서버에 행 수 상한이 있어 1.5년(약 390행)까지는 되고 6년은 빈 결과가 온다.
따라서 연 단위로 쪼개 요청한다(연 250행 내외, 요청당 2~3초).

    python backfill_petronet.py 2006      # 2006년부터 현재까지
    python backfill_petronet.py 2024      # 2024년부터
"""
import sys
import time
import warnings
from datetime import datetime

import requests

import config
import margin
import petronet
import store

warnings.filterwarnings("ignore")

HEADERS = dict(petronet.HEADERS)
HEADERS["Origin"] = "https://www.petronet.co.kr"

CRUDE_CODES = ["001", "002", "003", "004"]

SPECS = {
    "product": dict(menu=petronet.MENU_PRODUCT, codes=config.PROD_CODES,
                    columns=config.PROD_COLUMNS,
                    marker="일일국제제품가격 목록",
                    ilf_1="국제가격정보(일일제품가격)(intruser1)",
                    ilf_n="국제가격정보(일일제품가격_EXT)(intruser1)"),
    "crude": dict(menu=petronet.MENU_CRUDE, codes=CRUDE_CODES,
                  columns=config.CRUDE_COLUMNS,
                  marker="일일국제원유가격 목록",
                  ilf_1="국제가격정보(일일국제원유가)(intruser1)",
                  ilf_n="국제가격정보(일일국제원유가_EXT)(intruser1)"),
}


def _prod_param(codes):
    """JS와 동일한 이스케이프. 구분자가 백슬래시 콤마인 점이 핵심."""
    s = ":ProdCD='\\'" + codes[0] + "\\'"
    for c in codes[1:]:
        s += "\\,\\'" + c + "\\'"
    return s + " '"


def fetch_range(kind, frm, to):
    """frm~to (YYYYMMDD) 구간을 조회해 {date: {col: val}} 반환."""
    spec = SPECS[kind]
    menu = spec["menu"]

    s = requests.Session()
    s.get(petronet.MAIN_URL, headers=HEADERS, timeout=config.TIMEOUT, verify=False)
    # 세션 예열: 서브페이지를 한 번 정상 로드해야 이후 조회가 먹는다
    s.post(petronet.SUB_URL, data=dict(menu), headers=HEADERS, timeout=60, verify=False)

    days = (datetime.strptime(to, "%Y%m%d") - datetime.strptime(frm, "%Y%m%d")).days
    ilf = spec["ilf_1"] if days < 2 else spec["ilf_n"]
    disp = "%s년 %s월 %s일 ~ %s년 %s월 %s일" % (frm[:4], frm[4:6], frm[6:],
                                              to[:4], to[4:6], to[6:])
    param = ":T='D',:FromDate='%s',:ToDate='%s',%s,:DISP1='%s'" % (
        frm, to, _prod_param(spec["codes"]), disp)

    items = [("pageType", "list"), ("bbsSeq", "")] + list(menu.items()) + [
        ("Parameter", param), ("InitialLoadFile", ilf),
        ("ProdCDList", ",".join(spec["codes"])), ("firstFlag", "F"), ("term", "d"),
        ("by", frm[:4]), ("bq", "1"), ("bm", frm[4:6]), ("bw", "1"), ("bd", frm[6:]),
        ("ay", to[:4]), ("aq", "3"), ("am", to[4:6]), ("aw", "1"), ("ad", to[6:]),
    ] + [("ProdCd", c) for c in spec["codes"]]

    r = s.post(petronet.SUB_URL, data=items, headers=HEADERS, timeout=300, verify=False)
    text = petronet._text(r.content.decode("utf-8", "replace"))
    return petronet._parse_table_year(text, spec["columns"], spec["marker"], int(frm[:4]))


def backfill(start_year, end_year=None):
    end_year = end_year or datetime.today().year
    rows = {}
    for year in range(start_year, end_year + 1):
        frm = "%d0101" % year
        to = "%d1231" % year if year < end_year else datetime.today().strftime("%Y%m%d")
        got = {}
        for kind in ("crude", "product"):
            for attempt in range(3):
                try:
                    part = fetch_range(kind, frm, to)
                    if part:
                        for d, v in part.items():
                            got.setdefault(d, {}).update(v)
                        break
                    time.sleep(1.5)
                except Exception as e:
                    print("    %d %s 재시도(%d): %s" % (year, kind, attempt + 1, str(e)[:50]))
                    time.sleep(2)
        print("  %d: %d일" % (year, len(got)))
        rows.update(got)
        time.sleep(0.5)

    if not rows:
        print("수집 실패.")
        return None
    enriched = {d: margin.enrich(v) for d, v in rows.items()}
    df = store.upsert(config.PRICES_CSV, enriched)
    print("\n저장: %d행 x %d열  (%s ~ %s)"
          % (len(df), len(df.columns), df.index.min().date(), df.index.max().date()))
    return df


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2006
    print("[백필] %d년 ~ 현재" % start)
    backfill(start)
