"""Render slides.json into 1080x1350 carousel frames (HTML + PNG) in The Scout look.

Usage: python3 render.py SLIDES.json AUDIT.json OUT_DIR [--captures captures.json] [--data name=path ...]
The copy check runs first. If it fails, nothing is rendered. After rendering, each frame is checked for overflow.
"""
import argparse, hashlib, html, json, math, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, copycheck  # noqa: E402

THEME = {
    "deep": "#13233E", "navy": "#253B61", "ice": "#EEF8FA", "mint": "#DCF1EC", "cyan": "#76CCE0",
    "amber": "#F2B035", "amber_ink": "#8A5200", "muted_dark": "#A3B6CE", "muted_light": "#4A5F80",
    "panel_dark": "#1C3152", "display": "'Young Serif', Georgia, serif", "body": "'Bitter', Georgia, serif",
    "mono": "'Azeret Mono', ui-monospace, monospace",
    "fonts_url": "https://fonts.googleapis.com/css2?family=Azeret+Mono:wght@400;500;600&family=Bitter:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Young+Serif&display=swap",
    "paper": "#FFFFFF", "panel_light": "#F8FCFD", "callout_text": "#DCE6F0",
    "card_shadow": "0 14px 30px rgba(4,10,22,0.28)", "cover_shadow": "0 30px 60px rgba(4,10,22,0.55)",
}
# Poster theme: teal ground, kraft cream, vermilion, black ink, risograph grain, offset-ink display type, stamps.
KAIJU = dict(THEME, **{
    "deep": "#1F4D53", "navy": "#16110E", "ice": "#E9C48E", "mint": "#D7AE76", "cyan": "#E9C48E",
    "amber": "#E4492B", "amber_ink": "#9E2A14", "muted_dark": "#D3B78F", "muted_light": "#4A3B2C",
    "panel_dark": "#183F44", "paper": "#F0D5A8", "panel_light": "#F0D5A8", "callout_text": "#E9C48E",
    "card_shadow": "7px 7px 0 #16110E", "cover_shadow": "10px 10px 0 #16110E",
    "display": "'Dela Gothic One', 'Arial Black', sans-serif", "body": "'Zen Kaku Gothic New', 'Helvetica Neue', sans-serif",
    "mono": "'Space Mono', ui-monospace, monospace", "vertical": "'Dela Gothic One', 'Arial Black', sans-serif",
    "body": "'Archivo', 'Helvetica Neue', sans-serif",
    "fonts_url": "https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Dela+Gothic+One&family=Space+Mono:wght@400;700&display=swap",
    "texture": True, "extrude": True, "seals": True, "stamps": True, "display_scale": 1.0, "single_tone": True, "handmade": True,
    "image_filter": "sepia(0.16) saturate(0.92) contrast(1.04)", "body_weight": 500,
})
THEMES = {"scout": THEME, "kaiju": KAIJU}
SEALS = {"backtest": "BACKTEST", "calls": "CALLS", "registry": "EARLY MOVERS", "signal_board": "SIGNALS", "cover": "FIELD REPORT", "scorecard": "VERDICT", "day_bars": "JOURNAL", "source_bars": "SOURCES", "radar": "EVIDENCE",
         "image_grid": "PANEL", "metric_chart": "SIGNALS", "groups": "SIMPLIFY", "tests": "TESTS", "quote": "GIVEAWAY"}
# Hand-printed look: worn type, wobbly ink lines, uneven coverage. Filters live once per page.
HANDMADE_DEFS = (
    '<svg aria-hidden="true" width="0" height="0" style="position:absolute"><defs>'
    '<filter id="distress" x="-4%" y="-8%" width="108%" height="116%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="4" result="warp"/>'
    '<feDisplacementMap in="SourceGraphic" in2="warp" scale="2.5" xChannelSelector="R" yChannelSelector="G" result="wob"/>'
    '<feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="2" seed="11" result="speck"/>'
    '<feColorMatrix in="speck" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -4 0 0 0 3.35" result="mask"/>'
    '<feComposite in="wob" in2="mask" operator="in"/></filter>'
    '<filter id="rough" x="-3%" y="-3%" width="106%" height="106%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="8" result="w"/>'
    '<feDisplacementMap in="SourceGraphic" in2="w" scale="3.2" xChannelSelector="R" yChannelSelector="G"/></filter>'
    '</defs></svg>')
ICONS = {  # simple stroked line art, roughened by the filter
    "eye": '<path d="M4 24 Q24 6 44 24 Q24 42 4 24 Z" fill="none" stroke-width="3"/><circle cx="24" cy="24" r="7" fill="none" stroke-width="3"/><circle cx="24" cy="24" r="2.5"/>',
    "radar": '<circle cx="24" cy="24" r="19" fill="none" stroke-width="3"/><circle cx="24" cy="24" r="11" fill="none" stroke-width="2.5"/><path d="M24 24 L38 10" stroke-width="3.5" stroke-linecap="round"/><circle cx="33" cy="30" r="2.8"/>',
    "cross": '<path d="M9 9 L39 39 M39 9 L9 39" stroke-width="5" stroke-linecap="round"/><circle cx="8" cy="8" r="4"/><circle cx="40" cy="8" r="4"/><circle cx="8" cy="40" r="4"/><circle cx="40" cy="40" r="4"/>',
    "lens": '<circle cx="20" cy="20" r="13" fill="none" stroke-width="3.5"/><path d="M30 30 L42 42" stroke-width="6" stroke-linecap="round"/>',
    "check": '<path d="M8 25 L19 36 L40 12" fill="none" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>',
}


def icon(name, color, size=44):
    body = ICONS.get(name)
    if not body:
        return ""
    return (f'<svg aria-hidden="true" width="{size}" height="{size}" viewBox="0 0 48 48" fill="{color}" stroke="{color}" '
            f'style="filter:url(#rough);display:block">{body}</svg>')
GRAIN = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
         "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='{f}' numOctaves='2' seed='{seed}' stitchTiles='stitch'/>"
         "<feColorMatrix values='0 0 0 0 {r} 0 0 0 0 {g} 0 0 0 0 {b} 0 0 0 {a} -0.55'/></filter>"
         "<rect width='240' height='240' filter='url(%23n)'/></svg>")


def rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def display_style(t, dark, size):
    """Offset-ink poster type for the kaiju theme; plain display type otherwise."""
    if not t.get("extrude"):
        return f"font-size:{size}px;"
    size = round(size * t.get("display_scale", 1))
    depth = max(4, round(size / 10))
    if dark:
        ink = ",".join(f"{i}px {i}px 0 {t['navy']}" for i in range(1, depth + 1))
        edge = ",".join(f"{depth + a}px {depth + b}px 0 {t['amber']}" for a, b in ((2, 2), (3, 1), (1, 3), (3, 3), (2, 4), (4, 2)))
        return f"font-size:{size}px;color:{t['ice']};text-shadow:{ink},{edge};" + ("filter:url(#distress);" if t.get("handmade") else "")
    return (f"font-size:{size}px;color:{t['navy']};text-shadow:{round(depth * 0.7)}px {round(depth * 0.7)}px 0 {t['amber']};"
            + ("filter:url(#distress);" if t.get("handmade") else ""))


def texture(t):
    if not t.get("texture"):
        return ""
    dark = GRAIN.format(f="0.62", seed="3", r="0.05", g="0.04", b="0.03", a="1.8")
    light = GRAIN.format(f="1.1", seed="9", r="0.95", g="0.86", b="0.68", a="1.6")
    mottle = GRAIN.format(f="0.006", seed="21", r="0.04", g="0.05", b="0.05", a="1.3").replace("width='240' height='240'", "width='1080' height='1350'").replace("<rect width='240' height='240'", "<rect width='1080' height='1350'")
    z = "position:absolute;inset:0;pointer-events:none;z-index:0;"  # under the content: texture never sits on words
    return (f'<div class="tx" aria-hidden="true" style="{z}background-image:url(&quot;{dark}&quot;);opacity:0.7;mix-blend-mode:multiply"></div>'
            f'<div class="tx" aria-hidden="true" style="{z}background-image:url(&quot;{light}&quot;);opacity:0.35;mix-blend-mode:screen"></div>'
            f'<div class="tx" aria-hidden="true" style="{z}background-image:url(&quot;{mottle}&quot;);background-size:1080px 1350px;opacity:0.3;mix-blend-mode:multiply"></div>'
            f'<div class="tx" aria-hidden="true" style="{z}background:radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(0,0,0,0.3) 100%)"></div>')
PLATFORM_LABELS = {"web": "Publications", "x": "X", "tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
                   "reddit": "Reddit", "discord": "Discord", "streaming_charts": "Streaming charts",
                   "search_interest": "Search interest"}
KINDS = [("reporting", "REPORTING"), ("primary_evidence", "PRIMARY"), ("self_report", "SELF-REPORT"),
         ("commentary", "COMMENTARY"), ("platform_aggregate", "PLATFORM DATA")]


class Ctx:
    def __init__(self, theme, data, captures, deck):
        self.t, self.data, self.caps, self.deck = theme, data, captures, deck

    def txt(self, s):
        out, _ = copycheck.resolve(s or "", self.data)
        out = html.escape(out).replace("\n", "<br>")
        # links stay clickable in the text PDF
        return re.sub(r"(https?://[^\s<]+[^\s<.,;:)])", r'<a href="\1" style="color:inherit;text-decoration:underline">\1</a>', out)

    def fig(self, key):
        return copycheck.lookup(self.data, key)


def tone_colors(t, dark):
    if dark:
        return dict(bg=t["deep"], fg=t["ice"], muted=t["muted_dark"], rule=rgba(t["ice"], 0.22 if t.get("texture") else 0.18),
                    accent=t["amber"], good=t["cyan"], panel=t["panel_dark"], dark=True)
    return dict(bg=t["ice"], fg=t["navy"], muted=t["muted_light"], rule=rgba(t["navy"], 0.22 if t.get("texture") else 0.18),
                accent=t["amber_ink"], good=t["navy"], panel=t["panel_light"], dark=False)


