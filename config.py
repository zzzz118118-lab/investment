# -*- coding: utf-8 -*-
"""S-Oil 트래커 설정."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

# GitHub Pages가 게시하는 디렉터리. 대시보드는 여기에 index.html로 떨어진다.
SITE = BASE / "site"
SITE.mkdir(exist_ok=True)

PRICES_CSV = DATA / "prices.csv"     # 유가 + 제품가 + 크랙 + 복합마진 (일별)
FX_CSV = DATA / "fx.csv"             # 환율 (일별)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT = 30

# ── 페트로넷 제품 코드 ────────────────────────────────────────────
# 사이트 테이블 컬럼 순서와 동일. D001(경유 0.5%)은 2012년 게시 중단이라
# 조회 코드에는 포함되지만 결과 테이블에는 컬럼이 없다.
PROD_CODES = ["B001", "B007", "C001", "D001", "D008", "D009", "E001", "E008", "F001"]
PROD_COLUMNS = [
    "gasoline95",   # 휘발유 95RON
    "gasoline92",   # 휘발유 92RON
    "kerosene",     # 등유
    "diesel005",    # 경유 0.05%
    "diesel0001",   # 경유 0.001% (10ppm)
    "hsfo180",      # 고유황중유 180cst
    "hsfo380",      # 고유황중유 380cst
    "naphtha",      # 나프타
]

# 사이트 테이블 컬럼 순서: Dubai, Brent, WTI, Oman
# (메인 페이지 차트는 Dubai/WTI/Brent 순이라 다르다. 주의)
CRUDE_COLUMNS = ["dubai", "brent", "wti", "oman"]

# ── 크랙 스프레드 ────────────────────────────────────────────────
# 8개 유종 전부 계산해 둔다(비용이 없다).
CRACK_PRODUCTS = PROD_COLUMNS

# 하나증권 '화학 제품가격 동향'표와 동일한 유종 기준.
# 2026-07-15 자 표와 7/14~7/15 양일 소수점 둘째자리까지 일치 검증됨.
#   납사 naphtha / 가솔린 95RON / 등유 kerosene / 경유 0.05% / B-C 180cst
# 92RON·0.001%·380cst를 쓰면 각각 2.9 / 1.0 / 0.7 씩 어긋난다.
HEADLINE_CRACKS = {
    "납사":   "crack_naphtha",
    "가솔린": "crack_gasoline95",
    "등유":   "crack_kerosene",
    "경유":   "crack_diesel005",
    "B-C":    "crack_hsfo180",
}

# ── 정제마진 수율 ────────────────────────────────────────────────
# 하나증권 '화학 제품가격 동향'표의 Complex/Simple Crack 11일치(2026-07-01
# ~07-15)에 최소자승 적합해 역산한 계수. fit_yields.py 참조.
#
#   마진 = Σ(수율 × 제품크랙) − 운영비
#
# 크랙이 모두 Dubai 기준이라 이 형태로 성립한다. 수율 합이 1보다 작은
# 만큼이 자가소비·손실(Complex 6.9%, Simple 2.9%)에 해당한다.
#
# 적합도: Complex R²=1.0000 (잔차 최대 0.04), Simple R²=0.9999 (최대 0.05)
# 원표가 소수 첫째자리 반올림이므로 사실상 완전 재현이다.
#
# 해석도 물리적으로 타당하다. Complex는 경유 38%로 고도화 비중이 높고,
# Simple은 B-C가 42%로 잔사유가 그대로 남는다.
COMPLEX_YIELDS = {
    "crack_naphtha":    0.1652,
    "crack_gasoline95": 0.1626,
    "crack_kerosene":   0.1604,
    "crack_diesel005":  0.3836,
    "crack_hsfo180":    0.0588,
}
COMPLEX_OPEX = 0.1965

SIMPLE_YIELDS = {
    "crack_naphtha":    0.0945,
    "crack_gasoline95": 0.0984,
    "crack_kerosene":   0.1286,
    "crack_diesel005":  0.2253,
    "crack_hsfo180":    0.4244,
}
SIMPLE_OPEX = -0.0267
