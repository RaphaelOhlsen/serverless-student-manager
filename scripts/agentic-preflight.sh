#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR

set -uo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/agentic-common.sh
source "$script_directory/lib/agentic-common.sh"

export LC_ALL=C
export GIT_OPTIONAL_LOCKS=0

usage() {
  cat >&2 <<'EOF'
Usage: agentic-preflight.sh [--read-only]
       [--expected-branch <branch>] [--expected-head <sha>]
       [--base <ref-or-sha>] [--strict-untracked]
       [--format text|json]
EOF
}

mode="implementation"
expected_branch=""
expected_head=""
base_ref="origin/main"
base_explicit="no"
strict_untracked="no"
output_format="text"
mode_seen="no"
expected_branch_seen="no"
expected_head_seen="no"
base_seen="no"
strict_untracked_seen="no"
format_seen="no"

while (($# > 0)); do
  case "$1" in
    --read-only)
      if [[ "$mode_seen" == "yes" ]]; then
        usage
        exit 2
      fi
      mode="read-only"
      mode_seen="yes"
      shift
      ;;
    --expected-branch)
      if (($# < 2)) || [[ "$expected_branch_seen" == "yes" || -z "$2" ]]; then
        usage
        exit 2
      fi
      expected_branch="$2"
      expected_branch_seen="yes"
      shift 2
      ;;
    --expected-head)
      if (($# < 2)) || [[ "$expected_head_seen" == "yes" ]] ||
        ! agentic_is_full_sha "$2"; then
        usage
        exit 2
      fi
      expected_head="${2,,}"
      expected_head_seen="yes"
      shift 2
      ;;
    --base)
      if (($# < 2)) || [[ "$base_seen" == "yes" || -z "$2" ]]; then
        usage
        exit 2
      fi
      base_ref="$2"
      base_explicit="yes"
      base_seen="yes"
      shift 2
      ;;
    --strict-untracked)
      if [[ "$strict_untracked_seen" == "yes" ]]; then
        usage
        exit 2
      fi
      strict_untracked="yes"
      strict_untracked_seen="yes"
      shift
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

AGENTIC_ERRORS=()
tracked_changes=()
untracked_files=()
untracked_classifications=()
repository_root=""
repository_valid="no"
branch=""
head_sha=""
origin_main=""
base_sha=""
base_is_ancestor="unknown"
behind="unknown"
ahead="unknown"
origin_behind="unknown"
origin_ahead="unknown"
checkpoint_count=0
other_untracked_count=0

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
  origin_main="$(git rev-parse --verify 'refs/remotes/origin/main^{commit}' 2>/dev/null || true)"

  if [[ -z "$branch" ]]; then
    agentic_add_error "detached_head"
  elif [[ "$mode" == "implementation" && "$branch" == "main" ]]; then
    agentic_add_error "implementation_on_main"
  fi

  if [[ -n "$expected_branch" && "$branch" != "$expected_branch" ]]; then
    agentic_add_error "expected_branch_mismatch"
  fi
  if [[ -n "$expected_head" && "${head_sha,,}" != "$expected_head" ]]; then
    agentic_add_error "expected_head_mismatch"
  fi

  if base_sha="$(git rev-parse --verify "${base_ref}^{commit}" 2>/dev/null)"; then
    if [[ -n "$head_sha" ]]; then
      if git merge-base --is-ancestor "$base_sha" "$head_sha" 2>/dev/null; then
        base_is_ancestor="yes"
      else
        merge_base_status=$?
        base_is_ancestor="no"
        if ((merge_base_status > 1)); then
          agentic_add_error "base_ancestry_check_failed"
        elif [[ "$base_explicit" == "yes" ]]; then
          agentic_add_error "base_not_ancestor"
        fi
      fi

      counts="$(git rev-list --left-right --count "$base_sha...$head_sha" 2>/dev/null || true)"
      if [[ "$counts" =~ ^([0-9]+)[[:space:]]+([0-9]+)$ ]]; then
        behind="${BASH_REMATCH[1]}"
        ahead="${BASH_REMATCH[2]}"
      else
        agentic_add_error "base_divergence_check_failed"
      fi
    fi
  else
    base_sha=""
    agentic_add_error "base_missing"
  fi

  if [[ -z "$origin_main" ]]; then
    agentic_add_error "origin_main_missing"
  elif [[ -n "$head_sha" ]]; then
    origin_counts="$(git rev-list --left-right --count "$origin_main...$head_sha" 2>/dev/null || true)"
    if [[ "$origin_counts" =~ ^([0-9]+)[[:space:]]+([0-9]+)$ ]]; then
      origin_behind="${BASH_REMATCH[1]}"
      origin_ahead="${BASH_REMATCH[2]}"
    else
      agentic_add_error "origin_main_divergence_check_failed"
    fi
  fi

  if ! agentic_capture_lines_array tracked_changes \
    git -c core.quotePath=true status --short --untracked-files=no; then
    agentic_add_error "tracked_status_failed"
  fi
  if ! agentic_capture_nul_array untracked_files \
    git ls-files --others --exclude-standard -z; then
    agentic_add_error "untracked_status_failed"
  fi

  for file in "${untracked_files[@]}"; do
    if agentic_is_checkpoint "$file"; then
      untracked_classifications+=("checkpoint")
      checkpoint_count=$((checkpoint_count + 1))
    else
      untracked_classifications+=("other")
      other_untracked_count=$((other_untracked_count + 1))
    fi
  done

  if [[ "$strict_untracked" == "yes" ]] && ((other_untracked_count > 0)); then
    agentic_add_error "strict_untracked_violation"
  fi
  agentic_validate_checkpoint_tracking || true
fi

if ((${#AGENTIC_ERRORS[@]} == 0)); then
  result="PASS"
  exit_code=0
else
  result="FAIL"
  exit_code=1
fi

if [[ "$output_format" == "json" ]]; then
  printf '{'
  printf '"schemaVersion":%d,' "$AGENTIC_SCHEMA_VERSION"
  printf '"tool":"agentic-preflight",'
  printf '"result":%s,' "$(agentic_json_quote "$result")"
  printf '"repositoryRoot":%s,' "$(agentic_json_nullable_string "$repository_root")"
  printf '"repositoryValid":%s,' "$(agentic_json_boolean "$repository_valid")"
  printf '"mode":%s,' "$(agentic_json_quote "$mode")"
  printf '"branch":%s,' "$(agentic_json_nullable_string "$branch")"
  printf '"head":%s,' "$(agentic_json_nullable_string "$head_sha")"
  printf '"originMain":%s,' "$(agentic_json_nullable_string "$origin_main")"
  printf '"originMainBehind":%s,' \
    "$([[ "$origin_behind" == "unknown" ]] && printf 'null' || printf '%s' "$origin_behind")"
  printf '"originMainAhead":%s,' \
    "$([[ "$origin_ahead" == "unknown" ]] && printf 'null' || printf '%s' "$origin_ahead")"
  printf '"base":{'
  printf '"ref":%s,' "$(agentic_json_quote "$base_ref")"
  printf '"sha":%s,' "$(agentic_json_nullable_string "$base_sha")"
  printf '"explicit":%s,' "$(agentic_json_boolean "$base_explicit")"
  printf '"isAncestor":%s,' "$(agentic_json_quote "$base_is_ancestor")"
  printf '"behind":%s,' "$([[ "$behind" == "unknown" ]] && printf 'null' || printf '%s' "$behind")"
  printf '"ahead":%s},' "$([[ "$ahead" == "unknown" ]] && printf 'null' || printf '%s' "$ahead")"
  printf '"expected":{'
  printf '"branch":%s,' "$(agentic_json_nullable_string "$expected_branch")"
  printf '"head":%s},' "$(agentic_json_nullable_string "$expected_head")"
  printf '"strictUntracked":%s,' "$(agentic_json_boolean "$strict_untracked")"
  printf '"changes":{'
  printf '"tracked":'
  agentic_json_string_array tracked_changes
  printf ',"untracked":['
  separator=""
  for index in "${!untracked_files[@]}"; do
    printf '%s{' "$separator"
    printf '"path":%s,' "$(agentic_json_quote "${untracked_files[index]}")"
    printf '"classification":%s}' \
      "$(agentic_json_quote "${untracked_classifications[index]}")"
    separator=','
  done
  printf '],"checkpointCount":%d,"otherUntrackedCount":%d},' \
    "$checkpoint_count" "$other_untracked_count"
  printf '"errors":'
  agentic_json_string_array AGENTIC_ERRORS
  printf '}\n'
else
  printf 'REPOSITORY_ROOT='
  agentic_text_value "$repository_root"
  printf '\nREPOSITORY_VALID=%s\n' "$repository_valid"
  printf 'MODE=%s\n' "$mode"
  printf 'BRANCH=%s\n' "${branch:-DETACHED}"
  printf 'HEAD=%s\n' "${head_sha:-MISSING}"
  printf 'ORIGIN_MAIN=%s\n' "${origin_main:-MISSING}"
  printf 'BASE_REF='
  agentic_text_value "$base_ref"
  printf '\nBASE_SHA=%s\n' "${base_sha:-MISSING}"
  printf 'BASE_IS_ANCESTOR=%s\n' "$base_is_ancestor"
  printf 'BEHIND_BASE=%s\n' "${behind^^}"
  printf 'AHEAD_OF_BASE=%s\n' "${ahead^^}"
  printf 'BEHIND_ORIGIN_MAIN=%s\n' "${origin_behind^^}"
  printf 'AHEAD_OF_ORIGIN_MAIN=%s\n' "${origin_ahead^^}"
  printf 'TRACKED_CHANGES_COUNT=%d\n' "${#tracked_changes[@]}"
  for change in "${tracked_changes[@]}"; do
    printf 'TRACKED_CHANGE='
    agentic_text_value "$change"
    printf '\n'
  done
  printf 'UNTRACKED_FILES_COUNT=%d\n' "${#untracked_files[@]}"
  for index in "${!untracked_files[@]}"; do
    printf 'UNTRACKED_FILE='
    agentic_text_value "${untracked_files[index]}"
    printf ' CLASSIFICATION=%s\n' "${untracked_classifications[index]}"
  done
  printf 'CHECKPOINT_FILES_COUNT=%d\n' "$checkpoint_count"
  printf 'OTHER_UNTRACKED_FILES_COUNT=%d\n' "$other_untracked_count"
  for error in "${AGENTIC_ERRORS[@]}"; do
    printf 'ERROR='
    agentic_text_value "$error"
    printf '\n'
  done
  printf 'PREFLIGHT_RESULT=%s\n' "$result"
fi

exit "$exit_code"
