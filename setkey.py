# -*- coding: utf-8 -*-
"""API 인증키를 .env 에 안전하게 저장한다.

터미널 붙여넣기는 \\r 이나 \\x16(Ctrl+V) 같은 제어문자가 섞이기 쉽고,
그대로 저장하면 인증이 조용히 실패한다. 여기서 한 번에 정리하고
곧바로 실제 호출까지 해봐서 되는지 확인한다.

    python setkey.py
"""
import getpass
import re
import sys
import warnings
from pathlib import Path

import requests

warnings.filterwarnings("ignore")
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ENV = Path(__file__).resolve().parent / ".env"
NAME = "DATA_GO_KR_KEY"
TEST_URL = "http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"


def load_env():
    """.env 를 {키: 값} 으로 읽는다. 줄바꿈 처리는 \\n 만 기준으로 한다."""
    if not ENV.exists():
        return {}
    out = {}
    for line in ENV.read_text(encoding="utf-8", errors="replace").split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def save_env(d):
    ENV.write_text("\n".join("%s=%s" % (k, v) for k, v in d.items()) + "\n",
                   encoding="utf-8")


def test(key):
    try:
        r = requests.get(TEST_URL, timeout=40, verify=False, params={
            "serviceKey": key, "strtYymm": "202605", "endYymm": "202605",
            "hsSgn": "271019"})
    except Exception as e:
        return False, "요청 실패: %s" % str(e)[:120]
    if r.status_code == 401:
        return False, "401 Unauthorized — 키가 틀렸거나 아직 승인 전입니다"
    if r.status_code != 200:
        return False, "HTTP %d" % r.status_code
    body = r.text
    if "<item>" in body:
        return True, "정상 (item %d건)" % body.count("<item>")
    m = re.search(r"<returnAuthMsg>(.*?)</returnAuthMsg>", body)
    if m:
        return False, m.group(1)
    m = re.search(r"<resultMsg>(.*?)</resultMsg>", body)
    return False, (m.group(1) if m else re.sub(r"\s+", " ", body)[:200])


def main():
    print("=" * 58)
    print("공공데이터포털 인증키 저장")
    print("=" * 58)
    print("\n마이페이지 > 개발계정 > '일반 인증키(Decoding)' 를 복사하세요.")
    print("Encoding 쪽이 아니라 Decoding 쪽입니다.\n")
    print("붙여넣기는 마우스 오른쪽 클릭으로 하세요.")
    print("(Git Bash에서 Ctrl+V 는 붙여넣기가 아니라 제어문자가 들어갑니다)\n")

    raw = getpass.getpass("인증키 (화면에 안 보입니다): ")
    key = re.sub(r"[\x00-\x1f\x7f\s]", "", raw)   # 제어문자·공백 제거

    if not key:
        print("\n입력이 없습니다. 중단합니다.")
        return 1
    removed = len(raw) - len(key)
    print("\n입력 %d자" % len(raw) + (" (제어문자 %d개 제거)" % removed if removed else ""))
    print("저장할 키 길이: %d자" % len(key))

    print("\n실제 호출로 확인 중...")
    ok, msg = test(key)
    print("  -> %s" % msg)

    if not ok:
        print("\n저장하지 않았습니다. 키를 다시 확인해 주세요.")
        print("승인 직후라면 몇 분 뒤 다시 시도해 보세요.")
        return 1

    d = load_env()
    d[NAME] = key
    save_env(d)
    print("\n.env 에 저장했습니다. (이 파일은 깃에 올라가지 않습니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
