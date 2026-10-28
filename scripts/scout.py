"""The Scout, guided. Plain questions in, a finished edition out.

  python3 scripts/scout.py setup                      asks your niche, what to watch and your name, then makes the edition
  python3 scripts/scout.py setup --niche "K-pop" --names "NewJeans, ILLIT, KATSEYE" --mark "Sam" --x "@hybe_labels" --yes
  python3 scripts/scout.py starter music              start from a ready niche (music, marketing, games, ai-tools)
  python3 scripts/scout.py run [FOLDER]               refresh an edition (the most recent one if no folder)
  python3 scripts/scout.py list                       show your editions
Editions live in ~/Documents/The Scout/<niche>/ (set SCOUT_HOME to change). Nothing is posted or sent.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import signals  # noqa: E402

HOME = os.path.expanduser(os.environ.get("SCOUT_HOME", "~/Documents/The Scout"))
TECH = re.compile(r"\b(software|artificial intelligence|ai\b|app|application|chatbot|company|startup|programming|language model|"
                  r"code|open-source|platform|engine|framework|robot)", re.I)
CONTROLS = {
    "culture": [{"name": "Coffee", "wikipedia": "Coffee", "bluesky": "coffee"}, {"name": "Chess", "wikipedia": "Chess", "bluesky": "chess"},
                {"name": "Bicycle", "wikipedia": "Bicycle", "bluesky": "bicycle"}],
    "tech": [{"name": "Python", "hackernews": "python"}, {"name": "Linux", "hackernews": "linux"}, {"name": "PostgreSQL", "hackernews": "postgres"}],
}


def say(msg=""):
    print(msg, flush=True)


def ask(q, default=None):
    try:
        a = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:  # no keyboard attached (an agent or a script): take the default
        say("")
        a = ""
    return a or (default or "")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "my-scout"


HINTS = [(r"video game|game\)", "game"), (r"film\)", "film"), (r"tv series|television series|miniseries", "show"),
         (r"\(band\)", "band"), (r"language model|chatbot|software|code editor|artificial intelligence", "ai"), (r"album", "album")]


def search_term(name, title):
    """Posts search words: the plain name, plus one hint word when the name alone is an everyday word."""
    term = name.lower()
    words = re.findall(r"[a-z0-9]+", term)
    short = len(words) == 1 and len(words[0]) <= 7 or bool(re.fullmatch(r"[a-z0-9.]{1,8}", term.replace(" ", "")))
    paren = (re.search(r"\((.*?)\)", title) or [None, ""])[1].lower() if "(" in title else ""
    if short and paren:
        for pat, hint in HINTS:
            if re.search(pat, f"({paren})"):
                return f"{' '.join(words)} {hint}"
    return term


def find_article(name):
    """Best Wikipedia article for a name, with its one-line description so a person can confirm it."""
    try:
        d, _ = signals.get_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "opensearch", "search": name, "limit": 5, "namespace": 0, "format": "json"}))
    except Exception:
        return []
    out = []
    for title in (d[1] if len(d) > 1 else [])[:3]:
        try:
            s, _ = signals.get_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"), safe=""))
            if s.get("type") == "standard":
                out.append({"title": title, "description": s.get("description") or ""})
        except Exception:
            continue
    return out


def build_basket(niche, names, interactive):
    ents, lanes = [], set()
    for n in names:
        ent = {"name": n}
        if re.fullmatch(r"[\w.-]+/[\w.-]+", n):  # owner/repo
            ent.update(github=n, hackernews=n.split("/")[1])
            lanes.add("tech")
            ents.append(ent)
            say(f"  {n}: GitHub repository")
            continue
        cands = find_article(n)
        pick = cands[0] if cands else None
        if interactive and cands:
            say(f"\n  {n}")
            for i, c in enumerate(cands, 1):
                say(f"    {i}. {c['title']}  ({c['description']})")
            say("    0. none of these")
            choice = ask("    Which one is it", "1")
            pick = cands[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(cands) else None
        elif pick:
            say(f"  {n}: {pick['title']} ({pick['description']})")
        else:
            say(f"  {n}: no Wikipedia article found; tracking posts only")
        if pick:
            ent["wikipedia"] = pick["title"]
        ent["name"] = re.sub(r"\s*\(.*?\)", "", n).strip() or n
        ent["bluesky"] = search_term(ent["name"], pick["title"] if pick else "")
        if pick and TECH.search(pick["description"]):
            ent["hackernews"] = ent["bluesky"]
            lanes.add("tech")
        else:
            lanes.add("culture")
        ents.append(ent)
    controls = list(CONTROLS["culture"]) + (list(CONTROLS["tech"]) if "tech" in lanes else [])
    return {"watch_id": slugify(niche), "niche": niche, "start": "2023-01-02", "entities": ents, "controls": controls,
            "rule": {"baseline_weeks": 52, "threshold_mads": 3, "consecutive": 2,
                     "min_volume": {"wikipedia": 500, "hackernews": 3, "bluesky": 50, "github": 100}},
            "made_at": datetime.date.today().isoformat()}


WEEK_SLIDES = ("states", "move", "posts", "press")  # the pages every edition carries since the 28 Oct 2026 update
X_STAMP = {"value": "{{brief.counts.x_posts|thousands}}", "label": "X POSTS", "icon": "eye"}


def template():
    return json.load(open(os.path.join(ROOT, "templates", "starter-edition.json")))


def build_edition(niche, mark, basket, has_x=False):
    ed = template()
    ed["series"] = niche.upper()[:28]
    ed["mark"] = (mark or "").upper()[:24]
    ed["date"] = datetime.date.today().strftime("%d %b %Y").upper()
    cover = ed["slides"][0]
    cover["headline"] = f"{niche}, this week."
    cover["source"] = "Made with The Scout"
    if has_x:
        cover["stamps_row"].append(dict(X_STAMP))
    has = {src for e in basket["entities"] for src in e}
    if "hackernews" in has:
        at = next(i for i, s in enumerate(ed["slides"]) if s.get("id") == "bluesky") + 1
        ed["slides"].insert(at, {"id": "hackernews", "kind": "signal_board", "signal_source": "hackernews", "eyebrow": "BUILDERS",
                                 "headline": "What builders are posting.", "note": "Weekly Hacker News stories naming each, last 52 weeks.",
                                 "untraced_ok": [{"value": "52", "reason": "chart window length"}],
                                 "voiceover": "And what builders are posting about on Hacker News.", "source": "Source: Hacker News via Algolia"})
    return ed


def refresh_edition(path, has_x):
    """Every run: today's date on every page, and older editions get the weekly pages (in or out, the move, posts, press)."""
    ed = json.load(open(path))
    ed["date"] = datetime.date.today().strftime("%d %b %Y").upper()
    have = {s.get("kind") for s in ed.get("slides", [])}
    new = [s for s in template()["slides"] if s.get("kind") in WEEK_SLIDES and s.get("kind") not in have]
    if new:
        at = 1 if ed["slides"] and ed["slides"][0].get("kind") == "cover" else 0
        ed["slides"][at:at] = new
    cover = ed["slides"][0] if ed["slides"] and ed["slides"][0].get("kind") == "cover" else None
    if cover is not None and not cover.get("stamps_row"):
        cover["stamps_row"] = template()["slides"][0]["stamps_row"]
        cover["voiceover"] = "{{brief.voice.cover}}"
    if cover is not None and has_x and not any("x_posts" in (it.get("value") or "") for it in cover.get("stamps_row", [])):
        cover["stamps_row"].append(dict(X_STAMP))
    json.dump(ed, open(path, "w"), ensure_ascii=False, indent=1)


