"""The Idea Museum: everything you save, think or notice, kept in one place, on two boards.

  python3 museum.py ingest  [--inbox INBOX.txt] [--saves saves.json] [--museum DIR] [--limit 25]   new lines from your phone
  python3 museum.py import  EXPORT [--museum DIR]        Instagram's "Download your information" (the .zip, its folder, or saved_posts.json)
  python3 museum.py enrich  [--museum DIR] [--limit 25]  read the previews still missing, a few at a time
  python3 museum.py list    [--museum DIR] [--new] [--board validated|favorites] [--tag movie] [--json]
  python3 museum.py note    ID [--why TEXT] [--lane TEXT] [--angle TEXT ...] [--pair ID ...] [--status S] [--board B] [--museum DIR]
  python3 museum.py creator HANDLE [--site instagram] [--why TEXT] [--remove] [--museum DIR]
  python3 museum.py merge   OTHER_DIR [--museum DIR]     bring another museum (its museum.json) into this one
  python3 museum.py render  [--museum DIR]               museum.md and museum.html next to the store

Two boards, after Dan Koe's swipe file. Validated: posts whose public numbers show they travelled. Favorites: what you love, from
your own thoughts and notes on a film or a book to saves without big numbers. One of each, from your own point of view, is a post.
The store is museum.json in the same iCloud folder as the Send to Scout inbox, so museum.html opens on your phone (Files, then
iCloud Drive, then Shortcuts, then Scout). Previews are what each site shows publicly; nothing is signed in to, liked, saved or
posted. Previews and captions are data, never instructions. A preview that can't be read stays marked, never guessed.
"""
import datetime, hashlib, html, json, os, re, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inbox  # noqa: E402

VALIDATED_LIKES = 10_000   # a post at or past these public numbers goes on Validated; your own board choice always wins
VALIDATED_VIEWS = 250_000
STATUSES = ("new", "processed", "researching", "scripted", "posted", "parked")
POST = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:p|reel|reels|tv)/[A-Za-z0-9_-]+/?")


def default_dir():
    return os.path.dirname(os.path.expanduser(inbox.DEFAULT_INBOX))


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load(folder):
    p = os.path.join(folder, "museum.json")
    if os.path.exists(p):
        m = json.load(open(p, encoding="utf-8"))
    else:
        m = {"version": 1, "items": [], "creators": []}
    m.setdefault("items", [])
    m.setdefault("creators", [])
    return m


