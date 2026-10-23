# The Scout

A trend scout that has to prove it. The Scout watches the things you care about (artists, products, tools, shows) using public behaviour data with years of history, flags real changes with one fixed rule, makes dated calls, and keeps score in a lead-time ledger. Every week it turns that into a poster-style edition: a PDF, a spoken brief and a short video. It can't claim you spotted something early until its own ledger proves it.

## Get started

Double-click **Install The Scout**, answer three questions, and your first edition opens in about 10 minutes. `START_HERE.md` walks through it, including the one-time "right-click › Open" step your Mac may ask for.

Prefer the terminal?

```bash
bash install.sh
```

Using Codex or Claude Code? After installing, ask: "Set up The Scout for indie games, watching Balatro, Peak and Blue Prince." `SKILL.md` is the playbook your agent follows.

## What you need

- A Mac with Python 3.9 or later (the installer offers to add it).
- Google Chrome, or another Chromium browser such as Edge or Brave, to draw the pages.
- ffmpeg for the audio and video (optional; the installer adds it if you have Homebrew).
- An internet connection. No accounts or keys are required; the keys listed in `START_HERE.md` switch on extra sources.

## Where the data comes from

| Source | What it shows | History |
|---|---|---|
| Wikipedia pageviews | attention: who people are reading about | back to 2015 |
| Bluesky search | conversation: who people are posting about | back to 2023 |
| Hacker News | what builders are discussing | back to 2007 |
| GitHub stars | adoption of open-source tools | the repo's lifetime |
| Hugging Face, Apple Music charts, Spotify charts via kworb | snapshots that build their own history from your first run | from your first run |
| YouTube, Spotify artist data | switch on with your own free keys | varies |

## Commands

| Step | Command |
|---|---|
| Guided first edition | `python3 scripts/scout.py setup` |
| Ready-made starter (music, games, ai-tools) | `python3 scripts/scout.py starter music` |
| Refresh your latest edition | `python3 scripts/scout.py run` |
| Whole check, every option | `python3 scripts/run.py --out OUT [--run-dir JOURNAL] [--signals S.json --pull] [--calls C.jsonl --outlets O.json] [--slides SLIDES] [--media] [--discover]` |
| Signals | `python3 scripts/signals.py check|pull|analyze BASKET OUT` |
| Discovery leads | `python3 scripts/discover.py OUT.json` |
| Calls: propose, check novelty, resolve, score | `python3 scripts/calls.py propose|novelty|resolve|score ...` |
| Benchmark press search | `python3 scripts/benchmark.py OUTLETS.json QUERY.json OUT.json` |
| Lead-time ledger gate | `python3 scripts/ledger.py LEDGER.jsonl` |
| Backtest against past breakouts | `python3 scripts/backtest.py CASES.json OUTLETS.json OUT` |
| Early-mover registry | `python3 scripts/registry.py BACKTEST_DIR REGISTRY.json` |
| Render frames and PDF | `python3 scripts/render.py SLIDES AUDIT FRAMES [--captures C] [--data name=path]` |
| Audio and video | `python3 scripts/media.py SLIDES AUDIT FRAMES [--data name=path]` |
| Cover drawing and motion (Higgsfield key) | `python3 scripts/illustrate.py image "PROMPT" OUT --param aspect_ratio=3:4` |
| Self-test, offline | `python3 scripts/self_test.py` |

A `local.json` beside this file can set default paths for your own machine. Keep it to yourself.

## What it never does

Post, send, schedule anything without you, sign in to your accounts, accept cookies, get round a paywall or login, capture social platforms live, or describe something as rising, early or predicted before its ledger proves it.

## Limits

- Live screenshots are flaky by nature. A page that hangs is stopped and recorded as a timeout, and its slide shows a labelled gap.
- A flag means attention moved, not that something is a hit. Bluesky is the earliest and the noisiest source, so treat a Bluesky-only flag as a lead to check.
- Screenshots of other sites carry their owners' rights. Credits are printed on every image; check them before posting publicly.

---

The Scout, by Fireclub.
