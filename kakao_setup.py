# -*- coding: utf-8 -*-
"""카카오톡 최초 인증 도우미 (최초 1회, 본인 PC에서 직접 실행).

리프레시 토큰을 발급받는 절차를 안내한다. 발급된 값은 이 화면에만 출력되며
어디에도 저장하거나 전송하지 않는다. 출력된 값은 GitHub 시크릿에
직접 붙여넣을 것.

    python kakao_setup.py
"""
import sys
import webbrowser

import requests

REDIRECT = "https://localhost"
AUTH = "https://kauth.kakao.com/oauth/authorize"
TOKEN = "https://kauth.kakao.com/oauth/token"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    print("=" * 60)
    print("카카오톡 '나에게 보내기' 최초 인증")
    print("=" * 60)
    print("\n사전 준비 (developers.kakao.com):")
    print("  1) 애플리케이션 추가하기")
    print("  2) 카카오 로그인 → 활성화 ON")
    print("  3) 카카오 로그인 → Redirect URI 에 아래를 등록")
    print("       %s" % REDIRECT)
    print("  4) 카카오 로그인 → 동의항목 → '카카오톡 메시지 전송' 선택 동의로 설정")
    print("  5) 앱 키 → REST API 키 복사\n")

    key = input("REST API 키를 붙여넣으세요: ").strip()
    if not key:
        print("입력이 없습니다. 중단합니다.")
        return 1

    url = ("%s?client_id=%s&redirect_uri=%s&response_type=code&scope=talk_message"
           % (AUTH, key, REDIRECT))
    print("\n아래 주소를 브라우저에서 열고 '동의하고 계속하기'를 누르세요.")
    print("(브라우저가 자동으로 열립니다)\n")
    print(url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("동의하면 '연결할 수 없음' 같은 오류 페이지로 이동합니다. 정상입니다.")
    print("그때 주소창을 보면 ...localhost/?code=XXXXXXXX 형태입니다.")
    print("code= 뒤의 값만 복사하세요.\n")

    code = input("code 값을 붙여넣으세요: ").strip()
    if not code:
        print("입력이 없습니다. 중단합니다.")
        return 1

    r = requests.post(TOKEN, timeout=20, data={
        "grant_type": "authorization_code",
        "client_id": key,
        "redirect_uri": REDIRECT,
        "code": code,
    })
    if r.status_code != 200:
        print("\n실패 %d: %s" % (r.status_code, r.text[:400]))
        print("\ncode는 1회용입니다. 다시 받으려면 처음부터 실행하세요.")
        return 1

    j = r.json()
    refresh = j.get("refresh_token")
    if not refresh:
        print("\n리프레시 토큰이 없습니다. 응답: %s" % r.text[:400])
        return 1

    print("\n" + "=" * 60)
    print("발급 완료. 아래 두 값을 GitHub 시크릿에 등록하세요.")
    print("=" * 60)
    print("\n저장소 Settings → Secrets and variables → Actions → New repository secret\n")
    print("  이름: KAKAO_REST_API_KEY")
    print("  값  : %s\n" % key)
    print("  이름: KAKAO_REFRESH_TOKEN")
    print("  값  : %s\n" % refresh)
    print("=" * 60)
    print("주의: 위 값은 비밀번호와 같습니다. 채팅이나 공개 저장소에 붙여넣지 마세요.")
    print("리프레시 토큰 유효기간은 약 2개월입니다. 만료가 가까워지면")
    print("실행 로그에 새 토큰이 안내되며, 시크릿을 교체해야 합니다.")

    if input("\n지금 테스트 발송을 해볼까요? (y/N): ").strip().lower() == "y":
        import os
        os.environ["KAKAO_REST_API_KEY"] = key
        os.environ["KAKAO_REFRESH_TOKEN"] = refresh
        import kakao
        try:
            kakao.notify("S-Oil 트래커 연결 테스트입니다.",
                         "https://zzzz118118-lab.github.io/investment/")
            print("발송 성공. 카카오톡을 확인하세요.")
        except Exception as e:
            print("발송 실패: %s" % e)
            print("동의항목에 '카카오톡 메시지 전송'이 켜져 있는지 확인하세요.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