def image_box(c, ctx, ref, width, height, radius=8, shadow=True):
    cap = ctx.caps.get(ref if isinstance(ref, str) else ref.get("id"))
    frame = ref if isinstance(ref, dict) else {}
    sh = f"box-shadow:{ctx.t['card_shadow']};" if shadow else ""
    if not cap or cap.get("outcome") != "ok" or not cap.get("file"):
        why = cap.get("outcome", "not in manifest") if cap else "not in manifest"
        credit = html.escape((cap or {}).get("credit") or str(ref))
        return (f'<div style="width:{width}px;height:{height}px;box-sizing:border-box;border:2px dashed {c["muted"]};'
                f'border-radius:{radius}px;display:flex;align-items:center;justify-content:center;text-align:center;padding:16px;'
                f'font-family:{ctx.t["mono"]};font-size:15px;letter-spacing:0.08em;color:{c["muted"]}">IMAGE NOT CAPTURED<br>'
                f'{credit} · {html.escape(why)}</div>')
    src = "file://" + os.path.abspath(cap["file"])
    alt = html.escape(cap.get("credit") or "")
    art = cap.get("kind") == "illustration"
    flt = f"filter:{ctx.t['image_filter']};" if ctx.t.get("image_filter") and not art else ""
    if "zoom" in frame:
        return (f'<div style="position:relative;width:{width}px;height:{height}px;overflow:hidden;border-radius:{radius}px;{sh}background:{ctx.t["paper"]}">'
                f'<img src="{src}" alt="{alt}" style="position:absolute;display:block;max-width:none;{flt}left:{frame.get("x", 0)}px;'
                f'top:{frame.get("y", 0)}px;width:{frame["zoom"]}px">'
                + (f'<div aria-hidden="true" style="position:absolute;inset:0;background-image:radial-gradient({rgba(ctx.t["navy"], 0.55)} 0.9px, transparent 1.5px);background-size:4px 4px;mix-blend-mode:multiply;opacity:0"></div>' if ctx.t.get("handmade") else "")
                + '</div>')
    pos = frame.get("position", "50% 0%")
    if ctx.t.get("handmade") and not art:
        dots = f"radial-gradient({rgba(ctx.t['navy'], 0.55)} 0.9px, transparent 1.5px)"
        return (f'<div style="position:relative;width:{width}px;height:{height}px;border-radius:{radius}px;overflow:hidden;{sh}">'
                f'<img src="{src}" alt="{alt}" style="display:block;{flt}width:{width}px;height:{height}px;object-fit:cover;object-position:{pos}">'
                f'<div aria-hidden="true" style="position:absolute;inset:0;background-image:{dots};background-size:4px 4px;mix-blend-mode:multiply;opacity:0"></div></div>')
    return (f'<img src="{src}" alt="{alt}" style="display:block;{flt}width:{width}px;height:{height}px;object-fit:cover;'
            f'object-position:{pos};border-radius:{radius}px;{sh}">')


def credit_of(ctx, ref):
    cap = ctx.caps.get(ref if isinstance(ref, str) else ref.get("id")) or {}
    return html.escape(cap.get("credit") or "")


# ---------- slide bodies ----------

