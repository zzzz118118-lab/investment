# -*- coding: utf-8 -*-
"""HTML 대시보드 생성.

    python dashboard.py            # data/dashboard.html 생성
    python dashboard.py --open     # 생성 후 브라우저로 열기
"""
import sys
import webbrowser
from datetime import datetime

import pandas as pd

import aggregate
import charts
import config
import store

OUT = config.SITE / "index.html"

# 두 리포트가 제시한 기준선 (README 참조)
BENCH = [
    ("20년 평균", None),          # 실데이터에서 계산
    ("신영 리포트 복합마진", 33.2),
    ("하나 2Q26 평균", 37.1),
]


def _fmt(v, d=1):
    return "-" if v is None or pd.isna(v) else ("%,.*f" % (d, v)).replace("%", "")


def num(v, d=1):
    if v is None or pd.isna(v):
        return "-"
    return "{:,.{}f}".format(v, d)


def delta_html(cur, prev, d=1):
    if cur is None or prev is None or pd.isna(cur) or pd.isna(prev):
        return '<span class="dl flat">-</span>'
    diff = cur - prev
    if abs(diff) < 10 ** (-d) / 2:
        return '<span class="dl flat">보합</span>'
    cls = "up" if diff > 0 else "down"
    arrow = "▲" if diff > 0 else "▼"
    return '<span class="dl %s">%s %s</span>' % (cls, arrow, num(abs(diff), d))


def tile(label, value, prev=None, unit="", d=1, note=""):
    return ('<div class="tile"><div class="tl">%s</div>'
            '<div class="tv">%s<span class="tu">%s</span></div>'
            '<div class="tm">%s%s</div></div>'
            % (label, num(value, d), unit,
               delta_html(value, prev, d),
               ('<span class="note">%s</span>' % note) if note else ""))


def _n(v, d=0):
    """억원/원 단위 정수 포맷. None은 '-'."""
    if v is None or pd.isna(v):
        return "-"
    return "{:,.{}f}".format(v, d)


