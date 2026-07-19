# -*- coding: utf-8 -*-
"""제닉 트래커 HTML 대시보드 생성.

    python dashboard.py            # site/index.html 생성
    python dashboard.py --open     # 생성 후 브라우저로 열기

레이아웃은 soil-tracker와 같은 계열이다(카드 + 타일 + SVG 차트 + 표 뷰).
차이는 헤드라인 지표다. S-Oil이 정제마진(일별)이라면 제닉은
**마스크팩 수출액(월별)** 이 선행지표 자리에 온다.
"""
import sys
import webbrowser
from datetime import date, datetime

import pandas as pd

import charts
import config
import store

OUT = config.SITE / "index.html"

# 연간 매출/영업이익 실적 (억원). 네이버는 최근 3개년만 주므로 리포트 값을 고정한다.
# 세 리포트가 모두 같은 숫자를 싣고 있어 교차 확인됐다.
ANNUAL_HIST = [
    (2021, 384, -39), (2022, 314, -32), (2023, 281, -40),
    (2024, 499, 60), (2025, 782, 150),
]


def num(v, d=1):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return "{:,.{}f}".format(v, d)


def delta_html(pct, d=1, suffix="%"):
    """증감률을 화살표로. pct는 이미 % 단위."""
    if pct is None or pd.isna(pct):
        return '<span class="dl flat">-</span>'
    if abs(pct) < 0.05:
        return '<span class="dl flat">보합</span>'
    cls = "up" if pct > 0 else "down"
    return '<span class="dl %s">%s %s%s</span>' % (
        cls, "▲" if pct > 0 else "▼", num(abs(pct), d), suffix)


def tile(label, value, unit="", delta=None, note="", d=1):
    return ('<div class="tile"><div class="tl">%s</div>'
            '<div class="tv">%s<span class="tu">%s</span></div>'
            '<div class="tm">%s%s</div></div>'
            % (label, num(value, d) if not isinstance(value, str) else value, unit,
               delta if delta is not None else "",
               ('<span class="note">%s</span>' % note) if note else ""))


def qlabel(y, q):
    return "%dQ%02d" % (q, y % 100)


def build_freshness():
    """소스별 갱신 상태. 수동 소스가 밀리면 여기서 드러난다."""
    import freshness
    rows = freshness.write_status()

    trs = []
    for r in rows:
        age = "-" if r["age"] is None else "%d일 전" % r["age"]
        state = "갱신 필요" if r["stale"] else ("정상" if r["age"] is not None else "없음")
        trs.append([r["name"], "자동" if r["auto"] else "수동",
                    r["last"] or "-", age, state, r["note"]])
    tbl = charts.simple_table(
        ["소스", "방식", "최신", "경과", "상태", "갱신 방법"], trs)

    stale = [r["name"] for r in rows if r["stale"]]
    warn = ""
    if stale:
        warn = ('<div class="warn" style="margin:12px 0 0">'
                '<b>%s</b> 갱신이 필요합니다. 이 소스는 자동 수집이 안 되므로 '
                '직접 넣어야 합니다.</div>' % ", ".join(stale))

    return ('<div class="card" data-card="freshness"><h2>데이터 갱신 상태</h2>'
            '<p class="cap">자동 소스는 매일 07:00 KST에 GitHub Actions가 갱신한다. '
            '수동 소스는 아마존 ToS·유료 API 제약으로 자동화하지 않았다 — '
            'README 참조.</p>%s%s</div>' % (tbl, warn))


