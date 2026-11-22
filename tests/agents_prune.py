#!/usr/bin/env python3
"""bin/sync-harness retires the agent files it rendered and no longer renders.

#41 retired plan-review-deep, review-light and second-opinion, but their
rendered copies stayed in ~/.claude/agents, so Claude Code could still
dispatch them (found 2026-11-21). A file carrying the generated stamp whose
name the policy no longer renders is stale: --apply moves it aside to a
`.retired-<utc>` name Claude Code does not load. A file without the stamp is
the person's and is left alone.
"""
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("sync_harness", str(ROOT / "bin" / "sync-harness"))
_spec = importlib.util.spec_from_loader("sync_harness", _loader)
sync = importlib.util.module_from_spec(_spec)
_loader.exec_module(sync)

FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


policy = json.loads((ROOT / "policy" / "permissions.json").read_text())
rendered = set(sync.render_claude_agents(policy, ROOT))

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    agents = home / ".claude" / "agents"
    agents.mkdir(parents=True)
    for path, text in sync.agents_changes(policy, ROOT, home):
        sync.write_agent(path, text)
    stamp = f"<!-- {sync.GENERATED} from agents/review-light.md. Edit that file and the policy, not this one. -->"
    retired = agents / "review-light.md"
    retired.write_text(f"---\nname: review-light\nmodel: haiku\n---\n{stamp}\n\nold prompt\n")
    mine = agents / "my-own.md"
    mine.write_text("---\nname: my-own\n---\nA prompt I wrote.\n")

    stale = sync.stale_agents(policy, ROOT, home)
    check(stale == [retired], f"only the stamped, unrendered file is stale (got {[p.name for p in stale]})")
    check(all((agents / f"{n}.md") not in stale for n in rendered), "no rendered agent is stale")

    moved = sync.retire_agent(retired)
    check(not retired.exists(), "a retired agent no longer has a .md name Claude Code loads")
    check(moved.exists() and "old prompt" in moved.read_text(), "its text is kept beside it")
    check(not moved.name.endswith(".md"), f"the kept copy is not loadable ({moved.name})")
    check(mine.read_text() == "---\nname: my-own\n---\nA prompt I wrote.\n", "a hand-written agent is untouched")
    check(sync.stale_agents(policy, ROOT, home) == [], "after retiring, nothing is stale")

with tempfile.TemporaryDirectory() as tmp:
    # On a case-insensitive filesystem (macOS default) Review-Deep.md is the
    # rendered review-deep.md; retiring it would remove a live agent.
    home = Path(tmp)
    agents = home / ".claude" / "agents"
    agents.mkdir(parents=True)
    cased = agents / "Review-Deep.md"
    cased.write_text(f"---\nname: review-deep\n---\n<!-- {sync.GENERATED} from agents/review-deep.md. -->\n")
    check(cased not in sync.stale_agents(policy, ROOT, home), "a rendered agent under another case is never stale")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
