#!/usr/bin/env python3
"""bin/models resolves each role's model per person and per machine.

Friends use this repo with other subscriptions (2026-11-22), so the repo names
roles, never model ids. Resolution: the repo's default profile, then the
profile the person picks, then their machine's untracked
~/.config/opencode/models.local.json. `apply` writes one file per role, which
opencode.json reads through {file:}. opencode 2.3.2 silently drops a model whose
file is missing, so `check` fails on that and on any model this machine
cannot reach. A local file can never put the reviewer in the implementor's
family while the set has more than one family; a single-family set defaults
to a fresh same-model review, and a person may make that stricter ("stop").
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "bin" / "models"
ROLES = ("lead", "implementor", "reviewer", "advisor", "verifier", "explore", "drafter")
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def run(home: Path, *args: str, available: list[str] | None = None) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(MODELS), "--home", str(home), *args]
    if available is not None:
        listing = home / "available.txt"
        listing.write_text("\n".join(available) + "\n")
        argv += ["--available", str(listing)]
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def home_with(tmp: Path, name: str, local: dict | None = None) -> Path:
    home = tmp / name
    (home / ".config" / "opencode").mkdir(parents=True)
    if local is not None:
        (home / ".config" / "opencode" / "models.local.json").write_text(json.dumps(local))
    return home


def resolved(home: Path) -> dict:
    return json.loads((home / ".config" / "opencode" / "models.resolved.json").read_text())


def role_file(home: Path, role: str) -> str:
    return (home / ".config" / "opencode" / "models" / role).read_text()


EVERYTHING = [
    "claude-agent/opus", "claude-agent/sonnet", "claude-agent/haiku",
    "opencode-go/deepseek-v4.1-flash", "xai/grok-4.7",
]

with tempfile.TemporaryDirectory() as raw:
    tmp = Path(raw)

    # 1. No local file: the repo's default profile, one file per role.
    home = home_with(tmp, "default")
    r = run(home, "apply")
    check(r.returncode == 0, f"apply with no local file succeeds (got {r.returncode}: {r.stderr.strip()[-200:]})")
    files = sorted(p.name for p in (home / ".config" / "opencode" / "models").iterdir()) if r.returncode == 0 else []
    check(files == sorted(ROLES), f"apply writes one file per role (got {files})")
    defaults = json.loads((ROOT / "models" / "roles.json").read_text())
    profile = json.loads((ROOT / "models" / "profiles" / f"{defaults['default_profile']}.json").read_text())
    check(all(role_file(home, role) == profile["roles"][role] for role in ROLES) if files else False,
          "each role file holds the default profile's model, with no newline")
    check(resolved(home)["review_mode"] == "cross-family" if files else False,
          "the default profile mixes families, so review is cross-family")
    r = run(home, "check", available=EVERYTHING)
    check(r.returncode == 0, f"check passes on a fresh apply (got {r.returncode}: {r.stdout.strip()[-200:]})")

    # 2. A friend picks another profile; a machine overrides one role.
    home = home_with(tmp, "friend", {"profile": "go-only", "roles": {"explore": "opencode-go/deepseek-v4.1-flash#high"}})
    r = run(home, "apply")
    check(r.returncode == 0, f"a chosen profile applies (got {r.returncode}: {r.stderr.strip()[-200:]})")
    if r.returncode == 0:
        go = json.loads((ROOT / "models" / "profiles" / "go-only.json").read_text())
        check(role_file(home, "lead") == go["roles"]["lead"], "the chosen profile's model fills an unset role")
        check(role_file(home, "explore") == "opencode-go/deepseek-v4.1-flash#high", "the machine's override wins")
        check(resolved(home)["review_mode"] == "fresh-same-model",
              "one family resolves to a fresh same-model review by default")

    # 3. The person may make single-family review stricter.
    home = home_with(tmp, "strict", {"profile": "go-only", "review": {"single_family": "stop"}})
    r = run(home, "apply")
    check(r.returncode == 0 and resolved(home)["review_mode"] == "stop", "single_family 'stop' is honoured")

    # 4. A local file cannot put the reviewer in the implementor's family in a mixed set.
    home = home_with(tmp, "weaken", {"roles": {"reviewer": "opencode-go/deepseek-v4.1-flash#high"}})
    r = run(home, "apply")
    check(r.returncode != 0 and "implementor's family" in r.stderr,
          f"a same-family reviewer in a mixed set is refused (got {r.returncode})")
    check(not (home / ".config" / "opencode" / "models").exists(), "a refused apply writes no role files")

    # 5. Bad input is refused, not guessed.
    for name, local, marker in (
        ("unknown profile", {"profile": "nope"}, "no profile 'nope'"),
        ("unknown role", {"roles": {"boss": "claude-agent/opus"}}, "unknown role 'boss'"),
        ("unknown key", {"rolez": {}}, "unknown key 'rolez'"),
        ("bad model id", {"roles": {"lead": "opus"}}, "provider/model"),
        ("bad review mode", {"review": {"single_family": "anything"}}, "single_family"),
    ):
        home = home_with(tmp, name.replace(" ", "-"), local)
        r = run(home, "apply")
        check(r.returncode != 0 and marker in r.stderr, f"{name} is refused (got {r.returncode}: {r.stderr.strip()[-120:]})")

    # 6. check catches what opencode would silently drop.
    home = home_with(tmp, "drift")
    run(home, "apply")
    (home / ".config" / "opencode" / "models" / "reviewer").unlink()
    r = run(home, "check", available=EVERYTHING)
    check(r.returncode != 0 and "reviewer" in r.stdout, "a missing role file fails check")
    run(home, "apply")
    r = run(home, "check", available=[m for m in EVERYTHING if not m.startswith("claude-agent/")])
    check(r.returncode != 0 and "not available" in r.stdout, "a model this machine cannot reach fails check")
    (home / ".config" / "opencode" / "models" / "lead").write_text("xai/grok-4.7")
    r = run(home, "check", available=EVERYTHING)
    check(r.returncode != 0 and "lead" in r.stdout, "a hand-edited role file that no longer matches fails check")

    # 7. Every tracked profile resolves and keeps the family rule.
    for path in sorted((ROOT / "models" / "profiles").glob("*.json")):
        home = home_with(tmp, f"profile-{path.stem}", {"profile": path.stem})
        r = run(home, "apply")
        check(r.returncode == 0, f"profile {path.stem} applies (got {r.returncode}: {r.stderr.strip()[-160:]})")

    # 8. dream drafts with the drafter role, not a hard-coded model.
    home = home_with(tmp, "dream", {"profile": "claude-only"})
    run(home, "apply")
    env = dict(os.environ, HOME=str(home))
    env.pop("DREAM_MODEL", None)
    r = subprocess.run([sys.executable, str(ROOT / "bin" / "dream"), "--help"], capture_output=True, text=True, env=env, timeout=60)
    # argparse wraps help text mid-id ("claude-" / "agent/haiku"), so compare without whitespace.
    check(role_file(home, "drafter") in "".join(r.stdout.split()),
          "dream's default model is this machine's drafter role")

    # 9. Review of 248ffb4 (Opus): the lead writes diffs too.
    home = home_with(tmp, "lead-same", {"roles": {"lead": "opencode-go/deepseek-v4.1-flash#high",
                                                   "reviewer": "opencode-go/deepseek-v4.1-flash#high",
                                                   "implementor": "claude-agent/sonnet"}})
    r = run(home, "apply")
    check(r.returncode != 0 and "lead's family" in r.stderr,
          f"a reviewer in the lead's non-Claude family is refused in a mixed set (got {r.returncode})")

    # 10. Family comes from the vendor token anywhere in the id; an unknown vendor is refused.
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("models_mod", str(MODELS))
    spec = importlib.util.spec_from_loader("models_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    for model, want in (("amazon-bedrock/anthropic.claude-opus-4", "anthropic"),
                        ("opencode/claude-sonnet-5", "anthropic"),
                        ("claude-agent/claude-opus-4-8", "anthropic"),
                        ("opencode/gpt-6", "openai"),
                        ("opencode-go/glm-5.3-flash", "zhipu"),
                        ("opencode-go/deepseek-v4.1-flash#low", "deepseek")):
        check(mod.family(model) == want, f"family({model}) is {want} (got {mod.family(model)})")
    home = home_with(tmp, "unknown-vendor", {"roles": {"explore": "opencode/big-pickle"}})
    r = run(home, "apply")
    check(r.returncode != 0 and "unknown model family" in r.stderr, f"an unknown vendor is refused (got {r.returncode})")

    # 11. check catches a stale models.resolved.json, not only stale role files.
    home = home_with(tmp, "stale-resolved")
    run(home, "apply")
    (home / ".config" / "opencode" / "models.local.json").write_text('{"profile": "go-only", "review": {"single_family": "stop"}}')
    for role, model in json.loads((ROOT / "models" / "profiles" / "go-only.json").read_text())["roles"].items():
        (home / ".config" / "opencode" / "models" / role).write_text(model)
    r = run(home, "check", available=EVERYTHING)
    check(r.returncode != 0 and "models.resolved.json" in r.stdout, "a stale models.resolved.json fails check")

    # 12. A leftover .models-old from an interrupted apply does not break the next one.
    home = home_with(tmp, "leftover")
    run(home, "apply")
    (home / ".config" / "opencode" / ".models-old").mkdir(parents=True)
    (home / ".config" / "opencode" / ".models-old" / "lead").write_text("x/y")
    check(run(home, "apply").returncode == 0, "apply recovers from a leftover .models-old")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
