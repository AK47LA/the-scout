"""Calls ledger: dated, falsifiable calls, resolved by rule, scored with misses included.

A coverage call says a benchmark outlet will name something in a headline by a date. It is only made when the
same benchmark search finds no such headline yet. When it hits, the call becomes a lead-time ledger row, so the
radar gate opens on evidence, never on a claim.

Usage:
  python3 calls.py novelty OUTLETS.json SLUGS_JSON SINCE              is anything already in the benchmark press?
  python3 calls.py resolve CALLS.jsonl OUTLETS.json LEDGER.jsonl      resolve due or already-hit calls
  python3 calls.py score CALLS.jsonl                                  hit rate, misses included
Call fields: call_id, made_at, made_by, watch_id, subject, statement, kind ("coverage"), slug_patterns,
benchmark_outlet_set, resolve_by, evidence_at_call, status (open|hit|miss|void), resolved_at, outcome.
"""
import datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark  # noqa: E402

REQUIRED = ["call_id", "made_at", "made_by", "watch_id", "subject", "statement", "kind", "slug_patterns",
            "benchmark_outlet_set", "resolve_by", "evidence_at_call", "status"]


def load(path):
    if not path or not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def save(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def validate(rows):
    probs = []
    ids = set()
    for i, r in enumerate(rows, 1):
        for k in REQUIRED:
            if k not in r:
                probs.append(f"call {i}: missing {k}")
        if r.get("call_id") in ids:
            probs.append(f"call {i}: duplicate call_id {r.get('call_id')}")
        ids.add(r.get("call_id"))
        if r.get("status") not in ("open", "hit", "miss", "void"):
            probs.append(f"call {i}: bad status {r.get('status')}")
        try:
            if datetime.date.fromisoformat(r["resolve_by"]) <= datetime.date.fromisoformat(r["made_at"][:10]):
                probs.append(f"call {i}: resolve_by must be after made_at")
        except (KeyError, ValueError):
            probs.append(f"call {i}: made_at and resolve_by must be ISO dates")
    return probs


def bound(p):
    """A plain slug matches whole slug words only: "jev" must not match "sarajevo"."""
    import re as _re
    return f"(^|[/-]){_re.escape(p)}s?($|[/-])" if _re.fullmatch(r"[a-z0-9-]+", p) else p


def search(outlets, patterns, since, until, row="novelty"):
    q = {"row": row, "window_start": since, "window_end": until, "slug_patterns": [bound(p) for p in patterns], "max_candidates": 40}
    res = benchmark.run(outlets, q)
    hits = sorted(({"outlet": o["name"], "url": c["url"], "published": (c.get("published") or "")[:10], "title": c.get("title")}
                   for o in res["outlets"] for c in o["candidates"] if c.get("published")), key=lambda h: h["published"])
    cov = {o["name"]: o["coverage"] for o in res["outlets"]}
    return hits, cov, res


def novelty(outlets, patterns, since):
    hits, cov, _ = search(outlets, patterns, since, datetime.date.today().isoformat())
    return {"already_covered": bool(hits), "earliest": hits[0] if hits else None, "coverage": cov,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def resolve(calls, outlets, ledger_path):
    today = datetime.date.today()
    ledger_rows = [json.loads(l) for l in open(ledger_path)] if os.path.exists(ledger_path) else []
    changed = []
    for c in calls:
        if c["status"] != "open":
            continue
        made = c["made_at"][:10]
        until = min(today, datetime.date.fromisoformat(c["resolve_by"])).isoformat()
        hits, cov, _ = search(outlets, c["slug_patterns"], made, until, c["call_id"])
        hits = [h for h in hits if made <= h["published"] <= c["resolve_by"]]
        if hits:
            first = hits[0]
            c.update(status="hit", resolved_at=today.isoformat(), outcome=first)
            lead = (datetime.date.fromisoformat(first["published"]) - datetime.date.fromisoformat(made)).days
            complete = all(v == "enumerated" for v in cov.values())
            ledger_rows.append({
                "watch_id": c["watch_id"], "item": f"Call {c['call_id']}: {c['subject']}",
                "scout_first_seen_at": c["made_at"], "scout_record_id": c["call_id"], "origin_id": c.get("origin_id", c["call_id"]),
                "metric_inflection_at": (c.get("evidence_at_call") or {}).get("flag_known_at"),
                "benchmark_outlet_set": c["benchmark_outlet_set"], "first_benchmark_coverage_at": first["published"],
                "benchmark_url": first["url"],
                "search_method_and_coverage": {"coverage": "enumerated" if complete else "partial", "per_outlet": cov,
                                               "novelty_at_call": c.get("novelty_at_call")},
                "lead_days_vs_press": lead, "status": "resolved",
                "resolution_due": c["resolve_by"], "reviewer": "calls.py automatic resolution; same-item check pending human review"})
            changed.append((c["call_id"], "hit", lead))
        elif today > datetime.date.fromisoformat(c["resolve_by"]):
            complete = all(v == "enumerated" for v in cov.values())
            c.update(status="miss" if complete else "open", resolved_at=today.isoformat() if complete else None,
                     outcome={"no_benchmark_headline_by": c["resolve_by"], "coverage": cov})
            changed.append((c["call_id"], c["status"], None))
    with open(ledger_path, "w") as f:
        for r in ledger_rows:
            f.write(json.dumps(r) + "\n")
    return changed


def propose(discovery, outlets, days=90, top=15):
    """Turn discovery leads into call candidates: one benchmark search for all, drop anything already named."""
    import re as _re
    cands = []
    for it in (discovery.get("feeds", {}).get("github", {}).get("items", []))[:top]:
        owner, repo = it["name"].split("/", 1)
        pats = sorted({_re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")} | ({owner.lower()} if len(owner) > 5 else set()))
        cands.append({"subject": it["name"], "feed": "github", "lane": "tech", "slug_patterns": pats, "evidence": it})
    for it in (discovery.get("feeds", {}).get("wikipedia", {}).get("items", []))[:top]:
        base = _re.sub(r"\s*\(.*?\)", "", it["name"]).strip()
        cands.append({"subject": it["name"], "feed": "wikipedia", "lane": it.get("lane"),
                      "slug_patterns": [_re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")], "evidence": it})
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    union = sorted({p for c in cands for p in c["slug_patterns"] if len(p) >= 4})
    hits, cov, _ = search(outlets, [f"(^|[/-]){_re.escape(p)}($|[/-])" for p in union], since, datetime.date.today().isoformat(), "propose")
    for c in cands:
        mine = [h for h in hits if any(_re.search(f"(^|[/-]){_re.escape(p)}($|[/-])", h["url"]) for p in c["slug_patterns"])]
        c["already_covered"] = bool(mine)
        c["earliest_press"] = mine[0] if mine else None
    return {"since": since, "benchmark_coverage": cov, "candidates": cands,
            "uncovered": [c for c in cands if not c["already_covered"]]}


def score(calls):
    hits = sum(1 for c in calls if c["status"] == "hit")
    misses = sum(1 for c in calls if c["status"] == "miss")
    open_ = sum(1 for c in calls if c["status"] == "open")
    done = hits + misses
    return {"calls": len(calls), "open": open_, "hits": hits, "misses": misses,
            "hit_rate": round(hits / done, 3) if done else None,
            "next_due": min([c["resolve_by"] for c in calls if c["status"] == "open"], default=None)}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "novelty":
        outlets, pats, since = json.load(open(sys.argv[2])), json.loads(sys.argv[3]), sys.argv[4]
        print(json.dumps(novelty(outlets, pats, since), indent=1))
    elif mode == "resolve":
        calls = load(sys.argv[2])
        ch = resolve(calls, json.load(open(sys.argv[3])), sys.argv[4])
        save(sys.argv[2], calls)
        print(json.dumps({"changed": ch, "score": score(calls)}, indent=1))
    elif mode == "propose":
        res = propose(json.load(open(sys.argv[2])), json.load(open(sys.argv[3])))
        json.dump(res, open(sys.argv[4], "w"), indent=1)
        print(f"{len(res['candidates'])} candidates, {len(res['uncovered'])} not yet named by the benchmark press")
        for c in res["candidates"]:
            print(f"  {'NEW ' if not c['already_covered'] else 'seen'} {c['feed']:<9} {c['subject'][:50]:<50} {c['slug_patterns']}")
    elif mode == "score":
        calls = load(sys.argv[2])
        probs = validate(calls)
        print(json.dumps({"problems": probs, **score(calls)}, indent=1))
    else:
        sys.exit("mode must be novelty, resolve or score")