def build_financials():
    """주가 + 재무 표. 수집 실패 시 ('', '') 을 돌려주고 카드를 생략한다."""
    try:
        import financials
        d = financials.fetch_all()
    except Exception as e:
        print("  [경고] 재무 수집 실패: %s" % e)
        return "", ""

    px, ann, qtr, est = d["price"], d["annual"], d["quarterly"], d["estimates"]
    price = px.get("price")

    def e(src, period, col):
        if est.empty:
            return None
        m = est[(est.source == src) & (est.period == period)]
        if m.empty or pd.isna(m.iloc[0][col]):
            return None
        return float(m.iloc[0][col])

    def a(period, key):
        return ann.at[period, key] if period in ann.index and key in ann.columns else None

    # ── 연간: 2021~2025 실적 + 2026F/2027F 컨센서스 ────────────
    # 네이버는 억원, 리포트 CSV는 십억원이므로 10배로 맞춘다.
    # 2021~2022는 네이버가 주지 않아 DART에서 1회 받아둔 CSV를 쓴다.
    hist = {}
    hp = config.DATA / "financials_history.csv"
    if hp.exists():
        hdf = pd.read_csv(hp, comment="#").set_index("year")
        hist = {int(y): r for y, r in hdf.iterrows()}

    def hv(year, key):
        r = hist.get(year)
        if r is None or key not in r or pd.isna(r[key]):
            return None
        return float(r[key])

    hyrs = sorted(hist)                      # [2021, 2022]
    yrs = ["2023.12", "2024.12", "2025.12"]
    hdr = ["항목"] + [str(y) for y in hyrs] + ["2023", "2024", "2025", "2026F", "2027F"]

    c26_rev, c26_op, c26_np = a("2026.12(E)", "revenue"), a("2026.12(E)", "op"), a("2026.12(E)", "np")
    c27_rev = (e("컨센서스", "2027F", "revenue") or 0) * 10 or None
    c27_op = (e("컨센서스", "2027F", "op") or 0) * 10 or None
    c27_np = (e("컨센서스", "2027F", "np") or 0) * 10 or None

    def margin(num, den):
        return (num / den * 100) if (num is not None and den) else None

    def yld(dps):
        return (dps / price * 100) if (dps and price) else None

    d26_dps = a("2026.12(E)", "dps")
    d27_dps = e("신영", "2027F", "dps")   # 컨센서스 DPS가 없어 신영 추정치를 쓴다

    rows = [
        ["매출액"] + [_n(hv(y, "revenue")) for y in hyrs]
        + [_n(a(y, "revenue")) for y in yrs] + [_n(c26_rev), _n(c27_rev)],
        ["영업이익"] + [_n(hv(y, "op")) for y in hyrs]
        + [_n(a(y, "op")) for y in yrs] + [_n(c26_op), _n(c27_op)],
        ["영업이익률 (%)"] + [_n(margin(hv(y, "op"), hv(y, "revenue")), 2) for y in hyrs]
        + [_n(a(y, "op_margin"), 2) for y in yrs]
        + [_n(margin(c26_op, c26_rev), 2), _n(margin(c27_op, c27_rev), 2)],
        ["당기순이익"] + [_n(hv(y, "np")) for y in hyrs]
        + [_n(a(y, "np")) for y in yrs] + [_n(c26_np), _n(c27_np)],
        ["순이익률 (%)"] + [_n(margin(hv(y, "np"), hv(y, "revenue")), 2) for y in hyrs]
        + [_n(a(y, "np_margin"), 2) for y in yrs]
        + [_n(margin(c26_np, c26_rev), 2), _n(margin(c27_np, c27_rev), 2)],
        ["EPS (원)"] + [_n(hv(y, "eps")) for y in hyrs]
        + [_n(a(y, "eps")) for y in yrs]
        + [_n(a("2026.12(E)", "eps")), _n(e("컨센서스", "2027F", "eps"))],
        ["주당배당금 (원)"] + [_n(hv(y, "dps")) for y in hyrs]
        + [_n(a(y, "dps")) for y in yrs] + [_n(d26_dps), _n(d27_dps)],
        ["배당수익률 (%)"] + [_n(hv(y, "div_yield"), 2) for y in hyrs]
        + [_n(a(y, "div_yield"), 2) for y in yrs]
        + [_n(yld(d26_dps), 2), _n(yld(d27_dps), 2)],
    ]
    t_year = charts.simple_table(hdr, rows, split_after=len(hyrs) + 3)

    # ── 2026 분기 ───────────────────────────────────────────
    q_hdr = ["항목", "1Q26", "2Q26F", "3Q26F", "4Q26F"]

    def q(period, key):
        return qtr.at[period, key] if period in qtr.index and key in qtr.columns else None

    q1r, q1o, q1n = q("2026.03", "revenue"), q("2026.03", "op"), q("2026.03", "np")
    q2r, q2o, q2n = q("2026.06(E)", "revenue"), q("2026.06(E)", "op"), q("2026.06(E)", "np")
    q3r = (e("신영", "3Q26F", "revenue") or 0) * 10 or None
    q3o = (e("신영", "3Q26F", "op") or 0) * 10 or None
    q3n = (e("신영", "3Q26F", "np") or 0) * 10 or None
    q4r = (e("신영", "4Q26F", "revenue") or 0) * 10 or None
    q4o = (e("신영", "4Q26F", "op") or 0) * 10 or None
    q4n = (e("신영", "4Q26F", "np") or 0) * 10 or None

    q_rows = [
        ["매출액", _n(q1r), _n(q2r), _n(q3r), _n(q4r)],
        ["영업이익", _n(q1o), _n(q2o), _n(q3o), _n(q4o)],
        ["영업이익률 (%)", _n(margin(q1o, q1r), 2), _n(margin(q2o, q2r), 2),
         _n(margin(q3o, q3r), 2), _n(margin(q4o, q4r), 2)],
        ["당기순이익", _n(q1n), _n(q2n), _n(q3n), _n(q4n)],
        ["순이익률 (%)", _n(margin(q1n, q1r), 2), _n(margin(q2n, q2r), 2),
         _n(margin(q3n, q3r), 2), _n(margin(q4n, q4r), 2)],
    ]
    t_qtr = charts.simple_table(q_hdr, q_rows, split_after=1)

    # ── 컨센서스 vs 증권사 ───────────────────────────────────
    cmp_rows = []
    for period, cons in (("2026F", c26_op), ("2027F", c27_op)):
        sy = (e("신영", period, "op") or 0) * 10 or None
        ha = (e("하나", period, "op") or 0) * 10 or None
        cmp_rows.append([period + " 영업이익", _n(cons), _n(sy), _n(ha)])
    t_cmp = charts.simple_table(["구분", "컨센서스", "신영증권", "하나증권"], cmp_rows)

    chg = px.get("change")
    chg_pct = px.get("change_pct")
    cls = "up" if (chg or 0) > 0 else ("down" if (chg or 0) < 0 else "flat")
    arrow = "▲" if (chg or 0) > 0 else ("▼" if (chg or 0) < 0 else "")
    head = ('<div class="pxrow"><div><div class="tl">현재가</div>'
            '<div class="pxv">%s<span class="tu">원</span></div>'
            '<div class="tm"><span class="dl %s">%s %s (%s%%)</span></div></div>'
            '<div class="pxmeta">시가총액 %s억원<br>2026F PER %s배 · PBR %s배</div></div>'
            % (_n(price), cls, arrow, _n(abs(chg) if chg else None),
               _n(chg_pct, 2), _n(px.get("mktcap")),
               _n(a("2026.12(E)", "per"), 2), _n(a("2026.12(E)", "pbr"), 2)))

    return head, (t_year, t_qtr, t_cmp)


