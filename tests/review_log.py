#!/usr/bin/env python3
"""bin/review-log records what each gate catches, one file per record.

#41 deleted the review ledger's writer along with the machinery it measured,
so from 2026-11-14 nothing could say whether a gate caught anything. v2 brings
the ledger back with a `kind` (review, consult, verify) so every gate is
measured, and writes one file per record so parallel reviewers never append
to a shared file. The 89 legacy rows in reviews.jsonl are read, never rewritten.
"""
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "bin" / "review-log"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def run(base: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LOG), "--dir", str(base / "reviews"),
                           "--legacy", str(base / "reviews.jsonl"), *args],
                          capture_output=True, text=True, timeout=60)


def add(base: Path, kind: str, red: int = 0, date: str | None = None) -> subprocess.CompletedProcess:
    extra = ["--date", date] if date else []
    return run(base, "add", "--kind", kind, "--artifact", "change", "--model", "claude-agent/sonnet",
               "--harness", "claude", "--head", "abc1234", "--red", str(red), "--amber", "1",
               "--acted", "1", "--dismissed", "0", *extra)


with tempfile.TemporaryDirectory() as raw:
    base = Path(raw)
    legacy = base / "reviews.jsonl"
    legacy_rows = [{"id": "old1", "ts": "2026-11-01T00:00:00+00:00", "artifact": "change", "red": 2, "amber": 1, "acted": 3, "dismissed": 0},
                   {"id": "old2", "ts": "2026-11-02T00:00:00+00:00", "artifact": "plan", "red": 0, "amber": 2, "acted": 1, "dismissed": 1}]
    legacy.write_text("".join(json.dumps(r) + "\n" for r in legacy_rows))
    before = legacy.read_bytes()

    r = add(base, "review", red=1)
    check(r.returncode == 0, f"add writes a record (got {r.returncode}: {r.stderr.strip()[-200:]})")
    files = list((base / "reviews").glob("*.json"))
    check(len(files) == 1, f"one record is one file (got {len(files)})")
    rec = json.loads(files[0].read_text()) if files else {}
    check(rec.get("kind") == "review" and rec.get("red") == 1 and rec.get("harness") == "claude",
          "the record keeps kind, counts and harness")
    check(r.stdout.strip() == rec.get("id"), "add prints the new record's id")

    # Parallel reviewers never clobber each other.
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: add(base, "consult"), range(8)))
    check(all(x.returncode == 0 for x in results), "eight concurrent adds all succeed")
    check(len(list((base / "reviews").glob("*.json"))) == 9, "eight concurrent adds leave eight more records")

    r = run(base, "resolve", rec["id"], "--acted", "0", "--dismissed", "2")
    check(r.returncode == 0, f"resolve updates a record (got {r.returncode})")
    again = json.loads(files[0].read_text())
    check(again.get("acted") == 0 and again.get("dismissed") == 2 and "resolved_at" in again,
          "resolve rewrites only that record's counts and stamps it")
    check(run(base, "resolve", "nope", "--acted", "1").returncode != 0, "resolving an unknown id fails")

    r = run(base, "summary", "--now", "2026-11-21T00:00:00+00:00")
    out = r.stdout
    check(r.returncode == 0, f"summary runs (got {r.returncode}: {r.stderr.strip()[-200:]})")
    check("review   records 3" in out, "summary counts the legacy rows as reviews alongside new ones")
    check("consult  records 8" in out, "summary counts consults")
    check("verify   records 0" in out and "no record in 30 days" in out, "a gate kind with no records is flagged")
    check(legacy.read_bytes() == before, "the legacy ledger is never rewritten")

    r = add(base, "bogus")
    check(r.returncode != 0, "an unknown kind is refused")

    # Review of d512ffe (Sonnet): a gate measure must survive bad input.
    check(add(base, "review", date="garbage").returncode != 0, "an unparseable --date is refused")
    check(run(base, "add", "--kind", "review", "--artifact", "change", "--model", "m", "--harness", "claude",
              "--red", "-5").returncode != 0, "a negative count is refused")
    one = Path(raw) / "one"
    add(one, "review")
    check(run(one, "resolve", "*", "--acted", "1").returncode != 0, "resolve does not treat the id as a glob")
    (base / "reviews" / "zz-array.json").write_text("[]")
    (base / "reviews" / "zz-badcount.json").write_text('{"kind": "consult", "red": "z", "date": "2026-11-20T00:00:00+00:00"}')
    with legacy.open("a") as handle:
        handle.write('{"id": "old3", "ts": "2026-11-03T00:00:00", "red": "x"}\n')
    r = run(base, "summary", "--now", "2026-11-21T00:00:00+00:00")
    check(r.returncode == 0, f"summary survives malformed rows (got {r.returncode}: {r.stderr.strip()[-160:]})")
    check("consult  records 9" in r.stdout, "a record with a bad count still counts, as zero")

    # A kind whose last record is older than the window is flagged too.
    stale = Path(raw) / "stale"
    add(stale, "verify", date="2026-10-01T00:00:00+00:00")
    r = run(stale, "summary", "--now", "2026-11-21T00:00:00+00:00")
    check("verify   records 1" in r.stdout and "no record in 30 days" in r.stdout.split("verify", 1)[1],
          "a kind last recorded 51 days ago is flagged")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
