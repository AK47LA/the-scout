"""The Scout as a short news show: narrated beats with motion, real evidence on screen, labelled illustration.

Usage: python3 show.py SHOW.json OUT_DIR [--reuse]
SHOW.json: {"desk", "date", "segment", "voice": {voice_id, model_id}, "music": {"prompt", "volume"} | null,
            "ticker": ["HEADLINE", ...], "beats": [{"id", "scene", "vo", "pad", "min", "untraced_ok", ...scene props}]}
Scenes: sting, clip, evidence, decide, bars, timeline, card. Each beat lasts as long as its line plus a pad.
Every frame is HTML in the kaiju theme, rendered frame by frame through cdp.py, so motion is exact. Captures keep
their source on screen; Higgsfield clips are always tagged ILLUSTRATION. Numbers in lines and on screen go through
the same copy check as editions. Writes OUT_DIR/show.mp4 and OUT_DIR/show-receipt.json.
"""
import hashlib, html, json, os, shutil, struct, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp, copycheck, media, render, signals  # noqa: E402

W, H, FPS = 1080, 1350, 30
PAGE = {"w": W, "h": H, "top": 0}  # the output canvas; a taller page (9:16 for Reels) centres the 4:5 frame in it
T = render.KAIJU
INK, PAPER, CREAM, RED, TEAL = T["navy"], T["paper"], T["ice"], T["amber"], T["deep"]
E = html.escape

BASE_CSS = f"""
body{{margin:0;background:{TEAL}}}
#f{{width:{W}px;height:{H}px;position:relative;overflow:hidden;background:{TEAL};color:{CREAM};font-family:{T['body']};font-weight:500}}
#f>*:not(.tx){{position:absolute}}
.tx{{inset:-28px !important;animation:jit .5s steps(1) infinite}}
.mono{{font-family:{T['mono']};letter-spacing:.12em}}
.disp{{font-family:{T['display']};font-weight:400;line-height:1.02;letter-spacing:-.01em}}
.chip{{display:inline-block;font-family:{T['mono']};font-weight:700;letter-spacing:.16em;padding:8px 14px;border:3px solid currentColor;border-radius:3px;filter:url(#rough)}}
.card{{background:{PAPER};color:{INK};box-shadow:9px 9px 0 {INK};border-radius:2px}}
@keyframes jit{{0%{{transform:translate(0,0)}}25%{{transform:translate(-11px,7px)}}50%{{transform:translate(8px,-9px)}}75%{{transform:translate(-5px,-4px)}}}}
@keyframes rise{{0%{{transform:translateY(90px);opacity:0}}70%{{transform:translateY(-6px);opacity:1}}100%{{transform:translateY(0);opacity:1}}}}
@keyframes slam{{0%{{transform:scale(2.4) rotate(-14deg);opacity:0}}60%{{transform:scale(.94) rotate(-6deg);opacity:1}}100%{{transform:scale(1) rotate(-6deg);opacity:1}}}}
@keyframes drop{{0%{{transform:translateY(-120px) rotate(-6deg);opacity:0}}100%{{transform:translateY(0) rotate(-1.4deg);opacity:1}}}}
@keyframes slidein{{0%{{transform:translateX(-110%)}}100%{{transform:translateX(0)}}}}
@keyframes pop{{0%{{transform:scale(.4);opacity:0}}70%{{transform:scale(1.06);opacity:1}}100%{{transform:scale(1);opacity:1}}}}
@keyframes fade{{0%{{opacity:0}}100%{{opacity:1}}}}
@keyframes wipe{{0%{{transform:translateX(0)}}100%{{transform:translateX(-102%)}}}}
@keyframes crawl{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:.15}}}}
@keyframes shake{{0%,100%{{transform:translate(0,0)}}20%{{transform:translate(-9px,5px)}}40%{{transform:translate(7px,-6px)}}60%{{transform:translate(-5px,-3px)}}80%{{transform:translate(4px,4px)}}}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
@keyframes grow{{0%{{transform:scaleX(0)}}100%{{transform:scaleX(1)}}}}
@keyframes growy{{0%{{transform:scaleY(0)}}100%{{transform:scaleY(1)}}}}
@keyframes kb{{0%{{transform:scale(1)}}100%{{transform:scale(var(--z,1.14))}}}}
"""

# Counters and clip time are set per frame from the seek time.
SEEK_JS = """<script>
window.__ready = new Promise(r => { const v = document.querySelector('video'); if (!v) return r(1);
  if (v.readyState >= 2) return r(1); v.addEventListener('loadeddata', () => r(1), {once: true}); v.load(); });
window.onSeek = t => {
  for (const el of document.querySelectorAll('[data-to]')) {
    const at = +el.dataset.at, len = +el.dataset.len, to = +el.dataset.to;
    const p = Math.max(0, Math.min(1, (t - at) / len)), e = 1 - Math.pow(1 - p, 3);
    el.textContent = (el.dataset.pre || '') + Math.round(to * e).toLocaleString('en-US') + (el.dataset.post || '');
  }
  for (const el of document.querySelectorAll('[data-step]')) {
    el.textContent = Math.max(0, Math.min(+el.dataset.max, Math.floor((t - +el.dataset.at) / +el.dataset.step) + 1)).toString();
  }
  for (const el of document.querySelectorAll('[data-caps]')) {
    const caps = JSON.parse(el.dataset.caps); let cur = '';
    for (const c of caps) if (t >= c[0]) cur = c[1];
    el.textContent = cur; el.style.visibility = cur ? 'visible' : 'hidden';
  }
  const v = document.querySelector('video');
  if (!v) return null;
  const want = Math.min(v.duration - 0.05, (+v.dataset.from || 0) + t * +v.dataset.rate);
  if (Math.abs(v.currentTime - want) < 0.001) return null;
  return new Promise(r => { v.addEventListener('seeked', () => r(1), {once: true}); v.currentTime = want; });
};
</script>"""


