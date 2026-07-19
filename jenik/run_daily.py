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
    print("[1/4] 관세청 마스크팩 수출")
    try:
        import exports
        df = exports.update()
        if df is None:
            print("  실패 — 기존 CSV로 진행")
        else:
            print("  %d개월, 최신 %s" % (len(df), df.index.max().date()))
    except Exception:
        traceback.print_exc()

    print("[2/4] 주가 스냅샷")
    try:
        import price
        d = price.update()
        print("  %s" % ("실패" if d is None else "%s원" % int(d["price"].iloc[-1])))
    except Exception:
        traceback.print_exc()

    print("[3/4] 실적·컨센서스")
    try:
        import financials
        fin, changes = financials.update()
        print("  %s" % ("실패" if fin is None else "%d행 저장" % len(fin)))
        if changes:
            print("  ** 컨센서스 %d건 변경 — data/consensus_history.csv 확인" % changes)
    except Exception:
        traceback.print_exc()

    print("[4/4] 대시보드")
    import dashboard
    print("  생성: %s" % dashboard.build())

    # 수동 갱신이 밀리면 실행 로그에도 남긴다. 화면만 봐서는 놓치기 쉽다.
    try:
        import freshness
        for r in freshness.check():
            if r["stale"]:
                print("  ** 갱신 필요: %s (최신 %s, %d일 전) — %s"
                      % (r["name"], r["last"], r["age"], r["note"]))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
