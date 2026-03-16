# Poisson-Based Realistic Load Generation - Implementation Plan

## Overview

Simulate realistic server load patterns using Poisson processes where:
- **Number of concurrent users varies over time** (Poisson distribution)
- **Per-user request rate varies** (Poisson distribution)
- **Users come and go dynamically** (not fixed 12-hour sessions)
- **System sees continuous, variable load** (realistic stress testing)

This models real-world traffic patterns where load fluctuates naturally rather than artificial fixed-user scenarios.

## Key Insight: Queueing Theory Model

We're implementing an **M/M/∞ queueing system**:
- **Arrivals**: User arrivals follow Poisson process with rate λ_users
- **Service**: Per-user request generation follows Poisson with rate λ_qps
- **Servers**: Infinite (system can handle unbounded users)
- **Result**: Natural load variability mimicking production

## Architecture Design

### High-Level Flow

```
PoissonLoadGenerator (Orchestrator)
    ↓
[Time t=0] → Sample: 12 users active
    → Spawn 12 user processes
    → Each with Poisson(λ_qps) request rate
    ↓
[Time t=60s] → Sample: 15 users active
    → Spawn 3 new users
    → Existing users continue
    ↓
[Time t=120s] → Sample: 10 users active
    → Kill 5 users (random selection or oldest)
    → Remaining users continue
    ↓
[Time t=180s] → Sample: 13 users active
    → Spawn 3 new users
    ...continues for 12 hours...
```

### Load Model

```python
# At each time step (e.g., every 60 seconds):

1. Sample number of active users from Poisson(λ_users)
   num_users = poisson(λ_users)

2. For each new user:
   - Sample their QPS from Poisson(λ_qps_per_user)
   - Sample their session duration from Exponential(μ_session)
   - Spawn user process with these parameters

3. For existing users:
   - Check if session expired
   - If expired, gracefully terminate
   - If not, continue generating requests

4. Result: Variable concurrent load on server
   Total QPS ≈ num_users × avg_qps_per_user
```

## Mathematical Model

### Parameters

**User Arrival/Concurrency:**
- `λ_users` (lambda users): Average concurrent users
  - Example: λ_users = 50 → average 50 concurrent users
  - Actual: Varies according to Poisson(50) → [30, 70] typical range

**Per-User Request Rate:**
- `λ_qps` (lambda QPS): Average requests per second per user
  - Example: λ_qps = 2 → average 2 QPS per user
  - Actual: Varies according to Poisson(2) → [0, 5] typical range

**User Session Duration:**
- `μ_session` (mu session): Average session length in seconds
  - Example: μ_session = 300s (5 minutes)
  - Distribution: Exponential(μ_session)
  - Result: Some users 30s, some 600s, average 300s

**Resulting System Load:**
- Expected total QPS = λ_users × λ_qps
  - Example: 50 users × 2 QPS = 100 QPS average
  - Variance: Significant! Can spike to 150+ or drop to 50

### Time-Varying Load Patterns

**Simulate Daily Patterns:**
```python
def get_lambda_users(hour_of_day):
    """Model daily traffic patterns"""
    if 0 <= hour < 6:    # Night: low traffic
        return 20
    elif 6 <= hour < 9:  # Morning: ramp up
        return 50
    elif 9 <= hour < 17: # Business hours: peak
        return 100
    elif 17 <= hour < 22: # Evening: medium
        return 60
    else:                # Late night: low
        return 30
```

**Simulate Load Spikes:**
```python
def get_lambda_with_spikes(base_lambda, time_elapsed):
    """Add occasional load spikes"""
    # Random spike every ~2 hours
    if random.random() < 0.01:  # 1% chance per minute
        return base_lambda * 3  # 3x spike
    return base_lambda
```

## Configuration Schema

### YAML Configuration