def anim(name, dur, delay=0.0, ease="cubic-bezier(.2,.8,.2,1)", extra=""):
    return f"animation:{name} {dur:.3f}s {ease} {delay:.3f}s both{(' ' + extra) if extra else ''};"


def disp(size, dark=True):
    return render.display_style(T, dark, size)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def uri(path):
    return "file://" + urllib.request.pathname2url(os.path.abspath(path))


def shell(show, b, inner, start, total, first):
    """Desk header, ticker, source line, wipe-in transition and moving grain around a scene."""
    ticker = "   ·   ".join(E(x) for x in show.get("ticker", []))
    ticker = f"{ticker}   ·   {ticker}   ·   "
    head = (f'<div style="left:60px;right:60px;top:44px;display:flex;justify-content:space-between;align-items:center;z-index:5">'
            f'<div style="display:flex;align-items:center;gap:16px"><span style="font-weight:700;font-size:28px;letter-spacing:.16em">{E(show.get("brand", "THE SCOUT"))}</span>'
            f'<span class="chip" style="font-size:15px;color:{RED}"><span style="{anim("blink", 1.0, 0, "linear", "infinite")}">●</span> {E(show.get("desk", "NEWS DESK"))}</span></div>'
            f'<div style="display:flex;align-items:center;gap:16px"><span class="mono" style="font-size:17px;color:{T["muted_dark"]}">{E(show.get("date", ""))}</span>'
            f'<span class="chip" style="font-size:15px;color:{CREAM}">{E(b.get("segment", show.get("segment", "")))}</span></div></div>')
    src = (f'<div class="mono" style="left:60px;right:60px;bottom:96px;font-size:16px;letter-spacing:.06em;color:{T["muted_dark"]};z-index:5;{anim("fade", .5, .4)}">'
           f'{E(b.get("source", ""))}</div>') if b.get("source") else ""
    tick = (f'<div style="left:0;right:0;bottom:0;height:70px;background:{INK};display:flex;align-items:center;overflow:hidden;z-index:6">'
            f'<span class="mono" style="flex:none;height:70px;display:flex;align-items:center;padding:0 22px;background:{RED};color:{INK};font-weight:700;font-size:18px">LATEST</span>'
            f'<div style="flex:1;overflow:hidden;height:70px;display:flex;align-items:center"><div style="white-space:nowrap;font-family:{T["mono"]};font-size:20px;letter-spacing:.08em;color:{CREAM};padding-left:24px;'
            f'animation:crawl 90s linear {-start:.3f}s infinite">{ticker}</div></div></div>')
    caps = ""
    if b.get("_caps"):
        caps = (f'<div style="left:60px;right:60px;bottom:136px;z-index:7;display:flex;justify-content:center">'
                f'<span class="cap" data-caps="{E(json.dumps(b["_caps"]))}" style="background:{INK};color:{CREAM};font-size:38px;font-weight:700;line-height:1.25;'
                f'padding:12px 22px;text-align:center;max-width:900px;box-shadow:6px 6px 0 {RED}"></span></div>')
    wipe = "" if first else (f'<div style="inset:0;z-index:9;background:{RED};border-right:14px solid {INK};{anim("wipe", .34, 0, "cubic-bezier(.7,0,.3,1)")}"></div>')
    frame = f'<div id="f">{render.texture(T)}{head}{inner}{src}{caps}{tick}{wipe}</div>'
    if PAGE["h"] > H:  # poster margins above and below; captions stay clear of the app's bottom overlay
        frame = (f'<div style="position:relative;width:{PAGE["w"]}px;height:{PAGE["h"]}px;overflow:hidden;background:{TEAL}">{render.texture(T)}'
                 f'<div style="position:absolute;left:0;right:0;top:{PAGE["top"] - 18}px;height:6px;background:{RED};z-index:2"></div>'
                 f'<div style="position:absolute;left:0;top:{PAGE["top"]}px;z-index:1">{frame}</div>'
                 f'<div style="position:absolute;left:0;right:0;top:{PAGE["top"] + H + 12}px;height:6px;background:{RED};z-index:2"></div></div>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{T["fonts_url"]}"><style>{BASE_CSS}</style></head><body>'
            f'{render.HANDMADE_DEFS}{frame}{SEEK_JS}</body></html>')


# Scenes. Each returns the inner HTML for a beat of length d seconds.

def sc_sting(b, d):
    lines = "".join(f'<div class="disp" style="{disp(b.get("size", 132))}{anim("rise", .55, .35 + i * .22)}">{E(l)}</div>' for i, l in enumerate(b["lines"]))
    rays = (f'<div style="left:50%;top:46%;width:2400px;height:2400px;margin:-1200px 0 0 -1200px;z-index:0;opacity:.09;'
            f'background:repeating-conic-gradient({CREAM} 0 6deg, transparent 6deg 18deg);animation:spin 60s linear 0s infinite"></div>')
    stamp = (f'<div style="right:70px;top:{b.get("stamp_top", 860)}px;z-index:4;{anim("slam", .32, d * .52)}">'
             f'<span class="chip" style="font-size:40px;padding:14px 22px;border-width:6px;color:{RED};background:{TEAL}">{E(b.get("stamp", ""))}</span></div>') if b.get("stamp") else ""
    return (f'{rays}<div style="left:72px;right:72px;top:250px;z-index:3;{anim("shake", .3, d * .52 + .1, "linear")}">'
            f'<div class="mono" style="font-size:24px;color:{RED};font-weight:700;margin-bottom:26px;{anim("slidein", .4, .1)}">{E(b.get("kicker", ""))}</div>{lines}'
            f'<div style="font-size:34px;line-height:1.35;margin-top:34px;max-width:860px;{anim("fade", .6, .9)}">{E(b.get("sub", ""))}</div></div>{stamp}')


