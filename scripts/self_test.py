"""Offline self-test on a synthetic journal. No network, no browser needed. Usage: python3 self_test.py"""
import json, os, random, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit, copycheck, ledger, pageviews, render  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_journal(d):
    os.makedirs(os.path.join(d, "panel-progress"), exist_ok=True)
    obs = [
        dict(url="https://news.example/a", platform="web", creator_id="writer-a", origin_id="o1", evidence_kind="reporting",
             published_at="2026-10-01", observed_at="2026-10-03T10:00:00Z", promotion="unknown", summary="a"),
        dict(url="https://x.com/u/1", platform="x", creator_id="AliceB", origin_id="o2", evidence_kind="self_report",
             published_at="2026-10-02T09:00:00Z", observed_at="2026-10-03T09:00:00Z", promotion="own_product", summary="b"),
        dict(url="https://x.com/u/2", platform="x", creator_id="alice-b", origin_id="o2", evidence_kind="self_report",
             published_at=None, observed_at="2026-10-03", promotion="unknown", summary="c"),
        dict(url="https://ads.example/agg", platform="tiktok", creator_id=None, origin_id="o3", evidence_kind="platform_aggregate",
             published_at=None, observed_at="2026-10-03T08:00:00Z", promotion="unknown", summary="d"),
    ]
    for o in obs:
        o["review"] = {"decision": "accept"}
    held = dict(obs[0], url="https://news.example/held", review={"decision": "hold"})
    sig = [{"record_id": f"r{i}", "first_seen_at": f"2026-10-0{3 + i % 2}T00:00:00Z", "run_reference": "t", "observation": o}
           for i, o in enumerate(obs + [held, held])]
    with open(os.path.join(d, "signals.jsonl"), "w") as f:
        f.write("\n".join(json.dumps(s) for s in sig) + "\n")
    json.dump(obs, open(os.path.join(d, "history.json"), "w"))
    json.dump({"definitions": [{"trend_id": "w1"}, {"trend_id": "w2"}], "panels": [{"id": "p", "suggested_window_days": 7}],
               "windows": [], "assessments": []}, open(os.path.join(d, "watch_state.json"), "w"))
    th = {"minimum_baseline": 3, "minimum_absolute_change": 2, "relative_change": 0.5}
    with open(os.path.join(d, "trend_history.jsonl"), "w") as f:
        for _ in range(2):
            f.write(json.dumps({"run_reference": "t", "assessment": {"status": "insufficient_evidence", "thresholds": th}}) + "\n")
    json.dump({"window_start": "2026-10-05T00:00:00Z", "window_end": "2026-10-12T00:00:00Z"},
              open(os.path.join(d, "panel-progress", "p1.json"), "w"))
    json.dump({"path": "elsewhere/panel-progress/p1.json", "window_state": "open"},
              open(os.path.join(d, "panel-progress", "latest.json"), "w"))


