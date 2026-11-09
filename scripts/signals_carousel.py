"""The weekly "Signals I'm watching" carousel, in the owner's posted Instagram format (3:4, 1080x1440).

  python3 signals_carousel.py DECK.json OUT_DIR

DECK.json:
  {"handle": "@NAME", "lanes": "ENTERTAINMENT · CULTURE · EMERGING TECH",
   "cover": {"lines": ["Signals {s1} I'm", "{s2} watching as", "an *entertainment*", "*and tech* {s3}", "strategist."],
             "stickers": {"s1": "img.png", ...}, "person": "cutout.png", "corner": "img.png"},
   "slides": [{"lane": "CULTURE", "headline": "Lore beat slop", "aside": "the word of the year is \\"lore\\"",
               "media": [{"path": "a.png", "label": "SOURCE · DATE", "fit": "cover", "pos": "center"}] or
                        [{"list": ["1. Buddy", "2. NeeDoh"], "label": "..."}],
               "body": "What happened, plain words.", "take": "[YOUR TAKE: ...]"}]}
Words in *asterisks* and every "aside" are set in the gradient italic. Stdlib only, Python 3.9 compatible.
Reference: the owner's posted carousels of 23 and 30 Oct 2026 (dark ink ground, serif headline with a gradient
italic aside in brackets, one or two labelled media cards, one plain paragraph, the handle at the foot).
"""
import html, json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402

W, H = 1080, 1440
FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600"
         "&family=Geist+Mono:wght@400;500;600&display=swap")
GRAD = "linear-gradient(100deg,#7FD1C2 0%,#E2BE72 50%,#D08FD0 100%)"
CSS = f"""
*{{box-sizing:border-box}}html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden}}
body{{background:radial-gradient(120% 60% at 0% 0%,#14303A 0%,rgba(20,48,58,0) 55%),
radial-gradient(120% 50% at 100% 100%,#2A1C3A 0%,rgba(42,28,58,0) 55%),#0B1020;color:#EEF1F5;
font-family:'Geist','Helvetica Neue',sans-serif;-webkit-font-smoothing:antialiased}}
.f{{position:absolute;inset:0;padding:96px 92px 70px;display:flex;flex-direction:column}}
.lane{{font-family:'Geist Mono',monospace;font-size:19px;font-weight:500;letter-spacing:.22em;color:#E2BE72}}
.hl{{font-family:'Instrument Serif',Georgia,serif;font-weight:400;font-size:100px;line-height:1.02;letter-spacing:-.01em;margin:22px 0 0}}
.lit{{font-style:italic;background:{GRAD};-webkit-background-clip:text;background-clip:text;color:transparent;padding:0 .05em 0 .02em}}
.media{{display:flex;gap:22px;justify-content:center;margin-top:58px}}
.card{{display:flex;flex-direction:column;gap:12px}}
.lab{{font-family:'Geist Mono',monospace;font-size:15px;letter-spacing:.14em;color:#A9B3C6;text-transform:uppercase}}
.img{{border-radius:8px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.5);background:#141A2B}}
.img img{{display:block;width:100%;height:100%}}
.list{{border-radius:8px;background:#F4F1EA;color:#16110E;padding:30px 38px;box-shadow:0 24px 60px rgba(0,0,0,.5);
font-size:31px;line-height:1.55;font-weight:500}}
.body{{margin-top:auto;padding-top:34px;font-size:33px;line-height:1.45;color:#E6EAF1}}
.take{{margin-top:16px;font-size:30px;line-height:1.4;color:#E2BE72}}
.take.own{{font-size:30px;line-height:1.42;color:#EEF1F5}}
.body.small{{font-size:26px;color:#B8C1D1}}
.foot{{margin-top:34px;padding-top:18px;border-top:1px solid rgba(238,241,245,.12);font-family:'Geist Mono',monospace;font-size:15px;letter-spacing:.14em;color:#8A94A8}}
.cover .hl{{font-size:118px;line-height:1.08;margin-top:40px}}
.stk{{display:inline-block;vertical-align:middle;height:112px;margin:0 12px;border-radius:14px;transform:rotate(-3deg);filter:drop-shadow(0 10px 18px rgba(0,0,0,.55))}}
"""


def lit(text):
    out = html.escape(text)
    return re.sub(r"[*]([^*]+)[*]", r'<span class="lit">\1</span>', out)


def uri(p):
    return "file://" + os.path.abspath(p)


