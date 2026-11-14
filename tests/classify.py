#!/usr/bin/env python3
"""Regression tests for review-bundle's classifier: is_sensitive, critical_token,
and the --classify output lines (lines:, critical:, prose-lane:)."""

import atexit
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "bin", "review-bundle")

_loader = importlib.machinery.SourceFileLoader("review_bundle", PATH)
_spec = importlib.util.spec_from_loader("review_bundle", _loader)
review_bundle = importlib.util.module_from_spec(_spec)
_loader.exec_module(review_bundle)

CASES = [
    ("docs/author-notes.md", False),
    ("src/author.cs", False),
    ("src/Authoring.cs", False),
    ("Poly/DomainModeling/Analysis/AuthoringSuggestionAnalyzer.cs", False),
    ("Poly.Tests/DomainModeling/DomainAuthoringHappyPathTests.cs", False),
    ("Poly/DomainModeling/Queries/JsonSchemaExporter.cs", False),
    ("Poly.Mcp/Surface/PolyOutputSchema.cs", False),
    ("docs/json-schema.md", False),
    ("src/Auth.cs", True),
    ("src/auth", True),
    ("svc/auth/handler.cs", True),
    ("src/Authz.cs", True),
    ("src/Unauthorized.cs", True),
    ("src/Authorise.cs", True),
    ("db/schema.rb", True),
    ("prisma/schema.prisma", True),
    ("src/DbSchema.cs", True),
    ("src/Schemas/orders.json", True),
    ("src/AuthService.cs", True),
    ("src/Authentication.cs", True),
    ("src/authorization.py", True),
    ("src/OAuthClient.cs", True),
    ("lib/SecretStore.cs", True),
    ("src/secretmanager.go", True),
    ("docs/authentication-design.md", True),
    ("docs/plan-csharp-native-migration.md", True),
    ("docs/auth-redesign.md", True),
    ("docs/schema-change.md", True),
    ("notes/auth-secrets.txt", True),
    ("README.md", False),
    ("AGENTS.md", True),
    ("agents/build.md", True),
    ("policy/permissions.json", True),
    ("src/PermissionService.cs", True),
    ("db/migrations/001_init.sql", True),
    ("app.slnx", True),
]

# (path, expected token). "not auth" rows use a predicate.
TOKEN_CASES = [
    ("src/AuthService.cs", "auth"),
    ("policy/permissions.json", "security"),
    ("db/x.sql", "migration"),
    ("agents/build.md", "public-contract"),
    (".github/workflows/secret-scan.yml", None),
    ("docs/author-notes.md", lambda t: t != "auth"),
    ("opencode.json", "public-contract"),
    ("docs/auth-redesign.md", "auth"),
    ("lib/SecretStore.cs", "security"),
    ("db/migrations/001_init.sql", "migration"),
    ("prisma/schema.prisma", "migration"),
    ("app.slnx", "public-contract"),
    ("README.md", None),
    ("AGENTS.md", "public-contract"),
]

AGENTS_MD = """# Global instructions

## Default workflow

### Classify

Classify confirms.

### Safety

Reviewers are read-only.

### Ledger

Run review-log after the user answers.

## Memory

Durable memory lives here.
"""

AGENT_X = """---
description: x agent
mode: subagent
---

# X

Body line one.
Body line two.
"""


def run(args, cwd):
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{args} rc={res.returncode}: {res.stderr}")
    return res.stdout


def classify_out(repo, *extra):
    return run([sys.executable, PATH, repo, "--classify", *extra], repo)


def prose_lane(out):
    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("prose-lane:")]
    return lines


def make_repo():
    repo = tempfile.mkdtemp(prefix="classify-test-")
    atexit.register(shutil.rmtree, repo, True)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "t@example.invalid"], repo)
    run(["git", "config", "user.name", "t"], repo)
    os.makedirs(os.path.join(repo, "agents"))
    with open(os.path.join(repo, "agents", "x.md"), "w") as fh:
        fh.write(AGENT_X)
    with open(os.path.join(repo, "AGENTS.md"), "w") as fh:
        fh.write(AGENTS_MD)
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", "init"], repo)
    return repo