def k_cover(s, c, ctx):
    t = ctx.t
    if s.get("hero"):
        return k_hero_cover(s, c, ctx)
    imgs = s.get("images", [])[:3]
    hgt = s.get("collage_height", 700) if imgs else 0
    f = (hgt or 700) / 700
    spots = [(f"left:{round(-24 * f)}px;top:{round(18 * f)}px;width:{round(640 * f)}px", "-5deg"),
             (f"right:{round(-40 * f)}px;top:{round(70 * f)}px;width:{round(600 * f)}px", "4deg"),
             (f"left:{round(120 * f)}px;top:{round(300 * f)}px;width:{round(680 * f)}px", "-1.5deg")]
    cards = ""
    for ref, (pos, rot) in zip(imgs, spots):
        w = int(re.search(r"width:(\d+)", pos).group(1))
        cards += (f'<div style="position:absolute;{pos};transform:rotate({rot});border:6px solid {t["paper"] if t.get("texture") else t["ice"]};border-radius:{2 if t.get("texture") else 6}px;'
                  f'box-shadow:{t["cover_shadow"]};background:{t["ice"]}">{image_box(c, ctx, ref, w - 12, int((w - 12) * 0.5625), 2, False)}</div>')
    tag = f'<span style="position:absolute;left:{round(96 * f)}px;top:{round(656 * f)}px;transform:rotate(-1.5deg);font-family:{t["mono"]};font-size:17px;font-weight:600;letter-spacing:0.16em;padding:10px 16px;border-radius:6px;background:{t["amber"]};color:{t["deep"]}">{ctx.txt(s.get("tag"))}</span>' if s.get("tag") else ""
    return ((f'<div style="position:relative;height:{hgt}px;flex:none">{cards}{tag}</div>' if hgt else "") +
            f'<div style="display:flex;flex-direction:column;gap:18px"><h1 style="margin:0;font-family:{t["display"]};font-weight:400;{display_style(t, c["dark"], s.get("headline_size", 104))}line-height:1.0;letter-spacing:-0.01em;text-wrap:balance">{ctx.txt(s.get("headline"))}</h1>'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:24px"><p style="margin:0;font-size:32px;line-height:1.35;color:{c["muted"]};max-width:520px">{ctx.txt(s.get("sub"))}</p>{stamp_row(s, c, ctx)}</div></div>')


def k_hero_cover(s, c, ctx):
    """Poster cover: one illustration filling the top of the frame, the headline set over its lower edge."""
    t = ctx.t
    h = s.get("hero_height", 900)
    art = image_box(c, ctx, s["hero"], 1080, h, 0, False)
    credit = credit_of(ctx, s["hero"])
    fade = f"linear-gradient(to bottom, transparent 55%, {rgba(c['bg'], 0.92)} 100%)"
    return (f'<div style="position:absolute;left:0;top:0;width:1080px;height:{h}px;z-index:0">{art}'
            f'<div aria-hidden="true" style="position:absolute;inset:0;background:{fade}"></div>'
            '</div>'
            f'<div style="flex:1"></div>'
            f'<div style="position:relative;z-index:1;display:flex;flex-direction:column;gap:18px">'
            + (f'<span style="align-self:flex-start;transform:rotate(-1.5deg);font-family:{t["mono"]};font-size:17px;font-weight:700;letter-spacing:0.16em;padding:10px 16px;border-radius:3px;background:{t["amber"]};color:{t["deep"]};{"filter:url(#rough);" if t.get("handmade") else ""}">{ctx.txt(s.get("tag"))}</span>' if s.get("tag") else "")
            + f'<h1 style="margin:0;font-family:{t["display"]};font-weight:400;{display_style(t, c["dark"], s.get("headline_size", 112))}line-height:1.0;letter-spacing:-0.01em;text-wrap:balance">{ctx.txt(s.get("headline"))}</h1>'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:24px"><p style="margin:0;font-size:30px;line-height:1.35;color:{c["fg"]};max-width:520px">{ctx.txt(s.get("sub"))}</p>{stamp_row(s, c, ctx)}</div></div>')


def stamp_row(s, c, ctx):
    t = ctx.t
    items = s.get("stamps_row") or []
    return '<div style="display:flex;gap:12px">' + "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;min-width:96px;padding:10px 10px 8px;border:3px solid {t["amber"] if it.get("alert") else t["ice"]};'
        f'border-radius:3px;color:{t["amber"] if it.get("alert") else t["ice"]};transform:rotate({(-1) ** i * 1.5}deg);{"filter:url(#rough);" if t.get("handmade") else ""}">'
        f'<span style="font-family:{t["display"]};font-size:40px;line-height:1">{ctx.txt(it.get("value"))}</span>'
        f'{icon(it.get("icon", ""), t["amber"] if it.get("alert") else t["ice"], 38)}'
        f'<span style="font-family:{t["mono"]};font-size:13px;letter-spacing:0.14em">{ctx.txt(it.get("label"))}</span></div>'
        for i, it in enumerate(items)) + "</div>"


def head(s, c, ctx, size=80):
    t = ctx.t
    eb = f'<span style="font-family:{t["mono"]};font-size:20px;font-weight:600;letter-spacing:0.18em;color:{c["accent"]}">{ctx.txt(s.get("eyebrow"))}</span>' if s.get("eyebrow") else ""
    sub = f'<p style="margin:0;font-size:28px;line-height:1.4;color:{c["muted"]}">{ctx.txt(s.get("sub"))}</p>' if s.get("sub") else ""
    return (f'<div style="display:flex;flex-direction:column;gap:20px">{eb}<h2 style="margin:0;font-family:{t["display"]};font-weight:400;'
            f'{display_style(t, c["dark"], s.get("headline_size", size))}line-height:1.08;letter-spacing:-0.01em;text-wrap:balance">{ctx.txt(s.get("headline"))}</h2>{sub}</div>')


def chip(ctx, label, status):
    t = ctx.t
    if t.get("stamps"):
        col = t["amber"] if status in ("HOLD", "CUT") else (t["ice"] if status in ("ACCEPT", "KEEP") else t["muted_dark"])
        ic = {"ACCEPT": "check", "KEEP": "check", "HOLD": "lens", "CUT": "cross", "CHANGE": "radar", "WATCH": "eye", "FLAG": "radar",
              "CALL": "lens", "PROVE": "check", "OPEN": "lens", "HIT": "check", "MISS": "cross", "VOID": "cross",
              "WHAT": "eye", "MOVE": "check", "NEXT": "radar", "LEAD": "radar"}.get(status, "")
        if status in ("WATCH", "FLAG", "CALL", "PROVE", "WHAT", "MOVE", "NEXT", "LEAD"):
            col = t["amber"] if status in ("FLAG", "MOVE", "LEAD") else t["ice"]
        return (f'<span style="justify-self:start;display:inline-flex;align-items:center;gap:10px;transform:rotate(-2deg);filter:url(#rough);'
                f'font-family:{t["mono"]};font-size:17px;font-weight:700;letter-spacing:0.14em;padding:9px 13px;border:3px solid {col};'
                f'border-radius:3px;color:{col};background:{rgba(t["deep"], 0.35)}">{icon(ic, col, 26)}{html.escape(label)}</span>')
    bg = {"ACCEPT": t["cyan"], "KEEP": t["cyan"], "HOLD": t["amber"], "CUT": t["amber"], "CHANGE": t["mint"]}.get(status, t["mint"])
    ring = f"box-shadow:inset 0 0 0 1.5px {rgba(t['navy'], 0.35)};" if status == "CHANGE" else ""
    return (f'<span style="justify-self:start;font-family:{t["mono"]};font-size:18px;font-weight:600;letter-spacing:0.16em;'
            f'padding:10px 16px;border-radius:6px;background:{bg};color:{t["deep"]};{ring}">{html.escape(label)}</span>')


def k_scorecard(s, c, ctx):
    rows = ""
    for i, r in enumerate(s.get("rows", [])):
        last = f"border-bottom:1.5px solid {c['rule']};" if i == len(s["rows"]) - 1 else ""
        rows += (f'<div style="display:grid;grid-template-columns:172px minmax(0,1fr);gap:28px;align-items:start;padding:24px 0;border-top:1.5px solid {c["rule"]};{last}">'
                 f'{chip(ctx, r["status"], r["status"])}<div style="display:flex;flex-direction:column;gap:6px;min-width:0">'
                 f'<span style="font-size:32px;font-weight:600;line-height:1.2">{ctx.txt(r.get("title"))}</span>'
                 f'<span style="font-size:25px;line-height:1.4;color:{c["muted"]}">{ctx.txt(r.get("detail"))}</span></div></div>')
    return head(s, c, ctx) + f'<div style="display:flex;flex-direction:column">{rows}</div>'


def k_day_bars(s, c, ctx):
    import datetime as dt
    t = ctx.t
    days = ctx.fig("first_seen_by_day") or {}
    win = ctx.fig("open_window")
    wdays = ctx.fig("window_days") or 7
    if win:
        start = dt.date.fromisoformat(win["start"]) - dt.timedelta(days=wdays)
        n = wdays * 3
    else:
        keys = sorted(k for k in days if k)
        start = dt.date.fromisoformat(keys[0]) - dt.timedelta(days=3) if keys else dt.date.today()
        n = 21
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    top = max(days.values()) if days else 1
    cells, axis = "", ""
    for d in dates:
        v = days.get(d.isoformat(), 0)
        if v:
            cells += (f'<div style="height:340px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:10px">'
                      f'<span style="font-family:{t["display"]};font-size:34px">{v}</span><div style="width:100%;height:{round(280 * v / top)}px;background:{t["cyan"]};border-radius:4px 4px 0 0"></div></div>')
        else:
            cells += f'<div style="height:340px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center"><div style="width:6px;height:6px;border-radius:50%;background:{rgba(t["ice"], 0.32)}"></div></div>'
        strong = f"color:{c['fg']};font-weight:600;" if v else ""
        axis += f'<span style="text-align:center;{strong}">{d.day}</span>'
    brackets = ""
    if win:
        labels = s.get("windows", ["BEFORE PANEL", "WINDOW 1 · OPEN", "WINDOW 2"])
        styles = [f"2px solid {rgba(t['ice'], 0.25)};color:{c['muted']}", f"2px solid {t['amber']};color:{t['amber']}",
                  f"2px dashed {rgba(t['ice'], 0.4)};color:{c['muted']}"]
        for i in range(3):
            a, b = dates[i * wdays], dates[i * wdays + wdays - 1]
            rng = f"{a.strftime('%b').upper()} {a.day}–{'' if a.month == b.month else b.strftime('%b').upper() + ' '}{b.day}"
            brackets += f'<div style="grid-column:span {wdays};padding-top:10px;border-top:{styles[i]}">{rng}<br>{ctx.txt(labels[i])}</div>'
    cols = f"repeat({n},minmax(0,1fr))"
    stats = "".join(f'<div style="display:flex;flex-direction:column;gap:8px"><span style="font-family:{t["display"]};font-size:64px;line-height:1">{ctx.txt(x["value"])}</span>'
                    f'<span style="font-size:23px;line-height:1.35;color:{c["muted"]}">{ctx.txt(x["label"])}</span></div>' for x in s.get("stats", []))
    body = f'<p style="margin:0;font-size:28px;line-height:1.45;max-width:900px">{ctx.txt(s.get("body"))}</p>' if s.get("body") else ""
    return (head(s, c, ctx, 84) +
            f'<div style="display:flex;flex-direction:column;gap:14px"><span style="font-family:{t["mono"]};font-size:17px;letter-spacing:0.12em;color:{c["muted"]}">{ctx.txt(s.get("chart_label", "RECORDS FIRST SEEN PER DAY, UTC"))}</span>'
            f'<div style="display:grid;grid-template-columns:{cols};gap:6px;align-items:end;border-bottom:1.5px solid {rgba(t["ice"], 0.4)}">{cells}</div>'
            f'<div style="display:grid;grid-template-columns:{cols};gap:6px;font-family:{t["mono"]};font-size:15px;color:{c["muted"]}">{axis}</div>'
            f'<div style="display:grid;grid-template-columns:{cols};gap:6px;font-family:{t["mono"]};font-size:15px;letter-spacing:0.08em;line-height:1.4">{brackets}</div></div>'
            f'<div style="display:grid;grid-template-columns:repeat({max(1, len(s.get("stats", [])))},minmax(0,1fr));gap:28px;padding-top:28px;border-top:1.5px solid {c["rule"]}">{stats}</div>{body}')


def k_source_bars(s, c, ctx):
    t = ctx.t
    mix = dict(ctx.fig("platform_mix") or {})
    for k, v in (ctx.fig("absent_channels") or {}).items():
        mix.setdefault(k, v)
    order = sorted(mix.items(), key=lambda kv: -kv[1])
    top = max([v for _, v in order] or [1]) or 1
    rows = ""
    for k, v in order:
        lab = PLATFORM_LABELS.get(k, k.replace("_", " ").title())
        if v:
            rows += (f'<div style="display:grid;grid-template-columns:250px minmax(0,1fr) 64px;gap:22px;align-items:center;height:46px"><span style="font-size:25px">{html.escape(lab)}</span>'
                     f'<div style="height:22px;background:{t["mint"]};border-radius:4px;display:flex"><div style="height:22px;width:{round(100 * v / top, 1)}%;background:{t["navy"]};border-radius:4px"></div></div>'
                     f'<span style="font-family:{t["display"]};font-size:32px;text-align:right">{v}</span></div>')
        else:
            rows += (f'<div style="display:grid;grid-template-columns:250px minmax(0,1fr) 64px;gap:22px;align-items:center;height:46px"><span style="font-size:25px">{html.escape(lab)}</span>'
                     f'<div style="height:22px;box-sizing:border-box;border:1.5px dashed {rgba(t["amber_ink"], 0.45)};border-radius:4px"></div>'
                     f'<span style="font-family:{t["display"]};font-size:32px;text-align:right;color:{t["amber_ink"]}">0</span></div>')
    strip = ""
    imgs = s.get("images", [])
    if imgs:
        widths = s.get("image_widths") or [int((936 - 16 * (len(imgs) - 1)) / len(imgs))] * len(imgs)
        strip = '<div style="display:flex;gap:16px;align-items:flex-start">' + "".join(
            f'<div style="display:flex;flex-direction:column;gap:8px;width:{w}px">{image_box(c, ctx, ref, w, 170)}'
            f'<span style="font-family:{t["mono"]};font-size:14px;letter-spacing:0.1em;color:{c["muted"]}">{ctx.txt(cap) if (cap := (ref.get("caption") if isinstance(ref, dict) else None)) else credit_of(ctx, ref).upper()}</span></div>'
            for ref, w in zip(imgs, widths)) + "</div>"
    body = f'<p style="margin:0;font-size:26px;line-height:1.45">{ctx.txt(s.get("body"))}</p>' if s.get("body") else ""
    return (head(s, c, ctx, 76) + strip +
            f'<div style="display:flex;flex-direction:column"><span style="font-family:{t["mono"]};font-size:17px;letter-spacing:0.12em;color:{c["muted"]};padding-bottom:8px">{ctx.txt(s.get("chart_label", "WHERE THE ACCEPTED OBSERVATIONS CAME FROM"))}</span>{rows}</div>{body}')


def radar_svg(ctx, size=560):
    t = ctx.t
    pts = ctx.fig("evidence_points") or []
    C = 450
    rad = lambda d: 40 + 300 * math.log10(1 + d) / math.log10(1 + 700)
    kinds = [k for k, _ in KINDS]
    extra = sorted({p[0] for p in pts} - set(kinds))
    labels = KINDS + [(e, e.replace("_", " ").upper()) for e in extra]
    n = len(labels)
    span = 360 / n
    dots, lbls, seps = "", "", ""
    counts = {k: sum(1 for p in pts if p[0] == k) for k, _ in labels}
    for i, (k, lab) in enumerate(labels):
        start = -90 + i * span
        items = sorted([p for p in pts if p[0] == k], key=lambda p: hashlib.md5(p[2].encode()).hexdigest())
        amber = k == "platform_aggregate"
        for j, p in enumerate(items):
            ang = math.radians(start + span * 0.1 + (j + 0.5) / len(items) * span * 0.8)
            r = 372 if p[1] is None else min(340, rad(p[1]))
            x, y = C + r * math.cos(ang), C + r * math.sin(ang)
            if amber:
                dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="none" stroke="{t["amber"]}" stroke-width="3"></circle>'
            elif p[1] is None:
                dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="none" stroke="{t["ice"]}" stroke-width="2"></circle>'
            else:
                dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{t["ice"]}"></circle>'
        b = math.radians(start)
        seps += f'<line x1="{C + 40 * math.cos(b):.1f}" y1="{C + 40 * math.sin(b):.1f}" x2="{C + 372 * math.cos(b):.1f}" y2="{C + 372 * math.sin(b):.1f}" stroke="{t["ice"]}" stroke-opacity="0.12" stroke-width="1.5"></line>'
        m = math.radians(start + span / 2)
        lx, ly = C + 262 * math.cos(m), C + 262 * math.sin(m)
        col, sub = (t["amber"], t["amber"]) if amber else (t["ice"], t["muted_dark"])
        lbls += (f'<text x="{lx:.0f}" y="{ly - 6:.0f}" text-anchor="middle" font-family="{t["display"]}" font-size="50" fill="{col}">{counts[k]}</text>'
                 f'<text x="{lx:.0f}" y="{ly + 26:.0f}" text-anchor="middle" font-family="{t["mono"]}" font-size="18" letter-spacing="1.5" fill="{sub}">{html.escape(lab)}</text>')
    last = math.radians(-90 - span * 0.85)
    wx, wy = C + 372 * math.cos(last), C + 372 * math.sin(last)
    ro = 0.45 if t.get("handmade") else 0.22
    rings = "".join(f'<circle cx="450" cy="450" r="{r}" fill="none" stroke="{t["ice"]}" stroke-opacity="{ro}" stroke-width="1.5"></circle>' for r in (71.7, 135.2, 197.2, 310.2))
    ring_lbl = "".join(f'<text x="440" y="{450 - r - 6:.0f}">{l}</text>' for r, l in ((71.7, "1D"), (135.2, "7D"), (197.2, "30D"), (310.2, "1Y"), (372, "UNDATED")))
    aria = html.escape("Radar of accepted observations by evidence type: " + ", ".join(f"{counts[k]} {l.lower()}" for k, l in labels))
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 900 900" role="img" aria-label="{aria}" style="{"filter:url(#rough)" if t.get("handmade") else ""}"><defs><linearGradient id="sweep" gradientUnits="userSpaceOnUse" x1="{wx:.0f}" y1="{wy:.0f}" x2="450" y2="78">'
            f'<stop offset="0" stop-color="{t["amber"]}" stop-opacity="0"></stop><stop offset="1" stop-color="{t["amber"]}" stop-opacity="0.32"></stop></linearGradient></defs>'
            f'<path d="M450 450 L{wx:.1f} {wy:.1f} A372 372 0 0 1 450 78 Z" fill="url(#sweep)"></path>'
            f'<circle cx="450" cy="450" r="40" fill="none" stroke="{t["ice"]}" stroke-opacity="0.14" stroke-width="1.5"></circle>{rings}'
            f'<circle cx="450" cy="450" r="372" fill="none" stroke="{t["ice"]}" stroke-opacity="0.34" stroke-width="1.5" stroke-dasharray="4 9"></circle>{seps}'
            f'<line x1="450" y1="450" x2="450" y2="78" stroke="{t["amber"]}" stroke-opacity="0.9" stroke-width="2.5"></line>'
            f'<g font-family="{t["mono"]}" font-size="17" letter-spacing="1.5" fill="{t["muted_dark"]}" text-anchor="end">{ring_lbl}</g>'
            f'{dots}<circle cx="450" cy="450" r="5" fill="{t["amber"]}"></circle>{lbls}</svg>')