def media_html(media):
    if not media:
        return ""
    two = len(media) > 1
    w = 418 if two else 760
    h = 400 if two else 470
    cards = []
    for m in media:
        if m.get("list"):
            inner = f'<div class="list" style="width:{w}px">{"<br>".join(html.escape(x) for x in m["list"])}</div>'
        else:
            inner = (f'<div class="img" style="width:{w}px;height:{m.get("h", h)}px"><img src="{uri(m["path"])}" '
                     f'style="object-fit:{m.get("fit", "cover")};object-position:{m.get("pos", "center")}"></div>')
        cards.append(f'<div class="card"><span class="lab">{html.escape(m.get("label", ""))}</span>{inner}</div>')
    return f'<div class="media">{"".join(cards)}</div>'


def slide_html(s, handle):
    hl = lit(s["headline"]) + (f' <span class="lit">({html.escape(s["aside"])})</span>' if s.get("aside") else "")
    slot = s.get("take", "").startswith("[")  # an empty slot is marked in brass; the owner's own words read as body text
    take = (f'<div class="take{"" if slot else " own"}">{html.escape(s["take"])}</div>') if s.get("take") else ""
    return (f'<div class="f"><span class="lane">{html.escape(s["lane"])}</span><h1 class="hl">{hl}</h1>'
            f'{media_html(s.get("media"))}<div class="body{" small" if s.get("take") and not slot else ""}">{html.escape(s["body"])}</div>{take}'
            f'<div class="foot">{html.escape(handle)}</div></div>')


def cover_html(c, lanes):
    st = c.get("stickers", {})

    def line(l):
        parts = re.split(r"\{(\w+)\}", l)
        return "".join(f'<img class="stk" src="{uri(st[p])}">' if i % 2 else lit(p) for i, p in enumerate(parts))
    lines = "<br>".join(line(l) for l in c["lines"])
    person = (f'<img src="{uri(c["person"])}" style="position:absolute;right:0;bottom:0;height:{c.get("person_h", 660)}px">'
              if c.get("person") else "")
    corner = (f'<img src="{uri(c["corner"])}" style="position:absolute;left:92px;bottom:96px;height:{c.get("corner_h", 260)}px;'
              f'filter:drop-shadow(0 14px 24px rgba(0,0,0,.55))">' if c.get("corner") else "")
    return f'<div class="f cover"><span class="lane">{html.escape(lanes)}</span><h1 class="hl">{lines}</h1></div>{corner}{person}'


RECTS_JS = ("<script>document.fonts.ready.then(function(){var r=[].map.call(document.querySelectorAll('.img'),function(e){"
            "var b=e.getBoundingClientRect();return [Math.round(b.left),Math.round(b.top),Math.round(b.width),Math.round(b.height)]});"
            "document.body.setAttribute('data-rects',JSON.stringify(r));});</script>")


def page(inner):
    return (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{FONTS}">'
            f'<style>{CSS}</style></head><body>{inner}{RECTS_JS}</body></html>')


def card_rects(chrome, html_path):
    """Where each media card sits on the rendered slide, read from the page itself."""
    prof = tempfile.mkdtemp(prefix="scout-chrome-")
    try:
        out = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                              f"--window-size={W},{H}", "--virtual-time-budget=6000", f"--user-data-dir={prof}", "--dump-dom",
                              "file://" + os.path.abspath(html_path)], capture_output=True, text=True, timeout=90).stdout
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'data-rects="([^"]*)"', out)
    return json.loads(html.unescape(m.group(1))) if m else []