def edit(repo, rel, old, new):
    path = os.path.join(repo, rel)
    with open(path) as fh:
        text = fh.read()
    assert old in text, (rel, old)
    with open(path, "w") as fh:
        fh.write(text.replace(old, new, 1))


def body_edit(repo):
    edit(repo, "agents/x.md", "Body line two.", "Body line two, edited.")


def lane_cases():
    """(name, setup(repo) -> extra args, expected state, expected floor)."""

    def paths_only(repo):
        return ["--paths", "agents/x.md"]

    def body(repo):
        body_edit(repo)
        return []

    def frontmatter(repo):
        edit(repo, "agents/x.md", "mode: subagent", "mode: primary")
        return []

    def pin(repo):
        edit(repo, "agents/x.md", "Body line two.", "Body line two on claude-agent/opus.")
        return []

    def anchored(repo):
        edit(repo, "agents/x.md", "Body line two.", "See agents/build.md and/or read/grep.")
        return []

    def new_file(repo):
        with open(os.path.join(repo, "agents", "y.md"), "w") as fh:
            fh.write("# Y\n\nbody\n")
        return []

    def new_file_staged(repo):
        new_file(repo)
        run(["git", "add", "agents/y.md"], repo)
        return []

    def safety(repo):
        body_edit(repo)
        edit(repo, "AGENTS.md", "Reviewers are read-only.", "Reviewers stay read-only.")
        return []

    def classify_section(repo):
        body_edit(repo)
        edit(repo, "AGENTS.md", "Classify confirms.", "Classify only confirms.")
        return []

    def ledger(repo):
        body_edit(repo)
        edit(repo, "AGENTS.md", "Run review-log after", "Run review-log once after")
        return []

    def memory(repo):
        body_edit(repo)
        edit(repo, "AGENTS.md", "Durable memory lives here.", "Durable memory lives here, too.")
        return []

    def base_commit(repo):
        body_edit(repo)
        base = run(["git", "rev-parse", "HEAD"], repo).strip()
        run(["git", "commit", "-qam", "edit"], repo)
        return ["--base", base]

    def non_prose(repo):
        return ["--paths", "agents/x.md", "opencode.json"]

    return [
        ("--paths agents/x.md", paths_only, "candidate"),
        ("body-only edit", body, "eligible"),
        ("frontmatter edit", frontmatter, "ineligible"),
        ("added claude-agent/opus", pin, "ineligible"),
        ("anchored regex body line", anchored, "eligible"),
        ("new agents/y.md (untracked)", new_file, "ineligible"),
        ("new agents/y.md (staged)", new_file_staged, "ineligible"),
        ("AGENTS.md hunk under ### Safety", safety, "ineligible"),
        ("AGENTS.md hunk under ### Classify", classify_section, "ineligible"),
        ("AGENTS.md hunk under ### Ledger", ledger, "eligible"),
        ("AGENTS.md hunk under ## Memory", memory, "eligible"),
        ("--base body-only edit", base_commit, "eligible"),
        ("--paths with a non-prose sensitive path", non_prose, "ineligible"),
    ]


