# -*- coding: utf-8 -*-
"""매일 실행되는 엔트리포인트 (로컬/CI 공용).

수집이 실패해도 기존 CSV로 대시보드는 다시 만든다. 사이트가 빈 페이지가 되는
것보다 어제 데이터라도 떠 있는 편이 낫기 때문이다. 대신 정체 사실을 화면 배너,
site/status.json, 실행 로그 세 군데에 남긴다.

종료 코드
  0  정상 (수집 실패는 경고로 처리하고 사이트는 갱신한다)
  1  대시보드 생성 실패 (치명적)
"""
import json
import os
import sys
import traceback
from datetime import datetime

# Windows 기본 콘솔은 cp949라 '—', '·' 같은 문자에서 UnicodeEncodeError로 죽는다.
# CI(리눅스)는 UTF-8이라 문제가 없지만, 로컬 실행까지 안전하도록 출력을 고정한다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import collect
import config
import dashboard
import store

# 페트로넷 갱신주기가 화~토라 주말·연휴엔 자연히 며칠 비는 날이 있다.
# 이보다 오래 멈추면 고장으로 본다.
STALE_DAYS = 4


def build_message(df, stale):
    """카카오톡 텍스트 (200자 제한)."""
    r = df.iloc[-1]
    asof = df.index.max().date()

    def g(c):
        v = r.get(c)
        return None if v is None or v != v else v

    cm = g("complex_margin")
    prev = df["complex_margin"].dropna()
    d = (cm - prev.iloc[-2]) if cm is not None and len(prev) >= 2 else None

    # %-m 은 Windows에서 지원되지 않으므로 직접 조립한다
    lines = ["S-Oil 정제마진 %d/%d" % (asof.month, asof.day)]
    if cm is not None:
        lines.append("복합 %.2f%s" % (cm, (" (%+.2f)" % d) if d is not None else ""))
    ke, di = g("crack_kerosene"), g("crack_diesel005")
    if ke is not None and di is not None:
        lines.append("등유 %.1f · 경유 %.1f" % (ke, di))
    du = g("dubai")
    if du is not None:
        lines.append("Dubai %.1f" % du)
    if cm is not None:
        pct = (df["complex_margin"] < cm).mean() * 100
        lines.append("20년 평균 %.1f · 상위 %.0f%%" % (df["complex_margin"].mean(), 100 - pct))
    if stale > STALE_DAYS:
        # 특수문자는 Windows 콘솔(cp949)에서 인코딩 오류를 낸다. 대괄호로 대체.
        lines.append("[주의] 원자료 %d일째 정체" % stale)
    return "\n".join(lines)


def write_status(path, **kw):
    kw["generated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.write_text(json.dumps(kw, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    print("=" * 56)
    print("S-Oil 트래커 일일 실행  %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 56)

    n_before = len(store.load(config.PRICES_CSV))

    collected = True
    try:
        collect.collect(seed=False)
    except Exception:
        collected = False
        print("\n[경고] 수집 중 예외 발생")
        traceback.print_exc()

    df = store.load(config.PRICES_CSV)
    if df.empty:
        print("\n[치명] 데이터가 없습니다. 최초 1회 backfill_petronet.py를 실행하세요.")
        return 1

    latest = df.index.max().date()
    stale = (datetime.today().date() - latest).days
    print("\n행수 %d -> %d (신규 %d)" % (n_before, len(df), len(df) - n_before))
    print("최신일: %s (%d일 경과)" % (latest, stale))

    # collect()는 예외를 내부에서 삼키므로 반환값만으로는 성공 여부를 알 수 없다.
    # 실제로 판단할 것은 "데이터가 얼마나 낡았는가"다.
    if stale > STALE_DAYS:
        collected = False
        print("\n[경고] 데이터가 %d일째 갱신되지 않았습니다." % stale)
        print("       페트로넷 접속 또는 파싱이 실패했을 수 있습니다.")

    try:
        out = dashboard.build()
        print("대시보드: %s (%.0fKB)" % (out, out.stat().st_size / 1024))
    except Exception:
        print("\n[치명] 대시보드 생성 실패")
        traceback.print_exc()
        return 1

    cm = df["complex_margin"].dropna()
    write_status(config.SITE / "status.json",
                 ok=collected, asof=str(latest), stale_days=stale,
                 rows=len(df), new_rows=len(df) - n_before,
                 complex_margin=round(float(cm.iloc[-1]), 2) if len(cm) else None)
    print("상태 기록: site/status.json (ok=%s)" % collected)

    # ── 카카오톡 ─────────────────────────────────────────────
    try:
        import kakao
        msg = build_message(df, stale)
        kakao.notify(msg, os.environ.get("SITE_URL") or None)
        print("\n카카오톡 발송 완료:\n%s" % msg)
    except Exception as e:
        if e.__class__.__name__ == "NotConfigured":
            print("\n카카오톡: 미설정 — 건너뜀")
        else:
            print("\n[경고] 카카오톡 발송 실패: %s" % e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