def sc_clip(b, d):
    dur = media.duration(b["video"])
    rate = min(1.0, (dur - 0.1) / max(d, 0.1))
    cap = (f'<div style="left:60px;right:60px;bottom:150px;z-index:4;{anim("slidein", .45, .5)}"><div class="card" style="padding:22px 26px;font-size:34px;line-height:1.3;font-weight:600">'
           f'{E(b["caption"])}</div></div>') if b.get("caption") else ""
    return (f'<div style="left:0;top:0;width:{W}px;height:{H}px;overflow:hidden;z-index:1"><video src="{uri(b["video"])}" data-rate="{rate:.4f}" muted preload="auto" '
            f'style="width:100%;height:100%;object-fit:cover;--z:1.12;{anim("kb", d, 0, "linear")}"></video></div>'
            f'<div style="left:0;right:0;top:0;height:200px;z-index:2;background:linear-gradient({TEAL}, transparent)"></div>'
            f'<div style="right:60px;top:126px;z-index:4"><span class="chip" style="font-size:15px;color:{CREAM};background:rgba(22,17,14,.55)">{E(b.get("tag", "ILLUSTRATION · HIGGSFIELD"))}</span></div>{cap}')


def sc_evidence(b, d):
    iw, ih = png_size(b["image"])
    cx, cy, cw, ch = b.get("crop", [0, 0, iw, ih])
    fw, fh = 936, b.get("frame_h", 700)
    s = max(fw / cw, fh / ch)
    fx, fy, fwid, fhei = b.get("focus", [cx, cy, cw, ch])
    bx, by, bw, bh = (fx - cx) * s, (fy - cy) * s, fwid * s, fhei * s
    ox, oy = bx + bw / 2, by + bh / 2
    per = 2 * (bw + bh)
    img = (f'<div style="position:absolute;left:0;top:0;width:{fw}px;height:{fh}px;transform-origin:{ox:.0f}px {oy:.0f}px;--z:{b.get("zoom", 1.16)};{anim("kb", d, 0, "linear")}">'
           f'<img src="{uri(b["image"])}" style="position:absolute;left:{-cx * s:.1f}px;top:{-cy * s:.1f}px;width:{iw * s:.1f}px;filter:{T["image_filter"]}">'
           f'<svg width="{fw}" height="{fh}" style="position:absolute;left:0;top:0;overflow:visible"><rect x="{bx - 10:.0f}" y="{by - 10:.0f}" width="{bw + 20:.0f}" height="{bh + 20:.0f}" rx="6" '
           f'fill="none" stroke="{RED}" stroke-width="8" filter="url(#rough)" stroke-dasharray="{per + 80:.0f}" stroke-dashoffset="{per + 80:.0f}" '
           f'style="animation:draw .8s ease-out {b.get("box_at", .9):.2f}s both"></rect></svg></div>')
    card = (f'<div style="left:72px;top:{b.get("top", 210)}px;z-index:2;{anim("drop", .5, .05)}"><div class="card" style="border:10px solid {PAPER};padding:0">'
            f'<div style="position:relative;width:{fw}px;height:{fh}px;overflow:hidden;background:{b.get("frame_bg", "#fff")}">{img}</div></div>'
            f'<span class="chip" style="position:absolute;right:-10px;top:-26px;font-size:15px;background:{INK};color:{CREAM};border-color:{INK}">{E(b.get("tag", "CAPTURE"))}</span></div>')
    lower = (f'<div style="left:0;top:{b.get("top", 210) + fh + 64}px;z-index:3;{anim("slidein", .45, 1.0)}">'
             f'<div style="display:flex;flex-direction:column;align-items:flex-start;gap:0;padding-left:72px">'
             f'<span class="mono" style="background:{RED};color:{INK};font-weight:700;font-size:20px;padding:10px 18px">{E(b.get("kicker", ""))}</span>'
             f'<span style="background:{INK};color:{CREAM};font-size:40px;font-weight:700;line-height:1.2;padding:14px 22px;max-width:900px">{E(b.get("line", ""))}</span></div></div>')
    return card + lower


def sc_decide(b, d):
    qs = b["cards"]
    step = b.get("step", .62)
    n = max(1, int((d - 1.2) / step))
    cards = ""
    for k in range(n):
        q, a = qs[k % len(qs)]
        at = .9 + k * step
        cards += (f'<div class="card" style="position:absolute;left:0;top:0;width:400px;height:250px;padding:26px;box-sizing:border-box;'
                  f'animation:dcard {step:.3f}s cubic-bezier(.3,.7,.2,1) {at:.3f}s both"><div style="font-size:34px;font-weight:700;line-height:1.15">{E(q)}</div>'
                  f'<span class="chip" style="position:absolute;right:22px;bottom:20px;font-size:34px;border-width:5px;color:{RED};animation:dstamp {step:.3f}s linear {at:.3f}s both">{E(a)}</span></div>')
    css = (f'<style>@keyframes dcard{{0%{{transform:translateX(560px) rotate(6deg);opacity:0}}22%{{transform:translateX(0) rotate(-1deg);opacity:1}}'
           f'78%{{transform:translateX(0) rotate(-1deg);opacity:1}}100%{{transform:translate(-60px,260px) rotate(-14deg);opacity:0}}}}'
           f'@keyframes dstamp{{0%,34%{{transform:scale(2.2) rotate(-12deg);opacity:0}}44%{{transform:scale(1) rotate(-8deg);opacity:1}}100%{{transform:scale(1) rotate(-8deg);opacity:1}}}}'
           f'@keyframes dots{{0%,100%{{transform:translateY(0);opacity:.35}}50%{{transform:translateY(-12px);opacity:1}}}}</style>')
    dots = "".join(f'<span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:{INK};margin-right:12px;'
                   f'animation:dots 1.1s ease-in-out {i * .18:.2f}s infinite"></span>' for i in range(3))
    left = (f'<div style="left:72px;top:230px;width:420px;z-index:2;{anim("fade", .4, .2)}"><span class="chip" style="font-size:20px;color:{CREAM}">BIG MODEL</span>'
            f'<div class="card" style="margin-top:28px;padding:28px;font-size:34px;font-weight:700;line-height:1.2">{E(b.get("question", ""))}<div style="margin-top:26px">{dots}</div></div>'
            f'<div class="mono" style="margin-top:22px;font-size:20px;color:{T["muted_dark"]}">THINKING IT THROUGH</div>'
            f'<div class="mono" style="margin-top:40px;font-size:20px;color:{T["muted_dark"]}">DECISIONS MADE</div><div class="disp" style="{disp(140)}opacity:.5">0</div></div>')
    right = (f'<div style="left:566px;top:230px;width:440px;height:700px;z-index:3;{anim("fade", .4, .4)}"><span class="chip" style="font-size:20px;color:{RED}">DECISION MODEL</span>'
             f'<div style="position:absolute;left:0;top:80px"><div class="mono" style="font-size:20px;color:{T["muted_dark"]}">DECISIONS MADE</div>'
             f'<div class="disp" style="{disp(140)}" data-step="{step}" data-at=".9" data-max="{n}">0</div>'
             f'<div class="mono" style="font-size:22px;color:{CREAM};margin-top:6px">{E(b.get("speed", ""))}</div></div>'
             f'<div style="position:absolute;left:0;top:400px;width:400px;height:250px">{cards}</div></div>')
    return css + left + right


