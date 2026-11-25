#!/bin/sh
# Link this repo's agent config into the tools that don't read ~/.agents.
# Grok reads ~/.agents/skills itself and ~/.claude/CLAUDE.md, so it needs none.
#
#   ./install.sh          link (anything already there is moved to a backup)
#   ./install.sh --check  show what would change; exit 1 if anything would
#
# AGENTS.md     -> ~/.config/opencode/AGENTS.md and ~/.claude/CLAUDE.md
# opencode.json -> ~/.config/opencode/opencode.json
# skills/<n>    -> ~/.config/opencode/skills/<n> and ~/.claude/skills/<n>
# ~/.claude is used only when it exists (Claude Code is installed).
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
canonical=$(CDPATH='' cd -- "${DOTFILES_DIR:-$HOME/.agents}" 2>/dev/null && pwd -P || echo "")
if [ "$check" -eq 0 ] && [ "$repo" != "$canonical" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "refusing: $repo is not ${DOTFILES_DIR:-$HOME/.agents}; run that checkout's install.sh, or FORCE=1" >&2
  exit 3
fi
backup="$HOME/.config/dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
drift=0

save() { # move whatever is at $1 (file, folder or link) into the backup
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

oc="$HOME/.config/opencode"
realdir "$oc"
link AGENTS.md "$oc/AGENTS.md"
link opencode.json "$oc/opencode.json"
skills_into "$oc/skills"

if [ -d "$HOME/.claude" ]; then
  link AGENTS.md "$HOME/.claude/CLAUDE.md"
  skills_into "$HOME/.claude/skills"
fi

if [ "$check" -eq 1 ] && [ "$drift" -eq 1 ]; then
  exit 1
fi
echo "ok"
