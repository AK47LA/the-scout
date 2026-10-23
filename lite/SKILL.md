---
name: scout-lite
description: The Scout without installing anything. A weekly trend brief for any niche, built in Claude with web search - what is genuinely new this week, what is rising and what is going out, the tools worth an hour, and four posts to make - every claim with its link and date. Use when someone asks for their weekly Scout, a trend report or a trend radar for their industry.
---

# Scout Lite

A weekly brief that finds what's new in a niche, with receipts. It runs inside Claude with web search: no install, no keys. The full Scout (the rest of this repo) adds years of data history, X reading, charts, a narrated show and a lead-time ledger.

## Set up once

Ask the person, then keep the answers in this project's memory or the chat:
1. Their niche, in their words (for example "independent music marketing" or "AI tools for video editors").
2. Their role and what they decide each week (what to post, what to sign, what to build, what to pitch).
3. 10 to 40 people and outlets they trust: X handles, newsletters, sites. Only add a handle after opening its profile.
4. What to leave out (clients, confidential work, topics they don't cover).

## Every week

1. Search the last 7 days only. Use the date filters in your searches and check every result's date. Work through the trusted list first, then the niche's trade press, then X, Reddit, Hacker News and YouTube as they fit the niche. Search for launches, deals, lawsuits, chart moves, viral formats and phrases people started using this week.
2. Check launch dates. Something first released more than 30 days ago is not news this week, even if people are talking about it. Label it "resurfacing" with its original date, or leave it out.
3. Judge in or out for each candidate, with the numbers you can find: NEW (first appeared this week), RISING (clearly more mentions, views or searches than in recent weeks), PEAKING, FADING (well below its peak and falling) or GONE. If you have no number, say what the state rests on, or leave the state out.
4. Distil. Keep at most five things that would change one of the person's decisions this week. Merge repeats. Cut anything that only adds noise.
5. Write the brief in this order:
   - **The week on one page:** five items at most. Each one gets a line on what happened (with its date and link), why it matters to this person, and the move.
   - **In or out:** new, rising, fading, gone, each with its number and source.
   - **Pillars:** one short section for each area that moved this week, for example agents, models, creative tools, the person's industry, culture. Skip any area with nothing new.
   - **Try this week:** up to five new tools, with what each does, its launch date and its link. Say plainly that you haven't run them.
   - **For your content:** four posts people in this niche will share, built only from this week's finds. Make one the lead. Give each a ready first line, the receipt and a platform. A hook that claims a result is only true once the person has done it.
   - **What to watch next:** dated things coming up.

## Rules

- Every fact carries its link and date. A number with no source doesn't go in. Write "unsure" rather than guess.
- Quote posts word for word, with the author and date. Don't paraphrase a quote.
- Newest first. Nothing older than 30 days in a lead slot.
- English only on the page.
- Never invent a quote, a number, a launch date or an opinion for the person. Never use a real person's likeness.
- "Rising" and "fading" need the numbers behind them. Never claim the brief spotted something early unless you can show the earlier dated brief that said so.
- Keep client and confidential work out.
- Draft only: nothing is posted or sent.

## Where the full Scout goes further

Years of history from Wikipedia, Bluesky, Hacker News and GitHub, so "rising" is measured against the item's own past. X read weekly from a verified watchlist. Dated calls checked against the press. A designed PDF, a narrated news show and a 9:16 cut. Install it from this repo with `bash install.sh`.
