#!/usr/bin/env python3
"""Tests for the Grok Bot webhook setup and notify-bot helper.

Everything runs against a temporary HOME and a local HTTP listener. The auth
values are generated at runtime, so no credential-shaped literal lives here.
"""

import importlib.machinery
import importlib.util
import json
import re
import os
import pwd
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
SETUP = BIN / "setup-bot-webhooks"
NOTIFY = BIN / "notify-bot"

failures = []


def check(condition, label):
    if condition:
        print(f"ok   {label}")
    else:
        print(f"FAIL {label}")
        failures.append(label)


def load_notify():
    loader = importlib.machinery.SourceFileLoader("notify_bot", str(NOTIFY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_setup():
    loader = importlib.machinery.SourceFileLoader("setup_bot_webhooks", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def base_env(home, env_path):
    clean = {
        key: value
        for key, value in os.environ.items()
        if not re.fullmatch(r"[A-Za-z0-9_]+_WEBHOOK_(URL|AUTH)", key)
    }
    clean.update({
        "HOME": str(home),
        "SHELL": "/bin/zsh",
        "BOT_WEBHOOKS_ENV": str(env_path),
        "PYTHONPATH": str(ROOT),
    })
    clean.pop("XDG_CONFIG_HOME", None)
    return clean


def run(args, env, stdin=""):
    return subprocess.run(
        [sys.executable, *args],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )


NOTIFY_RUNNER = r'''
import importlib.machinery as m
import importlib.util as u
import sys
from pathlib import Path

loader = m.SourceFileLoader("n", sys.argv[1])
spec = u.spec_from_loader("n", loader)
mod = u.module_from_spec(spec)
loader.exec_module(mod)
path = Path(sys.argv[2])
args = sys.argv[3:]
if args[:1] == ["--list"]:
    sys.exit(mod.list_bots(path))
if args[:1] == ["--test"]:
    sys.exit(mod.send(args[1], "test", "notify-bot test", "local-test", path))
sys.exit(mod.send(args[0], args[1], args[2], args[3] if len(args) > 3 else "", path))
'''


def notify(env, env_path, *args):
    return subprocess.run(
        [sys.executable, "-c", NOTIFY_RUNNER, str(NOTIFY), str(env_path), *args],
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )


def configured(line):
    parts = line.split()
    return len(parts) >= 2 and parts[1] == "configured"


class Listener:
    """A local HTTP listener that records the last request."""

    def __init__(self, status=202, location=None):
        self.requests = []
        self.status = status
        self.location = location
        self.lock = threading.Lock()
        listener = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                with listener.lock:
                    listener.requests.append({
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    })
                payload = b'{"ok":true}'
                self.send_response(listener.status)
                if listener.location:
                    self.send_header("Location", listener.location)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            # urllib follows a 302 on a POST with a GET; record it so the redirect
            # test fails if the header travels to the second host.
            do_GET = do_POST

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        host, port = self.server.server_address
        return f"http://{host}:{port}/hook"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def main():
    for path in (SETUP, NOTIFY):
        if not path.is_file():
            print(f"FAIL missing {path.relative_to(ROOT)}")
            return 1

    module = load_notify()
    check(module.normalize_auth("abc123") == "Bearer abc123", "bare key gets Bearer")
    check(module.normalize_auth("Bearer abc123") == "Bearer abc123", "Bearer value is kept")
    check(module.normalize_auth("Basic abc123") == "Basic abc123", "Basic value is kept")
    check(module.normalize_auth("  Token xyz  ") == "Token xyz", "value is trimmed")
    check(module.normalize_auth("Authorization: Bearer abc") == "Bearer abc",
          "a pasted Authorization label is stripped")
    check(module.normalize_auth("bearer abc") == "bearer abc", "a lower-case scheme is kept")
    try:
        module.normalize_auth("Bearer a\rb")
    except ValueError:
        check(True, "a control character is refused")
    else:
        check(False, "a control character is refused")
    # The bot list is the person's config, not the code (2026-11-22: friends use this repo).
    check("ENGINEERING_LEAD" not in NOTIFY.read_text(), "notify-bot carries no person's bot names")
    with tempfile.TemporaryDirectory() as listing_tmp:
        empty = Path(listing_tmp) / "empty"
        empty.write_text("")
        check(module.bots(Path(listing_tmp) / "missing") == () and module.bots(empty) == (),
              "no config file, or an empty one, means no bots")
        listed = Path(listing_tmp) / "env"
        listed.write_text(
            "export B_WEBHOOK_URL='https://example.test/b'\nexport B_WEBHOOK_AUTH='Bearer x'\n"
            "export A_WEBHOOK_URL='https://example.test/a'\nexport A_WEBHOOK_AUTH='Bearer y'\n"
            "export C_WEBHOOK_URL='https://example.test/c'\n"
            "export D_WEBHOOK_AUTH='Bearer z'\n"
            "export lower_WEBHOOK_URL='https://example.test/l'\nexport _WEBHOOK_URL='https://x.test'\n"
            "export 9X_WEBHOOK_URL='https://example.test/9'\nexport SLACK_TOKEN='keep'\n")
        check(module.bots(listed) == ("B", "A", "C", "D"),
              f"bots come from the file in file order, URL-only and auth-only included (got {module.bots(listed)})")
        check(set(load_setup().read_bots(module.load_config(listed))) == set(module.bots(listed)),
              "setup and notify-bot read the same bot list")
    check(os.access(NOTIFY, os.X_OK) and os.access(SETUP, os.X_OK), "both bin scripts are executable")
    check(module.url_problem("https://example.test/hook") is None, "https is accepted")
    check(module.url_problem("http://127.0.0.1:9/hook") is None, "loopback http is accepted")
    check(module.url_problem("http://example.test/hook") is not None, "plain http elsewhere is refused")
    check(module.url_problem("ftp://example.test/hook") is not None, "a non-http scheme is refused")

    expected = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / "bot-webhooks" / "env"
    probe_env = dict(
        os.environ,
        HOME=str(Path(tempfile.gettempdir()) / "bot-webhooks-fake-home"),
        BOT_WEBHOOKS_ENV="/tmp/not-the-config",
        XDG_CONFIG_HOME="/tmp/not-the-config",
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.machinery as m, importlib.util as u, sys; "
            "l=m.SourceFileLoader('n', sys.argv[1]); s=u.spec_from_loader('n', l); "
            "mod=u.module_from_spec(s); l.exec_module(mod); print(mod.default_env_path())",
            str(NOTIFY),
        ],
        text=True,
        capture_output=True,
        env=probe_env,
        timeout=30,
    )
    check(probe.stdout.strip() == str(expected),
          "notify-bot pins its config path to the real home, not $HOME or XDG")

    secret = secrets.token_hex(16)
    other = secrets.token_hex(16)

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        env_path = home / ".config" / "bot-webhooks" / "env"
        env = base_env(home, env_path)

        # Unconfigured: a clear nonzero failure, no secret, no URL echo.
        listing = notify(env, env_path, "--list")
        check(listing.returncode == 0, "--list succeeds without a config file")
        check("no bots configured" in listing.stdout, "--list with no config says no bots are configured")

        missing = notify(env, env_path, "JARVIS", "done", "nothing to send")
        check(missing.returncode == 2, "unconfigured bot exits 2")
        check("JARVIS" in missing.stderr and "not configured" in missing.stderr, "unconfigured message names the bot")
        check("http" not in missing.stdout + missing.stderr, "unconfigured output has no URL")

        # The file is the only source: exported values alone do not configure a bot.
        env["JARVIS_WEBHOOK_URL"] = "http://127.0.0.1:9/no-file"
        env["JARVIS_WEBHOOK_AUTH"] = secret
        env_only = notify(env, env_path, "JARVIS", "done", "still nothing")
        check(env_only.returncode == 2, "exported values do not override the webhook file")
        env.pop("JARVIS_WEBHOOK_URL")
        env.pop("JARVIS_WEBHOOK_AUTH")

        usage = run([str(NOTIFY)], env)
        check(usage.returncode == 0 and "notify-bot <bot>" in usage.stdout,
              "notify-bot with no args prints usage")
        unknown = run([str(NOTIFY), "NOPE", "done", "x"], env)
        check(unknown.returncode == 2 and "not configured" in unknown.stderr and "--add NOPE" in unknown.stderr,
              "a bot not in the config exits 2 and says how to add it")
        bad_test = run([str(NOTIFY), "--test"], env)
        check(bad_test.returncode == 2, "--test without a bot exits 2")

        # Non-interactive setup from the environment.
        with Listener() as listener:
            env["JARVIS_WEBHOOK_URL"] = listener.url
            env["JARVIS_WEBHOOK_AUTH"] = secret
            first = run([str(SETUP), "--non-interactive", "--no-rc", "--add", "JARVIS"], env)
            check(first.returncode == 0, "non-interactive setup exits 0")
            check(env_path.is_file(), "env file is written")
            check((env_path.stat().st_mode & 0o777) == 0o600, "env file is 0600")
            check((env_path.parent.stat().st_mode & 0o777) == 0o700, "env directory is 0700")
            text = env_path.read_text()
            check(f"export JARVIS_WEBHOOK_URL='{listener.url}'" in text, "env file exports the URL")
            check(f"export JARVIS_WEBHOOK_AUTH='Bearer {secret}'" in text, "bare auth key is stored and exported with Bearer")
            check(secret not in first.stdout + first.stderr, "setup output has no secret")

            again = run([str(SETUP), "--non-interactive", "--no-rc"], env)
            check(again.returncode == 0, "second setup run exits 0")
            check(env_path.read_text() == text, "second setup run is idempotent")

            # A POST to the local listener.
            sent = notify(env, env_path, "JARVIS", "done", "shipped the webhook setup", "thread-123")
            check(sent.returncode == 0, "notify-bot posts and exits 0")
            check(len(listener.requests) == 1, "listener saw exactly one request")
            request = listener.requests[0]
            check(request["path"] == "/hook", "request path is the configured URL")
            check(request["headers"].get("authorization") == f"Bearer {secret}", "Authorization header is exact")
            check(request["headers"].get("content-type") == "application/json", "Content-Type is JSON")
            body = json.loads(request["body"])
            check(body == {
                "bot": "JARVIS",
                "thread": "thread-123",
                "status": "done",
                "summary": "shipped the webhook setup",
            }, "payload has bot, thread, status and summary")
            check(secret not in sent.stdout + sent.stderr, "notify-bot output has no secret")

            tested = notify(env, env_path, "--test", "jarvis")
            check(tested.returncode == 0, "--test posts and exits 0")
            check(json.loads(listener.requests[-1]["body"])["status"] == "test", "--test sends status test")

            listed = notify(env, env_path, "--list")
            check(listed.returncode == 0, "--list succeeds when configured")
            lines = {line.split()[0]: line for line in listed.stdout.splitlines() if line.split()}
            check(configured(lines.get("JARVIS", "")), "--list shows JARVIS configured")
            check("FORGE" not in lines, "--list does not show a bot that was never added")
            # Review of de8b3b8: a bot named but incomplete is listed as not configured.
            partial_path = Path(tmp) / "partial" / "env"
            partial_path.parent.mkdir()
            partial_path.write_text(f"export JARVIS_WEBHOOK_URL='{listener.url}'\n"
                                    f"export JARVIS_WEBHOOK_AUTH='Bearer {secret}'\n"
                                    "export FORGE_WEBHOOK_URL='https://example.test/forge'\n")
            partial = notify(env, partial_path, "--list")
            partial_lines = {line.split()[0]: line for line in partial.stdout.splitlines() if line.split()}
            check(configured(partial_lines.get("JARVIS", "")) and "FORGE" in partial_lines
                  and not configured(partial_lines["FORGE"]),
                  "--list shows a named but incomplete bot as not configured")
            check(secret not in listed.stdout and listener.url not in listed.stdout,
                  "--list prints no secret and no URL")

            other_missing = notify(env, env_path, "FORGE", "done", "not for forge")
            check(other_missing.returncode == 2, "an unconfigured bot exits 2 when another is configured")
            check(secret not in other_missing.stdout + other_missing.stderr
                  and listener.url not in other_missing.stdout + other_missing.stderr,
                  "an unconfigured bot prints no other bot's secret or URL")

            # A changed host with a blank auth is refused instead of reusing the old key.
            before_rotation = env_path.read_text()
            rotated = run([str(SETUP), "--no-rc"], env, stdin="http://localhost:9/other\n\n")
            check(rotated.returncode == 0, "changed-host attempt exits 0")
            check(env_path.read_text() == before_rotation,
                  "a changed host with a blank auth is not saved")

            # Keeping the existing values: two blank answers then EOF.
            kept = run([str(SETUP), "--no-rc"], env, stdin="\n\n")
            check(kept.returncode == 0, "interactive blank answers exit 0")
            check(env_path.read_text() == text, "blank answers keep the existing values")

            # Round-trip quoting: shell metacharacters survive write, parse and send.
            weird = "a'b$c`d e#f=g"
            env["HERALD_WEBHOOK_URL"] = listener.url
            env["HERALD_WEBHOOK_AUTH"] = "Bearer " + weird
            quoted = run([str(SETUP), "--non-interactive", "--no-rc", "--add", "HERALD"], env)
            check(quoted.returncode == 0, "second bot setup exits 0")
            parsed = module.load_config(env_path)
            check(parsed.get("HERALD_WEBHOOK_AUTH") == "Bearer " + weird,
                  "quoted value round-trips through the file")
            quoted_post = notify(env, env_path, "HERALD", "done", "quoted")
            check(quoted_post.returncode == 0, "quoted value posts")
            check(listener.requests[-1]["headers"].get("authorization") == "Bearer " + weird,
                  "quoted value is sent exactly")
            text = env_path.read_text()
            check("HERALD_WEBHOOK_URL=" in text and "HERALD_WEBHOOK_AUTH=" in text,
                  "second bot is stored")
            # Interactive entry for a later bot: blank/keep the ones before it.
            fresh = Path(tmp) / "fresh-home"
            fresh.mkdir()
            fresh_env_path = fresh / ".config" / "bot-webhooks" / "env"
            fresh_env = base_env(fresh, fresh_env_path)
            lines = ["", "http://127.0.0.1:9/herald", "Bearer " + other]
            typed = run([str(SETUP), "--no-rc", "--add", "JARVIS", "--add", "HERALD"], fresh_env,
                        stdin="\n".join(lines) + "\n")
            check(typed.returncode == 0, "interactive URL+auth entry exits 0")
            check("HERALD_WEBHOOK_AUTH='Bearer " + other + "'" in fresh_env_path.read_text(),
                  "interactive hidden value is stored normalized")
            check("JARVIS_WEBHOOK" not in fresh_env_path.read_text(),
                  "blank answers on a first run leave the earlier bots out")

            # rc block is replaced, never duplicated.
            rc = Path(tmp) / "zshrc"
            rc.write_text("export EDITOR=vi\n")
            rc_env = base_env(home, env_path)
            rc_env["SHELL"] = "/bin/zsh"
            rc_first = run([str(SETUP), "--non-interactive", "--rc", str(rc)], rc_env)
            check(rc_first.returncode == 0, "rc edit exits 0")
            first_rc = rc.read_text()
            check(first_rc.count("# BEGIN bot-webhooks") == 1, "rc gets one managed block")
            check("bot-webhooks/env" in first_rc and "$HOME/.local/bin" in first_rc,
                  "rc sources the env file and adds ~/.local/bin")
            rc_second = run([str(SETUP), "--non-interactive", "--rc", str(rc)], rc_env)
            check(rc_second.returncode == 0, "second rc edit exits 0")
            check(rc.read_text() == first_rc, "second rc edit is idempotent")
            check(rc.read_text().startswith("export EDITOR=vi\n"), "rc edit keeps the existing file")

            syntax = subprocess.run(["sh", "-n", str(rc)], capture_output=True, text=True)
            check(syntax.returncode == 0, "the rc block is valid sh")
            sourced = subprocess.run(
                ["sh", "-c", f'. "{rc}"; printf %s "$HERALD_WEBHOOK_AUTH"'],
                capture_output=True,
                text=True,
                env=rc_env,
                timeout=30,
            )
            check(sourced.returncode == 0 and sourced.stdout == "Bearer " + weird,
                  "the rc block exports the value to a child shell")

            setup_module = load_setup()
            rc_home = Path(tmp) / "rc-home"
            rc_home.mkdir()
            (rc_home / ".zprofile").write_text("")
            zsh_targets = setup_module.rc_targets(rc_home, "/bin/zsh")
            check(rc_home / ".zshrc" in zsh_targets and rc_home / ".zprofile" in zsh_targets,
                  "zsh targets .zshrc and an existing .zprofile")
            (rc_home / ".bash_profile").write_text("")
            (rc_home / ".profile").write_text("")
            bash_targets = setup_module.rc_targets(rc_home, "/bin/bash")
            check(rc_home / ".bashrc" in bash_targets and rc_home / ".bash_profile" in bash_targets,
                  "bash targets .bashrc and .bash_profile when it exists")
            check(rc_home / ".profile" not in bash_targets,
                  "bash does not add .profile when .bash_profile exists")

        # Advisor consult (2026-11-22): names come from the file and --add only, never the
        # environment, so an unrelated SLACK_WEBHOOK_URL is not swept into the secrets file.
        stray_path = Path(tmp) / "stray" / "env"
        stray_env = base_env(home, stray_path)
        stray_env["SLACK_WEBHOOK_URL"] = "https://hooks.example.test/slack"
        stray_env["SLACK_WEBHOOK_AUTH"] = secret
        stray = run([str(SETUP), "--non-interactive", "--no-rc"], stray_env)
        check(stray.returncode == 0 and not stray_path.exists(),
              "an unrelated *_WEBHOOK_* variable is not written without --add")
        badname = run([str(SETUP), "--non-interactive", "--no-rc", "--add", "x;y"], stray_env)
        check(badname.returncode == 2 and not stray_path.exists(), "--add refuses a name that is not A-Z, 0-9, _")
        nothing = run([str(SETUP), "--no-rc"], base_env(home, Path(tmp) / "nothing" / "env"), stdin="")
        check("--add" in nothing.stdout + nothing.stderr, "setup with no bots says to use --add")

        # A failing endpoint exits nonzero without printing the secret.
        with Listener(status=500) as broken:
            env["JARVIS_WEBHOOK_URL"] = broken.url
            env["JARVIS_WEBHOOK_AUTH"] = secret
            failed = run([str(SETUP), "--non-interactive", "--no-rc"], env)
            check(failed.returncode == 0, "setup accepts a URL it cannot know is broken")
            result = notify(env, env_path, "JARVIS", "done", "fail")
            check(result.returncode == 1, "a 500 response exits 1")
            check(secret not in result.stdout + result.stderr, "failure output has no secret")
            check("500" in result.stderr, "failure message names the HTTP status")

        # A redirect must not carry the Authorization header to a second host.
        with Listener() as target, Listener(status=302, location=target.url) as redirect:
            env["JARVIS_WEBHOOK_URL"] = redirect.url
            env["JARVIS_WEBHOOK_AUTH"] = secret
            run([str(SETUP), "--non-interactive", "--no-rc"], env)
            moved = notify(env, env_path, "JARVIS", "done", "redirect")
            check(moved.returncode == 1, "a redirect is refused")
            check(not target.requests, "a redirect receives no Authorization header")
            check(secret not in moved.stdout + moved.stderr, "redirect output has no secret")

        # A malformed URL is skipped by setup and fails cleanly at send time.
        bad_path = Path(tmp) / "bad" / "env"
        bad_env = base_env(home, bad_path)
        bad_env["JARVIS_WEBHOOK_URL"] = "http://host:notaport/hook"
        bad_env["JARVIS_WEBHOOK_AUTH"] = secret
        bad = run([str(SETUP), "--non-interactive", "--no-rc", "--add", "JARVIS"], bad_env)
        check(bad.returncode == 0, "a malformed URL does not crash setup")
        check(not bad_path.exists(), "a malformed URL is not written")

        bad_post_path = Path(tmp) / "badpost" / "env"
        bad_post_path.parent.mkdir()
        bad_post_path.write_text(
            f"export JARVIS_WEBHOOK_URL='http://host:notaport/hook'\n"
            f"export JARVIS_WEBHOOK_AUTH='Bearer {secret}'\n"
        )
        bad_post = notify(env, bad_post_path, "JARVIS", "done", "bad url")
        check(bad_post.returncode == 1, "a malformed URL fails without crashing")
        check(secret not in bad_post.stdout + bad_post.stderr
              and "notaport" not in bad_post.stdout + bad_post.stderr,
              "a malformed URL does not echo the URL or secret")

    # The standing rule lives in the loaded instructions, not only in a doc.
    rule = 'notify-bot <BOT> <status> "<one-line summary>" <thread-id>'
    # The rule moved from AGENTS.md to skills/finish-change (the person, 2026-11-23);
    # its trigger is in that skill's description, which every session loads.
    for rel in ("skills/finish-change/SKILL.md", "agents/build.md", "agents/implementor.md"):
        check(rule in (ROOT / rel).read_text(), f"{rel} has the standing notify-bot rule")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
