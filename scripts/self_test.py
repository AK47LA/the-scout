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

    import terms, xpass  # noqa: E402
    xd = os.path.join(tmp, "x")
    for day, texts in (("2026-10-16", ["agent loops all week", "nothing new"]), ("2026-10-23", ["decision model shipped", "decision model again", "decision model three"])):
        out = os.path.join(xd, day)
        os.makedirs(out)
        json.dump({"date": day, "pages": [{"id": "q-a", "kind": "search", "query": "a", "url": "https://x.com/search?q=a"}]},
                  open(os.path.join(out, "plan.json"), "w"))
        with open(os.path.join(out, "reservations.jsonl"), "w") as f:
            f.write(json.dumps({"allowed": True, "session_started_at": day + "T16:05:00+00:00"}) + "\n")
        with open(os.path.join(out, "posts.jsonl"), "w") as f:
            for i, t in enumerate(texts):
                f.write(json.dumps({"page_id": "q-a", "url": f"https://x.com/u{i}/status/{100 + i}", "author": f"@u{i}", "text": t}) + "\n")
            f.write(json.dumps({"page_id": "q-a", "url": "https://x.com/u0/status/100", "text": "duplicate"}) + "\n")
            f.write(json.dumps({"page_id": "q-a", "url": "https://example.com/not-x", "text": "x"}) + "\n")
        with open(os.path.join(out, "pages.jsonl"), "w") as f:
            f.write(json.dumps({"page_id": "q-a", "status": "read"}) + "\n")
        rc = xpass.ingest(out)
    check("xpass ingest keeps X posts, drops duplicates and non-X URLs", rc["posts"] == 3 and len(rc["dropped"]) == 1 and rc["complete"], rc)
    man = json.load(open(os.path.join(xd, "2026-10-23", "manifest.json")))
    check("xpass manifest carries native provenance", man["items"][0]["provenance"]["session_started_at"].startswith("2026-10-23"))
    latest, rec, base = terms.x_passes(xd)
    check("terms reads the newest X pass against earlier ones", latest == "2026-10-23" and len(rec) == 3 and len(base) == 2)
    hit = [t for t in terms.surface(rec, base, min_docs=3) if t["term"] == "decision model"]
    check("terms surfaces a phrase new on X", bool(hit) and hit[0]["new"])
    denied = xpass.reserve(os.path.join(tmp, "gate"), {"x_owner_consent": True, "x_gate": {"cwd": tmp, "cmd": [sys.executable, "-c",
                           "print('{\"allowed\": false, \"reason\": \"Outside window\"}')"]}})
    check("xpass reserve honours a denied gate", denied["allowed"] is False and denied["reason"] == "Outside window", denied)
    no_yes = xpass.reserve(os.path.join(tmp, "gate"), {})
    check("xpass reserve refuses every signed-in page without the owner's consent", no_yes["allowed"] is False and no_yes["gate"] == "x_owner_consent", no_yes)

    import formats  # noqa: E402
    base = {"name": "one move per video, in levels", "keep": ["one move per video"], "make_yours": ["the skill"],
            "captures": ["evidence/2026-10-23/captures/x.png"]}
    weeks = ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]
    rising = formats.judge(dict(base, creators={"tiktok": dict(zip(weeks, [0, 0, 0, 67, 263]))}, reels_checked=True))
    check("formats calls a new climb early", rising["verdict"] == "EARLY", rising["verdict"])
    check("formats flags first on Reels when Reels was checked and quiet", rising["first_on_reels"], rising["reels_note"])
    unchecked = formats.judge(dict(base, creators={"tiktok": dict(zip(weeks, [0, 0, 0, 67, 263]))}))
    check("formats never flags Reels it didn't check", not unchecked["first_on_reels"], unchecked["reels_note"])
    fading = formats.judge(dict(base, creators={"tiktok": dict(zip(weeks, [40, 222, 210, 120, 50]))}))
    check("formats calls a falling format late", fading["verdict"] == "LATE", fading["verdict"])
    blind = formats.judge(dict(base, captures=[]))
    check("formats says unknown without counts", blind["verdict"] == "UNKNOWN", blind["verdict"])
    for bad, why in ((dict(base, make_yours=[]), "make_yours"), (dict(base, creators={"tiktok": {"2026-10-19": 9}}, captures=[]), "captures")):
        try:
            formats.judge(bad)
            ok = False
        except ValueError as e:
            ok = why in str(e)
        check(f"formats refuses a format without {why}", ok)

    weekly_pages(tmp, F, data)
    print(f"\n{'all checks passed' if not FAILS else str(len(FAILS)) + ' check(s) failed'}")
    sys.exit(1 if FAILS else 0)