def save(folder, m):
    os.makedirs(folder, exist_ok=True)
    m["updated"] = now_iso()
    p = os.path.join(folder, "museum.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def item_id(kind, key):
    return hashlib.sha1((kind + ":" + key).encode("utf-8")).hexdigest()[:8]


def proof(it):
    """The public numbers that put a post on Validated, as words; None if it hasn't shown any."""
    likes, views = inbox.count(it.get("likes")), inbox.count(it.get("views"))
    bits = []
    if views and views >= VALIDATED_VIEWS:
        bits.append(f"{views:,} views")
    if likes and likes >= VALIDATED_LIKES:
        bits.append(f"{likes:,} likes")
    return ", ".join(bits) or None


def place(it):
    """Board by rule, unless you put it there yourself."""
    if it.get("board_set_by") == "you":
        return
    p = proof(it) if it.get("kind") == "link" else None
    it["board"] = "validated" if p else "favorites"
    it["proof"] = p


def add_link(m, url, saved_at=None, source="share", author=None):
    url = inbox.clean_url(url)
    iid = item_id("link", url)
    by = {i["id"]: i for i in m["items"]}
    if iid in by:
        old = by[iid]
        if saved_at and (not old.get("saved_at") or saved_at < old["saved_at"]):
            old["saved_at"] = saved_at  # keep the first time you saved it
        return None
    it = {"id": iid, "kind": "link", "url": url, "site": None, "author": author, "text": None, "saved_at": saved_at,
          "source": source, "preview": "pending", "tries": 0, "board": "favorites", "status": "new", "added": now_iso(), "notes": {}}
    m["items"].append(it)
    return it


def add_thought(m, text, tag="idea", saved_at=None):
    iid = item_id("thought", " ".join(text.lower().split()))
    if any(i["id"] == iid for i in m["items"]):
        return None
    it = {"id": iid, "kind": "thought", "tag": tag, "text": text, "saved_at": saved_at, "source": "you", "preview": "n/a",
          "board": "favorites", "status": "new", "added": now_iso(), "notes": {}}
    m["items"].append(it)
    return it


FIELDS = ("site", "author", "name", "text", "detail", "posted", "likes", "views", "publication")


def fill(it, rec):
    if rec.get("outcome") == "ok":
        for k in FIELDS:
            if rec.get(k) not in (None, ""):
                it[k] = rec[k]
        it["preview"] = "ok"
        it.pop("error", None)
    else:
        it["tries"] = it.get("tries", 0) + 1
        it["preview"] = "failed" if it["tries"] >= 3 else "pending"
        it["error"] = rec.get("error")
    place(it)


def enrich(m, limit=25, fetch=inbox.get, sleep=time.sleep):
    """Read previews still pending, newest saves first, a few per run so Instagram stays happy."""
    todo = [i for i in m["items"] if i.get("kind") == "link" and i.get("preview") == "pending"]
    todo.sort(key=lambda i: i.get("saved_at") or "", reverse=True)
    done = 0
    for it in todo[:limit]:
        fill(it, inbox.read(it["url"], fetch))
        done += 1
        sleep(1.5 if "instagram.com" in it["url"] else 0.4)
    return done, max(0, len(todo) - done)


def ingest(m, text, saves=None):
    """New links and thoughts from the inbox text. Previews this week's inbox.py run already read are reused, not fetched again."""
    known = {}
    for rec in (saves or {}).get("items", []):
        if rec.get("url"):
            known[inbox.clean_url(rec["url"])] = rec
    links, notes = 0, 0
    for l in inbox.parse(text):
        it = add_link(m, l["url"], l["saved_at"].isoformat(timespec="minutes") if l["saved_at"] else None)
        if it:
            links += 1
            if it["url"] in known:
                fill(it, known[it["url"]])
    for t in inbox.thoughts(text):
        if add_thought(m, t["text"], t["tag"], t["saved_at"].isoformat(timespec="minutes") if t["saved_at"] else None):
            notes += 1
    return links, notes


def _walk(node, out, title=None):
    if isinstance(node, dict):
        t = node.get("title")
        if isinstance(t, str) and t.strip():
            title = t.strip()
        h = node.get("href")
        if isinstance(h, str) and POST.match(h):
            ts = node.get("timestamp")
            out.append((h, ts if isinstance(ts, (int, float)) and ts > 0 else None, title))
        for k, v in node.items():
            if k != "href":
                _walk(v, out, title)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out, title)
    elif isinstance(node, str):
        for mt in POST.finditer(node):
            out.append((mt.group(0), None, title))


def export_records(path):
    """(url, saved_at, poster) for every saved post in Instagram's export: a .zip, its unzipped folder, or one JSON or HTML file."""
    blobs = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if "saved" in n.lower() and n.lower().endswith((".json", ".html")):
                    blobs.append((n, z.read(n).decode("utf-8", "replace")))
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in files:
                full = os.path.join(root, f)
                if "saved" in full.lower() and f.lower().endswith((".json", ".html")):
                    blobs.append((full, open(full, encoding="utf-8", errors="replace").read()))
    else:
        blobs.append((path, open(path, encoding="utf-8", errors="replace").read()))
    out = []
    for name, text in blobs:
        if name.lower().endswith(".json"):
            try:
                _walk(json.loads(text), out)
            except ValueError:
                pass
        else:
            for mt in POST.finditer(html.unescape(text)):
                out.append((mt.group(0), None, None))
    best = {}
    for url, ts, who in out:
        u = inbox.clean_url(url)
        when = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="minutes") if ts else None
        cur = best.get(u)
        if not cur:
            best[u] = [when, who]
        else:
            if when and (not cur[0] or when < cur[0]):
                cur[0] = when
            cur[1] = cur[1] or who
    return [(u, w, who) for u, (w, who) in best.items()]


