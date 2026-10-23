# Scout stress test

Audits a Scout trend journal, pulls backfilled Wikipedia attention for a watch, keeps a lead-time ledger, and renders a 1080×1350 carousel from real evidence imagery. Radar claims stay locked until the ledger shows the Scout ahead of the press.

## Install

The skill is one folder. Link it where your agent looks for skills.

Codex:
```bash
ln -s "$PWD" ~/.codex/skills/the-scout
```

Claude Code:
```bash
mkdir -p ~/.claude/skills && ln -s "$PWD" ~/.claude/skills/the-scout
```

Run both commands from inside this folder.

## Requirements

- Python 3.9 or later, standard library only.
- Google Chrome or Chromium for screenshots and PNG rendering. Set `SCOUT_CHROME` if it isn't in the usual place. Without a browser, HTML frames are still written and the receipt says PNGs weren't made.
- Network for Google Fonts, live captures and pageview pulls. The self-test needs none.
- A Scout journal folder: `signals.jsonl`, `history.json`, `watch_state.json`, optionally `trend_history.jsonl` and `panel-progress/latest.json`.

## Commands

| Step | Command |
|---|---|
| First edition for a new niche | see `START_HERE.md` |
| Weekly run (with `local.json`) | `python3 scripts/run.py --weekly` |
| Whole check | `python3 scripts/run.py --out OUT [--run-dir RUN] [--signals S.json --pull] [--basket B.json] [--calls C.jsonl --outlets O.json] [--manifest M] [--slides SLIDES] [--media] [--discover]` |
| Signals | `python3 scripts/signals.py check|pull|analyze BASKET OUT` |
| Backtest | `python3 scripts/backtest.py CASES.json OUTLETS.json OUT` |
| Discovery | `python3 scripts/discover.py OUT.json` |
| Calls | `python3 scripts/calls.py propose|novelty|resolve|score ...` |
| Registry | `python3 scripts/registry.py BACKTEST_DIR REGISTRY.json` |
| Benchmark search | `python3 scripts/benchmark.py OUTLETS.json QUERY.json OUT.json` |
| Ledger gate | `python3 scripts/ledger.py L` |
| Render frames and PDF | `python3 scripts/render.py SLIDES AUDIT FRAMES [--captures C] [--data name=path]` |
| Audio and video | `python3 scripts/media.py SLIDES AUDIT FRAMES [--data name=path]` |
| Illustration and motion | `python3 scripts/illustrate.py image "PROMPT" OUT --param aspect_ratio=3:4` or `video IMAGE_URL "PROMPT" OUT` |
| Self-test | `python3 scripts/self_test.py` |

`local.json` (optional) supplies default paths so `python3 scripts/run.py` works with no arguments. It is machine-specific: don't share it.

## What it never does

Post, send, schedule, sign in, accept cookies, bypass a paywall or gate, capture social platforms live, or describe a trend as rising, early or predicted while the ledger gate is closed.

## Limits

- Live captures are flaky by nature. A page that hangs is stopped and recorded as `timeout`, and its slide shows a labelled gap.
- The pageview rule's false-alarm rate depends on the control basket you choose. Check it on every run.
- Screenshots of other sites carry their owners' rights. Credits are printed on every image; check before posting publicly.

---

The Scout, by Fireclub.
