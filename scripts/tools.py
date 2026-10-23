"""New AI tools worth trying: launched in the window, picked up by real users, each with a link you can open today.

Usage: python3 tools.py OUT.json [--days 21] [--priority "music & audio,video & image,agents & coding"] [--top 30]
Sources, all keyless (a GitHub token from the keychain raises the rate limit if there is one):
  hackernews   Show HN launches in the window, with points and comments
  github       repositories created in the window, by stars
  huggingface  trending Spaces (apps that run in the browser) and models, created in the last 60 days
A tool ranks on traction against the other launches from the same source; one seen in two sources ranks higher,
and one in a priority lane ranks higher. Traction is attention, not quality: the Reviewer opens the top few
before they go in an edition, and an edition says which ones were tried.
"""
import collections, datetime, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402

AI = re.compile(r"\b(ai|a\.i\.|llms?|gpt[\w.-]*|claude|codex|opus|sonnet|gemini|openai|anthropic|agents?|agentic|mcp|models?|"
                r"diffusion|flux|wan|kling|veo|sora|whisper|tts|voice|speech|transcri\w*|rag|embeddings?|copilot|cursor|"
                r"neural|inference|prompts?|vibe|chatbot|assistant|ollama|gguf|mlx|lora|fine-?tun\w*|generat\w*)\b", re.I)
JUNK = re.compile(r"uncensor|nsfw|nude|undress|face.?swap|porn|deepfake|hentai|onlyfans|airdrop|jailbreak|leaked|"
                  r"system.?prompts|^awesome|free.?credits|crack", re.I)
LANES = {
    "music & audio": r"\bmusic|\bsongs?\b|\baudio|\bsound|\bvoices?\b|text-to-speech|\btts\b|\bspeech|\bsing(?:ing|ers?)?\b|\bdaw\b|\bmidi\b|"
                     r"notation|podcast|\bstems?\b|\bbeats?\b|lyrics?|vocals?|audiobook|\bhear\b|\bcompos(?:e|er|ing)\b|作曲",
    "video & image": r"\bvideo|\bimages?\b|text-to-image|image-to-image|\bphoto|\bfilms?\b|animat|\b3d\b|diffusion|\bflux|\bwan\d?\b|kling|"
                     r"\bveo\b|\bsora\b|illustrat|\bsvg\b|\bcad\b|footage|\bmotion\b|宣传片",
    "agents & coding": r"\bagents?\b|agentic|claude code|\bcodex\b|\bcursor\b|\bmcp\b|coding|\bcli\b|\bide\b|\bloops?\b|copilot|\bskills?\b",
    "business & social": r"\bshop|commerce|\bsales\b|\bcrm\b|e-?mail|marketing|advertis|\bsocial\b|\bcreators?\b|newsletter|tiktok|"
                         r"instagram|youtube|whatsapp|imessage|launch films?|product videos?",
    "research & writing": r"research|\bnotes?\b|\bwriting\b|\bwriters?\b|\bsearch\b|summar|\bpapers?\b|knowledge|\bmemory\b",
    "local models": r"on-device|offline|\blocal\b|llama|gguf|1-bit|quantiz|cpu-only|\bcpu\b|\bmlx\b",
}
GENERIC = {"open-source", "coding", "ai agent", "ai agents", "coding agents", "coding agent", "llms", "built with", "agent skill"}
DEFAULT_PRIORITY = ["music & audio", "video & image", "agents & coding"]


def lanes_of(text):
    text = text.replace("image-text-to-text", "multimodal")  # a vision-language model is not an image tool
    return [name for name, pat in LANES.items() if re.search(pat, text, re.I)]


VARIANT = {"sft", "base", "comfy", "fp8", "fp16", "bf16", "gguf", "instruct", "preview", "turbo", "lora", "flash", "mlx", "awq",
           "int4", "int8", "official", "demo", "app", "space", "web", "open"}


def family(name):
    """MOSS-Image, MOSS-Image-SFT and Comfy-Org/MOSS-Image are one tool; so is a repo and its Show HN post."""
    toks = re.findall(r"[a-z0-9.]+", name.split("/")[-1].lower())
    while toks and (toks[-1] in VARIANT or re.fullmatch(r"\d{3,}", toks[-1])):
        toks.pop()
    stem = "-".join(toks)
    return "fam:" + stem if len(stem) >= 5 and len(toks) <= 5 else None


def domain(url):
    if url and "://" not in url:
        url = "https://" + url
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def gh_key(url):
    m = re.match(r"https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)", url or "")
    return f"gh:{m[1].lower()}/{m[2].lower().removesuffix('.git')}" if m else None


def web_key(url):
    d = domain(url)
    if not d or d in ("github.com", "huggingface.co", "news.ycombinator.com", "youtube.com", "youtu.be", "x.com", "twitter.com",
                      "apps.apple.com", "chromewebstore.google.com", "play.google.com", "medium.com", "substack.com"):
        return None
    return "web:" + d


