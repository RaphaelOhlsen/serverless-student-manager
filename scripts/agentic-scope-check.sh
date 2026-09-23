#!/usr/bin/env bash

set -uo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/agentic-common.sh
source "$script_directory/lib/agentic-common.sh"

export LC_ALL=C
export GIT_OPTIONAL_LOCKS=0

usage() {
  cat >&2 <<'EOF'
Usage: agentic-scope-check.sh --expected-branch <branch>
       --expected-head <sha> --base <sha>
       --allow-file <repo-relative-path> [--allow-file <path> ...]
       [--format text|json]
EOF
}

expected_branch=""
expected_head=""
base_expected=""
output_format="text"
format_seen="no"
declare -A allowed_paths=()

while (($# > 0)); do
  case "$1" in
    --expected-branch)
      if (($# < 2)) || [[ -n "$expected_branch" || -z "$2" ]]; then
        usage
        exit 2
      fi
      expected_branch="$2"
      shift 2
      ;;
    --expected-head)
      if (($# < 2)) || [[ -n "$expected_head" ]] || ! agentic_is_full_sha "$2"; then
        usage
        exit 2
      fi
      expected_head="${2,,}"
      shift 2
      ;;
    --base)
      if (($# < 2)) || [[ -n "$base_expected" ]] || ! agentic_is_full_sha "$2"; then
        usage
        exit 2
      fi
      base_expected="${2,,}"
      shift 2
      ;;
    --allow-file)
      if (($# < 2)); then
        usage
        exit 2
      fi
      if ! normalized_path="$(agentic_normalize_repo_path "$2")"; then
        usage
        exit 2
      fi
      allowed_paths["$normalized_path"]=1
      shift 2
      ;;
    --format)
      if (($# < 2)) || [[ "$format_seen" == "yes" ]] ||
        [[ "$2" != "text" && "$2" != "json" ]]; then
        usage
        exit 2
      fi
      output_format="$2"
      format_seen="yes"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$expected_branch" || -z "$expected_head" || -z "$base_expected" ]] ||
  ((${#allowed_paths[@]} == 0)); then
  usage
  exit 2
fi

AGENTIC_ERRORS=()
repository_root=""
repository_valid="no"
branch=""
head_sha=""
base_sha=""
base_is_ancestor="unknown"
committed_files=()
staged_files=()
unstaged_files=()
untracked_files=()
conflicted_files=()
changed_files=()
out_of_scope_files=()
unused_allowed_files=()
checkpoint_files=()
committed_diff_check="NOT_RUN"
staged_diff_check="NOT_RUN"
unstaged_diff_check="NOT_RUN"
untracked_diff_check="NOT_RUN"

if repository_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  if ! cd -- "$repository_root"; then
    agentic_add_error "repository_unavailable"
  elif agentic_repository_is_valid "$repository_root"; then
    repository_valid="yes"
  else
    agentic_add_error "invalid_repository"
  fi
else
  agentic_add_error "not_inside_git_repository"
fi

if [[ -n "$repository_root" ]]; then
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if ! head_sha="$(git rev-parse --verify HEAD 2>/dev/null)"; then
    agentic_add_error "head_unavailable"
    head_sha=""
  fi

  if [[ -z "$branch" ]]; then
    agentic_add_error "detached_head"
  elif [[ "$branch" != "$expected_branch" ]]; then
    agentic_add_error "expected_branch_mismatch"
  fi
  if [[ "${head_sha,,}" != "$expected_head" ]]; then
    agentic_add_error "expected_head_mismatch"
  fi

  if base_sha="$(git rev-parse --verify "${base_expected}^{commit}" 2>/dev/null)"; then
    if [[ "${base_sha,,}" != "$base_expected" ]]; then
      agentic_add_error "base_resolution_mismatch"
    elif [[ -n "$head_sha" ]]; then
      if git merge-base --is-ancestor "$base_sha" "$head_sha" 2>/dev/null; then
        base_is_ancestor="yes"
      else
        merge_base_status=$?
        base_is_ancestor="no"
        if ((merge_base_status > 1)); then
          agentic_add_error "base_ancestry_check_failed"
        else
          agentic_add_error "base_not_ancestor"
        fi
      fi
    fi
  else
    base_sha=""
    agentic_add_error "base_missing"
  fi

  if [[ -n "$base_sha" && -n "$head_sha" ]]; then
    if ! agentic_capture_nul_array committed_files \
      git diff --name-only --no-renames -z "$base_sha...$head_sha" --; then
      agentic_add_error "committed_files_check_failed"
    fi
  fi
  if ! agentic_capture_nul_array staged_files \
    git diff --cached --name-only --no-renames -z --; then
    agentic_add_error "staged_files_check_failed"
  fi
  if ! agentic_capture_nul_array unstaged_files \
    git diff --name-only --no-renames -z --; then
    agentic_add_error "unstaged_files_check_failed"
  fi
  if ! agentic_capture_nul_array untracked_files \
    git ls-files --others --exclude-standard -z; then
    agentic_add_error "untracked_files_check_failed"
  fi
  if ! agentic_capture_nul_array conflicted_files \
    git diff --name-only --diff-filter=U -z --; then
    agentic_add_error "conflicted_files_check_failed"
  fi

  if ((${#conflicted_files[@]} > 0)); then
    agentic_add_error "unmerged_paths"
  fi

  changed_files=(
    "${committed_files[@]}"
    "${staged_files[@]}"
    "${unstaged_files[@]}"
    "${untracked_files[@]}"
  )
  if ! agentic_sort_unique_array changed_files; then
    agentic_add_error "changed_files_sort_failed"
  fi

  for file in "${changed_files[@]}"; do
    if agentic_has_control_characters "$file"; then
      agentic_add_error "unsafe_changed_path"
    fi
    if agentic_is_checkpoint "$file"; then
      checkpoint_files+=("$file")
      if agentic_array_contains committed_files "$file" ||
        agentic_array_contains staged_files "$file" ||
        agentic_array_contains unstaged_files "$file"; then
        agentic_add_error "checkpoint_changed:$file"
      fi
      continue
    fi
    if [[ -z "${allowed_paths[$file]+present}" ]]; then
      out_of_scope_files+=("$file")
    fi
  done

  if ((${#out_of_scope_files[@]} > 0)); then
    agentic_add_error "out_of_scope_files"
  fi

  for file in "${!allowed_paths[@]}"; do
    found="no"
    for changed in "${changed_files[@]}"; do
      if [[ "$file" == "$changed" ]]; then
        found="yes"
        break
      fi
    done
    if [[ "$found" == "no" ]]; then
      unused_allowed_files+=("$file")
    fi
  done
  agentic_sort_unique_array out_of_scope_files || agentic_add_error "scope_sort_failed"
  agentic_sort_unique_array unused_allowed_files || agentic_add_error "allowlist_sort_failed"
  agentic_sort_unique_array checkpoint_files || agentic_add_error "checkpoint_sort_failed"

  agentic_validate_checkpoint_tracking || true

  if [[ -n "$base_sha" && -n "$head_sha" ]]; then
    if agentic_git_diff_check "$base_sha...$head_sha" --; then
      committed_diff_check="PASS"
    else
      check_status=$?
      committed_diff_check="FAIL"
      if ((check_status == 1)); then
        agentic_add_error "committed_diff_whitespace"
      else
        agentic_add_error "committed_diff_check_failed"
      fi
    fi
  fi

  if agentic_git_diff_check --cached --; then
    staged_diff_check="PASS"
  else
    check_status=$?
    staged_diff_check="FAIL"
    if ((check_status == 1)); then
      agentic_add_error "staged_diff_whitespace"
    else
      agentic_add_error "staged_diff_check_failed"
    fi
  fi

  if agentic_git_diff_check --; then
    unstaged_diff_check="PASS"
  else
    check_status=$?
    unstaged_diff_check="FAIL"
    if ((check_status == 1)); then
      agentic_add_error "unstaged_diff_whitespace"
    else
      agentic_add_error "unstaged_diff_check_failed"
    fi
  fi

  untracked_diff_check="PASS"
  for file in "${untracked_files[@]}"; do
    if agentic_is_checkpoint "$file"; then
      continue
    fi
    if agentic_untracked_diff_check "$file"; then
      continue
    else
      check_status=$?
    fi
    untracked_diff_check="FAIL"
    if ((check_status == 1)); then
      agentic_add_error "untracked_diff_whitespace:$file"
    else
      agentic_add_error "untracked_diff_check_failed:$file"
    fi
  done
fi

allowed_files=("${!allowed_paths[@]}")
agentic_sort_unique_array allowed_files || agentic_add_error "allowlist_output_sort_failed"

if ((${#AGENTIC_ERRORS[@]} == 0)); then
  result="PASS"
  exit_code=0
else
  result="FAIL"
  exit_code=1
fi

if [[ "$output_format" == "json" ]]; then
  printf '{'
  printf '"schemaVersion":%d,"tool":"agentic-scope-check",' "$AGENTIC_SCHEMA_VERSION"
  printf '"result":%s,' "$(agentic_json_quote "$result")"
  printf '"repositoryRoot":%s,' "$(agentic_json_nullable_string "$repository_root")"
  printf '"repositoryValid":%s,' "$(agentic_json_boolean "$repository_valid")"
  printf '"branch":%s,"head":%s,' \
    "$(agentic_json_nullable_string "$branch")" \
    "$(agentic_json_nullable_string "$head_sha")"
  printf '"expectedBranch":%s,"expectedHead":%s,' \
    "$(agentic_json_quote "$expected_branch")" \
    "$(agentic_json_quote "$expected_head")"
  printf '"base":{'
  printf '"expected":%s,"resolved":%s,"isAncestor":%s},' \
    "$(agentic_json_quote "$base_expected")" \
    "$(agentic_json_nullable_string "$base_sha")" \
    "$(agentic_json_quote "$base_is_ancestor")"
  printf '"allowlist":'
  agentic_json_string_array allowed_files
  printf ',"changes":{'
  printf '"committed":'
  agentic_json_string_array committed_files
  printf ',"staged":'
  agentic_json_string_array staged_files
  printf ',"unstaged":'
  agentic_json_string_array unstaged_files
  printf ',"untracked":'
  agentic_json_string_array untracked_files
  printf ',"all":'
  agentic_json_string_array changed_files
  printf '},"outOfScope":'
  agentic_json_string_array out_of_scope_files
  printf ',"unusedAllowed":'
  agentic_json_string_array unused_allowed_files
  printf ',"checkpoints":'
  agentic_json_string_array checkpoint_files
  printf ',"diffCheck":{'
  printf '"committed":%s,"staged":%s,"unstaged":%s,"untracked":%s},' \
    "$(agentic_json_quote "$committed_diff_check")" \
    "$(agentic_json_quote "$staged_diff_check")" \
    "$(agentic_json_quote "$unstaged_diff_check")" \
    "$(agentic_json_quote "$untracked_diff_check")"
  printf '"errors":'
  agentic_json_string_array AGENTIC_ERRORS
  printf '}\n'
else
  printf 'REPOSITORY_ROOT='
  agentic_text_value "$repository_root"
  printf '\nREPOSITORY_VALID=%s\n' "$repository_valid"
  printf 'BRANCH=%s\nHEAD=%s\n' "${branch:-DETACHED}" "${head_sha:-MISSING}"
  printf 'EXPECTED_BRANCH=%s\nEXPECTED_HEAD=%s\n' "$expected_branch" "$expected_head"
  printf 'BASE_EXPECTED=%s\nBASE_RESOLVED=%s\nBASE_IS_ANCESTOR=%s\n' \
    "$base_expected" "${base_sha:-MISSING}" "$base_is_ancestor"
  printf 'ALLOWLIST_COUNT=%d\n' "${#allowed_files[@]}"
  for file in "${allowed_files[@]}"; do
    printf 'ALLOWED_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  printf 'COMMITTED_FILES_COUNT=%d\nSTAGED_FILES_COUNT=%d\n' \
    "${#committed_files[@]}" "${#staged_files[@]}"
  printf 'UNSTAGED_FILES_COUNT=%d\nUNTRACKED_FILES_COUNT=%d\n' \
    "${#unstaged_files[@]}" "${#untracked_files[@]}"
  for file in "${changed_files[@]}"; do
    printf 'CHANGED_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${out_of_scope_files[@]}"; do
    printf 'OUT_OF_SCOPE_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${unused_allowed_files[@]}"; do
    printf 'UNUSED_ALLOWED_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${checkpoint_files[@]}"; do
    printf 'CHECKPOINT_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  printf 'COMMITTED_DIFF_CHECK=%s\nSTAGED_DIFF_CHECK=%s\n' \
    "$committed_diff_check" "$staged_diff_check"
  printf 'UNSTAGED_DIFF_CHECK=%s\nUNTRACKED_DIFF_CHECK=%s\n' \
    "$unstaged_diff_check" "$untracked_diff_check"
  for error in "${AGENTIC_ERRORS[@]}"; do
    printf 'ERROR='
    agentic_text_value "$error"
    printf '\n'
  done
  printf 'SCOPE_RESULT=%s\n' "$result"
fi

exit "$exit_code"
