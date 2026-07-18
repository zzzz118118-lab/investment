# -*- coding: utf-8 -*-
"""크랙 스프레드 및 정제마진 계산.

정제마진은 페트로넷이 게시하지 않아 자체 산출한다. 다만 임의 가정이 아니라
하나증권 공표 시계열에 수율을 역산 적합한 계수를 쓰므로(config 참조)
하나증권 Complex/Simple Crack을 사실상 그대로 재현한다.
"""
import config


def add_cracks(row):
    """row(dict)에 제품별 크랙(제품가 - Dubai)을 추가."""
    dubai = row.get("dubai")
    if dubai is None:
        return row
    for p in config.CRACK_PRODUCTS:
        if row.get(p) is not None:
            row["crack_" + p] = round(row[p] - dubai, 2)
    return row


def _weighted(row, yields, opex):
    """Σ(수율 × 크랙) − 운영비. 크랙이 하나라도 없으면 None."""
    total = 0.0
    for crack_col, w in yields.items():
        v = row.get(crack_col)
        if v is None:
            return None
        total += v * w
    return round(total - opex, 2)


def complex_margin(row):
    return _weighted(row, config.COMPLEX_YIELDS, config.COMPLEX_OPEX)


def simple_margin(row):
    return _weighted(row, config.SIMPLE_YIELDS, config.SIMPLE_OPEX)


def enrich(row):
    """크랙 + 복합/단순 마진을 계산해 넣은 dict를 반환."""
    row = dict(row)
    add_cracks(row)
    for name, fn in (("complex_margin", complex_margin),
                     ("simple_margin", simple_margin)):
        v = fn(row)
        if v is not None:
            row[name] = v
    return row


if __name__ == "__main__":
    # 하나증권 2026-07-15 자: Complex 43.5 / Simple 30.3
    sample = {"dubai": 79.29, "gasoline95": 109.81, "kerosene": 148.13,
              "diesel005": 145.79, "naphtha": 90.60, "hsfo180": 84.88}
    out = enrich(sample)
    print("complex_margin %6.2f   (하나 43.5)" % out["complex_margin"])
    print("simple_margin  %6.2f   (하나 30.3)" % out["simple_margin"])
