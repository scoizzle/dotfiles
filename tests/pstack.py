#!/usr/bin/env python3
"""bin/sync-pstack: the model rules, the vocabulary they may use, and install safety.

Four things can rot quietly, so each one has a test here:

  renders   the three tracked rule files match a fresh render of pstack/models.json
  routes    every value is a model this harness actually routes, and no Cursor-only
            slug leaked into the Claude Code or opencode render
  install   a temp-home apply is idempotent, prunes what it recorded, resolves
            pstack's `../../docs` links through the symlink, and refuses to replace
            a skill directory it did not create
  drift     --check exits 1 when a link, a render or a role label moves

Everything runs offline against a synthetic tree, so CI never needs the 7 MB archive.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_loader = importlib.machinery.SourceFileLoader("sync_pstack", str(ROOT / "bin" / "sync-pstack"))
_spec = importlib.util.spec_from_loader("sync_pstack", _loader)
sync = importlib.util.module_from_spec(_spec)
_loader.exec_module(sync)

MODELS = json.loads((ROOT / "pstack" / "models.json").read_text())
# The declared routes, from pstack/models.json. bin/sync-pstack --check compares this
# table to `opencode models`, so it is not a constant that only echoes itself.
ROUTES = MODELS["routes"]
CLAUDE_MODEL = {"opus", "sonnet", "haiku", "fable"}
CLAUDE_EFFORT = {"low", "medium", "high", "xhigh", "max"}

BIN = ROOT / "bin" / "sync-pstack"
USED_ROUTES = sorted({entry.partition("#")[0] for values in MODELS["roles"].values() for entry in values["opencode"]})
STUB_DIR: Path | None = None
NO_OPENCODE: Path | None = None
failed = False


def fail(message: str) -> None:
    global failed
    failed = True
    print(f"FAIL {message}")


def ok(message: str) -> None:
    print(f"ok   {message}")


def make_stub(directory: Path, routes: list[str]) -> Path:
    """A fake `opencode models`, so the live probe is deterministic and never touches
    the machine's real providers."""
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "opencode"
    stub.write_text("#!/bin/sh\nprintf '%s\\n' " + " ".join(routes) + "\n")
    stub.chmod(0o755)
    return directory


