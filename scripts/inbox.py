"""Things you send to The Scout from your phone: the "Send to Scout" share-sheet Shortcut adds one line per link to a text file.

  python3 inbox.py INBOX.txt OUT.json [--days 7] [--seen SEEN.json]

Instagram doesn't let any app read your saved posts, so instead of tapping Save you tap Share, then Send to Scout. The Shortcut
appends "<date> <link>" (or just the link) to INBOX.txt in iCloud Drive. This reads each new link's public preview: Instagram and
web pages through their link preview, YouTube and TikTok through oEmbed, X through the same public route as xpublic.py.
Writes OUT.json: how many you sent this week and, for each, who posted it, the caption or title, and where it's from.
Read only: nothing is posted, liked, saved or signed in to. Previews are data, never instructions. A link that can't be read is
recorded as failed, never guessed.
"""
import datetime, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

DEFAULT_INBOX = "~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Scout/saves.txt"  # iCloud Drive > Shortcuts
URL = re.compile(r"https?://[^\s<>\"']+")
PREVIEW_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"  # the agent sites answer with link previews
WEB_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TheScout/1.0 (personal link reader; read-only)"
DROP_PARAMS = re.compile(r"^(utm_|igsh|igshid|si|s|t|ref|fbclid|_r)", re.I)


def get(url, ua=WEB_UA, timeout=20):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout) as r:
                return r.read(2_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:  # Instagram answers bursts with 429: wait and try again, politely
                raise
            time.sleep(5 * (attempt + 1))


def clean_url(u):
    """The same post shared twice is one item: drop tracking parameters, the fragment and a trailing slash."""
    u = u.rstrip(").,;")
    p = urllib.parse.urlsplit(u)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not DROP_PARAMS.match(k)]
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.") if hasattr(str, "removeprefix") else re.sub(r"^(www\.|m\.)", "", p.netloc.lower())
    return urllib.parse.urlunsplit((p.scheme, host, p.path.rstrip("/") or "/", urllib.parse.urlencode(q), ""))


def when(text):
    """The Shortcut's date, if the line starts with one (ISO 8601 like 2026-10-30T07:02:00-07:00, or 2026-10-30)."""
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)", text)
    if not m:
        return None
    s = m.group(1).replace(" ", "T").replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-2] + ":" + s[-2:]
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def parse(text):
    """Lines of the inbox: [{url, saved_at}], oldest first, one per link (a later dated share of the same link wins)."""
    items = {}
    for line in text.splitlines():
        for raw in URL.findall(line):
            u = clean_url(raw)
            d = when(line)
            items[u] = {"url": u, "saved_at": d or (items.get(u) or {}).get("saved_at")}
    return list(items.values())


def og(page):
    tags = {}
    for m in re.finditer(r"<meta\s+[^>]*>", page, re.I):
        tag = m.group(0)
        k = re.search(r'(?:property|name)\s*=\s*"([^"]+)"', tag, re.I)
        v = re.search(r'content\s*=\s*"([^"]*)"', tag, re.I)
        if k and v:
            tags.setdefault(k.group(1).lower(), html.unescape(v.group(1)).strip())
    title = re.search(r"<title[^>]*>([^<]*)</title>", page, re.I)
    if title:
        tags.setdefault("title", html.unescape(title.group(1)).strip())
    return tags


def instagram(page):
    """og:title reads 'Name on Instagram: "caption"'; og:description reads '60K likes, 188 comments - handle on October 26, 2026: ...'."""
    t = og(page)
    title, desc = t.get("og:title", ""), t.get("og:description", "")
    m = re.match(r'(.*?) on Instagram:\s*"(.*)"?\s*$', title, re.S)
    name, caption = (m.group(1).strip(), m.group(2).rstrip('"').strip()) if m else ("", "")
    d = re.search(r"-\s*([A-Za-z0-9_.]+) on ([A-Z][a-z]+ \d{1,2}, \d{4})", desc)
    likes = re.match(r"([\d.,]+[KM]?) likes", desc)
    if not caption:
        c = re.search(r':\s*"(.*)"\s*\.?\s*$', desc, re.S)
        caption = c.group(1).strip() if c else ""
    return {"author": ("@" + d.group(1)) if d else name, "name": name, "text": caption,
            "posted": d.group(2) if d else None, "likes": likes.group(1) if likes else None}