def stat_rows(s, c, ctx):
    t = ctx.t
    return '<div style="display:flex;flex-direction:column">' + "".join(
        f'<div style="display:grid;grid-template-columns:130px minmax(0,1fr);gap:24px;align-items:center;padding:18px 0;border-top:1.5px solid {c["rule"]}">'
        f'<span style="font-family:{t["display"]};font-size:68px;line-height:1;{"color:" + c["accent"] if r.get("accent") else ""}">{ctx.txt(r["value"])}</span>'
        f'<span style="font-size:26px;line-height:1.4">{ctx.txt(r["text"])}</span></div>' for r in s.get("rows", [])) + "</div>"


def k_radar(s, c, ctx):
    t = ctx.t
    howto = "".join(f"<span>{ctx.txt(x)}</span>" for x in s.get("how_to_read", [
        "One dot per accepted observation, grouped by evidence type.",
        "Distance from centre: how old the item was when collected.", "Hollow dot: no publication date recorded."]))
    return (head(s, c, ctx, 72) +
            f'<div style="display:grid;grid-template-columns:560px minmax(0,1fr);gap:28px;align-items:center">{radar_svg(ctx)}'
            f'<div style="display:flex;flex-direction:column;gap:14px;font-family:{t["mono"]};font-size:17px;line-height:1.55;letter-spacing:0.03em;color:{c["muted"]};min-width:0">'
            f'<span style="color:{c["fg"]};letter-spacing:0.12em">HOW TO READ IT</span>{howto}</div></div>' + stat_rows(s, c, ctx))


def k_image_grid(s, c, ctx):
    t = ctx.t
    cards = ""
    for it in s.get("cards", []):
        ty = it.get("type", "")
        gap = it.get("gap")
        tcol = c["accent"] if gap else c["muted"]
        cards += (f'<div style="display:flex;flex-direction:column;border:1.5px solid {c["rule"]};border-radius:10px;overflow:hidden;background:{c["panel"]};min-width:0">'
                  f'{image_box(c, ctx, it.get("image"), 459, 150, 0, False)}<div style="display:flex;flex-direction:column;gap:6px;padding:16px 20px 18px">'
                  f'<span style="font-family:{t["mono"]};font-size:15px;letter-spacing:0.14em;color:{tcol};{"font-weight:600;" if gap else ""}">{ctx.txt(ty)}</span>'
                  f'<span style="font-size:26px;font-weight:600;line-height:1.2">{ctx.txt(it.get("name"))}</span>'
                  f'<span style="font-size:21px;line-height:1.35;color:{c["muted"]}">{ctx.txt(it.get("note"))}</span></div></div>')
    stats = "".join(f'<div style="display:flex;flex-direction:column;gap:8px;min-width:0"><span style="font-family:{t["display"]};font-size:88px;line-height:1;color:{c["accent"]}">{ctx.txt(x["value"])}</span>'
                    f'<span style="font-size:24px;line-height:1.4">{ctx.txt(x["label"])}</span></div>' for x in s.get("stats", []))
    note = f'<p style="margin:0;font-family:{t["mono"]};font-size:15px;line-height:1.6;color:{c["muted"]}">{ctx.txt(s.get("note"))}</p>' if s.get("note") else ""
    return (head(s, c, ctx, 70) + f'<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px">{cards}</div>'
            + (f'<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:36px">{stats}</div>' if stats else "") + note)


def k_metric_chart(s, c, ctx):
    t = ctx.t
    series = ctx.fig(s["series"])  # e.g. backfill.monthly.Content Authenticity Initiative
    months = [m for m in sorted(series) if s.get("from", "0000") <= m <= s.get("to", "9999")]
    vals = [series[m] for m in months]
    top = max(vals) if vals else 1
    peak = vals.index(top) if vals else -1
    n = len(months)
    bars = ""
    for i, (m, v) in enumerate(zip(months, vals)):
        lab = ""
        if i == peak:
            lab = f'<span style="position:absolute;bottom:238px;left:50%;transform:translateX(-50%);font-family:{t["mono"]};font-size:16px;color:{t["amber"]};white-space:nowrap">{month_name(m)} · {v:,}</span>'
        elif i == n - 1:
            lab = f'<span style="position:absolute;bottom:{round(230 * v / top) + 38}px;right:0;font-family:{t["mono"]};font-size:16px;color:{t["ice"]};white-space:nowrap">{month_name(m)} · {v:,}</span>'
        col = f"background:{t['amber']};" if i == peak else ""
        bars += f'<div style="height:{max(2, round(230 * v / top, 1))}px;background:{t["cyan"]};border-radius:3px 3px 0 0;position:relative;{col}">{lab}</div>'
    years, spans = [], []
    for m in months:
        if not years or years[-1] != m[:4]:
            years.append(m[:4]); spans.append(0)
        spans[-1] += 1
    yrs = "".join(f'<span style="grid-column:span {sp};padding:8px 0 0 6px;border-left:1.5px solid {rgba(t["ice"], 0.3)}">{y}</span>' for y, sp in zip(years, spans))
    pills = "".join(f'<span style="font-size:21px;padding:10px 16px;border-radius:{4 if t.get("stamps") else 999}px;border:{2 if t.get("stamps") else 1.5}px solid {rgba(t["cyan"], 0.55)}">{ctx.txt(p)}</span>' for p in s.get("pills", []))
    callout = ""
    if s.get("callout"):
        co = s["callout"]
        callout = (f'<div style="display:flex;flex-direction:column;gap:10px;padding:24px 28px;border:2px solid {t["amber"]};border-radius:12px">'
                   f'<span style="font-family:{t["mono"]};font-size:15px;font-weight:600;letter-spacing:0.14em;color:{t["amber"]}">{ctx.txt(co.get("eyebrow"))}</span>'
                   f'<span style="font-family:{t["display"]};font-size:44px;line-height:1.1">{ctx.txt(co.get("title"))}</span>'
                   f'<span style="font-size:23px;line-height:1.45;color:{t["callout_text"]}">{ctx.txt(co.get("text"))}</span></div>')
    aria = html.escape(f"Monthly values for {s.get('title', '')}, {months[0] if months else ''} to {months[-1] if months else ''}. Peak {top:,}.")
    return (head(s, c, ctx, 80) +
            f'<div style="display:flex;flex-direction:column;gap:14px;padding:26px 24px 22px;background:{t["panel_dark"]};border-radius:12px">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:20px"><span style="font-size:28px;font-weight:600;line-height:1.2">{ctx.txt(s.get("title"))}</span>'
            f'<span style="font-family:{t["mono"]};font-size:15px;letter-spacing:0.12em;color:{t["cyan"]};white-space:nowrap">{ctx.txt(s.get("unit"))}</span></div>'
            f'<div style="padding-top:34px"><div role="img" aria-label="{aria}" style="display:grid;grid-template-columns:repeat({n},minmax(0,1fr));gap:4px;align-items:end;height:250px;border-bottom:1.5px solid {rgba(t["ice"], 0.4)}">{bars}</div>'
            f'<div style="display:grid;grid-template-columns:repeat({n},minmax(0,1fr));gap:4px;font-family:{t["mono"]};font-size:15px;color:{t["muted_dark"]}">{yrs}</div></div>'
            f'<span style="font-size:21px;line-height:1.45;color:{t["muted_dark"]}">{ctx.txt(s.get("caption"))}</span></div>'
            + (f'<div style="display:flex;flex-wrap:wrap;gap:12px">{pills}</div>' if pills else "") + callout)


def month_name(m):
    import calendar
    return f"{calendar.month_abbr[int(m[5:7])].upper()} {m[:4]}"


def k_groups(s, c, ctx):
    t = ctx.t
    groups = ""
    for g in s.get("groups", []):
        items = "".join(f'<span style="font-size:{s.get("item_size", 27)}px;line-height:1.4"><b style="font-weight:600">{ctx.txt(i.get("lead"))}</b> {ctx.txt(i.get("text"))}</span>' for i in g.get("items", []))
        groups += (f'<div style="display:grid;grid-template-columns:150px minmax(0,1fr);gap:28px;align-items:start;padding:22px 0;border-top:1.5px solid {c["rule"]}">'
                   f'{chip(ctx, g["label"], g["label"])}<div style="display:flex;flex-direction:column;gap:12px;min-width:0">{items}</div></div>')
    top = head(s, c, ctx, 66)
    if s.get("image"):
        img = s["image"]
        top = (f'<div style="display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:32px;align-items:center">{top}'
               f'<div style="display:flex;flex-direction:column;gap:14px;transform:rotate(2.5deg)"><div style="border:6px solid {t["paper"]};border-radius:{2 if t.get("texture") else 6}px;box-shadow:{t["card_shadow"]};background:{t["paper"]}">'
               f'{image_box(c, ctx, img, 368, 207, 0, False)}</div>'
               f'<span style="align-self:flex-start;font-family:{t["mono"]};font-size:15px;font-weight:600;letter-spacing:0.14em;padding:8px 12px;border-radius:6px;background:{t["amber"]};color:{t["deep"]}">{ctx.txt(s.get("image_tag"))}</span></div></div>')
    return top + f'<div style="display:flex;flex-direction:column;border-bottom:1.5px solid {c["rule"]}">{groups}</div>'