def sc_bars(b, d):
    rows = ""
    vmax = max(r["value"] for r in b["rows"])
    for i, r in enumerate(b["rows"]):
        at = .5 + i * .7
        w = 820 * r["value"] / vmax
        bh, gap, ns = b.get("bar_h", 120), b.get("row_gap", 60), b.get("num_size", 110)
        w = (b.get("bar_w", 820)) * r["value"] / vmax
        rows += (f'<div style="margin-top:{gap if i else 0}px"><div class="mono" style="font-size:22px;color:{T["muted_dark"]};margin-bottom:12px;{anim("fade", .3, at)}">{E(r["label"])}</div>'
                 f'<div style="display:flex;align-items:center;gap:26px"><div style="width:{w:.0f}px;height:{bh}px;background:{RED if r.get("hot") else CREAM};box-shadow:8px 8px 0 {INK};'
                 f'transform-origin:left;{anim("grow", 1.0, at, "cubic-bezier(.2,.9,.1,1)")}"></div>'
                 f'<div class="disp" style="{disp(ns)}{anim("fade", .2, at)}" data-to="{r["value"]}" data-at="{at}" data-len="1.0">0</div></div></div>')
    return (f'<div style="left:72px;right:72px;top:240px;z-index:3"><div class="mono" style="font-size:24px;color:{RED};font-weight:700;{anim("slidein", .4, .1)}">{E(b.get("kicker", ""))}</div>'
            f'<div class="disp" style="{disp(84)}margin:20px 0 70px;{anim("rise", .5, .2)}">{E(b.get("headline", ""))}</div>{rows}</div>')


def sc_timeline(b, d):
    ev = b["events"]
    n = len(ev)
    y0, gap = 250, b.get("gap", 168)
    line_len = gap * (n - 1)
    run = d * .62
    items = ""
    for i, e in enumerate(ev):
        at = .3 + run * i / max(1, n - 1)
        col = RED if e.get("kind") == "press" else CREAM
        tag = e.get("tag") or {"press": "PRESS", "backtest": "BACKTEST", "launch": "LAUNCH", "call": "CALL"}.get(e.get("kind"), "")
        items += (f'<div style="left:72px;top:{y0 + gap * i - 18}px;z-index:3;display:flex;gap:30px;align-items:flex-start;{anim("pop", .35, at)}">'
                  f'<div style="width:44px;height:44px;border-radius:50%;background:{col};border:5px solid {INK};flex:none;'
                  f'{"outline:3px dashed " + CREAM + ";outline-offset:6px;" if e.get("kind") == "backtest" else ""}"></div>'
                  f'<div><div style="display:flex;gap:16px;align-items:center"><span class="mono" style="font-size:22px;font-weight:700;color:{col}">{E(e["date"])}</span>'
                  f'{f"<span class=chip style=font-size:14px;color:{col}>{tag}</span>" if tag else ""}</div>'
                  f'<div style="font-size:36px;font-weight:700;line-height:1.2;margin-top:6px;max-width:820px">{E(e["title"])}</div></div></div>')
    line = (f'<div style="left:{72 + 22 - 3}px;top:{y0}px;width:6px;height:{line_len}px;background:{CREAM};transform-origin:top;z-index:2;'
            f'{anim("growy", run, .3, "linear")}"></div>')
    stamp_top = y0 + line_len + 80 if b.get("stamp_at") == "bottom" else y0 - 40
    stamp = (f'<div style="right:64px;top:{stamp_top}px;z-index:4;{anim("slam", .32, .3 + run + .35)}">'
             f'<span class="chip" style="font-size:30px;padding:14px 20px;border-width:6px;color:{RED};background:{TEAL}">{E(b.get("stamp", ""))}</span></div>') if b.get("stamp") else ""
    return line + items + stamp


def sc_card(b, d):
    words = b["headline"].split()
    hl = " ".join(f'<span style="display:inline-block;{anim("pop", .32, .35 + i * .11)}">{E(w)}</span>' for i, w in enumerate(words))
    stamp = (f'<div style="left:72px;top:250px;z-index:4;{anim("slam", .3, .1)}"><span class="chip" style="font-size:30px;border-width:5px;color:{RED}">{E(b.get("stamp", "MOVE"))}</span></div>')
    nxt = (f'<div style="left:0;right:0;bottom:290px;z-index:4;{anim("slidein", .45, max(.8, d - 2.4))}"><div style="margin-left:72px;display:inline-block;background:{CREAM};color:{INK};'
           f'font-family:{T["mono"]};font-weight:700;font-size:26px;letter-spacing:.12em;padding:18px 26px;box-shadow:8px 8px 0 {INK}">{E(b["next"])}</div></div>') if b.get("next") else ""
    return (f'{stamp}<div class="disp" style="left:72px;right:72px;top:360px;z-index:3;{disp(b.get("size", 96))}">{hl}</div>'
            f'<div style="left:72px;right:120px;top:{b.get("sub_top", 840)}px;font-size:34px;line-height:1.35;z-index:3;{anim("fade", .5, .35 + len(words) * .11 + .2)}">{E(b.get("sub", ""))}</div>{nxt}')


