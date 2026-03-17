# Poisson Load Test Results Guide

## Overview

Poisson load tests generate **system-wide aggregate results** that show how your server performs under variable, realistic traffic patterns. Unlike individual user metrics, these results focus on overall system stress and performance.

## Output Files

After a Poisson load test completes, you'll find these files in your results directory:

```
./data/results/llmperf/poisson_load_<test_name>/
├── poisson_config.json                          # Test configuration
├── poisson_load_aggregate_summary.json          # Detailed JSON results
├── poisson_load_aggregate_report.txt            # Human-readable summary
├── load_monitoring.jsonl                        # Real-time load state logs
└── user_user_XXXXXX/                           # Individual user directories (for debugging)
    └── endurance_*_individual_responses.jsonl  # Per-user responses
```

## Key Result Files

### 1. Aggregate Report (`poisson_load_aggregate_report.txt`)

**Quick summary for humans.** Example:

```
================================================================================
POISSON LOAD TEST AGGREGATE REPORT
================================================================================

Test Duration: 1.00 hours
Total Requests: 14,523
Successful: 14,445
Failed: 78
Error Rate: 0.54%
Average QPS: 4.03

LATENCY METRICS:
  TTFT - Mean: 0.234s, P95: 0.450s, P99: 0.680s
  E2E  - Mean: 1.456s, P95: 2.340s, P99: 3.120s

THROUGHPUT METRICS:
  Output - Mean: 156.3 tok/s
  Total  - Mean: 178.5 tok/s

USER DISTRIBUTION (12 total users):
   1. user_000045: 1,234 requests, 0.34 QPS, 3,600s session
   2. user_000023: 1,102 requests, 0.31 QPS, 3,543s session
   ...
================================================================================
```

**What this tells you:**
- **System-level performance:** How the server handled the aggregate load
- **Error rate:** Overall system reliability under stress
- **Latency distribution:** P95/P99 show tail latencies experienced by users
- **Load distribution:** How requests were spread across concurrent users

### 2. Aggregate Summary (`poisson_load_aggregate_summary.json`)

**Detailed JSON for analysis tools.** Contains:

#### Configuration Section
```json
{
  "configuration": {
    "load_config": {
      "test_duration_hours": 1.0,
      "user_concurrency": {
        "lambda_users": 4.0,
        "min_users": 1,
        "max_users": 8
      },
      "user_request_rate": {
        "lambda_qps": 2.0,
        "min_qps": 0.5,
        "max_qps": 5.0
      }
    }
  }
}
```

#### Aggregate Metrics Section
```json
{
  "aggregate_metrics": {
    "total_requests": 14523,
    "successful_requests": 14445,
    "failed_requests": 78,
    "error_rate": 0.0054,
    "test_duration_hours": 1.0,
    "average_qps": 4.03,

    "ttft_s": {
      "mean": 0.234,
      "stddev": 0.045,
      "min": 0.100,
      "max": 0.850,
      "p50": 0.220,
      "p75": 0.280,
      "p90": 0.350,
      "p95": 0.450,
      "p99": 0.680
    },

    "end_to_end_latency_s": {
      "mean": 1.456,
      "stddev": 0.234,
      "p50": 1.420,
      "p95": 2.340,
      "p99": 3.120
    }
  }
}
```

#### Time-Series Analysis Section
```json
{
  "time_series_analysis": {
    "bucket_size_seconds": 300,
    "num_buckets": 12,
    "buckets": [
      {
        "start_time": 1678901234.5,
        "end_time": 1678901534.5,
        "num_requests": 1250,
        "num_users": 4,
        "avg_qps": 4.17,
        "total_errors": 3,
        "avg_ttft": 0.240,
        "p95_ttft": 0.460,
        "avg_e2e_latency": 1.480,
        "p95_e2e_latency": 2.380
      }
      // ... more buckets ...
    ]
  }
}
```

**Use this for:**
- Graphing latency trends over time
- Identifying load spikes and their impact
- Analyzing how performance degrades under increased load