def k_tests(s, c, ctx):
    t = ctx.t
    rows = "".join(f'<div style="display:flex;flex-direction:column;gap:8px;padding:24px 0;border-top:1.5px solid {c["rule"]}">'
                   f'<span style="font-family:{t["display"]};font-size:38px;line-height:1.1">{ctx.txt(r["name"])}</span>'
                   f'<span style="font-size:23px;line-height:1.4;color:{c["muted"]}">{ctx.txt(r["detail"])}</span>'
                   f'<span style="font-family:{t["mono"]};font-size:19px;line-height:1.5;letter-spacing:0.04em;color:{t["cyan"]}"><b style="font-weight:600;letter-spacing:0.14em">PASS</b>  {ctx.txt(r["pass"])}</span></div>'
                   for r in s.get("rows", []))
    return head(s, c, ctx, 80) + f'<div style="display:flex;flex-direction:column;border-bottom:1.5px solid {c["rule"]}">{rows}</div>'


def k_quote(s, c, ctx):
    t = ctx.t
    return (f'<div style="display:flex;flex-direction:column;gap:30px"><span style="font-family:{t["mono"]};font-size:20px;font-weight:600;letter-spacing:0.18em;color:{c["accent"]}">{ctx.txt(s.get("eyebrow"))}</span>'
            f'<h2 style="margin:0;font-family:{t["display"]};font-weight:400;{display_style(t, c["dark"], s.get("headline_size", 148))}line-height:1.02;letter-spacing:-0.015em;text-wrap:balance">{ctx.txt(s.get("headline"))}</h2>'
            f'<p style="margin:0;font-size:32px;line-height:1.45;max-width:880px">{ctx.txt(s.get("body"))}</p></div>'
            f'<div style="display:flex;flex-direction:column;gap:22px;padding:44px 48px;background:{t["panel_dark"] if t.get("single_tone") else t["deep"]};color:{t["ice"]};border-radius:{3 if t.get("stamps") else 14}px;{"border:3px solid " + t["amber"] + ";box-shadow:" + t["card_shadow"] + ";" if t.get("stamps") else ""}">'
            f'<span style="font-family:{t["mono"]};font-size:16px;font-weight:600;letter-spacing:0.16em;color:{t["amber"]}">{ctx.txt(s.get("attribution"))}</span>'
            f'<span style="font-family:{t["display"]};font-size:54px;line-height:1.12;text-wrap:balance">{ctx.txt(s.get("quote"))}</span></div>')


def k_signal_board(s, c, ctx):
    """One row per tracked name: 52 weeks of backfilled history, latest week, and whether the rule flagged it."""
    t = ctx.t
    src = s.get("signal_source", "wikipedia")
    ents = ((ctx.data.get(s.get("signals_key", "signals")) or {}).get("sources") or {}).get(src, {}).get("entities", {})
    names = s.get("names") or sorted(ents, key=lambda n: -max(ents[n].get("tail52") or [0]))[: s.get("max_rows", 6)]
    rows = ""
    for n in names:
        e = ents.get(n)
        if not e:
            rows += (f'<div style="display:grid;grid-template-columns:260px minmax(0,1fr) 150px;gap:20px;align-items:center;padding:14px 0;border-top:1.5px solid {c["rule"]}">'
                     f'<span style="font-size:24px;font-weight:600">{html.escape(n)}</span><span style="font-family:{t["mono"]};font-size:15px;color:{c["muted"]}">NO DATA PULLED</span><span></span></div>')
            continue
        tail = e.get("tail52") or []
        top = max(tail) or 1
        bars = "".join(f'<div style="height:{0 if not v or v <= 0 else max(2, round(64 * v / top))}px;background:{t["amber"] if (e.get("flagged_recent") and i >= len(tail) - 8) else t["ice"]};opacity:{0.95 if i >= len(tail) - 8 else 0.7}"></div>' for i, v in enumerate(tail))
        flag = e.get("first_flag_week")
        if e.get("flagged_recent"):
            tag = chip(ctx, "FLAGGED", "HOLD")
        else:
            tag = f'<span style="font-family:{t["mono"]};font-size:15px;letter-spacing:0.12em;color:{c["muted"]}">NO FLAG</span>'
        last = tail[-1] if tail else 0
        rows += (f'<div style="display:grid;grid-template-columns:260px minmax(0,1fr) 150px;gap:20px;align-items:end;padding:14px 0;border-top:1.5px solid {c["rule"]}">'
                 f'<div style="display:flex;flex-direction:column;gap:4px;min-width:0"><span style="font-size:24px;font-weight:600;line-height:1.2">{html.escape(n)}</span>'
                 f'<span style="font-family:{t["mono"]};font-size:14px;color:{c["muted"]}">LAST WEEK {last:,} · PEAK {top:,}</span></div>'
                 f'<div role="img" aria-label="{html.escape(n)}: 52 weeks of {src} values, latest {last:,}" style="display:grid;grid-template-columns:repeat({max(1, len(tail))},minmax(0,1fr));gap:2px;align-items:end;height:64px;{"filter:url(#rough);" if t.get("handmade") else ""}">{bars}</div>'
                 f'<div style="justify-self:end">{tag}</div></div>')
    disclose = ("Each row is scaled to its own 52-week peak, so rows are not comparable in size. Blank weeks had no observations. "
                "NO FLAG means the fixed rule found no anomaly, not that attention is falling.")
    note = f'<p style="margin:0;font-family:{t["mono"]};font-size:15px;line-height:1.6;color:{c["muted"]}">{ctx.txt((s.get("note") or "") + " " + disclose)}</p>'
    return head(s, c, ctx, 76) + f'<div style="display:flex;flex-direction:column;border-bottom:1.5px solid {c["rule"]}">{rows}</div>' + note


def _tbl(c, cols, rows, t):
    head = "".join(f'<span style="font-family:{t["mono"]};font-size:14px;letter-spacing:0.12em;color:{c["muted"]}">{html.escape(h)}</span>' for h, _ in cols)
    tmpl = " ".join(w for _, w in cols)
    body = "".join(f'<div style="display:grid;grid-template-columns:{tmpl};gap:14px;align-items:center;padding:10px 0;border-top:1.5px solid {c["rule"]}">{r}</div>' for r in rows)
    return (f'<div style="display:flex;flex-direction:column;border-bottom:1.5px solid {c["rule"]}">'
            f'<div style="display:grid;grid-template-columns:{tmpl};gap:14px;padding-bottom:8px">{head}</div>{body}</div>')


def k_backtest(s, c, ctx):
    """Would the rule have flagged it before the benchmark press named it? Straight from backtest.json."""
    t = ctx.t
    bt = ctx.data.get("backtest") or {}
    cases = [r for r in bt.get("cases", []) if not s.get("ids") or r["id"] in s["ids"]]
    rows = []
    for r in cases:
        fb = r.get("first_benchmark") or {}
        src = min(((v["flag_known_at"], k) for k, v in r.get("per_source", {}).items() if v.get("flag_known_at")), default=(None, None))
        lead = r.get("lead_days_vs_press")
        dur = next((v.get("durability") for k, v in r.get("per_source", {}).items() if k == src[1]), None)
        lead_txt = "no flag" if lead is None and r.get("earliest_flag_known_at") is None else ("no press" if lead is None else f"{lead:+d} days")
        col = t["ice"] if (lead or 0) > 0 else t["amber"]
        src = (src[0], {"bluesky": "Bluesky", "hackernews": "Hacker News", "wikipedia": "Wikipedia", "github": "GitHub", "youtube": "YouTube"}.get(src[1], src[1]))
        rows.append(f'<span style="font-size:23px;font-weight:600;line-height:1.2">{html.escape(r["name"])}<br><span style="font-family:{t["mono"]};font-size:13px;font-weight:400;letter-spacing:0.1em;color:{c["muted"]}">{html.escape(r["kind"].upper())}</span></span>'
                    f'<span style="font-size:19px;line-height:1.3">{html.escape(fb.get("outlet", "none found"))}<br><span style="font-family:{t["mono"]};font-size:14px;color:{c["muted"]}">{html.escape(fb.get("published", "")[:10])}</span></span>'
                    f'<span style="font-size:19px;line-height:1.3">{html.escape(src[1] or "none")}<br><span style="font-family:{t["mono"]};font-size:14px;color:{c["muted"]}">{html.escape(src[0] or "")}</span></span>'
                    f'<span style="font-family:{t["display"]};font-size:26px;color:{col};text-align:right;white-space:nowrap">{html.escape(lead_txt)}</span>'
                    f'<span style="font-family:{t["mono"]};font-size:14px;letter-spacing:0.1em;color:{c["muted"]};text-align:right">{html.escape((dur or "").upper())}</span>')
    cols = [("CASE", "minmax(0,1.25fr)"), ("FIRST PRESS", "minmax(0,1.05fr)"), ("FIRST FLAG", "minmax(0,0.85fr)"), ("LEAD", "190px"), ("AFTER", "112px")]
    note = f'<p style="margin:0;font-family:{t["mono"]};font-size:15px;line-height:1.6;color:{c["muted"]}">{ctx.txt(s.get("note"))}</p>' if s.get("note") else ""
    return head(s, c, ctx, 70) + _tbl(c, cols, rows, t) + note


def k_calls(s, c, ctx):
    t = ctx.t
    calls = ctx.data.get("calls_list") or []
    rows = []
    for r in calls[: s.get("max_rows", 10)]:
        st = r.get("status", "open").upper()
        rows.append(f'<span style="font-family:{t["mono"]};font-size:15px;color:{c["muted"]}">{html.escape(r["call_id"])}</span>'
                    f'<span style="font-size:22px;font-weight:600;line-height:1.25">{html.escape(r["subject"])}</span>'
                    f'<span style="font-family:{t["mono"]};font-size:15px;color:{c["muted"]};text-align:right">{html.escape(r["resolve_by"])}</span>'
                    f'<span style="justify-self:end">{chip(ctx, st, "ACCEPT" if st == "HIT" else ("CUT" if st == "MISS" else "HOLD"))}</span>')
    cols = [("CALL", "90px"), ("SUBJECT", "minmax(0,1fr)"), ("DUE", "130px"), ("STATUS", "150px")]
    return head(s, c, ctx, 70) + _tbl(c, cols, rows, t)