def media_box(b, d, w, h):
    """A video (real time from b["from"], or slowed to fit) or a cropped image with a slow push toward its focus."""
    if b.get("video"):
        dur = media.duration(b["video"])
        rate = 1.0 if b.get("realtime") else min(1.0, (dur - 0.1) / max(d, 0.1))
        return (f'<video src="{uri(b["video"])}" data-rate="{rate:.4f}" data-from="{b.get("from", 0)}" muted preload="auto" '
                f'style="position:absolute;inset:0;width:100%;height:100%;object-fit:{b.get("fit", "cover")};background:#000;--z:{b.get("zoom", 1.04)};{anim("kb", d, 0, "linear")}"></video>')
    iw, ih = png_size(b["image"])
    cx, cy, cw, ch = b.get("crop", [0, 0, iw, ih])
    sc = max(w / cw, h / ch)
    fx, fy, fwid, fhei = b.get("focus", [cx, cy, cw, ch])
    ox, oy = (fx - cx + fwid / 2) * sc, (fy - cy + fhei / 2) * sc
    return (f'<div style="position:absolute;left:0;top:0;width:{w}px;height:{h}px;transform-origin:{ox:.0f}px {oy:.0f}px;--z:{b.get("zoom", 1.1)};{anim("kb", d, 0, "linear")}">'
            f'<img src="{uri(b["image"])}" style="position:absolute;left:{-cx * sc:.1f}px;top:{-cy * sc:.1f}px;width:{iw * sc:.1f}px;filter:{T["image_filter"]}"></div>')


def sc_rundown(b, d):
    items = b["items"]
    step = (d * .72) / max(1, len(items))
    fs, pad = (44, 20) if len(items) <= 5 else (38, 13)  # six or more items: tighter, so the list stays clear of the captions
    rows = "".join(f'<div style="display:flex;gap:26px;align-items:center;padding:{pad}px 0;border-top:2px solid rgba(233,196,142,.25);{anim("rise", .45, .9 + i * step)}">'
                   f'<span class="chip" style="font-size:22px;color:{RED};flex:none">{i + 1:02d}</span><span style="font-size:{fs}px;font-weight:700;line-height:1.15">{E(it)}</span></div>'
                   for i, it in enumerate(items))
    return (f'<div style="left:72px;right:72px;top:210px;z-index:3"><div class="mono" style="font-size:24px;color:{RED};font-weight:700;{anim("slidein", .4, .1)}">{E(b.get("kicker", ""))}</div>'
            f'<div class="disp" style="{disp(b.get("size", 150))}margin:18px 0 40px;{anim("slam", .35, .3)}transform-origin:left">{E(b.get("title", ""))}</div>{rows}</div>')


def sc_bumper(b, d):
    band = (f'<div style="left:-40px;right:-40px;top:520px;height:300px;background:{RED};z-index:1;transform-origin:left;transform:rotate(-3deg);'
            f'{anim("grow", .42, .05, "cubic-bezier(.7,0,.2,1)")}"></div>')
    return (f'{band}<div style="left:72px;right:72px;top:420px;z-index:3"><span class="chip" style="font-size:24px;color:{CREAM};background:{INK};border-color:{INK};{anim("fade", .3, .2)}">{E(b.get("kicker", ""))}</span>'
            f'<div class="disp" style="{disp(b.get("size", 124))}margin-top:120px;{anim("slam", .32, .25)}transform-origin:left">{E(b["title"])}</div></div>')


def sc_tool(b, d):
    mh = b.get("media_h", 527)
    box = (f'<div style="left:72px;top:200px;z-index:2;{anim("drop", .5, .05)}"><div class="card" style="border:10px solid {PAPER};padding:0">'
           f'<div style="position:relative;width:936px;height:{mh}px;overflow:hidden;background:#000">{media_box(b, d, 936, mh)}</div></div>'
           f'<span class="chip" style="position:absolute;right:-10px;top:-26px;font-size:15px;background:{INK};color:{CREAM};border-color:{INK}">{E(b.get("tag", "DEMO FOOTAGE"))}</span></div>')
    stats = "".join(f'<span class="chip" style="font-size:20px;color:{RED if i == 0 else CREAM}">{E(x)}</span>' for i, x in enumerate(b.get("stats", [])))
    top = 200 + mh + 64
    tryline = (f'<div class="mono" style="margin-top:18px;font-size:20px;color:{T["muted_dark"]}">{E(b["try"])}</div>') if b.get("try") else ""
    info = (f'<div style="left:72px;right:72px;top:{top}px;z-index:3">'
            f'<div class="disp" style="{disp(b.get("name_size", 76))}{anim("rise", .45, .5)}">{E(b["name"])}</div>'
            f'<div style="font-size:34px;line-height:1.3;font-weight:600;margin-top:18px;max-width:920px;{anim("fade", .4, .8)}">{E(b.get("line", ""))}</div>'
            f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:22px;{anim("fade", .3, 1.1)}">{stats}</div>'
            f'{tryline}</div>')
    return box + info


def sc_bignum(b, d):
    rows = ""
    for i, st in enumerate(b["stats"]):
        at = .4 + i * 1.2
        rows += (f'<div style="margin-top:{50 if i else 0}px;{anim("fade", .3, at)}"><div class="disp" style="{disp(st.get("size", 200 if i == 0 else 120))}" '
                 f'data-to="{st["value"]}" data-at="{at}" data-len="1.2" data-pre="{E(st.get("pre", ""))}" data-post="{E(st.get("post", ""))}">0</div>'
                 f'<div style="font-size:36px;font-weight:700;line-height:1.25;margin-top:12px;max-width:900px">{E(st["label"])}</div></div>')
    return (f'<div style="left:72px;right:72px;top:220px;z-index:3"><div class="mono" style="font-size:24px;color:{RED};font-weight:700;margin-bottom:40px;{anim("slidein", .4, .1)}">'
            f'{E(b.get("kicker", ""))}</div>{rows}</div>')