```yaml
# poisson_load_config.yaml

load_config:
  test_duration_hours: 12
  checkpoint_interval_seconds: 300
  results_dir: "./poisson_load_results"

  # User arrival/concurrency parameters
  user_concurrency:
    lambda_users: 50              # Average concurrent users
    distribution: "poisson"

    # Time-varying pattern (optional)
    time_pattern:
      enabled: true
      pattern_type: "daily"       # daily, custom, constant
      daily_pattern:
        night: 20      # 00:00-06:00
        morning: 50    # 06:00-09:00
        peak: 100      # 09:00-17:00
        evening: 60    # 17:00-22:00
        late: 30       # 22:00-24:00

  # Per-user request rate parameters
  user_request_rate:
    lambda_qps: 2.0               # Average QPS per user
    distribution: "poisson"
    min_qps: 0.1                  # Floor (prevent 0 QPS)
    max_qps: 20                   # Ceiling (prevent outliers)

  # User session lifecycle
  user_session:
    duration_distribution: "exponential"
    mean_duration_seconds: 300    # Average 5 minutes
    min_duration_seconds: 30      # Minimum 30 seconds
    max_duration_seconds: 1800    # Maximum 30 minutes

  # Resampling frequency
  resampling:
    user_count_interval_seconds: 60     # Resample user count every minute
    user_qps_interval_seconds: 30       # Resample per-user QPS every 30s

  # Request generation parameters
  request_params:
    num_input_tokens:
      distribution: "normal"
      mean: 1000
      std: 300
      min: 100
      max: 4000

    num_output_tokens:
      distribution: "normal"
      mean: 500
      std: 150
      min: 50
      max: 2000

    model_distribution:
      - model: "DeepSeek-V3.1"
        probability: 0.6
      - model: "Meta-Llama-3.3-70B-Instruct"
        probability: 0.3
      - model: "Meta-Llama-3.1-405B"
        probability: 0.1

  # Load spikes (optional)
  load_spikes:
    enabled: true
    spike_probability_per_minute: 0.01   # 1% chance per minute
    spike_multiplier: 3.0                # 3x normal load
    spike_duration_seconds: 300          # 5 minute spikes

  # System limits
  limits:
    max_concurrent_users: 200      # Hard cap on users
    max_total_qps: 2000           # Hard cap on total QPS
    thread_limit_per_user: 100    # Max threads per user process
```

### Simplified Configuration

```yaml
# Simple: Just specify target load
simple_load_config:
  target_avg_qps: 600           # Target average total QPS
  test_duration_hours: 12

  # Everything else uses smart defaults:
  # λ_users = 50, λ_qps = 12 → 600 QPS average
  # Session duration = 5 minutes
  # Normal distribution for token counts
```

## Implementation Components

### 1. PoissonLoadGenerator Class

**Location:** `src/poisson_load_generator.py` (new file)

