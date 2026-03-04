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
# QPS from 1 to 50 in steps of 5
qps_list=(5 10 15 20 25 30 35 40 45 50)
num_in_list=(1000)
num_out_list=(1000)
dry_run=0

# Fixed args (edit if you need different defaults)
MODE="real_workload"
# MODEL_NAME="Meta-Llama-3.1-405B"
MODEL_NAME="MiniMax-M2.5"
# MODEL_NAME="Meta-Llama-3.3-70B-Instruct"
# MODEL_NAME="DeepSeek-V3-0324"
# Results dir: base path + model name + timestamp so files don't overwrite across runs
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MODEL_SAFE="${MODEL_NAME//[^a-zA-Z0-9.-]/_}"
RESULTS_DIR="./data/results/llmperf/${MODEL_SAFE}_${TIMESTAMP}"
QPS_DISTRIBUTION="constant"
TIMEOUT="600"
MULTI_SIZE="na"
NUM_REQUESTS="1024"
DEBUG_MODE="False"
LLM_API="sncloud"

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
  for nin in "${num_in_list[@]}"; do
    for nout in "${num_out_list[@]}"; do
      echo "==> Running combo: qps=$qps, num_input_tokens=$nin, num_output_tokens=$nout"

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
        --num-requests "$NUM_REQUESTS"
        --use-debugging-mode "$DEBUG_MODE"
        --llm-api "$LLM_API"
      )

      # pass-through extras last (if any)
      if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
        cmd+=("${EXTRA_ARGS[@]}")
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
