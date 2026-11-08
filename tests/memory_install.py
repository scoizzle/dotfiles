#!/usr/bin/env python3
"""Contract for install.cs memory provisioning (sparse git clone, not a link).

Run from the repo root: python3 tests/memory_install.py

Source = a git clone of the checked-out HEAD (commit first). Every case gets its
own temp dirs and runs ./install.cs --home <tmp> with MEMORY_REMOTE=<source>.
Prints "PASS <name>" per case; exit 0 only if all pass.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(tempfile.mkdtemp(prefix="memory-install-"))
DOTNET_HOME = SCRATCH / "dotnet-home"
DOTNET_HOME.mkdir()

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
}


def run(cmd, env=None, cwd=None, check=True):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(cmd, env=e, cwd=cwd, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise AssertionError(f"{cmd} -> {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def git(*args, cwd=None, check=True):
    return run(["git", *args], env=GIT_ENV, cwd=cwd, check=check)


def make_source(name="source") -> Path:
    """A clone of the current checkout, including its committed changes."""
    src = SCRATCH / f"{name}-{time.monotonic_ns()}"
    git("clone", "-q", str(ROOT), str(src))
    return src


def install(home: Path, source: Path, *extra, shell_home: Path | None = None, check=True):
    env = {
        "MEMORY_REMOTE": str(source),
        # dotnet writes caches under HOME; keep them out of the case's homes.
        "HOME": str(shell_home or SCRATCH / "shell-home"),
        "DOTNET_CLI_HOME": str(DOTNET_HOME),
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "NUGET_PACKAGES": str(DOTNET_HOME / "nuget"),
    }
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    return run([str(ROOT / "install.cs"), "--home", str(home), *extra], env=env, cwd=ROOT, check=check)


def fresh(name):
    home = SCRATCH / f"{name}-{time.monotonic_ns()}"
    home.mkdir()
    return home


def memdir(home: Path) -> Path:
    return home / ".config" / "opencode" / "memory"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def case_real_clone():
    source = make_source()
    home = fresh("clone")
    install(home, source)
    m = memdir(home)
    require(m.is_dir() and not m.is_symlink(), "memory must be a real directory")
    require(git("-C", str(m), "rev-parse", "--is-inside-work-tree").stdout.strip() == "true", "not a work tree")
    require(git("-C", str(m), "remote", "get-url", "origin").stdout.strip() == str(source), "origin mismatch")
    for rel in ("INDEX.md", "core/safety.md", "memory/INDEX.md"):
        require((m / rel).is_file(), f"missing {rel}")
    for name in ("INDEX.md", "core", "learnings"):
        require((m / name).is_symlink(), f"{name} must be a link")
    require(not os.path.isabs(os.readlink(m / "core")), "links must be relative")
    require(not (m / "opencode.json").exists(), "sparse checkout leaked opencode.json (no-cone)")
    exclude = (m / ".git" / "info" / "exclude").read_text().split()
    for e in ("/INDEX.md", "/core", "/learnings"):
        require(e in exclude, f"{e} not excluded")
    require(git("-C", str(m), "status", "--porcelain").stdout.strip() == "", "clone dirty after install")
    require((m / ".gitignore").is_file(), "clone did not get the repo's root .gitignore")
    pending = m / "memory" / "learnings" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    probe = pending / "2099-01-01.md"
    probe.write_text("- known: probe\n")
    try:
        status = git("-C", str(m), "status", "--porcelain").stdout.strip()
        require(status == "", f"pending probe shows as untracked: {status}")
    finally:
        probe.unlink()


def case_check():
    source = make_source()
    home = fresh("check")
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1, f"fresh --check should exit 1, got {p.returncode}\n{p.stdout}")
    require("would create memory" in p.stdout, p.stdout)
    require(not memdir(home).exists(), "--check wrote memory")
    install(home, source)
    p = install(home, source, "--check", check=False)
    require(p.returncode == 0, f"--check after install exited {p.returncode}\n{p.stdout}")
    require("ok memory (clone)" in p.stdout, p.stdout)


def case_second_install():
    source = make_source()
    home = fresh("second")
    install(home, source)
    p = install(home, source)
    require("done (0 path(s) changed)" in p.stdout, p.stdout)


def case_missing_links_and_remote_mismatch():
    source = make_source()
    home = fresh("repair")
    install(home, source)
    m = memdir(home)
    (m / "core").unlink()
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1 and "would link memory" in p.stdout, p.stdout)
    p = install(home, source)
    require((m / "core").is_symlink() and "done (1 path(s) changed)" in p.stdout, p.stdout)
    other = make_source("other")
    p = install(home, other, check=False)
    require(p.returncode == 2 and "FAILED  memory" in p.stdout, p.stdout)
    require(str(source) in p.stdout and str(other) in p.stdout, "mismatch must print actual and expected")
    require(git("-C", str(m), "remote", "get-url", "origin").stdout.strip() == str(source), "remote was repointed")


def case_repair_sparse_set():
    source = make_source()
    home = fresh("sparse")
    install(home, source)
    m = memdir(home)
    # simulate a clone provisioned before install.cs asked for /.gitignore
    git("-C", str(m), "sparse-checkout", "set", "--no-cone", "/memory/")
    patterns = git("-C", str(m), "sparse-checkout", "list").stdout.split()
    require("/.gitignore" not in patterns, f"sparse set still has .gitignore: {patterns}")
    require(not (m / ".gitignore").exists(), ".gitignore still checked out")
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1, f"--check exited {p.returncode}\n{p.stdout}")
    require("would repair memory (sparse set)" in p.stdout, p.stdout)
    p = install(home, source)
    require(p.returncode == 0, f"repair exited {p.returncode}\n{p.stdout}")
    require("repair  memory (sparse set)" in p.stdout, p.stdout)
    patterns = git("-C", str(m), "sparse-checkout", "list").stdout.split()
    require("/.gitignore" in patterns, f"sparse set not repaired: {patterns}")
    require((m / ".gitignore").is_file(), ".gitignore not checked out after repair")
    p = install(home, source, "--check", check=False)
    require(p.returncode == 0 and "ok memory (clone)" in p.stdout, p.stdout)


def case_no_remote():
    home = fresh("noremote")
    env = {
        "HOME": str(SCRATCH / "shell-home"), "DOTNET_CLI_HOME": str(DOTNET_HOME),
        "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "NUGET_PACKAGES": str(DOTNET_HOME / "nuget"),
    }
    e = dict(os.environ)
    e.update(env)
    e.pop("MEMORY_REMOTE", None)
    # a copy of the repo without an origin remote
    repo = SCRATCH / f"noorigin-{time.monotonic_ns()}"
    git("clone", "-q", str(ROOT), str(repo))
    git("-C", str(repo), "remote", "remove", "origin")
    p = subprocess.run([str(repo / "install.cs"), "--home", str(home)], env=e, cwd=repo, text=True, capture_output=True)
    require(p.returncode != 0 and "no clone remote" in p.stdout, p.stdout + p.stderr)
    require(not memdir(home).exists(), "memory created without a remote")


def seed_session_db(path: Path):
    db = sqlite3.connect(path)
    db.execute("""create table session_v2 (
      id text, title text, directory text, agent text,
      time_created integer, time_updated integer, idle_outcome text,
      parent_id text, cost real
    )""")
    db.execute("""create table session_message (
      id text, session_id text, type text, seq integer, data text
    )""")
    now = int(time.time() * 1000)
    db.execute("insert into session_v2 values (?,?,?,?,?,?,?,?,?)",
               ("ses_test", "fix path", "/tmp/work", "build", now, now, "failed", None, 0.0))
    for i in (1, 2):
        data = json.dumps({"content": [{"type": "tool", "name": "shell", "state": {
            "status": "error",
            "input": {"command": "cat missing/file.txt"},
            "error": {"message": "No such file or directory: missing/file.txt"},
        }}]})
        db.execute("insert into session_message values (?,?,?,?,?)", (f"msg_{i}", "ses_test", "assistant", i, data))
    db.commit()
    db.close()


def case_dream_writes_in_clone():
    source = make_source()
    home = fresh("dream")
    install(home, source)
    m = memdir(home)
    core_before = sorted(str(p.relative_to(m / "core")) for p in (m / "core").rglob("*") if p.is_file())

    db = SCRATCH / f"dream-{time.monotonic_ns()}.db"
    seed_session_db(db)
    bindir = SCRATCH / f"stub-{time.monotonic_ns()}"
    bindir.mkdir()
    stub = bindir / "opencode"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "text = '- known: missing/file.txt is not in the tree [harness]\\n'\n"
        "sys.stdout.write(json.dumps({'type': 'text', 'part': {'text': text}}) + '\\n')\n"
    )
    stub.chmod(0o755)
    day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    cmd = [str(ROOT / "bin" / "dream"), "--memory", str(m), "--source", "opencode", "--db", str(db)]
    run(cmd, env=env, cwd=ROOT)
    pending = m / "memory" / "learnings" / "pending" / f"{day}.md"
    require(pending.is_file(), f"no pending file at {pending}")
    require(pending.read_text().count("missing/file.txt is not in the tree") == 1, "first run did not append once")
    core_after = sorted(str(p.relative_to(m / "core")) for p in (m / "core").rglob("*") if p.is_file())
    require(core_before == core_after, "dream touched core/")
    run(cmd, env=env, cwd=ROOT)
    require(pending.read_text().count("missing/file.txt is not in the tree") == 1, "second run appended again")
    require(git("-C", str(m), "status", "--porcelain").stdout.strip() == "", "pending must be ignored, not dirty")


def case_worktree_deleted():
    source = make_source("doomed")
    home = fresh("deleted")
    install(home, source)
    shutil.rmtree(source)
    m = memdir(home)
    git("-C", str(m), "fsck", "--no-dangling")
    require(git("-C", str(m), "log", "--oneline", "-1").stdout.strip() != "", "no history")
    require("memory" in (m / "INDEX.md").read_text().lower() or (m / "INDEX.md").stat().st_size > 0, "INDEX unreadable")
    require((m / "core" / "safety.md").read_text() != "", "tracked file unreadable")


def migrate_case(kind: str):
    source = make_source()
    home = fresh(f"migrate-{kind}")
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    if kind == "dir":
        old = cfg / "memory"
    else:
        old = home / "old-memory-target"
    (old / "learnings" / "pending").mkdir(parents=True)
    (old / "learnings" / "2026-01-01.md").write_text("# dated original\n")
    (old / "learnings" / "pending" / "2026-01-02.md").write_text("# pending original\n")
    (old / "learnings" / "working.md").write_text("# working original\n")
    (old / "INDEX.md").write_text("old index\n")
    if kind == "symlink":
        (cfg / "memory").symlink_to(old)

    install(home, source)
    m = memdir(home)
    require(m.is_dir() and not m.is_symlink(), "memory is not a real dir after migration")
    L = m / "memory" / "learnings"
    require((L / "2026-01-01.md").read_text() == "# dated original\n", "dated learning lost")
    require((L / "pending" / "2026-01-02.md").read_text() == "# pending original\n", "pending lost")
    require((L / "working.md").read_text() == "# working original\n", "working.md lost")
    require((L / "README.md").is_file(), "tracked README missing")
    backups = sorted((home / ".config").glob("opencode.bak-*"))
    require(len(backups) == 1, f"expected one backup, got {backups}")
    if kind == "dir":
        b = backups[0] / "memory" / "learnings"
        require((b / "2026-01-01.md").read_text() == "# dated original\n", "backup lost dated")
        require((b / "pending" / "2026-01-02.md").read_text() == "# pending original\n", "backup lost pending")
    else:
        require((backups[0] / "memory.link-target").read_text().strip() == str(old), "link target not recorded")
        require((old / "learnings" / "2026-01-01.md").is_file(), "symlink source was disturbed")
    p = install(home, source)
    require("done (0 path(s) changed)" in p.stdout, "second install after migration not idempotent")


def case_migrate_collision_and_dangling():
    source = make_source()
    # collision: dated file already tracked in the clone's HEAD would keep the clone copy
    home = fresh("collide")
    cfg = home / ".config" / "opencode"
    (cfg / "memory" / "learnings").mkdir(parents=True)
    (cfg / "memory" / "learnings" / "README.md").write_text("different readme\n")
    p = install(home, source)
    require("kept existing learnings/README.md" in p.stdout, p.stdout)
    require((memdir(home) / "memory" / "learnings" / "README.md").read_text() != "different readme\n", "clobbered")
    bak = next((home / ".config").glob("opencode.bak-*")) / "memory" / "learnings" / "README.md"
    require(bak.read_text() == "different readme\n", "backup copy lost")
    # dangling symlink
    home = fresh("dangling")
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "memory").symlink_to(home / "does-not-exist")
    p = install(home, source)
    require("dangling" in p.stdout and memdir(home).is_dir() and not memdir(home).is_symlink(), p.stdout)


def case_home_isolation():
    source = make_source()
    home = fresh("iso")
    other = fresh("other-home")
    install(home, source, shell_home=other)
    require(list(other.iterdir()) == [], f"--home leaked into HOME: {list(other.iterdir())}")
    require(memdir(home).is_dir(), "install did not land under --home")


CASES = [
    case_real_clone,
    case_check,
    case_second_install,
    case_missing_links_and_remote_mismatch,
    case_repair_sparse_set,
    case_no_remote,
    case_dream_writes_in_clone,
    case_worktree_deleted,
    lambda: migrate_case("dir"),
    lambda: migrate_case("symlink"),
    case_migrate_collision_and_dangling,
    case_home_isolation,
]
NAMES = [
    "real clone", "check", "second install", "repair and remote mismatch", "repair sparse set",
    "no remote",
    "dream writes in clone", "worktree deleted", "migrate dir", "migrate symlink",
    "migrate collision and dangling", "home isolation",
]


def main() -> int:
    only = sys.argv[1:]
    failed = 0
    try:
        for name, fn in zip(NAMES, CASES):
            if only and name not in only:
                continue
            try:
                fn()
                print(f"PASS {name}", flush=True)
            except Exception:
                failed += 1
                print(f"FAIL {name}", flush=True)
                traceback.print_exc()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
