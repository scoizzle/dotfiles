#!/usr/bin/env python3
"""Report per-model cost and steps for one run.sh execution.

Compares the stats snapshot taken before the run with the one after it. The
snapshot covers the whole day, so the delta attributes everything spent on that
model between the two snapshots - run.sh takes them around its own work, so this
is the run's cost as long as nothing else used the same model meanwhile.
"""
from __future__ import annotations

import json
import os
import sys


def load(path: str) -> dict[str, dict]:
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for entry in data.get("models") or []:
        ref = entry.get("model") or {}
        key = f"{ref.get('providerID')}/{ref.get('id')}"
        if ref.get("variant"):
            key += f"#{ref['variant']}"
        out[key] = entry
    return out


def main() -> None:
    work = sys.argv[1] if len(sys.argv) > 1 else "."
    before = load(os.path.join(work, "stats-before.json"))
    after = load(os.path.join(work, "stats-after.json"))

    print("cost for this run")
    printed = False
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key, {}), after.get(key, {})
        cost = float(new.get("cost") or 0) - float(old.get("cost") or 0)
        steps = int(new.get("steps") or 0) - int(old.get("steps") or 0)
        if abs(cost) > 1e-9 or steps:
            print(f"  {key:38s} ${cost:7.4f}  {steps:+d} steps")
            printed = True
    if not printed:
        print("  (no delta recorded)")


if __name__ == "__main__":
    main()
