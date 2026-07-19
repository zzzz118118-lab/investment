# -*- coding: utf-8 -*-
"""수집 → 대시보드 생성 일괄 실행.

    python run_daily.py

수집이 실패해도 기존 CSV로 대시보드는 다시 만든다(soil-tracker와 같은 정책).
사이트가 비는 것보다 낫고, 자료가 밀리면 대시보드 상단에 경고 배너가 뜬다.
"""
import sys
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def main():
    print("[1/3] 관세청 마스크팩 수출")
    try:
        import exports
        df = exports.update()
        if df is None:
            print("  실패 — 기존 CSV로 진행")
        else:
            print("  %d개월, 최신 %s" % (len(df), df.index.max().date()))
    except Exception:
        traceback.print_exc()

    print("[2/3] 주가 스냅샷")
    try:
        import price
        d = price.update()
        print("  %s" % ("실패" if d is None else "%s원" % int(d["price"].iloc[-1])))
    except Exception:
        traceback.print_exc()

    print("[3/3] 대시보드")
    import dashboard
    print("  생성: %s" % dashboard.build())


if __name__ == "__main__":
    main()
