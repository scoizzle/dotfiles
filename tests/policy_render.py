#!/usr/bin/env python3
"""bin/sync-harness must render agents/implement-deep.md from policy/permissions.json."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("sync_harness", str(ROOT / "bin" / "sync-harness"))
_spec = importlib.util.spec_from_loader("sync_harness", _loader)
sync = importlib.util.module_from_spec(_spec)
_loader.exec_module(sync)

policy = json.loads((ROOT / "policy" / "permissions.json").read_text())
targets = sync.repo_targets(policy, ROOT)
path = ROOT / "agents" / "implement-deep.md"
if path not in targets:
    print("FAIL: repo_targets does not render agents/implement-deep.md")
    sys.exit(1)
if targets[path] != path.read_text():
    print("FAIL: agents/implement-deep.md drifted from policy/permissions.json")
    sys.exit(1)
print("ok")