def k_registry(s, c, ctx):
    t = ctx.t
    reg = ctx.data.get("registry") or {}
    accts = reg.get("accounts", {})
    rows = []
    names = {cse["id"]: cse["name"] for cse in (ctx.data.get("backtest") or {}).get("cases", [])}
    picked, per_case = [], {}
    for key in reg.get("ranked") or []:  # spread the list across cases: at most two accounts per case
        if accts[key].get("likely_feed"):
            continue
        best = max(accts[key]["evidence"], key=lambda e: e["lead_days"])["case"]
        if per_case.get(best, 0) < s.get("per_case", 2):
            picked.append(key)
            per_case[best] = per_case.get(best, 0) + 1
        if len(picked) >= s.get("max_rows", 8):
            break
    for key in picked:
        a = accts[key]
        ev = sorted(a["evidence"], key=lambda e: -e["lead_days"])[0]
        rows.append(f'<span style="font-family:{t["mono"]};font-size:14px;letter-spacing:0.1em;color:{c["muted"]}">{html.escape(a["platform"].upper())}</span>'
                    f'<span style="font-size:22px;font-weight:600;line-height:1.25;overflow-wrap:anywhere">{html.escape(a["handle"])}</span>'
                    f'<span style="font-size:18px;line-height:1.3;color:{c["muted"]}">{html.escape(names.get(ev["case"], ev["case"]))} · beat {html.escape(ev["benchmark_outlet"])}</span>'
                    f'<span style="font-family:{t["display"]};font-size:28px;text-align:right">{ev["lead_days"]}d</span>')
    cols = [("WHERE", "110px"), ("ACCOUNT", "minmax(0,1fr)"), ("EARLY ON", "minmax(0,1fr)"), ("LEAD", "100px")]
    return head(s, c, ctx, 70) + _tbl(c, cols, rows, t)


def k_signal(s, c, ctx):
    """One signal per slide: number, what happened, the so-what, and (in the footer) the receipt."""
    t = ctx.t
    img = ""
    if s.get("image_path"):
        img = (f'<div style="border:8px solid {t["paper"]};box-shadow:{t["card_shadow"]};background:{t["paper"]};height:{s.get("image_h", 330)}px;overflow:hidden;transform:rotate(-1.2deg)">'
               f'<img src="file://{html.escape(s["image_path"])}" style="width:100%;height:100%;object-fit:cover;object-position:{s.get("image_pos", "center top")};filter:{t.get("image_filter", "none")}"></div>')
    so = (f'<div style="display:flex;gap:22px;align-items:flex-start;padding-top:24px;border-top:2px solid {c["rule"]}">'
          f'<span style="flex:none;font-family:{t["mono"]};font-weight:700;font-size:20px;letter-spacing:0.16em;padding:8px 14px;border:3px solid {t["amber"]};color:{t["amber"]};filter:url(#rough)">SO WHAT</span>'
          f'<span style="font-size:{s.get("so_size", 32)}px;line-height:1.35;font-weight:700">{ctx.txt(s.get("so_what"))}</span></div>')
    return (f'<div style="display:flex;flex-direction:column;gap:26px">'
            f'<div style="display:flex;align-items:baseline;gap:22px"><span style="font-family:{t["display"]};{display_style(t, c["dark"], 120)}line-height:0.9">{ctx.txt(s.get("number"))}</span>'
            f'<span style="font-family:{t["mono"]};font-size:21px;font-weight:600;letter-spacing:0.16em;color:{c["accent"]}">{ctx.txt(s.get("eyebrow"))}</span></div>'
            f'<h2 style="margin:0;font-family:{t["display"]};font-weight:400;{display_style(t, c["dark"], s.get("headline_size", 74))}line-height:1.06;text-wrap:balance">{ctx.txt(s.get("headline"))}</h2>'
            f'{img}<p style="margin:0;font-size:{s.get("what_size", 31)}px;line-height:1.4">{ctx.txt(s.get("what"))}</p>{so}'
            + (f'<p style="margin:0;font-family:{t["mono"]};font-size:17px;line-height:1.5;color:{c["muted"]}">NOT YET PROVEN: {ctx.txt(s.get("caveat"))}</p>' if s.get("caveat") else "")
            + '</div>')


def k_story(s, c, ctx):
    """An evidence-led story: one large screenshot, real output or chart, then what happened, why it matters,
    our read (labelled interpretation), what is unproven, a bounded next step and what would change the read."""
    t = ctx.t
    ev = ""
    if s.get("image_path"):
        ev = (f'<div style="position:relative;border:8px solid {t["paper"]};box-shadow:{t["card_shadow"]};background:{s.get("image_bg", t["paper"])};height:{s.get("image_h", 420)}px;overflow:hidden">'
              f'<img src="file://{html.escape(s["image_path"])}" style="width:100%;height:100%;object-fit:{s.get("image_fit", "cover")};object-position:{s.get("image_pos", "center top")};filter:{t.get("image_filter", "none")}">'
              f'<span style="position:absolute;right:10px;top:10px;font-family:{t["mono"]};font-size:14px;font-weight:700;letter-spacing:0.12em;padding:6px 10px;background:{t["navy"]};color:{t["ice"]}">{ctx.txt(s.get("tag", "CAPTURE"))}</span></div>')
    elif s.get("code"):
        ev = (f'<div style="position:relative;background:#0d1110;border:3px solid {t["paper"]};padding:22px 26px;box-shadow:{t["card_shadow"]}">'
              f'<pre style="margin:0;font-family:{t["mono"]};font-size:{s.get("code_size", 19)}px;line-height:1.5;color:#e9e3d2;white-space:pre-wrap">{html.escape(s["code"])}</pre>'
              f'<span style="position:absolute;right:10px;top:10px;font-family:{t["mono"]};font-size:14px;font-weight:700;letter-spacing:0.12em;padding:6px 10px;background:{t["amber"]};color:{t["navy"]}">{ctx.txt(s.get("tag", "ACTUAL OUTPUT"))}</span></div>')
    rows = "".join(f'<div style="display:grid;grid-template-columns:200px minmax(0,1fr);gap:20px;padding:10px 0;border-top:1.5px solid {c["rule"]}">'
                   f'<span style="font-family:{t["mono"]};font-size:15px;font-weight:700;letter-spacing:0.12em;color:{t["amber"] if lab.startswith(("OUR READ", "YOUR TAKE", "NEXT")) else c["muted"]};padding-top:4px">{html.escape(lab)}</span>'
                   f'<span style="font-size:{s.get("row_size", 23)}px;line-height:1.38">{ctx.txt(txt)}</span></div>' for lab, txt in s.get("rows", []))
    return (head(s, c, ctx, s.get("headline_size", 60)) + f'<div style="display:flex;flex-direction:column;gap:18px">{ev}'
            f'<div style="display:flex;flex-direction:column;border-bottom:1.5px solid {c["rule"]}">{rows}</div></div>')


def k_receipts(s, c, ctx):
    """Every source behind the edition, clickable in the text PDF, plus where the calls stand."""
    t = ctx.t
    items = "".join(f'<div style="display:grid;grid-template-columns:230px minmax(0,1fr);gap:18px;padding:8px 0;border-top:1px solid {c["rule"]}">'
                    f'<span style="font-family:{t["mono"]};font-size:14px;font-weight:700;letter-spacing:0.08em;color:{c["muted"]}">{html.escape(lab)}</span>'
                    f'<span style="font-size:17px;line-height:1.4;word-break:break-all">{ctx.txt(txt)}</span></div>' for lab, txt in s.get("links", []))
    calls = f'<p style="margin:0;font-size:22px;line-height:1.45">{ctx.txt(s.get("calls", ""))}</p>' if s.get("calls") else ""
    return head(s, c, ctx, 60) + f'<div style="display:flex;flex-direction:column;gap:16px">{calls}<div style="display:flex;flex-direction:column">{items}</div></div>'


def k_signal_cover(s, c, ctx):
    t = ctx.t
    lines = "".join(f'<div style="font-family:{t["display"]};{display_style(t, c["dark"], s.get("size", 120))}line-height:1.0">{ctx.txt(l)}</div>' for l in s.get("lines", []))
    return (f'<div style="display:flex;flex-direction:column;gap:34px;margin-top:40px">'
            f'<span style="font-family:{t["mono"]};font-size:22px;font-weight:700;letter-spacing:0.2em;color:{c["accent"]}">{ctx.txt(s.get("eyebrow"))}</span>{lines}'
            f'<p style="margin:0;font-size:34px;line-height:1.4;max-width:860px">{ctx.txt(s.get("sub"))}</p></div>')


def png_size(path):
    with open(path, "rb") as f:
        head_bytes = f.read(24)
    return (int.from_bytes(head_bytes[16:20], "big"), int.from_bytes(head_bytes[20:24], "big")) if head_bytes[:8] == b"\x89PNG\r\n\x1a\n" else (1280, 1500)


def sticker_filter(t):
    p = t["paper"]
    return f"drop-shadow(4px 0 0 {p}) drop-shadow(-4px 0 0 {p}) drop-shadow(0 4px 0 {p}) drop-shadow(0 -4px 0 {p}) drop-shadow(6px 6px 0 {t['navy']})"


def cutout(ctx, sp, h):
    """A receipt cut down to a sticker that sits between the words: centred on (cx, cy) of the image, at zoom.
    With "figure", a cut-out person or object on a transparent ground, outlined like a die-cut sticker."""
    t = ctx.t
    if sp.get("figure"):
        return (f'<img aria-hidden="true" src="file://{html.escape(sp["path"])}" style="display:inline-block;vertical-align:{sp.get("lift", "-0.2em")};height:{round(h * sp.get("scale", 1.3))}px;margin:0 0.06em;'
                f'transform:rotate({sp.get("tilt", -4)}deg);filter:{sticker_filter(t)}">')
    w = round(h * sp.get("aspect", 1.25))
    iw, ih = png_size(sp["path"])
    bw = w * sp.get("zoom", 3)
    bh = bw * ih / iw
    x = min(0, max(w - bw, w / 2 - sp.get("cx", 0.5) * bw))
    y = min(0, max(h - bh, h / 2 - sp.get("cy", 0.5) * bh))
    return (f'<span aria-hidden="true" style="display:inline-block;vertical-align:-0.1em;width:{w}px;height:{h}px;margin:0 0.1em;border:5px solid {t["paper"]};border-radius:14px;'
            f'box-shadow:{t["card_shadow"]};transform:rotate({sp.get("tilt", -4)}deg);background:url(\'file://{html.escape(sp["path"])}\') {x:.0f}px {y:.0f}px/{bw:.0f}px {bh:.0f}px no-repeat"></span>')


