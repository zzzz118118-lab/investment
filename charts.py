# -*- coding: utf-8 -*-
"""의존성 없는 인라인 SVG 차트 생성.

색은 dataviz 스킬 레퍼런스 팔레트의 카테고리 슬롯을 순서대로 쓴다.
슬롯 순서 자체가 CVD 안전 장치이므로 임의로 섞지 않는다.
"""
import json
import math

# 카테고리 슬롯 1~5 (light, dark)
SERIES = [
    ("#2a78d6", "#3987e5"),   # 1 blue
    ("#1baf7a", "#199e70"),   # 2 aqua
    ("#eda100", "#c98500"),   # 3 yellow
    ("#008300", "#008300"),   # 4 green
    ("#4a3aa7", "#9085e9"),   # 5 violet
]


def _nice_ticks(lo, hi, n=5):
    """읽기 좋은 눈금 값을 만든다."""
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw / mag <= m:
            step = m * mag
            break
    else:
        step = 10 * mag
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.5:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _spread(items, min_gap, lo, hi):
    """라벨 y좌표를 최소 간격 이상으로 벌린다(겹침 방지).

    items: [(y, ...), ...]  반환: 같은 순서의 조정된 y 리스트.
    """
    order = sorted(range(len(items)), key=lambda i: items[i][0])
    ys = [items[i][0] for i in order]
    # 위에서 아래로 밀어내기
    for k in range(1, len(ys)):
        if ys[k] - ys[k - 1] < min_gap:
            ys[k] = ys[k - 1] + min_gap
    # 아래 경계를 넘으면 위로 되밀기
    if ys and ys[-1] > hi:
        ys[-1] = hi
        for k in range(len(ys) - 2, -1, -1):
            if ys[k + 1] - ys[k] < min_gap:
                ys[k] = ys[k + 1] - min_gap
    if ys and ys[0] < lo:
        ys[0] = lo
        for k in range(1, len(ys)):
            if ys[k] - ys[k - 1] < min_gap:
                ys[k] = ys[k - 1] + min_gap
    out = [0.0] * len(items)
    for pos, i in enumerate(order):
        out[i] = ys[pos]
    return out


def line_chart(chart_id, labels, series, height=300, ylabel="$/bbl",
               direct_labels=True, width=980, dashed=(), colors=None):
    """series: [(이름, [값...]), ...]  값에 None 허용.

    dashed: 점선으로 그릴 계열 인덱스 집합 (확정치 vs 잠정치 구분용).
    colors: 슬롯 인덱스를 직접 지정하고 싶을 때. 없으면 순서대로 쓴다.

    반환: (svg_html, data_json) — data_json은 크로스헤어 JS가 쓴 데이터.
    """
    pad_l, pad_r, pad_t, pad_b = 52, 100 if direct_labels else 20, 28, 34
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b

    vals = [v for _, ys in series for v in ys if v is not None]
    if not vals:
        return "<p>데이터 없음</p>", "{}"
    lo, hi = min(vals), max(vals)
    ticks = _nice_ticks(lo, hi)
    ylo, yhi = ticks[0], ticks[-1]

    n = len(labels)

    def X(i):
        return pad_l + (iw * i / max(n - 1, 1))

    def Y(v):
        return pad_t + ih - ih * (v - ylo) / (yhi - ylo)

    out = ['<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" '
           'role="img" id="%s">' % (width, height, chart_id)]

    # 그리드 + y축 눈금
    for t in ticks:
        y = Y(t)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>'
                   % (pad_l, y, pad_l + iw, y))
        out.append('<text x="%d" y="%.1f" class="axis ar">%g</text>'
                   % (pad_l - 8, y + 4, t))
    out.append('<text x="%d" y="%d" class="axis">%s</text>' % (pad_l - 44, 12, _esc(ylabel)))

    # x축 눈금 (최대 8개)
    step = max(1, n // 8)
    for i in range(0, n, step):
        out.append('<text x="%.1f" y="%d" class="axis am">%s</text>'
                   % (X(i), pad_t + ih + 20, _esc(labels[i])))
    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="baseline"/>'
               % (pad_l, pad_t + ih, pad_l + iw, pad_t + ih))

    # 라인
    ends = []   # 직접 라벨 후보: (y, x, name, value, color)
    for si, (name, ys) in enumerate(series):
        slot = colors[si] if colors else si
        c_l, c_d = SERIES[slot % len(SERIES)]
        d, pen = [], False
        for i, v in enumerate(ys):
            if v is None:
                pen = False
                continue
            d.append(("M" if not pen else "L") + "%.1f %.1f" % (X(i), Y(v)))
            pen = True
        dash = ' stroke-dasharray="5 4"' if si in dashed else ""
        out.append('<path d="%s" fill="none" class="ln" style="--c:%s;--cd:%s" '
                   'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"%s/>'
                   % (" ".join(d), c_l, c_d, dash))
        if direct_labels:
            last = next((i for i in range(n - 1, -1, -1) if ys[i] is not None), None)
            if last is not None:
                out.append('<circle cx="%.1f" cy="%.1f" r="3.5" class="pt" '
                           'style="--c:%s;--cd:%s"/>' % (X(last), Y(ys[last]), c_l, c_d))
                ends.append([Y(ys[last]), X(last), name, ys[last], c_l, c_d])

    # 라벨이 서로 겹치지 않게 y를 벌린다. 점과 라벨이 떨어지면 연결선을 긋는다.
    if ends:
        adj = _spread(ends, 15, pad_t + 6, pad_t + ih)
        for (y0, x0, name, val, c_l, c_d), y1 in zip(ends, adj):
            if abs(y1 - y0) > 2:
                out.append('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f" fill="none" '
                           'class="lead"/>' % (x0 + 4, y0, x0 + 10, y1, x0 + 14, y1))
            out.append('<text x="%.1f" y="%.1f" class="dlab">%s %.1f</text>'
                       % (x0 + 17, y1 + 4, _esc(name), val))

    out.append('<line class="cross" id="%s-cross" x1="0" y1="%d" x2="0" y2="%d" '
               'style="display:none"/>' % (chart_id, pad_t, pad_t + ih))
    out.append("</svg>")

    meta = {"pad_l": pad_l, "iw": iw, "w": width, "labels": labels,
            "series": [{"name": nm, "vals": ys,
                        "c": SERIES[(colors[i] if colors else i) % len(SERIES)][0],
                        "cd": SERIES[(colors[i] if colors else i) % len(SERIES)][1]}
                       for i, (nm, ys) in enumerate(series)]}
    return "\n".join(out), json.dumps(meta, ensure_ascii=False)