def build():
    df = store.load(config.PRICES_CSV)
    if df.empty:
        raise SystemExit("prices.csv가 비어 있습니다. collect.py를 먼저 실행하세요.")

    agg = aggregate.load_all()
    wk, mo, yr = agg["weekly"], agg["monthly"], agg["yearly"]

    def two(col):
        return store.latest_two(df, col)

    cm, cm_p = two("complex_margin")
    sm, sm_p = two("simple_margin")
    du, du_p = two("dubai")
    ke, ke_p = two("crack_kerosene")
    di, di_p = two("crack_diesel005")
    ga, ga_p = two("crack_gasoline95")
    osp = df["osp_arab_light"].dropna().iloc[-1] if "osp_arab_light" in df.columns \
        and df["osp_arab_light"].notna().any() else None

    fxdf = store.load(config.FX_CSV)
    fxv = fxdf["usdkrw"].dropna().iloc[-1] if not fxdf.empty and "usdkrw" in fxdf else None

    asof = df.index.max().date()
    hist_avg = df["complex_margin"].mean()
    pct = (df["complex_margin"] < cm).mean() * 100 if cm is not None else None

    # 자동 실행이 조용히 실패하면 낡은 숫자를 최신인 줄 알고 볼 위험이 있다.
    # 원자료가 며칠 이상 멈추면 화면에 드러낸다.
    stale = (datetime.today().date() - asof).days
    banner = ""
    if stale > 4:
        banner = ('<div class="warn">원자료가 <b>%d일째</b> 갱신되지 않았습니다 '
                  '(최신 %s). 아래 숫자는 그 시점 기준입니다.</div>' % (stale, asof))

    # ── 차트 1: 복합/단순 마진 (일·주·월 전환) ───────────────────
    periods = [
        ("d", "일", "최근 120영업일", df.tail(120), "%m/%d", "%Y-%m-%d", "날짜"),
        ("w", "주", "최근 52주 (금요일 기준)", wk, "%y/%m/%d", "%Y-%m-%d", "주"),
        ("m", "월", "최근 24개월", mo, "%y-%m", "%Y-%m", "월"),
    ]
    blocks, datas = [], {}
    for i, (key, _lab, cap, d, xfmt, tfmt, tcol) in enumerate(periods):
        cid = "c1" + key
        svg, js = charts.line_chart(
            cid, [x.strftime(xfmt) for x in d.index],
            [("복합", [None if pd.isna(v) else round(v, 2) for v in d["complex_margin"]]),
             ("단순", [None if pd.isna(v) else round(v, 2) for v in d["simple_margin"]])],
            height=310, direct_labels=True)
        datas[cid] = js
        tbl = charts.table_view(
            [tcol, "복합마진", "단순마진", "Dubai", "등유크랙", "경유크랙"],
            [[x.strftime(tfmt), num(r.complex_margin), num(r.simple_margin),
              num(r.dubai), num(r.crack_kerosene), num(r.crack_diesel005)]
             for x, r in d[::-1].iterrows()], cap)
        blocks.append('<div class="pane" data-p="%s"%s><p class="cap">%s</p>%s%s</div>'
                      % (key, "" if i == 0 else ' hidden', cap, svg, tbl))
    c1 = ('<div class="seg" role="tablist">'
          + "".join('<button role="tab" data-p="%s"%s>%s</button>'
                    % (k, ' aria-selected="true"' if i == 0 else '', lab)
                    for i, (k, lab, *_) in enumerate(periods))
          + "</div>" + "".join(blocks))
    t1 = ""

    # ── 차트 2: 크랙 5종 최근 120영업일 ──────────────────────────
    d120 = df.tail(120)
    dl = [d.strftime("%m/%d") for d in d120.index]
    pairs = [("납사", "crack_naphtha"), ("가솔린", "crack_gasoline95"),
             ("등유", "crack_kerosene"), ("경유", "crack_diesel005"),
             ("B-C", "crack_hsfo180")]
    c2, c2d = charts.line_chart(
        "c2", dl,
        [(nm, [None if pd.isna(v) else round(v, 2) for v in d120[c]]) for nm, c in pairs],
        height=340, direct_labels=True)
    t2 = charts.table_view(
        ["날짜"] + [nm for nm, _ in pairs],
        [[d.strftime("%Y-%m-%d")] + [num(r[c]) for _, c in pairs]
         for d, r in d120.tail(30).iterrows()], "크랙 최근 30일")

    # ── 차트 3: 연평균 20년 ─────────────────────────────────────
    yl = [str(d.year) for d in yr.index]
    c3, _ = charts.bar_chart("c3", yl,
                             [None if pd.isna(v) else round(v, 2)
                              for v in yr["complex_margin"]], height=280)
    t3 = charts.table_view(
        ["연도", "복합마진", "단순마진", "Dubai", "등유크랙", "경유크랙"],
        [[d.year, num(r.complex_margin), num(r.simple_margin), num(r.dubai),
          num(r.crack_kerosene), num(r.crack_diesel005)] for d, r in yr.iterrows()],
        "연간 20년")

    # ── 월 24개월 표 ────────────────────────────────────────────
    t4 = charts.table_view(
        ["월", "복합마진", "단순마진", "Dubai", "등유크랙", "경유크랙", "가솔린크랙"],
        [[d.strftime("%Y-%m"), num(r.complex_margin), num(r.simple_margin),
          num(r.dubai), num(r.crack_kerosene), num(r.crack_diesel005),
          num(r.crack_gasoline95)] for d, r in mo.iterrows()],
        "월간 24개월")

    tiles = "".join([
        tile("Dubai", du, du_p, " $/bbl"),
        tile("등유 크랙", ke, ke_p, " $/bbl"),
        tile("경유 크랙", di, di_p, " $/bbl"),
        tile("가솔린 크랙", ga, ga_p, " $/bbl"),
        tile("단순정제마진", sm, sm_p, " $/bbl"),
        tile("OSP Arab Light", osp, None, " $/bbl", 1, "월간"),
        tile("원/달러", fxv, None, "", 0, "스냅샷"),
    ])

    px_head, fin_tables = build_financials()
    if fin_tables:
        t_year, t_qtr, t_cmp = fin_tables
        fin_card = FIN_CARD.format(px=px_head, t_year=t_year, t_qtr=t_qtr, t_cmp=t_cmp)
    else:
        fin_card = ""

    html = TEMPLATE.format(
        fin_card=fin_card,
        asof=asof, generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        hero=num(cm, 2), hero_delta=delta_html(cm, cm_p, 2),
        hist_avg=num(hist_avg, 1),
        pct=num(pct, 0), nrows=len(df),
        span="%s ~ %s" % (df.index.min().date(), df.index.max().date()),
        tiles=tiles, banner=banner,
        c1=c1, t1=t1, c2=c2, t2=t2, c3=c3, t3=t3, t4=t4,
        chartdata=", ".join('"%s": %s' % (k, v) for k, v in
                            list(datas.items()) + [("c2", c2d)]),
    )
    OUT.write_text(html, encoding="utf-8")
    return OUT