def main():
    tmp = tempfile.mkdtemp(prefix="scout-selftest-")
    j = os.path.join(tmp, "journal")
    write_journal(j)

    a = audit.audit(j)
    F = a["figures"]
    check("audit counts records", F["records"]["value"] == 6)
    check("audit counts held", F["held"]["value"] == 2)
    check("audit counts accepted", F["accepted"]["value"] == 4)
    check("audit platform mix", F["platform_mix"]["value"] == {"x": 2, "web": 1, "tiktok": 1})
    check("audit own product", F["own_product"]["value"] == 1)
    check("audit median age", F["median_age_days"]["value"] == 1.7, F["median_age_days"]["value"])
    check("audit finds creator id collision", "aliceb" in F["creator_id_collisions"]["value"])
    check("audit Poisson per watch at mean 3", F["false_label_per_watch"]["value"] == 0.272, F["false_label_per_watch"]["value"])
    check("audit Poisson across 2 watches", F["false_label_any_watch"]["value"] == 0.47, F["false_label_any_watch"]["value"])
    check("audit earliest comparison", F["earliest_comparison"]["value"] == "2026-10-19", F["earliest_comparison"]["value"])
    check("audit verdict digest without ledger", a["verdict"] == "digest")
    empty = os.path.join(tmp, "empty")
    os.makedirs(empty)
    e = audit.audit(empty)
    check("audit on empty folder marks files missing", e["files"]["history.json"] == "missing" and e["figures"]["accepted"]["value"] == 0)

    row = dict(watch_id="w1", item="x", scout_first_seen_at="2026-10-01", scout_record_id="r0", origin_id="o1",
               metric_inflection_at=None, benchmark_outlet_set=["Billboard"], first_benchmark_coverage_at="2026-10-09",
               benchmark_url="https://b.example", search_method_and_coverage={"coverage": "complete"}, status="resolved",
               resolution_due="2026-12-30", reviewer="me")
    check("gate closed with no ledger", not ledger.gate([])["open"])
    check("gate closed with open rows", not ledger.gate([dict(row, status="open", first_benchmark_coverage_at=None)])["open"])
    check("gate opens on resolved positive lead", ledger.gate([row])["open"])
    check("gate stays closed on negative lead", not ledger.gate([dict(row, first_benchmark_coverage_at="2026-09-20")])["open"])
    check("gate stays closed on a positive lead from a partial search",
          not ledger.gate([dict(row, search_method_and_coverage={"coverage": "partial"})])["open"])
    check("validator rejects typed lead mismatch", ledger.validate([dict(row, lead_days_vs_press=99)]) != [])
    check("validator rejects never_covered without complete search",
          ledger.validate([dict(row, status="never_covered", search_method_and_coverage={"coverage": "partial"})]) != [])

    data = dict(F)
    good = {"slides": [{"kind": "quote", "headline": "{{records}} records", "body": "{{false_label_per_watch|one_in}}"}]}
    probs, _ = copycheck.check(good, data, False)
    check("copy check passes traced numbers", probs == [], probs)
    claim = {"slides": [{"kind": "quote", "headline": "Microdramas are rising fast"}]}
    probs, _ = copycheck.check(claim, data, False)
    check("copy check blocks radar claim while gate closed", any("radar claim" in p for p in probs))
    probs, _ = copycheck.check(claim, data, True)
    check("copy check allows the claim once the gate opens", probs == [], probs)
    bare = {"slides": [{"kind": "quote", "headline": "We read 41 sources"}]}
    probs, _ = copycheck.check(bare, data, False)
    check("copy check blocks untraced number", any("'41'" in p for p in probs))
    probs, _ = copycheck.check(dict(bare, slides=[dict(bare["slides"][0], untraced_ok=[{"value": "41", "reason": "catalogue size"}])]), data, False)
    check("copy check allows a declared constant", probs == [], probs)

    rnd = random.Random(7)
    raw = {}
    start = __import__("datetime").date(2023, 1, 2)
    for name, level in (("Watch A", 300), ("Ctrl A", 900), ("Ctrl B", 700), ("Ctrl C", 1200)):
        raw[name] = {(start + __import__("datetime").timedelta(days=i)).strftime("%Y%m%d"): max(0, int(rnd.gauss(level, level * 0.1)))
                     for i in range(700)}
    bdir = os.path.join(tmp, "backfill")
    os.makedirs(bdir)
    json.dump(raw, open(os.path.join(bdir, "pageviews_raw.json"), "w"))
    an = pageviews.analyze({"watch_id": "w1", "watch": ["Watch A", "Missing Article"], "control": ["Ctrl A", "Ctrl B", "Ctrl C"],
                            "start": "20230102", "min_volume": 500}, bdir)
    check("backfill analysis runs offline", an["control_false_alarm_pooled"] is not None)
    check("backfill reports missing article, no zero fill", an["missing_articles"] == ["Missing Article"])
    check("backfill steady noise rarely flags", an["control_false_alarm_pooled"] < 0.05, an["control_false_alarm_pooled"])

    ctx = render.Ctx(dict(render.THEME), dict(F, backfill=an), {}, {"brand": "THE SCOUT", "series": "TEST", "date": "TODAY", "mark": "M"})
    kinds = [{"kind": "cover", "images": ["missing-1"], "headline": "Cover"},
             {"kind": "scorecard", "headline": "Score", "rows": [{"status": "HOLD", "title": "t", "detail": "d"}]},
             {"kind": "day_bars", "headline": "Days", "stats": [{"value": "{{records}}", "label": "records"}]},
             {"kind": "source_bars", "headline": "Sources"},
             {"kind": "radar", "headline": "Radar", "rows": [{"value": "{{own_product}}", "text": "own"}]},
             {"kind": "image_grid", "headline": "Grid", "cards": [{"image": "nope", "type": "T", "name": "N", "note": "n"}]},
             {"kind": "metric_chart", "headline": "Chart", "series": "backfill.monthly.Watch A", "title": "Watch A", "unit": "VIEWS"},
             {"kind": "groups", "headline": "Groups", "groups": [{"label": "KEEP", "items": [{"lead": "a", "text": "b"}]}]},
             {"kind": "tests", "headline": "Tests", "rows": [{"name": "n", "detail": "d", "pass": "p"}]},
             {"kind": "quote", "headline": "Quote", "body": "b", "quote": "q", "attribution": "a"}]
    for i, s in enumerate(kinds, 1):
        try:
            h = render.page(s, i, len(kinds), ctx, ctx.deck)
            check(f"render builds {s['kind']}", "<div id=\"frame\"" in h)
        except Exception as ex:  # noqa: BLE001
            check(f"render builds {s['kind']}", False, repr(ex))
    h = render.page(kinds[5], 6, 10, ctx, ctx.deck)
    check("missing image renders a labelled gap", "IMAGE NOT CAPTURED" in h)

    kctx = render.Ctx(dict(render.KAIJU), dict(F, backfill=an), {}, ctx.deck)
    kh = "".join(render.page(s, i, len(kinds), kctx, kctx.deck) for i, s in enumerate(kinds, 1))
    check("poster theme renders every kind", kh.count('<div id="frame"') == len(kinds))
    check("poster theme has no CJK characters", not any(0x3040 <= ord(ch) <= 0x9FFF for ch in kh))
    check("poster theme applies hand-printed filters", "url(#distress)" in kh and "url(#rough)" in kh)

    import signals, calls, media  # noqa: E401
    sdir = os.path.join(tmp, "signals")
    for src_ent, level, spike in (("watch-a", 200, True), ("ctrl-a", 900, False), ("ctrl-b", 700, False)):
        weekly = {}
        d0 = __import__("datetime").date(2024, 1, 1)
        for w in range(120):
            wk = (d0 + __import__("datetime").timedelta(weeks=w)).isoformat()
            weekly[wk] = int(rnd.gauss(level, level * 0.08)) * (6 if spike and w >= 110 else 1)
        os.makedirs(os.path.join(sdir, "raw", "wikipedia"), exist_ok=True)
        json.dump({"weekly": weekly}, open(os.path.join(sdir, "raw", "wikipedia", f"{src_ent}.json"), "w"))
    sb = {"watch_id": "t", "end": "2026-06-01", "entities": [{"name": "watch-a", "wikipedia": "A"}],
          "controls": [{"name": "ctrl-a", "wikipedia": "B"}, {"name": "ctrl-b", "wikipedia": "C"}]}
    sa = signals.analyze(sb, sdir)
    fw = sa["sources"]["wikipedia"]["entities"]["watch-a"]["first_flag_week"]
    check("signals flag a real spike", fw is not None and fw >= "2026-02-09", fw)
    good_call = {"call_id": "C-1", "made_at": "2026-10-23T00:00:00Z", "made_by": "t", "watch_id": "w", "subject": "s",
                 "statement": "x", "kind": "coverage", "slug_patterns": ["x"], "benchmark_outlet_set": ["A"],
                 "resolve_by": "2026-11-22", "evidence_at_call": {}, "status": "open"}
    check("calls validate a good call", calls.validate([good_call]) == [])
    check("calls reject resolve_by before made_at", calls.validate([dict(good_call, resolve_by="2026-10-01")]) != [])
    sc = calls.score([good_call, dict(good_call, call_id="C-2", status="hit"), dict(good_call, call_id="C-3", status="miss")])
    check("calls score includes misses", sc["hit_rate"] == 0.5 and sc["open"] == 1, sc)
    check("voiceover resolves placeholders", media.line_for({"voiceover": "{{records}} records"}, data) == "6 records")
    check("Hacker News phrases are matched exactly", signals.hn_query("vibe coding") == '"vibe coding"' and signals.hn_query("labubu") == "labubu")
    bt = {"cases": [{"id": "x", "name": "X", "kind": "breakout", "lead_days_vs_press": 12, "earliest_flag_known_at": "2025-01-01",
                     "first_benchmark": {"outlet": "Variety", "published": "2025-01-13"},
                     "per_source": {"bluesky": {"flag_known_at": "2025-01-01", "durability": "sustained"}}}]}
    reg = {"ranked": ["bluesky:a.b"], "accounts": {"bluesky:a.b": {"platform": "bluesky", "handle": "a.b", "evidence": [
        {"case": "x", "lead_days": 30, "benchmark_outlet": "Variety"}]}}}
    tctx = render.Ctx(dict(render.KAIJU), dict(F, backtest=bt, registry=reg, calls_list=[good_call]), {}, ctx.deck)
    for kind in ("backtest", "calls", "registry"):
        h = render.page({"kind": kind, "headline": kind}, 1, 1, tctx, tctx.deck)
        check(f"render builds {kind} table", "<div id=\"frame\"" in h and ("+12 days" in h if kind == "backtest" else True))

    prev = audit.audit(j)
    cur = json.loads(json.dumps(prev))
    cur["figures"]["accepted"]["value"] = 5
    ch = audit.compare(prev, cur)
    check("history compare reports a change", ch == [{"figure": "accepted", "before": 4, "after": 5}], ch)

    print(f"\n{'all checks passed' if not FAILS else str(len(FAILS)) + ' check(s) failed'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