#### User Distribution Section
```json
{
  "user_distribution": {
    "total_users": 12,
    "users": [
      {
        "user_id": "user_000045",
        "num_requests": 1234,
        "avg_qps": 0.34,
        "session_duration": 3600,
        "avg_ttft": 0.238,
        "p95_ttft": 0.455,
        "avg_e2e_latency": 1.462,
        "num_errors": 5
      }
      // ... more users ...
    ]
  }
}
```

**Use this for:**
- Understanding load distribution across users
- Identifying if certain users experienced worse performance
- Debugging outliers

#### Load Profile Section
```json
{
  "load_profile": {
    "avg_qps": 4.03,
    "min_qps": 1.2,
    "max_qps": 8.7,
    "stddev_qps": 1.45,
    "qps_variability_coefficient": 0.36,

    "avg_concurrent_users": 3.8,
    "min_concurrent_users": 1,
    "max_concurrent_users": 7
  }
}
```

**Use this for:**
- Understanding load variability (high variability = more realistic)
- Comparing test configuration vs actual load achieved

## Interpreting Results

### Stress Testing Focus

These results answer:
- ✅ **Can the server handle X QPS under variable load?**
- ✅ **What's the P95/P99 latency users experience at this load?**
- ✅ **How does error rate change with concurrent users?**
- ✅ **Does performance degrade over long duration (12+ hours)?**

These results DO NOT answer:
- ❌ Individual user experience (use individual JSONL files if needed)
- ❌ Why specific requests failed (check individual response logs)

### Key Metrics to Monitor

#### 1. **Error Rate**
- **Good:** < 1%
- **Warning:** 1-5%
- **Critical:** > 5%

High error rates indicate the server is overloaded.

#### 2. **P95/P99 Latencies**
- Compare to SLAs (e.g., "95% of requests < 2s")
- P99 shows worst-case user experience
- Large gap between mean and P99 = high variability

#### 3. **Average QPS**
- Compare to target QPS from config
- Lower than expected = server can't keep up
- Monitor with `qps_variability_coefficient` (higher = more realistic traffic)

#### 4. **Time-Series Trends**
- Look for degradation over time (memory leaks, resource exhaustion)
- Check impact of load spikes on latency
- Identify patterns (e.g., every 5min spike = GC pause?)

### Example Analysis

**Scenario:** 12-hour endurance test with λ_users=8, λ_qps=3 (target ~24 total QPS)

**Good Result:**
```
Total Requests: 1,036,800  (24 QPS × 12h × 3600s)
Error Rate: 0.2%
Average QPS: 23.8
P95 E2E Latency: 1.8s  (consistent throughout)
Max Concurrent Users: 15  (reasonable variation)
```
✅ Server handled target load with low errors and stable latency

**Bad Result:**
```
Total Requests: 432,000  (only 10 QPS achieved vs 24 target!)
Error Rate: 15.3%
Average QPS: 10.0  (less than half target)
P95 E2E Latency: 8.5s  (degraded over time)
Time-series: Latency increases linearly after hour 4
```
❌ Server overloaded, couldn't sustain target QPS, possible memory leak

## Real-Time Monitoring

### During Test

**Watch load state logs:**
```bash
tail -f ./data/results/llmperf/<test_name>/load_monitoring.jsonl
```

Each line shows:
```json
{
  "timestamp": "2024-03-16T20:30:45Z",
  "elapsed_seconds": 1234,
  "num_users": 5,
  "total_qps": 8.5,
  "user_details": [
    {"user_id": "user_000003", "qps": 2.0, "age_seconds": 456, "remaining_seconds": 123}
  ]
}
```

**Monitor aggregate progress:**
```bash
# Count total requests so far
find ./data/results/llmperf/<test_name> -name "*.jsonl" -exec wc -l {} + | tail -1

# Watch user count
ls -d ./data/results/llmperf/<test_name>/user_* | wc -l
```

### After Test