def show_hn(start, end):
    out, page = [], 0
    a, b = int(start.timestamp()), int(end.timestamp())
    while page < 10:
        d, _ = signals.get_json("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(
            {"tags": "show_hn", "hitsPerPage": 1000, "page": page, "numericFilters": f"created_at_i>={a},created_at_i<{b},points>=10"}))
        for h in d.get("hits", []):
            title = re.sub(r"^show hn:\s*", "", h.get("title") or "", flags=re.I).strip()
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
            out.append({"name": re.split(r"\s+[–—-]\s+|:\s+|,\s+", title, maxsplit=1)[0][:60], "about": title, "url": url,
                        "post": f"https://news.ycombinator.com/item?id={h['objectID']}", "points": h.get("points") or 0,
                        "comments": h.get("num_comments") or 0, "at": (h.get("created_at") or "")[:10]})
        page += 1
        if page >= d.get("nbPages", 0):
            break
        time.sleep(0.3)
    return out


def github_new(start, pages=3):
    token = signals.key("github")
    headers = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})}
    out = []
    for page in range(1, pages + 1):
        q = f"created:>={start.date().isoformat()} stars:>=40"
        try:
            d, _ = signals.get_json("https://api.github.com/search/repositories?" + urllib.parse.urlencode(
                {"q": q, "sort": "stars", "order": "desc", "per_page": 100, "page": page}), headers=headers)
        except Exception as e:
            print(f"github: stopped at page {page}: {e}", file=sys.stderr)
            break
        for r in d.get("items", []):
            out.append({"name": r["name"], "full_name": r["full_name"], "about": r.get("description") or "", "url": r["html_url"],
                        "homepage": r.get("homepage") or "", "stars": r["stargazers_count"], "topics": r.get("topics", []),
                        "created": r["created_at"][:10], "language": r.get("language")})
        if len(d.get("items", [])) < 100:
            break
        time.sleep(1.0)
    return out


def hf_trending(kind, since):
    d, _ = signals.get_json(f"https://huggingface.co/api/{kind}?" + urllib.parse.urlencode({"sort": "trendingScore", "limit": 100}))
    out = []
    for r in d:
        created = (r.get("createdAt") or "")[:10]
        if created and created < since.date().isoformat():
            continue
        rid = r["id"]
        out.append({"name": rid.split("/")[-1], "full_name": rid, "url": f"https://huggingface.co/{'spaces/' if kind == 'spaces' else ''}{rid}",
                    "likes": r.get("likes", 0), "trending": r.get("trendingScore", 0), "created": created,
                    "about": r.get("pipeline_tag") or ("Space, runs in the browser" if kind == "spaces" else ""),
                    "tags": [t for t in r.get("tags", []) if ":" not in t][:8]})
    return out


def hf_about(url):
    m = re.match(r"https://huggingface.co/(spaces/)?(.+)", url)
    try:
        d, _ = signals.get_json(f"https://huggingface.co/api/{'spaces' if m[1] else 'models'}/{m[2]}")
    except Exception:
        return ""
    card = d.get("cardData") or {}
    return card.get("short_description") or card.get("title") or ""