def bar_chart(chart_id, labels, values, height=280, ylabel="$/bbl",
              highlight_last=True, width=980):
    """단일 계열 막대. 마지막 막대를 강조할 수 있다."""
    pad_l, pad_r, pad_t, pad_b = 52, 16, 28, 40
    iw = width - pad_l - pad_r
    ih = height - pad_t - pad_b
    vals = [v for v in values if v is not None]
    if not vals:
        return "<p>데이터 없음</p>", "{}"
    ticks = _nice_ticks(min(0, min(vals)), max(vals))
    ylo, yhi = ticks[0], ticks[-1]
    n = len(values)
    slot = iw / n
    bw = max(4, slot - 6)   # 막대 사이 2px 이상 간격

    def Y(v):
        return pad_t + ih - ih * (v - ylo) / (yhi - ylo)

    out = ['<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" '
           'role="img" id="%s">' % (width, height, chart_id)]
    for t in ticks:
        y = Y(t)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>'
                   % (pad_l, y, pad_l + iw, y))
        out.append('<text x="%d" y="%.1f" class="axis ar">%g</text>' % (pad_l - 8, y + 4, t))
    out.append('<text x="%d" y="%d" class="axis">%s</text>' % (pad_l - 44, 12, _esc(ylabel)))

    base = Y(ylo)
    for i, v in enumerate(values):
        if v is None:
            continue
        x = pad_l + slot * i + (slot - bw) / 2
        y = Y(v)
        cls = "bar hi" if (highlight_last and i == n - 1) else "bar"
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" '
                   'class="%s"><title>%s: %.1f</title></rect>'
                   % (x, y, bw, max(base - y, 1), cls, _esc(labels[i]), v))
        out.append('<text x="%.1f" y="%d" class="axis am">%s</text>'
                   % (x + bw / 2, pad_t + ih + 18, _esc(labels[i])))
    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="baseline"/>'
               % (pad_l, base, pad_l + iw, base))
    out.append("</svg>")
    return "\n".join(out), "{}"


def simple_table(headers, rows, split_after=None):
    """항상 보이는 표. 각 칸은 이미 포맷된 문자열.

    split_after: 이 인덱스의 열 뒤에 실적/추정 경계선을 긋는다.
    음수 값은 자동으로 빨갛게 표시한다.
    """
    def th(i, x):
        c = " class='sep'" if split_after is not None and i == split_after + 1 else ""
        return "<th%s>%s</th>" % (c, _esc(x))

    head = "".join(th(i, x) for i, x in enumerate(headers))

    body = []
    for r in rows:
        cells = []
        for j, c in enumerate(r):
            cls = []
            s = str(c)
            if j > 0 and s.lstrip().startswith("-") and any(ch.isdigit() for ch in s):
                cls.append("neg")
            if split_after is not None and j == split_after + 1:
                cls.append("sep")
            attr = (' class="%s"' % " ".join(cls)) if cls else ""
            cells.append("<td%s>%s</td>" % (attr, _esc(c)))
        body.append("<tr>" + "".join(cells) + "</tr>")

    return ('<div class="scroll"><table class="fin"><thead><tr>%s</tr></thead>'
            "<tbody>%s</tbody></table></div>" % (head, "".join(body)))


def table_view(headers, rows, caption=""):
    """차트의 접근성 대체 표 (relief rule 대응)."""
    h = "".join("<th>%s</th>" % _esc(x) for x in headers)
    body = []
    for r in rows:
        body.append("<tr>" + "".join("<td>%s</td>" % _esc(c) for c in r) + "</tr>")
    return ('<details class="tbl"><summary>%s 표로 보기</summary>'
            '<div class="scroll"><table><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table></div></details>'
            % (_esc(caption), h, "".join(body)))