```python
class PoissonLoadGenerator:
    """
    Generates realistic variable load using Poisson processes.

    Responsibilities:
    - Sample number of active users from Poisson(λ_users)
    - Spawn/kill user processes to match sampled count
    - Resample periodically to create load variability
    - Track all active users and their lifecycles
    - Coordinate checkpointing across variable users
    - Aggregate results from transient users
    """

    def __init__(self, config_file):
        self.config = self.load_config(config_file)
        self.active_users = {}  # {user_id: UserProcess}
        self.user_counter = 0
        self.start_time = None

    def sample_user_count(self, current_time=None):
        """Sample number of concurrent users from Poisson"""
        lambda_users = self.get_lambda_users(current_time)
        sampled_count = np.random.poisson(lambda_users)

        # Apply limits
        sampled_count = min(sampled_count, self.config['max_concurrent_users'])
        return max(1, sampled_count)  # At least 1 user

    def sample_user_qps(self):
        """Sample QPS for a user from Poisson"""
        lambda_qps = self.config['lambda_qps']
        sampled_qps = np.random.poisson(lambda_qps)

        # Apply bounds
        sampled_qps = max(self.config['min_qps'], sampled_qps)
        sampled_qps = min(self.config['max_qps'], sampled_qps)
        return sampled_qps

    def sample_session_duration(self):
        """Sample session duration from Exponential"""
        mean_duration = self.config['mean_duration_seconds']
        duration = np.random.exponential(mean_duration)

        # Apply bounds
        duration = max(self.config['min_duration_seconds'], duration)
        duration = min(self.config['max_duration_seconds'], duration)
        return duration

    def spawn_user(self):
        """Create new user process with sampled parameters"""
        user_id = f"user_{self.user_counter}"
        self.user_counter += 1

        # Sample user parameters
        qps = self.sample_user_qps()
        session_duration = self.sample_session_duration()
        num_input_tokens = self.sample_input_tokens()
        num_output_tokens = self.sample_output_tokens()
        model_name = self.sample_model()

        # Create user process
        user = UserProcess(
            user_id=user_id,
            qps=qps,
            session_duration=session_duration,
            num_input_tokens=num_input_tokens,
            num_output_tokens=num_output_tokens,
            model_name=model_name,
            results_dir=self.config['results_dir'],
        )

        user.start()
        self.active_users[user_id] = {
            'process': user,
            'spawn_time': time.time(),
            'expiry_time': time.time() + session_duration,
            'qps': qps,
        }

        logger.info(f"Spawned {user_id}: QPS={qps}, duration={session_duration}s")
        return user_id

    def kill_user(self, user_id):
        """Gracefully terminate user process"""
        if user_id in self.active_users:
            user_info = self.active_users[user_id]
            user_process = user_info['process']

            # Signal graceful shutdown
            user_process.stop()
            user_process.join(timeout=30)

            # Force kill if needed
            if user_process.is_alive():
                user_process.terminate()

            del self.active_users[user_id]
            logger.info(f"Terminated {user_id}")

    def adjust_user_count(self, target_count):
        """Spawn or kill users to match target count"""
        current_count = len(self.active_users)

        if current_count < target_count:
            # Spawn new users
            for _ in range(target_count - current_count):
                self.spawn_user()

        elif current_count > target_count:
            # Kill excess users (oldest first or random)
            users_to_kill = current_count - target_count
            candidates = self.select_users_to_kill(users_to_kill)
            for user_id in candidates:
                self.kill_user(user_id)

    def select_users_to_kill(self, count):
        """Select which users to terminate"""
        # Strategy: Kill oldest users first
        sorted_users = sorted(
            self.active_users.items(),
            key=lambda x: x[1]['spawn_time']
        )
        return [user_id for user_id, _ in sorted_users[:count]]

    def cleanup_expired_users(self):
        """Terminate users whose session has expired"""
        current_time = time.time()
        expired = [
            user_id for user_id, info in self.active_users.items()
            if current_time >= info['expiry_time']
        ]
        for user_id in expired:
            logger.info(f"Session expired for {user_id}")
            self.kill_user(user_id)

    def resample_user_qps(self):
        """Resample QPS for all active users"""
        for user_id, user_info in self.active_users.items():
            new_qps = self.sample_user_qps()
            user_info['process'].update_qps(new_qps)
            user_info['qps'] = new_qps
            logger.debug(f"Updated {user_id} QPS to {new_qps}")

    def get_lambda_users(self, current_time=None):
        """Get λ_users parameter (possibly time-varying)"""
        if self.config.get('time_pattern', {}).get('enabled'):
            # Time-of-day pattern
            hour = datetime.now().hour
            return self.config['time_pattern']['daily_pattern'][hour]
        else:
            # Constant
            return self.config['lambda_users']

    def check_load_spike(self):
        """Randomly trigger load spikes"""
        if not self.config.get('load_spikes', {}).get('enabled'):
            return False

        spike_prob = self.config['load_spikes']['spike_probability_per_minute'] / 60
        return random.random() < spike_prob

    def run_load_generation(self):
        """Main orchestration loop"""
        self.start_time = time.time()
        test_duration = self.config['test_duration_hours'] * 3600

        user_resample_interval = self.config['resampling']['user_count_interval_seconds']
        qps_resample_interval = self.config['resampling']['user_qps_interval_seconds']

        last_user_resample = self.start_time
        last_qps_resample = self.start_time

        # Initial user spawn
        initial_count = self.sample_user_count()
        self.adjust_user_count(initial_count)

        while time.time() - self.start_time < test_duration:
            current_time = time.time()
            elapsed = current_time - self.start_time

            # Check for load spike
            if self.check_load_spike():
                logger.warning("⚡ LOAD SPIKE TRIGGERED ⚡")
                spike_multiplier = self.config['load_spikes']['spike_multiplier']
                spike_users = self.sample_user_count() * spike_multiplier
                self.adjust_user_count(int(spike_users))
                time.sleep(self.config['load_spikes']['spike_duration_seconds'])
                # Spike ends, resample normally

            # Cleanup expired user sessions
            self.cleanup_expired_users()

            # Resample number of concurrent users
            if current_time - last_user_resample >= user_resample_interval:
                target_users = self.sample_user_count(current_time)
                logger.info(f"Resampling users: target={target_users}, current={len(self.active_users)}")
                self.adjust_user_count(target_users)
                last_user_resample = current_time

            # Resample QPS for active users
            if current_time - last_qps_resample >= qps_resample_interval:
                self.resample_user_qps()
                last_qps_resample = current_time

            # Monitor health
            self.monitor_active_users()

            # Log current state
            if elapsed % 300 == 0:  # Every 5 minutes
                self.log_system_state()

            # Sleep briefly
            time.sleep(1)

        # Test complete - cleanup all users
        logger.info("Test duration complete. Cleaning up all users...")
        for user_id in list(self.active_users.keys()):
            self.kill_user(user_id)

        # Aggregate results
        self.aggregate_results()

    def monitor_active_users(self):
        """Check health of active user processes"""
        for user_id, user_info in list(self.active_users.items()):
            if not user_info['process'].is_alive():
                logger.error(f"{user_id} died unexpectedly!")
                # Don't restart - this is realistic (users disconnect)
                del self.active_users[user_id]

    def log_system_state(self):
        """Log current system load state"""
        total_qps = sum(u['qps'] for u in self.active_users.values())
        logger.info(f"System State: {len(self.active_users)} users, {total_qps} total QPS")

        # Optional: Write to monitoring file
        state = {
            'timestamp': datetime.now().isoformat(),
            'num_users': len(self.active_users),
            'total_qps': total_qps,
            'user_details': [
                {
                    'user_id': uid,
                    'qps': info['qps'],
                    'age_seconds': time.time() - info['spawn_time']
                }
                for uid, info in self.active_users.items()
            ]
        }

        monitoring_file = Path(self.config['results_dir']) / 'load_monitoring.jsonl'
        with open(monitoring_file, 'a') as f:
            f.write(json.dumps(state) + '\n')

    def aggregate_results(self):
        """Combine results from all transient users"""
        # This is complex - users come and go
        # Need to merge all their individual JSONL files
        results_dir = Path(self.config['results_dir'])

        # Find all user result files
        user_files = results_dir.glob('user_*/endurance_*_responses.jsonl')

        # Combine into single JSONL
        combined_file = results_dir / 'combined_responses.jsonl'
        with open(combined_file, 'w') as outfile:
            for user_file in user_files:
                with open(user_file, 'r') as infile:
                    outfile.write(infile.read())

        # Calculate aggregate statistics
        aggregator = PoissonLoadAggregator(results_dir)
        aggregator.generate_summary()
```