def sc_post(b, d):
    mh = b.get("media_h", 470)
    box = (f'<div style="left:110px;top:300px;z-index:2;transform:rotate(-1.6deg);{anim("drop", .5, .15)}"><div class="card" style="border:10px solid {PAPER}">'
           f'<div style="position:relative;width:860px;height:{mh}px;overflow:hidden;background:#000">{media_box(b, d, 860, mh)}</div></div></div>') if (b.get("image") or b.get("video")) else ""
    if not box and b.get("post"):  # the post that sets up this idea, quoted with its counts
        q = b["post"]
        m = q.get("post_metrics") or {}
        box = (f'<div style="left:110px;top:300px;width:860px;height:{mh}px;z-index:2;transform:rotate(-1.6deg);{anim("drop", .5, .15)}"><div class="card" style="padding:36px 40px;height:100%;box-sizing:border-box">'
               f'<div class="mono" style="font-size:20px;color:#5b4a38">{E(q["handle"])} · {E(q["when"])}</div>'
               f'<div style="font-size:38px;font-weight:600;line-height:1.3;margin-top:20px">{E(q["post_text"])}</div>'
               f'<div class="mono" style="font-size:22px;margin-top:24px"><b>{fmt_n(m.get("likes"))}</b> LIKES · <b>{fmt_n(m.get("views"))}</b> VIEWS</div></div></div>')
    words = b["hook"].split()
    hook = " ".join(f'<span style="display:inline-block;{anim("pop", .3, .9 + i * .07)}">{E(w)}</span>' for i, w in enumerate(words))
    note = f'<span style="font-size:26px;font-weight:600;margin-left:10px">{E(b["note"])}</span>' if b.get("note") else ""
    plats = "".join(f'<span class="chip" style="font-size:18px;color:{CREAM}">{E(x)}</span>' for x in b.get("platforms", []))
    return (f'<div style="left:72px;right:72px;top:190px;z-index:4;display:flex;gap:18px;align-items:center">'
            f'<span class="mono" style="font-size:24px;font-weight:700;color:{CREAM};{anim("slidein", .4, .05)}">{E(b.get("kicker", ""))}</span>'
            f'<span class="chip" style="font-size:24px;border-width:4px;color:{RED};{anim("slam", .3, .2)}">{E(b.get("kind", ""))}</span></div>{box}'
            f'<div class="disp" style="left:72px;right:72px;top:{300 + mh + 70}px;z-index:3;{disp(b.get("hook_size", 54))}">{hook}</div>'
            f'<div style="left:72px;top:{b.get("plat_top", 1080)}px;z-index:3;display:flex;gap:12px;{anim("fade", .3, 1.2)}">{plats}'
            f'{note}</div>')


def fmt_n(v):
    v = int(v or 0)
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}K" if v >= 10_000 else f"{v:,}"


def sc_xpost(b, d):
    """A real post, quoted verbatim with its author, time, counts and link, read through the public API."""
    p = b["post"]
    text = p["post_text"]
    words = text.split()
    body = " ".join(E(w) for w in words)
    m = p.get("post_metrics") or {}
    counts = "".join(f'<span class="mono" style="font-size:22px;color:{INK}"><b style="font-weight:700">{fmt_n(m.get(k))}</b> {lab}</span>'
                     for k, lab in (("likes", "LIKES"), ("reposts", "REPOSTS"), ("views", "VIEWS")) if m.get(k) is not None)
    initial = E(p["name"][:1].upper())
    card = (f'<div style="left:72px;right:72px;top:{b.get("top", 230)}px;z-index:3;{anim("drop", .5, .05)}"><div class="card" style="padding:40px 44px">'
            f'<div style="display:flex;gap:22px;align-items:center"><div style="width:84px;height:84px;border-radius:50%;background:{TEAL};color:{CREAM};display:flex;'
            f'align-items:center;justify-content:center;font-family:{T["display"]};font-size:44px;flex:none">{initial}</div>'
            f'<div><div style="font-size:34px;font-weight:700;line-height:1.1">{E(p["name"])}</div><div class="mono" style="font-size:20px;color:#5b4a38;margin-top:6px">'
            f'{E(p["handle"])} · {E(p["when"])}</div></div></div>'
            f'<div style="font-size:{b.get("text_size", 40)}px;font-weight:600;line-height:1.3;margin-top:30px;{anim("fade", .4, .5)}">{body}</div>'
            f'<div style="display:flex;gap:34px;margin-top:32px;padding-top:22px;border-top:2px solid rgba(22,17,14,.2);{anim("fade", .3, .9)}">{counts}</div></div>'
            f'<span class="chip" style="position:absolute;right:-10px;top:-26px;font-size:15px;background:{INK};color:{CREAM};border-color:{INK}">{E(b.get("tag", "X POST"))}</span></div>')
    kick = (f'<div style="left:72px;top:{b.get("top", 230) - 76}px;z-index:4;{anim("slidein", .4, .05)}"><span class="mono" style="background:{RED};color:{INK};'
            f'font-weight:700;font-size:20px;padding:10px 18px">{E(b.get("kicker", ""))}</span></div>') if b.get("kicker") else ""
    return kick + card


SCENES = {"xpost": sc_xpost, "rundown": sc_rundown, "bumper": sc_bumper, "tool": sc_tool, "bignum": sc_bignum, "post": sc_post, "sting": sc_sting, "clip": sc_clip, "evidence": sc_evidence, "decide": sc_decide, "bars": sc_bars, "timeline": sc_timeline, "card": sc_card}


