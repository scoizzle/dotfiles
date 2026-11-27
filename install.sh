#!/bin/sh
# Link this repo's agent config into Claude Code and opencode.
#
#   ./install.sh          link (a file or link already there is moved to a backup)
#   ./install.sh --check  show what would change; exit 1 if anything would,
#                         4 if a real directory sits at a destination
#
# AGENTS.md     -> ~/.config/opencode/AGENTS.md and ~/.claude/CLAUDE.md
# opencode.json -> ~/.config/opencode/opencode.json
# claude-settings.json -> ~/.claude/settings.json
# skills/<n>    -> ~/.config/opencode/skills/<n> and ~/.claude/skills/<n>
# ~/.claude is used only when it exists (Claude Code is installed).
# A real directory at a destination is never moved; install refuses (exit 4).
set -eu

check=0
case "${1:-}" in
  "") ;;
  --check) check=1 ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

repo=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
# Links point at the checkout that runs this, so only the canonical one may
# apply (2026-11-20: a feature worktree's install held for 32 hours).
canonical=$(CDPATH='' cd -- "${DOTFILES_DIR:-$HOME/dotfiles}" 2>/dev/null && pwd -P || echo "")
if [ "$check" -eq 0 ] && [ "$repo" != "$canonical" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "refusing: $repo is not ${DOTFILES_DIR:-$HOME/dotfiles}; run that checkout's install.sh, or FORCE=1" >&2
  exit 3
fi
oc="$HOME/.config/opencode"
refused=0
refuse() { # a real folder at $1 is never moved out of the way
  if [ -d "$1" ] && [ ! -L "$1" ]; then
    if [ "$check" -eq 1 ]; then
      echo "would refuse: $1 is a real directory" >&2
    else
      echo "refusing: $1 is a real directory; move it yourself, then rerun" >&2
    fi
    refused=1
  fi
}
refuse "$oc/AGENTS.md"
refuse "$oc/opencode.json"
for d in "$repo"/skills/*/; do
  n=$(basename -- "$d")
  [ -f "$d/SKILL.md" ] || continue
  # a linked skills folder is replaced wholesale by realdir; skip its contents
  if [ ! -L "$oc/skills" ]; then refuse "$oc/skills/$n"; fi
  if [ -d "$HOME/.claude" ] && [ ! -L "$HOME/.claude/skills" ]; then
    refuse "$HOME/.claude/skills/$n"
  fi
done
if [ -d "$HOME/.claude" ]; then refuse "$HOME/.claude/CLAUDE.md"; refuse "$HOME/.claude/settings.json"; fi
[ "$refused" -eq 0 ] || exit 4

backup="$HOME/.config/dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
drift=0

save() { # move whatever is at $1 (file or link) into the backup
  if [ -d "$1" ] && [ ! -L "$1" ]; then # backstop; the preflight above should catch it first
    echo "refusing: $1 is a real directory; move it yourself, then rerun" >&2
    exit 4
  fi
  mkdir -p "$backup$(dirname -- "${1#"$HOME"}")"
  mv -- "$1" "$backup${1#"$HOME"}"
  echo "saved  $1 -> $backup${1#"$HOME"}"
}

realdir() { # make $1 a real folder; a link there (e.g. a whole skills/ link) is saved
  if [ -L "$1" ]; then
    drift=1
    if [ "$check" -eq 1 ]; then echo "would replace the link $1 with a folder"; return; fi
    save "$1"
  fi
  [ "$check" -eq 1 ] || mkdir -p "$1"
}

link() { # link <repo path> <destination>
  src="$repo/$1" dst=$2
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ] && [ ! -L "$(dirname -- "$dst")" ]; then
    return
  fi
  drift=1
  if [ "$check" -eq 1 ]; then echo "would link $dst -> $src"; return; fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then save "$dst"; fi
  ln -s "$src" "$dst"
  echo "linked $dst"
}

prune() { # remove links in folder $1 that point into this repo at something gone
  [ -d "$1" ] || return 0
  for l in "$1"/*; do
    [ -L "$l" ] || continue
    case "$(readlink "$l")" in "$repo"/*) ;; *) continue ;; esac
    [ -e "$l" ] && continue
    drift=1
    if [ "$check" -eq 1 ]; then echo "would remove the dangling link $l"; else rm -- "$l"; echo "removed $l"; fi
  done
}

skills_into() { # skills_into <skills folder>
  realdir "$1"
  for d in "$repo"/skills/*/; do
    n=$(basename -- "$d")
    [ -f "$d/SKILL.md" ] || continue
    link "skills/$n" "$1/$n"
  done
  prune "$1"
}

realdir "$oc"
link AGENTS.md "$oc/AGENTS.md"
link opencode.json "$oc/opencode.json"
skills_into "$oc/skills"

if [ -d "$HOME/.claude" ]; then
  link AGENTS.md "$HOME/.claude/CLAUDE.md"
  link claude-settings.json "$HOME/.claude/settings.json"
  skills_into "$HOME/.claude/skills"
fi

if [ "$check" -eq 1 ] && [ "$drift" -eq 1 ]; then
  exit 1
fi
echo "ok"
