#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md, and the pin for the vendored ones.

A wrong skill header fails silently in opencode, so assert the contract the host
requires: `name` matches the directory, is a slug, and the description is in
bounds. A skill that names a file it does not ship fails at the moment an agent
needs it, so every `references/`, `scripts/` or `assets/` path in the body must
exist beside SKILL.md.

`skills/UPSTREAM.sha256` pins the files copied verbatim from another repository.
It is the "do not edit them here" rule made executable: a hand edit, a stale
re-vendor, or a file that appears in a vendored skill without being pinned all
fail. The file is standard `sha256sum` output, relative to `skills/`.

VENDORED is the expected set. A pin file cannot describe its own completeness:
emptied, it would pass. Adding a vendored skill is a deliberate line here, which
is the point of a pin.
"""

import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
PINNED = SKILLS / "UPSTREAM.sha256"

VENDORED = ("assertion-quality", "platform-detection", "run-tests", "test-anti-patterns")

PATH_REF = re.compile(r"\b((?:references|scripts|assets)/[A-Za-z0-9._/-]+\.[A-Za-z0-9]+)\b")
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SHA256 = re.compile(r"[0-9a-f]{64}")
DESCRIPTION_MAX = 1024
BLOCK_SCALARS = (">", ">-", ">+", "|", "|-", "|+")


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0 or text[end + 4 : end + 5] not in ("", "\n"):
        return None
    lines = text[4:end].splitlines()
    fields: dict[str, str] = {}
    i = 0
    while i < len(lines):
        match = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        i += 1
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in BLOCK_SCALARS or not value:
            block = []
            while i < len(lines) and lines[i].startswith((" ", "\t")):
                if lines[i].strip():
                    block.append(lines[i].strip())
                i += 1
            if value in BLOCK_SCALARS or block:
                value = " ".join(block)
        fields[key] = value.strip("\"'")
    return fields


def check_skill(path: pathlib.Path, failures: list[str]) -> None:
    name = path.parent.name
    text = path.read_text()
    fields = frontmatter(text)
    if fields is None:
        failures.append(f"{name}: no frontmatter block")
        return
    declared = fields.get("name", "")
    if declared != name:
        failures.append(f"{name}: frontmatter name is {declared!r}, expected {name!r}")
    if not SLUG.fullmatch(declared):
        failures.append(f"{name}: name {declared!r} is not a slug")
    description = fields.get("description", "")
    if not description:
        failures.append(f"{name}: no description; the host will not advertise it")
    elif len(description) > DESCRIPTION_MAX:
        failures.append(f"{name}: description is {len(description)} chars, over {DESCRIPTION_MAX}")
    for ref in sorted(set(PATH_REF.findall(text))):
        if not (path.parent / ref).exists():
            failures.append(f"{name}: names {ref}, which is not shipped beside SKILL.md")


def check_pin(failures: list[str]) -> set[str]:
    """Verify the pin, that it covers every file of a pinned skill, and that the
    pinned set is the expected one."""
    if not PINNED.exists():
        failures.append(f"{PINNED.relative_to(ROOT)}: missing; see the re-vendor command in skills/UPSTREAM.md")
    entries: dict[str, str] = {}
    for number, line in enumerate(PINNED.read_text().splitlines() if PINNED.exists() else [], 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"UPSTREAM.sha256:{number}: expected '<sha256>  <path>'")
            continue
        digest, rel = parts
        if not SHA256.fullmatch(digest):
            failures.append(f"UPSTREAM.sha256:{number}: {digest!r} is not a sha256")
        if rel in entries:
            failures.append(f"UPSTREAM.sha256:{number}: {rel} is pinned twice")
        entries[rel] = digest
    for rel, expected in sorted(entries.items()):
        path = SKILLS / rel
        if not path.is_file():
            failures.append(f"UPSTREAM.sha256: {rel} is pinned but missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(
                f"{rel}: sha256 {actual[:12]}... does not match the pin {expected[:12]}...; "
                "edited in place, or re-vendored without re-pinning"
            )
    pinned_dirs = {rel.split("/", 1)[0] for rel in entries}
    for directory in sorted(pinned_dirs):
        for path in sorted((SKILLS / directory).rglob("*")):
            if path.is_file():
                rel = path.relative_to(SKILLS).as_posix()
                if rel not in entries:
                    failures.append(f"{rel}: not pinned; a vendored skill gained a file")
    for name in sorted(set(VENDORED) - pinned_dirs):
        failures.append(f"{name}: listed in VENDORED but nothing of it is pinned")
    for name in sorted(pinned_dirs - set(VENDORED)):
        failures.append(f"{name}: pinned but not listed in VENDORED; add it deliberately or drop the pin")
    return pinned_dirs


def main() -> int:
    failures: list[str] = []
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    if not skills:
        print("FAIL no skills found")
        return 1
    for path in skills:
        check_skill(path, failures)
        print(f"checked {path.parent.name}")
    for directory in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        if not (directory / "SKILL.md").is_file():
            failures.append(f"{directory.name}: skill directory without SKILL.md; install.cs links it anyway")
    pinned_dirs = check_pin(failures)
    if pinned_dirs:
        print(f"pinned {len(pinned_dirs)} vendored skills")
    if failures:
        for message in failures:
            print(f"FAIL {message}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