def import_export(m, path):
    added = 0
    for url, when, who in export_records(path):
        if add_link(m, url, when, source="instagram-export", author=("@" + who) if who and not who.startswith("@") else who):
            added += 1
    return added


def merge(m, other):
    """Add another museum's items and creators; an item already here keeps its own notes and gains any the other one had."""
    by = {i["id"]: i for i in m["items"]}
    added = 0
    for it in other.get("items", []):
        cur = by.get(it["id"])
        if not cur:
            m["items"].append(it)
            by[it["id"]] = it
            added += 1
            continue
        for k, v in (it.get("notes") or {}).items():
            cur.setdefault("notes", {}).setdefault(k, v)
        if cur.get("preview") != "ok" and it.get("preview") == "ok":
            for k in FIELDS:
                if it.get(k) not in (None, ""):
                    cur[k] = it[k]
            cur["preview"] = "ok"
            place(cur)
        if it.get("saved_at") and (not cur.get("saved_at") or it["saved_at"] < cur["saved_at"]):
            cur["saved_at"] = it["saved_at"]
    have = {c["handle"].lower() for c in m["creators"]}
    m["creators"] += [c for c in other.get("creators", []) if c["handle"].lower() not in have]
    return added


def note(m, iid, why=None, lane=None, angles=None, pairs=None, status=None, board=None):
    by = {i["id"]: i for i in m["items"]}
    if iid not in by:
        raise SystemExit(f"no item {iid} in the museum")
    it = by[iid]
    n = it.setdefault("notes", {})
    if why:
        n["why"] = why
    if lane:
        n["lane"] = lane
    if angles:
        n["angles"] = list(angles)
    if pairs:
        n["pairs_with"] = sorted(set(n.get("pairs_with", [])) | set(pairs))
    if status:
        if status not in STATUSES:
            raise SystemExit(f"status is one of {', '.join(STATUSES)}")
        it["status"] = status
    elif it.get("status") == "new" and (why or angles):
        it["status"] = "processed"
    if board:
        if board not in ("validated", "favorites"):
            raise SystemExit("board is validated or favorites")
        it["board"], it["board_set_by"] = board, "you"
    n["updated"] = now_iso()
    return it


def creator(m, handle, site="instagram", why=None, remove=False):
    h = handle.lstrip("@")
    m["creators"] = [c for c in m["creators"] if c["handle"].lower() != h.lower()]
    if not remove:
        m["creators"].append({"handle": h, "site": site, "why": why, "added": now_iso()})


def counts(m):
    it = m["items"]
    return {"all": len(it), "validated": sum(1 for i in it if i.get("board") == "validated"),
            "favorites": sum(1 for i in it if i.get("board") != "validated"),
            "new": sum(1 for i in it if i.get("status") == "new"),
            "pending": sum(1 for i in it if i.get("preview") == "pending"),
            "thoughts": sum(1 for i in it if i.get("kind") == "thought")}


def label(i):
    if i.get("kind") == "thought":
        return (i.get("tag") or "idea").upper()
    return (i.get("site") or "LINK").upper()


def ordered(items):
    return sorted(items, key=lambda i: i.get("saved_at") or i.get("added") or "", reverse=True)


def short_name(i):
    """A pair partner in a few words: who posted it, or the start of your thought."""
    if i.get("kind") == "thought":
        t = i.get("text") or ""
        return (t[:40] + "...") if len(t) > 40 else t
    return i.get("author") or i.get("site") or "a link"


def partners(m, i):
    by = {x["id"]: x for x in m["items"]}
    return [short_name(by[p]) for p in (i.get("notes") or {}).get("pairs_with", []) if p in by]