def k_take_cover(s, c, ctx):
    """Carousel cover: big first-person words with receipts cut down to stickers between them, then one piece of art."""
    t = ctx.t
    size = s.get("size", 104)
    cuts = s.get("cutouts", {})

    def line(l):
        parts = re.split(r"\{(\w+)\}", l)
        return "".join(cutout(ctx, cuts[p], round(size * 0.74)) if i % 2 else ctx.txt(p) for i, p in enumerate(parts))
    lines = "".join(f'<div style="font-family:{t["display"]};{display_style(t, c["dark"], size)}line-height:1.12">{line(l)}</div>' for l in s.get("lines", []))
    art = ""
    if s.get("image_path"):
        art = (f'<div style="position:relative;align-self:flex-end;width:{s.get("image_w", 560)}px;height:{s.get("image_h", 380)}px;border:8px solid {t["paper"]};box-shadow:{t["card_shadow"]};overflow:hidden;transform:rotate(1.5deg)">'
               f'<img src="file://{html.escape(s["image_path"])}" style="width:100%;height:100%;object-fit:cover;object-position:{s.get("image_pos", "center")}">'
               + (f'<span style="position:absolute;left:10px;bottom:10px;font-family:{t["mono"]};font-size:13px;letter-spacing:0.1em;padding:5px 9px;background:{t["navy"]};color:{t["ice"]}">{ctx.txt(s["credit"])}</span>' if s.get("credit") else "")
               + '</div>')
    return (f'<div style="display:flex;flex-direction:column;gap:28px">'
            + (f'<span style="font-family:{t["mono"]};font-size:{s.get("eyebrow_size", 22)}px;font-weight:700;letter-spacing:0.16em;color:{c["accent"]}">{ctx.txt(s["eyebrow"])}</span>' if s.get("eyebrow") else "")
            + f'<div>{lines}</div>{art}'
            + (f'<p style="margin:0;font-size:32px;line-height:1.4;max-width:880px">{ctx.txt(s.get("sub"))}</p>' if s.get("sub") else "") + '</div>')


def k_take(s, c, ctx):
    """One signal in the carousel format: a plain headline, the receipt, what happened, then the owner's take in the first person."""
    t = ctx.t
    ev = ""
    if s.get("image_path") and s.get("crop"):  # an exact region of the capture, e.g. a press headline without the ads around it
        x, y, w, h = s["crop"]
        iw, ih = png_size(s["image_path"])
        box = s.get("crop_w", 920)
        k = min(box / w, s.get("crop_max_h", 10 ** 6) / h)  # a tall capture (an X post) shrinks to fit and sits centred
        fit = w * k < box - 2  # narrower than the column: the frame hugs the capture instead of padding it
        left = -x * k if fit else (box - w * k) / 2 - x * k
        size = f'width:{round(w * k)}px;align-self:center;' if fit else ""
        ev = (f'<div style="{size}border:8px solid {t["paper"]};box-shadow:{t["card_shadow"]};height:{round(h * k)}px;transform:rotate({s.get("tilt", -1)}deg);'
              f'background:{s.get("crop_bg", "transparent")} url(\'file://{html.escape(s["image_path"])}\') {left:.0f}px {-y * k:.0f}px/{iw * k:.0f}px {ih * k:.0f}px no-repeat"></div>')
    elif s.get("image_path"):
        ev = (f'<div style="border:8px solid {t["paper"]};box-shadow:{t["card_shadow"]};background:{t["paper"]};height:{s.get("image_h", 380)}px;overflow:hidden;transform:rotate({s.get("tilt", -1)}deg)">'
              f'<img src="file://{html.escape(s["image_path"])}" style="width:100%;height:100%;object-fit:cover;object-position:{s.get("image_pos", "center top")};filter:{t.get("image_filter", "none")}"></div>')
    elif s.get("code"):
        ev = (f'<div style="background:#0d1110;border:3px solid {t["paper"]};padding:20px 24px;box-shadow:{t["card_shadow"]}">'
              f'<pre style="margin:0;font-family:{t["mono"]};font-size:{s.get("code_size", 18)}px;line-height:1.5;color:#e9e3d2;white-space:pre-wrap">{html.escape(s["code"])}</pre></div>')
    elif s.get("post"):  # a quoted post, word for word, as the receipt
        q = s["post"]
        ev = (f'<div style="background:{t["paper"]};color:{t["navy"]};box-shadow:{t["card_shadow"]};padding:28px 34px;transform:rotate({s.get("tilt", -1)}deg)">'
              f'<div style="display:flex;gap:14px;align-items:baseline;flex-wrap:wrap"><b style="font-size:26px">{html.escape(q["name"])}</b>'
              f'<span style="font-family:{t["mono"]};font-size:18px;opacity:.7">{html.escape(q["handle"])} · {html.escape(q["when"])}</span></div>'
              f'<p style="margin:14px 0 0;font-size:{s.get("post_size", 28)}px;line-height:1.42">{html.escape(q["text"])}</p>'
              + (f'<div style="margin-top:16px;font-family:{t["mono"]};font-size:17px;letter-spacing:.06em;opacity:.7">{html.escape(q["stats"])}</div>' if q.get("stats") else "") + '</div>')
    if ev and s.get("sticker"):  # a small cut-out of the owner on the corner of the receipt
        st = s["sticker"]
        ev = (f'<div style="position:relative">{ev}<img aria-hidden="true" src="file://{html.escape(st["path"])}" style="position:absolute;right:{st.get("right", -24)}px;{f'top:{st["top"]}px' if "top" in st else f'bottom:{st.get("bottom", -40)}px'};'
              f'height:{st.get("h", 240)}px;transform:rotate({st.get("tilt", 5)}deg);filter:{sticker_filter(t)};z-index:3"></div>')
    size = s.get("what_size", 29)
    notes = s.get("notes") or ([[s.get("caveat_label", "NOT PROVEN"), s["caveat"]]] if s.get("caveat") else [])
    note = "".join(f'<p style="margin:0;font-family:{t["mono"]};font-size:17px;line-height:1.5;color:{c["muted"]}">{html.escape(lab)}: {ctx.txt(txt)}</p>' for lab, txt in notes)
    return (f'<div style="display:flex;flex-direction:column;gap:24px">'
            + (f'<span style="font-family:{t["mono"]};font-size:21px;font-weight:600;letter-spacing:0.16em;color:{c["accent"]}">{ctx.txt(s["eyebrow"])}</span>' if s.get("eyebrow") else "")
            + f'<h2 style="margin:-4px 0 0;font-family:{t["display"]};font-weight:400;{display_style(t, c["dark"], s.get("headline_size", 76))}line-height:1.06;text-wrap:balance">{ctx.txt(s.get("headline"))}</h2>'
            + ev + (f'<p style="margin:0;font-size:{size}px;line-height:1.42">{ctx.txt(s["what"])}</p>' if s.get("what") else "")
            + f'<p style="margin:0;font-size:{size}px;line-height:1.42;font-weight:700;border-left:6px solid {c["accent"]};padding-left:20px">{ctx.txt(s.get("take"))}</p>{note}</div>')


KIND = {"take": k_take, "take_cover": k_take_cover, "story": k_story, "receipts": k_receipts, "signal": k_signal, "signal_cover": k_signal_cover, "backtest": k_backtest, "calls": k_calls, "registry": k_registry, "signal_board": k_signal_board, "cover": k_cover, "scorecard": k_scorecard, "day_bars": k_day_bars, "source_bars": k_source_bars,
        "radar": k_radar, "image_grid": k_image_grid, "metric_chart": k_metric_chart, "groups": k_groups,
        "tests": k_tests, "quote": k_quote}

OVERFLOW_JS = """<script>document.fonts.ready.then(function(){var r=document.getElementById('frame');var bad=r.scrollHeight>r.clientHeight+1||r.scrollWidth>r.clientWidth+1;
document.documentElement.setAttribute('data-overflow',bad?'yes':'no');document.documentElement.setAttribute('data-fonts',Array.from(document.fonts).some(function(f){return f.family.replace(/["']/g,'')==='__DISPLAY__'&&f.status==='loaded';})?'ok':'fallback');});</script>"""


def page(s, i, total, ctx, deck):
    dark = True if ctx.t.get("single_tone") else s.get("tone", "dark" if i % 2 == 1 else "light") == "dark"
    c = tone_colors(ctx.t, dark)
    t = ctx.t
    body = KIND[s["kind"]](s, c, ctx)
    hdr = (f'<div style="position:relative;z-index:2;display:flex;justify-content:space-between;align-items:baseline;padding-bottom:22px;border-bottom:1.5px solid {c["rule"]}">'
           f'<div style="display:flex;align-items:baseline;gap:14px"><span style="font-weight:700;font-size:26px;letter-spacing:0.16em">{html.escape(deck.get("brand", "THE SCOUT"))}</span>'
           f'<span style="font-family:{t["mono"]};font-size:18px;letter-spacing:0.14em;color:{c["muted"]}">/ {html.escape(deck.get("series", "STRESS TEST"))}</span></div>'
           f'<span style="font-family:{t["mono"]};font-size:18px;letter-spacing:0.14em;color:{c["muted"]}">{html.escape(deck.get("date", ""))} · {i:02d}/{total:02d}</span></div>')
    seal = ""
    if t.get("seals"):
        word = s.get("seal") or SEALS.get(s["kind"], "")
        seal = (f'<span aria-hidden="true" style="position:absolute;right:28px;top:128px;z-index:3;transform:rotate(3deg);writing-mode:vertical-rl;filter:url(#rough);'
                f'font-family:{t["mono"]};font-weight:700;font-size:17px;letter-spacing:0.22em;line-height:1;padding:14px 8px;border:3px solid {t["amber"]};color:{t["amber"]};'
                f'border-radius:3px;background:{rgba(c["bg"], 0.6)}">{html.escape(word)}</span>') if word else ""
        if s["kind"] == "cover":
            seal += (f'<span aria-hidden="true" style="position:absolute;left:14px;top:150px;writing-mode:vertical-rl;transform:rotate(180deg);font-family:{t["vertical"]};'
                     f'font-size:46px;line-height:1;letter-spacing:0.08em;color:{t["ice"]};text-shadow:3px 3px 0 {t["navy"]},6px 6px 0 {t["amber"]};z-index:2;filter:url(#distress)">'
                     f'{html.escape(deck.get("vertical_title", deck.get("brand", "THE SCOUT")))}</span>')
    ftr = (f'<div style="position:relative;z-index:2;display:flex;justify-content:space-between;align-items:baseline;gap:24px;padding-top:18px;border-top:1.5px solid {c["rule"]};font-family:{t["mono"]};font-size:17px;letter-spacing:0.06em;color:{c["muted"]}">'
           f'<span>{ctx.txt(s.get("source"))}</span><span style="letter-spacing:0.14em">{html.escape(deck.get("mark", ""))}</span></div>')
    if deck.get("minimal"):  # a personal post: no masthead, stamps or source line, only the owner's handle
        hdr, seal = "", ""
        body = f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:48px;padding-bottom:28px">{body}</div>'
        ftr = (f'<div style="position:relative;z-index:2;padding-top:18px;border-top:1.5px solid {c["rule"]};font-family:{t["mono"]};font-size:18px;letter-spacing:0.14em;color:{c["muted"]}">'
               f'{html.escape(deck.get("mark", ""))}</div>')
    overflow_js = OVERFLOW_JS.replace("__DISPLAY__", t["display"].split(",")[0].strip(" '"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(deck.get("brand", ""))} {i:02d}</title>'
            f'<link rel="stylesheet" href="{t["fonts_url"]}"><style>body{{margin:0}}#frame>*:not(.tx){{position:relative;z-index:1}}</style></head><body>{HANDMADE_DEFS if t.get("handmade") else ""}'
            f'<div id="frame" style="width:1080px;height:1350px;box-sizing:border-box;padding:60px 72px 56px;background:{c["bg"]};color:{c["fg"]};'
            f'font-family:{t["body"]};font-weight:{t.get("body_weight", 400)};display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;position:relative">{texture(t)}{hdr}{body}{ftr}{seal}</div>{overflow_js}</body></html>')


