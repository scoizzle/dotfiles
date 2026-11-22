#!/usr/bin/env python3
"""sync-harness writes the account's home only from the canonical checkout.

Same mistake class as install.cs on 2026-11-20: a feature checkout's
`sync-harness --apply` renders that branch's agents, permissions and hook into
~/.claude for every session. The canonical checkout is install.cs's:
$DOTFILES_DIR, default ~/dotfiles. --check, --scope repo, and an explicit
throwaway --home stay allowed.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYNC = ROOT / "bin" / "sync-harness"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def sync(home: Path, *args: str, canonical: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), DOTFILES_DIR=str(canonical))
    return subprocess.run([sys.executable, str(SYNC), *args], capture_output=True, text=True, env=env, timeout=300)


with tempfile.TemporaryDirectory() as raw:
    tmp = Path(raw)
    home = tmp / "home"
    (home / ".claude").mkdir(parents=True)
    elsewhere = tmp / "dotfiles"  # the canonical checkout is somewhere else

    r = sync(home, "--scope", "home", "--apply", canonical=elsewhere)
    check(r.returncode == 3, f"--apply to the account's home from a non-canonical checkout exits 3 (got {r.returncode})")
    check("not the canonical checkout" in r.stderr, "the refusal says why")
    check(not (home / ".claude" / "agents").exists() and not (home / ".claude" / "settings.json").exists(),
          "a refused apply writes nothing into the home")

    r = sync(home, "--scope", "home", "--apply", "--from", str(tmp / "other"), canonical=elsewhere)
    check(r.returncode == 3, f"--from naming another checkout is refused (got {r.returncode})")

    r = sync(home, "--scope", "home", canonical=elsewhere)
    check(r.returncode != 3 and "not the canonical checkout" in r.stderr, "--check runs anywhere and warns")

    other_home = tmp / "throwaway"
    (other_home / ".claude").mkdir(parents=True)
    r = sync(home, "--scope", "home", "--apply", "--home", str(other_home), canonical=elsewhere)
    check(r.returncode == 0, f"an explicit throwaway --home applies (got {r.returncode}: {r.stderr.strip()[-160:]})")

    r = sync(home, "--scope", "home", "--apply", "--from", str(ROOT), canonical=elsewhere)
    check(r.returncode == 0, f"--from naming this checkout applies (got {r.returncode}: {r.stderr.strip()[-160:]})")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
