#!/usr/bin/env python3
"""bin/sync-harness must render the opt-in Claude Code sandbox profile.

The profile is security-relevant: a plain --apply must never add, change or
remove the sandbox key, and --apply --sandbox must merge additively, keeping the
user's own paths, permission rules and unrelated settings. Everything acts on a
temporary home; the real one is never read or written.
"""

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYNC = ROOT / "bin" / "sync-harness"
POLICY = json.loads((ROOT / "policy" / "permissions.json").read_text())
EXPECTED_WRITE = ["~/.nuget/packages", "~/.local/share/NuGet"]


def load_sync():
    loader = importlib.machinery.SourceFileLoader("sync_harness", str(SYNC))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

failures = 0


def fail(message):
    global failures
    failures += 1
    print(f"FAIL {message}")


def run(*args):
    return subprocess.run([sys.executable, str(SYNC), *args], capture_output=True, text=True)


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text())


def sandbox_block(text):
    """The source text of the `"sandbox"` value, braces included."""
    start = text.index('"sandbox"')
    depth = 0
    for index in range(text.index("{", start), len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError("unbalanced sandbox block")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --scope sandbox prints one JSON fragment and writes nothing.
        preview = run("--scope", "sandbox")
        if preview.returncode != 0:
            fail(f"--scope sandbox exited {preview.returncode}: {preview.stderr.strip()}")
        try:
            fragment = json.loads(preview.stdout)
        except json.JSONDecodeError as error:
            fail(f"--scope sandbox did not print JSON ({error}): {preview.stdout[:200]!r}")
            print("FAIL")
            return 1
        sandbox = fragment.get("sandbox") or {}
        if sandbox.get("enabled") is not True:
            fail("sandbox.enabled must be true")
        if sandbox.get("allowUnsandboxedCommands") is not False:
            fail("sandbox.allowUnsandboxedCommands must be false")
        filesystem = sandbox.get("filesystem", {})
        allow = filesystem.get("allowWrite", [])
        if allow != EXPECTED_WRITE:
            fail(f"allowWrite must be exactly {EXPECTED_WRITE}: {allow}")
        for path in allow:
            if path == "~/.dotnet" or path.startswith("~/.dotnet/"):
                fail(f"allowWrite grants {path!r}; ~/.dotnet/tools holds binaries "
                     "that later run unsandboxed")
        for path in POLICY["sandbox"]["allow_write"]:
            if path not in allow:
                fail(f"allowWrite is missing {path!r}: {allow}")
        domains = sandbox.get("network", {}).get("allowedDomains", [])
        for domain in POLICY["sandbox"]["allowed_domains"]:
            if domain not in domains:
                fail(f"allowedDomains is missing {domain!r}")
        credentials = sandbox.get("credentials", {})
        if {"name": "GH_TOKEN", "mode": "deny"} not in credentials.get("envVars", []):
            fail(f"credentials.envVars has no deny for GH_TOKEN: {credentials.get('envVars')}")
        if "gh *" not in sandbox.get("excludedCommands", []):
            fail(f"excludedCommands is missing 'gh *': {sandbox.get('excludedCommands')}")
        denied = {item.get("path") for item in credentials.get("files", [])
                  if isinstance(item, dict) and item.get("mode") == "deny"}
        denied |= set(filesystem.get("denyRead", []))
        for entry in POLICY["protected"]["paths"]:
            if entry.rstrip("/") not in denied:
                fail(f"the profile has no read deny for protected path {entry}")

        # A Write(path) rule is inert in Claude Code (only Edit(path) is matched
        # by its file permission checks), so the live-config asks are Edit only.
        native_ask = load_sync().render_native(POLICY)["ask"]
        for wanted in ("Edit(~/.config/opencode/bin/**)", "Edit(~/dotfiles/bin/**)"):
            if wanted not in native_ask:
                fail(f"the native ask rules are missing {wanted}")
        dead = [text for text in native_ask
                if text.startswith(("Write(~/.config/opencode", "Write(~/dotfiles"))]
        if dead:
            fail(f"the native ask rules carry inert Write(path) rules: {dead}")

        home = tmp / "home"
        (home / ".claude").mkdir(parents=True)
        path = home / ".claude" / "settings.json"
        path.write_text(json.dumps({
            "model": "m",
            "permissions": {"deny": ["Bash(mine:*)"]},
            "sandbox": {"filesystem": {"allowWrite": ["~/mine"]}},
        }, indent=2) + "\n")
        before = path.read_text()
        before_sandbox = sandbox_block(before)

        without = run("--scope", "home", "--home", str(home), "--apply")
        if without.returncode != 0:
            fail(f"home --apply without --sandbox exited {without.returncode}: {without.stderr.strip()}")
        if "not managed" not in without.stdout or "sandbox" not in without.stdout:
            fail(f"the home report must say the sandbox profile is not managed: {without.stdout!r}")
        after = path.read_text()
        if '"sandbox"' not in after or sandbox_block(after) != before_sandbox:
            fail("home --apply without --sandbox changed the sandbox block")
        plain = settings(home)
        if plain.get("model") != "m" or "Bash(mine:*)" not in plain["permissions"]["deny"]:
            fail("home --apply without --sandbox dropped the user's own settings")

        opted_in = run("--scope", "home", "--home", str(home), "--apply", "--sandbox")
        if opted_in.returncode != 0:
            fail(f"home --apply --sandbox exited {opted_in.returncode}: {opted_in.stderr.strip()}")
        merged = settings(home)
        block = merged.get("sandbox", {})
        if block.get("enabled") is not True or block.get("allowUnsandboxedCommands") is not False:
            fail(f"home --apply --sandbox did not enable the profile: {block}")
        allow = block.get("filesystem", {}).get("allowWrite", [])
        if "~/mine" not in allow:
            fail(f"the merge dropped the user's own allowWrite entry: {allow}")
        for entry in POLICY["sandbox"]["allow_write"]:
            if entry not in allow:
                fail(f"the merge dropped policy allowWrite entry {entry!r}: {allow}")
        if merged.get("model") != "m" or "Bash(mine:*)" not in merged["permissions"]["deny"]:
            fail("home --apply --sandbox dropped the user's own settings")
        if not list((home / ".claude").glob("settings.json.bak-*")):
            fail("home --apply --sandbox wrote without a backup")

        snapshot = path.read_text()
        again = run("--scope", "home", "--home", str(home), "--apply", "--sandbox")
        if again.returncode != 0 or "drift" in again.stdout:
            fail(f"a second run must report no drift: rc={again.returncode} out={again.stdout!r}")
        if path.read_text() != snapshot:
            fail("a second --apply --sandbox run changed the file")

        # An absent sandbox key stays absent without --sandbox.
        other = tmp / "other"
        (other / ".claude").mkdir(parents=True)
        (other / ".claude" / "settings.json").write_text(json.dumps({"model": "m"}, indent=2) + "\n")
        run("--scope", "home", "--home", str(other), "--apply")
        if "sandbox" in settings(other):
            fail("home --apply without --sandbox added a sandbox key")

    print("FAIL" if failures else "ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
