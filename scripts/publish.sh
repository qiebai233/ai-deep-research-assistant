#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DeepResearch one-command publisher (macOS / Linux / Git Bash).
#
# What it does:
#   1. verifies git is installed and the working tree is clean;
#   2. replaces the 'qiebai233' placeholder with --owner
#      (README, docs, .github, pyproject.toml, docs URL / User-Agent in src/);
#   3. git init (if needed) + git add -A + git commit;
#   4. gh repo create <owner>/deepresearch --public --source . --push
#      (prints manual commands instead when gh is missing);
#   5. creates the release tag, pushes the branch and the tag;
#   6. prints the Actions and Release URLs.
#
# The GitHub Release itself is created by .github/workflows/release.yml when the
# tag is pushed — this script never calls the Releases API.
#
# Usage:
#   ./scripts/publish.sh --owner qiebai233 --dry-run
#   ./scripts/publish.sh --owner qiebai233
#   ./scripts/publish.sh --owner qiebai233 --tag v0.2.0
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPO_NAME="deepresearch"
PLACEHOLDER="qiebai233"
DEFAULT_TAG="v0.1.0"

OWNER=""
TAG="$DEFAULT_TAG"
DRY_RUN=false
SKIP_REPLACE=false
SKIP_CREATE=false

# Root-level files and directory trees scanned for the placeholder.
REPLACE_TARGETS=(
  "README.md"
  "README_EN.md"
  "CHANGELOG.md"
  "CONTRIBUTING.md"
  "SECURITY.md"
  "CODE_OF_CONDUCT.md"
  "pyproject.toml"
  "docs"
  ".github"
  "examples"
  "src/deepresearch/cli.py"
  "src/deepresearch/http.py"
)

# docs/publishing.md intentionally keeps the placeholder in its examples.
REPLACE_EXCLUDED="docs/publishing.md"

c_reset=""; c_cyan=""; c_green=""; c_yellow=""; c_red=""; c_dim=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  c_reset=$'\033[0m'; c_cyan=$'\033[36m'; c_green=$'\033[32m'
  c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_dim=$'\033[90m'
fi

head()   { printf '\n%s== %s%s\n' "$c_cyan" "$1" "$c_reset"; }
ok()     { printf '   %s[ok]%s %s\n' "$c_green" "$c_reset" "$1"; }
note()   { printf '   %s%s%s\n' "$c_dim" "$1" "$c_reset"; }
warn()   { printf '   %s[warn]%s %s\n' "$c_yellow" "$c_reset" "$1"; }
fail()   { printf '   %s[fail]%s %s\n' "$c_red" "$c_reset" "$1" >&2; }

usage() {
  cat <<'EOF'
DeepResearch publisher

Usage:
  ./scripts/publish.sh --owner <github-user> [options]

Options:
  -o, --owner <name>   GitHub user or organisation (required)
      --tag <tag>      Release tag to create (default: v0.1.0)
      --dry-run        Show what would change/run; write nothing, run no git writes
      --skip-replace   Do not replace the qiebai233 placeholder
      --skip-create    Do not run `gh repo create` (repository already exists)
  -h, --help           Show this help

Requires: git. Optional: gh (GitHub CLI) for automatic repository creation.
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    -o|--owner)      OWNER="${2:-}"; shift 2 ;;
    --owner=*)       OWNER="${1#*=}"; shift ;;
    --tag)           TAG="${2:-}"; shift 2 ;;
    --tag=*)         TAG="${1#*=}"; shift ;;
    --dry-run)       DRY_RUN=true; shift ;;
    --skip-replace)  SKIP_REPLACE=true; shift ;;
    --skip-create)   SKIP_CREATE=true; shift ;;
    -h|--help)       usage; exit 0 ;;
    *) fail "unknown option: $1"; usage; exit 1 ;;
  esac
done

if [ -z "$OWNER" ]; then
  fail "--owner is required"; usage; exit 1
fi
case "$OWNER" in
  *[!A-Za-z0-9-]*) fail "invalid GitHub owner name: $OWNER"; exit 1 ;;
esac
case "$TAG" in
  v[0-9]*.[0-9]*.[0-9]*) : ;;
  *) fail "invalid tag (expected vMAJOR.MINOR.PATCH): $TAG"; exit 1 ;;
esac

cd "$REPO_ROOT"

# Run a mutating command unless in dry-run mode.
run() {
  if [ "$DRY_RUN" = true ]; then
    note "dry-run: $*"
    return 0
  fi
  "$@"
}

show_manual_commands() {
  local branch="$1"
  head "manual steps (no gh or no origin remote)"
  cat <<EOF
   cd "$REPO_ROOT"
   git remote add origin https://github.com/$OWNER/$REPO_NAME.git
   git push -u origin $branch
   git tag -a $TAG -m "DeepResearch $TAG"
   git push origin $TAG

   Then open: https://github.com/$OWNER/$REPO_NAME/actions
   The Release workflow creates the GitHub Release from tag $TAG.
EOF
}

# ---------------------------------------------------------------------------
# 1. Environment checks
# ---------------------------------------------------------------------------
head "DeepResearch publisher (owner: $OWNER, tag: $TAG)"

if [ ! -f "pyproject.toml" ]; then
  fail "pyproject.toml not found in $REPO_ROOT — run this script from the repository."
  exit 1
fi
ok "repository root: $REPO_ROOT"

if ! command -v git >/dev/null 2>&1; then
  fail "git is not installed or not on PATH."
  show_manual_commands "main"
  note "No changes were made. Install Git and re-run this script."
  exit 0
fi
ok "git: $(git --version)"

IS_REPO=false
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IS_REPO=true
fi

