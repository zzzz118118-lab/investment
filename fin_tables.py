# -*- coding: utf-8 -*-
"""주가·실적 표 조립.

기간을 하드코딩하지 않는다. 네이버는 최근 3개년/6분기만 노출하고 시간이
가면 그 창이 밀리므로, 컬럼을 해석해 '오늘 기준 과거 5년 + 향후 2년'을
매번 다시 만든다.

값 우선순위 (높은 쪽이 이긴다):
    리포트 추정 < 컨센서스 < 네이버 추정 < DART 확정 < 네이버 확정

따라서 3Q26 실적이 실제로 발표되면 신영증권 추정치를 자동으로 밀어낸다.
"""
from datetime import date

import pandas as pd

import charts
import config
import financials

# (우선순위, 라벨) — 숫자가 클수록 이긴다
SRC = {"리포트": 1, "컨센서스": 2, "네이버추정": 3, "DART": 4, "네이버실적": 5}
ACTUAL = {"DART", "네이버실적"}

METRICS = ["revenue", "op", "np", "eps", "dps", "div_yield", "per", "pbr"]


def _n(v, d=0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return "{:,.{}f}".format(v, d)


def _margin(num, den):
    return (num / den * 100) if (num not in (None, 0) and den) else None


class Cell(dict):
    """한 기간의 값 묶음. put()으로 우선순위가 높은 출처만 남긴다."""

    def __init__(self):
        super().__init__()
        self.src = None

    def put(self, src, vals):
        if self.src and SRC[src] < SRC[self.src]:
            return
        for k, v in vals.items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            self[k] = float(v)
        self.src = src if not self.src or SRC[src] > SRC[self.src] else self.src

    @property
    def is_actual(self):
        return self.src in ACTUAL


def _est_lookup(est, source, period):
    if est.empty:
        return {}
    m = est[(est.source == source) & (est.period == period)]
    if m.empty:
        return {}
    r = m.iloc[0]
    # 리포트 CSV는 십억원 단위 -> 억원으로 맞춘다
    out = {}
    for k, scale in (("revenue", 10), ("op", 10), ("np", 10),
                     ("eps", 1), ("dps", 1)):
        v = r.get(k)
        if v is not None and not pd.isna(v):
            out[k] = float(v) * scale
    return out


def collect_annual(d, years):
    """{year: Cell} 구성."""
    ann, est = d["annual"], d["estimates"]
    cells = {y: Cell() for y in years}

    # 1) 증권사 리포트 (가장 낮은 우선순위) — 컨센서스가 없는 칸만 메운다
    for y in years:
        for src in ("하나", "신영"):
            v = _est_lookup(est, src, "%dF" % y)
            if v:
                cells[y].put("리포트", v)

    # 2) 컨센서스
    for y in years:
        v = _est_lookup(est, "컨센서스", "%dF" % y)
        if v:
            cells[y].put("컨센서스", v)

    # 3) DART 확정 실적
    hp = config.DATA / "financials_history.csv"
    if hp.exists():
        h = pd.read_csv(hp, comment="#").set_index("year")
        for y in years:
            if y in h.index:
                cells[y].put("DART", {k: h.at[y, k] for k in METRICS if k in h.columns})

    # 4) 네이버 (실적/추정)
    for col in ann.index:
        p = financials.parse_period(col)
        if not p:
            continue
        y, _, is_est = p
        if y not in cells:
            continue
        vals = {k: ann.at[col, k] for k in METRICS if k in ann.columns}
        vals["op_margin"] = ann.at[col, "op_margin"] if "op_margin" in ann.columns else None
        vals["np_margin"] = ann.at[col, "np_margin"] if "np_margin" in ann.columns else None
        cells[y].put("네이버추정" if is_est else "네이버실적", vals)

    return cells


def collect_quarterly(d, year):
    """{quarter: Cell} 구성 (1~4분기)."""
    qtr, est = d["quarterly"], d["estimates"]
    cells = {q: Cell() for q in (1, 2, 3, 4)}

    for q in cells:
        for src in ("하나", "신영"):
            for label in ("%dQ%02dF" % (q, year % 100), "%dQ%02d" % (q, year % 100)):
                v = _est_lookup(est, src, label)
                if v:
                    cells[q].put("리포트", v)
                    break

    for col in qtr.index:
        p = financials.parse_period(col)
        if not p:
            continue
        y, mon, is_est = p
        if y != year:
            continue
        q = (mon + 2) // 3
        if q not in cells:
            continue
        vals = {k: qtr.at[col, k] for k in METRICS if k in qtr.columns}
        vals["op_margin"] = qtr.at[col, "op_margin"] if "op_margin" in qtr.columns else None
        vals["np_margin"] = qtr.at[col, "np_margin"] if "np_margin" in qtr.columns else None
        cells[q].put("네이버추정" if is_est else "네이버실적", vals)

    return cells


def _rows(cells, keys, labels, price):
    """표 본문 행 생성. cells는 {key: Cell}."""
    def g(c, k):
        return c.get(k)

    def m(c, key, a, b):
        v = g(c, key)
        return v if v is not None else _margin(g(c, a), g(c, b))

    out = [
        ["매출액"] + [_n(g(cells[k], "revenue")) for k in keys],
        ["영업이익"] + [_n(g(cells[k], "op")) for k in keys],
        ["영업이익률 (%)"] + [_n(m(cells[k], "op_margin", "op", "revenue"), 2) for k in keys],
        ["당기순이익"] + [_n(g(cells[k], "np")) for k in keys],
        ["순이익률 (%)"] + [_n(m(cells[k], "np_margin", "np", "revenue"), 2) for k in keys],
    ]
    if labels == "annual":
        def yld(c):
            v = g(c, "div_yield")
            if v is not None and c.is_actual:
                return v
            dps = g(c, "dps")
            return (dps / price * 100) if (dps and price) else None

        out += [
            ["EPS (원)"] + [_n(g(cells[k], "eps")) for k in keys],
            ["주당배당금 (원)"] + [_n(g(cells[k], "dps")) for k in keys],
            ["배당수익률 (%)"] + [_n(yld(cells[k]), 2) for k in keys],
        ]
    out.append(["출처"] + [cells[k].src or "-" for k in keys])
    return out


def build(d):
    """(주가 헤더 html, (연간표, 분기표, 비교표)) 반환."""
    px = d["price"]
    price = px.get("price")
    today = date.today()
    years = list(range(today.year - 5, today.year + 2))   # 과거 5년 + 올해 + 내년

    ac = collect_annual(d, years)
    hdr = ["항목"] + ["%d%s" % (y, "" if ac[y].is_actual else "F") for y in years]
    last_actual = max([i for i, y in enumerate(years) if ac[y].is_actual] or [-1])
    t_year = charts.simple_table(hdr, _rows(ac, years, "annual", price),
                                 split_after=last_actual)

    qc = collect_quarterly(d, today.year)
    qs = [1, 2, 3, 4]
    q_hdr = ["항목"] + ["%dQ%02d%s" % (q, today.year % 100,
                                      "" if qc[q].is_actual else "F") for q in qs]
    q_last = max([i for i, q in enumerate(qs) if qc[q].is_actual] or [-1])
    t_qtr = charts.simple_table(q_hdr, _rows(qc, qs, "quarter", price),
                                split_after=q_last)

    # 컨센서스 vs 증권사 (영업이익)
    est = d["estimates"]
    cmp_rows = []
    for y in (today.year, today.year + 1):
        p = "%dF" % y
        # 네이버 컨센서스가 리포트에 인쇄된 스냅샷보다 최신이므로 그쪽을 먼저 쓴다
        cons = ac[y].get("op") if ac[y].src == "네이버추정" else None
        if cons is None:
            cons = _est_lookup(est, "컨센서스", p).get("op")
        sy = _est_lookup(est, "신영", p).get("op")
        ha = _est_lookup(est, "하나", p).get("op")
        if any(v is not None for v in (cons, sy, ha)):
            cmp_rows.append(["%d 영업이익" % y, _n(cons), _n(sy), _n(ha)])
    t_cmp = charts.simple_table(["구분", "컨센서스", "신영증권", "하나증권"], cmp_rows)

    chg, pct = px.get("change"), px.get("change_pct")
    cls = "up" if (chg or 0) > 0 else ("down" if (chg or 0) < 0 else "flat")
    arrow = "▲" if (chg or 0) > 0 else ("▼" if (chg or 0) < 0 else "")
    cy = ac[today.year]
    val = ""
    if cy.get("per") or cy.get("pbr"):
        val = "<br>%d년 PER %s배 · PBR %s배" % (today.year, _n(cy.get("per"), 2),
                                              _n(cy.get("pbr"), 2))
    head = ('<div class="pxrow"><div><div class="tl">현재가</div>'
            '<div class="pxv">%s<span class="tu">원</span></div>'
            '<div class="tm"><span class="dl %s">%s %s (%s%%)</span></div></div>'
            '<div class="pxmeta">시가총액 %s억원%s</div></div>'
            % (_n(price), cls, arrow, _n(abs(chg) if chg else None),
               _n(pct, 2), _n(px.get("mktcap")), val))
    return head, (t_year, t_qtr, t_cmp)
