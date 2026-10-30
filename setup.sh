#!/bin/sh
# setup.sh — stage 0. Gets a .NET toolchain onto a bare machine, then hands to install.cs.
#
#   ./setup.sh            report what is missing and stop before changing anything
#   ./setup.sh --install  install missing system packages (needs sudo), then continue
#   ./setup.sh --dry-run  print the plan, change nothing
#
# Why this is not C#: it bootstraps the SDK that runs C#. See docs/plan-csharp-native-migration.md.
# shellcheck disable=SC1007  # empty CDPATH= prefix is intentional: ignore CDPATH
# shellcheck disable=SC2086  # $MISSING_PKGS is a space-separated package list, split on purpose

set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
DOTNETUP_DIR="$HOME/.dotnetup"
DOTNETUP="$DOTNETUP_DIR/dotnetup"

DRY_RUN=0
DO_INSTALL=0

usage() {
    printf '%s\n' "usage: $0 [--install] [--dry-run]"
    printf '%s\n' "  --install  run the package commands for missing prerequisites (sudo)"
    printf '%s\n' "  --dry-run  print what would happen, change nothing"
}

for arg in "$@"; do
    case "$arg" in
        --install) DO_INSTALL=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }

# run CMD... — respects --dry-run
run() {
    if [ "$DRY_RUN" -eq 1 ]; then say "would run: $*"; else "$@"; fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# platform
# ---------------------------------------------------------------------------
case "$(uname -s)" in
    Darwin) OS=macos ;;
    Linux)  OS=linux ;;
    *)
        printf 'unsupported OS: %s\n' "$(uname -s)" >&2
        printf 'this repo targets macOS and Linux; on Windows use WSL2.\n' >&2
        exit 2
        ;;
esac

if [ "$OS" = linux ]; then
    if [ -f /etc/arch-release ]; then DISTRO=arch
    elif [ -f /etc/debian_version ]; then DISTRO=debian
    else DISTRO=other
    fi
else
    DISTRO=none
fi

step "platform"
say "  os      $OS ($DISTRO)"
say "  arch    $(uname -m)"
say "  repo    $REPO"

# ---------------------------------------------------------------------------
# prerequisites
#
# clang and zlib headers are only needed for Native AOT. install.cs degrades to
# interpreted shims without them, so a missing toolchain is a note, not a failure.
# ---------------------------------------------------------------------------
step "prerequisites"

MISSING_PKGS=""
note_toolchain=0

need() {  # need <command> <package>
    if have "$1"; then
        say "  ok      $1"
    else
        say "  MISSING $1"
        MISSING_PKGS="$MISSING_PKGS $2"
    fi
}

if have curl; then
    say "  ok      curl"
else
    say "  MISSING curl"
    MISSING_PKGS="$MISSING_PKGS curl"
fi
need git git
if have python3; then
    say "  ok      python3"
else
    say "  MISSING python3"
    case "$DISTRO" in
        arch) MISSING_PKGS="$MISSING_PKGS python" ;;
        *)    MISSING_PKGS="$MISSING_PKGS python3" ;;
    esac
fi