### 2. UserProcess Class

**Location:** `src/poisson_load_generator.py`

```python
class UserProcess(multiprocessing.Process):
    """
    Short-lived user process that generates requests for a session.

    Can dynamically update QPS mid-session.
    """

    def __init__(self, user_id, qps, session_duration, **kwargs):
        super().__init__()
        self.user_id = user_id
        self.qps = multiprocessing.Value('d', qps)  # Shared double
        self.session_duration = session_duration
        self.stop_event = multiprocessing.Event()
        self.kwargs = kwargs

    def update_qps(self, new_qps):
        """Update QPS from parent process"""
        self.qps.value = new_qps

    def stop(self):
        """Signal graceful shutdown"""
        self.stop_event.set()

    def run(self):
        """Run user session"""
        # Create evaluator for this user
        evaluator = EndurancePerformanceEvaluator(
            user_name=self.user_id,
            qps=self.qps.value,
            test_duration_hours=self.session_duration / 3600,
            **self.kwargs
        )

        # Override with dynamic QPS checking
        original_get_wait = evaluator._get_wait_time

        def dynamic_wait_time():
            # Read current QPS from shared memory
            current_qps = self.qps.value
            mean_wait = 1 / current_qps
            # Apply distribution
            if evaluator.qps_distribution == 'exponential':
                return random.expovariate(1 / mean_wait)
            elif evaluator.qps_distribution == 'uniform':
                return random.uniform(0, 2 * mean_wait)
            else:
                return mean_wait

        evaluator._get_wait_time = dynamic_wait_time

        # Run test
        try:
            evaluator.run_benchmark(
                num_input_tokens=self.kwargs['num_input_tokens'],
                num_output_tokens=self.kwargs['num_output_tokens'],
                num_requests=999999,  # Ignored in endurance mode
                sampling_params={}
            )
        except Exception as e:
            logger.error(f"Error in {self.user_id}: {e}")
```