def voice_line(text, voice, key, cache):
    """The spoken line, plus per-character timings from ElevenLabs when there is a key (for captions)."""
    os.makedirs(cache, exist_ok=True)
    h = hashlib.sha1(json.dumps([text, voice], sort_keys=True).encode()).hexdigest()[:16]
    out, align = os.path.join(cache, f"{h}.mp3"), os.path.join(cache, f"{h}.align.json")
    if not os.path.exists(out):
        if key:
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}/with-timestamps?output_format=mp3_44100_128",
                data=json.dumps(dict({"text": text, "model_id": voice["model_id"]}, **({"voice_settings": voice["settings"]} if voice.get("settings") else {}))).encode(),
                headers={"xi-api-key": key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            import base64
            open(out, "wb").write(base64.b64decode(d["audio_base64"]))
            json.dump(d.get("alignment") or {}, open(align, "w"))
        else:
            media.tts_system(text, out)
    return out, (json.load(open(align)) if os.path.exists(align) else None)


def caption_chunks(align, offset, max_words=5):
    """Group words into short caption chunks, each with the time its first word is spoken."""
    if not align or not align.get("characters"):
        return []
    chars, starts = align["characters"], align["character_start_times_seconds"]
    words, cur, t0 = [], "", None
    for ch, st in zip(chars, starts):
        if ch.isspace():
            if cur:
                words.append((t0, cur))
            cur, t0 = "", None
        else:
            if not cur:
                t0 = st
            cur += ch
    if cur:
        words.append((t0, cur))
    groups, buf = [], []
    for t, w in words:  # break at sentence ends, at commas once a phrase has some length, or at the word cap
        buf.append((t, w))
        if len(buf) >= max_words + 1 or (w[-1] in ".?!" and len(buf) >= 2) or (w[-1] in ",:;" and len(buf) >= 3):
            groups.append(buf)
            buf = []
    if buf:
        groups.append(buf)
    merged = []
    for g in groups:  # never leave a one- or two-word scrap on screen
        if merged and (len(g) <= 2 or len(merged[-1]) <= 2) and len(merged[-1]) + len(g) <= max_words + 3:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    return [[round(g[0][0] + offset, 3), " ".join(x[1] for x in g)] for g in merged]


def eleven_audio(path, key, endpoint, body):
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/{endpoint}", data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=300) as r:
        open(path, "wb").write(r.read())
    return path


def music_bed(spec, seconds, key, cache):
    """A bed for the whole show: ElevenLabs music if the account has it, else a looped sound-effects bed, else none."""
    if not spec or not key:
        return None, "none"
    import time
    h = hashlib.sha1(json.dumps([spec, round(seconds)]).encode()).hexdigest()[:12]
    out, loop = os.path.join(cache, f"music-{h}.mp3"), os.path.join(cache, f"loopbed-{h}.mp3")
    if os.path.exists(out):
        return out, "elevenlabs music (cached)"
    why = "music API not tried"
    for attempt in range(5):  # the music service answers 429 "system busy" under load; wait and retry
        try:
            return eleven_audio(out, key, "music", {"prompt": spec["prompt"], "music_length_ms": int(min(300, seconds + 2) * 1000)}), "elevenlabs music"
        except urllib.error.HTTPError as e:
            why = f"music API refused ({e.code})"
            if e.code not in (429, 503):
                break
            time.sleep(20 * (attempt + 1))
    import glob
    earlier = sorted(glob.glob(os.path.join(cache, "music-*.mp3")), key=lambda f: -media.duration(f))
    if earlier:  # a real theme from an earlier render beats a short loop
        return earlier[0], why + "; reused an earlier theme from this edition"
    if os.path.exists(loop):
        return loop, why + "; sound-generation loop (cached)"
    try:
        return eleven_audio(loop, key, "sound-generation", {"text": spec["prompt"], "duration_seconds": 22, "prompt_influence": 0.35}), why + "; sound-generation loop"
    except urllib.error.HTTPError as e:
        return None, why + f"; sound-generation refused ({e.code})"


def sfx(name, prompt, seconds, key, cache):
    out = os.path.join(cache, f"sfx-{name}.mp3")
    if os.path.exists(out) or not key:
        return out if os.path.exists(out) else None
    try:
        return eleven_audio(out, key, "sound-generation", {"text": prompt, "duration_seconds": seconds, "prompt_influence": 0.6})
    except urllib.error.HTTPError:
        return None


def render_beat(chrome, html_doc, b, d, path_html, path_mp4):
    open(path_html, "w").write(html_doc)
    chrome.open(uri(path_html))
    chrome.js("window.__ready")
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), path_mp4], stdin=subprocess.PIPE)
    for i in range(round(d * FPS)):
        enc.stdin.write(chrome.frame(i / FPS))
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError(f"encode failed for {b['id']}")


