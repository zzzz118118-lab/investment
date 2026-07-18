# -*- coding: utf-8 -*-
"""원/달러 환율 수집 (네이버 금융)."""
import re
import warnings
from datetime import datetime

import requests

import config

warnings.filterwarnings("ignore")

URL = "https://finance.naver.com/marketindex/"


def fetch_usdkrw():
    """현재 원/달러 매매기준율을 반환. 실패 시 None."""
    r = requests.get(URL, headers={"User-Agent": config.UA},
                     timeout=config.TIMEOUT, verify=False)
    html = r.content.decode("euc-kr", "replace")

    # <a href="...USDKRW"> ... <span class="value">1,383.50</span>
    i = html.find("USDKRW")
    if i < 0:
        return None
    m = re.search(r'class="value">([\d,]+\.\d+)</span>', html[i:i + 2000])
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


if __name__ == "__main__":
    v = fetch_usdkrw()
    print("USD/KRW:", v, "(", datetime.now().strftime("%Y-%m-%d %H:%M"), ")")
