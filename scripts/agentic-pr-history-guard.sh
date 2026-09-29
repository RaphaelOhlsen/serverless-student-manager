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
Usage: agentic-pr-history-guard.sh --base <ref-or-sha>
       [--head <ref-or-sha>] [--format text|json]
EOF
}

base_ref=""
head_ref="HEAD"
output_format="text"
head_seen="no"
format_seen="no"

while (($# > 0)); do
  case "$1" in
    --base)
      if (($# < 2)) || [[ -n "$base_ref" || -z "$2" ]]; then
        usage
        exit 2
      fi
      base_ref="$2"
      shift 2
      ;;
    --head)
      if (($# < 2)) || [[ "$head_seen" == "yes" || -z "$2" ]]; then
        usage
        exit 2
      fi
      head_ref="$2"
      head_seen="yes"
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

if [[ -z "$base_ref" ]]; then
  usage
  exit 2
fi

AGENTIC_ERRORS=()
repository_root=""
base_sha=""
head_sha=""
merge_base=""
behind="unknown"
ahead="unknown"
direct_files=()
three_dot_files=()
direct_only_files=()
three_dot_only_files=()
file_sets_equal="unknown"
reason="INCONCLUSIVE_EVIDENCE"
recommended_action="VERIFY_REFS_AND_RETRY"

if repository_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  if ! cd -- "$repository_root"; then
    agentic_add_error "repository_unavailable"
  elif ! agentic_repository_is_valid "$repository_root"; then
    agentic_add_error "invalid_repository"
  fi
else
  agentic_add_error "not_inside_git_repository"
fi

if [[ -n "$repository_root" ]]; then
  if ! base_sha="$(git rev-parse --verify "${base_ref}^{commit}" 2>/dev/null)"; then
    base_sha=""
    agentic_add_error "base_missing"
  fi
  if ! head_sha="$(git rev-parse --verify "${head_ref}^{commit}" 2>/dev/null)"; then
    head_sha=""
    agentic_add_error "head_missing"
  fi

  if [[ -n "$base_sha" && -n "$head_sha" ]]; then
    if ! merge_base="$(git merge-base "$base_sha" "$head_sha" 2>/dev/null)"; then
      merge_base=""
      agentic_add_error "merge_base_unavailable"
    fi

    counts="$(git rev-list --left-right --count "$base_sha...$head_sha" 2>/dev/null || true)"
    if [[ "$counts" =~ ^([0-9]+)[[:space:]]+([0-9]+)$ ]]; then
      behind="${BASH_REMATCH[1]}"
      ahead="${BASH_REMATCH[2]}"
    else
      agentic_add_error "divergence_check_failed"
    fi

    if ! agentic_capture_nul_array direct_files \
      git diff --name-only --no-renames -z "$base_sha" "$head_sha" --; then
      agentic_add_error "direct_diff_failed"
    fi
    if ! agentic_capture_nul_array three_dot_files \
      git diff --name-only --no-renames -z "$base_sha...$head_sha" --; then
      agentic_add_error "three_dot_diff_failed"
    fi

    agentic_sort_unique_array direct_files || agentic_add_error "direct_sort_failed"
    agentic_sort_unique_array three_dot_files || agentic_add_error "three_dot_sort_failed"

    for file in "${direct_files[@]}"; do
      if ! agentic_array_contains three_dot_files "$file"; then
        direct_only_files+=("$file")
      fi
    done
    for file in "${three_dot_files[@]}"; do
      if ! agentic_array_contains direct_files "$file"; then
        three_dot_only_files+=("$file")
      fi
    done

    if ((${#direct_only_files[@]} == 0 && ${#three_dot_only_files[@]} == 0)); then
      file_sets_equal="yes"
      if ((${#direct_files[@]} == 0)); then
        reason="NO_CHANGES"
        recommended_action="NO_PR_REQUIRED"
      else
        reason="SCOPES_EQUAL"
        recommended_action="PROCEED_WITH_REVIEW"
      fi
    else
      file_sets_equal="no"
      if [[ "$behind" != "unknown" && "$ahead" != "unknown" ]] &&
        ((behind > 0 && ahead > 0)) &&
        ((${#direct_only_files[@]} == 0 && ${#three_dot_only_files[@]} > 0)); then
        reason="SQUASH_HISTORY_DIVERGENCE"
        recommended_action="CREATE_FRESH_BRANCH_FROM_BASE"
      else
        reason="PR_SCOPE_DIVERGENCE"
        recommended_action="REVIEW_BRANCH_HISTORY_AND_SCOPE"
      fi
    fi
  fi
fi

if ((${#AGENTIC_ERRORS[@]} > 0)); then
  result="INCONCLUSIVE"
  exit_code=2
elif [[ "$file_sets_equal" == "no" ]]; then
  result="FAIL"
  exit_code=1
else
  result="PASS"
  exit_code=0
fi

if [[ "$file_sets_equal" == "unknown" ]]; then
  file_sets_equal_json="null"
else
  file_sets_equal_json="$(agentic_json_boolean "$file_sets_equal")"
fi

if [[ "$output_format" == "json" ]]; then
  printf '{'
  printf '"schemaVersion":%d,"tool":"agentic-pr-history-guard",' "$AGENTIC_SCHEMA_VERSION"
  printf '"result":%s,' "$(agentic_json_quote "$result")"
  printf '"base":{"ref":%s,"sha":%s},' \
    "$(agentic_json_quote "$base_ref")" \
    "$(agentic_json_nullable_string "$base_sha")"
  printf '"head":{"ref":%s,"sha":%s},' \
    "$(agentic_json_quote "$head_ref")" \
    "$(agentic_json_nullable_string "$head_sha")"
  printf '"mergeBase":%s,' "$(agentic_json_nullable_string "$merge_base")"
  printf '"behind":%s,"ahead":%s,' \
    "$([[ "$behind" == "unknown" ]] && printf 'null' || printf '%s' "$behind")" \
    "$([[ "$ahead" == "unknown" ]] && printf 'null' || printf '%s' "$ahead")"
  printf '"directFiles":'
  agentic_json_string_array direct_files
  printf ',"threeDotFiles":'
  agentic_json_string_array three_dot_files
  printf ',"directOnlyFiles":'
  agentic_json_string_array direct_only_files
  printf ',"threeDotOnlyFiles":'
  agentic_json_string_array three_dot_only_files
  printf ',"fileSetsEqual":%s,' "$file_sets_equal_json"
  printf '"reason":%s,"recommendedAction":%s,' \
    "$(agentic_json_quote "$reason")" \
    "$(agentic_json_quote "$recommended_action")"
  printf '"authorizationGranted":false,"errors":'
  agentic_json_string_array AGENTIC_ERRORS
  printf '}\n'
else
  printf 'BASE_REF=%s\n' "$(agentic_text_value "$base_ref")"
  printf 'BASE_SHA=%s\n' "$(agentic_text_value "$base_sha")"
  printf 'HEAD_REF=%s\n' "$(agentic_text_value "$head_ref")"
  printf 'HEAD_SHA=%s\n' "$(agentic_text_value "$head_sha")"
  printf 'MERGE_BASE=%s\n' "$(agentic_text_value "$merge_base")"
  printf 'BEHIND=%s\nAHEAD=%s\n' "$behind" "$ahead"
  printf 'DIRECT_DIFF_FILE_COUNT=%d\n' "${#direct_files[@]}"
  for file in "${direct_files[@]}"; do
    printf 'DIRECT_DIFF_FILE=%s\n' "$(agentic_text_value "$file")"
  done
  printf 'THREE_DOT_DIFF_FILE_COUNT=%d\n' "${#three_dot_files[@]}"
  for file in "${three_dot_files[@]}"; do
    printf 'THREE_DOT_DIFF_FILE=%s\n' "$(agentic_text_value "$file")"
  done
  printf 'FILE_SETS_EQUAL=%s\n' "${file_sets_equal^^}"
  for file in "${direct_only_files[@]}"; do
    printf 'DIRECT_ONLY_FILE=%s\n' "$(agentic_text_value "$file")"
  done
  for file in "${three_dot_only_files[@]}"; do
    printf 'THREE_DOT_ONLY_FILE=%s\n' "$(agentic_text_value "$file")"
  done
  printf 'REASON=%s\n' "$reason"
  printf 'RECOMMENDED_ACTION=%s\n' "$recommended_action"
  printf 'AUTHORIZATION_GRANTED=no\n'
  for error in "${AGENTIC_ERRORS[@]}"; do
    printf 'ERROR=%s\n' "$(agentic_text_value "$error")"
  done
  printf 'PR_HISTORY_GUARD=%s\n' "$result"
fi

exit "$exit_code"