### 3. Result Aggregation

**Location:** `src/poisson_load_aggregator.py` (new file)

```python
class PoissonLoadAggregator:
    """
    Aggregate results from transient users with Poisson arrival.

    Challenges:
    - Users come and go (different start/end times)
    - Variable QPS per user
    - Need time-series analysis
    """

    def __init__(self, results_dir):
        self.results_dir = Path(results_dir)

    def load_all_responses(self):
        """Load responses from all user JSONL files"""
        all_responses = []

        for jsonl_file in self.results_dir.glob('user_*/endurance_*_responses.jsonl'):
            with open(jsonl_file, 'r') as f:
                for line in f:
                    response = json.loads(line)
                    # Add user_id from filename
                    user_id = jsonl_file.parent.name
                    response['user_id'] = user_id
                    all_responses.append(response)

        return pd.DataFrame(all_responses)

    def generate_summary(self):
        """Generate comprehensive summary"""
        df = self.load_all_responses()

        summary = {
            'test_metadata': {
                'total_users': df['user_id'].nunique(),
                'total_requests': len(df),
                'duration_hours': (df['end_time'].max() - df['start_time'].min()) / 3600,
            },
            'aggregate_metrics': self.calculate_aggregate_metrics(df),
            'time_series': self.generate_time_series(df),
            'load_distribution': self.analyze_load_distribution(df),
        }

        # Write summary
        summary_file = self.results_dir / 'poisson_load_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

    def calculate_aggregate_metrics(self, df):
        """Calculate system-wide metrics"""
        # Filter successful requests
        success_df = df[df['error_code'].isna()]

        return {
            'total_successful_requests': len(success_df),
            'total_errors': len(df) - len(success_df),
            'error_rate': (len(df) - len(success_df)) / len(df),
            'avg_latency': success_df['client_end_to_end_latency_s'].mean(),
            'p50_latency': success_df['client_end_to_end_latency_s'].quantile(0.5),
            'p95_latency': success_df['client_end_to_end_latency_s'].quantile(0.95),
            'p99_latency': success_df['client_end_to_end_latency_s'].quantile(0.99),
            'avg_ttft': success_df['client_ttft_s'].mean(),
            'throughput_tokens_per_sec': success_df['client_output_token_per_s_per_request'].mean(),
        }

    def generate_time_series(self, df, bucket_seconds=300):
        """Generate time-bucketed metrics (5-minute buckets)"""
        df['timestamp'] = pd.to_datetime(df['start_time'], unit='s')
        df['bucket'] = df['timestamp'].dt.floor(f'{bucket_seconds}s')

        timeseries = []
        for bucket, group in df.groupby('bucket'):
            success = group[group['error_code'].isna()]
            timeseries.append({
                'timestamp': bucket.isoformat(),
                'num_requests': len(group),
                'num_users': group['user_id'].nunique(),
                'avg_latency': success['client_end_to_end_latency_s'].mean() if len(success) > 0 else None,
                'p95_latency': success['client_end_to_end_latency_s'].quantile(0.95) if len(success) > 0 else None,
                'error_rate': (len(group) - len(success)) / len(group) if len(group) > 0 else 0,
                'qps': len(group) / bucket_seconds,
            })

        return timeseries

    def analyze_load_distribution(self, df):
        """Analyze how load was distributed"""
        load_by_user = df.groupby('user_id').agg({
            'user_id': 'count',  # Renamed to num_requests
            'client_end_to_end_latency_s': 'mean',
        }).rename(columns={'user_id': 'num_requests'})

        return {
            'user_count_distribution': {
                'min': int(load_by_user['num_requests'].min()),
                'max': int(load_by_user['num_requests'].max()),
                'mean': float(load_by_user['num_requests'].mean()),
                'std': float(load_by_user['num_requests'].std()),
            },
            'top_users': load_by_user.nlargest(10, 'num_requests').to_dict(),
        }
```

## CLI Interface

### New Arguments