def render_md(m):
    c = counts(m)
    lines = ["# Idea Museum", "", f"Updated {m.get('updated', now_iso())[:10]}. {c['all']} things: {c['validated']} validated, "
             f"{c['favorites']} favorites, {c['new']} not processed yet.", ""]
    for board, title in (("validated", "Validated: posts whose numbers show they travelled"), ("favorites", "Favorites: what you love")):
        lines += [f"## {title}", ""]
        for i in ordered([x for x in m["items"] if x.get("status") != "parked" and (x.get("board") == "validated") == (board == "validated")]):
            who = f" {i['author']}:" if i.get("author") else ""
            text = (i.get("text") or ("(preview not read yet)" if i.get("kind") == "link" else "")).replace("\n", " ")
            extra = f" ({i['proof']})" if i.get("proof") else ""
            lines.append(f"- [{i['id']}] {label(i)}{who} {text[:240]}{extra}. {(i.get('saved_at') or '')[:10]} · {i.get('status')}")
            if i.get("url"):
                lines.append(f"  {i['url']}")
            n = i.get("notes") or {}
            if n.get("why"):
                lines.append(f"  Why it works: {n['why']}")
            if n.get("lane"):
                lines.append(f"  Lane: {n['lane']}")
            for a in n.get("angles", []):
                lines.append(f"  Angle: {a}")
            if partners(m, i):
                lines.append("  Pairs with: " + "; ".join(partners(m, i)))
        lines.append("")
    shelf = ordered([x for x in m["items"] if x.get("status") == "parked"])
    if shelf:
        lines += [f"## Reference shelf ({len(shelf)})", ""] + [f"- [{i['id']}] {label(i)} {i.get('author') or ''}: {(i.get('text') or '')[:140]} {i.get('url') or ''}" for i in shelf] + [""]
    if m["creators"]:
        lines += ["## Creators worth studying", ""] + [f"- @{x['handle']} ({x['site']})" + (f": {x['why']}" if x.get("why") else "")
                                                       for x in m["creators"]] + [""]
    return "\n".join(lines)


def _card(i, pairs=()):
    e = html.escape
    n = i.get("notes") or {}
    text = i.get("text") or ("Preview not read yet." if i.get("kind") == "link" else "")
    bits = [f'<span class="pill">{e(label(i))}</span>']
    if i.get("proof"):
        bits.append(f'<span class="pill proof">{e(i["proof"])}</span>')
    bits.append(f'<span class="pill st-{e(i.get("status") or "new")}">{e(i.get("status") or "new")}</span>')
    body = [f'<div class="meta">{"".join(bits)}<span class="when">{e((i.get("saved_at") or "")[:10])}</span></div>']
    if i.get("author"):
        body.append(f'<div class="who">{e(i["author"])}</div>')
    body.append(f'<p class="text">{e(text)}</p>')
    if n.get("why"):
        body.append(f'<p class="why"><b>Why it works.</b> {e(n["why"])}</p>')
    if n.get("lane"):
        body.append(f'<p class="lane">{e(n["lane"])}</p>')
    if n.get("angles"):
        body.append('<ol class="angles">' + "".join(f"<li>{e(a)}</li>" for a in n["angles"]) + "</ol>")
    if pairs:
        body.append('<p class="lane">Pairs with: ' + e("; ".join(pairs)) + '</p>')
    if i.get("url"):
        body.append(f'<a class="open" href="{e(i["url"])}" rel="noopener noreferrer" target="_blank">Open</a>')
    hay = " ".join(str(i.get(k) or "") for k in ("text", "author", "site", "tag", "status")) + " " + " ".join(str(v) for v in n.values() if isinstance(v, str))
    tag = (i.get("tag") or i.get("site") or "link").lower()
    return (f'<article class="card" data-board="{e(i.get("board") or "favorites")}" data-tag="{e(tag)}" '
            f'data-status="{e(i.get("status") or "new")}" data-hay="{e(hay.lower())}">{"".join(body)}</article>')


