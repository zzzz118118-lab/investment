# -*- coding: utf-8 -*-
"""카카오톡 '나에게 보내기' 발송.

환경변수
  KAKAO_REST_API_KEY    카카오 개발자 앱의 REST API 키
  KAKAO_REFRESH_TOKEN   최초 1회 수동 인증으로 받은 리프레시 토큰
  KAKAO_CLIENT_SECRET   클라이언트 시크릿 (해당 키에 활성화된 경우에만)
  SITE_URL              대시보드 주소 (메시지 버튼에 붙는다)

카카오는 요즘 REST API 키를 새로 발급하면 클라이언트 시크릿을 기본 활성화한다.
이 경우 시크릿 없이 토큰을 요청하면 401 KOE010(Bad client credentials)이 난다.

설정되지 않았으면 조용히 건너뛴다. 카카오를 안 쓰는 환경에서도
파이프라인이 실패하지 않도록 하기 위함이다.

리프레시 토큰 유효기간은 약 2개월이다. 남은 기간이 1개월 미만이면
갱신 요청 시 카카오가 새 토큰을 함께 돌려주는데, GitHub Actions는 자기
시크릿을 스스로 갱신할 수 없다. 그래서 새 토큰이 오면 로그에 크게 남기고
카카오 메시지에도 안내를 붙인다. 사용자가 시크릿을 수동으로 교체해야 한다.
"""
import json
import os

import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
TEXT_LIMIT = 200        # 기본 텍스트 템플릿 제한


class NotConfigured(Exception):
    pass


def _env():
    key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    ref = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    sec = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
    if not key or not ref:
        raise NotConfigured("KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN 미설정")
    return key, ref, sec


def refresh_access_token(rest_key, refresh_token, client_secret=""):
    """(access_token, 새 refresh_token 또는 None) 반환."""
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret
    r = requests.post(TOKEN_URL, timeout=20, data=data)
    if r.status_code != 200:
        raise RuntimeError("토큰 갱신 실패 %d: %s" % (r.status_code, r.text[:300]))
    j = r.json()
    return j["access_token"], j.get("refresh_token")


def send_text(access_token, text, url=None, button="대시보드 열기"):
    if len(text) > TEXT_LIMIT:
        text = text[:TEXT_LIMIT - 1] + "…"
    obj = {"object_type": "text", "text": text,
           "link": {"web_url": url, "mobile_web_url": url} if url else {}}
    if url:
        obj["button_title"] = button
    r = requests.post(SEND_URL, timeout=20,
                      headers={"Authorization": "Bearer " + access_token},
                      data={"template_object": json.dumps(obj, ensure_ascii=False)})
    if r.status_code != 200:
        raise RuntimeError("발송 실패 %d: %s" % (r.status_code, r.text[:300]))
    return r.json()


def notify(text, url=None):
    """설정돼 있으면 발송한다. 미설정이면 NotConfigured를 던진다."""
    key, ref, sec = _env()
    token, new_ref = refresh_access_token(key, ref, sec)
    if new_ref and new_ref != ref:
        print("\n" + "!" * 60)
        print("카카오가 새 리프레시 토큰을 발급했습니다.")
        print("GitHub 시크릿 KAKAO_REFRESH_TOKEN 을 아래 값으로 교체하세요:")
        print("  " + new_ref)
        print("교체하지 않으면 약 2개월 뒤 발송이 멈춥니다.")
        print("!" * 60 + "\n")
        text = (text + "\n\n※ 토큰 갱신 필요 (실행 로그 확인)")[:TEXT_LIMIT]
    send_text(token, text, url)
    return True


if __name__ == "__main__":
    import sys
    try:
        notify("S-Oil 트래커 연결 테스트입니다.",
               os.environ.get("SITE_URL") or None)
        print("발송 성공. 카카오톡을 확인하세요.")
    except NotConfigured as e:
        print("미설정: %s" % e)
        sys.exit(2)
    except Exception as e:
        print("실패: %s" % e)
        sys.exit(1)
