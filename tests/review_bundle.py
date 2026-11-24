#!/usr/bin/env python3
"""Tests for review-bundle's evidence sections: test changes and recorded checks.

Each case builds a throwaway git repo, bundles it, and reads the section files.
The bundle root is redirected with OPENCODE_TMP so nothing lands in the user's
temp dir.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "bin", "review-bundle")

_loader = importlib.machinery.SourceFileLoader("review_bundle_tested", PATH)
_spec = importlib.util.spec_from_loader("review_bundle_tested", _loader)
review_bundle = importlib.util.module_from_spec(_spec)
_loader.exec_module(review_bundle)

failures = []


def check(ok, message):
    print(f"{'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def git(repo, *args):
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
        GIT_CONFIG_NOSYSTEM="1",
        HOME=repo,
    )
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, env=env, check=True
    )


def make_repo(root, files):
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q")
    write(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def write(repo, files):
    for rel, body in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path) or repo, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(body)


def bundle(repo, root, *extra, env=None):
    tmp = os.path.join(root, "bundles")
    os.makedirs(tmp, exist_ok=True)
    saved = {k: os.environ.get(k) for k in ("OPENCODE_TMP", *(env or {}))}
    os.environ["OPENCODE_TMP"] = tmp
    os.environ.update(env or {})
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = review_bundle.main([repo, *extra])
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return rc, out.getvalue().strip(), err.getvalue(), tmp


def bundle_dir(tmp):
    made = os.path.join(tmp, "review-bundles")
    return os.path.join(made, os.listdir(made)[0])


def sections(cwd):
    return {name: open(os.path.join(cwd, name)).read() for name in sorted(os.listdir(cwd))}


def section(files, prefix):
    names = [n for n in files if n.startswith(prefix)]
    return "".join(files[n] for n in sorted(names))


BASE_TEST = """def test_add():
    assert add(1, 2) == 3
    assert add(2, 2) == 4
"""


def case_removed_assertion_and_skip(root):
    repo = make_repo(root, {"tests/test_math.py": BASE_TEST})
    write(
        repo,
        {
            "tests/test_math.py": """import pytest


@pytest.mark.skip
def test_add():
    assert add(1, 2) == 3