def run(*args: str, probe: bool = True) -> subprocess.CompletedProcess:
    """Run the tool with only the stub on PATH, so `shutil.which("opencode")` is ours."""
    path = STUB_DIR if probe else NO_OPENCODE
    env = {**os.environ, "PATH": str(path)}
    return subprocess.run(
        [sys.executable, str(BIN), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def make_tree(root: Path, version: str, names: list[str], extra_label: str | None = None) -> Path:
    (root / "skills").mkdir(parents=True)
    (root / "docs" / "guide").mkdir(parents=True)
    (root / "docs" / "guide" / "01-setup.md").write_text("# setup\n")
    (root / "plugin.json").write_text(json.dumps({"name": "pstack", "version": version}) + "\n")
    for name in names:
        skill = root / "skills" / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: fixture\n---\n# {name}\n")
    labels = list(json.loads((ROOT / "pstack" / "models.json").read_text())["roles"])
    if extra_label:
        labels.append(extra_label)
    shape = "".join(f"{label}: opus high\n" for label in labels)
    setup = root / "skills" / "setup-pstack"
    setup.mkdir(exist_ok=True)
    (setup / "SKILL.md").write_text(
        "---\nname: setup-pstack\ndescription: fixture\n---\n\n"
        "### 5. Write the rule\n\nShape:\n\n"
        "```\n---\ndescription: pstack per-role model choices (overrides skill defaults)\n---\n"
        "# defaults: 3\n# budget: large (xhigh)\n" + shape + "```\n"
    )
    if "setup-pstack" not in names:
        names.append("setup-pstack")
    return root


def make_repo(tmp: Path, version: str = "0.15.46") -> Path:
    repo = tmp / "repo"
    (repo / "pstack").mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "pstack", repo / "pstack", dirs_exist_ok=True)
    (repo / "opencode.json").write_text((ROOT / "opencode.json").read_text())
    pin = json.loads((ROOT / "tools.json").read_text())
    pin["skills"]["pstack"]["version"] = version
    (repo / "tools.json").write_text(json.dumps(pin, indent=2) + "\n")
    return repo


def check_vocabulary() -> None:
    models = json.loads((ROOT / "pstack" / "models.json").read_text())
    renders = sync.render_all(ROOT)
    for harness, rel in sync.RENDER_TARGETS.items():
        committed = ROOT / rel
        if not committed.is_file():
            fail(f"{rel} is missing")
            continue
        if committed.read_text() != renders[rel]:
            fail(f"{rel} drifted from pstack/models.json (run bin/sync-pstack --apply)")
            continue
        ok(f"{rel} matches models.json")

    for label, values in models["roles"].items():
        for entry in values["opencode"]:
            if entry in ("inherit-parent", "auto"):
                continue
            if "/" not in entry:
                fail(f"opencode role {label!r}: {entry!r} is not provider/model[#variant]")
                continue
            route, _, variant = entry.partition("#")
            if route not in ROUTES:
                fail(f"opencode role {label!r}: {route!r} is not a route this harness has")
                continue
            if variant and variant not in ROUTES[route]:
                fail(f"opencode role {label!r}: {route} has no {variant!r} effort")
        for entry in values["claude"]:
            if entry in ("inherit-parent", "auto"):
                continue
            parts = entry.split()
            if len(parts) != 2 or parts[0] not in CLAUDE_MODEL or parts[1] not in CLAUDE_EFFORT:
                fail(f"claude role {label!r}: {entry!r} is not '<model> <effort>' or inherit-parent")
        for entry in values["cursor"]:
            if "/" in entry or "#" in entry or entry != entry.lower() or " " in entry:
                fail(f"cursor role {label!r}: {entry!r} is not a Cursor slug")

    for harness in ("claude", "opencode"):
        text = renders[sync.RENDER_TARGETS[harness]]
        for values in models["roles"].values():
            for slug in values["cursor"]:
                if slug in text:
                    fail(f"{sync.RENDER_TARGETS[harness]} carries the Cursor-only slug {slug!r}")
    if "-fast" in renders[sync.RENDER_TARGETS["opencode"]]:
        fail("the opencode render carries a -fast suffix; opencode has only effort variants")

    # The panel seats must stay multi-vendor: that is the point of the arena.
    for label in ("arena runners", "interrogate reviewers"):
        families = {
            entry.split("/")[0]
            for entry in models["roles"][label]["opencode"]
            if entry not in ("inherit-parent", "auto")
        }
        if len(families) < 2:
            fail(f"role {label!r} has one vendor; the panel loses its point")
        else:
            ok(f"{label}: {len(families)} vendors")
    for label in ("arena runners", "arena cross-judge pool", "interrogate reviewers"):
        gemini = [i for i, entry in enumerate(models["roles"][label]["opencode"]) if "gemini" in entry]
        if not gemini:
            fail(f"role {label!r} lost its Gemini seat")
            continue
        entry = models["roles"][label]["claude"][gemini[0]]
        if entry != "inherit-parent":
            fail(f"role {label!r}: the Gemini seat is {entry!r} in the Claude render; "
                 "the Agent tool has no such model, so it must be inherit-parent")


def check_install(tmp: Path) -> None:
    home = tmp / "home"
    repo = make_repo(tmp)
    tree = make_tree(tmp / "tree", "0.15.46", ["arena", "tdd"])

    before = run("--home", str(home), "--repo", str(repo))
    if before.returncode != 1 or "not installed" not in before.stdout:
        fail(f"--check before apply: rc={before.returncode}\n{before.stdout}{before.stderr}")
    else:
        ok("--check reports a missing install")

    applied = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if applied.returncode != 0:
        fail(f"--apply from a fixture tree: rc={applied.returncode}\n{applied.stdout}{applied.stderr}")
        return
    ok("--apply installs from a local tree")

    links = sorted(p.name for p in (home / ".agents" / "skills").iterdir())
    if links != ["arena", "setup-pstack", "tdd"]:
        fail(f"unexpected ~/.agents/skills: {links}")
    else:
        ok("~/.agents/skills holds one link per skill")

    # pstack's poteto-help reads ../../docs/guide; the link must resolve physically.
    target = home / ".agents" / "skills" / "arena" / ".." / ".." / "docs" / "guide" / "01-setup.md"
    if not target.exists():
        fail(f"{target} does not resolve; the whole tree must be installed, not only skills/")
    else:
        ok("../../docs resolves through the skill symlink")

    again = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if again.returncode != 0 or "already at the pin" not in again.stdout:
        fail(f"second apply: rc={again.returncode}\n{again.stdout}{again.stderr}")
        return
    checked = run("--home", str(home), "--repo", str(repo))
    if checked.returncode != 0:
        fail(f"--check after apply: rc={checked.returncode}\n{checked.stdout}{checked.stderr}")
    else:
        ok("a second apply only repairs links, and --check is green")

    # A skill this tool did not create is never replaced.
    other = tmp / "home-collision"
    (other / ".agents" / "skills" / "tdd").mkdir(parents=True)
    (other / ".agents" / "skills" / "tdd" / "SKILL.md").write_text("mine\n")
    collision = run("--home", str(other), "--repo", str(repo), "--from", str(tree), "--apply")
    if collision.returncode == 0 or "collision" not in collision.stdout:
        fail(f"collision was not refused: rc={collision.returncode}\n{collision.stdout}")
    elif (other / ".agents" / "skills" / "tdd" / "SKILL.md").read_text() != "mine\n":
        fail("collision overwrote a directory this tool did not create")
    else:
        ok("a foreign skill directory is reported, not replaced")

    # A symlink to something else is a collision too (install.cs links repo skills here).
    otherlink = tmp / "home-otherlink"
    (otherlink / ".claude" / "skills").mkdir(parents=True)
    foreign = tmp / "foreign-skill"
    foreign.mkdir()
    os.symlink(foreign, otherlink / ".claude" / "skills" / "tdd")
    linked = run("--home", str(otherlink), "--repo", str(repo), "--from", str(tree), "--apply")
    if linked.returncode == 0 or "other-link" not in linked.stdout:
        fail(f"a foreign symlink was not refused: rc={linked.returncode}\n{linked.stdout}")
    elif os.readlink(otherlink / ".claude" / "skills" / "tdd") != str(foreign):
        fail("a foreign symlink was replaced")
    else:
        ok("a foreign symlink is reported, not replaced")

    # Upgrading drops the links and the tree the old version owned.
    v2 = make_tree(tmp / "tree2", "0.15.47", ["arena"])
    repo2 = make_repo(tmp / "repo2", "0.15.47")
    upgraded = run("--home", str(home), "--repo", str(repo2), "--from", str(v2), "--apply")
    if upgraded.returncode != 0:
        fail(f"upgrade apply: rc={upgraded.returncode}\n{upgraded.stdout}{upgraded.stderr}")
        return
    links = sorted(p.name for p in (home / ".agents" / "skills").iterdir())
    if links != ["arena", "setup-pstack"]:
        fail(f"upgrade left stale links: {links}")
    elif (home / ".agents" / "pstack" / "0.15.46").exists():
        fail("upgrade left the previous tree in place")
    else:
        ok("upgrade prunes the old links and tree")

    # --check notices a moved link, a moved render and a renamed role.
    (home / ".claude" / "skills" / "arena").unlink()
    broken = run("--home", str(home), "--repo", str(repo2))
    if broken.returncode != 1 or "drift" not in broken.stdout:
        fail(f"--check missed a removed link: rc={broken.returncode}\n{broken.stdout}")
    else:
        ok("--check notices a missing link")

    render = repo2 / "pstack" / "opencode" / "pstack-models.md"
    render.write_text(render.read_text() + "swarm workers: nope/nope#xhigh\n")
    rendered = run("--home", str(home), "--repo", str(repo2))
    if rendered.returncode != 1 or "pstack-models.md" not in rendered.stdout:
        fail(f"--check missed a hand-edited render: rc={rendered.returncode}\n{rendered.stdout}")
    else:
        ok("--check notices a hand-edited render")

    renamed = make_tree(tmp / "tree3", "0.15.47", ["arena"], extra_label="loop runners")
    renamed_home = tmp / "home-renamed"
    run("--home", str(renamed_home), "--repo", str(repo2), "--from", str(renamed), "--apply")
    recomputed = run("--home", str(renamed_home), "--repo", str(repo2))
    if recomputed.returncode != 1 or "loop runners" not in recomputed.stdout:
        fail(f"--check missed a role rename upstream: rc={recomputed.returncode}\n{recomputed.stdout}")
    else:
        ok("--check notices a role label upstream added")


def check_rules_and_links(tmp: Path) -> None:
    """The two home rule links are checked, repaired, and never swapped for a plain file."""
    home = tmp / "home-rules"
    repo = make_repo(tmp / "repo-rules")
    tree = make_tree(tmp / "tree-rules", "0.15.46", ["arena"])
    applied = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if applied.returncode != 0:
        fail(f"rules: apply failed: rc={applied.returncode}\n{applied.stdout}{applied.stderr}")
        return
    for rel in (".claude/rules/pstack-models.md", ".cursor/rules/pstack-models.mdc"):
        if not (home / rel).is_symlink():
            fail(f"rules: {rel} was not linked")
    if not failed:
        ok("--apply links both home rule files")

    rule = home / ".claude" / "rules" / "pstack-models.md"
    rule.unlink()
    rule.write_text("pstack wrote this\n")
    swapped = run("--home", str(home), "--repo", str(repo))
    if swapped.returncode != 1 or "real file" not in swapped.stdout:
        fail(f"rules: a plain file where the link was is not reported: rc={swapped.returncode}\n{swapped.stdout}")
    else:
        ok("--check notices a rule file swapped for a plain file")

    refused = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if refused.returncode == 0 or "run ./install.cs" not in refused.stdout:
        fail(f"rules: --apply overwrote a plain file: rc={refused.returncode}\n{refused.stdout}")
    elif rule.read_text() != "pstack wrote this\n":
        fail("rules: --apply changed a file it must not own")
    else:
        ok("--apply refuses to overwrite a plain rule file")

    rule.unlink()
    again = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    green = run("--home", str(home), "--repo", str(repo))
    if again.returncode != 0 or green.returncode != 0:
        fail(f"rules: re-apply did not heal the link: rc={again.returncode}/{green.returncode}\n{green.stdout}")
    else:
        ok("re-apply links the rule file again and --check is green")


def check_dangling_and_state(tmp: Path) -> None:
    """Stale links are reported, and a tampered state.json cannot delete outside the tree."""
    home = tmp / "home-dangling"
    repo = make_repo(tmp / "repo-dangling")
    tree = make_tree(tmp / "tree-dangling", "0.15.46", ["arena"])
    run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")

    old = home / ".agents" / "pstack" / "0.0.9" / "skills" / "ghost"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("---\nname: ghost\ndescription: x\n---\n")
    (home / ".agents" / "pstack" / "0.0.9" / ".dotfiles-pstack").write_text("0.0.9 x\n")
    os.symlink(old, home / ".agents" / "skills" / "ghost")
    dangling = run("--home", str(home), "--repo", str(repo))
    if dangling.returncode != 1 or "another pstack tree" not in dangling.stdout:
        fail(f"a link into a lost tree is not reported: rc={dangling.returncode}\n{dangling.stdout}")
    else:
        ok("--check notices a link into another pstack tree")

    healed = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    green = run("--home", str(home), "--repo", str(repo))
    if healed.returncode != 0 or green.returncode != 0:
        fail(f"a stray link never converges: apply rc={healed.returncode}, check rc={green.returncode}\n"
             f"{healed.stdout}{green.stdout}")
    elif (home / ".agents" / "skills" / "ghost").exists() or (home / ".agents" / "pstack" / "0.0.9").exists():
        fail("--apply did not remove the stray link or its unreferenced tree")
    else:
        ok("--apply removes a stray link and the tree nothing points at")

    # A dangling link into a tree that is gone is ours to repair.
    os.symlink(home / ".agents" / "pstack" / "9.9.9" / "skills" / "gone",
               home / ".agents" / "skills" / "gone")
    dangling = run("--home", str(home), "--repo", str(repo))
    healed = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if dangling.returncode != 1 or "another pstack tree" not in dangling.stdout:
        fail(f"a dangling link is not reported: rc={dangling.returncode}\n{dangling.stdout}")
    elif healed.returncode != 0 or (home / ".agents" / "skills" / "gone").is_symlink():
        fail(f"a dangling link was not repaired: rc={healed.returncode}\n{healed.stdout}")
    else:
        ok("a dangling link is reported and then repaired")

    # An unstamped tree a person put here is kept, even with a link into it.
    mine = home / ".agents" / "pstack" / "9.9.9" / "skills" / "mine"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: mine\ndescription: x\n---\n")
    os.symlink(mine, home / ".claude" / "skills" / "mine")
    kept = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if kept.returncode != 0 or not (home / ".agents" / "pstack" / "9.9.9").is_dir():
        fail(f"an unstamped tree was removed: rc={kept.returncode}\n{kept.stdout}{kept.stderr}")
    elif not (home / ".claude" / "skills" / "mine").is_symlink():
        fail("a person's link into an unstamped tree was deleted")
    else:
        ok("a tree this tool did not stamp, and the link into it, are kept")

    # A broken link inside a tree that still exists is the person's, not ours.
    os.symlink(home / ".agents" / "pstack" / "9.9.9" / "skills" / "typo",
               home / ".claude" / "skills" / "typo")
    run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if not (home / ".claude" / "skills" / "typo").is_symlink():
        fail("a person's broken link inside their own unstamped tree was deleted")
    else:
        ok("a broken link inside a tree that exists is kept")

    # A foreign tree sitting exactly on the pin's path is refused, not replaced.
    foreign_home = tmp / "home-foreign-pin"
    pinned = foreign_home / ".agents" / "pstack" / "0.15.46"
    shutil.copytree(tree, pinned)
    (pinned / "mine.txt").write_text("edit\n")
    refused = run("--home", str(foreign_home), "--repo", str(repo), "--from", str(tree), "--apply")
    if refused.returncode == 0 or "was not written by this tool" not in refused.stdout + refused.stderr:
        fail(f"a foreign tree on the pin's path was accepted: rc={refused.returncode}\n{refused.stdout}")
    elif not (pinned / "mine.txt").is_file() or (pinned / "mine.txt").read_text() != "edit\n":
        fail("a foreign tree on the pin's path was overwritten")
    else:
        ok("a foreign tree on the pin's path is refused and left intact")

    # A symlinked version directory is kept with a note; it must not abort the apply.
    link_home = tmp / "home-symlink-tree"
    (link_home / ".agents" / "pstack").mkdir(parents=True)
    real = tmp / "real-tree"
    shutil.copytree(tree, real)
    (real / ".dotfiles-pstack").write_text("7.7.7 x\n")
    os.symlink(real, link_home / ".agents" / "pstack" / "7.7.7")
    symlinked = run("--home", str(link_home), "--repo", str(repo), "--from", str(tree), "--apply")
    if symlinked.returncode != 0 or "it is a link to another directory" not in symlinked.stdout:
        fail(f"a symlinked version directory aborted apply: rc={symlinked.returncode}\n{symlinked.stdout}")
    elif not (real / ".dotfiles-pstack").is_file():
        fail("a symlinked version directory was deleted through its link")
    else:
        ok("a symlinked version directory is kept, and the apply still finishes")

    victim = home / "victim"
    victim.mkdir()
    os.symlink(home / ".agents" / "pstack" / "0.15.46" / "skills" / "arena", victim / "link")
    state = home / ".agents" / "pstack" / "state.json"
    state.write_text(json.dumps({"version": "../../victim", "commit": "x", "skills": []}) + "\n")
    tampered = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if tampered.returncode != 0:
        fail(f"a tampered state.json broke apply: rc={tampered.returncode}\n{tampered.stdout}{tampered.stderr}")
    elif not victim.is_dir():
        fail("a tampered state.json made the tool delete a directory outside ~/.agents/pstack")
    else:
        ok("a tampered state.json cannot delete outside the pstack tree")

    # A tampered skill name must not be usable as a path segment either.
    state.write_text(json.dumps({"version": "0.15.46", "commit": "x", "skills": ["../../victim/link"]}) + "\n")
    named = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if named.returncode != 0 or not (victim / "link").is_symlink():
        fail(f"a tampered skill name reached a path outside the skills root: rc={named.returncode}\n{named.stdout}")
    else:
        ok("a tampered skill name is discarded instead of used as a path")

    # A Cursor marketplace copy is drift even at the pinned commit: two copies is the problem.
    cache = home / ".cursor" / "plugins" / "cache"
    cache.mkdir(parents=True)
    (cache / ".cloud-plugin-manifest.json").write_text(json.dumps({"plugins": [
        {"name": "pstack", "resolvedCommitSha": "0" * 40}
    ]}))
    plugin = run("--home", str(home), "--repo", str(repo))
    if plugin.returncode != 1 or "Cursor plugin pstack" not in plugin.stdout:
        fail(f"an installed Cursor plugin is not reported: rc={plugin.returncode}\n{plugin.stdout}")
    else:
        ok("--check reports an installed Cursor marketplace copy as drift")


def check_probe(tmp: Path) -> None:
    """The live route probe: only what roles use, and a missing one is drift."""
    home = tmp / "home-probe"
    repo = make_repo(tmp / "repo-probe")
    tree = make_tree(tmp / "tree-probe", "0.15.46", ["arena"])
    run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")

    blind = run("--home", str(home), "--repo", str(repo), probe=False)
    if blind.returncode != 0 or "opencode not on PATH" not in blind.stdout:
        fail(f"with no opencode the probe must note, not drift: rc={blind.returncode}\n{blind.stdout}")
    else:
        ok("with no opencode on PATH the probe reports a note and stays green")

    missing = make_stub(tmp / "stub-missing", [route for route in USED_ROUTES if route != "claude-agent/fable"])
    broken = subprocess.run([sys.executable, str(BIN), "--home", str(home), "--repo", str(repo)],
                            capture_output=True, text=True, env={**os.environ, "PATH": str(missing)})
    if broken.returncode != 1 or "does not list" not in broken.stdout:
        fail(f"a used route the local opencode lacks is not drift: rc={broken.returncode}\n{broken.stdout}")
    else:
        ok("a route a role uses but opencode does not list is drift")

    unused = json.loads((ROOT / "pstack" / "models.json").read_text())["routes"]
    unused = [route for route in unused if route not in USED_ROUTES]
    if unused:
        unused_stub = make_stub(tmp / "stub-unused", USED_ROUTES)
        result = subprocess.run([sys.executable, str(BIN), "--home", str(home), "--repo", str(repo)],
                                capture_output=True, text=True, env={**os.environ, "PATH": str(unused_stub)})
        if result.returncode != 0 or "unused by any role" not in result.stdout:
            fail(f"an unused declared route must be a note, not drift: rc={result.returncode}\n{result.stdout}")
        else:
            ok("a declared route no role uses is a note, not drift")


def check_fetch_guard(tmp: Path) -> None:
    """A wrong archive version must fail loudly instead of installing the wrong bytes."""
    home = tmp / "home-version"
    repo = make_repo(tmp, "0.15.46")
    tree = make_tree(tmp / "tree-v", "0.9.9", ["arena"])
    result = run("--home", str(home), "--repo", str(repo), "--from", str(tree), "--apply")
    if result.returncode == 0 or "0.9.9" not in result.stdout + result.stderr:
        fail(f"a mismatched tree was accepted: rc={result.returncode}\n{result.stdout}{result.stderr}")
    else:
        ok("a tree whose plugin.json disagrees with the pin is refused")


def main() -> int:
    global STUB_DIR, NO_OPENCODE
    with tempfile.TemporaryDirectory() as tmp:
        STUB_DIR = make_stub(Path(tmp) / "stub", USED_ROUTES)
        NO_OPENCODE = Path(tmp) / "empty"
        NO_OPENCODE.mkdir()
        check_vocabulary()
        check_install(Path(tmp))
        check_rules_and_links(Path(tmp))
        check_dangling_and_state(Path(tmp))
        check_probe(Path(tmp))
        check_fetch_guard(Path(tmp))
    if failed:
        print("pstack: FAIL")
        return 1
    print("pstack: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
