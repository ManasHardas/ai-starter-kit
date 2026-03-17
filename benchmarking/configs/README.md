# Poisson Load Configuration Files

This directory contains example configuration files for Poisson-based variable load testing.

## Available Configurations

### Quick Test (`poisson_load_quick_test.yaml`)
**Duration:** 5 minutes
**Purpose:** Fast validation and testing
**Load:** 1-4 concurrent users, ~2 total QPS
**Use case:** Verify setup, test new features, quick sanity checks

```bash
python src/evaluator.py \
  --mode poisson_load \
  --config configs/poisson_load_quick_test.yaml
```

### Basic Load (`poisson_load_basic.yaml`)
**Duration:** 1 hour
**Purpose:** Light to moderate load testing
**Load:** 1-8 concurrent users (avg 4), ~8 total QPS
**Use case:** Initial performance baseline, development testing

```bash
python src/evaluator.py \
  --mode poisson_load \
  --config configs/poisson_load_basic.yaml
```

### Stress Test (`poisson_load_stress.yaml`)
**Duration:** 2 hours
**Purpose:** High load with traffic spikes
**Load:** 5-30 concurrent users (avg 15), ~120 total QPS
**Features:**
- 3x load spike at 30 minutes (5 minutes duration)
- 2x load spike at 1 hour (10 minutes duration)
- Higher token counts (2000 input, 1000 output)

**Use case:** Stress testing, capacity planning, spike handling

```bash
python src/evaluator.py \
  --mode poisson_load \
  --config configs/poisson_load_stress.yaml
```

### Endurance Test (`poisson_load_endurance.yaml`)
**Duration:** 12 hours
**Purpose:** Sustained production-like load
**Load:** 2-20 concurrent users (avg 8), ~24 total QPS
**Features:**
- Time-varying patterns (daily cycles)
- Morning ramp-up (50% load)
- Peak hours (150% load)
- Evening decline (70% load)
- Periodic load spikes throughout test

**Use case:** Long-term stability, memory leak detection, production simulation

```bash
python src/evaluator.py \
  --mode poisson_load \
  --config configs/poisson_load_endurance.yaml
```

## Configuration Structure

Each YAML configuration file contains:

### Test Configuration
- `test_duration_hours`: Total test duration
- `results_dir`: Output directory for results

### User Arrival Pattern
```yaml
user_count:
  type: "poisson"
  lambda_users: 4.0        # Average concurrent users
  min_users: 1
  max_users: 8
  resample_interval_seconds: 60  # How often to resample
```

### Per-User Request Rate
```yaml
user_qps:
  type: "poisson"
  lambda_qps: 2.0          # Average QPS per user
  min_qps: 0.5
  max_qps: 5.0
  resample_interval_seconds: 30
```

### Session Duration
```yaml
session_duration:
  type: "exponential"
  mean_duration_seconds: 300
  min_duration_seconds: 60
  max_duration_seconds: 900
```

### Request Configuration
```yaml
request:
  num_input_tokens: 1000
  num_output_tokens: 500
  models:
    - "DeepSeek-V3.1"
    - "Meta-Llama-3.3-70B-Instruct"
  input_token_variation: 0.2   # ±20%
  output_token_variation: 0.2
```

### Load Spikes (Optional)
```yaml
load_spikes:
  enabled: true
  spikes:
    - time_offset_seconds: 1800  # 30 minutes
      spike_multiplier: 3.0      # 3x normal load
      duration_seconds: 300      # 5 minutes
```

### Time-Varying Patterns (Optional)
```yaml
time_varying_pattern:
  enabled: true
  patterns:
    - name: "peak_hours"
      start_hour: 2.0
      end_hour: 6.0
      lambda_multiplier: 1.5   # 150% of base load
```

## Creating Custom Configurations

To create a custom configuration:

1. Copy an existing config as a starting point
2. Adjust parameters to match your needs
3. Calculate expected total QPS:
   ```
   Total QPS ≈ lambda_users × lambda_qps
   ```
4. Consider memory and thread limits:
   - Max concurrent users × max QPS per user = peak load
   - System can handle ~1200 QPS reliably

5. Test with quick validation first:
   ```bash
   # Set test_duration_hours: 0.0833 (5 minutes)
   # Verify everything works before long tests
   ```

## Tips

**For stable load:**
- Use higher `mean_duration_seconds` (longer sessions)
- Use longer `resample_interval_seconds` (slower changes)
- Set narrow min/max ranges

**For variable load:**
- Use lower `mean_duration_seconds` (more churn)
- Use shorter `resample_interval_seconds` (faster changes)
- Set wide min/max ranges

**For realistic production:**
- Use time-varying patterns to simulate daily cycles
- Add occasional load spikes (1.5-2x for 5-10 minutes)
- Mix multiple models
- Add token variation (20-30%)

## Load Estimation

| Config | Avg Users | Avg QPS/User | Total QPS | Thread Workers | Memory |
|--------|-----------|--------------|-----------|----------------|---------|
| Quick Test | 2 | 1.0 | 2 | 100 | ~50 MB |
| Basic | 4 | 2.0 | 8 | 100 | ~50 MB |
| Stress | 15 | 8.0 | 120 | 360 | ~100 MB |
| Endurance | 8 | 3.0 | 24 | 100 | ~80 MB |

Memory usage includes all user processes combined.

## Validation Checklist

Before running a new configuration:

- [ ] Total QPS within system limits (<1200)
- [ ] Results directory path exists or can be created
- [ ] All model names are valid
- [ ] Token counts are appropriate for models
- [ ] Spike times are within test duration
- [ ] Time-varying pattern hours sum to test duration
- [ ] Checkpoint intervals are reasonable

## Troubleshooting

**Too many users spawned:**
- Reduce `lambda_users`
- Reduce `max_users`
- Increase `min_duration_seconds` (reduce churn)

**System overload:**
- Reduce `lambda_qps`
- Reduce `lambda_users`
- Increase `resample_interval_seconds` (slower changes)

**Not enough variability:**
- Increase min/max ranges
- Decrease `resample_interval_seconds`
- Decrease `mean_duration_seconds` (more churn)
- Enable load spikes