FIN_CARD = """
<div class="card">
  <h2>주가 · 실적</h2>
  {px}
  <h3>연간</h3>
  <p class="cap">단위: 억원. 2026F·2027F는 컨센서스이며, 회색 세로선 왼쪽이 확정 실적이다.</p>
  {t_year}
  <h3>2026년 분기</h3>
  <p class="cap">1Q26은 확정 실적, 2Q26F는 컨센서스, 3Q·4Q26F는 신영증권 추정치다.</p>
  {t_qtr}
  <h3>2026~27 영업이익 — 컨센서스 대비</h3>
  <p class="cap">두 증권사 모두 컨센서스보다 공격적이다. 특히 2027년 차이가 크다.</p>
  {t_cmp}
  <p class="cap" style="margin-top:14px">
    실적·컨센서스는 네이버 금융(FnGuide), 증권사 추정치는 신영증권 2026-07-15 /
    하나증권 2026-07-07 리포트.
    2021~2022년은 네이버가 제공하지 않아 DART 사업보고서(연결)에서 1회 받아
    고정해 두었다 — 확정 실적이라 갱신이 필요 없다.
    2027F 주당배당금만 컨센서스가 없어 신영증권 추정치(6,000원)를 썼고,
    추정 연도의 배당수익률은 현재가 기준으로 계산했다.
  </p>
</div>
"""

TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>S-Oil 정제마진 트래커 — {asof}</title>
<style>
:root {{
  color-scheme: light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --base:#c3c2b7; --ring:rgba(11,11,11,0.10);
  --up:#006300; --down:#d03b3b; --accent:#2a78d6;
  --mode:0;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --base:#383835; --ring:rgba(255,255,255,0.10);
    --up:#0ca30c; --down:#d03b3b; --accent:#3987e5;
    --mode:1;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --base:#383835; --ring:rgba(255,255,255,0.10);
  --up:#0ca30c; --down:#d03b3b; --accent:#3987e5;
  --mode:1;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--plane); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:28px 20px 64px; }}
header {{ display:flex; justify-content:space-between; align-items:baseline;
  flex-wrap:wrap; gap:8px; margin-bottom:20px; }}
h1 {{ font-size:20px; margin:0; letter-spacing:-0.01em; }}
.sub {{ color:var(--muted); font-size:13px; }}
.card {{ background:var(--surface-1); border:1px solid var(--ring);
  border-radius:12px; padding:20px; margin-bottom:18px; }}
.warn {{ background:var(--surface-1); border:1px solid #ec835a;
  border-left:4px solid #ec835a; border-radius:10px; padding:13px 16px;
  margin-bottom:16px; font-size:13.5px; color:var(--ink2); }}
.warn b {{ color:var(--ink); }}
.hero {{ display:flex; align-items:flex-end; gap:20px; flex-wrap:wrap; }}
.hv {{ font-size:52px; font-weight:600; line-height:1; letter-spacing:-0.02em; }}
.hu {{ font-size:17px; color:var(--ink2); margin-left:6px; font-weight:400; }}
.hl {{ font-size:13px; color:var(--muted); margin-bottom:6px; }}
.ctx {{ color:var(--ink2); font-size:13.5px; margin-top:12px; }}
.ctx b {{ color:var(--ink); font-weight:600; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(152px,1fr));
  gap:10px; margin-bottom:18px; }}
.tile {{ background:var(--surface-1); border:1px solid var(--ring);
  border-radius:10px; padding:14px 16px; }}
.tl {{ font-size:12px; color:var(--muted); }}
.tv {{ font-size:23px; font-weight:600; margin:3px 0 2px; letter-spacing:-0.01em; }}
.tu {{ font-size:12px; color:var(--muted); font-weight:400; }}
.tm {{ font-size:12px; display:flex; gap:6px; align-items:center; }}
.dl.up {{ color:var(--up); }} .dl.down {{ color:var(--down); }}
.dl.flat {{ color:var(--muted); }}
.note {{ color:var(--muted); }}
h2 {{ font-size:15px; margin:0 0 3px; }}
.cap {{ font-size:12.5px; color:var(--muted); margin:0 0 14px; }}
.chart {{ width:100%; height:auto; display:block; overflow:visible; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.baseline {{ stroke:var(--base); stroke-width:1; }}
.axis {{ fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }}
.ar {{ text-anchor:end; }} .am {{ text-anchor:middle; }}
.ln {{ stroke:var(--c); }} .pt {{ fill:var(--c); stroke:var(--surface-1); stroke-width:2; }}
.dlab {{ fill:var(--ink2); font-size:11.5px; font-weight:500; }}
.lead {{ stroke:var(--base); stroke-width:1; }}
.bar {{ fill:var(--accent); opacity:.55; }}
.bar.hi {{ opacity:1; }}
.cross {{ stroke:var(--base); stroke-width:1; stroke-dasharray:3 3; pointer-events:none; }}
:root[data-theme="dark"] .ln, :root[data-theme="dark"] .pt {{ --c:var(--cd); }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) .ln, :root:not([data-theme="light"]) .pt {{ --c:var(--cd); }}
}}
.seg {{ display:inline-flex; gap:2px; padding:2px; margin:12px 0 4px;
  background:var(--plane); border:1px solid var(--ring); border-radius:9px; }}
