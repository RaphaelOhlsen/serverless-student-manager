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
Usage: agentic-staging-check.sh --expected-branch <branch>
       --expected-head <sha>
       --allow-file <repo-relative-path> [--allow-file <path> ...]
       [--expected-diff-sha256 <sha256>] [--format text|json]
EOF
}

expected_branch=""
expected_head=""
expected_diff_sha256=""
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
    --expected-diff-sha256)
      if (($# < 2)) || [[ -n "$expected_diff_sha256" ]] ||
        ! agentic_is_sha256 "$2"; then
        usage
        exit 2
      fi
      expected_diff_sha256="${2,,}"
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

if [[ -z "$expected_branch" || -z "$expected_head" ]] ||
  ((${#allowed_paths[@]} == 0)); then
  usage
  exit 2
fi

AGENTIC_ERRORS=()
repository_root=""
repository_valid="no"
branch=""
head_sha=""
index_sha256_before=""
index_sha256_after=""
staged_diff_sha256=""
staged_diff_check="NOT_RUN"
obvious_secret_scan="NOT_RUN"
staged_files=()
out_of_scope_files=()
checkpoint_files=()
binary_files=()
artifact_rules=()
artifact_files=()
secret_rules=()
secret_files=()

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

  index_path="$(git rev-parse --git-path index 2>/dev/null || true)"
  if [[ -z "$index_path" || ! -f "$index_path" ]] ||
    ! index_sha256_before="$(agentic_sha256_file "$index_path")"; then
    agentic_add_error "index_snapshot_unavailable"
    index_sha256_before=""
  fi

  if ! agentic_capture_nul_array staged_files \
    git diff --cached --name-only --no-renames -z --; then
    agentic_add_error "staged_files_check_failed"
  fi
  if ((${#staged_files[@]} == 0)); then
    agentic_add_error "empty_staging_area"
  fi

  for file in "${staged_files[@]}"; do
    if agentic_has_control_characters "$file"; then
      agentic_add_error "unsafe_staged_path"
    fi
    if agentic_is_checkpoint "$file"; then
      checkpoint_files+=("$file")
      agentic_add_error "checkpoint_staged:$file"
    fi
    if [[ -z "${allowed_paths[$file]+present}" ]]; then
      out_of_scope_files+=("$file")
    fi
  done

  if ((${#out_of_scope_files[@]} > 0)); then
    agentic_add_error "out_of_scope_files"
  fi
  agentic_sort_unique_array out_of_scope_files || agentic_add_error "scope_sort_failed"
  agentic_sort_unique_array checkpoint_files || agentic_add_error "checkpoint_sort_failed"
  agentic_validate_checkpoint_tracking || true

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

  staged_diff_file="$(mktemp)" || staged_diff_file=""
  if [[ -z "$staged_diff_file" ]]; then
    agentic_add_error "staged_diff_snapshot_failed"
  elif git -c core.quotePath=true diff --cached --binary --full-index --no-color \
    --no-ext-diff --no-textconv --no-renames --diff-algorithm=myers \
    --no-indent-heuristic --unified=3 --inter-hunk-context=0 -O/dev/null \
    --src-prefix=a/ --dst-prefix=b/ -- \
    >"$staged_diff_file"; then
    if ! staged_diff_sha256="$(agentic_sha256_file "$staged_diff_file")"; then
      agentic_add_error "sha256_tool_unavailable"
      staged_diff_sha256=""
    fi
    rm -f -- "$staged_diff_file"
  else
    rm -f -- "$staged_diff_file"
    agentic_add_error "staged_diff_snapshot_failed"
  fi

  if [[ -n "$expected_diff_sha256" &&
    "$staged_diff_sha256" != "$expected_diff_sha256" ]]; then
    agentic_add_error "expected_diff_sha256_mismatch"
  fi

  obvious_secret_scan="PASS"
  for file in "${staged_files[@]}"; do
    lower_path="${file,,}"
    base_name="${lower_path##*/}"
    artifact_rule=""
    case "$base_name" in
      .env|.env.*)
        if [[ "$base_name" != ".env.example" ]]; then
          artifact_rule="environment_file"
        fi
        ;;
      *.pem|*.key|*.p12|*.pfx) artifact_rule="private_key_artifact" ;;
      *.tfstate|*.tfstate.*|*.tfplan) artifact_rule="terraform_artifact" ;;
      *.zip) artifact_rule="archive_artifact" ;;
    esac
    case "/$lower_path/" in
      */.aws-sam/*) artifact_rule="sam_build_artifact" ;;
      */node_modules/*) artifact_rule="dependency_artifact" ;;
      */coverage/*) artifact_rule="coverage_artifact" ;;
      */.aws/credentials/*) artifact_rule="aws_credentials_file" ;;
    esac

    if [[ -n "$artifact_rule" ]]; then
      artifact_rules+=("$artifact_rule")
      artifact_files+=("$file")
      obvious_secret_scan="FAIL"
      agentic_add_error "prohibited_artifact:$file"
    fi

    if ! entry="$(git ls-files --stage -- "$file" 2>/dev/null)"; then
      agentic_add_error "staged_index_read_failed:$file"
      continue
    fi
    if [[ -z "$entry" ]]; then
      # Deleted paths have no staged blob to inspect.
      continue
    fi
    read -r mode object_id stage_number _ <<<"$entry"
    if [[ "$stage_number" != "0" ]]; then
      agentic_add_error "unmerged_staged_path:$file"
      continue
    fi
    if [[ "$mode" == "160000" ]]; then
      binary_files+=("$file")
      continue
    fi

    blob_file="$(mktemp)" || blob_file=""
    if [[ -z "$blob_file" ]]; then
      agentic_add_error "staged_blob_read_failed:$file"
      continue
    fi
    if ! git cat-file blob "$object_id" >"$blob_file" 2>/dev/null; then
      rm -f -- "$blob_file"
      agentic_add_error "staged_blob_read_failed:$file"
      continue
    fi

    if [[ -s "$blob_file" ]] && ! LC_ALL=C grep -Iq '' "$blob_file"; then
      binary_files+=("$file")
      rm -f -- "$blob_file"
      continue
    fi

    matched_rule=""
    if LC_ALL=C grep -Eaq -- '-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----' "$blob_file"; then
      matched_rule="private_key_material"
    elif LC_ALL=C grep -Eaq -- '(AKIA|ASIA)[A-Z0-9]{16}' "$blob_file"; then
      matched_rule="aws_access_key_id"
    elif LC_ALL=C grep -Eaq -- 'gh[pousr]_[A-Za-z0-9]{20,}' "$blob_file"; then
      matched_rule="github_token"
    elif LC_ALL=C grep -Eaq -- \
      'Bearer[[:space:]]+eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' \
      "$blob_file"; then
      matched_rule="bearer_jwt"
    fi

    if [[ -n "$matched_rule" ]]; then
      secret_rules+=("$matched_rule")
      secret_files+=("$file")
      obvious_secret_scan="FAIL"
      agentic_add_error "obvious_secret:$file"
    fi
    rm -f -- "$blob_file"
  done

  agentic_sort_unique_array binary_files || agentic_add_error "binary_sort_failed"

  if [[ -z "$index_path" || ! -f "$index_path" ]] ||
    ! index_sha256_after="$(agentic_sha256_file "$index_path")"; then
    agentic_add_error "index_snapshot_recheck_failed"
    index_sha256_after=""
  elif [[ "$index_sha256_before" != "$index_sha256_after" ]]; then
    agentic_add_error "index_changed_during_check"
  fi
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
  printf '"schemaVersion":%d,"tool":"agentic-staging-check",' "$AGENTIC_SCHEMA_VERSION"
  printf '"result":%s,' "$(agentic_json_quote "$result")"
  printf '"authorizationGranted":false,'
  printf '"repositoryRoot":%s,' "$(agentic_json_nullable_string "$repository_root")"
  printf '"repositoryValid":%s,' "$(agentic_json_boolean "$repository_valid")"
  printf '"branch":%s,"head":%s,' \
    "$(agentic_json_nullable_string "$branch")" \
    "$(agentic_json_nullable_string "$head_sha")"
  printf '"expectedBranch":%s,"expectedHead":%s,' \
    "$(agentic_json_quote "$expected_branch")" \
    "$(agentic_json_quote "$expected_head")"
  printf '"allowlist":'
  agentic_json_string_array allowed_files
  printf ',"stagedFiles":'
  agentic_json_string_array staged_files
  printf ',"outOfScope":'
  agentic_json_string_array out_of_scope_files
  printf ',"checkpoints":'
  agentic_json_string_array checkpoint_files
  printf ',"binaryFiles":'
  agentic_json_string_array binary_files
  printf ',"artifactFindings":['
  separator=""
  for index in "${!artifact_rules[@]}"; do
    printf '%s{' "$separator"
    printf '"rule":%s,"path":%s}' \
      "$(agentic_json_quote "${artifact_rules[index]}")" \
      "$(agentic_json_quote "${artifact_files[index]}")"
    separator=','
  done
  printf '],"secretFindings":['
  separator=""
  for index in "${!secret_rules[@]}"; do
    printf '%s{' "$separator"
    printf '"rule":%s,"path":%s}' \
      "$(agentic_json_quote "${secret_rules[index]}")" \
      "$(agentic_json_quote "${secret_files[index]}")"
    separator=','
  done
  printf '],"stagedDiffCheck":%s,' "$(agentic_json_quote "$staged_diff_check")"
  printf '"obviousSecretScan":%s,' "$(agentic_json_quote "$obvious_secret_scan")"
  printf '"stagedDiffSha256":%s,' "$(agentic_json_nullable_string "$staged_diff_sha256")"
  printf '"expectedDiffSha256":%s,' \
    "$(agentic_json_nullable_string "$expected_diff_sha256")"
  printf '"indexSha256Before":%s,"indexSha256After":%s,' \
    "$(agentic_json_nullable_string "$index_sha256_before")" \
    "$(agentic_json_nullable_string "$index_sha256_after")"
  printf '"errors":'
  agentic_json_string_array AGENTIC_ERRORS
  printf '}\n'
else
  printf 'REPOSITORY_ROOT='
  agentic_text_value "$repository_root"
  printf '\nREPOSITORY_VALID=%s\n' "$repository_valid"
  printf 'BRANCH=%s\nHEAD=%s\n' "${branch:-DETACHED}" "${head_sha:-MISSING}"
  printf 'EXPECTED_BRANCH=%s\nEXPECTED_HEAD=%s\n' "$expected_branch" "$expected_head"
  printf 'ALLOWLIST_COUNT=%d\n' "${#allowed_files[@]}"
  for file in "${allowed_files[@]}"; do
    printf 'ALLOWED_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  printf 'STAGED_FILES_COUNT=%d\n' "${#staged_files[@]}"
  for file in "${staged_files[@]}"; do
    printf 'STAGED_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${out_of_scope_files[@]}"; do
    printf 'OUT_OF_SCOPE_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${checkpoint_files[@]}"; do
    printf 'CHECKPOINT_FILE='
    agentic_text_value "$file"
    printf '\n'
  done
  for file in "${binary_files[@]}"; do
    printf 'BINARY_FILE='
    agentic_text_value "$file"
    printf ' INSPECTION=NOT_INSPECTABLE\n'
  done
  for index in "${!artifact_rules[@]}"; do
    printf 'ARTIFACT_FINDING_RULE=%s PATH=' "${artifact_rules[index]}"
    agentic_text_value "${artifact_files[index]}"
    printf '\n'
  done
  for index in "${!secret_rules[@]}"; do
    printf 'SECRET_FINDING_RULE=%s PATH=' "${secret_rules[index]}"
    agentic_text_value "${secret_files[index]}"
    printf '\n'
  done
  printf 'STAGED_DIFF_CHECK=%s\n' "$staged_diff_check"
  printf 'OBVIOUS_SECRET_SCAN=%s\n' "$obvious_secret_scan"
  printf 'STAGED_DIFF_SHA256=%s\n' "${staged_diff_sha256:-UNAVAILABLE}"
  printf 'EXPECTED_DIFF_SHA256=%s\n' "${expected_diff_sha256:-NOT_PROVIDED}"
  printf 'INDEX_SHA256_BEFORE=%s\nINDEX_SHA256_AFTER=%s\n' \
    "${index_sha256_before:-UNAVAILABLE}" "${index_sha256_after:-UNAVAILABLE}"
  printf 'AUTHORIZATION_GRANTED=no\n'
  for error in "${AGENTIC_ERRORS[@]}"; do
    printf 'ERROR='
    agentic_text_value "$error"
    printf '\n'
  done
  printf 'STAGING_RESULT=%s\n' "$result"
fi

exit "$exit_code"