def ff(args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y"] + args, check=True)


def motion_clip(m, w, h, dur, out):
    """A moving card: the source's own footage when there is a clip, a crossfade of its photos, or a slow push on a still."""
    fps = 30
    w2, h2 = w - w % 2, h - h % 2
    cover = f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2}:(in_w-{w2})/2:(in_h-{h2})*{m.get('ypos', 0.5)}"
    if m.get("video"):
        ff(["-ss", str(m.get("start", 0)), "-t", str(dur), "-stream_loop", "-1", "-i", m["video"], "-an",
            "-vf", f"{cover},fps={fps},setsar=1", "-t", str(dur), "-pix_fmt", "yuv420p", out])
        return
    frames = m.get("frames") or [m["path"]]
    n = len(frames)
    seg = dur / n + (0.6 if n > 1 else 0)
    parts = []
    for i, f in enumerate(frames):
        pp = out + f".{i}.mp4"
        big = f"scale={w2 * 2}:{h2 * 2}:force_original_aspect_ratio=increase,crop={w2 * 2}:{h2 * 2}"
        zoom = f"zoompan=z='1+0.07*on/{int(seg * fps)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(seg * fps)}:s={w2}x{h2}:fps={fps}"
        ff(["-loop", "1", "-t", str(seg), "-i", f, "-vf", f"{big},{zoom},setsar=1", "-t", str(seg), "-pix_fmt", "yuv420p", pp])
        parts.append(pp)
    if n == 1:
        os.replace(parts[0], out)
        return
    args, chain, last, off = [], "", "[0:v]", 0.0
    for p in parts:
        args += ["-i", p]
    for i in range(1, n):
        off += seg - 0.6
        chain += f"{last}[{i}:v]xfade=transition=fade:duration=0.6:offset={off:.2f}[x{i}];"
        last = f"[x{i}]"
    ff(args + ["-filter_complex", chain.rstrip(";"), "-map", last, "-t", str(dur), "-pix_fmt", "yuv420p", out])
    for p in parts:
        os.remove(p)


def slide_video(png, rects, media, out, dur=9.0):
    """The posted format moves: the slide stays put and each media card plays its footage, cut to rounded corners."""
    from_media = [m for m in (media or []) if not m.get("list")]
    tmp = tempfile.mkdtemp(prefix="scout-slide-")
    try:
        args = ["-loop", "1", "-t", str(dur), "-i", png]
        chain, last, k = "", "[0:v]", 1
        for (x, y, w, h), m in zip(rects, from_media):
            w2, h2 = w - w % 2, h - h % 2
            clip = os.path.join(tmp, f"c{k}.mp4")
            motion_clip(m, w2, h2, dur, clip)
            mask = os.path.join(tmp, f"m{k}.png")
            ff(["-f", "lavfi", "-i", f"color=black:s={w2}x{h2}", "-vf",
                f"format=gray,geq=lum='if(gt(abs(X-{w2}/2)-({w2}/2-8),0)*gt(abs(Y-{h2}/2)-({h2}/2-8),0)*gt(hypot(abs(X-{w2}/2)-({w2}/2-8),abs(Y-{h2}/2)-({h2}/2-8)),8),0,255)'",
                "-frames:v", "1", mask])
            args += ["-i", clip, "-loop", "1", "-i", mask]
            chain += (f"[{k}:v]format=rgba[c{k}];[{k + 1}:v]format=gray[m{k}];[c{k}][m{k}]alphamerge[a{k}];"
                      f"{last}[a{k}]overlay={x}:{y}:shortest=1[o{k}];")
            last, k = f"[o{k}]", k + 2
        if not chain:
            return False
        ff(args + ["-filter_complex", chain.rstrip(";"), "-map", last, "-t", str(dur), "-r", "30",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    deck = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    os.chdir(base)
    chrome = capture.find_chrome()
    pages = [page(cover_html(deck["cover"], deck.get("lanes", "")))] + [page(slide_html(s, deck.get("handle", ""))) for s in deck["slides"]]
    for i, p in enumerate(pages, 1):
        hp = os.path.join(out, f"{i:02d}.html")
        open(hp, "w", encoding="utf-8").write(p)
        png = os.path.join(out, f"{i:02d}.png")
        ok = capture.screenshot(chrome, "file://" + os.path.abspath(hp), png, W, H, 60, 6000) if chrome else "no chrome"
        moved = ""
        if i > 1 and ok == "ok" and deck.get("video", True) and shutil.which("ffmpeg"):  # every signal slide moves; the cover stays a still
            media = deck["slides"][i - 2].get("media")
            rects = card_rects(chrome, hp)
            base_html = os.path.join(out, f"{i:02d}-base.html")  # the slide without its stills, so only the footage shows in the cards
            open(base_html, "w", encoding="utf-8").write(p.replace("</style>", ".img img{visibility:hidden}</style>"))
            base = os.path.join(out, f"{i:02d}-base.png")
            capture.screenshot(chrome, "file://" + os.path.abspath(base_html), base, W, H, 60, 6000)
            if slide_video(base, rects, media, os.path.join(out, f"{i:02d}.mp4"), float(deck.get("seconds", 9))):
                moved = " + video"
        print(f"{i:02d} {ok}{moved}")


if __name__ == "__main__":
    main()
