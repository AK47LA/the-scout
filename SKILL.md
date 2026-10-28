---
name: the-scout
description: The Scout's measurement and publishing kit. Pulls behaviour data with history for any niche (Wikipedia, Hacker News, Bluesky, GitHub keyless; YouTube, Spotify, ElevenLabs with keys), flags changes with one fixed rule, backtests it against past breakouts, keeps dated calls and a lead-time ledger, finds early-mover accounts, and renders a poster-style 4:5 edition with PDF, audio and video from real evidence. Radar claims stay locked until the ledger proves one. Use for the weekly Scout run, a new niche's first edition, a backtest, making or resolving calls, or asking whether the Scout is ahead of the press.
---

# The Scout: measure, prove, publish

Everything runs through `scripts/`, Python standard library plus Chrome or Chromium and ffmpeg. It works the same from Codex or Claude Code. New users start with `START_HERE.md`.

## The weekly loop

1. **Monday.** `python3 scripts/run.py --weekly`, or `scout.py run` for a guided edition. It runs when someone runs it; schedule it with launchd or cron only if the owner asks. It refreshes the audit and compares it with last week, adds the newest weeks of backfilled signals, reads the week's headlines (`headlines.py`), resolves calls against the benchmark press (a hit becomes a ledger row), scans discovery feeds, puts every tracked item in or out (`trendstate.py`), writes the week in one place (`brief.py`: in and out, the move, four posts, the press), renders the edition from numbers only, and makes the audio and video. Read `RUN.json` first.
2. **X pass, in the account window (opt-in).** X is where new terms show up first, and reading more than public posts needs a signed-in browser. Before the first pass, tell the owner plainly: reading their bookmarks and following list means you drive their signed-in X, X's rules don't allow automated access, and it can put their account at risk. Only with their explicit yes, set `"x_owner_consent": true` (and `"x_owner"`) in local.json; without it `xpass.py` skips those pages and plans only search and trend pages. `xpass.py plan x/DATE` builds the read list (trending and news tabs, Latest searches for the names they track and any `x_searches` in local.json, open calls, found terms and tools, and registry early movers whose own profile links an X account). `xpass.py reserve x/DATE` asks the site gate (`x_gate` in local.json) before any signed-in page; denied means stop. Read each page read only, appending to `posts.jsonl`, `trends.jsonl` and `pages.jsonl`, then `xpass.py ingest x/DATE`. `terms.py --x-dir x` compares the newest pass with the earlier ones. Never sign in, like, follow, reply, repost, bookmark or DM.
3. **The written edition.** Read the audit changes, `signals/signals-analysis.json` (anything `flagged_recent`), `discovery.json`, `terms.json`, `tools.json`, the ledger and the calls score. Write `slides.json` in the `kaiju` theme (patterns: `templates/starter-edition.json`, `starters/*/edition.json`), with a `voiceover` line per slide. Render with `run.py --slides ... --media`. Look at every frame, fix crops and crowding, render again. A hero drawing for the cover can come from `illustrate.py image` in the poster style; it is always credited as an illustration and never stands in for evidence.
4. **Make calls.** `python3 scripts/calls.py propose discovery.json OUTLETS.json proposals.json` drops anything the benchmark press already named. For each lead worth calling, write a dated, falsifiable row in the calls ledger with a 30, 60 or 90 day resolve date. Calls with weak relevance to the profile's decisions are not worth making.
5. **Learn who moves first.** After a backtest or a resolved hit, `python3 scripts/registry.py BACKTEST_DIR REGISTRY.json` credits the accounts that posted before the press. Feed the top Bluesky and Hacker News movers into the signals basket, and X accounts into the Scout profile through its gated browser work.
6. **Hand over.** Say what was captured, what failed, what the gate allows and what's due next. Never post, send or schedule anything new.

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
| This week's headlines: Google News search for the niche and each name, plus basket `outlets` feeds | `headlines.py` |
| The week in one place: in and out, the move, four posts, the press, from this run's files only | `brief.py` |
| New terms nobody supplied: phrases that jumped against their own past (Hacker News, Bluesky seeds, saved X text) | `terms.py` |
| New AI tools to try: Show HN, new GitHub repos, trending Hugging Face, ranked by traction and lane | `tools.py` |
| X pass: read list, site gate, saved post text for `terms.py --x-dir` | `xpass.py plan|reserve|ingest|status` |
| Formats to steal: early or late from creator counts, first on Reels, keep and make yours | `formats.py` |
| Calls: propose, novelty, resolve, score | `calls.py` |
| Lead-time ledger and gate | `ledger.py` |
| Early-mover registry | `registry.py` |
| Captures with receipts | `capture.py` |
| Copy check | `copycheck.py` |
| Frames, PDF (`kaiju` poster theme or `scout`) | `render.py` |
| Spoken brief and video (ElevenLabs voice, cached per line; animated intro) | `media.py` |
| Drawings and motion via Higgsfield (Soul images, Kling video), labelled as illustration | `illustrate.py` |
| News-show cut: narrated beats with motion, captures, Higgsfield b-roll, synced captions, music bed | `show.py` |
| Frame-accurate headless Chrome (standard library only) | `cdp.py` |
| Self-test, offline | `self_test.py` |

## X, every week

X is where frontier AI, music and culture news breaks first, so every edition reads it. `xpublic.py pull WATCHLIST OUT` reads each watchlist account's public posts without a login; `xpublic.py report OUT --history DIR` ranks the window's biggest posts per lane, finds the words and names that jumped against earlier weeks, and separates new from resurfacing. The watchlist (`x_watchlist` in local.json) only holds handles whose profile was read and matched; never guess one. When a browser is linked and the owner has switched it on (`x_owner_consent`), `xpass.py` adds the owner's bookmarks and following. If both routes fail, `templates/grok-x-prompt.md` asks Grok, and every link it returns is checked before use. Lead with what was first posted in the window, check each launch date, and quote posts verbatim with their counts (the `xpost` scene).