```python
# evaluator.py additions

parser.add_argument(
    '--enable-poisson-load',
    type=str2bool,
    default=False,
    help='Enable Poisson-based variable load generation'
)

parser.add_argument(
    '--poisson-config-file',
    type=str,
    help='Path to Poisson load configuration YAML file'
)

parser.add_argument(
    '--target-avg-qps',
    type=float,
    help='Target average total QPS (simplified config)'
)

parser.add_argument(
    '--lambda-users',
    type=float,
    help='Lambda parameter for Poisson user count distribution'
)

parser.add_argument(
    '--lambda-qps-per-user',
    type=float,
    help='Lambda parameter for Poisson per-user QPS distribution'
)
```

### Usage Examples

```bash
# Full configuration file
python src/evaluator.py \
  --mode real_workload \
  --enable-poisson-load \
  --poisson-config-file poisson_load_config.yaml \
  --results-dir "./poisson_test_1"

# Simplified - just specify target QPS
python src/evaluator.py \
  --mode real_workload \
  --enable-poisson-load \
  --target-avg-qps 600 \
  --test-duration-hours 12 \
  --results-dir "./poisson_test_2"

# Command-line parameters (no config file)
python src/evaluator.py \
  --mode real_workload \
  --enable-poisson-load \
  --lambda-users 50 \
  --lambda-qps-per-user 2 \
  --test-duration-hours 12 \
  --results-dir "./poisson_test_3"
```

### Bash Wrapper

```bash
# run_poisson_load.sh (new file)
./run_poisson_load.sh \
  --config-file poisson_load_config.yaml \
  --test-duration-hours 12
```

## Expected Load Behavior

### Example: λ_users=50, λ_qps=2

**Theoretical:**
- Average concurrent users: 50
- Average QPS per user: 2
- Average total QPS: 100
- Variance: Significant!

**Observed (simulated):**
```
[00:00] 48 users, 96 QPS   (3 light users, 45 normal)
[00:01] 52 users, 104 QPS  (5 heavy users!)
[00:02] 45 users, 90 QPS   (5 users left)
[00:03] 51 users, 102 QPS  (6 users joined)
[00:04] 73 users, 146 QPS  (⚡ SPIKE!)
[00:05] 49 users, 98 QPS   (spike ended)
...
```

**Characteristics:**
- Natural variability (80-120 QPS range)
- Occasional spikes (150+ QPS)
- User churn (users come/go every minute)
- Realistic stress testing

## Monitoring & Visualization

### Real-Time Monitoring

```bash
# Monitor load in real-time
python tools/monitor_poisson_load.py --results-dir ./poisson_test_1
```

**Output:**
```
Poisson Load Test - Live Monitor
=================================
Elapsed: 2h 15m / 12h (18.75%)

Current State (last 1 minute):
- Active Users: 52
- Total QPS: 104
- Avg Latency: 0.678s

Load Over Time (5-min buckets):
┌────────┬───────┬─────┬──────────┬──────────┐
│ Time   │ Users │ QPS │ Latency  │ Errors   │
├────────┼───────┼─────┼──────────┼──────────┤
│ 02:10  │ 48    │ 96  │ 0.654s   │ 0.1%     │
│ 02:15  │ 52    │ 104 │ 0.678s   │ 0.2%     │
└────────┴───────┴─────┴──────────┴──────────┘

Load Distribution (current):
● Light users (QPS 0-1): 12
● Medium users (QPS 1-3): 35
● Heavy users (QPS 3+): 5

System Resources:
- Total Threads: 8,400
- Memory: 420 MB
- Disk: 2.3 GB
```

### Post-Test Visualization

```python
# Generate plots
python tools/plot_poisson_results.py --results-dir ./poisson_test_1
```

**Plots Generated:**
1. **User Count Over Time**: Shows Poisson variability
2. **Total QPS Over Time**: System load fluctuation
3. **Latency Distribution**: Per-quantile over time
4. **Load Heatmap**: Users × Time
5. **User Session Distribution**: Session length histogram

## Advantages Over Fixed-User Approach

### Realism
- ✅ Mimics production traffic patterns
- ✅ Natural load variability
- ✅ User churn (connect/disconnect)
- ✅ Organic load spikes

### Stress Testing
- ✅ Tests system under variable load
- ✅ Finds performance degradation patterns
- ✅ Validates autoscaling behavior
- ✅ Tests resource contention

