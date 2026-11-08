#!/usr/bin/env python3
"""Contract for install.cs memory provisioning: ~/.config/opencode/.memory is a
sparse git clone and ~/.config/opencode/memory is a symlink to .memory/memory.

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


def child_env(source: Path | None, shell_home: Path | None = None) -> dict:
    """Env for an install.cs child. HOME is inherited unless shell_home is given.

    The dotnet host on Linux needs a real HOME (LocalApplicationData); --home
    already isolates install.cs's writes, so only temp/cache dirs move to SCRATCH.
    """
    tmp = SCRATCH / "tmp"
    dirs = {
        "TMPDIR": tmp, "TMP": tmp, "TEMP": tmp,
        "XDG_DATA_HOME": SCRATCH / "xdg-data",
        "XDG_CACHE_HOME": SCRATCH / "xdg-cache",
        "XDG_CONFIG_HOME": SCRATCH / "xdg-config",
        "DOTNET_CLI_HOME": DOTNET_HOME,
        "NUGET_PACKAGES": DOTNET_HOME / "nuget",
    }
    env = {k: str(v) for k, v in dirs.items()}
    for v in dirs.values():
        v.mkdir(parents=True, exist_ok=True)
    env.update({
        "DOTNET_NOLOGO": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    })
    if source is not None:
        env["MEMORY_REMOTE"] = str(source)
    if shell_home is not None:
        (shell_home / ".local" / "share").mkdir(parents=True, exist_ok=True)
        (shell_home / ".dotnet").mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(shell_home)
    return env


def run_child(cmd, env, cwd, check=True):
    e = dict(os.environ)
    e.update(env)
    if "MEMORY_REMOTE" not in env:
        e.pop("MEMORY_REMOTE", None)
    p = subprocess.run(cmd, env=e, cwd=cwd, text=True, capture_output=True)
    if check and p.returncode != 0:
        dump = "\n".join(f"{k}={v}" for k, v in sorted(e.items()))
        raise AssertionError(
            f"command: {cmd}\nreturncode: {p.returncode}\n--- stdout ---\n{p.stdout}\n"
            f"--- stderr ---\n{p.stderr}\n--- child env ---\n{dump}"
        )
    return p


def install(home: Path, source: Path, *extra, shell_home: Path | None = None, check=True):
    return run_child([str(ROOT / "install.cs"), "--home", str(home), *extra],
                     child_env(source, shell_home), ROOT, check)


def fresh(name):
    home = SCRATCH / f"{name}-{time.monotonic_ns()}"
    home.mkdir()
    return home


def memdir(home: Path) -> Path:
    """The managed path: a symlink to .memory/memory."""
    return home / ".config" / "opencode" / "memory"


def clonedir(home: Path) -> Path:
    """The sparse clone itself."""
    return home / ".config" / "opencode" / ".memory"


def learnings(home: Path) -> Path:
    return clonedir(home) / "memory" / "learnings"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def case_real_clone():
    source = make_source()
    home = fresh("clone")
    install(home, source)
    link, c = memdir(home), clonedir(home)
    require(link.is_symlink(), "memory must be a symlink")
    require(os.readlink(link) == ".memory/memory", f"link target must be relative .memory/memory, got {os.readlink(link)}")
    require(c.is_dir() and not c.is_symlink() and (c / ".git").exists(), ".memory must be a real clone")
    require(git("-C", str(c), "rev-parse", "--is-inside-work-tree").stdout.strip() == "true", "not a work tree")
    require(git("-C", str(c), "remote", "get-url", "origin").stdout.strip() == str(source), "origin mismatch")
    patterns = git("-C", str(c), "sparse-checkout", "list").stdout.split()
    require("/memory/" in patterns and "/.gitignore" in patterns, f"sparse set wrong: {patterns}")
    for rel in ("INDEX.md", "core/safety.md", "learnings/README.md"):
        require((link / rel).is_file(), f"memory/{rel} does not resolve through the link")
    require((c / "memory" / "core" / "safety.md").is_file(), "missing .memory/memory/core/safety.md")
    require(not (c / "opencode.json").exists(), "sparse checkout leaked opencode.json (no-cone)")
    require(sorted(x.name for x in c.iterdir()) == [".git", ".gitignore", "memory"],
            f"clone root has extras: {sorted(x.name for x in c.iterdir())}")
    exclude = c / ".git" / "info" / "exclude"
    require(not exclude.exists() or "/core" not in exclude.read_text().split(), "unexpected exclude entries")
    require(git("-C", str(c), "status", "--porcelain").stdout.strip() == "", "clone dirty after install")
    pending = learnings(home) / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    probe = pending / "2099-01-01.md"
    probe.write_text("- known: probe\n")
    try:
        status = git("-C", str(c), "status", "--porcelain").stdout.strip()
        require(status == "", f"pending probe shows as untracked: {status}")
    finally:
        probe.unlink()


def case_check():
    source = make_source()
    home = fresh("check")
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1, f"fresh --check should exit 1, got {p.returncode}\n{p.stdout}")
    require("would create memory (clone" in p.stdout, p.stdout)
    require("would link memory" in p.stdout, p.stdout)
    require(not clonedir(home).exists() and not memdir(home).is_symlink(), "--check wrote memory")
    install(home, source)
    p = install(home, source, "--check", check=False)
    require(p.returncode == 0, f"--check after install exited {p.returncode}\n{p.stdout}")
    require("ok memory (clone)" in p.stdout and "ok memory (link)" in p.stdout, p.stdout)


def case_second_install():
    source = make_source()
    home = fresh("second")
    install(home, source)
    p = install(home, source)
    require("done (0 path(s) changed)" in p.stdout, p.stdout)


def case_missing_link_and_wrong_link():
    source = make_source()
    home = fresh("repair")
    install(home, source)
    m = memdir(home)
    m.unlink()
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1 and "would link memory" in p.stdout, p.stdout)
    require(not m.exists() and not m.is_symlink(), "--check recreated the link")
    p = install(home, source)
    require(m.is_symlink() and os.readlink(m) == ".memory/memory" and "done (1 path(s) changed)" in p.stdout, p.stdout)
    # a symlink pointing elsewhere is replaced, its target left alone
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "marker.txt").write_text("x\n")
    m.unlink()
    m.symlink_to(elsewhere)
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1 and "would link memory" in p.stdout, p.stdout)
    p = install(home, source)
    require(os.readlink(m) == ".memory/memory" and (m / "INDEX.md").is_file(), p.stdout)
    require((elsewhere / "marker.txt").is_file(), "wrong link's target was disturbed")
    p = install(home, source)
    require("done (0 path(s) changed)" in p.stdout, p.stdout)


def case_remote_mismatch():
    source = make_source()
    home = fresh("mismatch")
    install(home, source)
    c = clonedir(home)
    other = make_source("other")
    p = install(home, other, check=False)
    require(p.returncode == 2 and "FAILED  memory" in p.stdout, p.stdout)
    require(str(source) in p.stdout and str(other) in p.stdout, "mismatch must print actual and expected")
    require(git("-C", str(c), "remote", "get-url", "origin").stdout.strip() == str(source), "remote was repointed")


def case_repair_sparse_set():
    source = make_source()
    home = fresh("sparse")
    install(home, source)
    m = clonedir(home)
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
    # a copy of the repo without an origin remote
    repo = SCRATCH / f"noorigin-{time.monotonic_ns()}"
    git("clone", "-q", str(ROOT), str(repo))
    git("-C", str(repo), "remote", "remove", "origin")
    p = run_child([str(repo / "install.cs"), "--home", str(home)], child_env(None), repo, check=False)
    require(p.returncode != 0 and "no clone remote" in p.stdout, p.stdout + p.stderr)
    require(not clonedir(home).exists() and not memdir(home).exists(), "memory created without a remote")


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
    pending = clonedir(home) / "memory" / "learnings" / "pending" / f"{day}.md"
    require(pending.is_file(), f"no pending file at {pending}")
    require((m / "learnings" / "pending" / f"{day}.md").is_file(), "pending not visible through the memory link")
    require(pending.read_text().count("missing/file.txt is not in the tree") == 1, "first run did not append once")
    core_after = sorted(str(p.relative_to(m / "core")) for p in (m / "core").rglob("*") if p.is_file())
    require(core_before == core_after, "dream touched core/")
    run(cmd, env=env, cwd=ROOT)
    require(pending.read_text().count("missing/file.txt is not in the tree") == 1, "second run appended again")
    require(git("-C", str(clonedir(home)), "status", "--porcelain").stdout.strip() == "", "pending must be ignored, not dirty")


def case_worktree_deleted():
    source = make_source("doomed")
    home = fresh("deleted")
    install(home, source)
    shutil.rmtree(source)
    m, c = memdir(home), clonedir(home)
    git("-C", str(c), "fsck", "--no-dangling")
    require(git("-C", str(c), "log", "--oneline", "-1").stdout.strip() != "", "no history")
    require((m / "INDEX.md").stat().st_size > 0, "INDEX unreadable")
    require((m / "core" / "safety.md").read_text() != "", "tracked file unreadable")


def migrate_case(kind: str):
    source = make_source()
    home = fresh(f"migrate-{kind}")
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    if kind == "dir":
        old = cfg / "memory"
        lear = old / "learnings"
    elif kind == "symlink":
        old = home / "old-memory-target"
        lear = old / "learnings"
    else:  # "clone": the previous layout, a nested sparse clone at memory/
        old = cfg / "memory"
        git("clone", "-q", str(source), str(old))
        git("-C", str(old), "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore")
        for n, t in (("INDEX.md", "memory/INDEX.md"), ("core", "memory/core"), ("learnings", "memory/learnings")):
            (old / n).symlink_to(t)
        lear = old / "memory" / "learnings"
    (lear / "pending").mkdir(parents=True, exist_ok=True)
    (lear / "2026-01-01.md").write_text("# dated original\n")
    (lear / "pending" / "2026-01-02.md").write_text("# pending original\n")
    (lear / "working.md").write_text("# working original\n")
    if kind != "clone":
        (old / "INDEX.md").write_text("old index\n")
    if kind == "symlink":
        (cfg / "memory").symlink_to(old)

    install(home, source)
    m = memdir(home)
    require(m.is_symlink() and os.readlink(m) == ".memory/memory", "memory is not the link after migration")
    require((clonedir(home) / ".git").exists() and not (clonedir(home) / ".git" / "info" / "exclude").read_text().count("/core"),
            ".memory is not a fresh clone")
    L = learnings(home)
    require((L / "2026-01-01.md").read_text() == "# dated original\n", "dated learning lost")
    require((L / "pending" / "2026-01-02.md").read_text() == "# pending original\n", "pending lost")
    require((L / "working.md").read_text() == "# working original\n", "working.md lost")
    require((L / "README.md").is_file(), "tracked README missing")
    require((m / "learnings" / "2026-01-01.md").is_file(), "migrated learning not visible through the link")
    backups = sorted((home / ".config").glob("opencode.bak-*"))
    require(len(backups) == 1, f"expected one backup, got {backups}")
    if kind == "dir":
        b = backups[0] / "memory" / "learnings"
        require((b / "2026-01-01.md").read_text() == "# dated original\n", "backup lost dated")
        require((b / "pending" / "2026-01-02.md").read_text() == "# pending original\n", "backup lost pending")
    elif kind == "clone":
        b = backups[0] / "memory"
        require((b / ".git").exists(), "old clone's .git not preserved in the backup")
        require((b / "memory" / "learnings" / "2026-01-01.md").is_file(), "backup lost dated")
        require(not (b / ".migrating").exists(), "marker left behind")
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
    require((learnings(home) / "README.md").read_text() != "different readme\n", "clobbered")
    bak = next((home / ".config").glob("opencode.bak-*")) / "memory" / "learnings" / "README.md"
    require(bak.read_text() == "different readme\n", "backup copy lost")
    # dangling symlink
    home = fresh("dangling")
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "memory").symlink_to(home / "does-not-exist")
    p = install(home, source)
    require("dangling" in p.stdout and memdir(home).is_symlink() and (memdir(home) / "INDEX.md").is_file(), p.stdout)


def case_home_isolation():
    source = make_source()
    home = fresh("iso")
    other = fresh("other-home")
    install(home, source, shell_home=other)
    leaked = [x for x in (other / ".config" / "opencode", other / ".config" / "opencode" / ".memory") if x.exists()]
    require(not leaked, f"--home leaked into HOME: {leaked}")
    require(memdir(home).is_symlink() and clonedir(home).is_dir(), "install did not land under --home")


def install_raw(args, source: Path, shell_home: Path):
    return run_child([str(ROOT / "install.cs"), *args], child_env(source, shell_home), ROOT, check=False)


def case_home_flag_validation():
    source = make_source()
    for args in (["--home"], ["--home", "--check"]):
        real = fresh("realhome")
        p = install_raw(args, source, real)
        require(p.returncode != 0, f"{args} exited 0\n{p.stdout}")
        require("FAILED" in p.stdout, p.stdout)
        touched = [x.name for x in real.iterdir() if x.name in (".config", ".claude", ".grok")]
        require(touched == [], f"{args} touched the real home: {touched}")


def case_memory_remote_flag_validation():
    source = make_source()
    for args in (["--memory-remote"], ["--memory-remote", "--check"]):
        real = fresh("realhome")
        p = install_raw(["--home", str(real), *args], source, real)
        require(p.returncode != 0, f"{args} exited 0\n{p.stdout}")
        require("FAILED" in p.stdout, p.stdout)
        require("--memory-remote" in p.stdout, p.stdout)
        touched = [x.name for x in real.iterdir() if x.name in (".config", ".claude", ".grok")]
        require(touched == [], f"{args} touched the real home: {touched}")


def case_interrupted_migration():
    source = make_source()
    home = fresh("interrupted")
    install(home, source)
    bak = home / ".config" / "opencode.bak-20260101-000000" / "memory"
    (bak / "learnings" / "pending").mkdir(parents=True)
    (bak / "learnings" / "2026-02-02.md").write_text("# interrupted dated\n")
    (bak / "learnings" / "pending" / "2026-02-03.md").write_text("# interrupted pending\n")
    (bak / ".migrating").write_text("")
    p = install(home, source)
    L = learnings(home)
    require((L / "2026-02-02.md").read_text() == "# interrupted dated\n", p.stdout)
    require((L / "pending" / "2026-02-03.md").read_text() == "# interrupted pending\n", p.stdout)
    require(not (bak / ".migrating").exists(), "marker not removed")
    require((bak / "learnings" / "2026-02-02.md").is_file(), "backup source disturbed")
    p = install(home, source)
    require("done (0 path(s) changed)" in p.stdout, "not idempotent after resume\n" + p.stdout)


def case_migration_conflict():
    source = make_source()
    home = fresh("conflict")
    install(home, source)
    L = learnings(home)
    (L / "2026-01-01.md").write_text("# clone version\n")
    bak = home / ".config" / "opencode.bak-20260101-000000" / "memory"
    (bak / "learnings").mkdir(parents=True)
    (bak / "learnings" / "2026-01-01.md").write_text("# local version\n")
    (bak / "learnings" / "2026-01-04.md").write_text("# same\n")
    (L / "2026-01-04.md").write_text("# same\n")
    (bak / ".migrating").write_text("")
    p = install(home, source)
    require((L / ".conflict" / "2026-01-01.md").read_text() == "# local version\n", p.stdout)
    require((L / "2026-01-01.md").read_text() == "# clone version\n", "clone file was clobbered")
    require(str(L / ".conflict" / "2026-01-01.md") in p.stdout, "warning must name the conflict path\n" + p.stdout)
    require(not (L / ".conflict" / "2026-01-04.md").exists(), "identical file was copied to .conflict")


def case_unreadable_git():
    source = make_source()
    home = fresh("brokengit")
    c = clonedir(home)
    c.mkdir(parents=True)
    (c / ".git").write_text("gitdir: /nonexistent/nowhere\n")
    (c / "keep.txt").write_text("keep\n")
    p = install(home, source, check=False)
    require(p.returncode != 0 and "FAILED" in p.stdout and "cannot read" in p.stdout, p.stdout)
    require((c / ".git").is_file() and (c / "keep.txt").read_text() == "keep\n", "broken clone was replaced")
    require(not list((home / ".config").glob("opencode.bak-*")), "a backup was made")
    require(not memdir(home).exists() and not memdir(home).is_symlink(), "link created next to a broken clone")


def case_non_clone_memory_dir():
    source = make_source()
    home = fresh("plainclone")
    c = clonedir(home)
    c.mkdir(parents=True)
    (c / "stray.txt").write_text("stray\n")
    install(home, source)
    require((c / ".git").exists() and (c / "memory" / "INDEX.md").is_file(), ".memory not re-provisioned")
    bak = next((home / ".config").glob("opencode.bak-*")) / "memory-src"
    require((bak / "stray.txt").read_text() == "stray\n", "old .memory not preserved in backup")


def case_symlink_memory_src():
    source = make_source()
    home = fresh("symsrc")
    target = home / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("keep\n")
    c = clonedir(home)
    c.parent.mkdir(parents=True)
    c.symlink_to(target)
    p = install(home, source, check=False)
    require(p.returncode != 0 and "FAILED" in p.stdout and "is a symlink" in p.stdout, p.stdout)
    require(c.is_symlink() and os.readlink(c) == str(target), ".memory symlink was touched")
    require((target / "keep.txt").read_text() == "keep\n" and sorted(x.name for x in target.iterdir()) == ["keep.txt"],
            "symlink target was disturbed or cloned into")
    require(not list((home / ".config").glob("opencode.bak-*")), "a backup was made")
    require(not memdir(home).exists() and not memdir(home).is_symlink(), "memory link created")


def case_non_clone_with_learnings():
    source = make_source()
    home = fresh("plainlearn")
    c = clonedir(home)
    (c / "memory" / "learnings").mkdir(parents=True)
    (c / "memory" / "learnings" / "2026-03-03.md").write_text("# old dated\n")
    install(home, source)
    require((learnings(home) / "2026-03-03.md").read_text() == "# old dated\n", "learnings not migrated")
    bak = next((home / ".config").glob("opencode.bak-*")) / "memory-src"
    require((bak / "memory" / "learnings" / "2026-03-03.md").is_file(), "old .memory not in backup")


def case_replaced_clone_link_ok():
    source = make_source()
    home = fresh("replaced")
    install(home, source)
    c = clonedir(home)
    shutil.rmtree(c)
    (c / "memory" / "learnings").mkdir(parents=True)
    (c / "memory" / "learnings" / "2026-04-04.md").write_text("# kept\n")
    require(os.readlink(memdir(home)) == ".memory/memory", "precondition: link intact")
    install(home, source)
    require((c / ".git").exists() and (learnings(home) / "2026-04-04.md").read_text() == "# kept\n",
            "migration skipped when the link was already ok")


def case_absolute_link():
    source = make_source()
    home = fresh("abslink")
    install(home, source)
    m = memdir(home)
    abs_target = clonedir(home) / "memory"
    m.unlink()
    m.symlink_to(abs_target)
    p = install(home, source, "--check", check=False)
    require(p.returncode == 1 and "would link memory" in p.stdout, p.stdout)
    p = install(home, source)
    require(os.readlink(m) == ".memory/memory", f"link not relative: {os.readlink(m)}\n{p.stdout}")
    rec = next((home / ".config").glob("opencode.bak-*")) / "memory.link-target"
    require(rec.read_text().strip() == str(abs_target), f"target not recorded: {rec.read_text()!r}")
    require((abs_target / "INDEX.md").is_file(), "link target disturbed")


def case_temp_env_override():
    source = make_source()
    home = fresh("tmpenv")
    bogus = SCRATCH / "bogus-tmp-must-not-exist"
    saved = {k: os.environ.get(k) for k in ("TMPDIR", "TMP", "TEMP")}
    try:
        for k in saved:
            os.environ[k] = str(bogus)
        env = child_env(source)
        for k in saved:
            require(env[k] == str(SCRATCH / "tmp"), f"child {k} not scratch: {env[k]}")
        install(home, source)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    require(memdir(home).is_symlink() and (clonedir(home) / ".git").exists(), "no clone provisioned")
    require(not bogus.exists(), "bogus temp path was created")


CASES = [
    case_home_flag_validation,
    case_memory_remote_flag_validation,
    case_interrupted_migration,
    case_migration_conflict,
    case_unreadable_git,
    case_non_clone_memory_dir,
    case_symlink_memory_src,
    case_non_clone_with_learnings,
    case_replaced_clone_link_ok,
    case_absolute_link,
    case_real_clone,
    case_check,
    case_second_install,
    case_missing_link_and_wrong_link,
    case_remote_mismatch,
    case_repair_sparse_set,
    case_no_remote,
    case_dream_writes_in_clone,
    case_worktree_deleted,
    lambda: migrate_case("dir"),
    lambda: migrate_case("symlink"),
    lambda: migrate_case("clone"),
    case_migrate_collision_and_dangling,
    case_home_isolation,
    case_temp_env_override,
]
NAMES = [
    "home flag validation", "memory-remote flag validation", "interrupted migration", "migration conflict",
    "unreadable git", "non-clone .memory",
    "symlink .memory", "non-clone with learnings", "replaced clone link ok", "absolute link", "real clone", "check", "second install", "missing and wrong link",
    "remote mismatch", "repair sparse set", "no remote",
    "dream writes in clone", "worktree deleted", "migrate dir", "migrate symlink", "migrate old clone",
    "migrate collision and dangling", "home isolation", "temp env override",
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
