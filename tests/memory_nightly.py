#!/usr/bin/env python3
"""Contract for bin/memory-nightly. Run from the repo root: python3 tests/memory_nightly.py"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "memory-nightly"
failures = 0


def sh(*cmd, cwd=None, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd} -> {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


class Fixture:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="memnightly-"))
        self.env = dict(os.environ)
        self.env.update({
            "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "f@x",
            "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "f@x",
            "HOME": str(self.tmp / "home"),
        })
        (self.tmp / "home").mkdir()
        self.remote = self.tmp / "remote.git"
        sh("git", "init", "--bare", "-b", "main", str(self.remote), env=self.env)
        seed = self.tmp / "seed"
        self.seed = seed
        sh("git", "clone", str(self.remote), str(seed), env=self.env, check=False)
        sh("git", "-C", str(seed), "checkout", "-B", "main", env=self.env)
        (seed / ".gitignore").write_text("memory/learnings/pending/\n")
        mem = seed / "memory"
        (mem / "core").mkdir(parents=True)
        (mem / "learnings").mkdir()
        (mem / "INDEX.md").write_text("index\n")
        (mem / "core" / "a.md").write_text("core\n")
        (mem / "learnings" / "README.md").write_text("readme\n")
        sh("git", "-C", str(seed), "add", "-A", env=self.env)
        sh("git", "-C", str(seed), "commit", "-m", "seed", env=self.env)
        sh("git", "-C", str(seed), "push", "origin", "main", env=self.env)
        sh("git", "-C", str(self.remote), "symbolic-ref", "HEAD", "refs/heads/main", env=self.env)
        self.clone = self.tmp / "clone"
        sh("git", "clone", "--no-checkout", str(self.remote), str(self.clone), env=self.env)
        sh("git", "-C", str(self.clone), "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore", env=self.env)
        sh("git", "-C", str(self.clone), "checkout", "main", env=self.env)
        for link, target in (("INDEX.md", "memory/INDEX.md"), ("core", "memory/core"), ("learnings", "memory/learnings")):
            os.symlink(target, self.clone / link)
        with open(self.clone / ".git" / "info" / "exclude", "a") as f:
            f.write("/INDEX.md\n/core\n/learnings\n")
        # stub gh
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.gh_state = self.tmp / "gh_state"
        self.gh_log = self.tmp / "gh_log"
        self.gh_state.write_text("[]")
        gh = self.bin / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{self.gh_log}"\n'
            'if [ "$1 $2" = "pr list" ]; then cat "' + str(self.gh_state) + '"; exit 0; fi\n'
            'if [ "$1 $2" = "pr create" ]; then echo "https://example/pr/1"; '
            f'echo \'[{{"number":1}}]\' > "{self.gh_state}"; exit 0; fi\n'
            "exit 0\n")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env['PATH']}"

    def pending(self, name, text="- known: x\n"):
        d = self.clone / "memory" / "learnings" / "pending"
        d.mkdir(exist_ok=True)
        (d / name).write_text(text)

    def run(self, *extra):
        return sh(sys.executable, str(SCRIPT), "--repo", str(self.clone), "--skip-dream", *extra,
                  env=self.env, check=False)

    def remote_log(self):
        p = sh("git", "-C", str(self.remote), "log", "--format=%H", "memory/dream", env=self.env, check=False)
        return p.stdout.split() if p.returncode == 0 else []

    def gh_calls(self):
        return self.gh_log.read_text().splitlines() if self.gh_log.exists() else []

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def check(name, cond, detail=""):
    global failures
    if cond:
        print(f"PASS {name}")
    else:
        failures += 1
        print(f"FAIL {name} {detail}")


def tree_files(fx, rev):
    return sh("git", "-C", str(fx.remote), "ls-tree", "-r", "--name-only", rev, env=fx.env).stdout.split()


def main():
    fx = Fixture()
    try:
        # (a) nothing pending
        p = fx.run()
        check("a_nothing_pending", p.returncode == 0 and "nothing to commit" in p.stdout and not fx.remote_log(),
              p.stdout + p.stderr)

        # (b) one pending file
        fx.pending("2026-11-08.md")
        p = fx.run()
        log = fx.remote_log()
        files = tree_files(fx, "memory/dream") if log else []
        branch = sh("git", "-C", str(fx.clone), "rev-parse", "--abbrev-ref", "HEAD", env=fx.env).stdout.strip()
        status = sh("git", "-C", str(fx.clone), "status", "--porcelain", env=fx.env).stdout
        check("b_one_pending_one_commit",
              p.returncode == 0 and len(log) == 2 and "memory/learnings/pending/2026-11-08.md" in files
              and branch == "main" and status == "", p.stdout + p.stderr + f" log={log} branch={branch} status={status!r}")

        # (c) rerun (PR is open now via stub state after create)
        p = fx.run()
        check("c_rerun_idempotent", p.returncode == 0 and "nothing to commit" in p.stdout and len(fx.remote_log()) == 2,
              p.stdout + p.stderr)

        # (d) second pending file
        creates_before = sum(1 for c in fx.gh_calls() if c.startswith("pr create"))
        fx.pending("2026-11-09.md")
        p = fx.run()
        creates_after = sum(1 for c in fx.gh_calls() if c.startswith("pr create"))
        check("d_second_pending_two_commits",
              p.returncode == 0 and len(fx.remote_log()) == 3 and creates_before == 1 and creates_after == 1,
              p.stdout + p.stderr + f" log={len(fx.remote_log())} creates={creates_before}/{creates_after}")

        # (e) promote simulation
        pend = fx.clone / "memory" / "learnings" / "pending"
        line = (pend / "2026-11-08.md").read_text()
        (fx.clone / "memory" / "learnings" / "2026-11-08.md").write_text(line)
        for f in pend.glob("*"):
            f.unlink()
        p = fx.run()
        files = tree_files(fx, "memory/dream")
        check("e_promote_simulation",
              p.returncode == 0 and "memory/learnings/2026-11-08.md" in files
              and not any("/pending/" in f for f in files) and len(fx.remote_log()) == 4,
              p.stdout + p.stderr + f" files={files}")

        # (f) --dry-run changes nothing
        fx.pending("2026-11-10.md")
        before = fx.remote_log()
        calls = len(fx.gh_calls())
        p = fx.run("--dry-run")
        check("f_dry_run", p.returncode == 0 and fx.remote_log() == before and "would run" in p.stdout
              , p.stdout + p.stderr)
        check("f_dry_run_no_push", fx.remote_log() == before and len(fx.gh_calls()) == calls)

        # (g) --no-pr makes no gh call
        calls = len(fx.gh_calls())
        p = fx.run("--no-pr")
        check("g_no_pr", p.returncode == 0 and len(fx.gh_calls()) == calls and len(fx.remote_log()) == 5,
              p.stdout + p.stderr)

        # (i) author identity
        author = sh("git", "-C", str(fx.remote), "log", "-1", "--format=%an <%ae>|%cn <%ce>", "memory/dream", env=fx.env).stdout.strip()
        check("i_author", author == "memory-nightly <memory-nightly@localhost>|memory-nightly <memory-nightly@localhost>", author)

        # (h) no open PR but ref exists
        fx.gh_state.write_text("[]")
        fx.pending("2026-11-11.md")
        before = fx.remote_log()
        p = fx.run()
        check("h_closed_pr_refuses",
              p.returncode != 0 and "delete the remote branch" in p.stderr and fx.remote_log() == before,
              p.stdout + p.stderr)

        # (j) an untracked file must not block the fast-forward to a new upstream commit
        (fx.seed / "memory" / "core" / "new.md").write_text("new core\n")
        sh("git", "-C", str(fx.seed), "add", "-A", env=fx.env)
        sh("git", "-C", str(fx.seed), "commit", "-m", "upstream: new core", env=fx.env)
        sh("git", "-C", str(fx.seed), "push", "origin", "main", env=fx.env)
        untracked = fx.clone / "memory" / "learnings" / "2099-01-01.md"
        untracked.write_text("- known: untracked dated file\n")
        p = fx.run("--no-pr")
        merged = fx.clone / "memory" / "core" / "new.md"
        check("j_ff_with_untracked",
              p.returncode == 0 and merged.is_file() and untracked.is_file(),
              p.stdout + p.stderr + f" merged={merged.exists()} untracked={untracked.exists()}")
    finally:
        fx.cleanup()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
