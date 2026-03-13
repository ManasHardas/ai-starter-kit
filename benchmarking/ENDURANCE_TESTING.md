# Endurance Testing Documentation

## Overview

The endurance testing feature enables long-running benchmarking tests (6-12+ hours) with automatic checkpointing, crash recovery, and bounded memory usage.

## Features

- **Duration-based testing**: Run tests for a specified duration instead of a fixed number of requests
- **Incremental result writing**: Results are written to JSONL as they arrive, not buffered in memory
- **Periodic checkpointing**: State is saved every 5 minutes (configurable) to prevent data loss
- **Automatic resume**: Tests automatically resume from the last checkpoint if interrupted
- **Rolling statistics**: Memory-efficient statistics calculation using Welford's algorithm and reservoir sampling
- **Bounded memory**: Only ~50MB peak memory usage regardless of test duration

## Quick Start

### Basic 12-hour endurance test

```bash
cd benchmarking
./run_multiple_real_workloads.sh \
  --qps 10 \
  --num-input-tokens 1000 \
  --num-output-tokens 1000 \
  --enable-endurance-mode True \
  --test-duration-hours 12
```

**Note:** On macOS, the script automatically uses `caffeinate` to prevent system sleep during endurance tests. This ensures your tests won't hang if your computer tries to sleep.

### Custom checkpoint intervals

```bash
python src/evaluator.py \
  --mode real_workload \
  --model-name "DeepSeek-V3.1" \
  --results-dir "./endurance_test_results" \
  --llm-api sncloud \
  --qps 10 \
  --qps-distribution constant \
  --num-input-tokens 1000 \
  --num-output-tokens 500 \
  --multimodal-image-size na \
  --enable-endurance-mode True \
  --test-duration-hours 6 \
  --checkpoint-interval-seconds 60 \
  --checkpoint-interval-requests 500
```

### 24-hour stress test with exponential QPS distribution

```bash
python src/evaluator.py \
  --mode real_workload \
  --model-name "Meta-Llama-3.3-70B-Instruct" \
  --results-dir "./stress_test_results" \
  --llm-api sncloud \
  --qps 50 \
  --qps-distribution exponential \
  --num-input-tokens 2000 \
  --num-output-tokens 1000 \
  --multimodal-image-size na \
  --enable-endurance-mode True \
  --test-duration-hours 24 \
  --checkpoint-interval-seconds 300
```

## CLI Arguments

### Endurance Mode Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--enable-endurance-mode` | bool | False | Enable endurance testing mode |
| `--test-duration-hours` | float | 12.0 | Test duration in hours |
| `--checkpoint-interval-seconds` | int | 300 | Minimum seconds between checkpoints |
| `--checkpoint-interval-requests` | int | 1000 | Minimum requests between checkpoints |
| `--enable-resume` | bool | True | Auto-resume from checkpoint if found |
| `--checkpoint-dir` | str | None | Custom checkpoint directory (defaults to results-dir) |
| `--prevent-sleep` | bool | True | Use caffeinate on macOS to prevent system sleep (bash script only) |

### Standard Real Workload Arguments

All standard real_workload arguments are still supported:
- `--qps` - Queries per second
- `--qps-distribution` - Distribution type (constant, uniform, exponential)
- `--num-input-tokens` - Number of input tokens per request
- `--num-output-tokens` - Number of output tokens per request
- `--model-name` - Model to test
- `--llm-api` - API type (sncloud)
- etc.

## Output Files

Endurance tests produce the following files:

```
./results_dir/
├── checkpoint_{run_uuid}.json                    # Checkpoint state (deleted after completion)
├── endurance_*_individual_responses.jsonl        # Streaming JSONL with all responses
├── endurance_*_summary.json                      # Final summary with statistics
└── intermediate_summary_{run_uuid}.json          # Latest checkpoint statistics
```

### JSONL Format

Individual responses are written as newline-delimited JSON:

```json
{"client_ttft_s": 0.123, "client_end_to_end_latency_s": 1.456, ...}
{"client_ttft_s": 0.145, "client_end_to_end_latency_s": 1.523, ...}
...
```

