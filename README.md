# The Scout

A trend scout that has to prove it. Each time you run it (once a week is the idea), The Scout reads this week's headlines for your niche, the public posts of X accounts you choose, and years of public behaviour data for the things you track. It says what came in and what went out with the numbers behind each call, picks the move for the week, suggests four posts to make, and turns it into a poster-style edition: a PDF, plus a spoken brief and video when ffmpeg is installed. With Codex or Claude Code it can go further: new terms and tools nobody told it about, a narrated news show, a 9:16 cut, and dated calls scored in a lead-time ledger, so it can't claim you spotted something early until the ledger proves it.

## Get started

Click **Code › Download ZIP**, unzip it, double-click **Install The Scout**, answer a few questions, and your first edition opens in about 10 minutes. `START_HERE.md` walks through it, including the one-time **Privacy & Security › Open Anyway** step your Mac asks for.

Prefer the terminal?

```bash
bash install.sh
```

No install? Use **Scout Lite** in Claude: upload `lite/scout-lite.zip` under Customize › Skills, turn on web search, and say "Run my Scout for this week." See `lite/README.md`.

Using Codex or Claude Code? After installing, ask: "Set up The Scout for indie games, watching Balatro, Peak and Blue Prince." `SKILL.md` is the playbook your agent follows.

## What you need

- A Mac with Python 3.9 or later. The Python that comes with macOS works; the installer offers to add it if it's missing.
- Google Chrome, or another Chromium browser such as Edge or Brave, to draw the pages.
- ffmpeg for the audio and video (optional; the installer adds it if you have Homebrew).
- An internet connection. No accounts or keys are required; the keys listed in `START_HERE.md` switch on extra sources.

## Where the data comes from

| Source | What it shows | History |
|---|---|---|
| Headlines: Google News search for your niche and each name, plus any outlet feeds you add | what the press wrote this week | last 7 days, every run |
| X, public posts from accounts you name at setup (each checked first; no login) | where news breaks first: labs, builders, artists, press | builds week on week |
| Wikipedia pageviews | attention: who people are reading about | back to 2015 |
| Bluesky search | conversation: who people are posting about | back to 2023 |
| Hacker News | what builders are discussing | back to 2007 |
| GitHub stars | adoption of open-source tools | the repo's lifetime |
| Hugging Face, Apple Music charts, Spotify charts via kworb | snapshots that build their own history from your first run | from your first run |
| Chartmetric artist history (Spotify listeners and followers, TikTok, YouTube, Instagram) | streaming and social reach, with history | your own Chartmetric API key |
| YouTube, Spotify artist data | switch on with your own free keys | varies |

## Commands

| Step | Command |
|---|---|
| Guided first edition | `python3 scripts/scout.py setup` |
| Ready-made starter (music, marketing, games, ai-tools) | `python3 scripts/scout.py starter music` |
| Refresh your latest edition (adds only the newest weeks of data) | `python3 scripts/scout.py run` |
| This week's headlines | `python3 scripts/headlines.py BASKET.json OUT.json` |
| The week in one place: in and out, the move, four posts, the press | `python3 scripts/brief.py OUT.json --states STATES.json --headlines HEADLINES.json` |
| Whole check, every option | `python3 scripts/run.py --out OUT [--run-dir JOURNAL] [--signals S.json --pull] [--calls C.jsonl --outlets O.json] [--slides SLIDES] [--media] [--discover]` |
| Signals | `python3 scripts/signals.py check|pull|analyze BASKET OUT` |
| Discovery leads | `python3 scripts/discover.py OUT.json` |
| X this week, no login | `python3 scripts/xpublic.py pull WATCHLIST.json OUT` then `report OUT --history DIR` |
| New terms and new AI tools nobody told it about | `python3 scripts/terms.py OUT.json` and `python3 scripts/tools.py OUT.json` |
| In or out: new, rising, peaking, fading, gone | `python3 scripts/trendstate.py signals BASKET SIGNALS_DIR OUT.json` or `x POSTS.jsonl OUT.json` |
| Formats to steal: early or late, first on Reels, keep and make yours | `python3 scripts/formats.py formats.json formats-state.json` |
| News-show video and 9:16 cut | `python3 scripts/show.py SHOW.json OUT` |
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

Post, send, schedule anything without you, sign in to your accounts, accept cookies, or get round a paywall or login. It calls something rising or fading only with the measured numbers on the page, and never claims it spotted something early or predicted it before its ledger proves it. X is read from public posts only. An agent can also read your own bookmarks and following list in your signed-in browser, but only after you switch it on (`"x_owner_consent": true` in local.json): X's rules don't allow automated access, so it can put your account at risk.

## Limits

- Live screenshots are flaky by nature. A page that hangs is stopped and recorded as a timeout, and its slide shows a labelled gap.
- A flag means attention moved, not that something is a hit. Bluesky is the earliest and the noisiest source, so treat a Bluesky-only flag as a lead to check.
- Screenshots of other sites carry their owners' rights. Credits are printed on every image; check them before posting publicly.
- The no-login X route uses a free public service (api.fxtwitter.com). If it stops answering, `templates/grok-x-prompt.md` asks Grok instead, and every link is checked before use.
- Each starter comes with an X watchlist (`starters/*/x-watchlist.json`) and checked outlet feeds. Add the people you trust; setup checks every handle you type before keeping it.
- Bluesky search counts stop at 10,000 a week, so very big names can't be judged on Bluesky. The edition says so instead of calling a state.
- It runs when you run it. Double-click **Make my Scout edition** once a week, or schedule it yourself.
- Headlines come from Google News's public feeds, which are for personal use. Keep the edition for your own research.

MIT licensed: see `LICENSE`.

---

The Scout, by Fireclub.