.seg button {{ font:inherit; font-size:13px; color:var(--ink2); background:none;
  border:0; padding:5px 16px; border-radius:7px; cursor:pointer; }}
.seg button:hover {{ color:var(--ink); }}
.seg button[aria-selected="true"] {{ background:var(--surface-1); color:var(--ink);
  font-weight:600; box-shadow:0 1px 3px rgba(0,0,0,.10); }}
.pane[hidden] {{ display:none; }}
.legend {{ display:flex; gap:16px; flex-wrap:wrap; margin:10px 0 2px; font-size:12.5px;
  color:var(--ink2); }}
.legend i {{ width:11px; height:11px; border-radius:3px; display:inline-block;
  margin-right:5px; vertical-align:-1px; }}
h3 {{ font-size:13.5px; margin:22px 0 3px; color:var(--ink); }}
.pxrow {{ display:flex; justify-content:space-between; align-items:flex-end;
  flex-wrap:wrap; gap:12px; padding-bottom:6px; }}
.pxv {{ font-size:34px; font-weight:600; line-height:1.1; letter-spacing:-0.02em; }}
.pxmeta {{ font-size:12.5px; color:var(--muted); text-align:right; line-height:1.6; }}
table.fin {{ min-width:520px; }}
table.fin td:first-child, table.fin th:first-child {{ text-align:left;
  color:var(--ink2); white-space:nowrap; }}
table.fin tbody tr:hover {{ background:var(--plane); }}
table.fin .neg {{ color:var(--down); }}
table.fin .sep {{ border-left:2px solid var(--base); }}
.tbl {{ margin-top:12px; }}
.tbl summary {{ cursor:pointer; color:var(--ink2); font-size:12.5px; padding:5px 0; }}
.scroll {{ overflow-x:auto; margin-top:8px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px;
  font-variant-numeric:tabular-nums; }}
th,td {{ padding:6px 10px; text-align:right; border-bottom:1px solid var(--grid);
  white-space:nowrap; }}
th:first-child,td:first-child {{ text-align:left; }}
th {{ color:var(--muted); font-weight:500; }}
.tip {{ position:fixed; pointer-events:none; background:var(--surface-1);
  border:1px solid var(--ring); border-radius:8px; padding:8px 10px; font-size:12px;
  box-shadow:0 4px 16px rgba(0,0,0,.14); display:none; z-index:9;
  font-variant-numeric:tabular-nums; }}
.tip b {{ display:block; margin-bottom:4px; color:var(--ink); }}
.tip .r {{ display:flex; justify-content:space-between; gap:14px; color:var(--ink2); }}
.tip i {{ width:8px; height:8px; border-radius:2px; display:inline-block; margin-right:5px; }}
footer {{ color:var(--muted); font-size:12px; margin-top:26px; line-height:1.7; }}
</style></head><body>
<div class="wrap">
<header>
  <h1>S-Oil 정제마진 트래커</h1>
  <div class="sub">기준일 {asof} · 생성 {generated}</div>
</header>

{banner}
{fin_card}
<div class="card">
  <div class="hero">
    <div>
      <div class="hl">복합정제마진 (Complex Crack)</div>
      <div class="hv">{hero}<span class="hu">$/bbl</span></div>
    </div>
    <div style="padding-bottom:6px">{hero_delta} <span class="note">전일 대비</span></div>
  </div>
  <div class="ctx">
    20년 평균 <b>{hist_avg}</b> · 과거 관측의 <b>{pct}%</b>보다 높은 수준입니다.
  </div>
</div>

<div class="tiles">{tiles}</div>

