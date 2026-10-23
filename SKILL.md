---
name: the-scout
description: The Scout's measurement and publishing kit. Pulls behaviour data with history for any niche (Wikipedia, Hacker News, Bluesky, GitHub keyless; YouTube, Spotify, ElevenLabs with keys), flags changes with one fixed rule, backtests it against past breakouts, keeps dated calls and a lead-time ledger, finds early-mover accounts, and renders a poster-style 4:5 edition with PDF, audio and video from real evidence. Radar claims stay locked until the ledger proves one. Use for the weekly Scout run, a new niche's first edition, a backtest, making or resolving calls, or asking whether the Scout is ahead of the press.
---

# The Scout: measure, prove, publish

Everything runs through `scripts/`, Python standard library plus Chrome or Chromium and ffmpeg. It works the same from Codex or Claude Code. New users start with `START_HERE.md`.

## The weekly loop

1. **Monday, automatic.** `python3 scripts/run.py --weekly` (schedule it with launchd or cron if you want it hands-free). It refreshes the audit and compares it with last week, pulls backfilled signals, resolves calls against the benchmark press (a hit becomes a ledger row), scans discovery feeds, renders the scoreboard edition from numbers only, and makes the audio and video. Read `RUN.json` first.
2. **The written edition.** Read the audit changes, `signals/signals-analysis.json` (anything `flagged_recent`), `discovery.json`, `terms.json`, `tools.json`, the ledger and the calls score. Write `slides.json` in the `kaiju` theme (patterns: `templates/starter-edition.json`, `starters/*/edition.json`), with a `voiceover` line per slide. Render with `run.py --slides ... --media`. Look at every frame, fix crops and crowding, render again. A hero drawing for the cover can come from `illustrate.py image` in the poster style; it is always credited as an illustration and never stands in for evidence.
3. **Make calls.** `python3 scripts/calls.py propose discovery.json OUTLETS.json proposals.json` drops anything the benchmark press already named. For each lead worth calling, write a dated, falsifiable row in the calls ledger with a 30, 60 or 90 day resolve date. Calls with weak relevance to the profile's decisions are not worth making.
4. **Learn who moves first.** After a backtest or a resolved hit, `python3 scripts/registry.py BACKTEST_DIR REGISTRY.json` credits the accounts that posted before the press. Feed the top Bluesky and Hacker News movers into the signals basket, and X accounts into the Scout profile through its gated browser work.
5. **Hand over.** Say what was captured, what failed, what the gate allows and what's due next. Never post, send or schedule anything new.

## Rules the code enforces

- Numbers enter copy only as placeholders (`{{records}}`, `{{false_label_per_watch|one_in}}`, `{{earliest_comparison|date}}`, `{{radar_gate.reason}}`). A bare digit fails unless the slide lists it in `untraced_ok` with a reason.
- Radar claims ("is rising", "spotted early", "ahead of the press", "predicted") fail while the gate is closed. The gate opens only on a resolved ledger row with a positive lead from a fully enumerated benchmark search.
- Social platforms are never captured live. X, Instagram and TikTok images come from files the Scout saved under `evidence/YYYY-MM-DD/captures/` with a manifest entry.
- Every fetch records ok, failed, skipped or timeout. Nothing missing is zero-filled. Snapshot sources (Hugging Face, Apple Music, kworb, Spotify API) build their own history from the first run and are never shown as backfilled.

## The tools

| Job | Script |
|---|---|
| Journal audit and history | `audit.py`, `run.py` |
| Signals with history, detection, durability | `signals.py pull|analyze|check` |
| Wikipedia backfill for one watch | `pageviews.py` |
| Benchmark press search (sitemaps) | `benchmark.py` |
| Backtest past breakouts | `backtest.py` |
| Discovery leads | `discover.py` |
| New terms nobody supplied: phrases that jumped against their own past (Hacker News, Bluesky seeds, saved X text) | `terms.py` |
| New AI tools to try: Show HN, new GitHub repos, trending Hugging Face, ranked by traction and lane | `tools.py` |
| Calls: propose, novelty, resolve, score | `calls.py` |
| Lead-time ledger and gate | `ledger.py` |
| Early-mover registry | `registry.py` |
| Captures with receipts | `capture.py` |
| Copy check | `copycheck.py` |
| Frames, PDF (`kaiju` poster theme or `scout`) | `render.py` |
| Spoken brief and video (ElevenLabs voice, cached per line; animated intro) | `media.py` |
| Drawings and motion via Higgsfield (Soul images, Kling video), labelled as illustration | `illustrate.py` |
| Self-test, offline | `self_test.py` |

## Writing the edition

The edition has to find things the reader didn't tell it. Every week, open the top of `terms.json` and `tools.json`, trace each lead to its first post, pull its history (`signals.py`), run `calls.py novelty` on it, and put what survives in a "Found by the Scout" section and a "Try this week" section. Open each tool before recommending it and say which ones were tried. Plain slugs match whole slug words only; a name that is also an ordinary word or another company (Gutsy, Jev in Sarajevo) needs its match read before it counts.

Lead with what changed since last week. Grade with ACCEPT and HOLD. A flag is attention, not adoption; say so. A zero channel means nothing collected, not nothing happening. Missing coverage is never decline. Separate facts from interpretation, and end with what's due next: the next call date, the next comparison window, the watch that's closest to a flag.