def x_posts_api(handle):
    """An account's newest public posts, read without a login (the same route xpublic.py uses), or None."""
    try:
        d, _ = signals.get_json(f"https://api.fxtwitter.com/2/profile/{urllib.parse.quote(handle)}/statuses", retries=1)
    except Exception:
        return None
    return (d or {}).get("results") or None


def build_watchlist(niche, handles, interactive):
    """X accounts the reader names, each read once to confirm it exists and to show its name before it's kept."""
    accounts, today = [], datetime.date.today().isoformat()
    for raw in handles:
        h = raw.strip().lstrip("@").split("/")[-1]
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", h):
            say(f"  {raw}: not an X handle, skipped")
            continue
        posts = x_posts_api(h)
        if not posts:
            say(f"  @{h}: couldn't read any public posts, skipped (check the spelling)")
            continue
        a = posts[0].get("author") or {}
        name, followers = a.get("name") or h, a.get("followers")
        desc = f"{name}" + (f", {followers:,} followers" if isinstance(followers, int) else "")
        if interactive and ask(f"  @{a.get('screen_name') or h}: {desc}. Keep it? (Y/n)", "y").lower().startswith("n"):
            continue
        say(f"  @{a.get('screen_name') or h}: {desc}")
        accounts.append({"handle": a.get("screen_name") or h, "lane": "watchlist", "name": name,
                         "verified": f"public posts read on {today}; shown to the owner as {desc}"})
    return {"niche": niche, "updated": today, "rule": "Add a handle only after reading its profile and matching the name; never guess one.",
            "why": "xpublic.py reads these accounts' public posts every run without a login.", "accounts": accounts}