"""
        },
    )
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    cwd = bundle_dir(tmp)
    body = section(sections(cwd), "06-test-changes")
    check("### removed assertion" in body, f"{root}: 06 has a removed-assertion section")
    check("tests/test_math.py:3" in body, f"{root}: 06 gives the removed line's old line number")
    check("assert add(2, 2) == 4" in body, f"{root}: 06 quotes the removed assertion")
    check("### added skip" in body, f"{root}: 06 has an added-skip section")
    check("pytest.mark.skip" in body, f"{root}: 06 quotes the added skip marker")
    check("07-checks" not in " ".join(sections(cwd)), f"{root}: no check section without --check")


def case_deleted_and_moved(root):
    repo = make_repo(
        root,
        {
            "tests/test_gone.py": "def test_gone():\n    assert True\n",
            "tests/test_move.py": "def test_move():\n    assert True\n",
        },
    )
    git(repo, "rm", "-q", "tests/test_gone.py")
    git(repo, "mv", "tests/test_move.py", "subject.py")
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    cwd = bundle_dir(tmp)
    body = section(sections(cwd), "06-test-changes")
    check("tests/test_gone.py" in body, f"{root}: 06 names the deleted test file")
    check("### deleted test file" in body, f"{root}: 06 has a deleted-file section")
    check("tests/test_move.py" in body, f"{root}: 06 names the relocated test file")
    check("### test file moved out of a test path" in body, f"{root}: 06 has a moved-file section")


def case_clean_change(root):
    repo = make_repo(root, {"src/app.py": "def f():\n    return 1\n"})
    write(repo, {"src/app.py": "def f():\n    return 2\n"})
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    cwd = bundle_dir(tmp)
    body = section(sections(cwd), "06-test-changes")
    check(body.startswith("test changes: none"), f"{root}: 06 states none explicitly, not by omission")


def case_check_evidence(root):
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    second = "printf 'MARK-OUT\\n'; printf 'MARK-ERR\\n' >&2; exit 7"
    rc, _out, err, tmp = bundle(repo, root, "--check", "true", "--check", second)
    check(rc == 0, f"{root}: a failing check does not fail the bundle ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "07-checks")
    check(body.count("### check:") == 2, f"{root}: 07 records both commands")
    check("### check: true" in body, f"{root}: 07 records the first command")
    check("exit: 0" in body, f"{root}: 07 records a passing exit code")
    check(f"### check: {second}" in body, f"{root}: 07 records the second command")
    check("exit: 7" in body, f"{root}: 07 records the failing exit code")
    output = body.rsplit("--- output", 1)[1]
    check("MARK-OUT" in output, f"{root}: 07 keeps stdout")
    check("MARK-ERR" in output, f"{root}: 07 keeps stderr")


def case_check_timeout(root):
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    rc, _out, err, tmp = bundle(repo, root, "--check", "sleep 5", "--check-timeout", "1")
    check(rc == 0, f"{root}: a timed-out check still yields a bundle ({err.strip()})")
    cwd = bundle_dir(tmp)
    body = section(sections(cwd), "07-checks")
    check("timeout" in body, f"{root}: 07 records the timeout instead of dropping the run")


def case_skip_word_is_not_a_skip(root):
    repo = make_repo(root, {"src/config.py": "PATTERN = 1\n"})
    write(repo, {"src/config.py": 'PATTERN = 1\nSKIP = re.compile(r"x")\nskip_things = True\n'})
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    cwd = bundle_dir(tmp)
    body = section(sections(cwd), "06-test-changes")
    check("### added skip" not in body, f"{root}: a variable named SKIP is not an added skip")


def case_untracked_test_skip(root):
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    write(repo, {"tests/test_new.py": "import pytest\n\n\n@pytest.mark.skip\ndef test_new():\n    assert 1\n"})
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "06-test-changes")
    check("### added skip" in body, f"{root}: an untracked test file is scanned for skips")
    check("tests/test_new.py:" in body, f"{root}: the untracked skip names its file and line")


def case_test_layouts(root):
    """.test.ts, a *.UnitTests project, and a root FooTests.cs are all test paths."""
    files = {
        "src/app.test.ts": "it('a', () => {\n  expect(1).toBe(1);\n  expect(2).toBe(2);\n});\n",
        "MyApp.UnitTests/CalcTests.cs": "public class T {\n  [Fact]\n  public void A() {\n    Assert.True(true);\n    Assert.False(true);\n  }\n}\n",
        "FooTests.cs": "public class T {\n  [Fact]\n  public void B() {\n    Assert.True(true);\n    Assert.False(true);\n  }\n}\n",
    }
    repo = make_repo(root, files)
    write(
        repo,
        {
            "src/app.test.ts": "it('a', () => {\n  expect(1).toBe(1);\n});\n",
            "MyApp.UnitTests/CalcTests.cs": "public class T {\n  [Fact]\n  public void A() {\n    Assert.True(true);\n  }\n}\n",
            "FooTests.cs": "public class T {\n  [Fact]\n  public void B() {\n    Assert.True(true);\n  }\n}\n",
        },
    )
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "06-test-changes")
    for rel in ("src/app.test.ts", "MyApp.UnitTests/CalcTests.cs", "FooTests.cs"):
        check(f"{rel}:" in body, f"{root}: a removed assertion in {rel} is reported")


def case_zero_timeout_is_refused(root):
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    rc, _out, err, _tmp = bundle(repo, root, "--check", "true", "--check-timeout", "0")
    check(rc == 2, f"{root}: --check-timeout 0 is a usage error (rc={rc})")
    check("--check-timeout" in err, f"{root}: the refusal names the flag ({err.strip()[:120]})")


def case_skip_word_in_a_string(root):
    """A marker quoted inside a fixture is not a skipped test."""
    repo = make_repo(root, {"src/app.py": "x = 1\n", "docs/guide.py": '"""A skip looks like this."""\n'})
    write(
        repo,
        {
            "tests/test_strings.py": (
                "def test_a():\n"
                "    body = check(\"pytest.mark.skip\" in text)\n"
                "    assert body\n"
            ),
            "docs/guide.py": (
                '"""A skip looks like (`[Fact(Skip = \"x\")]`)."""\n'
                "# [Fact(Skip = \"x\")] in a comment is not a skip either\n"
            ),
        },
    )
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "06-test-changes")
    check("### added skip" not in body, f"{root}: a quoted marker in code and in prose is not an added skip")


SKIP_FORMS = {
    "Engine/Calc.cs": ("[Fact]\npublic void A() { }\n", "[Fact(Skip = \"flaky\")]\npublic void A() { }\n"),
    "Engine/Theory.cs": ("[Fact]\npublic void B() { }\n", "[Theory(Skip=\"x\")]\npublic void B() { }\n"),
    "Engine/Ignored.cs": ("[Test]\npublic void C() { }\n", "[Test, Ignore(\"x\")]\npublic void C() { }\n"),
    "web/app.test.ts": ("it('a', () => {});\n", "it.skip('a', () => {});\n"),
    "web/desc.test.ts": ("describe('x', () => {});\n", "describe.skip('x', () => {});\n"),
    "web/t.test.ts": ("test('x', () => {});\n", "test.skip('x', () => {});\n"),
    "Engine/Two.cs": ("[Test]\npublic void D() { }\n", "[Test] [Ignore(\"x\")]\npublic void D() { }\n"),
    "Engine/TwoFacts.cs": ("[Fact]\npublic void E() { }\n", "[Fact, Trait(\"a\",\"b\")] [Fact(Skip=\"x\")]\npublic void E() { }\n"),
    "jvm/Pair.java": ("@Test\npublic void F() { }\n", "@Test @Disabled\npublic void F() { }\n"),
}


def case_skip_forms(root):
    """The forms people actually use must not be silently dropped."""
    repo = make_repo(root, {rel: before for rel, (before, _after) in SKIP_FORMS.items()})
    write(repo, {rel: after for rel, (_before, after) in SKIP_FORMS.items()})
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "06-test-changes")
    check("### added skip" in body, f"{root}: 06 has an added-skip section")
    skips = body.split("### added skip", 1)[1] if "### added skip" in body else ""
    for rel, (_before, _after) in SKIP_FORMS.items():
        check(f"{rel}:" in skips, f"{root}: {rel} skip form is in the added-skip section")


def case_untracked_symlink(root):
    """An untracked symlink is not followed: 03 skips it, so 06 must too."""
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    outside = os.path.join(root, "outside.py")
    with open(outside, "w") as fh:
        fh.write("import pytest\n\n\n@pytest.mark.skip\ndef test_x():\n    assert 1\n")
    os.makedirs(os.path.join(repo, "tests"))
    os.symlink(outside, os.path.join(repo, "tests", "link_test.py"))
    rc, _out, err, tmp = bundle(repo, root)
    check(rc == 0, f"{root}: bundle succeeds ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "06-test-changes")
    check("link_test.py" not in body, f"{root}: an untracked symlink is not scanned")


def case_timeout_is_bounded(root):
    """A timed-out check returns promptly, with its children killed and the run recorded."""
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    started = time.monotonic()
    rc, _out, err, tmp = bundle(repo, root, "--check", "sleep 30 & sleep 30", "--check-timeout", "1")
    elapsed = time.monotonic() - started
    check(rc == 0, f"{root}: a timed-out check still yields a bundle ({err.strip()})")
    check(elapsed < 15, f"{root}: a timed-out check returns promptly ({elapsed:.1f}s)")
    body = section(sections(bundle_dir(tmp)), "07-checks")
    check("timeout after 1s" in body, f"{root}: 07 records the timeout")


def case_timeout_records_cut_output(root):
    """A child that escaped the process group must not hang the bundle."""
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    escaped = "echo BEFORE-ESCAPE; python3 -c 'import os,time;os.setsid();time.sleep(60)' & sleep 30"
    started = time.monotonic()
    rc, _out, err, tmp = bundle(repo, root, "--check", escaped, "--check-timeout", "1")
    elapsed = time.monotonic() - started
    check(rc == 0, f"{root}: an escaping child still yields a bundle ({err.strip()})")
    check(elapsed < 25, f"{root}: an escaping child does not hang the bundle ({elapsed:.1f}s)")
    body = section(sections(bundle_dir(tmp)), "07-checks")
    check("timeout after 1s" in body, f"{root}: 07 records the timeout")
    output = body.split("--- output", 1)[1]
    check("output cut" in output, f"{root}: 07 says the output was cut, not that it was empty")
    check(output.count("BEFORE-ESCAPE") == 1, f"{root}: 07 keeps the output it read before the kill, once")


def case_timeout_does_not_duplicate(root):
    """CPython keeps what communicate read, so the second call returns it again."""
    repo = make_repo(root, {"src/app.py": "x = 1\n"})
    rc, _out, err, tmp = bundle(repo, root, "--check", "echo ONCE-ONLY; sleep 30", "--check-timeout", "1")
    check(rc == 0, f"{root}: a timed-out check still yields a bundle ({err.strip()})")
    body = section(sections(bundle_dir(tmp)), "07-checks")
    output = body.split("--- output", 1)[1]
    check(output.count("ONCE-ONLY") == 1, f"{root}: 07 records the output once, not twice ({output.count('ONCE-ONLY')}x)")


CASES = (
    case_removed_assertion_and_skip,
    case_deleted_and_moved,
    case_clean_change,
    case_check_evidence,
    case_check_timeout,
    case_skip_word_is_not_a_skip,
    case_untracked_test_skip,
    case_test_layouts,
    case_zero_timeout_is_refused,
    case_skip_word_in_a_string,
    case_skip_forms,
    case_untracked_symlink,
    case_timeout_is_bounded,
    case_timeout_records_cut_output,
    case_timeout_does_not_duplicate,
)


def main():
    for case in CASES:
        root = tempfile.mkdtemp(prefix="rb-test-")
        try:
            case(root)
        except Exception as exc:  # a case that raises is a failure, not a pass
            check(False, f"{case.__name__}: raised {type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
