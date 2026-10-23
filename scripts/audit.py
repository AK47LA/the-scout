"""Audit a Scout journal. Every figure in audit.json names the file and field it came from.

Usage: python3 audit.py RUN_DIR OUT_DIR [--ledger LEDGER.jsonl] [--mean 3] [--today YYYY-MM-DD]
RUN_DIR is a profile run folder holding signals.jsonl, history.json, watch_state.json.
Reads only. Writes OUT_DIR/audit.json.
"""
import argparse, collections, datetime, json, math, os, re, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as ledger_mod  # noqa: E402

ABSENT_CHANNELS = ["youtube", "reddit", "discord", "streaming_charts", "search_interest"]
DEFAULT_RULE = {"minimum_baseline": 3, "minimum_absolute_change": 2, "relative_change": 0.5}


def load_json(path, default):
    if not os.path.exists(path):
        return default, "missing"
    with open(path) as f:
        return json.load(f), "ok"


def load_jsonl(path):
    if not os.path.exists(path):
        return [], "missing"
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()], "ok"


def parse_time(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if len(s) == 10:
        s += "T00:00:00+00:00"
    try:
        t = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def fig(value, source, field, note=None):
    out = {"value": value, "source": source, "field": field}
    if note:
        out["note"] = note
    return out


def poisson_false_label(mean, rule):
    """Chance that two independent windows with the same true mean get a rising or fading label."""
    base, absd, rel = rule["minimum_baseline"], rule["minimum_absolute_change"], rule["relative_change"]
    pmf = lambda k: math.exp(-mean) * mean ** k / math.factorial(k)
    top = int(mean * 6 + 30)
    rise = fade = 0.0
    for p in range(top):
        pp = pmf(p)
        for c in range(top):
            pr = pp * pmf(c)
            if p >= base and c - p >= absd and c >= (1 + rel) * p:
                rise += pr
            if p >= base and p - c >= absd and c <= (1 - rel) * p:
                fade += pr
    return rise, fade


def norm_id(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def audit(run_dir, ledger_path=None, mean=None, today=None):
    run_dir = run_dir or os.path.join(os.sep, "scout-no-journal-yet")  # a new niche has no journal: every file reads as missing
    signals, s_state = load_jsonl(os.path.join(run_dir, "signals.jsonl"))
    accepted, h_state = load_json(os.path.join(run_dir, "history.json"), [])
    watch, w_state = load_json(os.path.join(run_dir, "watch_state.json"), {})
    trend_hist, t_state = load_jsonl(os.path.join(run_dir, "trend_history.jsonl"))
    progress, p_state = load_json(os.path.join(run_dir, "panel-progress", "latest.json"), {})
    files = {"signals.jsonl": s_state, "history.json": h_state, "watch_state.json": w_state,
             "trend_history.jsonl": t_state, "panel-progress/latest.json": p_state}

    F = {}
    # Journal size and timing
    F["records"] = fig(len(signals), "signals.jsonl", "line count")
    days = collections.Counter((r.get("first_seen_at") or "")[:10] for r in signals)
    F["first_seen_by_day"] = fig(dict(sorted(days.items())), "signals.jsonl", "first_seen_at[:10]")
    F["collection_days"] = fig(len([d for d in days if d]), "signals.jsonl", "distinct first_seen_at days")
    decisions = collections.Counter(((r.get("observation") or {}).get("review") or {}).get("decision") or "none" for r in signals)
    F["review_decisions"] = fig(dict(decisions), "signals.jsonl", "observation.review.decision")
    F["held"] = fig(decisions.get("hold", 0), "signals.jsonl", "observation.review.decision == hold")
    F["accepted"] = fig(len(accepted), "history.json", "array length")

    # Measurement state
    windows = watch.get("windows") or []
    defs = watch.get("definitions") or []
    F["watches"] = fig(len(defs), "watch_state.json", "definitions length")
    F["completed_windows"] = fig(len(windows), "watch_state.json", "windows length")
    statuses = collections.Counter((t.get("assessment") or {}).get("status") or "none" for t in trend_hist)
    F["assessments"] = fig(len(trend_hist), "trend_history.jsonl", "line count")
    F["assessment_status"] = fig(dict(statuses), "trend_history.jsonl", "assessment.status")
    F["insufficient_assessments"] = fig(statuses.get("insufficient_evidence", 0), "trend_history.jsonl",
                                        "assessment.status == insufficient_evidence")

    # Source and evidence mix
    plat = collections.Counter(o.get("platform") or "unknown" for o in accepted)
    F["platform_mix"] = fig(dict(plat.most_common()), "history.json", "platform")
    F["absent_channels"] = fig({c: plat.get(c, 0) for c in ABSENT_CHANNELS}, "history.json", "platform",
                               "Channels with no accepted observation. Zero here means none collected, not none happening.")
    kinds = collections.Counter(o.get("evidence_kind") or "unknown" for o in accepted)
    F["evidence_kinds"] = fig(dict(kinds.most_common()), "history.json", "evidence_kind")
    F["own_product"] = fig(sum(1 for o in accepted if o.get("promotion") == "own_product"), "history.json",
                           "promotion == own_product")
    agg = [o for o in accepted if o.get("evidence_kind") == "platform_aggregate"]
    F["platform_aggregate"] = fig(len(agg), "history.json", "evidence_kind == platform_aggregate")
    F["platform_aggregate_captures"] = fig(len({(o.get("url"), o.get("observed_at")) for o in agg}), "history.json",
                                           "distinct (url, observed_at) among platform_aggregate")
    F["origins"] = fig(len({o.get("origin_id") for o in accepted if o.get("origin_id")}), "history.json", "distinct origin_id")

    ages, points = [], []
    for o in accepted:
        a, b = parse_time(o.get("published_at")), parse_time(o.get("observed_at"))
        age = max(0.0, (b - a).total_seconds() / 86400) if a and b else None
        if age is not None:
            ages.append(age)
        points.append([o.get("evidence_kind") or "unknown", None if age is None else round(age, 2),
                       f"{o.get('url', '')}|{o.get('summary', '')[:40]}"])
    F["evidence_points"] = fig(points, "history.json", "[evidence_kind, age_days or null, stable key] per accepted observation")
    F["dated_accepted"] = fig(len(ages), "history.json", "published_at and observed_at both present")
    F["median_age_days"] = fig(round(statistics.median(ages), 1) if ages else None, "history.json",
                               "median(observed_at - published_at)")
    F["undated_accepted"] = fig(len(accepted) - len(ages), "history.json", "published_at or observed_at missing")

    x_obs = [o for o in accepted if o.get("platform") == "x"]
    x_groups = collections.Counter(norm_id(o.get("creator_id")) for o in x_obs)
    top2 = sum(n for _, n in x_groups.most_common(2))
    F["x_accepted"] = fig(len(x_obs), "history.json", "platform == x")
    F["x_top2_accounts"] = fig(top2, "history.json", "two largest normalised creator_id groups among platform == x")
    raw_by_norm = collections.defaultdict(set)
    for o in accepted:
        if o.get("creator_id"):
            raw_by_norm[norm_id(o["creator_id"])].add(o["creator_id"])
    dupes = {k: sorted(v) for k, v in raw_by_norm.items() if len(v) > 1}
    F["creator_id_collisions"] = fig(dupes, "history.json", "creator_id values equal after lowercasing and removing punctuation")

    # Panel noise under the saved rule
    rule = dict(DEFAULT_RULE)
    for t in trend_hist:
        th = (t.get("assessment") or {}).get("thresholds") or {}
        for k in rule:
            if k in th:
                rule[k] = th[k]
    m = float(mean) if mean is not None else float(rule["minimum_baseline"])
    rise, fade = poisson_false_label(m, rule)
    per = rise + fade
    n = max(1, len(defs))
    F["noise_rule"] = fig(rule, "trend_history.jsonl", "assessment.thresholds (defaults where absent)")
    F["noise_mean"] = fig(m, "assumption", "--mean, else the rule's minimum baseline",
                          "No completed windows exist to measure a real mean." if not windows else None)
    F["false_label_per_watch"] = fig(round(per, 3), "calculated", "Poisson, two independent windows, same true mean")
    F["false_rising_per_watch"] = fig(round(rise, 3), "calculated", "Poisson")
    F["false_fading_per_watch"] = fig(round(fade, 3), "calculated", "Poisson")
    F["false_label_any_watch"] = fig(round(1 - (1 - per) ** n, 3), "calculated", f"1 - (1 - per_watch)^{n} watches")

    # Earliest comparison date
    panels = watch.get("panels") or []
    wdays = int((panels[0].get("suggested_window_days") if panels else None) or 7)
    earliest, open_window = None, None
    prog_path = progress.get("path") if progress else None
    if prog_path:
        cand = os.path.join(run_dir, "panel-progress", os.path.basename(prog_path))
        prog, _ = load_json(cand, {})
        start, end = parse_time(prog.get("window_start")), parse_time(prog.get("window_end"))
        if start and end:
            open_window = {"start": start.date().isoformat(), "end": end.date().isoformat()}
        if end:
            need_more = max(0, 2 - len(windows) - 1)
            earliest = (end + datetime.timedelta(days=wdays * need_more)).date().isoformat()
    F["window_days"] = fig(wdays, "watch_state.json", "panels[0].suggested_window_days")
    F["open_window"] = fig(open_window, "panel-progress", "window_start, window_end of the open checkpoint")
    F["earliest_comparison"] = fig(earliest, "panel-progress", "open window_end + further windows needed for two complete",
                                   None if earliest else "No open window checkpoint found.")

    gate = ledger_mod.gate(ledger_mod.load(ledger_path) if ledger_path else [])
    F["ledger_rows"] = fig(gate["rows"], ledger_path or "none", "line count")
    F["ledger_resolved_hits"] = fig(gate["hits"], ledger_path or "none", "status == resolved and lead_days_vs_press > 0")

    verdict = "radar" if gate["open"] else "digest"
    return {
        "schema": 1,
        "generated_at": (today or datetime.datetime.now(datetime.timezone.utc).isoformat()),
        "run_dir": os.path.abspath(run_dir),
        "files": files,
        "figures": F,
        "radar_gate": gate,
        "verdict": verdict,
        "verdict_reason": gate["reason"],
    }


TRACKED = ["records", "accepted", "held", "completed_windows", "insufficient_assessments", "own_product",
           "platform_aggregate", "median_age_days", "x_top2_accounts", "ledger_rows", "ledger_resolved_hits"]


def compare(prev, cur):
    """Plain changes between two audits, for the weekly read."""
    out = []
    pf, cf = prev["figures"], cur["figures"]
    for k in TRACKED:
        a, b = (pf.get(k) or {}).get("value"), (cf.get(k) or {}).get("value")
        if a != b:
            out.append({"figure": k, "before": a, "after": b})
    for k in ("platform_mix", "evidence_kinds"):
        a, b = (pf.get(k) or {}).get("value") or {}, (cf.get(k) or {}).get("value") or {}
        for key in sorted(set(a) | set(b)):
            if a.get(key, 0) != b.get(key, 0):
                out.append({"figure": f"{k}.{key}", "before": a.get(key, 0), "after": b.get(key, 0)})
    if prev.get("verdict") != cur.get("verdict"):
        out.append({"figure": "verdict", "before": prev.get("verdict"), "after": cur.get("verdict")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--ledger")
    ap.add_argument("--mean", type=float)
    ap.add_argument("--today")
    a = ap.parse_args()
    result = audit(a.run_dir, a.ledger, a.mean, a.today)
    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, "audit.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1)
    F = result["figures"]
    print(f"wrote {out}")
    print(f"records {F['records']['value']} accepted {F['accepted']['value']} held {F['held']['value']} "
          f"windows {F['completed_windows']['value']} verdict {result['verdict']}")


if __name__ == "__main__":
    main()