# .NET on Linux needs the system ICU unless it runs in invariant mode, and dotnetup
# installs an SDK without any system dependencies. Arch's `base` has no ICU; some
# Debian images don't either (this is why the Ubuntu VM needed libicu-dev by hand).
if [ "$OS" = linux ]; then
    has_icu=0
    for f in /usr/lib*/libicuuc.so* /usr/lib/*/libicuuc.so*; do
        [ -e "$f" ] && has_icu=1 && break
    done
    if [ "$has_icu" -eq 1 ]; then
        say "  ok      icu"
    else
        say "  MISSING icu (.NET needs it on Linux)"
        case "$DISTRO" in
            arch)   MISSING_PKGS="$MISSING_PKGS icu" ;;
            debian) MISSING_PKGS="$MISSING_PKGS libicu-dev" ;;
        esac
    fi
fi

if have clang; then
    say "  ok      clang (native AOT available)"
else
    say "  note    clang absent — tools will run interpreted (still works, ~200 ms)"
    note_toolchain=1
    case "$DISTRO" in
        # binutils is only needed to link AOT output; --needed makes it a no-op otherwise.
        arch)   MISSING_PKGS="$MISSING_PKGS clang zlib binutils" ;;
        debian) MISSING_PKGS="$MISSING_PKGS clang zlib1g-dev" ;;
    esac
fi

install_cmds() {
    case "$DISTRO" in
        arch)   printf '  sudo pacman -S --needed%s\n' "$MISSING_PKGS" ;;
        debian) printf '  sudo apt-get install -y%s\n' "$MISSING_PKGS" ;;
        macos)  printf '  xcode-select --install    # provides git and clang; opens a GUI dialog\n' ;;
        *)      printf '  install manually:%s\n' "$MISSING_PKGS" ;;
    esac
}

if [ -n "$MISSING_PKGS" ]; then
    printf '\nmissing packages:\n'
    install_cmds
    if [ "$DO_INSTALL" -eq 1 ] && [ "$DISTRO" != macos ] && [ "$DISTRO" != other ]; then
        case "$DISTRO" in
            arch)   run sudo pacman -S --needed $MISSING_PKGS ;;
            debian) run sudo apt-get install -y $MISSING_PKGS ;;
        esac
    elif [ "$DISTRO" = macos ]; then
        say "  (xcode-select is interactive; run it yourself, then re-run $0)"
    else
        say "  (re-run with --install to execute the command above)"
    fi
fi

# ---------------------------------------------------------------------------
# dotnetup
# ---------------------------------------------------------------------------
step "dotnetup"

if [ -x "$DOTNETUP" ] || have dotnetup; then
    say "  ok      already installed"
else
    say "  installing to $DOTNETUP_DIR"
    if [ "$DRY_RUN" -eq 1 ]; then
        say "would run: curl -fsSL https://aka.ms/dotnetup/get-dotnetup.sh | bash"
    else
        curl -fsSL https://aka.ms/dotnetup/get-dotnetup.sh | bash
    fi
fi

PATH="$DOTNETUP_DIR:$PATH"
export PATH

if [ ! -x "$DOTNETUP" ] && ! have dotnetup; then
    if [ "$DRY_RUN" -eq 1 ]; then
        say "  (dry run) would install dotnetup, then the SDK, then run ./install.cs"
        exit 0
    fi
    say "  dotnetup unavailable after install; stopping before the SDK step"
    say "  install it, then re-run: ./setup.sh"
    exit 1
fi

# Persist the toolchain for future shells. Without this, `./install.cs` fails in a new
# terminal with "env: 'dotnet': No such file or directory" (measured on Ubuntu 26.04).
# Idempotent; revert with `dotnetup env clear`.
if [ "$DRY_RUN" -eq 1 ]; then
    say "  would run: dotnetup env set shell   # persists PATH/DOTNET_ROOT"
else
    if dotnetup env set shell >/dev/null 2>&1; then
        say "  ok      wrote PATH/DOTNET_ROOT to your shell profile (revert: dotnetup env clear)"
    else
        say "  note    could not persist PATH; add manually: export PATH=\"\$HOME/.dotnetup:\$PATH\""
    fi
fi

step "SDK"

if [ ! -f "$REPO/global.json" ]; then
    say "  no global.json in repo; dotnetup will fall back to 'latest'"
fi

cd "$REPO"
run dotnetup sdk install --no-progress

# env script emits DOTNET_ROOT/PATH for THIS process. It ends with `rehash`, which is a
# zsh builtin, so a plain sh eval would trip `set -e`; hence the guards.
if [ "$DRY_RUN" -eq 0 ]; then
    set +e
    eval "$(dotnetup env script 2>/dev/null)"
    set -e
    say "  dotnet  $(command -v dotnet || echo 'not resolved')"
    dotnet --version 2>/dev/null | sed 's/^/  sdk     /'
fi

# ---------------------------------------------------------------------------
# pinned global tools
#
# Dependabot cannot see global .NET tools, so tools.json pins them and the scheduled
# tools workflow compares that pin to NuGet. Install the pin, not "latest", or the
# repo has no reproducible toolchain.
# ---------------------------------------------------------------------------
step "tools"

ROS_PIN=$(sed -n 's/.*"roslynk"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO/tools.json" 2>/dev/null | head -1)

if [ -z "$ROS_PIN" ]; then
    say "  no roslynk pin in tools.json; skipping"
elif [ "$DRY_RUN" -eq 1 ]; then
    say "would install roslynk $ROS_PIN from the tools.json pin"
else
    if dotnet tool list -g 2>/dev/null | awk 'NR > 2 { print $1 }' | grep -qx roslynk; then
        run dotnet tool update -g roslynk --version "$ROS_PIN"
    else
        run dotnet tool install -g roslynk --version "$ROS_PIN"
    fi
fi

# The Roslynk NuGet package ships no SKILL.md (only appsettings.json), so the skill
# cannot come from the tool. Without this a wiped machine silently loses it.
if [ -n "$ROS_PIN" ]; then
    SKILL_DIR="$HOME/.agents/skills/roslynk"
    if [ -f "$SKILL_DIR/SKILL.md" ] && [ "$(cat "$SKILL_DIR/.pin" 2>/dev/null)" = "$ROS_PIN" ]; then
        say "  ok      roslynk skill $ROS_PIN"
    elif [ "$DRY_RUN" -eq 1 ]; then
        say "would fetch the roslynk skill at tag $ROS_PIN"
    else
        tmp=$(mktemp -d)
        if curl -fsSL "https://github.com/mrpmorris/Roslynk/archive/refs/tags/${ROS_PIN}.tar.gz" |
            tar -xz -C "$tmp" 2>/dev/null; then
            src=$(find "$tmp" -maxdepth 3 -type d -path "*/skills/roslynk" | head -1)
            if [ -n "$src" ]; then
                mkdir -p "$SKILL_DIR"
                cp -R "$src/." "$SKILL_DIR/"
                printf '%s\n' "$ROS_PIN" > "$SKILL_DIR/.pin"
                say "  ok      roslynk skill $ROS_PIN"
            else
                say "  note    no skills/roslynk in the tag archive"
            fi
        else
            say "  note    could not download the roslynk skill at $ROS_PIN"
        fi
        rm -rf "$tmp"
    fi