def main():
    show_path, out = sys.argv[1], os.path.abspath(sys.argv[2])
    reuse = "--reuse" in sys.argv  # trust beat videos rendered before beat hashes existed
    base = os.path.dirname(os.path.abspath(show_path))
    show = json.load(open(show_path))
    for b in show["beats"]:
        for k in ("video", "image"):
            if b.get(k) and not os.path.isabs(b[k]):
                b[k] = os.path.normpath(os.path.join(base, b[k]))
    problems, _ = copycheck.check({"slides": show["beats"]}, {}, False)
    problems += [p for p in copycheck.check({"slides": [{"id": "ticker", "text": " ".join(show.get("ticker", [])),
                                                         "untraced_ok": show.get("ticker_untraced_ok", [])}]}, {}, False)[0]]
    if problems:
        for p in problems:
            print("FAIL", p)
        sys.exit("copy check failed; nothing rendered")
    os.makedirs(os.path.join(out, "beats"), exist_ok=True)
    cache = os.path.join(out, "audio")
    key = signals.key("elevenlabs")
    voice = show.get("voice") or {"voice_id": "IKne3meq5aSn9XLyUdCD", "model_id": "eleven_multilingual_v2"}

    lead = 0.25
    timeline, t = [], 0.0
    for b in show["beats"]:
        vo, align = voice_line(b["vo"], voice, key, cache) if b.get("vo") else (None, None)
        d = max(b.get("min", 2.0), (media.duration(vo) + lead + b.get("pad", 0.55)) if vo else 0)
        if show.get("captions", True):
            b["_caps"] = caption_chunks(align, lead)
        timeline.append({"beat": b, "vo": vo, "start": round(t, 3), "dur": round(d, 3)})
        t += d
    total = t
    print(f"{len(timeline)} beats, {total:.1f}s")

    if show.get("page"):
        PAGE.update(w=show["page"][0], h=show["page"][1], top=show.get("page_top", (show["page"][1] - H) // 2))
    with cdp.Chrome(PAGE["w"], PAGE["h"]) as chrome:
        for i, row in enumerate(timeline):
            b = row["beat"]
            p = os.path.join(out, "beats", f"{i:02d}-{b['id']}")
            doc = shell(show, b, SCENES[b["scene"]](b, row["dur"]), row["start"], total, i == 0)
            h = hashlib.sha1(f"{doc}|{row['dur']:.3f}|{FPS}".encode()).hexdigest()
            row["video"] = p + ".mp4"
            have = os.path.exists(p + ".hash") and open(p + ".hash").read() == h
            if os.path.exists(row["video"]) and (have or (reuse and not os.path.exists(p + ".hash"))):
                open(p + ".hash", "w").write(h)  # unchanged beat: keep its frames
                print(f"  {i:02d} {b['id']:<12} {row['dur']:5.2f}s  kept")
                continue
            render_beat(chrome, doc, b, row["dur"], p + ".html", row["video"])
            open(p + ".hash", "w").write(h)
            print(f"  {i:02d} {b['id']:<12} {row['dur']:5.2f}s")

    lst = os.path.join(out, "beats", "list.txt")
    open(lst, "w").write("".join(f"file '{r['video']}'\n" for r in timeline))
    silent = os.path.join(out, "beats", "silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)

    bed, bed_how = music_bed(show.get("music"), total, key, cache)
    whoosh = sfx("whoosh", "fast cinematic whoosh swipe transition, short and punchy", 1.0, key, cache)
    thud = sfx("stamp", "heavy rubber stamp slammed on a wooden desk, single thud", 0.8, key, cache)
    ins, filt, mix = ["-i", silent], [], []
    n = 1
    for r in timeline:
        if r["vo"]:
            ins += ["-i", r["vo"]]
            ms = int((r["start"] + lead) * 1000)
            filt.append(f"[{n}:a]aresample=44100,adelay={ms}|{ms},volume=1.0[v{n}]")
            mix.append(f"[v{n}]")
            n += 1
        if r["beat"].get("audio") and r["beat"].get("video"):
            ins += ["-ss", str(r["beat"].get("from", 0)), "-t", f'{r["dur"]:.2f}', "-i", r["beat"]["video"]]
            ms = int(r["start"] * 1000)
            filt.append(f"[{n}:a]aresample=44100,adelay={ms}|{ms},volume={r['beat'].get('audio_volume', 0.32)},afade=t=out:st={max(0, r['dur'] - 0.4):.2f}:d=0.4[c{n}]")
            mix.append(f"[c{n}]")
            n += 1
        if whoosh and r["start"] > 0:
            ins += ["-i", whoosh]
            ms = max(0, int((r["start"] - 0.12) * 1000))
            filt.append(f"[{n}:a]aresample=44100,adelay={ms}|{ms},volume=0.45[w{n}]")
            mix.append(f"[w{n}]")
            n += 1
        if thud and r["beat"]["scene"] in ("sting", "timeline", "card") and r["beat"].get("stamp"):
            at = {"sting": .52, "timeline": .62}.get(r["beat"]["scene"])
            off = r["start"] + (r["dur"] * at + (.3 + .35 if r["beat"]["scene"] == "timeline" else 0) if at else .1) + .1
            ins += ["-i", thud]
            ms = int(off * 1000)
            filt.append(f"[{n}:a]aresample=44100,adelay={ms}|{ms},volume=0.7[s{n}]")
            mix.append(f"[s{n}]")
            n += 1
    if bed:
        ins += ["-stream_loop", "-1", "-i", bed]
        vol = (show.get("music") or {}).get("volume", 0.16)
        filt.append(f"[{n}:a]aresample=44100,atrim=0:{total:.2f},volume={vol},afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.8):.2f}:d=1.8[bed]")
        mix.append("[bed]")
        n += 1
    filt.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:dropout_transition=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[a]")
    final = os.path.join(out, f'{show.get("name", "show")}.mp4')
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", final], check=True)
    parts, cur = [], None
    for r in timeline:
        name = r["beat"].get("part")
        if name and (not cur or cur["name"] != name):
            cur = {"name": name, "start": r["start"], "end": r["start"] + r["dur"]}
            parts.append(cur)
        elif cur and (not name or name == cur["name"]):
            cur["end"] = r["start"] + r["dur"]
    if len(parts) > 1:
        os.makedirs(os.path.join(out, "parts"), exist_ok=True)
        for i, pt in enumerate(parts):
            pt["file"] = os.path.join(out, "parts", f"{show.get('name', 'show')} - {i + 1:02d} {pt['name']}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{pt['start']:.3f}", "-t", f"{pt['end'] - pt['start']:.3f}", "-i", final,
                            "-c:v", "libx264", "-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                            "-af", "afade=t=in:d=0.05", "-movflags", "+faststart", pt["file"]], check=True)
    receipt = {"show": os.path.abspath(show_path), "parts": parts, "seconds": round(total, 2), "fps": FPS, "size": [PAGE["w"], PAGE["h"]],
               "voice": "elevenlabs" if key else "system preview", "music": bed_how, "sfx": bool(whoosh or thud),
               "beats": [{"id": r["beat"]["id"], "scene": r["beat"]["scene"], "start": r["start"], "dur": r["dur"],
                          "evidence": r["beat"].get("image"), "illustration": r["beat"].get("video")} for r in timeline]}
    json.dump(receipt, open(os.path.join(out, "show-receipt.json"), "w"), indent=1)
    print(f"{os.path.basename(final)} {total:.1f}s  music: {bed_how}  -> {final}")


if __name__ == "__main__":
    main()
