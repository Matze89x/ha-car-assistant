"""Tiny dependency-free SVG helpers (no JS, no external requests – works inside the Ingress sandbox)."""

from __future__ import annotations

from html import escape


def line_svg(points: list[tuple[str, float]], width: int = 640, height: int = 180, unit: str = "", trend: int = 0) -> str:
    """Line chart of (label, value). Returns an empty string for fewer than two points."""
    if len(points) < 2:
        return ""
    pad_l, pad_r, pad_t, pad_b = 40, 12, 12, 22
    values = [v for _, v in points]
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    span = hi - lo
    lo, hi = lo - span * 0.1, hi + span * 0.1
    inner_w, inner_h = width - pad_l - pad_r, height - pad_t - pad_b

    def x(i: int) -> float:
        return pad_l + inner_w * i / (len(points) - 1)

    def y(v: float) -> float:
        return pad_t + inner_h * (1 - (v - lo) / (hi - lo))

    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3"><title>{escape(label)}: {v:.1f}{escape(unit)}</title></circle>'
        for i, (label, v) in enumerate(points)
    )
    grid = ""
    for frac in (0, 0.5, 1):
        gv = lo + (hi - lo) * frac
        gy = y(gv)
        grid += (
            f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>'
            f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" text-anchor="end">{gv:.1f}</text>'
        )
    first, last = escape(points[0][0]), escape(points[-1][0])
    labels = (
        f'<text x="{pad_l}" y="{height - 4}" text-anchor="start">{first}</text>'
        f'<text x="{width - pad_r}" y="{height - 4}" text-anchor="end">{last}</text>'
    )
    smooth = ""
    if trend > 1 and len(points) >= trend:  # moving average over `trend` points
        avg = [sum(values[max(0, i - trend + 1) : i + 1]) / len(values[max(0, i - trend + 1) : i + 1]) for i in range(len(values))]
        smooth = f'<path d="{" ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(avg))}" class="trend"/>'
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">'
        f'{grid}<path d="{path}" class="line"/>{smooth}{dots}{labels}</svg>'
    )


MAX_ROUTE_POINTS = 1500


def route_svg(points: list[tuple[float, float]], width: int = 480, height: int = 320) -> str:
    """Draw a GPS track as a polyline (equirectangular, no map tiles)."""
    import math

    if len(points) < 2:
        return ""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lon, max_lat = min(lons), max(lats)
    mid_lat = math.radians((min(lats) + max(lats)) / 2)
    lon_scale = max(math.cos(mid_lat), 0.01)
    w_deg = max((max(lons) - min(lons)) * lon_scale, 1e-6)
    h_deg = max(max(lats) - min(lats), 1e-6)
    pad = 16
    scale = min((width - 2 * pad) / w_deg, (height - 2 * pad) / h_deg)
    off_x = (width - w_deg * scale) / 2
    off_y = (height - h_deg * scale) / 2

    def xy(lat: float, lon: float) -> tuple[float, float]:
        return off_x + (lon - min_lon) * lon_scale * scale, off_y + (max_lat - lat) * scale

    step = max(1, len(points) // MAX_ROUTE_POINTS)  # a screen cannot show more; the file keeps every point
    shown = points[::step] if points[::step][-1] == points[-1] else [*points[::step], points[-1]]
    coords = [xy(lat, lon) for lat, lon in shown]
    d = " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(coords))
    (sx, sy), (ex, ey) = coords[0], coords[-1]
    return (
        f'<svg class="route" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{d}" class="line"/><circle cx="{sx:.1f}" cy="{sy:.1f}" r="5" class="start"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" class="end"/></svg>'
    )


def bars_svg(
    rows: list[tuple[str, list[float]]], width: int = 640, height: int = 200, unit: str = "", names: list[str] | None = None
) -> str:
    """Stacked bar chart: one bar per (label, [value of series 1, 2, ...]); the series are classed b1, b2 ... (colours in the stylesheet).
    Empty string when nothing is above zero."""
    totals = [sum(v for v in vals if v) for _l, vals in rows]
    top = max(totals, default=0)
    if top <= 0:
        return ""
    pad_l, pad_r, pad_t, pad_b = 44, 8, 10, 22
    inner_w, inner_h = width - pad_l - pad_r, height - pad_t - pad_b
    slot = inner_w / len(rows)
    bar = max(1.5, min(34.0, slot * 0.72))
    grid = ""
    for frac in (0, 0.5, 1):
        gy = pad_t + inner_h * (1 - frac)
        grid += (
            f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>'
            f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" text-anchor="end">{top * frac:.0f}</text>'
        )
    body = ""
    for i, (label, vals) in enumerate(rows):
        x = pad_l + slot * i + (slot - bar) / 2
        y = pad_t + inner_h
        for n, v in enumerate(vals):
            if not v or v <= 0:
                continue
            h = inner_h * v / top
            y -= h
            tip = f"{label}: {(names[n] + ' ') if names else ''}{v:.0f}{unit}"
            body += f'<rect class="b{n + 1}" x="{x:.1f}" y="{y:.1f}" width="{bar:.1f}" height="{h:.1f}"><title>{escape(tip)}</title></rect>'
    first, last = escape(rows[0][0]), escape(rows[-1][0])
    labels = (
        f'<text x="{pad_l}" y="{height - 4}" text-anchor="start">{first}</text>'
        f'<text x="{width - pad_r}" y="{height - 4}" text-anchor="end">{last}</text>'
    )
    return (
        f'<svg class="chart bars" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">{grid}{body}{labels}</svg>'
    )


def spark_svg(values: list[float], width: int = 160, height: int = 44) -> str:
    """A small area line without axes for a widget (the last values, oldest first). Empty string with fewer than two values."""
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 5.0
    step = (width - 2 * pad) / (len(vals) - 1)
    pts = [(pad + i * step, pad + (height - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = f"{line} L{pts[-1][0]:.1f},{height} L{pts[0][0]:.1f},{height} Z"
    x, y = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" xmlns="http://www.w3.org/2000/svg">'
        f'<path class="sp-area" d="{area}"/><path class="sp-line" d="{line}"/><circle class="sp-dot" cx="{x:.1f}" cy="{y:.1f}" r="3.2"/></svg>'
    )


def mini_bars_svg(rows: list[tuple[str, float]], width: int = 160, height: int = 44) -> str:
    """Tiny bar chart (one bar per label, e.g. the last seven days); the highest bar is classed ``top``. Empty when everything is zero."""
    top = max((v for _l, v in rows), default=0)
    if top <= 0:
        return ""
    slot = width / len(rows)
    bar = slot * 0.62
    body = ""
    for i, (label, v) in enumerate(rows):
        h = max(2.0, (height - 4) * v / top) if v > 0 else 2.0
        cls = "top" if v == top else ("none" if v <= 0 else "")
        body += (
            f'<rect class="mb {cls}" x="{slot * i + (slot - bar) / 2:.1f}" y="{height - h:.1f}" width="{bar:.1f}" height="{h:.1f}" rx="2">'
            f"<title>{escape(label)}: {v:.0f}</title></rect>"
        )
    return f'<svg class="minibars" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
