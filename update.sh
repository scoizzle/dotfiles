#!/bin/sh
# update.sh — bring installed tools up to date, without changing declared versions.
#
#   ./update.sh             tools that have their own updater
#   ./update.sh --brew      also install/refresh the declared Homebrew packages
#   ./update.sh --dry-run    print the plan, run nothing
#
# Two declarations are deliberately NEVER rewritten here:
#
#   global.json  is a FLOOR, not a target. `dotnetup update` runs WITHOUT
#                --update-global-json, because raising the floor breaks any machine
#                whose system SDK is older. Dependabot made exactly that mistake.
#
#   tools.json   pins are EXACT. roslynk is updated *to the pin*, never to latest.
#                Bumping a pin is a reviewed change, proposed by tools.yml.
#
# Run this from a plain terminal, not from inside opencode or T3: it replaces the
# binaries those processes are running.
# shellcheck disable=SC1007  # empty CDPATH= prefix is intentional: ignore CDPATH

set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

DRY_RUN=0
BREW=0
fail=0

usage() {
    printf '%s\n' "usage: $0 [--brew] [--dry-run]"
    printf '%s\n' "  --brew     also run brew update + brew bundle for declared packages"
    printf '%s\n' "  --dry-run  print what would run, change nothing"
}

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --brew) BREW=1 ;;
        -h | --help) usage; exit 0 ;;
        *)
            printf 'unknown argument: %s\n' "$arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        say "would run: $*"
        return 0
    fi
    say "\$ $*"
    "$@" || {
        say "  FAILED"
        fail=$((fail + 1))
    }
}

# dotnetup installs here; it is not on PATH until setup.sh persists it.
PATH="$HOME/.dotnetup:$PATH"
export PATH

# ---------------------------------------------------------------------------
step "dotnetup"

if have dotnetup; then
    run dotnetup self update
    # NO --update-global-json: see the header.
    run dotnetup update
else
    say "  dotnetup not found; run ./setup.sh first"
    fail=$((fail + 1))
fi

# ---------------------------------------------------------------------------
step "dotnet global tools"

PIN=$(sed -n 's/.*"roslynk"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO/tools.json" 2>/dev/null | head -1)

if [ -z "$PIN" ]; then
    say "  no roslynk pin in tools.json; skipped"
elif ! have dotnet; then
    say "  dotnet not on PATH; skipped"
else
    installed=$(dotnet tool list -g 2>/dev/null | awk '$1 == "roslynk" { print $2 }' || true)
    if [ "$installed" = "$PIN" ]; then
        say "  ok      roslynk $PIN (at pin)"
    else
        run dotnet tool update -g roslynk --version "$PIN"
    fi
fi

# ---------------------------------------------------------------------------
step "aspire"

if have aspire; then
    run aspire update --self -y
else
    say "  aspire not installed; skipped"
fi

# ---------------------------------------------------------------------------
step "opencode"

if have opencode; then
    run opencode upgrade
else
    say "  opencode not installed; skipped"
fi

# ---------------------------------------------------------------------------
step "t3"

if have t3; then
    run t3 update
else
    say "  t3 not installed; skipped"
fi

# ---------------------------------------------------------------------------
step "claude"

if have claude; then
    run claude update
else
    say "  claude not installed; skipped (needed only for the Claude subscription)"
fi

# ---------------------------------------------------------------------------
if [ "$BREW" -eq 1 ]; then
    step "homebrew"

    if have brew; then
        run brew update
        # Scoped to the Brewfile on purpose: `brew upgrade` with no argument would
        # touch every formula on the machine, not only what this repo declares.
        run brew bundle --file="$REPO/Brewfile"
    else
        say "  brew not installed; skipped"
    fi
else
    say ""
    say "  (skipping homebrew; pass --brew to refresh declared packages)"
fi

# ---------------------------------------------------------------------------
step "rebuild"

run "$REPO/install.cs"

# ---------------------------------------------------------------------------
say ""
if [ "$fail" -ne 0 ]; then
    printf '%s step(s) failed\n' "$fail" >&2
    exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    say "dry run: nothing changed"
else
    say "up to date"
fi
