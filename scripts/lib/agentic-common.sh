#!/usr/bin/env bash

# Shared, read-only helpers for the Agentic Development Harness guards.

AGENTIC_SCHEMA_VERSION=1
AGENTIC_CHECKPOINTS=(
  "prompt_inicio_dia.txt"
  "prompt_inicio_dia copy.txt"
)

agentic_add_error() {
  local code="$1"
  AGENTIC_ERRORS+=("$code")
}

agentic_is_checkpoint() {
  local path="$1"
  local checkpoint

  for checkpoint in "${AGENTIC_CHECKPOINTS[@]}"; do
    if [[ "$path" == "$checkpoint" ]]; then
      return 0
    fi
  done
  return 1
}

agentic_is_full_sha() {
  local value="$1"
  [[ "$value" =~ ^[0-9a-fA-F]{40}$ || "$value" =~ ^[0-9a-fA-F]{64}$ ]]
}

agentic_is_sha256() {
  local value="$1"
  [[ "$value" =~ ^[0-9a-fA-F]{64}$ ]]
}

agentic_has_control_characters() {
  local value="$1"
  local character code index

  for ((index = 0; index < ${#value}; index++)); do
    character="${value:index:1}"
    printf -v code '%d' "'$character"
    if ((code < 32 || code == 127)); then
      return 0
    fi
  done
  return 1
}

agentic_normalize_repo_path() {
  local path="$1"
  local segment
  local -a segments=()

  while [[ "$path" == ./* ]]; do
    path="${path#./}"
  done

  if [[ -z "$path" || "$path" == "." || "$path" == /* || "$path" == */ ||
    "$path" == *//* ]] || agentic_has_control_characters "$path"; then
    return 1
  fi

  IFS='/' read -r -a segments <<<"$path"
  for segment in "${segments[@]}"; do
    if [[ -z "$segment" || "$segment" == "." || "$segment" == ".." ]]; then
      return 1
    fi
  done

  if [[ "$path" == ".git" || "$path" == .git/* ]]; then
    return 1
  fi

  printf '%s' "$path"
}

agentic_json_quote() {
  local value="$1"
  local character code index

  printf '"'
  LC_ALL=C
  for ((index = 0; index < ${#value}; index++)); do
    character="${value:index:1}"
    case "$character" in
      '"') printf '\\"' ;;
      '\\') printf '\\\\' ;;
      $'\b') printf '\\b' ;;
      $'\f') printf '\\f' ;;
      $'\n') printf '\\n' ;;
      $'\r') printf '\\r' ;;
      $'\t') printf '\\t' ;;
      *)
        printf -v code '%d' "'$character"
        if ((code < 32 || code == 127)); then
          printf '\\u%04x' "$code"
        else
          printf '%s' "$character"
        fi
        ;;
    esac
  done
  printf '"'
}

agentic_json_nullable_string() {
  local value="$1"
  if [[ -n "$value" ]]; then
    agentic_json_quote "$value"
  else
    printf 'null'
  fi
}

agentic_json_boolean() {
  if [[ "$1" == "yes" || "$1" == "true" ]]; then
    printf 'true'
  else
    printf 'false'
  fi
}

agentic_json_string_array() {
  local array_name="$1"
  local -n values="$array_name"
  local separator=""
  local value

  printf '['
  for value in "${values[@]}"; do
    printf '%s' "$separator"
    agentic_json_quote "$value"
    separator=','
  done
  printf ']'
}

agentic_text_value() {
  local value="$1"
  if agentic_has_control_characters "$value"; then
    agentic_json_quote "$value"
  else
    printf '%s' "$value"
  fi
}

agentic_capture_nul_array() {
  local array_name="$1"
  shift
  local -n target="$array_name"
  local temporary

  temporary="$(mktemp)" || return 1
  if ! "$@" >"$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  target=()
  mapfile -d '' -t target <"$temporary"
  rm -f -- "$temporary"
}

agentic_capture_lines_array() {
  local array_name="$1"
  shift
  local -n target="$array_name"
  local temporary

  temporary="$(mktemp)" || return 1
  if ! "$@" >"$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  target=()
  mapfile -t target <"$temporary"
  rm -f -- "$temporary"
}

agentic_sort_unique_array() {
  local array_name="$1"
  local -n values="$array_name"
  local temporary

  if ((${#values[@]} == 0)); then
    return 0
  fi

  temporary="$(mktemp)" || return 1
  if ! printf '%s\0' "${values[@]}" | LC_ALL=C sort -zu >"$temporary"; then
    rm -f -- "$temporary"
    return 1
  fi
  values=()
  mapfile -d '' -t values <"$temporary"
  rm -f -- "$temporary"
}

agentic_array_contains() {
  local array_name="$1"
  local expected="$2"
  local -n values="$array_name"
  local value

  for value in "${values[@]}"; do
    if [[ "$value" == "$expected" ]]; then
      return 0
    fi
  done
  return 1
}

agentic_sha256_file() {
  local path="$1"
  local output

  if command -v sha256sum >/dev/null 2>&1; then
    output="$(sha256sum -- "$path")" || return 1
    printf '%s' "${output%% *}"
  elif command -v shasum >/dev/null 2>&1; then
    output="$(shasum -a 256 -- "$path")" || return 1
    printf '%s' "${output%% *}"
  else
    return 1
  fi
}

agentic_git_diff_check() {
  local standard_output standard_error return_code

  standard_output="$(mktemp)" || return 2
  standard_error="$(mktemp)" || {
    rm -f -- "$standard_output"
    return 2
  }

  if git diff --check "$@" >"$standard_output" 2>"$standard_error"; then
    return_code=0
  else
    return_code=$?
  fi

  if [[ -s "$standard_output" ]]; then
    return_code=1
  elif [[ -s "$standard_error" ]] &&
    ! LC_ALL=C grep -Eq '^(fatal|error):' "$standard_error"; then
    return_code=1
  elif [[ -s "$standard_error" || $return_code -gt 1 ]]; then
    return_code=2
  fi

  rm -f -- "$standard_output" "$standard_error"
  return "$return_code"
}

agentic_untracked_diff_check() {
  local path="$1"
  local standard_output standard_error return_code

  standard_output="$(mktemp)" || return 2
  standard_error="$(mktemp)" || {
    rm -f -- "$standard_output"
    return 2
  }

  if git diff --no-index --check -- /dev/null "$path" \
    >"$standard_output" 2>"$standard_error"; then
    return_code=0
  else
    return_code=$?
  fi

  if [[ -s "$standard_output" ]]; then
    return_code=1
  elif [[ -s "$standard_error" ]] &&
    ! LC_ALL=C grep -Eq '^(fatal|error):' "$standard_error"; then
    return_code=1
  elif [[ -s "$standard_error" || $return_code -gt 1 ]]; then
    return_code=2
  elif [[ $return_code -eq 1 ]]; then
    # A normal no-index diff returns 1 when the files differ.
    return_code=0
  fi

  rm -f -- "$standard_output" "$standard_error"
  return "$return_code"
}

agentic_repository_is_valid() {
  local repository_root="$1"
  [[ "$(basename -- "$repository_root")" == "serverless-student-manager" ]] &&
    [[ -f "$repository_root/AGENTS.md" ]] &&
    grep -q '^# AGENTS.md — Serverless Student Manager$' "$repository_root/AGENTS.md"
}

agentic_validate_checkpoint_tracking() {
  local checkpoint
  local failed=0
  local -a index_paths=()
  local -a head_paths=()

  for checkpoint in "${AGENTIC_CHECKPOINTS[@]}"; do
    if ! agentic_capture_nul_array index_paths git ls-files -z -- "$checkpoint"; then
      agentic_add_error "checkpoint_index_check_failed:$checkpoint"
      failed=1
      continue
    fi
    if ! agentic_capture_nul_array head_paths \
      git ls-tree -r --name-only -z HEAD -- "$checkpoint"; then
      agentic_add_error "checkpoint_head_check_failed:$checkpoint"
      failed=1
      continue
    fi
    if ((${#index_paths[@]} > 0 || ${#head_paths[@]} > 0)); then
      agentic_add_error "checkpoint_tracked:$checkpoint"
      failed=1
    fi
  done
  return "$failed"
}