def dom_flags(chrome, path, timeout=40):
    import signal, tempfile, shutil
    prof = tempfile.mkdtemp(prefix="scout-chrome-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000", f"--user-data-dir={prof}",
                             "--window-size=1080,1350", "--dump-dom", "file://" + path], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out = ""
    shutil.rmtree(prof, ignore_errors=True)
    ov = re.search(r'data-overflow="(\w+)"', out or "")
    fo = re.search(r'data-fonts="(\w+)"', out or "")
    return (ov.group(1) if ov else "unknown"), (fo.group(1) if fo else "unknown")


def make_text_pdf(chrome, html_paths, out_dir, deck, timeout=180):
    """A PDF printed from the pages themselves: selectable, searchable text and clickable links."""
    import signal, tempfile, shutil
    sections, head = [], ""
    # one pre-rendered grain image per page instead of live SVG noise, which prints as huge rasters
    grain = os.path.abspath(os.path.join(out_dir, "grain.jpg"))
    if html_paths and not os.path.exists(grain):
        doc0 = open(html_paths[0], encoding="utf-8").read()
        layers = "".join(re.findall(r'<div class="tx"[^>]*?style="[^"]*"></div>', doc0))
        bg = re.search(r'id="frame" style="[^"]*background:([^;"]+)', doc0)
        gh = os.path.abspath(os.path.join(out_dir, "grain.html"))
        open(gh, "w").write(f'<!doctype html><html><body style="margin:0"><div style="position:relative;width:1080px;height:1350px;overflow:hidden;background:{bg.group(1) if bg else "#1F4D53"}">{layers}</div></body></html>')
        gp = grain[:-4] + ".png"
        if capture.screenshot(chrome, "file://" + gh, gp, 1080, 1350, 60, 4000) == "ok":
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "78", gp, "--out", grain], capture_output=True)
    for hp in html_paths:
        doc = open(hp, encoding="utf-8").read()
        if os.path.exists(grain):
            doc = re.sub(r'<div class="tx"[^>]*?style="[^"]*"></div>', "", doc)
            doc = re.sub(r'(<div id="frame" style="[^"]*">)', lambda m: m.group(1) + f'<img class="grain" src="file://{grain}" style="position:absolute;inset:0;width:1080px;height:1350px;z-index:0">', doc, count=1)
        doc = re.sub(r'filter:[^;"]*;?', "", doc).replace('filter="url(#rough)"', "")  # CSS filters print as full-page rasters

        def jpeg(m):  # big PNG screenshots go in as JPEG
            src = m.group(1)
            if not src.lower().endswith(".png") or not os.path.exists(src):
                return m.group(0)
            dst = os.path.abspath(os.path.join(out_dir, "print-" + hashlib.sha1(src.encode()).hexdigest()[:10] + ".jpg"))
            if not os.path.exists(dst):
                subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", "1600", src, "--out", dst], capture_output=True)
            return f'src="file://{dst}"' if os.path.exists(dst) else m.group(0)
        doc = re.sub(r'src="file://([^"]+)"', jpeg, doc)
        doc = doc.replace("#frame>*:not(.tx)", "#frame>*:not(.tx):not(.grain)")
        if "text-shadow" in doc:  # stacked shadows print as extra copies of the words, so they go in as one transparent picture
            sp = os.path.abspath(os.path.join(out_dir, "shadow-" + os.path.basename(hp)[:-5] + ".png"))
            sd = os.path.abspath(os.path.join(out_dir, "shadow.html"))
            hide = ("<style>html,body,#frame{background:transparent!important}#frame *{color:transparent!important;background:transparent!important;"
                    "border-color:transparent!important;box-shadow:none!important;-webkit-text-stroke:0!important}"
                    "#frame img,#frame svg,#frame .tx{visibility:hidden!important}</style>")
            open(sd, "w", encoding="utf-8").write(doc.replace("</head>", hide + "</head>", 1))
            if capture.screenshot(chrome, "file://" + sd, sp, 1080, 1350, 60, 4000, ["--default-background-color=00000000"]) == "ok":
                doc = re.sub(r'text-shadow:[^;"]*;?', "", doc)
                doc = re.sub(r'(<div id="frame" style="[^"]*">(?:<img class="grain"[^>]*>)?)', lambda m: m.group(1) + f'<img class="grain" src="file://{sp}" style="position:absolute;inset:0;width:1080px;height:1350px;z-index:0">', doc, count=1)
        if not head:
            m = re.search(r"<head>(.*?)</head>", doc, re.S)
            head = re.sub(r"<title>.*?</title>", "", m.group(1), flags=re.S) if m else ""
        body = re.search(r"<body>(.*)</body>", doc, re.S).group(1)
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        sections.append(f'<section style="width:1080px;height:1350px;break-after:page;overflow:hidden;position:relative">{body}</section>')
    ed = os.path.abspath(os.path.join(out_dir, "edition-text.html"))
    open(ed, "w").write(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(deck.get("brand", ""))} {html.escape(deck.get("date", ""))}</title>{head}'
                        '<style>@page{size:1080px 1350px;margin:0}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}section:last-child{break-after:auto}</style></head><body>'
                        + "".join(sections) + "</body></html>")
    pdf = os.path.join(out_dir, "edition.pdf")
    prof = tempfile.mkdtemp(prefix="scout-chrome-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                             "--virtual-time-budget=9000", f"--print-to-pdf={pdf}", "file://" + ed],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    shutil.rmtree(prof, ignore_errors=True)
    return pdf if os.path.exists(pdf) else None


def make_pdf(chrome, png_paths, out_dir, deck, timeout=120):
    """One page per frame, built from the rendered PNGs so the grain stays exact and the file stays small."""
    import signal, tempfile, shutil
    pages = []
    for png in png_paths:
        src = png
        jpg = png[:-4] + ".pdf.jpg"
        if shutil.which("sips") and subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88", png, "--out", jpg],
                                                    capture_output=True).returncode == 0:
            src = jpg
        pages.append(f'<section style="width:1080px;height:1350px;break-after:page"><img src="file://{os.path.abspath(src)}" style="display:block;width:1080px;height:1350px"></section>')
    ed = os.path.abspath(os.path.join(out_dir, "edition.html"))
    open(ed, "w").write(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(deck.get("brand", ""))} edition</title>'
                        '<style>@page{size:1080px 1350px;margin:0}body{margin:0}section:last-child{break-after:auto}</style></head><body>'
                        + "".join(pages) + "</body></html>")
    pdf = os.path.join(out_dir, "edition.pdf")
    prof = tempfile.mkdtemp(prefix="scout-chrome-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                             "--virtual-time-budget=6000", f"--print-to-pdf={pdf}", "file://" + ed],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    shutil.rmtree(prof, ignore_errors=True)
    for png in png_paths:
        if os.path.exists(png[:-4] + ".pdf.jpg"):
            os.remove(png[:-4] + ".pdf.jpg")
    return pdf if os.path.exists(pdf) and os.path.getsize(pdf) > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slides")
    ap.add_argument("audit")
    ap.add_argument("out_dir")
    ap.add_argument("--captures")
    ap.add_argument("--data", action="append", default=[])
    a = ap.parse_args()
    deck = json.load(open(a.slides))
    audit, data = copycheck.load_data(a.audit, a.data)
    gate_open = audit.get("radar_gate", {}).get("open", False)
    problems, _ = copycheck.check(deck, data, gate_open)
    if problems:
        for p in problems:
            print("FAIL", p)
        sys.exit(f"copy check failed with {len(problems)} problem(s); nothing rendered")
    caps = {}
    if a.captures:
        caps = {it["id"]: it for it in json.load(open(a.captures)).get("items", [])}
    th = deck.get("theme", {})
    theme = dict(THEMES.get(th, THEME)) if isinstance(th, str) else dict(THEMES.get(th.get("base", "scout"), THEME), **th)
    ctx = Ctx(theme, data, caps, deck)
    os.makedirs(a.out_dir, exist_ok=True)
    chrome = capture.find_chrome()
    slides = deck["slides"]
    report = []
    for i, s in enumerate(slides, 1):
        name = f"{i:02d}-{s.get('id', s['kind'])}"
        hp = os.path.abspath(os.path.join(a.out_dir, name + ".html"))
        open(hp, "w").write(page(s, i, len(slides), ctx, deck))
        row = {"slide": i, "html": hp}
        if chrome:
            png = os.path.join(a.out_dir, name + ".png")
            row["png"] = capture.screenshot(chrome, "file://" + hp, png, 1080, 1350, 60, 8000) == "ok" and png
            row["overflow"], row["fonts"] = dom_flags(chrome, hp)
        else:
            row["png"], row["overflow"], row["fonts"] = None, "unchecked", "unchecked"
        report.append(row)
        print(f"{name:<22} png={'ok' if row['png'] else 'no'} overflow={row['overflow']} fonts={row['fonts']}")
    if chrome and deck.get("pdf") == "text":
        pdf = make_text_pdf(chrome, [r["html"] for r in report], a.out_dir, deck)
    else:
        pdf = make_pdf(chrome, [r["png"] for r in report if r.get("png")], a.out_dir, deck) if chrome else None
    print(f"edition.pdf {'ok' if pdf else 'not made'}")
    json.dump({"slides": report, "pdf": pdf, "radar_gate": audit.get("radar_gate"), "browser": chrome},
              open(os.path.join(a.out_dir, "render.json"), "w"), indent=1)
    bad = [r["slide"] for r in report if r["overflow"] == "yes"]
    if bad:
        sys.exit(f"overflow on slide(s) {bad}")


if __name__ == "__main__":
    main()
