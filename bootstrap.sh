#!/bin/sh
# bootstrap.sh — cold start on a machine with nothing but a shell and curl/wget.
#
# Safe to PIPE. It never uses $0 (which is `sh` when piped) and never reads stdin
# (which is the script itself under `curl | sh`).
#
#   curl -fsSL <url> | sh
#   sh -c "$(curl -fsSL <url>)"
#
# The repo is PRIVATE, so fetching it needs credentials:
#   DOTFILES_TOKEN=<github token with repo scope>   or   an authenticated `gh`
#
# Environment:
#   DOTFILES_SLUG   owner/repo            (default scoizzle/dotfiles)
#   DOTFILES_DIR    clone destination     (default $HOME/dotfiles)
#   DOTFILES_BRANCH branch                (default main)
#   DOTFILES_TOKEN  token for a private clone
set -eu

# shellcheck disable=SC1007  # empty CDPATH= prefix is intentional
# shellcheck disable=SC2086  # package lists are split on purpose

REPO_SLUG="${DOTFILES_SLUG:-scoizzle/dotfiles}"
DEST="${DOTFILES_DIR:-$HOME/dotfiles}"
BRANCH="${DOTFILES_BRANCH:-main}"

DRY_RUN=0
RUN_SETUP=1

usage() {
    printf '%s\n' "usage: $0 [--dry-run] [--no-setup]"
    printf '%s\n' "  --dry-run   print what would happen, change nothing"
    printf '%s\n' "  --no-setup  stop after cloning; do not run setup.sh"
}

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-setup) RUN_SETUP=0 ;;
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
die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

run() {
    if [ "$DRY_RUN" -eq 1 ]; then say "would run: $*"; else "$@"; fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# sudo only when needed; containers often run as root with no sudo at all
as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# ---------------------------------------------------------------------------
step "preflight"

say "  repo    $REPO_SLUG"
say "  dest    $DEST"
say "  branch  $BRANCH"

have curl || have wget || die "need curl or wget to do anything"
say "  fetch   $(have curl && echo curl || echo wget)"

if [ -e "$DEST" ]; then
    if [ -d "$DEST/.git" ]; then
        say "  exists  $DEST already has a git checkout; leaving it alone"
        if [ "$RUN_SETUP" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
            step "setup"
            exec "$DEST/setup.sh"
        fi
        exit 0
    fi
    die "$DEST exists but is not a git checkout; move it or set DOTFILES_DIR"
fi

# ---------------------------------------------------------------------------
# git: genuinely absent on a minimal Ubuntu or Arch install
# ---------------------------------------------------------------------------
step "git"

if have git; then
    say "  ok      $(git --version)"
else
    say "  missing; installing"
    if have apt-get; then
        run as_root apt-get update -qq
        run as_root apt-get install -y git
    elif have pacman; then
        run as_root pacman -S --needed --noconfirm git
    elif have dnf; then
        run as_root dnf install -y git
    elif have yum; then
        run as_root yum install -y git
    elif have apk; then
        run as_root apk add --no-cache git
    elif have brew; then
        run brew install git
    else
        die "no supported package manager found; install git, then re-run with --no-setup"
    fi

    if [ "$DRY_RUN" -eq 0 ]; then
        have git || die "git still not on PATH after install"
    fi
fi

# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------
step "clone"

if [ "$DRY_RUN" -eq 1 ]; then
    say "would clone $REPO_SLUG into $DEST"
elif have gh && gh auth status >/dev/null 2>&1; then
    say "  using authenticated gh"
    gh repo clone "$REPO_SLUG" "$DEST" -- --branch "$BRANCH" --quiet

elif [ -n "${DOTFILES_TOKEN:-}" ] || [ -n "${GH_TOKEN:-}" ]; then
    token="${DOTFILES_TOKEN:-${GH_TOKEN:-}}"
    say "  using DOTFILES_TOKEN/GH_TOKEN"
    token_url="https://x-access-token:${token}@github.com/${REPO_SLUG}.git"
    git clone --branch "$BRANCH" --quiet "$token_url" "$DEST"
    # do not leave the token in .git/config
    git -C "$DEST" remote set-url origin "https://github.com/${REPO_SLUG}.git"

else
    say ""
    say "  This repo is private, so a bare machine cannot clone it anonymously."
    say "  Do one of these and re-run:"
    say "    DOTFILES_TOKEN=<token>   # github.com/settings/tokens, 'repo' scope"
    say "    gh auth login            # if the gh CLI is available"
    say ""
    say "  Or make the repo public and this needs nothing."
    exit 1
fi

if [ "$DRY_RUN" -eq 0 ]; then
    [ -d "$DEST/.git" ] || die "clone did not produce $DEST/.git"
    say "  ok      $DEST"
fi

# ---------------------------------------------------------------------------
step "setup"

if [ "$RUN_SETUP" -eq 0 ]; then
    say "  skipped (--no-setup); run: $DEST/setup.sh"
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    say "would run: $DEST/setup.sh"
    exit 0
fi

exec "$DEST/setup.sh"