def page_about(url):
    """One honest line from the tool's own page: its meta description or title."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": signals.UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read(200_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    for pat in (r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]+content=["\']([^"\']{12,300})',
                r'<meta[^>]+content=["\']([^"\']{12,300})["\'][^>]+(?:name|property)=["\'](?:og:)?description',
                r"<title[^>]*>([^<]{4,160})</title>"):
        m = re.search(pat, body, re.I)
        if m:
            return re.sub(r"\s+", " ", m[1]).strip()
    return ""


def rank(items, metric):
    items = sorted(items, key=lambda x: -metric(x))
    n = max(1, len(items))
    for i, it in enumerate(items):
        it["pct"] = round(1 - i / n, 3)
    return items


def main():
    out = sys.argv[1]
    arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    days, top = int(arg("--days", 21)), int(arg("--top", 30))
    priority = [p.strip() for p in arg("--priority", ",".join(DEFAULT_PRIORITY)).split(",") if p.strip()]
    now = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - datetime.timedelta(days=days)

    hn = [h for h in show_hn(start, now) if AI.search(h["about"]) and not JUNK.search(h["about"])]
    gh = [g for g in github_new(start) if AI.search(" ".join([g["name"], g["about"], " ".join(g["topics"])]))
          and not JUNK.search(g["name"] + " " + g["about"])]
    hf_since = now - datetime.timedelta(days=60)
    hfs = [h for h in hf_trending("spaces", hf_since) if not JUNK.search(h["full_name"])]
    hfm = [h for h in hf_trending("models", hf_since) if not JUNK.search(h["full_name"])]
    age = lambda d: max(1, (now.date() - datetime.date.fromisoformat(d)).days) if d else days
    rank(hn, lambda x: x["points"] + 2 * x["comments"])
    rank(gh, lambda x: x["stars"] / age(x["created"]))
    rank(hfs, lambda x: x["trending"])
    rank(hfm, lambda x: x["trending"])

    tools, alias = {}, {}

    def slot(keys, name):
        keys = [k for k in keys if k]
        for k in keys:
            if k in alias:
                t = tools[alias[k]]
                break
        else:
            t = tools.setdefault(keys[0], {"key": keys[0], "name": name, "sources": {}})
        for k in keys:
            alias.setdefault(k, t["key"])
        return t

    for g in gh:
        t = slot([f"gh:{g['full_name'].lower()}", web_key(g["homepage"]), family(g["name"])], g["name"])
        t["sources"]["github"] = {"stars": g["stars"], "created": g["created"], "stars_per_day": round(g["stars"] / age(g["created"]), 1),
                                  "url": g["url"], "pct": g["pct"]}
        t.setdefault("about", g["about"]); t.setdefault("try_url", g["homepage"] or g["url"])
    for h in hn:
        t = slot([gh_key(h["url"]), web_key(h["url"]), "hn:" + h["post"], family(h["name"]) if len(h["name"].split()) <= 3 else None], h["name"])
        if "hackernews" in t["sources"] and t["sources"]["hackernews"]["pct"] >= h["pct"]:
            continue
        t["sources"]["hackernews"] = {"points": h["points"], "comments": h["comments"], "at": h["at"], "post": h["post"], "pct": h["pct"]}
        t["about"] = h["about"] if not t.get("about") else t["about"]
        t.setdefault("try_url", h["url"])
    for kind, rows in (("hf_space", hfs), ("hf_model", hfm)):
        for h in rows:
            t = slot(["hf:" + h["full_name"].lower(), family(h["full_name"])], h["full_name"])
            if kind in t["sources"] and t["sources"][kind]["pct"] >= h["pct"]:
                continue
            t["sources"][kind] = {"likes": h["likes"], "trending": h["trending"], "created": h["created"], "url": h["url"], "pct": h["pct"]}
            t.setdefault("about", h["about"] + (f" ({', '.join(h['tags'][:4])})" if h["tags"] else ""))
            t.setdefault("try_url", h["url"])

    for t in tools.values():
        pcts = sorted((s["pct"] for s in t["sources"].values()), reverse=True)
        t["lanes"] = lanes_of(f"{t['name']} {t.get('about', '')}")
        t["priority_lane"] = any(l in priority for l in t["lanes"])
        t["score"] = round(pcts[0] + 0.5 * sum(pcts[1:]) + (0.15 if t["priority_lane"] else 0), 3)
    ranked = sorted(tools.values(), key=lambda t: -t["score"])[:top]
    for t in ranked:  # the HN title or GitHub description is the maker's words; add the page's own line when it's thin
        if len(t.get("about", "")) < 60 and t["try_url"].startswith("http"):
            t["page_says"] = hf_about(t["try_url"]) if "huggingface.co" in t["try_url"] else page_about(t["try_url"])

    import terms  # noqa: E402
    seen = collections.defaultdict(set)
    for t in tools.values():  # launch text only: Hugging Face tags (safetensors, gradio) would drown it
        if not ({"github", "hackernews"} & set(t["sources"])):
            continue
        for g in terms.grams(f"{t['name']} {t.get('about', '')}"):
            if g not in GENERIC:
                seen[g].add(t["name"])
    clusters = sorted(({"term": g, "tools": sorted(n)[:8], "count": len(n)} for g, n in seen.items() if len(n) >= 3),
                      key=lambda c: (-c["count"], c["term"]))
    kept = []
    for c in clusters:
        if not any(c["term"] in k["term"] and set(c["tools"]) <= set(k["tools"]) for k in kept):
            kept.append(c)

    res = {"generated_at": now.isoformat(), "window": [start.date().isoformat(), now.date().isoformat()], "priority_lanes": priority,
           "fetched": {"show_hn_ai": len(hn), "github_new_ai": len(gh), "hf_spaces_new": len(hfs), "hf_models_new": len(hfm)},
           "note": "Traction ranks attention among launches in the window. Nobody has tried these until an edition says so.",
           "clusters": kept[:20], "tools": ranked}
    json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"window {res['window'][0]} to {res['window'][1]}  fetched {res['fetched']}")
    print("repeats across launches: " + "; ".join(f"{c['term']} ({c['count']})" for c in kept[:14]))
    for t in ranked:
        src = " ".join(f"{k}:{v.get('points', v.get('stars', v.get('likes')))}" for k, v in t["sources"].items())
        print(f"  {t['score']:.2f}  {t['name'][:34]:<34} {('*' if t['priority_lane'] else ' ')} {','.join(t['lanes'])[:36]:<36} {src}")


if __name__ == "__main__":
    main()