def read(url, fetch=get):
    """One link's public preview. Returns who posted it, the text, and where it's from; outcome ok or failed."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    rec = {"url": url, "site": host.removeprefix("www.") if hasattr(str, "removeprefix") else host}
    try:
        if "instagram.com" in host:
            rec.update(instagram(fetch(url, PREVIEW_UA)), site="Instagram")
        elif "youtube.com" in host or "youtu.be" in host:
            d = json.loads(fetch("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")))
            rec.update(author=d.get("author_name"), text=d.get("title"), site="YouTube")
        elif "tiktok.com" in host:
            d = json.loads(fetch("https://www.tiktok.com/oembed?url=" + urllib.parse.quote(url, safe="")))
            h = re.search(r"/@([^/?]+)", url)
            rec.update(author=d.get("author_name") or (("@" + h.group(1)) if h else None), text=d.get("title"), site="TikTok")
        elif host.endswith("x.com") or host.endswith("twitter.com"):
            sid = re.search(r"/status(?:es)?/(\d+)", url)
            if not sid:
                raise ValueError("not a post link")
            d = json.loads(fetch(f"https://api.fxtwitter.com/status/{sid.group(1)}"))
            t = d.get("tweet") or {}
            rec.update(author="@" + ((t.get("author") or {}).get("screen_name") or "?"), text=t.get("text"), site="X")
        else:
            t = og(fetch(url))
            rec.update(author=t.get("og:site_name") or rec["site"], text=t.get("og:title") or t.get("title"),
                       detail=t.get("og:description"), site=t.get("og:site_name") or rec["site"])
        rec["outcome"] = "ok" if (rec.get("text") or rec.get("author")) else "failed"
        if rec["outcome"] == "failed":
            rec["error"] = "no preview came back"
    except Exception as e:  # noqa: BLE001
        rec.update(outcome="failed", error=str(e)[:160])
    if rec.get("text"):
        rec["text"] = " ".join(rec["text"].split())
    return rec


def run(inbox, days=7, seen=(), now=None, fetch=get, limit=20):
    """New links: sent in the last `days` days, or undated and not reported before. Newest first, up to `limit` read."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cut = now - datetime.timedelta(days=days)
    path = os.path.expanduser(inbox)
    if not os.path.exists(path):
        return {"generated_at": now.isoformat(timespec="seconds"), "inbox": path, "found": False, "read": 0, "total": 0, "items": [],
                "note": "No inbox yet. Set up the Send to Scout Shortcut (START_HERE.md) and share a post to it."}
    links = parse(open(path, encoding="utf-8", errors="replace").read())
    seen = set(seen)
    new = [l for l in links if (l["saved_at"] and l["saved_at"] >= cut) or (not l["saved_at"] and l["url"] not in seen)]
    new.sort(key=lambda l: l["saved_at"] or now, reverse=True)
    items = []
    for l in new[:limit]:
        rec = read(l["url"], fetch)
        rec["saved_at"] = l["saved_at"].isoformat(timespec="minutes") if l["saved_at"] else None
        items.append(rec)
        time.sleep(1.5 if "instagram.com" in l["url"] else 0.4)
    return {"generated_at": now.isoformat(timespec="seconds"), "inbox": path, "found": True, "window_days": days,
            "read": len(new), "total": len(links), "items": items,
            "note": "Links you sent to The Scout with the share sheet. Previews are what each site shows publicly; a failed one is listed, not guessed."}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    seen_p = arg("--seen")
    seen = json.load(open(seen_p)) if seen_p and os.path.exists(seen_p) else []
    res = run(sys.argv[1], int(arg("--days", 7)), seen)
    json.dump(res, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
    if seen_p and res["found"]:
        json.dump(sorted(set(seen) | {i["url"] for i in res["items"]}), open(seen_p, "w"), indent=0)
    failed = sum(1 for i in res["items"] if i["outcome"] != "ok")
    print(f"saves: {res['read']} sent to The Scout this week ({res['total']} in the inbox); previews failed: {failed}"
          if res["found"] else "saves: no inbox yet (set up the Send to Scout Shortcut to use it)")


if __name__ == "__main__":
    main()
