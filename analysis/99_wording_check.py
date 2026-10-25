"""Final wording check against HANDOFF section 2 (supply not demand; associations not causes; simulation labels).

Scans the written deliverables and the chart titles in the analysis scripts for risky phrases and writes
outputs/wording_check.txt with every hit and its context, so each one can be checked by hand.
Usage: .venv/bin/python -m analysis.99_wording_check
"""
from __future__ import annotations

import re
from pathlib import Path

FILES = [Path("outputs/summary.md"), Path("outputs/recommendation_inputs.md"), Path("outputs/tables/forecast_README.md"),
         Path("sim/page_template.html"), Path("sim/v3/template.html")] + sorted(Path("analysis").glob("[0-9]*.py"))
PATTERNS = {
    "demand": r"\bdemand\b", "unmet": r"\bunmet\b", "lost riders": r"lost (riders|trips|passengers)",
    "waiting time": r"wait(ing)? time", "revenue": r"\brevenue\b|\bfares?\b", "cause": r"\bcaus(e|es|ed|al)\b",
    "rain reduces": r"rain (reduces|cuts|drives|makes)", "leads to": r"\bleads? to\b", "validation": r"\bvalidat",
    "weather adds no value": r"no (early-warning )?value", "guarantee": r"\bguarantee",
}


def main():
    out = []
    for f in FILES:
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            for name, pat in PATTERNS.items():
                if re.search(pat, line, re.I):
                    out.append(f"{f}:{i} [{name}] {line.strip()[:160]}")
    Path("outputs/wording_check.txt").write_text("\n".join(out) + "\n")
    print(len(out), "hits written to outputs/wording_check.txt")


if __name__ == "__main__":
    main()