def run(folder, media=True):
    basket, edition = os.path.join(folder, "basket.json"), os.path.join(folder, "edition.json")
    if not (os.path.exists(basket) and os.path.exists(edition)):
        sys.exit(f"{folder} has no basket.json and edition.json; run setup first")
    say("\nPulling public data with history. The first run takes a few minutes; later runs add only the newest weeks.")
    config = os.path.join(folder, "none.json")
    wl = os.path.join(folder, "x-watchlist.json")
    has_x = os.path.exists(wl) and bool(json.load(open(wl)).get("accounts"))
    if has_x:  # X every week, no login: the niche's watchlist, read and compared week to week
        config = os.path.join(folder, "scout-config.json")
        json.dump({"root": folder, "x_watchlist": "x-watchlist.json", "x_public_dir": "x/{date}", "x_history": "x"}, open(config, "w"), indent=1)
    refresh_edition(edition, has_x)
    cmd = [sys.executable, "-I", os.path.join(HERE, "run.py"), "--config", config, "--out", folder,
           "--signals", basket, "--pull", "--headlines", "--slides", edition]
    if media and shutil.which("ffmpeg"):
        cmd.append("--media")
    elif media:
        say("ffmpeg isn't installed, so this run makes the PDF and images but skips the audio and video.")
    rc = subprocess.call(cmd)
    frames = os.path.join(folder, "frames")
    pdf, mp4 = os.path.join(frames, "edition.pdf"), os.path.join(frames, "edition.mp4")
    made = [p for p in (pdf, mp4) if os.path.exists(p)]
    say("")
    if made:
        say("Your edition is ready:")
        for p in made:
            say(f"  {p}")
        if sys.platform == "darwin" and not os.environ.get("SCOUT_NO_OPEN"):
            subprocess.call(["open", made[0]])
    else:
        say("No edition was made. The messages above say why.")
    json.dump({"last_run": datetime.datetime.now().isoformat(timespec="seconds"), "exit": rc},
              open(os.path.join(folder, "last-run.json"), "w"))
    return rc


def latest():
    if not os.path.isdir(HOME):
        return None
    dirs = [os.path.join(HOME, d) for d in os.listdir(HOME) if os.path.exists(os.path.join(HOME, d, "basket.json"))]
    return max(dirs, key=os.path.getmtime) if dirs else None


