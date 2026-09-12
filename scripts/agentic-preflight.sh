#!/usr/bin/env bash

set -u

mode="implementation"
if [[ "${1:-}" == "--read-only" ]]; then
  mode="read-only"
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--read-only]" >&2
  exit 2
fi

if ! repository_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "PREFLIGHT_RESULT=FAIL"
  echo "ERROR=not_inside_git_repository"
  exit 1
fi

cd "$repository_root" || exit 1

failed=0
if [[ "$(basename "$repository_root")" != "serverless-student-manager" ]] ||
  [[ ! -f AGENTS.md ]] ||
  ! grep -q '^# AGENTS.md — Serverless Student Manager$' AGENTS.md; then
  repository_valid="no"
  failed=1
else
  repository_valid="yes"
fi

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
head_sha="$(git rev-parse HEAD)"
origin_main="$(git rev-parse --verify refs/remotes/origin/main 2>/dev/null || true)"

echo "REPOSITORY_ROOT=$repository_root"
echo "REPOSITORY_VALID=$repository_valid"
echo "MODE=$mode"
echo "BRANCH=${branch:-DETACHED}"
echo "HEAD=$head_sha"
echo "ORIGIN_MAIN=${origin_main:-MISSING}"

if [[ -z "$branch" ]]; then
  echo "ERROR=detached_head"
  failed=1
elif [[ "$mode" == "implementation" && "$branch" == "main" ]]; then
  echo "ERROR=implementation_on_main"
  failed=1
fi

if [[ -n "$origin_main" ]]; then
  read -r behind ahead < <(git rev-list --left-right --count origin/main...HEAD)
  echo "BEHIND_ORIGIN_MAIN=$behind"
  echo "AHEAD_OF_ORIGIN_MAIN=$ahead"
else
  echo "BEHIND_ORIGIN_MAIN=UNKNOWN"
  echo "AHEAD_OF_ORIGIN_MAIN=UNKNOWN"
  echo "ERROR=origin_main_missing"
  failed=1
fi

mapfile -t tracked_changes < <(git status --short --untracked-files=no)
echo "TRACKED_CHANGES_COUNT=${#tracked_changes[@]}"
for change in "${tracked_changes[@]}"; do
  echo "TRACKED_CHANGE=$change"
done

mapfile -d '' -t untracked_files < <(git ls-files --others --exclude-standard -z)
checkpoint_count=0
other_untracked_count=0
echo "UNTRACKED_FILES_COUNT=${#untracked_files[@]}"
for file in "${untracked_files[@]}"; do
  case "$file" in
    prompt_inicio_dia.txt|"prompt_inicio_dia copy.txt")
      classification="checkpoint"
      checkpoint_count=$((checkpoint_count + 1))
      ;;
    *)
      classification="other"
      other_untracked_count=$((other_untracked_count + 1))
      ;;
  esac
  echo "UNTRACKED_FILE=$file CLASSIFICATION=$classification"
done
echo "CHECKPOINT_FILES_COUNT=$checkpoint_count"
echo "OTHER_UNTRACKED_FILES_COUNT=$other_untracked_count"

if ((failed)); then
  echo "PREFLIGHT_RESULT=FAIL"
  exit 1
fi

echo "PREFLIGHT_RESULT=PASS"