def main():
    failures = 0

    def report(ok, msg):
        nonlocal failures
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        if not ok:
            failures += 1

    for rel, expected in CASES:
        actual = review_bundle.is_sensitive(rel)
        report(actual == expected, f"is_sensitive {rel}: expected {expected}, got {actual}")

    for rel, expected in TOKEN_CASES:
        try:
            actual = review_bundle.critical_token(rel)
        except AttributeError as exc:
            report(False, f"critical_token {rel}: {exc}")
            continue
        ok = expected(actual) if callable(expected) else actual == expected
        report(ok, f"critical_token {rel}: expected {expected}, got {actual}")

    for name, setup, state in lane_cases():
        repo = make_repo()
        try:
            extra = setup(repo)
            out = classify_out(repo, *extra)
        except Exception as exc:  # noqa: BLE001 - a test harness reports, not raises
            report(False, f"prose-lane {name}: {exc}")
            continue
        first = out.splitlines()[0] if out else ""
        lanes = prose_lane(out)
        ok = first == "T2" and len(lanes) == 1 and lanes[0].startswith(f"prose-lane: {state} — ")
        report(ok, f"prose-lane {name}: expected {state}, got line1={first!r} {lanes}")

    # T1 floor prints no prose-lane line; --paths prints the lines note; diff mode does not.
    repo = make_repo()
    out = classify_out(repo, "--paths", "README.md")
    report(
        out.splitlines()[0] == "T1" and not prose_lane(out)
        and "  lines: not measured (planned paths); integrate --base applies the 400-line limit" in out.splitlines(),
        f"--paths README.md: T1, lines note, no prose-lane: {out!r}",
    )
    edit(repo, "AGENTS.md", "Classify confirms.", "Classify only confirms.")
    out = classify_out(repo)
    lanes = prose_lane(out)
    report(
        out.splitlines()[:1] == ["T2"]
        and len(lanes) == 1
        and lanes[0].startswith("prose-lane: ineligible — ")
        and "### Classify" in lanes[0]
        and "  critical: AGENTS.md — public-contract" in out.splitlines()
        and "lines: not measured" not in out,
        f"AGENTS.md-only diff under ### Classify: T2, ineligible, public-contract: {out!r}",
    )

    def agents_only(old, new, state, label):
        tree = make_repo()
        edit(tree, "AGENTS.md", old, new)
        got = classify_out(tree)
        lanes = prose_lane(got)
        ok = (
            got.splitlines()[:1] == ["T2"]
            and len(lanes) == 1
            and lanes[0].startswith(f"prose-lane: {state} — ")
            and "  critical: AGENTS.md — public-contract" in got.splitlines()
        )
        report(ok, f"AGENTS.md-only diff under {label}: T2, {state}, public-contract: {got!r}")

    agents_only("Reviewers are read-only.", "Reviewers stay read-only.", "ineligible", "### Safety")
    agents_only("Run review-log after", "Run review-log once after", "eligible", "### Ledger")

    repo = make_repo()
    out = classify_out(repo, "--paths", "opencode.json", ".github/workflows/secret-scan.yml")
    report(
        "  critical: opencode.json — public-contract" in out.splitlines()
        and "critical: .github" not in out,
        f"--paths opencode.json + CI: critical token lines: {out!r}",
    )
    out = classify_out(repo, "--paths", "agents/x.md")
    report(
        "  critical: agents/x.md — public-contract" in out.splitlines()
        and "informational on a T1 lane" in out,
        f"--paths agents/x.md: informational note: {out!r}",
    )

    # Diff modes (--base and the working tree) print the same critical: and
    # prose-lane: lines as --paths, so the integrate reclassify carries them.
    def diff_mode_change(repo):
        with open(os.path.join(repo, "opencode.json"), "w") as fh:
            fh.write('{"x": 1}\n')
        run(["git", "add", "opencode.json"], repo)
        body_edit(repo)

    def diff_mode_ok(out):
        lines = out.splitlines()
        return (
            lines[:1] == ["T2"]
            and "  critical: opencode.json — public-contract" in lines
            and "  critical: agents/x.md — public-contract" in lines
            and len(prose_lane(out)) == 1
        )

    repo = make_repo()
    base = run(["git", "rev-parse", "HEAD"], repo).strip()
    diff_mode_change(repo)
    run(["git", "commit", "-qam", "change"], repo)
    out = classify_out(repo, "--base", base)
    report(diff_mode_ok(out), f"--base opencode.json + agents/x.md: critical and prose-lane lines: {out!r}")

    repo = make_repo()
    diff_mode_change(repo)
    out = classify_out(repo)
    report(diff_mode_ok(out), f"working tree opencode.json + agents/x.md: critical and prose-lane lines: {out!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