def main():
    ap = argparse.ArgumentParser(description="The Scout, guided.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("setup")
    s.add_argument("--niche")
    s.add_argument("--names", help="comma-separated: artists, products, tools, shows, or owner/repo")
    s.add_argument("--mark", help="your name or brand for the footer")
    s.add_argument("--x", help="optional, comma-separated X handles to read each week (each is checked before it's kept)")
    s.add_argument("--yes", action="store_true", help="accept the best match for every name without asking")
    s.add_argument("--no-media", action="store_true")
    st = sub.add_parser("starter")
    st.add_argument("name", nargs="?")
    st.add_argument("--mark")
    st.add_argument("--no-media", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("folder", nargs="?")
    r.add_argument("--no-media", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args()

    if a.cmd in (None, "setup"):
        say("The Scout\n\nA few questions, then it builds your first edition from public data with years of history.\n")
        niche = getattr(a, "niche", None) or ask("What's your niche (for example K-pop, indie games, skincare, AI tools)")
        names = getattr(a, "names", None) or ask("Name 3 to 10 things to watch: artists, products, tools, shows. Separate them with commas")
        mark = a.mark if getattr(a, "mark", None) is not None else ("" if getattr(a, "yes", False) else ask("Your name or brand for the footer (optional)", ""))
        items = [x.strip() for x in names.split(",") if x.strip()][:12]
        if len(items) < 1:
            sys.exit("Add at least one thing to watch.")
        x_raw = a.x if getattr(a, "x", None) is not None else ("" if getattr(a, "yes", False) else ask(
            "Optional: up to 20 X accounts that cover your niche, so The Scout reads their public posts each week "
            "(for example @billboard, @pitchfork). Separate them with commas, or press Return to skip", ""))
        say("\nFinding each one on Wikipedia so the history is right:")
        basket = build_basket(niche, items, interactive=not getattr(a, "yes", False))
        folder = os.path.join(HOME, slugify(niche))
        os.makedirs(folder, exist_ok=True)
        json.dump(basket, open(os.path.join(folder, "basket.json"), "w"), indent=1)
        handles = [x.strip() for x in x_raw.split(",") if x.strip()][:20]
        has_x = False
        if handles:
            say("\nChecking each X account by reading its public posts:")
            wl = build_watchlist(niche, handles, interactive=not getattr(a, "yes", False))
            if wl["accounts"]:
                json.dump(wl, open(os.path.join(folder, "x-watchlist.json"), "w"), indent=1, ensure_ascii=False)
                has_x = True
        json.dump(build_edition(niche, mark, basket, has_x), open(os.path.join(folder, "edition.json"), "w"), ensure_ascii=False, indent=1)
        say(f"\nSaved your setup in {folder}")
        sys.exit(run(folder, media=not getattr(a, "no_media", False)))
    if a.cmd == "starter":
        names = sorted(d for d in os.listdir(os.path.join(ROOT, "starters")) if not d.startswith("."))
        if not a.name or a.name not in names:
            say("Ready starters: " + ", ".join(names))
            a.name = ask("Which one", names[0])
        src = os.path.join(ROOT, "starters", a.name)
        folder = os.path.join(HOME, a.name)
        os.makedirs(folder, exist_ok=True)
        for f in ("basket.json", "edition.json", "x-watchlist.json"):
            if os.path.exists(os.path.join(src, f)):
                shutil.copyfile(os.path.join(src, f), os.path.join(folder, f))
        if a.mark:
            ed = json.load(open(os.path.join(folder, "edition.json")))
            ed["mark"] = a.mark.upper()[:24]
            json.dump(ed, open(os.path.join(folder, "edition.json"), "w"), ensure_ascii=False, indent=1)
        sys.exit(run(folder, media=not a.no_media))
    if a.cmd == "run":
        folder = a.folder or latest()
        if not folder:
            sys.exit("No editions yet. Run setup first.")
        sys.exit(run(os.path.abspath(os.path.expanduser(folder)), media=not a.no_media))
    if a.cmd == "list":
        if not os.path.isdir(HOME):
            say("No editions yet.")
        for d in sorted(os.listdir(HOME)) if os.path.isdir(HOME) else []:
            say(f"  {d}")


if __name__ == "__main__":
    main()
