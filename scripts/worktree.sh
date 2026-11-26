#!/usr/bin/env bash
# Create an isolated git worktree for an agent task under .worktree/<name>.
#
#   scripts/worktree.sh <name> [base-ref]   create .worktree/<name> on branch agent/<name>
#   scripts/worktree.sh <name> --from-working-tree
#                                           same, then copy the main checkout's uncommitted
#                                           state (modified, deleted, untracked) into it
#   scripts/worktree.sh --remove <name> [--force]
#                                           remove the worktree (branch is kept); --force
#                                           discards its uncommitted changes
#
# Each worktree gets its own .venv via `uv sync --locked` (hardlinked from the
# uv cache, so it is fast and nearly free on disk). The torch build follows
# PDF2EPUB_TORCH (cu132 or cpu; default: cu132 if nvidia-smi works, else cpu).
# Without uv, the main checkout's .venv is symlinked instead.
# Git-ignored local data (books/, bench/out) is symlinked from the main
# checkout; it is shared, so treat it as read-only.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
# Always operate from the main checkout, even when called inside a worktree.
root="$(git -C "$root" worktree list --porcelain | awk 'NR==1 {print $2}')"
cd "$root"

# Git-ignored local resources shared from the main checkout.
SHARED=(books bench/out)

usage() {
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

[[ $# -ge 1 ]] || usage

if [[ "$1" == "--remove" ]]; then
    [[ $# -eq 2 || ( $# -eq 3 && "$3" == "--force" ) ]] || usage
    force=()
    [[ "${3:-}" == "--force" ]] && force=(--force)
    # Drop links into the main checkout first; git sees them as untracked files.
    find ".worktree/$2" -type l -lname "$root/*" -delete
    if ! git worktree remove "${force[@]}" ".worktree/$2"; then
        echo "Not removed. Review or commit its changes, or pass --force to discard them." >&2
        exit 1
    fi
    echo "Removed .worktree/$2 (branch agent/$2 kept; delete it with: git branch -d agent/$2)"
    exit 0
fi

name="$1"
base="${2:-HEAD}"
copy_working_tree=false
if [[ "$base" == "--from-working-tree" ]]; then
    copy_working_tree=true
    base=HEAD
fi
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid name: $name" >&2; exit 1; }
path=".worktree/$name"
branch="agent/$name"

if ! $copy_working_tree && [[ -n "$(git status --porcelain --untracked-files=no)" && "$base" == "HEAD" ]]; then
    echo "Warning: the main checkout has uncommitted changes; they are NOT in the new worktree." >&2
fi

git worktree add -b "$branch" "$path" "$base"

if $copy_working_tree; then
    # Tracked and untracked (non-ignored) files as they are on disk now...
    while IFS= read -r -d '' f; do
        [[ -e "$f" || -L "$f" ]] && printf '%s\0' "$f"
    done < <(git ls-files -z --cached --others --exclude-standard -- ':!:.worktree') \
        | tar --null -T - -cf - | tar -xf - -C "$path"
    # ...and tracked files deleted in the main checkout.
    git ls-files -z --deleted -- ':!:.worktree' | (cd "$path" && xargs -0 -r rm -f --)
    # Git does not track directories, so drop the ones the deletions emptied.
    find "$path" -mindepth 1 -type d -empty -delete
    echo "Copied the main checkout's uncommitted state into $path (not committed)."
fi

# Link $1 (in the main checkout) at $2. If $2 is already a real directory
# (e.g. books/ holding a tracked .gitkeep), link each missing entry inside it.
link_shared() {
    local src="$1" dst="$2" child
    if [[ ! -e "$dst" && ! -L "$dst" ]]; then
        mkdir -p "$(dirname "$dst")"
        ln -s "$src" "$dst"
    elif [[ -d "$dst" && ! -L "$dst" && -d "$src" ]]; then
        for child in "$src"/* "$src"/.[!.]*; do
            if [[ -e "$child" ]]; then link_shared "$child" "$dst/$(basename "$child")"; fi
        done
    fi
}

for shared in "${SHARED[@]}"; do
    if [[ -e "$root/$shared" ]]; then link_shared "$root/$shared" "$path/$shared"; fi
done

if command -v uv >/dev/null && [[ -f "$path/uv.lock" ]]; then
    torch="${PDF2EPUB_TORCH:-$(nvidia-smi >/dev/null 2>&1 && echo cu132 || echo cpu)}"
    echo "Creating $path/.venv with uv (torch: $torch)..."
    (cd "$path" && uv sync --locked --extra "$torch")
elif [[ -e "$root/.venv" ]]; then
    echo "uv or uv.lock not found; sharing the main checkout's .venv (do not install into it)." >&2
    ln -s "$root/.venv" "$path/.venv"
fi

echo "Worktree ready: $root/$path (branch $branch)"
