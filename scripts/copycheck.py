"""Copy check for slides.json: every number traces to data, and radar claims stay locked until the ledger opens.

Numbers enter copy only as placeholders: {{key}}, {{key.sub}}, {{key|pct}}, {{key|one_in}}, {{key|x_in_10}},
{{key|thousands}}. Keys resolve against audit.json figures, then any extra data files (receipt, ledger summary)
passed as name=path. A bare digit in copy fails unless the slide lists it in "untraced_ok" with a reason.
Usage: python3 copycheck.py SLIDES.json AUDIT.json [name=path ...]
"""
import json, re, sys

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*(?:\|\s*([a-z_0-9]+))?\s*\}\}")
DIGITS = re.compile(r"(?<![A-Za-z])\d[\d,.]*")
RADAR = [
    r"\b(is|are|was|were|now)\s+(rising|surging|exploding|accelerating|fading|declining|emerging|trending)\b",
    r"\b(rising|emerging|breakout|accelerating|fading)\s+(trend|signal|theme|scene|format|movement)s?\b",
    r"\b(spotted|caught|saw|detected|flagged)\b.{0,40}\b(early|first|before)\b",
    r"\bahead of (the )?(press|market|curve|trades|everyone|competition)\b",
    r"\bpredicted\b",
    r"\b(predicts|forecasts|forecasted)\b",
    r"\b(our|the scout'?s?|scout'?s)\s+(prediction|forecast)s?\b",
    r"\btrend (detected|confirmed|identified)\b",
    r"\b\d+\s+days?\s+(ahead|early|before the)\b",
]
TEXT_FIELDS = {"eyebrow", "headline", "sub", "body", "caption", "label", "note", "title", "text", "quote",
               "attribution", "source", "name", "detail", "pass", "value"}


def lookup(data, path):
    cur = data
    for part in path.split("."):
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
            if isinstance(cur, dict) and set(cur) >= {"value", "source"}:
                cur = cur["value"]
        else:
            raise KeyError(path)
    return cur


def fmt(value, how):
    if isinstance(value, float) and value.is_integer() and how in (None, "", "thousands"):
        value = int(value)
    if how in ("date", "dm"):
        import datetime
        d = datetime.date.fromisoformat(str(value)[:10])
        return f"{d.day} {d.strftime('%B')} {d.year}" if how == "date" else f"{d.day} {d.strftime('%b')}"
    if how in (None, ""):
        return f"{value:,}" if isinstance(value, int) and abs(value) >= 10000 else str(value)
    if how == "pct":
        return f"{round(value * 100)}%"
    if how == "one_in":
        return f"1 in {round(1 / value)}"
    if how == "x_in_10":
        return f"{round(value * 10)} in 10"
    if how == "thousands":
        return f"{value:,}"
    raise ValueError(f"unknown format {how}")


def strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in ("untraced_ok", "image", "images", "kind", "theme", "id", "from", "to", "series", "status", "tone", "context", "signal_source", "names", "signals_key"):
                continue
            yield from strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{path}[{i}]")


def resolve(text, data):
    errors = []

    def sub(m):
        try:
            return fmt(lookup(data, m.group(1)), m.group(2))
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as e:
            errors.append(f"placeholder {m.group(0)} failed: {e}")
            return m.group(0)
    return PLACEHOLDER.sub(sub, text), errors


def check(slides, data, gate_open):
    problems, rendered = [], []
    for i, s in enumerate(slides.get("slides", []), 1):
        ok = {str(x.get("value") if isinstance(x, dict) else x) for x in s.get("untraced_ok", [])}
        for k in s.get("untraced_ok", []):
            if isinstance(k, dict) and not k.get("reason"):
                problems.append(f"slide {i}: untraced_ok {k.get('value')} needs a reason")
        for path, text in strings(s):
            bare = PLACEHOLDER.sub(" ", text)
            for d in DIGITS.findall(bare):
                d = d.rstrip(".,")
                if d and d not in ok:
                    problems.append(f"slide {i} {path}: number {d!r} is not traced. Use a placeholder or list it in untraced_ok with a reason.")
            out, errs = resolve(text, data)
            problems += [f"slide {i} {path}: {e}" for e in errs]
            # A backtest is a retrospective test, not a live call: allowed only where it says so in the sentence.
            retro = s.get("context") == "backtest" and re.search(r"\bbacktest|\bwould have\b", out, re.I)
            if not gate_open and not retro:
                for pat in RADAR:
                    m = re.search(pat, out, re.I)
                    if m:
                        problems.append(f"slide {i} {path}: radar claim {m.group(0)!r} while the ledger gate is closed")
            rendered.append((i, path, out))
    return problems, rendered


def load_data(audit_path, extras):
    with open(audit_path) as f:
        audit = json.load(f)
    data = dict(audit["figures"])
    data["radar_gate"] = audit.get("radar_gate", {})
    for e in extras:
        name, path = e.split("=", 1)
        with open(path) as f:
            data[name] = [json.loads(l) for l in f if l.strip()] if path.endswith(".jsonl") else json.load(f)
    return audit, data


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        slides = json.load(f)
    audit, data = load_data(sys.argv[2], sys.argv[3:])
    problems, _ = check(slides, data, audit.get("radar_gate", {}).get("open", False))
    for p in problems:
        print("FAIL", p)
    print("copy check passed" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
