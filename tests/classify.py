#!/usr/bin/env python3
"""Regression tests for review-bundle's is_sensitive classifier."""

import importlib.machinery
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "bin", "review-bundle")

_loader = importlib.machinery.SourceFileLoader("review_bundle", PATH)
_spec = importlib.util.spec_from_loader("review_bundle", _loader)
review_bundle = importlib.util.module_from_spec(_spec)
_loader.exec_module(review_bundle)

CASES = [
    ("docs/author-notes.md", False),
    ("docs/plan-csharp-native-migration.md", False),
    ("agents/build.md", True),
    ("policy/permissions.json", True),
    ("src/author.cs", True),
    ("src/PermissionService.cs", True),
    ("db/migrations/001_init.sql", True),
    ("app.slnx", True),
]


def main():
    failures = 0
    for rel, expected in CASES:
        actual = review_bundle.is_sensitive(rel)
        ok = actual == expected
        print(f"{'ok  ' if ok else 'FAIL'} {rel}: expected {expected}, got {actual}")
        if not ok:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