BRANCH="main"
if [ "$IS_REPO" = true ]; then
  ok "git repository detected"
  if [ -n "$(git status --porcelain)" ]; then
    fail "working tree is not clean. Commit or stash your changes first:"
    git status --porcelain | sed 's/^/     /' >&2
    note "Nothing was changed."
    exit 1
  fi
  current="$(git branch --show-current 2>/dev/null || true)"
  if [ -n "$current" ]; then BRANCH="$current"; fi
  ok "working tree clean (branch: $BRANCH)"
else
  warn "no git repository here yet — will run: git init -b main"
  BRANCH="main"
fi

# ---------------------------------------------------------------------------
# 2. Placeholder replacement
# ---------------------------------------------------------------------------
list_placeholder_files() {
  local target
  for target in "${REPLACE_TARGETS[@]}"; do
    if [ -f "$target" ]; then
      if grep -q "$PLACEHOLDER" "$target" 2>/dev/null; then
        printf '%s\n' "$target"
      fi
    elif [ -d "$target" ]; then
      find "$target" -type f \
        \( -name '*.md' -o -name '*.markdown' -o -name '*.yml' -o -name '*.yaml' \
           -o -name '*.toml' -o -name '*.py' -o -name '*.json' -o -name '*.txt' \) \
        -print 2>/dev/null | while IFS= read -r file; do
          if grep -q "$PLACEHOLDER" "$file" 2>/dev/null; then
            printf '%s\n' "$file"
          fi
        done
    fi
  done | grep -v "^${REPLACE_EXCLUDED}$" | sort -u || true
}

head "replace placeholder"
FILES=()
while IFS= read -r file; do
  [ -n "$file" ] && FILES+=("$file")
done < <(list_placeholder_files)

if [ "$SKIP_REPLACE" = true ]; then
  note "skipped (--skip-replace)"
elif [ "${#FILES[@]}" -eq 0 ]; then
  note "placeholder not found (already replaced?) — nothing to do"
elif [ "$DRY_RUN" = true ]; then
  note "dry-run: would replace '$PLACEHOLDER' -> '$OWNER' in ${#FILES[@]} file(s):"
  for file in "${FILES[@]}"; do note "  - $file"; done
else
  for file in "${FILES[@]}"; do
    sed -i.bak "s|${PLACEHOLDER}|${OWNER}|g" "$file"
    rm -f "$file.bak"
  done
  ok "replaced '$PLACEHOLDER' -> '$OWNER' in ${#FILES[@]} file(s)"
fi

if [ "$DRY_RUN" = true ]; then
  head "dry-run plan (nothing written)"
  note "git init -b main   # only if not a repository yet"
  note "git add -A"
  note "git commit -m \"release: $TAG\""
  note "gh repo create $OWNER/$REPO_NAME --public --source . --push"
  note "git tag -a $TAG -m \"DeepResearch $TAG\""
  note "git push -u origin $BRANCH"
  note "git push origin $TAG"
  head "dry-run finished"
  note "No files were modified and no commands were executed."
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. git init + commit
# ---------------------------------------------------------------------------
head "commit"
if [ "$IS_REPO" = false ]; then
  run git init -b main
  ok "initialised repository (main)"
fi
run git add -A
if [ -n "$(git status --porcelain)" ]; then
  run git commit -m "release: $TAG"
  ok "committed: release: $TAG"
else
  note "nothing to commit — skipping"
fi

# ---------------------------------------------------------------------------
# 4. create the GitHub repository if needed
# ---------------------------------------------------------------------------
head "GitHub repository"
HAS_ORIGIN=false
if git remote | grep -qx "origin"; then HAS_ORIGIN=true; fi
REMOTE_READY=false

if [ "$HAS_ORIGIN" = true ]; then
  ok 'remote "origin" already configured — skipping gh repo create'
  REMOTE_READY=true
elif [ "$SKIP_CREATE" = true ]; then
  note "skipped (--skip-create) but no origin remote exists"
elif ! command -v gh >/dev/null 2>&1; then
  warn "GitHub CLI (gh) not found"
else
  if run gh repo create "$OWNER/$REPO_NAME" --public --source . --push; then
    REMOTE_READY=true
    ok "created and pushed https://github.com/$OWNER/$REPO_NAME"
  else
    warn "gh repo create failed — falling back to manual commands below"
  fi
fi

if [ "$REMOTE_READY" = false ]; then
  show_manual_commands "$BRANCH"
  head "done (manual steps required)"
  note "Placeholder replacement and the local commit are complete; push manually as shown above."
  exit 0
fi

# ---------------------------------------------------------------------------
# 5. push branch + tag
# ---------------------------------------------------------------------------
head "push and tag"
run git push -u origin "$BRANCH"
ok "pushed branch $BRANCH"

if git tag -l "$TAG" | grep -qx "$TAG"; then
  warn "tag $TAG already exists locally — reusing it"
else
  run git tag -a "$TAG" -m "DeepResearch $TAG"
  ok "created tag $TAG"
fi
run git push origin "$TAG"
ok "pushed tag $TAG"

# ---------------------------------------------------------------------------
# 6. next steps
# ---------------------------------------------------------------------------
head "done"
printf '\n'
printf '   Repository : %s\n' "https://github.com/$OWNER/$REPO_NAME"
printf '   Actions    : %s\n' "https://github.com/$OWNER/$REPO_NAME/actions"
printf '   Release    : %s\n' "https://github.com/$OWNER/$REPO_NAME/releases/tag/$TAG"
printf '\n'
note "The Release workflow builds the sdist/wheel for tag $TAG and creates the GitHub Release."
note "If the Actions tab shows nothing, enable workflows under Settings -> Actions -> General."
