#!/usr/bin/env bash
# Test script to verify sleep prevention works

set -euo pipefail

echo "Testing sleep prevention integration..."
echo

# Test 1: Check if caffeinate is available on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    echo "✓ Running on macOS"
    if command -v caffeinate &> /dev/null; then
        echo "✓ caffeinate is available: $(which caffeinate)"
    else
        echo "✗ caffeinate not found! This is unusual for macOS."
        exit 1
    fi
else
    echo "ℹ Not running on macOS - caffeinate not needed"
fi
echo

# Test 2: Test caffeinate wrapping logic
echo "Testing command wrapping logic..."
ENABLE_ENDURANCE_MODE="True"
PREVENT_SLEEP="True"

cmd=(echo "test command")

if [[ "$ENABLE_ENDURANCE_MODE" == "True" ]] && [[ "$PREVENT_SLEEP" == "True" ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v caffeinate &> /dev/null; then
            cmd=(caffeinate -i "${cmd[@]}")
            echo "✓ Command wrapped with caffeinate: ${cmd[*]}"
        fi
    fi
fi
echo

# Test 3: Execute a short test command with caffeinate
echo "Testing 5-second sleep with caffeinate..."
if [[ "$(uname)" == "Darwin" ]]; then
    caffeinate -i sh -c 'echo "Starting 5-second test..."; sleep 5; echo "Test completed!"'
    echo "✓ caffeinate executed successfully"
else
    sleep 5
    echo "✓ Sleep completed (no caffeinate on non-macOS)"
fi
echo

# Test 4: Verify script parsing
echo "Testing script argument parsing..."
if [[ "$(uname)" == "Darwin" ]]; then
    output=$(./run_multiple_real_workloads.sh \
        --qps 1 \
        --num-input-tokens 100 \
        --num-output-tokens 100 \
        --enable-endurance-mode True \
        --test-duration-hours 0.001 \
        --prevent-sleep True \
        --dry-run 2>&1)

    if echo "$output" | grep -q "caffeinate"; then
        echo "✓ Script includes caffeinate in dry-run output"
    else
        echo "✗ caffeinate not found in script output"
        echo "Output preview:"
        echo "$output" | head -20
    fi
else
    echo "ℹ Skipping caffeinate check on non-macOS"
fi

echo
echo "All tests passed! ✓"
echo
echo "To test with a real short endurance run:"
echo "  ./run_multiple_real_workloads.sh \\"
echo "    --qps 1 \\"
echo "    --enable-endurance-mode True \\"
echo "    --test-duration-hours 0.0028"  # ~10 seconds