### Flexibility
- ✅ Time-of-day patterns
- ✅ Load spikes
- ✅ Configurable distributions
- ✅ Realistic user behavior

## Mathematical Properties

### Expected Values

**With λ_users=50, λ_qps=2:**
- E[concurrent users] = λ_users = 50
- E[QPS per user] = λ_qps = 2
- E[total QPS] = λ_users × λ_qps = 100

**Variance:**
- Var[concurrent users] = λ_users = 50
- Var[QPS per user] = λ_qps = 2
- Var[total QPS] ≈ λ_users × λ_qps + λ_users × λ_qps² ≈ 300

**Coefficient of Variation:**
- CV[total QPS] = √300 / 100 ≈ 17%
- Result: QPS varies ±17% naturally

### Load Range

**95% Confidence Interval (2 std dev):**
- Total QPS range: 100 ± 2√300 ≈ [65, 135]
- This is realistic variability!

## Implementation Timeline

### Week 1: Core Infrastructure
- [x] Day 1-2: PoissonLoadGenerator class
- [x] Day 3-4: UserProcess with dynamic QPS
- [x] Day 5: Poisson sampling functions

### Week 2: Integration & Testing
- [x] Day 1-2: CLI integration
- [x] Day 3-4: Result aggregation
- [x] Day 5: Simple tests (2-5 users)

### Week 3: Advanced Features
- [x] Day 1-2: Time-varying patterns
- [x] Day 3: Load spikes
- [x] Day 4-5: Monitoring tools

### Week 4: Validation & Docs
- [x] Day 1-2: Scale testing (50+ users)
- [x] Day 3: Full 12-hour test
- [x] Day 4-5: Documentation

## Testing Strategy

### Phase 1: Basic Poisson (2 hours)
```yaml
lambda_users: 5
lambda_qps: 2
test_duration_hours: 2
```
**Goal:** Validate Poisson sampling works

### Phase 2: Realistic Load (4 hours)
```yaml
lambda_users: 20
lambda_qps: 5
test_duration_hours: 4
```
**Goal:** Test variable load handling

### Phase 3: High Variability (6 hours)
```yaml
lambda_users: 50
lambda_qps: 10
load_spikes: enabled
test_duration_hours: 6
```
**Goal:** Stress test with spikes

### Phase 4: Full Endurance (12 hours)
```yaml
lambda_users: 50
lambda_qps: 12
time_pattern: enabled (daily)
test_duration_hours: 12
```
**Goal:** Production readiness

## File Structure

```
benchmarking/
├── src/
│   ├── poisson_load_generator.py    # NEW: Main orchestrator
│   ├── poisson_load_aggregator.py   # NEW: Result aggregation
│   ├── performance_evaluation.py    # MODIFIED: Add user_name support
│   └── evaluator.py                 # MODIFIED: Add Poisson mode
│
├── configs/
│   ├── poisson_simple.yaml         # NEW: Simple config
│   ├── poisson_realistic.yaml      # NEW: Realistic traffic
│   ├── poisson_stress.yaml         # NEW: High load + spikes
│   └── poisson_daily_pattern.yaml  # NEW: Time-of-day variation
│
├── tools/
│   ├── monitor_poisson_load.py     # NEW: Real-time monitoring
│   ├── plot_poisson_results.py     # NEW: Visualizations
│   └── analyze_poisson_load.py     # NEW: Statistical analysis
│
├── run_poisson_load.sh             # NEW: Bash wrapper
├── POISSON_LOAD_GUIDE.md           # NEW: User guide
└── POISSON_LOAD_PLAN.md            # THIS FILE
```

## Summary

This Poisson-based approach provides:

✅ **Realistic Traffic**: Variable users, variable QPS, natural patterns
✅ **True Stress Testing**: System sees continuous, unpredictable load
✅ **Mathematically Grounded**: Based on queueing theory (M/M/∞)
✅ **Flexible**: Time patterns, spikes, configurable distributions
✅ **Observable**: Rich monitoring and analysis tools

**Key Insight**: Focus on system load, not user lifecycle. Users are transient, load is continuous.

**Estimated Implementation:** 3-4 weeks, ~2,000 lines of code + tests + docs

Ready to implement? Any questions or adjustments to this plan?
