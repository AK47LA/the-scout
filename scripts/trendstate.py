"""What is just trending, what is peaking, and what is going out: one rule over weekly series, from any source.

  python3 trendstate.py signals BASKET.json SIGNALS_DIR [BASKET2 DIR2 ...] OUT.json
  python3 trendstate.py x POSTS.jsonl [POSTS2.jsonl ...] OUT.json [--names "Claude Duet,Suno"] [--min 3]
States, judged on the latest complete week against the item's own history:
  NEW        nothing in any earlier week, something now
  RISING     at least 1.5x the mean of the previous four weeks (JUST TRENDING when it is also the first time above
             the minimum in 12 weeks)
  PEAKING    within 15% of its own peak, and the last four weeks were near it too
  FADING     under 40% of its peak and below its own four-week mean: going out
  GONE       under 10% of its peak
  STEADY     none of the above
For X, a week is the posts by watchlist accounts that name the item; the current week is scaled to seven days.
A state is attention, not adoption. Every row keeps its numbers so a reader can check the call.
"""
import collections, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402


def classify(weeks, minimum=1):
    """weeks: list of (monday_iso, value), oldest first, last one the week being judged."""
    if not weeks:
        return None
    vals = [v for _, v in weeks]
    now, past = vals[-1], vals[:-1]
    peak = max(vals)
    if peak < minimum:  # never big enough to call either way
        return None
    prior4 = sum(past[-4:]) / max(1, len(past[-4:])) if past else 0
    row = {"week": weeks[-1][0], "value": round(now, 1), "prior4_mean": round(prior4, 1), "peak": round(peak, 1),
           "peak_week": weeks[vals.index(peak)][0], "pct_of_peak": round(100 * now / peak) if peak else None,
           "vs_prior4_pct": round(100 * (now - prior4) / prior4) if prior4 else None}
    if now >= minimum and not any(v > 0 for v in past):
        state = "NEW"
    elif now >= minimum and now >= 1.5 * prior4 and (prior4 > 0 or now >= 2 * minimum):
        state = "JUST TRENDING" if not any(v >= minimum for v in past[-12:]) else "RISING"
    elif peak and now >= 0.85 * peak and prior4 >= 0.7 * peak:
        state = "PEAKING"
    elif peak and now < 0.1 * peak:
        state = "GONE"
    elif peak and now < 0.4 * peak and now < prior4:
        state = "FADING"
    else:
        state = "STEADY"
    row["state"] = state
    return row


def complete_weeks(weekly, today=None):
    """Drop the current, partial week; signals weeks are Mondays."""
    today = today or datetime.date.today()
    this_monday = (today - datetime.timedelta(days=today.weekday())).isoformat()
    return [(w, v) for w, v in sorted(weekly.items()) if w < this_monday]


SATURATED = []  # (name, source) pairs whose recent weeks sit at a source's reporting ceiling, so no state is called


def from_signals(pairs):
    rows, seen = [], set()
    for basket_p, out_dir in pairs:
        basket = json.load(open(basket_p))
        for ent in basket.get("entities", []):
            for src in signals.BACKFILLED:
                if not ent.get(src):
                    continue
                try:
                    weekly = signals.load_weekly(out_dir, src, ent)
                except Exception:
                    continue
                weeks = complete_weeks(weekly or {})[-52:]
                capped = set(signals.capped_weeks(src, dict(weeks)))
                if capped & {w for w, _ in weeks[-6:]}:  # too big for this source to count: say so instead of calling a state
                    SATURATED.append({"name": ent["name"], "source": src, "cap": signals.BLUESKY_CAP,
                                      "note": f"{src} reports at most {signals.BLUESKY_CAP:,} a week, and recent weeks hit that ceiling"})
                    continue
                r = classify(weeks, minimum=signals.DEFAULT_MIN.get(src, 1))
                if r and (ent["name"].lower(), src) not in seen:
                    seen.add((ent["name"].lower(), src))
                    rows.append(dict(r, name=ent["name"], source=src, basket=os.path.basename(basket_p),
                                     note=f"judged on the week of {r['week']}, the latest complete week"))
    return rows


def from_x(post_files, names=None, minimum=3, today=None):
    posts = {}
    for f in post_files:
        for l in open(f):
            r = json.loads(l)
            if not r.get("reposted_by"):
                posts[r["id"]] = r
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    this_monday = today - datetime.timedelta(days=today.weekday())
    scale = 7 / max(1, (today - this_monday).days + 1)
    counts = collections.defaultdict(collections.Counter)
    if not names:  # the names this week's posts repeat most
        import xpublic
        c = collections.Counter(n for r in posts.values() if r["posted_at"][:10] >= this_monday.isoformat() for n in xpublic.names(r["text"]))
        names = [n for n, k in c.most_common(60) if k >= minimum]
    pats = {n: re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])", re.I) for n in names}
    for r in posts.values():
        day = datetime.date.fromisoformat(r["posted_at"][:10])
        w = (day - datetime.timedelta(days=day.weekday())).isoformat()
        for n, p in pats.items():
            if p.search(r["text"]):
                counts[n][w] += 1
    first = min((datetime.date.fromisoformat(r["posted_at"][:10]) for r in posts.values()), default=today)
    start = first - datetime.timedelta(days=first.weekday())
    mondays = []
    d = start
    while d <= this_monday:
        mondays.append(d.isoformat())
        d += datetime.timedelta(days=7)
    rows = []
    for n in names:
        weeks = [(m, counts[n].get(m, 0) * (scale if m == this_monday.isoformat() else 1)) for m in mondays]
        r = classify(weeks[-12:], minimum=minimum)
        if r:
            rows.append(dict(r, name=n, source="x", note="posts by watchlist accounts naming it; this week scaled to 7 days"))
    return rows


ORDER = {"NEW": 0, "JUST TRENDING": 1, "RISING": 2, "PEAKING": 3, "STEADY": 4, "FADING": 5, "GONE": 6}


def main():
    mode, args = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")]
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    flags = {arg("--names"), arg("--min")}
    args = [a for a in args if a not in flags]
    out = args[-1]
    if mode == "signals":
        rows = from_signals(list(zip(args[:-1:2], args[1:-1:2])))
    elif mode == "x":
        names = [n.strip() for n in (arg("--names") or "").split(",") if n.strip()] or None
        rows = from_x(args[:-1], names, int(arg("--min", 3)))
    else:
        sys.exit(__doc__)
    rows.sort(key=lambda r: (ORDER[r["state"]], -(r.get("vs_prior4_pct") or 0)))
    json.dump({"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "rule": __doc__.split("States,")[1].split("For X")[0].strip(),
               "rows": rows, "saturated": SATURATED}, open(out, "w"), indent=1, ensure_ascii=False)
    for r in rows:
        print(f"  {r['state']:<14} {r['name'][:32]:<32} {r['source']:<11} now {r['value']:>10} prior4 {r['prior4_mean']:>10} peak% {r['pct_of_peak']}")


if __name__ == "__main__":
    main()
