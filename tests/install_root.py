#!/usr/bin/env python3
"""install.cs applies only from the canonical checkout, unless told otherwise.

On 2026-11-20 install.cs ran from a feature worktree. Its root comes from the
compile-time source path, so every harness link moved into that worktree, and
stayed there for 32 hours after the branch merged. A second plain clone would
have done the same. The canonical checkout is $DOTFILES_DIR (the variable
bootstrap.sh already clones to), default ~/dotfiles; anything else needs
--from <that checkout>.

Each case copies the working install.cs into a temp clone or a linked worktree
of it and installs into a throwaway HOME. DOTNET_CLI_HOME and NUGET_PACKAGES stay
at the real home so the SDK does not do a first-run restore per case; that
writes the SDK's own sentinels under the real ~/.dotnet, and nothing else.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def run(script: str, home: str, *args: str, canonical: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=home)
    # Nothing may steer a write back into the real config.
    for name in ("DOTFILES_DIR", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
        env.pop(name, None)
    if canonical is not None:
        env["DOTFILES_DIR"] = canonical
    real = os.path.expanduser("~")
    env.setdefault("DOTNET_CLI_HOME", real)
    env.setdefault("NUGET_PACKAGES", os.path.join(real, ".nuget", "packages"))
    return subprocess.run([script, *args], capture_output=True, text=True, env=env, timeout=600)


def linked_nothing(home: str) -> bool:
    return not os.path.lexists(os.path.join(home, ".config", "opencode", "AGENTS.md")) and \
        not os.path.lexists(os.path.join(home, ".claude", "CLAUDE.md"))


def links_into(home: str, tree: str) -> bool:
    link = os.path.join(home, ".config", "opencode", "AGENTS.md")
    return os.path.realpath(link) == os.path.realpath(os.path.join(tree, "AGENTS.md"))


def fresh_home(tmp: str, name: str) -> str:
    home = os.path.join(tmp, name)
    # On Linux a file-based app keeps its build cache in the local app-data
    # folder (~/.local/share); in an empty HOME that folder is missing and
    # `dotnet` dies with "Unable to determine a temporary directory path"
    # before install.cs runs. macOS uses $TMPDIR, so it never showed there.
    os.makedirs(os.path.join(home, ".local", "share"))
    return home


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="install-root-")
    try:
        canonical = os.path.join(tmp, "dotfiles")
        feature = os.path.join(tmp, "feature")
        stray = os.path.join(tmp, "scratch-clone")
        subprocess.run(["git", "clone", "-q", ROOT, canonical], check=True)
        subprocess.run(["git", "-C", canonical, "worktree", "add", "-q", "--detach", feature], check=True)
        subprocess.run(["git", "clone", "-q", ROOT, stray], check=True)
        for tree in (canonical, feature, stray):
            shutil.copy2(os.path.join(ROOT, "install.cs"), os.path.join(tree, "install.cs"))

        # 1. The 2026-11-20 run: a linked worktree of the canonical checkout.
        home = fresh_home(tmp, "home-worktree")
        r = run(os.path.join(feature, "install.cs"), home, canonical=canonical)
        check(r.returncode == 3, f"apply from a linked worktree exits 3 (got {r.returncode})")
        check("not the canonical checkout" in r.stderr, "the refusal says it is not the canonical checkout, on stderr")
        check("--from" in r.stderr, "the refusal names the flag that overrides it")
        check(linked_nothing(home), "a refused apply links nothing")

        # 2. A second plain clone is refused the same way.
        home = fresh_home(tmp, "home-stray")
        r = run(os.path.join(stray, "install.cs"), home, canonical=canonical)
        check(r.returncode == 3, f"apply from another plain clone exits 3 (got {r.returncode})")
        check(linked_nothing(home), "a refused apply from another clone links nothing")

        # 3. --check is read-only and allowed anywhere; it warns.
        r = run(os.path.join(feature, "install.cs"), home, "--check", canonical=canonical)
        check(r.returncode == 1, f"--check from a worktree reports drift, exit 1 (got {r.returncode})")
        check("not the canonical checkout" in r.stderr, "--check from a worktree warns")
        check(linked_nothing(home), "--check from a worktree writes nothing")

        # 4. --from <path> naming the running checkout applies, on purpose.
        home = fresh_home(tmp, "home-from")
        r = run(os.path.join(feature, "install.cs"), home, "--from", feature, canonical=canonical)
        check(r.returncode == 0, f"--from <this checkout> applies (got {r.returncode}: {r.stderr.strip()[-200:]})")
        check(links_into(home, feature), "--from links into the checkout it names")

        # 5. --from naming a different checkout is refused: it cannot redirect the root.
        home = fresh_home(tmp, "home-from-other")
        r = run(os.path.join(feature, "install.cs"), home, "--from", stray, canonical=canonical)
        check(r.returncode == 3, f"--from <another checkout> is refused (got {r.returncode})")
        check(linked_nothing(home), "a mismatched --from links nothing")

        # 6. The canonical checkout applies, via DOTFILES_DIR (how CI and bootstrap run).
        home = fresh_home(tmp, "home-canonical")
        r = run(os.path.join(canonical, "install.cs"), home, canonical=canonical)
        check(r.returncode == 0, f"apply from DOTFILES_DIR succeeds (got {r.returncode}: {r.stderr.strip()[-200:]})")
        check(links_into(home, canonical), "the canonical apply links into the canonical checkout")

        # 7. With DOTFILES_DIR unset, the default is ~/dotfiles under the HOME in use.
        home = fresh_home(tmp, "home-default")
        default = os.path.join(home, "dotfiles")
        subprocess.run(["git", "clone", "-q", ROOT, default], check=True)
        shutil.copy2(os.path.join(ROOT, "install.cs"), os.path.join(default, "install.cs"))
        r = run(os.path.join(default, "install.cs"), home)
        check(r.returncode == 0, f"apply from ~/dotfiles succeeds by default (got {r.returncode}: {r.stderr.strip()[-200:]})")
        r = run(os.path.join(stray, "install.cs"), fresh_home(tmp, "home-default-stray"))
        check(r.returncode == 3, f"by default another clone is refused (got {r.returncode})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