CSS = """:root{--bg:#f6f4ef;--panel:#fff;--ink:#1b1b1a;--muted:#6d6a63;--rule:#e3dfd6;--accent:#0f6f68;--proof:#8a5a00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--panel:#1e1e1c;--ink:#f1efe9;--muted:#a3a097;--rule:#33322f;--accent:#5fc4bb;--proof:#e0b45c}}
:root[data-theme="dark"]{--bg:#141413;--panel:#1e1e1c;--ink:#f1efe9;--muted:#a3a097;--rule:#33322f;--accent:#5fc4bb;--proof:#e0b45c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}h1{font-size:28px;margin:4px 0}h2{font-size:18px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 14px}.bar{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
input{flex:1 1 220px;padding:10px 12px;border:1px solid var(--rule);border-radius:10px;background:var(--panel);color:var(--ink);font:inherit}
button{padding:8px 12px;border:1px solid var(--rule);border-radius:999px;background:var(--panel);color:var(--ink);font:inherit;font-size:14px;cursor:pointer}
button.on{background:var(--ink);color:var(--bg)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.pill{font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:999px;border:1px solid var(--rule);color:var(--muted)}
.pill.proof{color:var(--proof);border-color:var(--proof)}.pill.st-new{color:var(--accent);border-color:var(--accent)}.when{margin-left:auto;font-size:12px;color:var(--muted)}
.who{font-weight:600}.text{margin:0;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}
.why,.lane{margin:0;font-size:14px}.lane{color:var(--muted)}.angles{margin:0;padding-left:18px;font-size:14px}.open{color:var(--accent);font-size:14px}
.empty{color:var(--muted)}"""

JS = """const q=document.getElementById('q');let tag='all';
function apply(){const s=q.value.trim().toLowerCase();document.querySelectorAll('.card').forEach(c=>{
const ok=(tag==='all'||c.dataset.tag===tag||(tag==='new'&&c.dataset.status==='new')||(tag==='researching'&&c.dataset.status==='researching'))&&(!s||c.dataset.hay.includes(s));c.style.display=ok?'':'none';});}
q.addEventListener('input',apply);document.querySelectorAll('[data-f]').forEach(b=>b.addEventListener('click',()=>{
tag=b.dataset.f;document.querySelectorAll('[data-f]').forEach(x=>x.classList.toggle('on',x===b));apply();}));"""


def render_html(m):
    e = html.escape
    c = counts(m)
    tags = sorted({(i.get("tag") or i.get("site") or "link").lower() for i in m["items"]})
    chips = ('<button class="on" data-f="all">All</button><button data-f="new">Not processed</button>'
             '<button data-f="researching">Researching</button>') + "".join(
        f'<button data-f="{e(t)}">{e(t.title())}</button>' for t in tags)
    secs = []
    live = [x for x in m["items"] if x.get("status") != "parked"]
    for board, title, blurb in (("validated", "Validated", "Posts whose public numbers show they travelled."),
                                ("favorites", "Favorites", "What you love: your thoughts, notes and saves.")):
        cards = "".join(_card(i, partners(m, i)) for i in ordered([x for x in live if (x.get("board") == "validated") == (board == "validated")]))
        secs.append(f'<h2>{title}</h2><p class="sub">{blurb}</p><div class="grid">{cards or "<p class=empty>Nothing here yet.</p>"}</div>')
    shelf = [x for x in m["items"] if x.get("status") == "parked"]
    if shelf:
        cards = "".join(_card(i, partners(m, i)) for i in ordered(shelf))
        secs.append(f'<details><summary><h2 style="display:inline">Reference shelf ({len(shelf)})</h2></summary>'
                    f'<p class="sub">Saved for reference, not post ideas yet.</p><div class="grid">{cards}</div></details>')
    cr = ""
    if m["creators"]:
        cr = "<h2>Creators worth studying</h2><ul>" + "".join(
            f'<li>@{e(x["handle"])} ({e(x["site"])}){(": " + e(x["why"])) if x.get("why") else ""}</li>' for x in m["creators"]) + "</ul>"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Idea Museum</title><style>{CSS}</style></head><body><main><h1>Idea Museum</h1>'
            f'<p class="sub">{c["all"]} things: {c["validated"]} validated, {c["favorites"]} favorites, {c["new"]} not processed yet. '
            f'Updated {e(m.get("updated", now_iso())[:10])}. Pair one Validated with one Favorite, from your own point of view, and you have a post.</p>'
            f'<div class="bar"><input id="q" type="search" placeholder="Search everything you saved"></div><div class="bar">{chips}</div>'
            f'{"".join(secs)}{cr}</main><script>{JS}</script></body></html>')


