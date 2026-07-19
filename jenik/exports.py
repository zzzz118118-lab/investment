# -*- coding: utf-8 -*-
"""마스크팩 수출 실적 (관세청 품목별 수출입실적 API).

제닉 추적의 핵심 선행지표. 세 리포트 모두 이 숫자를 근거로 쓴다:
  하나  "1분기 마스크팩 수출 YoY 59%, 2분기 YoY 70% 상회"
  유안타 "마스크팩 수출금액 22년 6.12억달러 → 25년 8.73억달러"
  교보  "글로벌 수요가 폭발적으로 증가"

HS 3307.90 아래 네 품목 중 3307904000이 '마스크 팩'이다.
관세청은 매월 15일경 전월 확정치를 반영한다.

인증키: .env 의 DATA_GO_KR_KEY (없으면 환경변수). soil-tracker와 같은 키다.

API 제약 (soil-tracker/customs.py와 동일):
  - hsSgn은 6자리까지만 먹는다. 10자리를 넣으면 빈 결과가 온다.
  - 조회 구간이 길면 빈 결과가 온다. 연 단위로 끊어 요청한다.
  - 실패해도 예외가 아니라 빈 XML이 오므로 행 수를 반드시 확인할 것.
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
    """한 해치를 조회해 {date: {...}} 반환. 값 단위는 USD, kg."""
    key = key or _key()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY 없음")
    r = requests.get(URL, timeout=120, verify=False, params={
        "serviceKey": key, "strtYymm": "%d01" % year,
        "endYymm": "%d12" % year, "hsSgn": config.HS6})

    out = {}
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        name = config.HS_ITEMS.get(_tag(it, "hsCode"))
        if not name:
            continue
        m = re.match(r"(\d{4})\.(\d{2})", _tag(it, "year"))   # '2026.05'
        if not m:
            continue
        try:
            usd = float(_tag(it, "expDlr") or 0)
            kg = float(_tag(it, "expWgt") or 0)
        except ValueError:
            continue
        d = date(int(m.group(1)), int(m.group(2)), 1)
        row = out.setdefault(d, {})
        row["%s_usd" % name] = usd
        row["%s_kg" % name] = kg

    # 파생 지표. 합계는 리포트(유안타)가 쓰는 기준이라 따로 남긴다.
    for d, row in out.items():
        row["total_usd"] = sum(v for k, v in row.items() if k.endswith("_usd"))
        mk, kg = row.get("mask_usd"), row.get("mask_kg")
        if mk and kg:
            row["mask_usd_kg"] = round(mk / kg, 2)
    return out


def update(start_year=2015):
    rows = {}
    for y in range(start_year, date.today().year + 1):
        try:
            got = fetch_year(y)
            if not got:
                print("    %d년 빈 결과" % y)
            rows.update(got)
        except Exception as e:
            print("    %d년 실패: %s" % (y, str(e)[:70]))
    if not rows:
        return None
    return store.upsert(config.EXPORTS_CSV, rows)


def yoy(df, col="mask_usd"):
    """전년 동월 대비 증가율(%) 시리즈."""
    s = df[col].dropna()
    return (s / s.shift(12) - 1) * 100


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    df = update()
    if df is None:
        raise SystemExit("수집 실패")
    print("%d개월  %s ~ %s" % (len(df), df.index.min().date(), df.index.max().date()))
    show = df.tail(15)[["mask_usd", "mask_kg", "mask_usd_kg", "total_usd"]].copy()
    show["mask_usd"] /= 1e6
    show["total_usd"] /= 1e6
    show["mask_kg"] /= 1000
    show.columns = ["마스크팩(백만$)", "중량(톤)", "$/kg", "330790계(백만$)"]
    print(show.round(2).to_string())
    y = yoy(df)
    print("\n최근 YoY(%%): \n%s" % y.tail(8).round(1).to_string())