## Distil

The point is less noise, not more. Every edition opens with one page of at most five things that matter, each with why it matters to the reader and the move. Every later page is a pillar (agents, security, models, creative AI, music, entertainment and culture, graphs with history, found this month, tools, content, open calls, what to watch) and must be current or carry its date. Cut anything older than 30 days from the lead pages, merge repeats, and drop a page that doesn't change a decision. The X search list grows itself: `xkeywords.py update` adds up to six of this week's strongest new names and terms, and drops any that go quiet for three weeks.

## In or out

Every edition says what is just trending and what is going out, not only what might come. `trendstate.py` puts every tracked item on one rule: NEW, JUST TRENDING, RISING, PEAKING, STEADY, FADING or GONE, judged on the latest complete week against its own history (X weeks are scaled when partial). Put a page near the front with what came in and what went out, with the numbers behind each call. X history builds week on week, so early editions will call too much NEW; check first-launch dates before saying new.

## Formats to steal

A format is a way of making posts that many creators copy (one move per video in numbered levels, a then-and-now cut, a sound with a set action). A topic is what they talk about. When the edition recommends a format, it says three things the reader can act on:
- **Early or late.** Count distinct creators who posted the format each week, per platform, from saved captures only (the X pass, and TikTok or Instagram search pages read in the signed-in browser under the site gate, saved under `evidence/YYYY-MM-DD/captures/` with a manifest entry). Write the counts into `formats.json` (pattern: `templates/formats-example.json`) and run `python3 scripts/formats.py formats.json formats-state.json`. It uses the In or out rule and turns it into EARLY, NOW, HOLD, LATE or UNKNOWN. With no counts the stage is unknown; say so instead of guessing.
- **First on Reels.** Flagged only when the format is early on TikTok and a Reels search was read this week and came back quiet. An unchecked platform is missing coverage, not an opening.
- **Keep and make yours.** What stays the same (the mechanics that made it work: structure, length, recurring character, cover, sound) and what the reader changes (the subject, the skill, the voice, the brand). `formats.py` refuses a format without both lists.
Never say a format will go viral.

## The show

`show.py SHOW.json OUT` turns an edition into a narrated news-desk video in the same poster style, plus one file per part for posting. Scenes: rundown, bumper, sting, evidence (a capture with its source), tool (the tool's own demo footage or page, with its real stats), decide, bars, bignum, timeline, post, card, clip. Use each tool's own launch film or README media for demos, credited on screen. English only on screen: no Chinese, Japanese or Korean characters, in copy or in footage; use a tool's English cut or an excerpt without them (the copy check enforces the copy side); captures carry their source and date; Higgsfield clips are always tagged ILLUSTRATION. Every line and on-screen number goes through the copy check.

## Writing the edition

End every edition with a "For your content" page: up to four posts people in the reader's niche will share, built from this edition's finds. Mix the kinds: a format to ride, a tool to film, a hook, a public call. Each gets its receipt, a platform and a ready first line. A format to ride also gets its `formats.py` verdict in one line (early, now, late or unknown, with the creator counts behind it), the first-on-Reels flag when it applies, a keep list and a make-yours list, and the reader's version beat by beat: the opening shot, the text on screen and the caption. Mark one as the lead. A hook that claims a result is only true once the reader has done it; say so. Never generate a real person's likeness, and keep client or confidential work out. Every edition carries the brand from local.json ("brand") and the weekday and date it was made, on screen and in its file names. Newest first. Headline slots go to things first seen in the last 30 days, each with its first-seen date; anything older is labelled established (or OLD NEWS on a slide) and kept out of the lead. The edition has to find things the reader didn't tell it. Every week, open the top of `terms.json` and `tools.json`, trace each lead to its first post, pull its history (`signals.py`), run `calls.py novelty` on it, and put what survives in a "Found by the Scout" section and a "Try this week" section. Open each tool before recommending it and say which ones were tried. Plain slugs match whole slug words only; a name that is also an ordinary word or another company (Gutsy, or Arc inside "search") needs its match read before it counts.

## New, not obvious: the social set

The brief keeps the rigour; the posts have to be worth stopping for. Hold every slide to one test: would a smart person in the reader's world say "obvious, people have done that for years"? Keep only alpha, meaning a verified, surprising result with its numbers plus a format, tool or play to copy this week, and read the owner's own bookmarks first. Interview the owner for their take on each signal and keep their words; never write an opinion for them. For the carousel, set `"minimal": true` (no masthead, stamps or source lines; sources go in a `caption`). Use the `take_cover` kind (big words with `cutouts`, either receipt crops or `figure` cut-outs) and the `take` kind (headline, one receipt as `image_path` with an optional exact `crop`, `code` or a quoted `post`, then `what` and the first-person `take`; a corner `sticker` cut-out is optional). Write in plain words for the owner's audience and put no caveat lines on social. The number in a line must match the number visible in its receipt. A long show for the owner alone can drop the owner's name and say "your take"; public cuts keep the brand. An owner can keep their own edition playbook as a separate skill beside this one.

Lead with what changed since last week. Grade with ACCEPT and HOLD. A flag is attention, not adoption; say so. A zero channel means nothing collected, not nothing happening. Missing coverage is never decline. Separate facts from interpretation, and end with what's due next: the next call date, the next comparison window, the watch that's closest to a flag.