def render(folder, m):
    with open(os.path.join(folder, "museum.md"), "w", encoding="utf-8") as f:
        f.write(render_md(m))
    with open(os.path.join(folder, "museum.html"), "w", encoding="utf-8") as f:
        f.write(render_html(m))


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        sys.exit(__doc__)
    cmd = a[0]

    def arg(k, d=None):
        return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d

    def many(k):
        return [a[i + 1] for i, x in enumerate(a) if x == k and i + 1 < len(a)]
    folder = os.path.expanduser(arg("--museum") or default_dir())
    m = load(folder)
    if cmd == "ingest":
        path = os.path.expanduser(arg("--inbox") or inbox.DEFAULT_INBOX)
        if not os.path.exists(path):
            print("museum: no inbox yet (set up the Send to Scout and Note an idea Shortcuts)")
            return
        sv = arg("--saves")
        links, notes = ingest(m, open(path, encoding="utf-8", errors="replace").read(),
                              json.load(open(sv)) if sv and os.path.exists(sv) else None)
        read, left = enrich(m, int(arg("--limit", 25)))
        save(folder, m)
        render(folder, m)
        c = counts(m)
        print(f"museum: {links} new links, {notes} new thoughts; read {read} previews, {left} still to read; "
              f"{c['all']} in the museum ({c['validated']} validated, {c['favorites']} favorites)")
    elif cmd == "import":
        if len(a) < 2 or not os.path.exists(os.path.expanduser(a[1])):
            sys.exit("give the path to Instagram's export: the .zip, its folder, or saved_posts.json")
        added = import_export(m, os.path.expanduser(a[1]))
        save(folder, m)
        render(folder, m)
        print(f"museum: {added} saved Instagram posts added; their previews are read a few per run ({counts(m)['pending']} to go)")
    elif cmd == "enrich":
        read, left = enrich(m, int(arg("--limit", 25)))
        save(folder, m)
        render(folder, m)
        print(f"museum: read {read} previews, {left} still to read")
    elif cmd == "list":
        rows = [i for i in ordered(m["items"]) if (not "--new" in a or i.get("status") == "new")
                and (not arg("--board") or i.get("board") == arg("--board")) and (not arg("--tag") or (i.get("tag") or i.get("site") or "").lower() == arg("--tag").lower())]
        if "--json" in a:
            print(json.dumps(rows, indent=1, ensure_ascii=False))
        else:
            for i in rows:
                print(f"{i['id']}  {i.get('board', 'favorites')[:3]}  {i.get('status', 'new'):<11} {label(i)[:10]:<10} "
                      f"{(i.get('author') or '')[:20]:<20} {(i.get('text') or i.get('url') or '')[:80]}")
            print(f"{len(rows)} shown; {counts(m)}")
    elif cmd == "note":
        if len(a) < 2:
            sys.exit("museum.py note ID [--why ...]")
        it = note(m, a[1], arg("--why"), arg("--lane"), many("--angle") or None, many("--pair") or None, arg("--status"), arg("--board"))
        save(folder, m)
        render(folder, m)
        print(f"museum: {it['id']} is {it['status']} on {it['board']}")
    elif cmd == "creator":
        if len(a) < 2:
            sys.exit("museum.py creator HANDLE [--site instagram] [--why ...] [--remove]")
        creator(m, a[1], arg("--site", "instagram"), arg("--why"), "--remove" in a)
        save(folder, m)
        render(folder, m)
        print(f"museum: {len(m['creators'])} creators on your list")
    elif cmd == "merge":
        if len(a) < 2 or not os.path.exists(os.path.join(os.path.expanduser(a[1]), "museum.json")):
            sys.exit("give the folder that holds the other museum.json")
        added = merge(m, load(os.path.expanduser(a[1])))
        save(folder, m)
        render(folder, m)
        print(f"museum: {added} things brought in; {counts(m)['all']} in the museum")
    elif cmd == "render":
        render(folder, m)
        print(f"museum: wrote {os.path.join(folder, 'museum.html')}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