fi

# ---------------------------------------------------------------------------
# aspire
#
# Deliberately the self-contained bundle, not `dotnet tool Aspire.Cli`: the bundle
# carries the dashboard and templates, and `aspire agent init` regenerates the agent
# skills into ~/.agents/skills, so those never need to live in this repo.
# Not added to tools.json because it is not a dotnet tool in this install mode.
# ---------------------------------------------------------------------------
step "aspire"

if [ "$DRY_RUN" -eq 1 ]; then
    say "would install the Aspire bundle if missing, then: aspire agent init"
else
    if have aspire; then
        say "  ok      $(command -v aspire)"
    elif [ -x "$HOME/.aspire/bin/aspire" ]; then
        PATH="$HOME/.aspire/bin:$PATH"
        export PATH
        say "  ok      $HOME/.aspire/bin/aspire"
    else
        say "  installing to $HOME/.aspire"
        curl -sSL https://aspire.dev/install.sh | bash
        PATH="$HOME/.aspire/bin:$PATH"
        export PATH
    fi

    if have aspire; then
        say "  version $(aspire --version 2>/dev/null | head -1)"
        # `standard` is ~/.agents/skills, which opencode already discovers. Deliberately
        # NOT passing `opencode`: that location is ~/.config/opencode/skills, a symlink
        # into this repo, so the CLI would write generated skills into version control.
        # `--workspace-root "$HOME"` is required: without it the CLI treats the cwd (this
        # repo) as the workspace and writes .agents/, .claude/ and .github/skills/ into
        # the working tree. Verified on Ubuntu 26.04.
        (cd "$HOME" && aspire agent init --non-interactive --skills all \
            --skill-locations standard,claudecode,github --workspace-root "$HOME") 2>&1 | tail -3 ||
            say "  note    aspire agent init failed; run it manually"
    else
        say "  note    aspire still not on PATH; skipping agent init"
    fi
fi

# ---------------------------------------------------------------------------
# hand off
# ---------------------------------------------------------------------------
step "install"

if [ "$note_toolchain" -eq 1 ]; then
    say "  note: no clang, so Native AOT is unavailable; install.cs will degrade to shims"
fi

run ./install.cs --doctor || true
if [ "$DRY_RUN" -eq 0 ]; then
    ./install.cs
fi

step "done"
say "  dotnetup PATH/DOTNET_ROOT persisted for new shells (revert: dotnetup env clear)"
say "  this current shell still needs: export PATH=\"\$HOME/.dotnetup:\$PATH\""
say "  then: ./install.cs --check"