<div class="card">
  <h2>정제마진 추이</h2>
  <div class="legend">
    <span><i style="background:#2a78d6"></i>복합정제마진</span>
    <span><i style="background:#1baf7a"></i>단순정제마진</span>
  </div>
  {c1}{t1}
</div>

<div class="card">
  <h2>제품별 크랙 스프레드 — 최근 120영업일</h2>
  <p class="cap">각 제품가 − Dubai. 등·경유가 현 사이클의 엔진이다.</p>
  <div class="legend">
    <span><i style="background:#2a78d6"></i>납사</span>
    <span><i style="background:#1baf7a"></i>가솔린</span>
    <span><i style="background:#eda100"></i>등유</span>
    <span><i style="background:#008300"></i>경유</span>
    <span><i style="background:#4a3aa7"></i>B-C</span>
  </div>
  {c2}
  {t2}
</div>

<div class="card">
  <h2>복합정제마진 — 연평균 20년</h2>
  <p class="cap">올해가 과거 사이클 대비 어디쯤인지 본다. 마지막 막대가 올해.</p>
  {c3}
  {t3}
</div>

<div class="card">
  <h2>월 평균 — 최근 24개월</h2>
  <p class="cap">분기 실적 추정에 쓰는 단위.</p>
  {t4}
</div>

<footer>
데이터: 한국석유공사 페트로넷 (일별 {nrows}행, {span}) · 환율 네이버금융<br>
정제마진은 자체 산출이며, 수율을 하나증권 공표 시계열에 역산 적합해 검증했다
(Complex R²=1.0000). 산식이 바뀌면 어긋날 수 있다.<br>
투자 판단의 근거로 쓰기 전에 원자료를 확인할 것.
</footer>
</div>

<div class="tip" id="tip"></div>
<script>
const DATA = {{ {chartdata} }};

// 일 / 주 / 월 전환
document.querySelectorAll('.seg button').forEach(b => {{
  b.addEventListener('click', () => {{
    const seg = b.closest('.seg'), card = b.closest('.card'), p = b.dataset.p;
    seg.querySelectorAll('button').forEach(x =>
      x.setAttribute('aria-selected', String(x === b)));
    card.querySelectorAll('.pane').forEach(x => {{
      x.hidden = x.dataset.p !== p;
    }});
  }});
}});
const tip = document.getElementById('tip');
const dark = () => document.documentElement.dataset.theme === 'dark' ||
  (!document.documentElement.dataset.theme &&
   matchMedia('(prefers-color-scheme: dark)').matches);

for (const [id, m] of Object.entries(DATA)) {{
  const svg = document.getElementById(id);
  if (!svg || !m.labels) continue;
  const cross = document.getElementById(id + '-cross');
  const n = m.labels.length;
  svg.addEventListener('mousemove', ev => {{
    const r = svg.getBoundingClientRect();
    const vx = (ev.clientX - r.left) / r.width * m.w;
    let i = Math.round((vx - m.pad_l) / (m.iw / Math.max(n - 1, 1)));
    i = Math.max(0, Math.min(n - 1, i));
    const x = m.pad_l + m.iw * i / Math.max(n - 1, 1);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x);
    cross.style.display = '';
    let h = '<b>' + m.labels[i] + '</b>';
    let any = false;
    for (const s of m.series) {{
      const v = s.vals[i];
      if (v === null || v === undefined) continue;
      any = true;
      h += '<div class="r"><span><i style="background:' + (dark() ? s.cd : s.c) +
           '"></i>' + s.name + '</span><span>' + v.toFixed(2) + '</span></div>';
    }}
    if (!any) {{ tip.style.display = 'none'; return; }}
    tip.innerHTML = h;
    tip.style.display = 'block';
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let L = ev.clientX + 14, T = ev.clientY - th - 12;
    if (L + tw > innerWidth - 8) L = ev.clientX - tw - 14;
    if (T < 8) T = ev.clientY + 16;
    tip.style.left = L + 'px'; tip.style.top = T + 'px';
  }});
  svg.addEventListener('mouseleave', () => {{
    tip.style.display = 'none'; cross.style.display = 'none';
  }});
}}
</script>
</body></html>
"""


if __name__ == "__main__":
    p = build()
    print("생성: %s" % p)
    if "--open" in sys.argv:
        webbrowser.open(p.as_uri())