**Quick validation:**
```bash
# View text report
cat ./data/results/llmperf/<test_name>/poisson_load_aggregate_report.txt

# Extract key metrics
cat ./data/results/llmperf/<test_name>/poisson_load_aggregate_summary.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  m=d['aggregate_metrics']; \
  print(f\"Total Requests: {m['total_requests']:,}\"); \
  print(f\"Error Rate: {m['error_rate']*100:.2f}%\"); \
  print(f\"Avg QPS: {m.get('average_qps', 0):.2f}\"); \
  print(f\"P95 E2E: {m['end_to_end_latency_s']['p95']:.3f}s\")"
```

## Comparison with Standard Benchmarking

| Feature | Standard Benchmarking | Poisson Load Testing |
|---------|----------------------|----------------------|
| **Load Pattern** | Fixed users, constant QPS | Variable users, variable QPS |
| **Duration** | 10-30 minutes | 1-12+ hours |
| **Realism** | Synthetic | Production-like |
| **Use Case** | Quick capacity check | Endurance stress testing |
| **Memory** | Accumulates all results | Streaming (bounded memory) |
| **Results** | Per-request details | System-wide aggregates |

## Tips

### Choosing Test Parameters

**For stress testing:**
- Start with `lambda_users` = target_concurrent_users / 2
- Start with `lambda_qps` = target_total_qps / lambda_users
- Increase gradually until you see > 1% error rate (that's your limit)

**For endurance testing:**
- Use moderate load (50-70% of capacity)
- Run for 12+ hours
- Look for degradation over time (memory leaks, connection exhaustion)

**For spike testing:**
- Enable `load_spikes` in config
- Set `spike_multiplier: 2-3`
- Monitor P99 latency during spike

### Analyzing Failures

If you see high error rates:

1. **Check time-series:** Do errors correlate with high QPS periods?
2. **Check user distribution:** Are errors concentrated in specific users?
3. **Check individual JSONL files:** Look at actual error messages
4. **Monitor server logs:** CPU, memory, connection count during test

### Comparing Tests

When comparing multiple runs:

```bash
for dir in ./data/results/llmperf/poisson_*/; do
  echo "=== $(basename $dir) ==="
  cat $dir/poisson_load_aggregate_report.txt | grep -A 5 "Total Requests"
  echo ""
done
```

## Automated Analysis

You can process the JSON results programmatically:

```python
import json

with open('poisson_load_aggregate_summary.json') as f:
    results = json.load(f)

metrics = results['aggregate_metrics']

# SLA checks
assert metrics['error_rate'] < 0.01, "Error rate > 1%!"
assert metrics['end_to_end_latency_s']['p95'] < 2.0, "P95 latency > 2s!"

# Load verification
config = results['configuration']['load_config']
expected_qps = config['user_concurrency']['lambda_users'] * config['user_request_rate']['lambda_qps']
actual_qps = metrics.get('average_qps', 0)
assert actual_qps >= expected_qps * 0.9, f"Only achieved {actual_qps:.1f} QPS vs {expected_qps:.1f} target!"

print("✅ All SLA checks passed!")
```

## Troubleshooting

### No aggregate files created

Check that test completed successfully:
```bash
ls -la ./data/results/llmperf/<test_name>/
# Should see poisson_load_aggregate_summary.json and poisson_load_aggregate_report.txt
```

If missing, the test may have crashed before aggregation. Check for error logs.

### Empty or zero metrics

All requests failed (error_rate = 100%). Check:
- API credentials in `.env`
- Model name in config
- Network connectivity
- First error message in any `*_individual_responses.jsonl` file

### Low QPS achieved

Server couldn't keep up with target load:
- Reduce `lambda_users` or `lambda_qps`
- Check server CPU/memory during test
- Increase `timeout` if requests are timing out

### High memory usage

- Ensure `enable-endurance-mode` is True
- Check that JSONL files are growing (not buffered)
- Monitor with: `ps aux | grep evaluator.py`

## Examples

See `/configs/README.md` for example configurations and expected results for different test scenarios.
