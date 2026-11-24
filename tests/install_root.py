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
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []
EVERY_MODEL = os.path.join(tempfile.gettempdir(), f"install-root-models-{os.getpid()}.txt")
with open(EVERY_MODEL, "w") as _handle:
    _handle.write("claude-agent/opus\nclaude-agent/sonnet\nclaude-agent/haiku\nopencode-go/deepseek-v4.1-flash\n")


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
    # A throwaway HOME has no provider logins, so the real `opencode models`
    # would list no Claude model. Each case says what its machine can reach.
    env.setdefault("DOTFILES_MODELS_AVAILABLE", EVERY_MODEL)
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
        # opencode.json reads each model from a role file; without them opencode
        # silently runs every agent on its default model.
        role_dir = os.path.join(home, ".config", "opencode", "models")
        check(os.path.isfile(os.path.join(role_dir, "reviewer")) and os.path.isfile(os.path.join(role_dir, "lead")),
              "the canonical apply writes the role model files")
        r = run(os.path.join(canonical, "install.cs"), home, "--check", canonical=canonical)
        check(r.returncode == 0, f"--check after apply finds no drift, role files included (got {r.returncode}: {r.stdout.strip()[-200:]})")
        with open(os.path.join(role_dir, "reviewer")) as handle:
            reviewer = handle.read()
        check(reviewer.startswith("claude-agent/opus"), f"the reviewer file holds the default profile's reviewer (got {reviewer!r})")
        os.unlink(os.path.join(role_dir, "reviewer"))
        r = run(os.path.join(canonical, "install.cs"), home, "--check", canonical=canonical)
        check(r.returncode == 1 and "reviewer" in r.stdout, f"--check reports a missing role file as drift (got {r.returncode})")

        # 6b. A machine that cannot reach a role's model fails the install, loudly.
        home = fresh_home(tmp, "home-no-claude")
        listing = os.path.join(tmp, "no-claude.txt")
        with open(listing, "w") as handle:
            handle.write("opencode-go/deepseek-v4.1-flash\n")
        os.environ["DOTFILES_MODELS_AVAILABLE"] = listing
        try:
            r = run(os.path.join(canonical, "install.cs"), home, canonical=canonical)
        finally:
            del os.environ["DOTFILES_MODELS_AVAILABLE"]
        check(r.returncode == 2 and "not available" in r.stdout,
              f"install fails when this machine cannot reach a role's model (got {r.returncode})")

        # 7. With DOTFILES_DIR unset, the default is ~/dotfiles under the HOME in use.
        home = fresh_home(tmp, "home-default")
        default = os.path.join(home, "dotfiles")
        subprocess.run(["git", "clone", "-q", ROOT, default], check=True)
        shutil.copy2(os.path.join(ROOT, "install.cs"), os.path.join(default, "install.cs"))
        r = run(os.path.join(default, "install.cs"), home)
        check(r.returncode == 0, f"apply from ~/dotfiles succeeds by default (got {r.returncode}: {r.stderr.strip()[-200:]})")
        r = run(os.path.join(stray, "install.cs"), fresh_home(tmp, "home-default-stray"))
        check(r.returncode == 3, f"by default another clone is refused (got {r.returncode})")

        # 8. bin/harness-guard is gone (2026-11-24), so the PreToolUse hook an earlier
        # install wrote into ~/.claude/settings.json would point at nothing: the
        # install removes exactly that entry, keeps the rest, and backs the file up.
        home = fresh_home(tmp, "home-settings")
        claude = os.path.join(home, ".claude")
        os.makedirs(claude)
        guard = os.path.join(home, ".config", "opencode", "bin", "harness-guard")
        settings = {"model": "opus", "hooks": {
            "PreToolUse": [{"matcher": "Bash|Edit", "hooks": [{"type": "command", "command": guard, "timeout": 10}]},
                           {"matcher": "Write", "hooks": [{"type": "command", "command": "/opt/mine/check.sh"}]}],
            "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "bash", "args": ["/x/t.sh"]}]}]}}
        with open(os.path.join(claude, "settings.json"), "w") as handle:
            json.dump(settings, handle)
        r = run(os.path.join(canonical, "install.cs"), home, canonical=canonical)
        after = json.load(open(os.path.join(claude, "settings.json")))
        pre = after.get("hooks", {}).get("PreToolUse", [])
        check(r.returncode == 0 and not any(h.get("command") == guard for e in pre for h in e.get("hooks", [])),
              f"install removes the harness-guard hook (got {r.returncode}: {pre})")
        check(any(h.get("command") == "/opt/mine/check.sh" for e in pre for h in e.get("hooks", []))
              and after["hooks"].get("PostToolUse") and after.get("model") == "opus",
              "install keeps every other hook and setting")
        check(any(n.startswith("settings.json.bak-") for n in os.listdir(claude)), "install backs settings.json up first")
        r = run(os.path.join(canonical, "install.cs"), home, canonical=canonical)
        check(len([n for n in os.listdir(claude) if n.startswith("settings.json.bak-")]) == 1,
              "a second install leaves settings.json alone (no second backup)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