This format allows:
- Efficient appending during test execution
- Streaming reads without loading entire file into memory
- Recovery from partial writes (each line is independent)

### Summary Format

The summary file maintains the same format as standard benchmarking results for compatibility:

```json
{
  "name": "endurance_*_summary",
  "metadata": {
    "model": "DeepSeek-V3.1",
    "test_duration_hours": 12.0,
    "qps": 10.0,
    "results": {
      "client_ttft_s": {
        "mean": 0.234,
        "min": 0.100,
        "max": 0.500,
        "stddev": 0.045,
        "quantiles": {
          "p50": 0.220,
          "p90": 0.350,
          "p95": 0.400,
          "p99": 0.480
        }
      },
      ...
    }
  }
}
```

## Crash Recovery

If a test is interrupted (crash, network failure, manual stop):

1. Checkpoint files remain in the results directory
2. Simply re-run the same command
3. Test automatically resumes from the last checkpoint
4. Results continue appending to the JSONL file

**Example:**

```bash
# Start test
./run_multiple_real_workloads.sh --enable-endurance-mode True --test-duration-hours 12

# ... test runs for 8 hours then crashes ...

# Resume (same command)
./run_multiple_real_workloads.sh --enable-endurance-mode True --test-duration-hours 12
# Output: "Found checkpoint! Resuming from 28,800 completed requests."
```

## Monitoring Test Progress

### Real-time monitoring with intermediate summaries

```bash
# Watch intermediate summary updates (refreshes every 5 minutes)
watch -n 30 cat ./results_dir/intermediate_summary_*.json
```

### Count completed requests

```bash
# Count lines in JSONL file
wc -l ./results_dir/endurance_*_individual_responses.jsonl
```

### Monitor with tail

```bash
# Watch requests streaming in real-time
tail -f ./results_dir/endurance_*_individual_responses.jsonl
```

## Memory Usage

Endurance tests are designed for bounded memory usage:

| Component | Memory Usage | Notes |
|-----------|--------------|-------|
| Response buffer | ~50 KB | 1000 responses × 50 bytes |
| Rolling statistics | ~10 MB | 10K samples × 5 metrics × 200 bytes |
| Request queue | ~20 MB | ThreadPoolExecutor overhead |
| **Total** | **~50 MB** | Independent of test duration |

For comparison, standard mode accumulates:
- 12 hours @ 10 QPS = 432,000 responses
- ~50 MB per 1,000 responses
- **~20 GB total memory** (400x more!)

## Performance Expectations

**12-hour test at 10 QPS:**

| Metric | Value |
|--------|-------|
| Total Requests | 432,000 |
| Checkpoints | 144 (every 5 min) |
| JSONL File Size | ~500 MB |
| Peak Memory | ~50 MB |
| Checkpoint Size | ~1 MB |
| Resume Time | <5 seconds |

## Troubleshooting

### macOS System Sleep Issues

**Problem:** Test hangs or fails when Mac goes to sleep during long tests.

**Solution:** The script automatically prevents sleep on macOS using `caffeinate` when endurance mode is enabled.

**Manual verification:**
```bash
# Check if caffeinate is available
which caffeinate
# Should output: /usr/bin/caffeinate

# Manually run with caffeinate
caffeinate -i python src/evaluator.py --enable-endurance-mode True ...
```

**Disable sleep prevention** (not recommended):
```bash
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --prevent-sleep False  # Disables caffeinate
```

**Additional protection:**
1. Go to System Settings → Lock Screen → Turn display off when inactive: Never
2. Go to System Settings → Battery → Prevent automatic sleeping when display is off: On
3. Keep Mac plugged into power

**Network retry logic:** The endurance evaluator automatically retries network requests up to 3 times with exponential backoff (1s, 2s, 4s) to handle transient network issues after wake.

### Test not resuming from checkpoint

Check that:
1. You're using the same `--results-dir`
2. Checkpoint file exists: `ls ./results_dir/checkpoint_*.json`
3. `--enable-resume True` is set (default)

