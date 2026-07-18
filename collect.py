# -*- coding: utf-8 -*-
"""수집 엔트리포인트.

  python collect.py         # 일일 수집 (최근 7영업일 갱신)
  python collect.py --seed  # 메인 페이지 차트에서 22영업일 시딩 후 수집

매일 실행하면 prices.csv에 히스토리가 누적된다.
"""
import sys
from datetime import datetime

import config
import fx
import margin
import petronet
import store


def collect(seed=False):
    rows = {}

    if seed:
        try:
            h = petronet.fetch_history_from_main()
            for d, v in h.items():
                rows.setdefault(d, {}).update(v)
            print("  시딩(메인차트): %d일" % len(h))
        except Exception as e:
            print("  [경고] 메인차트 시딩 실패: %s" % e)

    # 상세 테이블이 더 정확하므로 나중에 적용해 시딩값을 덮어쓴다
    try:
        c = petronet.fetch_crude()
        for d, v in c.items():
            rows.setdefault(d, {}).update(v)
        print("  원유가격: %d일" % len(c))
    except Exception as e:
        print("  [오류] 원유가격 수집 실패: %s" % e)

    try:
        p = petronet.fetch_products()
        for d, v in p.items():
            rows.setdefault(d, {}).update(v)
        print("  제품가격: %d일" % len(p))
    except Exception as e:
        print("  [오류] 제품가격 수집 실패: %s" % e)

    if not rows:
        print("  수집된 데이터 없음. 중단.")
        return None

    enriched = {d: margin.enrich(v) for d, v in rows.items()}
    df = store.upsert(config.PRICES_CSV, enriched)
    print("  저장: %s (%d행 x %d열)" % (config.PRICES_CSV.name, len(df), len(df.columns)))

    # 환율은 일중 스냅샷이라 오늘 날짜로 별도 저장
    try:
        v = fx.fetch_usdkrw()
        if v:
            store.upsert(config.FX_CSV, {datetime.today().date(): {"usdkrw": v}})
            print("  환율: %.2f" % v)
    except Exception as e:
        print("  [경고] 환율 수집 실패: %s" % e)

    # 윤활유 수출단가 (월간, 2~3개월 시차). 매일 받아도 부담이 없어 그냥 갱신한다.
    try:
        import lube
        ldf = lube.update()
        if ldf is not None and not ldf.empty:
            print("  윤활유 수출단가: %d개월 (최신 %s)"
                  % (len(ldf), ldf.index.max().date()))
    except Exception as e:
        print("  [경고] 윤활유 수집 실패: %s" % e)

    return df


if __name__ == "__main__":
    seed = "--seed" in sys.argv
    print("[수집 시작] %s%s" % (datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "  (시딩 포함)" if seed else ""))
    df = collect(seed=seed)
    if df is not None and not df.empty:
        cols = [c for c in ["dubai", "gasoline92", "kerosene", "diesel0001",
                            "crack_diesel0001", "complex_margin"] if c in df.columns]
        print("\n[최근 5일]")
        print(df[cols].tail().to_string())
