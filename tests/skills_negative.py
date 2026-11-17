#!/usr/bin/env python3
"""The skills validator must fail on broken trees, not only pass on a good one.

Same shape as tests/lint_config.py: copy the tree, break one thing, expect
tests/skills.py to exit 1 naming the break. A validator whose failures nobody
tests is a green light with no bulb.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(tree: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "tests/skills.py"], cwd=tree, capture_output=True, text=True)


def expect(name: str, tree: pathlib.Path, marker: str) -> bool:
    result = run(tree)
    output = result.stdout + result.stderr
    ok = result.returncode == 1 and marker in output
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        print(f"  rc={result.returncode}, expected 1 mentioning {marker!r}\n{output}")
    return ok


def edit(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise AssertionError(f"{path}: missing {old!r}")
    path.write_text(text.replace(old, new))


def main() -> int:
    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        pristine = pathlib.Path(tmp) / "pristine"
        shutil.copytree(ROOT / "skills", pristine / "skills")
        shutil.copytree(ROOT / "tests", pristine / "tests", ignore=shutil.ignore_patterns("__pycache__"))

        result = run(pristine)
        if result.returncode != 0:
            print(f"FAIL unmodified copy: rc={result.returncode}\n{result.stdout}{result.stderr}")
            failed = True
        else:
            print("ok unmodified copy")

        pin = pristine / "skills" / "UPSTREAM.sha256"

        def case(name: str, marker: str, mutate) -> None:
            nonlocal failed
            tree = pathlib.Path(tmp) / name.replace(" ", "-").replace("'", "")
            if tree.exists():
                shutil.rmtree(tree)
            shutil.copytree(pristine, tree)
            mutate(tree)
            failed |= not expect(name, tree, marker)

        case("edited vendored file", "does not match the pin",
             lambda t: edit(t / "skills/run-tests/SKILL.md", "# Run .NET Tests", "# Run .NET Tests edited"))
        case("pinned file missing", "pinned but missing",
             lambda t: (t / "skills/platform-detection/references/command-mode.md").unlink())
        case("unpinned file added", "a vendored skill gained a file",
             lambda t: (t / "skills/run-tests/references").mkdir()
             or (t / "skills/run-tests/references/extra.md").write_text("x\n"))
        case("name does not match directory", "expected 'run-tests'",
             lambda t: edit(t / "skills/run-tests/SKILL.md", "name: run-tests", "name: run-testing"))
        case("description removed", "no description",
             lambda t: edit(t / "skills/assertion-quality/SKILL.md",
                            "description: \"Analyze assertion quality", "x-description: \"Analyze assertion quality"))
        case("shipped reference missing", "which is not shipped",
             lambda t: (t / "skills/platform-detection/references/command-mode.md").unlink()
             or edit(t / "skills/UPSTREAM.sha256",
                     "08e276dcafe6bd5bfbaab435065ca24a5800a4eae3ffd7fc15daa1e81354bbc4  platform-detection/references/command-mode.md\n", ""))
        case("empty pin", "listed in VENDORED",
             lambda t: (t / "skills/UPSTREAM.sha256").write_text("# emptied\n"))
        case("pinned set shrinks", "assertion-quality: listed in VENDORED",
             lambda t: (t / "skills/UPSTREAM.sha256").write_text(
                 "".join(line for line in pin.read_text().splitlines(True)
                         if "assertion-quality/" not in line)))
        case("directory without SKILL.md", "without SKILL.md",
             lambda t: (t / "skills/half-vendored").mkdir())

    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
