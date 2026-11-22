#!/usr/bin/env python3
"""dream writes memory only through the canonical checkout's link.

From 2026-11-20 the live ~/.config/opencode/memory pointed into a merged
feature worktree, and the daily dream pass kept staging lessons there, so the
2026-11-20 pending file split across two trees. dream's default memory path is
the live link; it must resolve to $DOTFILES_DIR/memory (default
~/dotfiles/memory) before dream writes, and a drifted link is refused.

Each case builds a throwaway HOME. --promote --yes with nothing pending reaches
the write path without a model or a session store. An explicit --memory (what
the other dream tests use) is not checked.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DREAM = ROOT / "bin" / "dream"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def memory_tree(at: Path) -> Path:
    (at / "memory" / "learnings" / "pending").mkdir(parents=True)
    (at / "memory" / "core").mkdir()
    return at / "memory"


def dream(home: Path, *args: str, canonical: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    env.pop("DOTFILES_DIR", None)
    if canonical is not None:
        env["DOTFILES_DIR"] = str(canonical)
    return subprocess.run([sys.executable, str(DREAM), *args], capture_output=True, text=True, env=env, timeout=120)


def home_linked_to(tmp: Path, name: str, memory: Path) -> Path:
    home = tmp / name
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "memory").symlink_to(memory)
    return home


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dream-canonical-") as raw:
        tmp = Path(raw)
        canonical = tmp / "dotfiles"
        canon_memory = memory_tree(canonical)
        stale_memory = memory_tree(tmp / "merged-feature-worktree")

        # 1. The 2026-11-20 state: the live link points into another checkout.
        home = home_linked_to(tmp, "home-drifted", stale_memory)
        r = dream(home, "--promote", "--yes", canonical=canonical)
        check(r.returncode != 0, f"a drifted memory link is refused (got {r.returncode})")
        check("not the canonical" in r.stderr, "the refusal says the link is not the canonical checkout's")
        check(str(canonical) in r.stderr, "the refusal names the canonical checkout")

        # 2. The same, with DOTFILES_DIR unset: the default is ~/dotfiles.
        r = dream(home, "--promote", "--yes")
        check(r.returncode != 0, f"by default a link outside ~/dotfiles is refused (got {r.returncode})")

        # 3. The canonical link works as before.
        home = home_linked_to(tmp, "home-canonical", canon_memory)
        r = dream(home, "--promote", "--yes", canonical=canonical)
        check(r.returncode == 0, f"the canonical link is accepted (got {r.returncode}: {r.stderr.strip()[-200:]})")

        # 4. An explicit --memory is the caller's choice and is not checked.
        r = dream(tmp / "home-drifted", "--promote", "--yes", "--memory", str(stale_memory), canonical=canonical)
        check(r.returncode == 0, f"an explicit --memory is not checked (got {r.returncode}: {r.stderr.strip()[-200:]})")

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