def weekly_pages(tmp, F, data):
    """The weekly pages added 28 Oct 2026: headlines, in or out, the move, four posts, the press, and the refresh rules."""
    import datetime as dt
    import brief, headlines, scout, signals, trendstate, zipfile  # noqa: E401
    now = dt.datetime(2026, 10, 28, 12, tzinfo=dt.timezone.utc)
    gn = (b'<rss><channel><item><title>Katseye sells out arena - Billboard</title><link>https://b.example/1</link>'
          b'<pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate><source url="https://b.example">Billboard</source></item>'
          b'<item><title>Katseye sells out arena - Billboard</title><link>https://b.example/2</link><pubDate>Tue, 27 Oct 2026 11:00:00 GMT</pubDate>'
          b'<source url="https://b.example">Billboard</source></item>'
          b'<item><title>Old story - Variety</title><link>https://v.example/1</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>'
          b'<source url="https://v.example">Variety</source></item></channel></rss>')
    feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Doechii tour news</title><link href="https://p.example/1"/>'
            b'<published>2026-10-26T09:00:00Z</published></entry></feed>')
    hl = headlines.run({"niche": "Music", "entities": [{"name": "Katseye"}, {"name": "Doechii"}],
                        "outlets": [{"name": "Pitchfork", "rss": "https://p.example/feed"}]}, 7, now,
                       fetcher=lambda u: feed if "p.example" in u else gn)
    check("headlines strip the outlet from Google News titles", hl["headlines"][0]["title"] in ("Katseye sells out arena", "Doechii tour news"), hl["headlines"][:1])
    check("headlines keep one per story and drop old ones", hl["read"] == 2 and hl["outlets"] == 2, (hl["read"], hl["outlets"]))
    check("headlines count each tracked name", hl["by_name"] == {"Katseye": 1, "Doechii": 1}, hl["by_name"])
    failing = headlines.run({"niche": "Music", "entities": []}, 7, now, fetcher=lambda u: (_ for _ in ()).throw(OSError("offline")))
    check("headlines record a failed feed instead of crashing", failing["read"] == 0 and failing["feeds"][0]["outcome"] == "failed")

    wk = ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]
    rows = [dict(trendstate.classify(list(zip(wk, [1000, 1000, 1100, 1000, 3000])), 500), name="Katseye", source="wikipedia"),
            dict(trendstate.classify(list(zip(wk, [9000, 4000, 3000, 2600, 2000])), 500), name="Doechii", source="wikipedia"),
            dict(trendstate.classify([(f"w{k:02d}", v) for k, v in enumerate([30000] + [2000] * 8 + [2050])], 500), name="Flat After Spike", source="wikipedia")]
    b = brief.build([{"rows": rows, "saturated": [{"name": "Coffee", "source": "bluesky"}]}], hl, None, {"entities": [{}, {}]}, dt.date(2026, 10, 28))
    check("brief puts a jump in and a fall out", [r["name"] for r in b["came_in"]] == ["Katseye"] and [r["name"] for r in b["went_out"]] == ["Doechii"],
          (b["came_in"], b["went_out"]))
    check("brief never calls a flat name gone after one spike", all(r["name"] != "Flat After Spike" for r in b["went_out"]))
    check("brief move names the jump with its number", b["move"]["name"] == "Katseye" and "%" in b["move"]["why"], b["move"])
    check("brief gives four posts, each with a receipt", len(b["posts"]) <= 4 and b["posts"] and all(p["receipt"] for p in b["posts"]), b["posts"])
    check("brief counts headlines for the cover", b["counts"]["headlines"] == 2 and "2 headlines" in b["voice"]["cover"], b["voice"]["cover"])
    empty = brief.build([], None, None, None, dt.date(2026, 10, 28))
    check("brief says plainly when nothing moved", empty["move"]["name"] is None and empty["posts"] == [], empty["move"])

    tpl = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "starter-edition.json")))
    gate = {"reason": "No ledger rows yet, so the rule stays closed."}
    bdata = dict(data, brief=b, radar_gate=gate)
    probs, _ = copycheck.check(tpl, bdata, False)
    check("starter edition passes the copy check with a brief", probs == [], probs)
    probs, _ = copycheck.check(tpl, dict(data, brief=empty, radar_gate=gate), False)
    check("starter edition passes the copy check when nothing moved", probs == [], probs)
    loud = {"read": 1, "outlets": 1, "by_name": {}, "top_outlets": [["Billboard", 1]],
            "headlines": [{"title": "Billboard predicted Doechii would win, ahead of the curve", "outlet": "Billboard",
                           "published": "2026-10-28T09:00", "names": []}]}
    xr = {"recent_posts": 1, "top_by_lane": {"music": [{"author": "@someone", "text": "I predicted this weeks ago",
                                                         "posted_at": "2026-10-27T10:00", "metrics": {"views": 5000}}]}}
    rss_only = brief.build([], hl, None, {"entities": [{"name": "Katseye"}], "outlets": [{"rss": "https://p.example/feed"}]})
    check("brief takes an outlet given only as a feed address", rss_only["posts"] is not None)
    down = brief.build([], dict(failing, feeds=[{"feed": "niche: Music", "outcome": "failed"}]), None, None)
    check("a failed headline read shows FAILED, not 0", down["stamps"]["headlines"] == "FAILED" and "didn't come back" in down["voice"]["cover"], down["stamps"])
    check("no headline read shows NOT READ, not 0", brief.build([], None, None, None)["stamps"]["headlines"] == "NOT READ")
    full = brief.build([], dict(hl, by_name={"Katseye": 77, "Doechii": 90}, capped=["Katseye"]), None, None)
    check("a name whose search hit the 100 cap is marked, not ranked", full["press"]["most_named"][0] == ["Katseye", 77, True]
          and "at least" in full["voice"]["press"], full["press"]["most_named"])
    many = (b'<rss><channel>' + b''.join(b'<item><title>Story %d - Billboard</title><pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate>'
            b'<source url="https://b.example">Billboard</source></item>' % i for i in range(100)) + b'</channel></rss>')
    hit = headlines.run({"niche": "Music", "entities": [{"name": "Katseye"}]}, 7, now, fetcher=lambda u: many)
    check("headlines note a name search that hit Google News's 100 cap", hit["capped"] == ["Katseye"], hit["capped"])
    check("long post titles are cut at a word and keep their closing quote", render._cut("Answer @a: “" + "word " * 40 + "”", 60).endswith("…”"))
    for label, b2 in (("headline", brief.build([], loud, None, {"entities": [{"name": "Doechii"}]})),
                      ("X post", brief.build([], None, xr, {"entities": [{"name": "Doechii"}]}))):
        probs, _ = copycheck.check(tpl, dict(data, brief=b2, radar_gate=gate), False)
        check(f"a quoted {label} saying 'predicted' stays out of the narration", probs == [] and b2["posts"], (probs, b2["voice"]["posts"]))
    for th in (render.THEME, render.KAIJU):
        ctx = render.Ctx(dict(th), bdata, {}, {"brand": "THE SCOUT", "series": "TEST", "date": "TODAY", "mark": "M"})
        for kind in ("states", "move", "posts", "press"):
            s = next(x for x in tpl["slides"] if x["kind"] == kind)
            h = render.page(s, 2, 8, ctx, ctx.deck)
            check(f"render builds {kind} ({'poster' if th is render.KAIJU else 'plain'})", '<div id="frame"' in h and "Katseye" in h if kind != "press" else "BILLBOARD" in h)
        h = render.page(next(x for x in tpl["slides"] if x["kind"] == "states"), 2, 8, render.Ctx(dict(th), dict(data, brief=empty), {}, ctx.deck), ctx.deck)
        check("render states page explains an empty week", "Nothing on your list jumped" in h)

    sat_dir = os.path.join(tmp, "sat")
    os.makedirs(os.path.join(sat_dir, "raw", "bluesky"))
    mon = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    big = {(mon - dt.timedelta(weeks=k)).isoformat(): 10000 for k in range(1, 12)}
    json.dump({"weekly": big}, open(os.path.join(sat_dir, "raw", "bluesky", "coffee.json"), "w"))
    bp = os.path.join(tmp, "sat-basket.json")
    json.dump({"entities": [{"name": "Coffee", "bluesky": "coffee"}]}, open(bp, "w"))
    trendstate.SATURATED.clear()
    got = trendstate.from_signals([(bp, sat_dir)])
    check("trendstate won't judge a series stuck at Bluesky's ceiling", got == [] and trendstate.SATURATED and trendstate.SATURATED[0]["name"] == "Coffee")

    rdir = os.path.join(tmp, "refresh")
    path = os.path.join(rdir, "raw", "wikipedia", "watch.json")
    os.makedirs(os.path.dirname(path))
    old = {"weekly": {"2026-09-28": 10, "2026-10-05": 20}, "fetched_at": "2026-10-06T00:00:00+00:00"}
    json.dump(old, open(path, "w"))
    seen = []
    saved = signals.FETCH["wikipedia"]
    signals.FETCH["wikipedia"] = lambda q, a, b: seen.append(a) or {"weekly": {"2026-10-05": 25, "2026-10-12": 30}}
    try:
        signals.pull({"start": "2023-01-02", "end": "2026-10-20", "entities": [{"name": "watch", "wikipedia": "Watch"}]}, rdir, workers=1)
    finally:
        signals.FETCH["wikipedia"] = saved
    merged = json.load(open(path))["weekly"]
    check("weekly refresh fetches only the recent weeks", seen and seen[0] == dt.date(2026, 9, 14), seen)
    check("weekly refresh keeps history and replaces recent weeks", merged == {"2026-09-28": 10, "2026-10-05": 25, "2026-10-12": 30}, merged)
    # fetched on an earlier day this week: last week was already complete, so the saved data is reused
    mon = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    json.dump(dict(old, fetched_at=mon.isoformat() + "T08:00:00+00:00"), open(path, "w"))
    seen.clear()
    signals.FETCH["wikipedia"] = lambda q, a, b: seen.append(a) or {"weekly": {}}
    try:
        recs = signals.pull({"start": "2023-01-02", "entities": [{"name": "watch", "wikipedia": "Watch"}]}, rdir, workers=1)
        json.dump(dict(old, fetched_at=(mon - dt.timedelta(days=2)).isoformat() + "T08:00:00+00:00"), open(path, "w"))
        signals.pull({"start": "2023-01-02", "entities": [{"name": "watch", "wikipedia": "Watch"}]}, rdir, workers=1)
    finally:
        signals.FETCH["wikipedia"] = saved
    check("data fetched this week is reused", recs and recs[0]["outcome"] == "cached", recs)
    check("data fetched last weekend is refreshed, so last week isn't judged as a part-week", len(seen) == 1, seen)
    xa, xb = os.path.join(tmp, "xa.jsonl"), os.path.join(tmp, "xb.jsonl")
    with open(xa, "w") as f:
        f.write(json.dumps({"id": "1", "text": "Katseye tour", "posted_at": "2026-10-13T10:00:00+00:00"}) + "\n")
    with open(xb, "w") as f:
        f.write(json.dumps({"id": "2", "text": "Katseye again", "posted_at": "2026-10-20T10:00:00+00:00"}) + "\n")
        f.write(json.dumps({"id": "3", "text": "Rolling Stone cover", "posted_at": "2026-10-20T11:00:00+00:00"}) + "\n")
    got = trendstate.from_x([xa, xb], ["Katseye"], minimum=1, today=dt.date(2026, 10, 28))
    check("X states count every weekly pull, on the tracked names only", [r["name"] for r in got] == ["Katseye"], got)

    ep = os.path.join(tmp, "old-edition.json")
    json.dump({"date": "22 OCT 2026", "slides": [{"id": "cover", "kind": "cover", "headline": "Music"}, {"id": "gate", "kind": "quote"}]}, open(ep, "w"))
    scout.refresh_edition(ep, has_x=True)
    ed = json.load(open(ep))
    check("refresh dates the edition today", ed["date"] == dt.date.today().strftime("%d %b %Y").upper(), ed["date"])
    check("refresh adds the weekly pages to an older edition", [s["kind"] for s in ed["slides"]][:5] == ["cover", "states", "move", "posts", "press"],
          [s["kind"] for s in ed["slides"]])
    check("refresh adds the X count to the cover when X is read", any("x_posts" in i["value"] for i in ed["slides"][0]["stamps_row"]))
    json.dump({"date": "27 OCT 2026", "slides": [{"id": "cover", "kind": "cover", "stamps_row": [
        {"value": "{{brief.counts.headlines|thousands}}", "label": "HEADLINES"}]}]}, open(ep, "w"))
    scout.refresh_edition(ep, has_x=False)
    check("refresh moves an older cover to stamps that can say FAILED", json.load(open(ep))["slides"][0]["stamps_row"][0]["value"] == "{{brief.stamps.headlines}}")

    lite = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lite")
    z = zipfile.ZipFile(os.path.join(lite, "scout-lite.zip"))
    check("Scout Lite ZIP matches lite/SKILL.md", z.namelist() == ["scout-lite/SKILL.md"] and
          z.read("scout-lite/SKILL.md").decode() == open(os.path.join(lite, "SKILL.md")).read())


if __name__ == "__main__":
    main()