def build_cotrend(datas, df):
    """검색량 · 수출 · 매출 동행 카드.

    셋의 단위가 전혀 달라(검색 건수 / 백만달러 / 억원) 그대로는 한 축에 못 얹는다.
    기준 분기를 100으로 지수화한다. 매출이 분기 단위라 분기로 맞춘다.
    """
    import searches
    sq = searches.quarterly()
    if sq.empty:
        return ""

    # 마스크팩 수출 분기 합계 — 완결 분기만
    g = df["mask_usd"].groupby([df.index.year, df.index.quarter])
    eq = g.sum()[g.count() == 3] / 1e6

    # 쌓인 네이버 실적을 우선 쓴다. 새 분기가 발표되면 자동으로 늘어난다.
    import financials
    rev = financials.quarterly_revenue()
    base = config.INDEX_BASE
    if base not in sq.index or base not in eq.index or base not in rev:
        return ""

    keys = sorted(k for k in set(sq.index) | set(eq.index)
                  if k >= base and (k in sq.index or k in eq.index))
    labels = [qlabel(*k) for k in keys]

    def idx(series, b):
        return [None if k not in series or pd.isna(series[k])
                else round(series[k] / b * 100, 1) for k in keys]

    revs = pd.Series(rev)
    series = [
        ("제닉 매출", idx(revs, rev[base])),
        ("마스크팩 수출", idx(eq, eq[base])),
        ("바이오던스 검색량", idx(sq, sq[base])),
    ]
    svg, js = charts.line_chart("cco", labels, series, height=320,
                                ylabel="지수 (%s=100)" % qlabel(*base))
    datas["cco"] = js

    tbl = charts.table_view(
        ["분기", "제닉 매출(억원)", "지수", "마스크팩 수출(백만$)", "지수",
         "검색량", "지수"],
        [[qlabel(*k),
          num(rev.get(k), 0), num(rev[k] / rev[base] * 100, 1) if k in rev else "-",
          num(eq.get(k), 0), num(eq[k] / eq[base] * 100, 1) if k in eq.index else "-",
          num(sq.get(k), 0), num(sq[k] / sq[base] * 100, 1) if k in sq.index else "-"]
         for k in keys[::-1]], "동행 지표")

    last_s = keys[-1]
    grew = {}
    for name, s, b in [("검색량", sq, sq[base]), ("수출", eq, eq[base])]:
        if last_s in s.index:
            grew[name] = s[last_s] / b

    return ('<div class="card" data-card="cotrend"><h2>검색량 · 수출 · 매출 동행</h2>'
            '<p class="cap">%s를 100으로 지수화. 단위가 각각 건수·백만달러·억원이라 '
            '그대로는 한 축에 얹을 수 없어 배수로 환산했다.</p>'
            '<div class="legend">'
            '<span><i style="background:#2a78d6"></i>제닉 매출</span>'
            '<span><i style="background:#1baf7a"></i>마스크팩 수출</span>'
            '<span><i style="background:#eda100"></i>바이오던스 검색량</span>'
            '</div>%s%s'
            '<p class="cap" style="margin-top:14px">'
            '검색량은 %s 기준 <b>%.1f배</b>, 마스크팩 수출은 <b>%.1f배</b>가 됐다. '
            '제닉 매출선이 1Q26에서 끊기는 것은 2Q26 실적이 아직 발표 전이기 '
            '때문이다. <b>검색량 예측치 12개월분은 제외</b>했다.</p>'
            '<p class="cap">바이오던스와 제닉의 공급 관계는 <b>확인되지 않았다.</b> '
            '이 차트는 인과가 아니라 시기적 동행만 보여준다.</p>'
            '</div>'
            % (qlabel(*base), svg, tbl, qlabel(*last_s),
               grew.get("검색량", 0), grew.get("수출", 0)))


def build_amazon(datas):
    """아마존 순위 카드. 스냅샷이 없으면 안내만 띄운다."""
    import amazon
    df = amazon.load()
    if df.empty:
        return ('<div class="card" data-card="amazon"><h2>아마존 Best Sellers 순위</h2>'
                '<p class="cap">적립된 스냅샷이 없습니다. capture.js로 캡처한 뒤 '
                '<code>python amazon.py --ingest</code>를 실행하세요.</p></div>')

    cur = amazon.latest(df)
    snap_date = cur.date.max()
    nsnap = df.date.nunique()

    rows = []
    for _, r in cur.iterrows():
        star = " ★" if r.asin in config.WATCH_ASINS else ""
        rows.append(["#%d" % r["rank"], str(r.title)[:60] + star, r.asin,
                     num(r.rating, 1), num(r.reviews, 0)])
    tbl = charts.simple_table(["순위", "제품", "ASIN", "평점", "리뷰수"], rows)

    # 순위 추이 — 스냅샷이 2장 이상 쌓여야 의미가 있다
    chart = ""
    if nsnap >= 2:
        dates = sorted(df.date.unique())
        labels = [pd.Timestamp(d).strftime("%m/%d") for d in dates]
        series = []
        for asin in config.WATCH_ASINS:
            h = amazon.history(asin, df)
            title = df[df.asin == asin].title.iloc[-1] if (df.asin == asin).any() else asin
            series.append((str(title)[:18],
                           [None if pd.isna(v) else int(v) for v in h.values]))
        if series:
            svg, js = charts.line_chart("cam", labels, series, height=260,
                                        ylabel="순위", invert=True)
            datas["cam"] = js
            chart = ('<p class="cap">위로 갈수록 높은 순위. 순위 밖으로 나간 날은 '
                     '선이 끊긴다.</p>%s' % svg)
    else:
        chart = ('<p class="cap">순위 추이 차트는 스냅샷이 2장 이상 쌓이면 '
                 '나타납니다 (현재 %d장).</p>' % nsnap)

    return ('<div class="card" data-card="amazon"><h2>아마존 Best Sellers 순위</h2>'
            '<p class="cap">%s 카테고리(node %s) · '
            '%s 기준 · 스냅샷 %d장 · <b>수동 캡처</b></p>'
            '%s%s'
            '<p class="cap" style="margin-top:14px">'
            '★ 표시는 개별 추적 중인 제품이다. BIODANCE 바이오 콜라겐 리얼 딥 마스크는 '
            '하이드로겔 오버나이트 마스크로 제닉 주력과 성격이 같지만, '
            '<b>제닉이 이 제품을 만드는지는 확인되지 않았다</b> — 하나 리포트는 최대 '
            '고객사를 &#39;H사&#39;로만 표기한다. 확인 전까지 근거로 쓰지 말 것.</p>'
            '</div>'
            % (config.AMAZON_CATEGORY, config.AMAZON_NODE,
               pd.Timestamp(snap_date).strftime("%Y-%m-%d"), nsnap, chart, tbl))


