#!/usr/bin/env bash
# run_multiple_real_workloads.sh
# Usage examples:
#   ./run_multiple_real_workloads.sh --qps [20,40] --num-input-tokens [500,1000] --num-output-tokens [500,1000]
#   ./run_multiple_real_workloads.sh --qps 40,80 --num-input-tokens 1000 --num-output-tokens [100,500]
#   ./run_multiple_real_workloads.sh --qps [20,40] --num-input-tokens [500,1000] --num-output-tokens [500,1000] --dry-run
#
# Notes:
# - Accepts list values either as [a,b,c] or a,b,c or single scalar like 40
# - Add --dry-run to just print the commands without executing
# - Everything after a standalone `--` is passed through to evaluator.py verbatim

set -euo pipefail

ulimit -n 4096 || true

# Defaults (can be overridden by flags)
# QPS from 10 to 600 in steps of 10
qps_list=({1..60})
num_in_list=(1000)
num_out_list=(1000)
dry_run=0

# Fixed args (edit if you need different defaults)
MODE="real_workload"
MODEL_NAME="MiniMax-M2.5"
# Results dir: base path + model name + timestamp so files don't overwrite across runs
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MODEL_SAFE="${MODEL_NAME//[^a-zA-Z0-9.-]/_}"
RESULTS_DIR="./data/results/llmperf/${MODEL_SAFE}_${TIMESTAMP}"
QPS_DISTRIBUTION="constant"
TIMEOUT="600"
MULTI_SIZE="na"
DEBUG_MODE="False"
LLM_API="sncloud"

# Endurance testing parameters (defaults)
ENABLE_ENDURANCE_MODE="False"
TEST_DURATION_HOURS="12.0"
CHECKPOINT_INTERVAL_SECONDS="300"
CHECKPOINT_INTERVAL_REQUESTS="1000"
ENABLE_RESUME="True"
CHECKPOINT_DIR=""
PREVENT_SLEEP="True"  # Use caffeinate on macOS to prevent system sleep

EXTRA_ARGS=()

# --- helpers ---------------------------------------------------------------

# _parse_to_array VAR_NAME INPUT
# Accepts "[1,2,3]" or "1,2,3" or "1" and writes a bash array into VAR_NAME
_parse_to_array() {
  local __var="$1"
  local s="$2"
  # strip surrounding brackets if present
  s="${s#[}"
  s="${s%]}"
  # convert commas to spaces
  s="${s//,/ }"
  # squeeze multiple spaces
  # shellcheck disable=SC2001
  s="$(echo "$s" | sed -E 's/[[:space:]]+/ /g' | sed -E 's/^ | $//g')"
  # assign as array
  # shellcheck disable=SC2086
  eval "$__var=($s)"
}

