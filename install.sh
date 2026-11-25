#!/bin/sh
# Link this repo's agent config into Claude Code and opencode.
#
#   ./install.sh          link (anything already there is moved to a backup)
#   ./install.sh --check  show what would change; exit 1 if anything would
#
# AGENTS.md  -> ~/.config/opencode/AGENTS.md and ~/.claude/CLAUDE.md
# opencode.json -> ~/.config/opencode/opencode.json
# skills/<n> -> ~/.config/opencode/skills/<n> and ~/.claude/skills/<n>
# ~/.claude is used only when it exists (Claude Code is installed).
set -eu

repo=$(cd "$(dirname "$0")" && pwd -P)
check=0
[ "${1:-}" = "--check" ] && check=1
# Links point at the checkout that runs this, so only the canonical one may
# apply (2026-11-20: a feature worktree's install held for 32 hours).
canonical=$(cd "${DOTFILES_DIR:-$HOME/dotfiles}" 2>/dev/null && pwd -P || echo "")
if [ "$check" -eq 0 ] && [ "$repo" != "$canonical" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "refusing: $repo is not ${DOTFILES_DIR:-$HOME/dotfiles}; run that checkout's install.sh, or FORCE=1" >&2
  exit 3
fi
backup="$HOME/.config/dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
drift=0

link() { # link <repo path> <destination>
  src="$repo/$1" dst=$2
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    return
  fi
  drift=1
  if [ "$check" -eq 1 ]; then
    echo "would link $dst -> $src"
    return
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    mkdir -p "$backup$(dirname "${dst#"$HOME"}")"
    mv "$dst" "$backup${dst#"$HOME"}"
    echo "saved  $dst -> $backup${dst#"$HOME"}"
  fi
  ln -s "$src" "$dst"
  echo "linked $dst"
}

oc="$HOME/.config/opencode"
link AGENTS.md "$oc/AGENTS.md"
link opencode.json "$oc/opencode.json"
for d in "$repo"/skills/*/; do
  n=$(basename "$d")
  [ -f "$d/SKILL.md" ] || continue
  link "skills/$n" "$oc/skills/$n"
done

if [ -d "$HOME/.claude" ]; then
  link AGENTS.md "$HOME/.claude/CLAUDE.md"
  for d in "$repo"/skills/*/; do
    n=$(basename "$d")
    [ -f "$d/SKILL.md" ] || continue
    link "skills/$n" "$HOME/.claude/skills/$n"
  done
fi

if [ "$check" -eq 1 ] && [ "$drift" -eq 1 ]; then
  exit 1
fi
echo "ok"
