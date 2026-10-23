# Ask Grok for the week on X (fallback when the public pull or the signed-in pass can't run)

Paste into Grok, fill the brackets, and paste the JSON answer back to the Scout. Every link is checked before it is used.

```text
You have live access to X. Today is [WEEKDAY DATE]. I work in [NICHE], and I need what is genuinely new this week, from the people who see it first.

1. Accounts. Look at who @[YOUR HANDLE] follows. Then list the 40 X accounts that post the earliest, most useful news in [NICHE] right now. For each: handle, name, what they cover, and one post of theirs from the last 7 days with its link.
2. What is new. From the last 72 hours only, list the 25 most important new things in [NICHE]. For each: name, one line on what it is, the first post about it (link, author, date and time), its likes, reposts and views as shown, and whether it is brand new this week or older and resurfacing (give the original date if older).
3. Rising terms. 10 words or phrases people started using this week that they were not using a month ago, with 2 example post links each.

Rules: only real posts with real links that you can open. If you are not sure of a link, a date or a number, write "unsure". Answer as one JSON object with keys "accounts", "new_this_week" and "rising_terms".
```
