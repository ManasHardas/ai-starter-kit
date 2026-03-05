#!/bin/bash
# run_real_workload_dataset.sh

set -euo pipefail

ulimit -n 4096

# --- configuration -----------------------------------------------------------

MODEL_NAME="gpt-oss-120b"
RESULTS_DIR="./data/results/llmperf"
QPS="${QPS:-1}"                    # Allow overriding via env var: QPS=10 ./run_real_workload_dataset.sh
QPS_DISTRIBUTION="constant"
TIMEOUT=600
NUM_INPUT_TOKENS=1000
NUM_OUTPUT_TOKENS=1000
MULTIMODAL_IMAGE_SIZE="na"
NUM_REQUESTS=128
DEBUG_MODE="False"
LLM_API="sncloud"

# --- timing ------------------------------------------------------------------

SCRIPT_START=$(date +%s)

echo "==================================================================="
echo " Real workload benchmark"
echo " Model        : ${MODEL_NAME}"
echo " QPS          : ${QPS}"
echo " Results dir  : ${RESULTS_DIR}"
echo " Started at   : $(date)"
echo "==================================================================="
echo

RUN_START=$(date +%s)
echo "[RUN] Starting real workload run at $(date) (qps=${QPS})"
echo

python src/evaluator.py \
  --mode real_workload \
  --model-name "${MODEL_NAME}" \
  --results-dir "${RESULTS_DIR}" \
  --qps "${QPS}" \
  --qps-distribution "${QPS_DISTRIBUTION}" \
  --timeout "${TIMEOUT}" \
  --num-input-tokens "${NUM_INPUT_TOKENS}" \
  --num-output-tokens "${NUM_OUTPUT_TOKENS}" \
  --multimodal-image-size "${MULTIMODAL_IMAGE_SIZE}" \
  --num-requests "${NUM_REQUESTS}" \
  --use-debugging-mode "${DEBUG_MODE}" \
  --llm-api "${LLM_API}"

RUN_END=$(date +%s)
RUN_ELAPSED=$((RUN_END - RUN_START))

echo
echo "[RUN] Finished real workload run (qps=${QPS}) in ${RUN_ELAPSED}s at $(date)"

SCRIPT_END=$(date +%s)
SCRIPT_ELAPSED=$((SCRIPT_END - SCRIPT_START))

echo "-------------------------------------------------------------------"
echo " Total script time: ${SCRIPT_ELAPSED}s"
echo "-------------------------------------------------------------------"
echo

# Notes:
# Here are some examples of how to run the script with different models and API endpoints.
#
# 1. SambaNova Cloud 
#
#   1.1 Instruct models

# python src/evaluator.py \
# --mode real_workload \
# --model-names "Meta-Llama-3.3-70B-Instruct" \
# --results-dir "./data/results/llmperf" \
# --num-concurrent-requests 1 \
# --timeout 600 \
# --num-input-tokens 1000 \
# --num-output-tokens 1000 \
# --multimodal-image-size na \
# --num-requests 16 \
# --use-debugging-mode False \
# --llm-api sncloud

#   1.2 Multimodal models 

# python src/evaluator.py \
# --mode real_workload \
# --model-names "Llama-3.2-11B-Vision-Instruct" \
# --results-dir "./data/results/llmperf" \
# --num-concurrent-requests 1 \
# --timeout 600 \
# --num-input-tokens 1000 \
# --num-output-tokens 1000 \
# --multimodal-image-size medium \
# --num-requests 16 \
# --use-debugging-mode False \
# --llm-api sncloud
