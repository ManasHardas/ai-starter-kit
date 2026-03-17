#!/bin/bash

# Poisson Load Test Wrapper Script
# Simplifies running Poisson-based variable load tests

set -e  # Exit on error

# Default configuration
CONFIG_FILE="configs/poisson_load_basic.yaml"
TARGET_QPS=""
LLM_API="sncloud"
TIMEOUT=600
USE_DEBUGGING_MODE="False"
METADATA=""
SAMPLING_PARAMS="{}"
PREVENT_SLEEP="True"

# Python interpreter detection
if [[ -x "../py3.12/bin/python" ]]; then
    PYTHON="../py3.12/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --target-qps)
            TARGET_QPS="$2"
            shift 2
            ;;
        --llm-api)
            LLM_API="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --use-debugging-mode)
            USE_DEBUGGING_MODE="$2"
            shift 2
            ;;
        --metadata)
            METADATA="$2"
            shift 2
            ;;
        --sampling-params)
            SAMPLING_PARAMS="$2"
            shift 2
            ;;
        --prevent-sleep)
            PREVENT_SLEEP="$2"
            shift 2
            ;;
        --python)
            PYTHON="$2"
            shift 2
            ;;
        --help)
            echo "Poisson Load Test Wrapper Script"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --config <file>              Path to YAML config file (default: configs/poisson_load_basic.yaml)"
            echo "  --target-qps <float>         Target total QPS (optional, generates simplified config)"
            echo "  --llm-api <string>           LLM API type (default: sncloud)"
            echo "  --timeout <int>              Request timeout in seconds (default: 600)"
            echo "  --use-debugging-mode <bool>  Enable debug mode (default: False)"
            echo "  --metadata <string>          Comma-separated metadata (e.g., name=foo,bar=1)"
            echo "  --sampling-params <json>     JSON sampling parameters (default: {})"
            echo "  --prevent-sleep <bool>       Prevent system sleep on macOS (default: True)"
            echo "  --python <path>              Python interpreter path (auto-detected)"
            echo "  --help                       Show this help message"
            echo ""
            echo "Examples:"
            echo "  # Quick test (5 minutes)"
            echo "  $0 --config configs/poisson_load_quick_test.yaml"
            echo ""
            echo "  # Basic load test (1 hour)"
            echo "  $0 --config configs/poisson_load_basic.yaml"
            echo ""
            echo "  # Stress test (2 hours)"
            echo "  $0 --config configs/poisson_load_stress.yaml"
            echo ""
            echo "  # Endurance test (12 hours)"
            echo "  $0 --config configs/poisson_load_endurance.yaml"
            echo ""
            echo "  # Generate config from target QPS"
            echo "  $0 --config configs/poisson_load_basic.yaml --target-qps 20"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Verify config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    echo ""
    echo "Available configs:"
    ls -1 configs/poisson_load_*.yaml 2>/dev/null || echo "  (none found)"
    echo ""
    exit 1
fi

echo "=========================================="
echo "Poisson Load Test"
echo "=========================================="
echo "Config file:      $CONFIG_FILE"
echo "Python:           $PYTHON"
echo "LLM API:          $LLM_API"
echo "Timeout:          ${TIMEOUT}s"
if [[ -n "$TARGET_QPS" ]]; then
    echo "Target QPS:       $TARGET_QPS"
fi
echo "=========================================="
echo ""

# Build command
cmd=(
    "$PYTHON" src/evaluator.py
    --mode poisson_load
    --config "$CONFIG_FILE"
    --llm-api "$LLM_API"
    --timeout "$TIMEOUT"
    --use-debugging-mode "$USE_DEBUGGING_MODE"
)

# Add optional arguments
if [[ -n "$TARGET_QPS" ]]; then
    cmd+=(--target-qps "$TARGET_QPS")
fi

if [[ -n "$METADATA" ]]; then
    cmd+=(--metadata "$METADATA")
fi

if [[ -n "$SAMPLING_PARAMS" && "$SAMPLING_PARAMS" != "{}" ]]; then
    cmd+=(--sampling-params "$SAMPLING_PARAMS")
fi

# Check if we should use caffeinate on macOS
if [[ "$PREVENT_SLEEP" == "True" ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v caffeinate &> /dev/null; then
            echo "==> Using caffeinate to prevent system sleep during test"
            cmd=(caffeinate -i "${cmd[@]}")
        else
            echo "==> Warning: caffeinate not found. System may sleep during test."
        fi
    fi
fi

# Display command
echo "Running command:"
echo "${cmd[@]}"
echo ""

# Execute
"${cmd[@]}"

exit_code=$?

echo ""
echo "=========================================="
if [[ $exit_code -eq 0 ]]; then
    echo "Poisson load test completed successfully!"
else
    echo "Poisson load test failed with exit code: $exit_code"
fi
echo "=========================================="

exit $exit_code
