"""The Scout, guided. Plain questions in, a finished edition out.

  python3 scripts/scout.py setup                      asks your niche, what to watch and your name, then makes the edition
  python3 scripts/scout.py setup --niche "K-pop" --names "NewJeans, ILLIT, KATSEYE" --mark "Sam" --yes
  python3 scripts/scout.py starter music              start from a ready niche (music, games, ai-tools)
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
    a = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
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


def build_edition(niche, mark, basket):
    ed = json.load(open(os.path.join(ROOT, "templates", "starter-edition.json")))
    ed["series"] = niche.upper()[:28]
    ed["mark"] = (mark or "").upper()[:24]
    ed["date"] = datetime.date.today().strftime("%d %b %Y").upper()
    cover = ed["slides"][0]
    cover["headline"] = f"{niche}, with its history."
    cover["voiceover"] = f"This is The Scout for {niche}: behaviour data with history, flagged by one fixed rule."
    cover["source"] = "Made with The Scout"
    has = {src for e in basket["entities"] for src in e}
    if "hackernews" in has:
        ed["slides"].insert(3, {"id": "hackernews", "kind": "signal_board", "signal_source": "hackernews", "eyebrow": "BUILDERS",
                                "headline": "What builders are posting.", "note": "Weekly Hacker News stories naming each, last 52 weeks.",
                                "untraced_ok": [{"value": "52", "reason": "chart window length"}],
                                "voiceover": "And what builders are posting about on Hacker News.", "source": "Source: Hacker News via Algolia"})
    return ed


def run(folder, media=True):
    basket, edition = os.path.join(folder, "basket.json"), os.path.join(folder, "edition.json")
    if not (os.path.exists(basket) and os.path.exists(edition)):
        sys.exit(f"{folder} has no basket.json and edition.json; run setup first")
    say("\nPulling public data with history. The first run takes a few minutes; later runs reuse what's saved.")
    cmd = [sys.executable, "-I", os.path.join(HERE, "run.py"), "--config", os.path.join(folder, "none.json"), "--out", folder,
           "--signals", basket, "--pull", "--slides", edition]
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
        mark = getattr(a, "mark", None) if getattr(a, "mark", None) is not None else ask("Your name or brand for the footer (optional)", "")
        items = [x.strip() for x in names.split(",") if x.strip()][:12]
        if len(items) < 1:
            sys.exit("Add at least one thing to watch.")
        say("\nFinding each one on Wikipedia so the history is right:")
        basket = build_basket(niche, items, interactive=not getattr(a, "yes", False))
        folder = os.path.join(HOME, slugify(niche))
        os.makedirs(folder, exist_ok=True)
        json.dump(basket, open(os.path.join(folder, "basket.json"), "w"), indent=1)
        json.dump(build_edition(niche, mark, basket), open(os.path.join(folder, "edition.json"), "w"), ensure_ascii=False, indent=1)
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
        for f in ("basket.json", "edition.json"):
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
