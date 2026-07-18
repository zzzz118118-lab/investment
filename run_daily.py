# -*- coding: utf-8 -*-
"""매일 실행되는 엔트리포인트 (로컬/CI 공용).

수집이 실패해도 기존 CSV로 대시보드는 다시 만든다. 사이트가 빈 페이지가 되는
것보다 어제 데이터라도 떠 있는 편이 낫기 때문이다. 대신 헤더의 기준일로
데이터가 멈춘 것이 드러난다.

종료 코드
  0  수집·생성 모두 성공
  1  대시보드 생성 실패 (치명적)
  0  수집만 실패 (경고만 출력 — CI를 실패로 만들지 않는다)
"""
import sys
import traceback
from datetime import datetime

import collect
import config
import dashboard
import store

# 페트로넷 갱신주기가 화~토라 주말·연휴엔 자연히 며칠 비는 날이 있다.
# 이보다 오래 멈추면 고장으로 본다.
STALE_DAYS = 4


def main():
    print("=" * 56)
    print("S-Oil 트래커 일일 실행  %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 56)

    before = store.load(config.PRICES_CSV)
    n_before = len(before)

    collected = False
    try:
        collect.collect(seed=False)
        collected = True
    except Exception:
        print("\n[경고] 수집 실패 — 기존 데이터로 대시보드만 생성합니다.")
        traceback.print_exc()

    after = store.load(config.PRICES_CSV)
    if after.empty:
        print("\n[치명] 데이터가 없습니다. 최초 1회 backfill_petronet.py를 실행하세요.")
        return 1
    print("\n행수 %d -> %d (신규 %d)" % (n_before, len(after), len(after) - n_before))

    # collect()는 예외를 내부에서 삼키므로 반환값만으로는 성공 여부를 알 수 없다.
    # 실제로 판단해야 할 것은 "데이터가 얼마나 낡았는가"다.
    latest = after.index.max().date()
    stale = (datetime.today().date() - latest).days
    print("최신일: %s (%d일 경과)" % (latest, stale))
    if stale > STALE_DAYS:
        print("\n[경고] 데이터가 %d일째 갱신되지 않았습니다." % stale)
        print("       페트로넷 접속 또는 파싱이 실패했을 수 있습니다.")
        collected = False

    try:
        out = dashboard.build()
        print("대시보드: %s (%.0fKB)" % (out, out.stat().st_size / 1024))
    except Exception:
        print("\n[치명] 대시보드 생성 실패")
        traceback.print_exc()
        return 1

    if not collected:
        print("\n※ 수집은 실패했으나 사이트는 갱신했습니다. 기준일을 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
