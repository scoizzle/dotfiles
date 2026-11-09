#!/usr/bin/env python3
"""Contract for bin/memory-nightly. Run from the repo root: python3 tests/memory_nightly.py"""

from __future__ import annotations

import fcntl
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
        self.oc = self.tmp / "oc"
        self.oc.mkdir()
        self.clone = self.oc / ".memory"
        sh("git", "clone", "--no-checkout", str(self.remote), str(self.clone), env=self.env)
        sh("git", "-C", str(self.clone), "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore", env=self.env)
        sh("git", "-C", str(self.clone), "checkout", "main", env=self.env)
        self.link = self.oc / "memory"
        os.symlink(".memory/memory", self.link)
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

    def pending(self, name, text="- known: x [harness]\n"):
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
        (pend / "2026-11-08.md").unlink()  # promote consumes only the promoted file
        p = fx.run()
        files = tree_files(fx, "memory/dream")
        check("e_promote_simulation",
              p.returncode == 0 and "memory/learnings/2026-11-08.md" in files
              and "memory/learnings/pending/2026-11-08.md" not in files
               and "memory/learnings/pending/2026-11-09.md" in files and len(fx.remote_log()) == 4,
              p.stdout + p.stderr + f" files={files}")

        # (f) --dry-run changes nothing
        fx.pending("2026-11-10.md")
        before = fx.remote_log()
        calls = sum(1 for c in fx.gh_calls() if c.startswith("pr create"))
        p = fx.run("--dry-run")
        check("f_dry_run", p.returncode == 0 and fx.remote_log() == before and "would run" in p.stdout
              , p.stdout + p.stderr)
        check("f_dry_run_no_push", fx.remote_log() == before
              and sum(1 for c in fx.gh_calls() if c.startswith("pr create")) == calls)

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

        # (j) an unpublished untracked dated file must BLOCK the fast-forward
        (fx.seed / "memory" / "core" / "new.md").write_text("new core\n")
        sh("git", "-C", str(fx.seed), "add", "-A", env=fx.env)
        sh("git", "-C", str(fx.seed), "commit", "-m", "upstream: new core", env=fx.env)
        sh("git", "-C", str(fx.seed), "push", "origin", "main", env=fx.env)
        untracked = fx.clone / "memory" / "learnings" / "2099-01-01.md"
        untracked.write_text("- known: untracked dated file [harness]\n")
        p = fx.run("--no-pr")
        merged = fx.clone / "memory" / "core" / "new.md"
        check("j_untracked_blocks_ff",
              p.returncode == 0 and not merged.exists() and untracked.is_file()
              and untracked.read_text() == "- known: untracked dated file [harness]\n",
              p.stdout + p.stderr + f" merged={merged.exists()} untracked={untracked.exists()}")
        untracked.unlink()

        # (stray) strays never enter the published tree
        learn = fx.clone / "memory" / "learnings"
        (learn / "notes.md").write_text("stray\n")
        (learn / ".DS_Store").write_text("x")
        (learn / "x.bak").write_text("x")
        fx.pending("2026-12-01.md")
        p = fx.run("--no-pr")
        files = tree_files(fx, "memory/dream")
        check("stray_excluded",
              p.returncode == 0 and "memory/learnings/pending/2026-12-01.md" in files
              and not any(f.endswith(("notes.md", ".DS_Store", ".bak")) for f in files),
              p.stdout + p.stderr + f" files={files}")
        for n in ("notes.md", ".DS_Store", "x.bak"):
            (learn / n).unlink()

        # (branch main) refuses to target main
        main_before = sh("git", "-C", str(fx.remote), "rev-parse", "main", env=fx.env).stdout
        p = fx.run("--branch", "main")
        p2 = fx.run("--branch", "memory/dream", "--base", "memory/dream")
        check("branch_main_refused",
              p.returncode != 0 and p2.returncode != 0
              and sh("git", "-C", str(fx.remote), "rev-parse", "main", env=fx.env).stdout == main_before,
              p.stdout + p.stderr)

        # (lock) a held lock exits 75 and pushes nothing
        gitdir = sh("git", "-C", str(fx.clone), "rev-parse", "--absolute-git-dir", env=fx.env).stdout.strip()
        fx.pending("2026-12-02.md")
        before = fx.remote_log()
        with open(os.path.join(gitdir, "memory-nightly.lock"), "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                      pass_fds=[lk.fileno()])
            p = fx.run("--no-pr")
            holder.kill()
            holder.wait()
        check("lock_contention_75",
              p.returncode == 75 and "another memory-nightly is running" in (p.stdout + p.stderr)
              and fx.remote_log() == before, p.stdout + p.stderr)

        # (machine path) refused, nothing pushed
        fx.pending("2026-12-03.md", "- known: see /Users/x/y/file for details [harness]\n")
        before = fx.remote_log()
        p = fx.run("--no-pr")
        check("machine_path_refused",
              p.returncode == 1 and "2026-12-03.md" in p.stderr and fx.remote_log() == before,
              p.stdout + p.stderr)
        (learn / "pending" / "2026-12-03.md").unlink()

        # (bad pending) hand-edited line refused
        fx.pending("2026-12-04.md", "garbage line\n")
        before = fx.remote_log()
        p = fx.run("--no-pr")
        check("bad_pending_refused",
              p.returncode == 1 and "2026-12-04.md" in p.stderr and fx.remote_log() == before,
              p.stdout + p.stderr)
        (learn / "pending" / "2026-12-04.md").unlink()

        # (dry-run output) resolved base and paths
        p = fx.run("--dry-run")
        check("dry_run_reports_base", "resolved base:" in p.stdout and "would publish:" in p.stdout,
              p.stdout + p.stderr)

        # (repo_via_symlink) --repo <memory symlink> behaves like the clone root
        fx.pending("2026-12-05.md")
        p = sh(sys.executable, str(SCRIPT), "--repo", str(fx.link), "--skip-dream", "--no-pr",
               env=fx.env, check=False)
        files = tree_files(fx, "memory/dream")
        lock_ok = (fx.clone / ".git" / "memory-nightly.lock").exists()
        stray = [q for q in (fx.link / "memory-nightly.lock", fx.link / ".git", fx.clone / "memory" / "memory")
                 if os.path.lexists(q)]
        check("repo_via_symlink",
              p.returncode == 0 and "memory/learnings/pending/2026-12-05.md" in files
              and lock_ok and not stray and not any(f.startswith("memory/memory") for f in files),
              p.stdout + p.stderr + f" stray={stray}")
        (learn / "pending" / "2026-12-05.md").unlink()
        bad = sh(sys.executable, str(SCRIPT), "--repo", str(fx.tmp / "home"), "--skip-dream", "--no-pr",
                 env=fx.env, check=False)
        check("repo_invalid_one_line", bad.returncode == 1 and bad.stderr.startswith("error:")
              and len(bad.stderr.strip().splitlines()) == 1, bad.stderr)

        # (default_repo_*) no --repo: the default consumer path works before and after install
        def default_repo_case(name, rel, link):
            fxd = Fixture()
            try:
                cfg = Path(fxd.env["HOME"]) / ".config" / "opencode"
                cfg.mkdir(parents=True)
                clone = cfg / rel
                sh("git", "clone", "--no-checkout", str(fxd.remote), str(clone), env=fxd.env)
                sh("git", "-C", str(clone), "sparse-checkout", "set", "--no-cone",
                   "/memory/", "/.gitignore", env=fxd.env)
                sh("git", "-C", str(clone), "checkout", "main", env=fxd.env)
                if link:
                    os.symlink(".memory/memory", cfg / "memory")
                pending = clone / "memory" / "learnings" / "pending"
                pending.mkdir(exist_ok=True)
                (pending / "2026-11-12.md").write_text("- known: x [harness]\n")
                p = sh(sys.executable, str(SCRIPT), "--skip-dream", "--no-pr", env=fxd.env, check=False)
                files = tree_files(fxd, "memory/dream")
                nested = [q for q in (clone / "memory" / "memory",) if os.path.lexists(q)]
                check(name, p.returncode == 0
                      and "memory/learnings/pending/2026-11-12.md" in files and not nested,
                      p.stdout + p.stderr + f" files={files} nested={nested}")
            finally:
                fxd.cleanup()

        default_repo_case("default_repo_old_layout", "memory", False)
        default_repo_case("default_repo_new_layout", ".memory", True)

        # (two clones) a fresh clone lacking A's dated file must not delete it
        fx2 = Fixture()
        try:
            # fresh clone B against the same remote
            clone_b = fx2.tmp / "cloneb"
            sh("git", "clone", "--no-checkout", str(fx2.remote), str(clone_b), env=fx2.env)
            sh("git", "-C", str(clone_b), "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore", env=fx2.env)
            sh("git", "-C", str(clone_b), "checkout", "main", env=fx2.env)
            (fx2.clone / "memory" / "learnings" / "2027-01-01.md").write_text("- known: from A [harness]\n")
            p = fx2.run("--no-pr")
            ok_a = p.returncode == 0
            (clone_b / "memory" / "learnings" / "2027-01-02.md").write_text("- known: from B [harness]\n")
            p = sh(sys.executable, str(SCRIPT), "--repo", str(clone_b), "--skip-dream", "--no-pr",
                   env=fx2.env, check=False)
            files = tree_files(fx2, "memory/dream")
            check("two_clones_both_dated",
                  ok_a and p.returncode == 0 and "memory/learnings/2027-01-01.md" in files
                  and "memory/learnings/2027-01-02.md" in files, p.stdout + p.stderr + f" files={files}")
        finally:
            fx2.cleanup()

        # (promote-publish-merge)
        fx3 = Fixture()
        try:
            fx3.pending("2027-02-01.md")
            p = fx3.run("--no-pr")
            ok1 = p.returncode == 0 and "memory/learnings/pending/2027-02-01.md" in tree_files(fx3, "memory/dream")
            l3 = fx3.clone / "memory" / "learnings"
            (l3 / "2027-02-01.md").write_text((l3 / "pending" / "2027-02-01.md").read_text())
            (l3 / "pending" / "2027-02-01.md").unlink()
            p = fx3.run("--no-pr")
            files = tree_files(fx3, "memory/dream")
            ok2 = (p.returncode == 0 and "memory/learnings/2027-02-01.md" in files
                   and not any("/pending/" in f for f in files))
            sh("git", "-C", str(fx3.seed), "fetch", "origin", env=fx3.env)
            sh("git", "-C", str(fx3.seed), "merge", "--no-edit", "origin/memory/dream", env=fx3.env)
            sh("git", "-C", str(fx3.seed), "push", "origin", "main", env=fx3.env)
            mfiles = tree_files(fx3, "main")
            check("promote_publish_merge",
                  ok1 and ok2 and "memory/learnings/2027-02-01.md" in mfiles
                  and not any("/pending/" in f for f in mfiles), f"{ok1} {ok2} {files} {mfiles}")
        finally:
            fx3.cleanup()
        # (ff_after_merge)
        fx5 = Fixture()
        try:
            fx5.pending("2027-03-01.md")
            fx5.run("--no-pr")
            l5 = fx5.clone / "memory" / "learnings"
            (l5 / "2027-03-01.md").write_text((l5 / "pending" / "2027-03-01.md").read_text())
            (l5 / "pending" / "2027-03-01.md").unlink()
            fx5.run("--no-pr")
            sh("git", "-C", str(fx5.seed), "fetch", "origin", env=fx5.env)
            sh("git", "-C", str(fx5.seed), "merge", "--no-edit", "origin/memory/dream", env=fx5.env)
            sh("git", "-C", str(fx5.seed), "push", "origin", "main", env=fx5.env)
            sh("git", "-C", str(fx5.seed), "push", "origin", "--delete", "memory/dream", env=fx5.env)
            (fx5.seed / "memory" / "core" / "later.md").write_text("later\n")
            sh("git", "-C", str(fx5.seed), "add", "-A", env=fx5.env)
            sh("git", "-C", str(fx5.seed), "commit", "-m", "later", env=fx5.env)
            sh("git", "-C", str(fx5.seed), "push", "origin", "main", env=fx5.env)
            head0 = sh("git", "-C", str(fx5.clone), "rev-parse", "HEAD", env=fx5.env).stdout
            p = fx5.run("--no-pr")
            head1 = sh("git", "-C", str(fx5.clone), "rev-parse", "HEAD", env=fx5.env).stdout
            check("ff_after_merge",
                  p.returncode == 0 and head0 != head1 and (fx5.clone / "memory" / "core" / "later.md").exists()
                  and "skipping fast-forward" not in p.stderr, p.stdout + p.stderr)
        finally:
            fx5.cleanup()

        def push_main(fxx, rel, text):
            f = fxx.seed / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
            sh("git", "-C", str(fxx.seed), "add", "-A", env=fxx.env)
            sh("git", "-C", str(fxx.seed), "commit", "-m", "up", env=fxx.env)
            sh("git", "-C", str(fxx.seed), "push", "origin", "main", env=fxx.env)

        # (stale_readme_not_published)
        fx6 = Fixture()
        try:
            push_main(fx6, "memory/learnings/README.md", "readme v2\n")
            (fx6.clone / "memory" / "core" / "a.md").write_text("dirty\n")  # blocks the fast-forward
            fx6.pending("2027-04-01.md")
            p = fx6.run("--no-pr")
            readme = sh("git", "-C", str(fx6.remote), "show", "memory/dream:memory/learnings/README.md",
                        env=fx6.env, check=False).stdout
            check("stale_readme_not_published", p.returncode == 0 and readme == "readme v2\n",
                  p.stdout + p.stderr + repr(readme))
        finally:
            fx6.cleanup()

        # (stale_dated_not_reverted)
        fx7 = Fixture()
        try:
            push_main(fx7, "memory/learnings/2027-05-10.md", "- known: A [harness]\n- known: B [harness]\n")
            (fx7.clone / "memory" / "learnings" / "2027-05-10.md").write_text("- known: A [harness]\n")
            p = fx7.run("--no-pr")
            check("stale_dated_not_reverted",
                  p.returncode == 0 and "diverged from upstream" in p.stderr and not fx7.remote_log(),
                  p.stdout + p.stderr)
        finally:
            fx7.cleanup()

        # (append_publishes)
        fx8 = Fixture()
        try:
            push_main(fx8, "memory/learnings/2027-05-10.md", "- known: A [harness]\n")
            full = "- known: A [harness]\n- known: B [harness]\n"
            (fx8.clone / "memory" / "learnings" / "2027-05-10.md").write_text(full)
            p = fx8.run("--no-pr")
            got = sh("git", "-C", str(fx8.remote), "show", "memory/dream:memory/learnings/2027-05-10.md",
                     env=fx8.env, check=False).stdout
            check("append_publishes", p.returncode == 0 and got == full, p.stdout + p.stderr + repr(got))
        finally:
            fx8.cleanup()

        # (drop_pending)
        fx9 = Fixture()
        try:
            fx9.pending("2026-11-09.md")
            fx9.run("--no-pr")
            ok1 = "memory/learnings/pending/2026-11-09.md" in tree_files(fx9, "memory/dream")
            p = fx9.run("--no-pr", "--drop-pending", "2026-11-09.md")
            gone = "memory/learnings/pending/2026-11-09.md" not in tree_files(fx9, "memory/dream")
            kept = (fx9.clone / "memory" / "learnings" / "pending" / "2026-11-09.md").exists()
            bad = fx9.run("--no-pr", "--drop-pending", "notes.md")
            check("drop_pending", ok1 and p.returncode == 0 and gone and kept and bad.returncode != 0,
                  p.stdout + p.stderr + bad.stderr)
        finally:
            fx9.cleanup()

        # (missing_dream)
        fx10 = Fixture()
        try:
            fx10.pending("2027-06-01.md")
            p = sh(sys.executable, str(SCRIPT), "--repo", str(fx10.clone), "--skip-dream", "--no-pr",
                   "--dream", "/nonexistent/dream", env=fx10.env, check=False)
            check("missing_dream",
                  p.returncode != 0 and "Traceback" not in p.stderr and p.stderr.startswith("error:")
                  and len(p.stderr.strip().splitlines()) == 1 and not fx10.remote_log(), p.stdout + p.stderr)
        finally:
            fx10.cleanup()
    finally:
        fx.cleanup()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