# --- arg parsing -----------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --qps)
      [[ $# -ge 2 ]] || { echo "Error: --qps needs a value"; exit 1; }
      _parse_to_array qps_list "$2"
      shift 2
      ;;
    --num-input-tokens)
      [[ $# -ge 2 ]] || { echo "Error: --num-input-tokens needs a value"; exit 1; }
      _parse_to_array num_in_list "$2"
      shift 2
      ;;
    --num-output-tokens)
      [[ $# -ge 2 ]] || { echo "Error: --num-output-tokens needs a value"; exit 1; }
      _parse_to_array num_out_list "$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --enable-endurance-mode)
      [[ $# -ge 2 ]] || { echo "Error: --enable-endurance-mode needs a value"; exit 1; }
      ENABLE_ENDURANCE_MODE="$2"
      shift 2
      ;;
    --test-duration-hours)
      [[ $# -ge 2 ]] || { echo "Error: --test-duration-hours needs a value"; exit 1; }
      TEST_DURATION_HOURS="$2"
      shift 2
      ;;
    --checkpoint-interval-seconds)
      [[ $# -ge 2 ]] || { echo "Error: --checkpoint-interval-seconds needs a value"; exit 1; }
      CHECKPOINT_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --checkpoint-interval-requests)
      [[ $# -ge 2 ]] || { echo "Error: --checkpoint-interval-requests needs a value"; exit 1; }
      CHECKPOINT_INTERVAL_REQUESTS="$2"
      shift 2
      ;;
    --enable-resume)
      [[ $# -ge 2 ]] || { echo "Error: --enable-resume needs a value"; exit 1; }
      ENABLE_RESUME="$2"
      shift 2
      ;;
    --checkpoint-dir)
      [[ $# -ge 2 ]] || { echo "Error: --checkpoint-dir needs a value"; exit 1; }
      CHECKPOINT_DIR="$2"
      shift 2
      ;;
    --prevent-sleep)
      [[ $# -ge 2 ]] || { echo "Error: --prevent-sleep needs a value"; exit 1; }
      PREVENT_SLEEP="$2"
      shift 2
      ;;
    --) # pass-through to evaluator.py
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      echo "Unknown option: $1"
      echo "Try: --qps [20,40] --num-input-tokens [500,1000] --num-output-tokens [500,1000] [--dry-run] [-- ...extra flags]"
      exit 1
      ;;
  esac
done

# --- run all permutations --------------------------------------------------

echo "qps: ${qps_list[*]}"
echo "num-input-tokens: ${num_in_list[*]}"
echo "num-output-tokens: ${num_out_list[*]}"
echo "results-dir: $RESULTS_DIR"
[[ ${#EXTRA_ARGS[@]} -gt 0 ]] && echo "extra args -> ${EXTRA_ARGS[*]}"

rc=0
for qps in "${qps_list[@]}"; do
  # Set num-requests to 3x current QPS
  # num_requests=$((2 * qps))
  num_requests=128
  for nin in "${num_in_list[@]}"; do
    for nout in "${num_out_list[@]}"; do
      echo "==> Running combo: qps=$qps, num_requests=$num_requests, num_input_tokens=$nin, num_output_tokens=$nout"

      cmd=(python src/evaluator.py
        --mode "$MODE"
        --model-name "$MODEL_NAME"
        --results-dir "$RESULTS_DIR"
        --qps "$qps"
        --qps-distribution "$QPS_DISTRIBUTION"
        --timeout "$TIMEOUT"
        --num-input-tokens "$nin"
        --num-output-tokens "$nout"
        --multimodal-image-size "$MULTI_SIZE"
        --num-requests "$num_requests"
        --use-debugging-mode "$DEBUG_MODE"
        --llm-api "$LLM_API"
        --enable-endurance-mode "$ENABLE_ENDURANCE_MODE"
        --test-duration-hours "$TEST_DURATION_HOURS"
        --checkpoint-interval-seconds "$CHECKPOINT_INTERVAL_SECONDS"
        --checkpoint-interval-requests "$CHECKPOINT_INTERVAL_REQUESTS"
        --enable-resume "$ENABLE_RESUME"
      )

      # Add checkpoint-dir if specified
      if [[ -n "$CHECKPOINT_DIR" ]]; then
        cmd+=(--checkpoint-dir "$CHECKPOINT_DIR")
      fi

      # pass-through extras last (if any)
      if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
        cmd+=("${EXTRA_ARGS[@]}")
      fi

      # Wrap with caffeinate on macOS to prevent sleep during endurance tests
      if [[ "$ENABLE_ENDURANCE_MODE" == "True" ]] && [[ "$PREVENT_SLEEP" == "True" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
          if command -v caffeinate &> /dev/null; then
            echo "==> Using caffeinate to prevent system sleep during endurance test"
            cmd=(caffeinate -i "${cmd[@]}")
          else
            echo "WARNING: caffeinate not found. System may sleep during long tests!" >&2
          fi
        fi
      fi

      echo "+ ${cmd[*]}"
      if [[ $dry_run -eq 0 ]]; then
        if ! "${cmd[@]}"; then
          echo "ERROR: run failed for qps=$qps nin=$nin nout=$nout" >&2
          rc=1
        fi
      fi
    done
  done
done

exit "$rc"