def build():
    df = store.load(config.EXPORTS_CSV)
    if df.empty:
        raise SystemExit("exports.csv가 비어 있습니다. exports.py를 먼저 실행하세요.")

    mask = df["mask_usd"].dropna() / 1e6          # 백만달러
    total = df["total_usd"].dropna() / 1e6
    unit_price = df["mask_usd_kg"].dropna()

    asof = mask.index.max()
    cur = mask.iloc[-1]
    prev_y = mask.get(asof - pd.DateOffset(years=1))
    yoy = (cur / prev_y - 1) * 100 if prev_y else None
    mom = (cur / mask.iloc[-2] - 1) * 100 if len(mask) > 1 else None

    # ── 관세청은 매월 15일경 전월치를 반영한다. 밀리면 화면에 드러낸다 ──
    today = date.today()
    gap = (today.year - asof.year) * 12 + (today.month - asof.month)
    banner = ""
    if gap > 2 or (gap == 2 and today.day > 20):
        banner = ('<div class="warn">수출 통계가 <b>%d개월째</b> 갱신되지 않았습니다 '
                  '(최신 %s). 관세청은 통상 매월 15일경 전월치를 반영합니다.</div>'
                  % (gap, asof.strftime("%Y년 %m월")))

    # ── 주가 ─────────────────────────────────────────────────────
    px, ann_naver, qtr_naver = {}, pd.DataFrame(), pd.DataFrame()
    try:
        import price
        d = price.fetch_all()
        px, ann_naver, qtr_naver = d["price"], d["annual"], d["quarterly"]
    except Exception as e:
        print("  [경고] 주가 수집 실패: %s" % e)

    est = pd.read_csv(config.DATA / "report_estimates.csv", comment="#")
    seg = pd.read_csv(config.DATA / "segments.csv", comment="#")

    # 12MF PER — 컨센서스 EPS가 있으면 그걸로, 없으면 생략
    fwd_per, fwd_eps = None, None
    if not ann_naver.empty:
        for idx in ann_naver.index:
            p = price.parse_period(idx)
            if p and p[2] and ann_naver.at[idx, "eps"]:      # (E) 연도
                fwd_eps = ann_naver.at[idx, "eps"]
        if fwd_eps and px.get("price"):
            fwd_per = px["price"] / fwd_eps

    # ── 분기 수출 집계 ────────────────────────────────────────────
    qm = df["mask_usd"].groupby([df.index.year, df.index.quarter]).sum() / 1e6
    qt = df["total_usd"].groupby([df.index.year, df.index.quarter]).sum() / 1e6
    # 진행 중인 분기는 달 수가 모자라 YoY가 왜곡된다. 완결 분기만 쓴다.
    months_in = df.index.to_period("Q").value_counts()
    complete = [k for k in qm.index
                if months_in.get(pd.Period("%dQ%d" % (k[0], k[1]), "Q"), 0) == 3]
    qm_c = qm.loc[complete].sort_index()
    qt_c = qt.loc[complete].sort_index()
    qyoy = (qm_c / qm_c.shift(4) - 1) * 100
    qyoy_t = (qt_c / qt_c.shift(4) - 1) * 100
    last_q = qm_c.index[-1]
    partial = [k for k in qm.index if k not in complete]

    # ── 타일 ─────────────────────────────────────────────────────
    # 주가·PER은 위 카드에 이미 크게 있다. 타일은 수출·생산 지표만 담는다.
    tiles = []
    tiles.append(tile("마스크팩 수출", cur, "백만$", delta_html(yoy), "YoY", d=1))
    tiles.append(tile("HS 330790 계", total.iloc[-1], "백만$",
                      delta_html((total.iloc[-1] / total.get(
                          asof - pd.DateOffset(years=1), float("nan")) - 1) * 100),
                      "리포트 기준", d=1))
    tiles.append(tile("수출단가", unit_price.iloc[-1], "$/kg",
                      delta_html((unit_price.iloc[-1] / unit_price.iloc[-13] - 1) * 100
                                 if len(unit_price) > 13 else None), "YoY", d=2))
    tiles.append(tile("%s 수출" % qlabel(*last_q), qm_c.iloc[-1], "백만$",
                      delta_html(qyoy.iloc[-1]), "완결 분기", d=0))
    tiles.append(tile("생산 라인", "%d호기" % config.LINES[-2][1], "",
                      None, "7월 %d호기 예정" % config.LINES[-1][1]))
    tiles.append(tile("가동률", config.CAPA[-1][2], "%", None, "2025년"))

    datas = {}

    # ── 차트 1: 월별 수출 (24개월 / 전체 전환) ───────────────────
    panes, segbtns = [], []
    for i, (key, lab, cap, sub) in enumerate([
            ("r", "최근 24개월", "최근 24개월", df.tail(24)),
            ("a", "전체", "2019년~ (3307904000 세부코드 신설 이후)",
             df[df.index >= "2019-01-01"])]):
        cid = "c1" + key
        idx = sub.index
        svg, js = charts.line_chart(
            cid, [x.strftime("%y-%m") for x in idx],
            [("마스크팩", [None if pd.isna(v) else round(v / 1e6, 1)
                        for v in sub["mask_usd"]]),
             ("330790 계", [None if pd.isna(v) else round(v / 1e6, 1)
                          for v in sub["total_usd"]])],
            height=320, ylabel="백만$")
        datas[cid] = js
        tbl = charts.table_view(
            ["월", "마스크팩(백만$)", "330790계(백만$)", "중량(톤)", "$/kg"],
            [[x.strftime("%Y-%m"), num(r.mask_usd / 1e6, 1),
              num(r.total_usd / 1e6, 1), num(r.mask_kg / 1000, 0),
              num(r.mask_usd_kg, 2)] for x, r in sub.iloc[::-1].iterrows()],
            cap)
        segbtns.append('<button data-p="%s" aria-selected="%s">%s</button>'
                       % (key, "true" if i == 0 else "false", lab))
        panes.append('<div class="pane" data-p="%s"%s><p class="cap">%s</p>%s%s</div>'
                     % (key, "" if i == 0 else " hidden", cap, svg, tbl))
    c1 = '<div class="seg">%s</div>%s' % ("".join(segbtns), "".join(panes))

    # ── 차트 2: 분기 수출 YoY ─────────────────────────────────────
    n = min(12, len(qyoy.dropna()))
    ql = [qlabel(*k) for k in qyoy.dropna().index[-n:]]
    c2, _ = charts.bar_chart("c2", ql, [round(v, 1) for v in qyoy.dropna().values[-n:]],
                             height=260, ylabel="%")
    t2 = charts.table_view(
        ["분기", "마스크팩(백만$)", "YoY %", "330790계(백만$)", "YoY %"],
        [[qlabel(*k), num(qm_c[k], 0), num(qyoy.get(k), 1),
          num(qt_c[k], 0), num(qyoy_t.get(k), 1)]
         for k in list(qm_c.index)[::-1][:16]], "분기별 수출")

    # ── 차트 3: 제닉 분기 매출 (실적 + 하나 추정) ─────────────────
    hana_q = est[(est.broker == "하나") & est.period.str.contains("Q")]
    qlabels, actual, forecast, opm_a, opm_f = [], [], [], [], []
    if not qtr_naver.empty:
        for idx in qtr_naver.index:
            p = price.parse_period(idx)
            if not p:
                continue
            y, m, is_est = p
            lab = "%dQ%02d" % ((m + 2) // 3, y % 100)
            rev = qtr_naver.at[idx, "revenue"]
            opm = qtr_naver.at[idx, "op_margin"]
            qlabels.append(lab)
            actual.append(None if is_est else rev)
            forecast.append(rev if is_est else None)
            opm_a.append(None if is_est else opm)
            opm_f.append(opm if is_est else None)
    # 네이버가 안 주는 3Q26E·4Q26E는 하나 추정치로 잇는다
    for _, r in hana_q.iterrows():
        lab = r.period.replace("E", "")
        if lab not in qlabels:
            qlabels.append(lab)
            actual.append(None)
            forecast.append(r.revenue)
            opm_a.append(None)
            opm_f.append(r.op_margin)
    # 실선과 점선이 끊겨 보이지 않도록 이음매 한 점을 공유시킨다
    for i in range(1, len(forecast)):
        if forecast[i] is not None and forecast[i - 1] is None and actual[i - 1] is not None:
            forecast[i - 1] = actual[i - 1]
            opm_f[i - 1] = opm_a[i - 1]
            break

    c3, js3 = charts.line_chart(
        "c3", qlabels, [("매출(실적)", actual), ("매출(추정)", forecast)],
        height=300, ylabel="억원", dashed={1}, colors=[0, 0])
    datas["c3"] = js3
    c3b, js3b = charts.line_chart(
        "c3b", qlabels, [("OPM(실적)", opm_a), ("OPM(추정)", opm_f)],
        height=240, ylabel="%", dashed={1}, colors=[2, 2])
    datas["c3b"] = js3b
    t3 = charts.table_view(
        ["분기", "매출(억원)", "영업이익률(%)", "구분"],
        [[qlabels[i], num(actual[i] if actual[i] is not None else forecast[i], 0),
          num(opm_a[i] if opm_a[i] is not None else opm_f[i], 1),
          "실적" if actual[i] is not None else "추정"]
         for i in range(len(qlabels))], "분기 실적")

    # ── 차트 4: 연간 매출 ─────────────────────────────────────────
    yl = [str(y) for y, _, _ in ANNUAL_HIST] + ["2026E", "2027E"]
    yv = [r for _, r, _ in ANNUAL_HIST] + [1345, 1841]     # 하나 추정
    c4, _ = charts.bar_chart("c4", yl, yv, height=270, ylabel="억원")

    # ── 표: 3사 추정 비교 ────────────────────────────────────────
    def pick(broker, period, col):
        r = est[(est.broker == broker) & (est.period == period)]
        return None if r.empty else r.iloc[0][col]

    rows = []
    for col, lab in [("revenue", "매출액"), ("op", "영업이익"), ("op_margin", "영업이익률")]:
        rows.append([lab,
                     num(pick("하나", "2026E", col), 1 if "률" in lab else 0),
                     num(pick("교보", "2026E", col), 1 if "률" in lab else 0),
                     num(pick("컨센서스", "2026E", col), 1 if "률" in lab else 0),
                     num(pick("하나", "2027E", col), 1 if "률" in lab else 0),
                     num(pick("컨센서스", "2027E", col), 1 if "률" in lab else 0)])
    t_cmp = charts.simple_table(
        ["항목", "하나 26E", "교보 26E", "컨센 26E", "하나 27E", "컨센 27E"],
        rows, split_after=2)

    # ── 표: 하나 분기 전망 (채널별) ───────────────────────────────
    hcols = ["1Q25", "2Q25", "3Q25", "4Q25", "1Q26", "2Q26E", "3Q26E", "4Q26E"]
    hseg = seg[seg.source == "hana"]
    t_seg = charts.simple_table(
        ["채널"] + hcols,
        [[r.segment] + [num(r[c], 0) for c in hcols] for _, r in hseg.iterrows()],
        split_after=5)

    kcols = ["1Q25", "2Q25", "3Q25", "4Q25", "1Q26"]
    kseg = seg[seg.source == "kyobo"]
    t_prod = charts.simple_table(
        ["제품"] + kcols,
        [[r.segment] + [num(r[c], 0) for c in kcols] for _, r in kseg.iterrows()])

    # ── 표: CAPA ─────────────────────────────────────────────────
    t_capa = charts.simple_table(
        ["연도", "생산 캐파(만장)", "가동률(%)"],
        [[str(y), num(c, 0), num(u, 1)] for y, c, u in config.CAPA])

    # ── 주가 헤더 줄 ─────────────────────────────────────────────
    pxrow = ""
    if px.get("price"):
        pxrow = ('<div class="pxrow"><div><div class="hl">제닉 123330</div>'
                 '<div class="pxv">%s<span class="hu">원</span></div>'
                 '<div style="margin-top:4px">%s</div></div>'
                 '<div class="pxmeta">시가총액 %s억원<br>%s52주 %s</div></div>'
                 % (num(px["price"], 0),
                    delta_html(px.get("change_pct")),
                    num(px.get("mktcap"), 0),
                    ("12MF PER %s배<br>" % num(fwd_per, 1)) if fwd_per else "",
                    "42,600 / 15,920원"))

    # datas에 차트를 추가하므로 chartdata를 만들기 전에 불러야 한다
    amazon_card = build_amazon(datas)
    cotrend_card = build_cotrend(datas, df)
    fresh_card = build_freshness()

    html = TEMPLATE.format(
        asof=asof.strftime("%Y년 %m월"),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        banner=banner, pxrow=pxrow,
        hero=num(cur, 1), hero_delta=delta_html(yoy),
        mom=delta_html(mom), tiles="".join(tiles),
        partial=("<b>%s</b>는 아직 진행 중이라 완결 분기에서 제외했습니다. "
                 % ", ".join(qlabel(*k) for k in partial)) if partial else "",
        amazon_card=amazon_card, cotrend_card=cotrend_card,
        fresh_card=fresh_card,
        c1=c1, c2=c2, t2=t2, c3=c3, c3b=c3b, t3=t3, c4=c4,
        t_cmp=t_cmp, t_seg=t_seg, t_prod=t_prod, t_capa=t_capa,
        nrows=len(df), span="%s~%s" % (df.index.min().strftime("%Y-%m"),
                                       asof.strftime("%Y-%m")),
        chartdata=",\n".join('"%s": %s' % (k, v) for k, v in datas.items()),
    )
    OUT.write_text(html, encoding="utf-8")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>제닉 트래커 — {asof}</title>
<style>
:root {{
  color-scheme: light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --base:#c3c2b7; --ring:rgba(11,11,11,0.10);
  --up:#006300; --down:#d03b3b; --accent:#2a78d6;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --base:#383835; --ring:rgba(255,255,255,0.10);
    --up:#0ca30c; --down:#d03b3b; --accent:#3987e5;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --base:#383835; --ring:rgba(255,255,255,0.10);
  --up:#0ca30c; --down:#d03b3b; --accent:#3987e5;
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
.tu {{ font-size:12px; color:var(--muted); font-weight:400; margin-left:3px; }}
.tm {{ font-size:12px; display:flex; gap:6px; align-items:center; }}
.dl.up {{ color:var(--up); }} .dl.down {{ color:var(--down); }}
.dl.flat {{ color:var(--muted); }}
.note {{ color:var(--muted); }}
h2 {{ font-size:15px; margin:0 0 3px; }}
h3 {{ font-size:13.5px; margin:22px 0 3px; color:var(--ink); }}
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
.pxrow {{ display:flex; justify-content:space-between; align-items:flex-end;
  flex-wrap:wrap; gap:12px; }}
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
footer b {{ color:var(--ink2); }}

/* ── 카드 순서 드래그 ─────────────────────────────────────────
   손잡이(.grip)를 잡을 때만 draggable이 켜진다. 카드 전체를 draggable로
   두면 차트의 mousemove(크로스헤어·툴팁)와 텍스트 선택이 막힌다. */
#cards > [data-card] {{ position:relative; }}
.grip {{ position:absolute; top:9px; right:9px; z-index:3;
  background:none; border:0; color:var(--muted); cursor:grab;
  font-size:14px; line-height:1; padding:5px 7px; border-radius:6px;
  opacity:.30; transition:opacity .15s, background .15s; }}
#cards > [data-card]:hover .grip {{ opacity:1; }}
.grip:hover {{ background:var(--plane); color:var(--ink); }}
.grip:focus-visible {{ opacity:1; outline:2px solid var(--accent); outline-offset:1px; }}
.grip:active {{ cursor:grabbing; }}
[data-card].dragging {{ opacity:.4; }}
#cards > [data-card] {{ scroll-margin-top:12px; }}
/* 타일 묶음은 카드가 아니라 배경이 없다. 손잡이 자리만 확보한다. */
.block {{ padding-top:2px; }}
.block .grip {{ top:-4px; }}
#reset {{ font:inherit; font-size:12px; background:none; border:0; padding:0;
  color:var(--accent); cursor:pointer; text-decoration:underline; }}
</style></head><body>
<div class="wrap">
<header>
  <h1>제닉 트래커 — 마스크팩 수출</h1>
  <div class="sub">수출 기준월 {asof} · 생성 {generated}
    · <a href="../" style="color:var(--accent)">S-Oil 트래커</a>
    <span id="resetwrap" hidden>· <button id="reset" type="button">카드 순서 초기화</button></span></div>
</header>

{banner}

<div id="cards">
<div class="card" data-card="price">{pxrow}</div>

<div class="card" data-card="hero">
  <div class="hero">
    <div>
      <div class="hl">마스크팩 월 수출액 (HS 3307904000)</div>
      <div class="hv">{hero}<span class="hu">백만$</span></div>
    </div>
    <div style="padding-bottom:6px">{hero_delta} <span class="note">전년 동월</span>
      &nbsp; {mom} <span class="note">전월</span></div>
  </div>
  <div class="ctx">
    제닉은 하이드로겔 마스크팩 ODM이라 <b>회사 매출이 이 통계를 후행</b>한다.
    세 리포트 모두 이 수출 증가를 실적 전망의 1차 근거로 쓴다.
  </div>
</div>

<div class="block" data-card="tiles"><div class="tiles">{tiles}</div></div>

<div class="card" data-card="monthly">
  <h2>월별 수출액</h2>
  <div class="legend">
    <span><i style="background:#2a78d6"></i>마스크팩 (3307904000)</span>
    <span><i style="background:#1baf7a"></i>HS 330790 전체</span>
  </div>
  {c1}
</div>

<div class="card" data-card="qyoy">
  <h2>분기 수출 증가율 (YoY)</h2>
  <p class="cap">마스크팩 단품 기준. {partial}완결된 분기만 표시한다.</p>
  {c2}
  {t2}
</div>

<div class="card" data-card="qrev">
  <h2>제닉 분기 매출 · 수익성</h2>
  <p class="cap">실선이 확정 실적, 점선이 추정치(2Q26E는 컨센서스,
    3Q·4Q26E는 하나증권 2026-06-05).</p>
  {c3}
  <h3>영업이익률</h3>
  <p class="cap">1Q26 OPM 11.6%는 신제품 초기 수율 저하와 가동률 100% 초과에 따른
    특근 노무비 탓이다. 두 리포트 모두 2분기부터 정상화를 전망한다.</p>
  {c3b}
  {t3}
</div>

<div class="card" data-card="annual">
  <h2>연간 매출 추이</h2>
  <p class="cap">단위 억원. 2026E·2027E는 하나증권 추정치.</p>
  {c4}
</div>

<div class="card" data-card="estimates">
  <h2>증권사 추정치 비교</h2>
  <p class="cap">단위 억원 / %. 회색 세로선 오른쪽이 2027년.
    교보는 26F만 제시했고 유안타는 추정치를 내지 않았다.</p>
  {t_cmp}
  <h3>채널별 분기 매출 — 하나증권</h3>
  <p class="cap">단위 억원. 회색 세로선 오른쪽이 추정 구간이다.</p>
  {t_seg}
  <h3>제품별 분기 매출 — 교보증권</h3>
  <p class="cap">단위 억원. 하이드로겔(얼굴) 한 품목이 성장 전부를 설명한다.</p>
  {t_prod}
</div>

{cotrend_card}

{amazon_card}

<div class="card" data-card="capa">
  <h2>생산 캐파 · 가동률</h2>
  <p class="cap">유안타증권 2026-05-14. 가동률이 이미 높아 증설이 곧 매출이다.</p>
  {t_capa}
  <p class="cap" style="margin-top:12px">
    교보 탐방노트(2026-06-24): 1Q26 8호기 → 4월 10호기 → 5월 11호기로
    1분기 대비 캐파 <b>+38%</b>. 7월 1호기 추가 증설 예정, 3호기 추가 계획.
    증설에도 가동률은 여전히 100%를 넘을 것으로 파악. 호기당 월 100~120만장.
  </p>
</div>

{fresh_card}
</div>

<footer>
데이터: 관세청 품목별 수출입실적 API (월별 {nrows}행, {span}) · 주가·컨센서스 네이버 금융<br>
<b>수치 대조 주의.</b> 유안타 리포트의 마스크팩 수출액(22년 6.12 → 25년 8.73억달러)은
HS <b>330790 전체</b> 합계와 정확히 일치한다. 순수 마스크팩 세부코드(3307904000)는
같은 기간 4.53 → 6.08억달러로 수준이 다르다. 이 대시보드는 헤드라인에 세부코드를,
비교용으로 전체 합계를 함께 싣는다.<br>
하나증권이 인용한 "1분기 수출 YoY 59%, 2분기 70% 상회"는 두 계열 어느 쪽과도
맞지 않는다(각각 +29% / +37%). 다른 기준의 통계로 보이며 확인되지 않았다.<br>
3307904000 세부코드는 2019년 신설이라 그 이전은 마스크팩 단품 집계가 없다.<br>
투자 판단의 근거로 쓰기 전에 원자료를 확인할 것.
</footer>
</div>

<div class="tip" id="tip"></div>
<script>
/* ── 카드 순서 드래그 ──────────────────────────────────────────
   페이지는 매일 CI가 새로 만든다. 그래서 순서는 서버가 아니라
   localStorage에 둔다. data-card 키는 내용이 바뀌어도 그대로다.       */
(() => {{
  const wrap = document.getElementById('cards');
  if (!wrap) return;
  const KEY = 'jenik.cardOrder.v1';
  const kids = () => [...wrap.children].filter(el => el.dataset.card);

  const save = () => {{
    localStorage.setItem(KEY, JSON.stringify(kids().map(el => el.dataset.card)));
    document.getElementById('resetwrap').hidden = false;
  }};

  // 저장된 순서를 적용한다. 나중에 카드가 추가되면 저장된 목록에 없으므로
  // 맨 뒤에 붙는다 — 사라지지 않는다.
  try {{
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]');
    if (saved.length) {{
      const map = new Map(kids().map(el => [el.dataset.card, el]));
      const order = saved.filter(k => map.has(k));
      const rest = [...map.keys()].filter(k => !order.includes(k));
      [...order, ...rest].forEach(k => wrap.appendChild(map.get(k)));
      document.getElementById('resetwrap').hidden = false;
    }}
  }} catch (e) {{ /* 저장값이 깨졌으면 기본 순서로 둔다 */ }}

  let dragEl = null;

  kids().forEach(el => {{
    const grip = document.createElement('button');
    grip.type = 'button';
    grip.className = 'grip';
    grip.textContent = '⠿';
    grip.title = '드래그해서 순서 변경 (↑↓ 키로도 이동)';
    grip.setAttribute('aria-label', '카드 순서 변경');

    // 손잡이를 누른 동안만 드래그를 허용한다
    const arm = () => {{ el.draggable = true; }};
    grip.addEventListener('mousedown', arm);
    grip.addEventListener('touchstart', arm, {{ passive: true }});

    grip.addEventListener('keydown', ev => {{
      const prev = el.previousElementSibling, next = el.nextElementSibling;
      if (ev.key === 'ArrowUp' && prev) {{ wrap.insertBefore(el, prev); }}
      else if (ev.key === 'ArrowDown' && next) {{ wrap.insertBefore(next, el); }}
      else return;
      ev.preventDefault();
      save();
      el.scrollIntoView({{ block: 'nearest' }});
      grip.focus();
    }});

    el.prepend(grip);

    el.addEventListener('dragstart', ev => {{
      dragEl = el;
      el.classList.add('dragging');
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('text/plain', el.dataset.card);
    }});
    el.addEventListener('dragend', () => {{
      el.draggable = false;
      el.classList.remove('dragging');
      dragEl = null;
      save();
    }});
  }});

  wrap.addEventListener('dragover', ev => {{
    if (!dragEl) return;
    ev.preventDefault();
    const t = ev.target.closest ? ev.target.closest('[data-card]') : null;
    if (!t || t === dragEl || t.parentElement !== wrap) return;
    const r = t.getBoundingClientRect();
    wrap.insertBefore(dragEl, (ev.clientY < r.top + r.height / 2) ? t : t.nextSibling);
  }});

  document.getElementById('reset').addEventListener('click', () => {{
    localStorage.removeItem(KEY);
    location.reload();
  }});
}})();

const DATA = {{ {chartdata} }};

document.querySelectorAll('.seg button').forEach(b => {{
  b.addEventListener('click', () => {{
    const seg = b.closest('.seg'), card = b.closest('.card'), p = b.dataset.p;
    seg.querySelectorAll('button').forEach(x =>
      x.setAttribute('aria-selected', String(x === b)));
    card.querySelectorAll('.pane').forEach(x => {{ x.hidden = x.dataset.p !== p; }});
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
           '"></i>' + s.name + '</span><span>' + v.toFixed(1) + '</span></div>';
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
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    p = build()
    print("생성: %s" % p)
    if "--open" in sys.argv:
        webbrowser.open(p.as_uri())
