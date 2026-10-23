"""Lead-time ledger: schema check and the radar-claim gate.

One JSON object per line. Radar language is allowed only when at least one row is resolved
with a positive lead over the benchmark press set. Usage: python3 ledger.py LEDGER.jsonl
"""
import datetime, json, os, sys

REQUIRED = ["watch_id", "item", "scout_first_seen_at", "scout_record_id", "origin_id", "metric_inflection_at",
            "benchmark_outlet_set", "first_benchmark_coverage_at", "benchmark_url", "search_method_and_coverage",
            "status", "resolution_due", "reviewer"]
STATUSES = {"open", "resolved", "never_covered", "expired"}
DATE_FIELDS = ["scout_first_seen_at", "metric_inflection_at", "first_benchmark_coverage_at", "resolution_due"]


def load(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _date(s):
    if not s:
        return None
    return datetime.date.fromisoformat(str(s)[:10])


def lead_days(row):
    a, b = _date(row.get("scout_first_seen_at")), _date(row.get("first_benchmark_coverage_at"))
    return (b - a).days if a and b else None


def validate(rows):
    """Return a list of problems. lead_days_vs_press is computed here, never trusted from the file."""
    problems = []
    for i, r in enumerate(rows, 1):
        for k in REQUIRED:
            if k not in r:
                problems.append(f"row {i}: missing {k}")
        for k in DATE_FIELDS:
            try:
                _date(r.get(k))
            except ValueError:
                problems.append(f"row {i}: {k} is not an ISO date")
        st = r.get("status")
        if st not in STATUSES:
            problems.append(f"row {i}: status {st!r} not in {sorted(STATUSES)}")
        cov = r.get("search_method_and_coverage") or {}
        complete = isinstance(cov, dict) and cov.get("coverage") == "complete"
        if st == "never_covered" and not complete:
            problems.append(f"row {i}: never_covered needs search_method_and_coverage.coverage == complete")
        if st == "resolved" and not r.get("first_benchmark_coverage_at"):
            problems.append(f"row {i}: resolved needs first_benchmark_coverage_at")
        typed = r.get("lead_days_vs_press")
        if typed is not None and typed != lead_days(r):
            problems.append(f"row {i}: lead_days_vs_press {typed} does not match the dates ({lead_days(r)})")
    return problems


VERIFIED_COVERAGE = {"complete", "enumerated"}


def coverage(row):
    cov = row.get("search_method_and_coverage") or {}
    return cov.get("coverage") if isinstance(cov, dict) else None


def gate(rows):
    """A positive lead counts only when every benchmark outlet was enumerated for the window: a missed earlier
    article would otherwise make the Scout look ahead when it wasn't. Negative leads need no such proof."""
    problems = validate(rows)
    positive = [r for r in rows if r.get("status") == "resolved" and (lead_days(r) or 0) > 0]
    hits = [r for r in positive if coverage(r) in VERIFIED_COVERAGE]
    unverified = len(positive) - len(hits)
    if problems:
        return {"open": False, "rows": len(rows), "hits": 0, "problems": problems,
                "reason": "Ledger has schema problems, so radar claims stay locked."}
    if not rows:
        return {"open": False, "rows": 0, "hits": 0, "problems": [],
                "reason": "No lead-time ledger rows yet, so radar claims stay locked."}
    leads = [lead_days(r) for r in rows if r.get("status") == "resolved" and lead_days(r) is not None]
    if not hits:
        why = "No resolved row shows the Scout ahead of the benchmark press, so radar claims stay locked."
        if unverified:
            why = (f"{unverified} row(s) show a positive lead but the benchmark search wasn't fully enumerated, "
                   "so radar claims stay locked.")
        return {"open": False, "rows": len(rows), "hits": 0, "unverified_positive": unverified, "problems": [],
                "resolved_leads": leads, "reason": why}
    best = max(lead_days(r) for r in hits)
    return {"open": True, "rows": len(rows), "hits": len(hits), "unverified_positive": unverified, "problems": [],
            "resolved_leads": leads, "best_lead_days": best,
            "reason": f"{len(hits)} resolved row(s) show the Scout ahead of the press, best by {best} days."}


if __name__ == "__main__":
    g = gate(load(sys.argv[1] if len(sys.argv) > 1 else None))
    print(json.dumps(g, indent=1))
    sys.exit(0 if not g["problems"] else 1)
