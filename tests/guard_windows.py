#!/usr/bin/env python3
"""harness-guard must normalize Windows paths in protected_path, protected_name and in_no_edit."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("harness_guard", str(ROOT / "bin" / "harness-guard"))
_spec = importlib.util.spec_from_loader("harness_guard", _loader)
mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(mod)
mod.HOME = "C:/Users/u"

policy = json.loads((ROOT / "policy" / "permissions.json").read_text())

CASES = [
    ("protected_path .ssh", lambda: mod.protected_path(policy, "C:\\Users\\u\\.ssh\\id_rsa"), "~/.ssh/"),
    ("protected_path .aws", lambda: mod.protected_path(policy, "C:\\Users\\u\\.aws\\credentials"), "~/.aws/"),
    ("protected_name .env", lambda: mod.protected_name(policy, "C:\\Users\\u\\work\\.env", True), ".env"),
    ("in_no_edit memory/core", lambda: mod.in_no_edit(policy, "C:\\Users\\u\\x\\memory\\core\\safety.md"), True),
    ("protected_path app.cs", lambda: mod.protected_path(policy, "C:\\Users\\u\\src\\app.cs"), None),
]


def main():
    failures = 0
    for name, run, expected in CASES:
        actual = run()
        ok = actual == expected
        print(f"{'ok  ' if ok else 'FAIL'} {name}: expected {expected!r}, got {actual!r}")
        failures += not ok
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