### High memory usage

Check that:
1. `--enable-endurance-mode True` is set
2. Checkpoints are being created (look for log messages)
3. JSONL file is growing (not buffered in memory)

### Checkpoint corruption

If a checkpoint is corrupted:
```bash
# Remove checkpoint to start fresh
rm ./results_dir/checkpoint_*.json

# Note: This will lose progress, but JSONL data is preserved
```

### Test not ending at specified duration

Check that:
1. You're not hitting the `--timeout` limit first
2. System time hasn't changed (monotonic clock is used)
3. No stop signal was sent

## Integration with Existing Tools

Endurance tests produce the same summary format as standard tests, so existing analysis tools work without modification:

```bash
# Existing tools still work
python analyze_results.py ./results_dir/endurance_*_summary.json
```

For JSONL analysis:

```python
import json

# Read JSONL file
with open('endurance_*_individual_responses.jsonl', 'r') as f:
    for line in f:
        response = json.loads(line)
        # Process response...
```

## Best Practices

1. **Start with shorter tests**: Validate with 1-hour tests before running 12+ hour tests
2. **Monitor disk space**: JSONL files can grow large (500MB for 12 hours @ 10 QPS)
3. **Use checkpoint intervals wisely**: More frequent checkpoints = less data loss risk, but more I/O
4. **Plan for restarts**: Design tests assuming they will be interrupted and resumed
5. **Archive checkpoints**: Keep checkpoint files until test completes successfully

## Example Test Suite

```bash
# Quick validation (5 minutes)
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --test-duration-hours 0.0833 \
  --checkpoint-interval-seconds 30 \
  --qps 5

# Short endurance (1 hour)
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --test-duration-hours 1 \
  --qps 10

# Medium endurance (6 hours)
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --test-duration-hours 6 \
  --qps 10

# Full endurance (12 hours)
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --test-duration-hours 12 \
  --qps 10

# Extended stress test (24 hours)
./run_multiple_real_workloads.sh \
  --enable-endurance-mode True \
  --test-duration-hours 24 \
  --qps 50 \
  --qps-distribution exponential
```

## Technical Details

### Rolling Statistics Implementation

The endurance evaluator uses two techniques to maintain bounded memory:

1. **Welford's Online Algorithm** for mean and variance:
   - Incremental calculation without storing all values
   - Numerically stable for large datasets
   - O(1) memory per metric

2. **Reservoir Sampling** for quantiles:
   - Maintains random sample of 10K values
   - Provides approximate quantiles (within 1% error)
   - O(k) memory where k=10,000

### Checkpoint Format

Checkpoints store:
- Test configuration (QPS, duration, model, etc.)
- Progress counters (requests completed/started)
- Rolling statistics state (Welford state + reservoir samples)
- Timestamps (start, last checkpoint)

Total checkpoint size: ~1 MB (mostly from reservoir samples)

### Atomic Writes

Checkpoints use atomic write pattern:
1. Write to temporary file: `checkpoint_{uuid}.tmp`
2. Atomic rename: `mv checkpoint_{uuid}.tmp checkpoint_{uuid}.json`
3. Ensures no partial/corrupted checkpoints

### File Locking

Prevents corruption from concurrent writes:
- Uses `filelock` library
- Timeout: 10 seconds
- Lock file: `checkpoint_{uuid}.lock`

### Network Error Handling

Automatically retries requests on network failures:
- Max retries: 3 attempts
- Exponential backoff: 1s, 2s, 4s
- Detects: connection errors, timeouts, network unreachable, connection reset
- Critical for recovering from system sleep/wake cycles
- Failed requests are logged and recorded in error metrics

### System Sleep Prevention (macOS)

Uses `caffeinate` to prevent system sleep:
- Command: `caffeinate -i` (prevents idle sleep)
- Enabled by default for endurance tests
- Automatically detects macOS
- Falls back gracefully if caffeinate not available
- Can be disabled with `--prevent-sleep False`
