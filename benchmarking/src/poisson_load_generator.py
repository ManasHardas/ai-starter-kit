"""
Poisson-based realistic load generation for stress testing.

This module implements variable, realistic server load using Poisson processes where:
- Number of concurrent users varies over time (Poisson distribution)
- Per-user request rate varies (Poisson distribution)
- Users come and go dynamically (exponential session durations)
- System sees continuous, variable load (production-like)
"""

import json
import logging
import multiprocessing
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml

from benchmarking.src.performance_evaluation import EndurancePerformanceEvaluator

logger = logging.getLogger(__name__)


class UserProcess(multiprocessing.Process):
    """
    Short-lived user process that generates requests for a session.

    Simulates a single user with:
    - Dynamic QPS (can be updated mid-session)
    - Finite session duration
    - Independent request generation
    """

    def __init__(
        self,
        user_id: str,
        qps: float,
        session_duration: float,
        num_input_tokens: int,
        num_output_tokens: int,
        model_name: str,
        results_dir: str,
        qps_distribution: str = 'constant',
        checkpoint_interval_seconds: int = 300,
        checkpoint_interval_requests: int = 1000,
        llm_api: str = 'sncloud',
    ):
        """
        Initialize user process.

        Args:
            user_id: Unique user identifier
            qps: Initial queries per second for this user
            session_duration: How long this user session lasts (seconds)
            num_input_tokens: Input tokens per request
            num_output_tokens: Output tokens per request
            model_name: Model to query
            results_dir: Directory for results
            qps_distribution: Distribution for request timing
            checkpoint_interval_seconds: Seconds between checkpoints
            checkpoint_interval_requests: Requests between checkpoints
            llm_api: API to use
        """
        super().__init__()
        self.user_id = user_id
        self.qps = multiprocessing.Value('d', qps)  # Shared double for dynamic updates
        self.session_duration = session_duration
        self.num_input_tokens = num_input_tokens
        self.num_output_tokens = num_output_tokens
        self.model_name = model_name
        self.results_dir = results_dir
        self.qps_distribution = qps_distribution
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.checkpoint_interval_requests = checkpoint_interval_requests
        self.llm_api = llm_api
        self.stop_event = multiprocessing.Event()

        # User-specific results directory
        self.user_results_dir = os.path.join(results_dir, f'user_{user_id}')

    def update_qps(self, new_qps: float):
        """
        Update QPS from parent process (dynamic adjustment).

        Args:
            new_qps: New QPS value
        """
        with self.qps.get_lock():
            self.qps.value = new_qps

    def stop(self):
        """Signal graceful shutdown."""
        self.stop_event.set()

    def run(self):
        """Run user session with dynamic QPS."""
        try:
            logger.info(f"Starting {self.user_id}: QPS={self.qps.value}, duration={self.session_duration}s")

            # Create user-specific evaluator
            evaluator = EndurancePerformanceEvaluator(
                user_name=self.user_id,
                multimodal_image_size='na',  # Required parameter
                model_name=self.model_name,
                results_dir=self.user_results_dir,
                qps=self.qps.value,
                qps_distribution=self.qps_distribution,
                test_duration_hours=self.session_duration / 3600,
                checkpoint_interval_seconds=self.checkpoint_interval_seconds,
                checkpoint_interval_requests=self.checkpoint_interval_requests,
                enable_resume=False,  # Poisson users don't resume
                llm_api=self.llm_api,
                timeout=600,
                user_metadata={'user_type': 'poisson_user', 'model_idx': 0},
                use_debugging_mode=False,
            )

            # Override _get_wait_time to read dynamic QPS
            original_get_wait = evaluator._get_wait_time

            def dynamic_wait_time():
                """Get wait time based on current QPS from shared memory."""
                with self.qps.get_lock():
                    current_qps = self.qps.value

                if current_qps <= 0:
                    return 1.0  # Default 1 second if QPS is invalid

                mean_wait = 1 / current_qps

                # Apply distribution
                if evaluator.qps_distribution == 'exponential':
                    return random.expovariate(1 / mean_wait)
                elif evaluator.qps_distribution == 'uniform':
                    return random.uniform(0, 2 * mean_wait)
                else:  # constant
                    return mean_wait

            evaluator._get_wait_time = dynamic_wait_time

            # Run benchmark for session duration
            evaluator.run_benchmark(
                num_input_tokens=self.num_input_tokens,
                num_output_tokens=self.num_output_tokens,
                num_requests=999999,  # Ignored in endurance mode (duration-based)
                sampling_params={},
            )

            logger.info(f"Completed {self.user_id}")

        except Exception as e:
            logger.error(f"Error in {self.user_id}: {e}", exc_info=True)


class PoissonLoadGenerator:
    """
    Generates realistic variable load using Poisson processes.

    Simulates production-like traffic where:
    - Number of concurrent users follows Poisson(λ_users)
    - Per-user QPS follows Poisson(λ_qps)
    - User sessions have exponential duration
    - Load varies naturally over time
    """

    def __init__(self, config_file: Optional[str] = None, config_dict: Optional[Dict] = None):
        """
        Initialize Poisson load generator.

        Args:
            config_file: Path to YAML configuration file
            config_dict: Configuration dictionary (alternative to file)
        """
        if config_file:
            self.config = self.load_config_from_file(config_file)
        elif config_dict:
            self.config = config_dict
        else:
            raise ValueError("Must provide either config_file or config_dict")

        self.active_users: Dict[str, Dict[str, Any]] = {}
        self.user_counter = 0
        self.start_time: Optional[float] = None
        self.monitoring_file: Optional[Path] = None

        # Create results directory
        results_dir = Path(self.config['load_config']['results_dir'])
        results_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = results_dir

        # Setup monitoring file
        self.monitoring_file = self.results_dir / 'load_monitoring.jsonl'

        # Save configuration for aggregator
        config_path = self.results_dir / 'poisson_config.json'
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

        logger.info(f"Initialized PoissonLoadGenerator with λ_users={self.config['load_config']['user_concurrency']['lambda_users']}")

    def load_config_from_file(self, config_file: str) -> Dict:
        """
        Load configuration from YAML file.

        Args:
            config_file: Path to YAML file

        Returns:
            Configuration dictionary
        """
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config

    @staticmethod
    def create_simple_config(target_avg_qps: float, test_duration_hours: float, results_dir: str) -> Dict:
        """
        Create simplified configuration from target QPS.

        Automatically calculates λ_users and λ_qps to achieve target total QPS.

        Args:
            target_avg_qps: Target average total QPS
            test_duration_hours: Test duration in hours
            results_dir: Results directory

        Returns:
            Configuration dictionary
        """
        # Heuristic: λ_users = sqrt(target_qps * 10), λ_qps = target_qps / λ_users
        lambda_users = max(10, int(np.sqrt(target_avg_qps * 10)))
        lambda_qps = target_avg_qps / lambda_users

        return {
            'load_config': {
                'test_duration_hours': test_duration_hours,
                'checkpoint_interval_seconds': 300,
                'results_dir': results_dir,
                'user_concurrency': {
                    'lambda_users': lambda_users,
                    'distribution': 'poisson',
                    'time_pattern': {'enabled': False},
                },
                'user_request_rate': {
                    'lambda_qps': lambda_qps,
                    'distribution': 'poisson',
                    'min_qps': 0.1,
                    'max_qps': 50.0,
                },
                'user_session': {
                    'duration_distribution': 'exponential',
                    'mean_duration_seconds': 300,
                    'min_duration_seconds': 30,
                    'max_duration_seconds': 1800,
                },
                'resampling': {
                    'user_count_interval_seconds': 60,
                    'user_qps_interval_seconds': 30,
                },
                'request_params': {
                    'num_input_tokens': {'distribution': 'constant', 'value': 1000},
                    'num_output_tokens': {'distribution': 'constant', 'value': 500},
                    'model_distribution': [{'model': 'DeepSeek-V3.1', 'probability': 1.0}],
                },
                'load_spikes': {'enabled': False},
                'limits': {
                    'max_concurrent_users': 200,
                    'max_total_qps': 2000,
                },
                'llm_api': 'sncloud',
            }
        }

    def sample_user_count(self, current_time: Optional[float] = None) -> int:
        """
        Sample number of concurrent users from Poisson distribution.

        Args:
            current_time: Current time (for time-varying patterns)

        Returns:
            Number of users to have active
        """
        lambda_users = self.get_lambda_users(current_time)
        sampled_count = np.random.poisson(lambda_users)

        # Apply limits
        max_users = self.config['load_config']['limits']['max_concurrent_users']
        sampled_count = min(sampled_count, max_users)
        sampled_count = max(1, sampled_count)  # At least 1 user

        return sampled_count

    def sample_user_qps(self) -> float:
        """
        Sample QPS for a user from Poisson distribution.

        Returns:
            QPS value for user
        """
        lambda_qps = self.config['load_config']['user_request_rate']['lambda_qps']
        sampled_qps = float(np.random.poisson(lambda_qps))

        # Apply bounds
        min_qps = self.config['load_config']['user_request_rate']['min_qps']
        max_qps = self.config['load_config']['user_request_rate']['max_qps']
        sampled_qps = max(min_qps, sampled_qps)
        sampled_qps = min(max_qps, sampled_qps)

        return sampled_qps

    def sample_session_duration(self) -> float:
        """
        Sample session duration from exponential distribution.

        Returns:
            Session duration in seconds
        """
        mean_duration = self.config['load_config']['user_session']['mean_duration_seconds']
        duration = np.random.exponential(mean_duration)

        # Apply bounds
        min_duration = self.config['load_config']['user_session']['min_duration_seconds']
        max_duration = self.config['load_config']['user_session']['max_duration_seconds']
        duration = max(min_duration, duration)
        duration = min(max_duration, duration)

        return duration

    def sample_input_tokens(self) -> int:
        """
        Sample number of input tokens.

        Returns:
            Number of input tokens
        """
        token_config = self.config['load_config']['request_params']['num_input_tokens']

        if token_config['distribution'] == 'constant':
            return token_config['value']
        elif token_config['distribution'] == 'normal':
            value = int(np.random.normal(token_config['mean'], token_config['std']))
            return max(token_config['min'], min(token_config['max'], value))
        else:
            return 1000  # Default

    def sample_output_tokens(self) -> int:
        """
        Sample number of output tokens.

        Returns:
            Number of output tokens
        """
        token_config = self.config['load_config']['request_params']['num_output_tokens']

        if token_config['distribution'] == 'constant':
            return token_config['value']
        elif token_config['distribution'] == 'normal':
            value = int(np.random.normal(token_config['mean'], token_config['std']))
            return max(token_config['min'], min(token_config['max'], value))
        else:
            return 500  # Default

    def sample_model(self) -> str:
        """
        Sample model from distribution.

        Returns:
            Model name
        """
        models = self.config['load_config']['request_params']['model_distribution']
        model_names = [m['model'] for m in models]
        probabilities = [m['probability'] for m in models]

        # Normalize probabilities
        total_prob = sum(probabilities)
        probabilities = [p / total_prob for p in probabilities]

        return np.random.choice(model_names, p=probabilities)

    def get_lambda_users(self, current_time: Optional[float] = None) -> float:
        """
        Get λ_users parameter (possibly time-varying).

        Args:
            current_time: Current time for time-of-day patterns

        Returns:
            Lambda value for user count
        """
        user_config = self.config['load_config']['user_concurrency']

        if user_config.get('time_pattern', {}).get('enabled', False):
            # Time-of-day pattern
            hour = datetime.now().hour
            pattern = user_config['time_pattern'].get('daily_pattern', {})

            if 0 <= hour < 6:
                return pattern.get('night', user_config['lambda_users'])
            elif 6 <= hour < 9:
                return pattern.get('morning', user_config['lambda_users'])
            elif 9 <= hour < 17:
                return pattern.get('peak', user_config['lambda_users'])
            elif 17 <= hour < 22:
                return pattern.get('evening', user_config['lambda_users'])
            else:
                return pattern.get('late', user_config['lambda_users'])
        else:
            # Constant
            return user_config['lambda_users']

    def spawn_user(self) -> str:
        """
        Create and start a new user process with sampled parameters.

        Returns:
            User ID of spawned user
        """
        user_id = f"user_{self.user_counter:06d}"
        self.user_counter += 1

        # Sample user parameters
        qps = self.sample_user_qps()
        session_duration = self.sample_session_duration()
        num_input_tokens = self.sample_input_tokens()
        num_output_tokens = self.sample_output_tokens()
        model_name = self.sample_model()

        # Create user process
        user_process = UserProcess(
            user_id=user_id,
            qps=qps,
            session_duration=session_duration,
            num_input_tokens=num_input_tokens,
            num_output_tokens=num_output_tokens,
            model_name=model_name,
            results_dir=str(self.results_dir),
            qps_distribution='constant',  # Individual user uses constant
            checkpoint_interval_seconds=self.config['load_config']['checkpoint_interval_seconds'],
            checkpoint_interval_requests=1000,
            llm_api=self.config['load_config']['llm_api'],
        )

        user_process.start()

        # Track user
        self.active_users[user_id] = {
            'process': user_process,
            'spawn_time': time.time(),
            'expiry_time': time.time() + session_duration,
            'qps': qps,
            'model': model_name,
            'duration': session_duration,
        }

        logger.info(
            f"Spawned {user_id}: QPS={qps:.1f}, duration={session_duration:.0f}s, "
            f"tokens={num_input_tokens}/{num_output_tokens}, model={model_name}"
        )

        return user_id

    def kill_user(self, user_id: str):
        """
        Gracefully terminate user process.

        Args:
            user_id: User to terminate
        """
        if user_id not in self.active_users:
            return

        user_info = self.active_users[user_id]
        user_process = user_info['process']

        # Signal graceful shutdown
        user_process.stop()
        user_process.join(timeout=30)

        # Force kill if needed
        if user_process.is_alive():
            logger.warning(f"Force terminating {user_id}")
            user_process.terminate()
            user_process.join(timeout=5)

        # Close the process object to release resources properly
        user_process.close()

        # Remove from tracking
        age = time.time() - user_info['spawn_time']
        del self.active_users[user_id]

        logger.info(f"Terminated {user_id} (lived {age:.0f}s)")

    def adjust_user_count(self, target_count: int):
        """
        Spawn or kill users to match target count.

        Args:
            target_count: Desired number of active users
        """
        current_count = len(self.active_users)

        if current_count < target_count:
            # Spawn new users
            num_to_spawn = target_count - current_count
            logger.info(f"Spawning {num_to_spawn} new users (current: {current_count}, target: {target_count})")
            for _ in range(num_to_spawn):
                self.spawn_user()

        elif current_count > target_count:
            # Kill excess users (oldest first)
            num_to_kill = current_count - target_count
            logger.info(f"Killing {num_to_kill} users (current: {current_count}, target: {target_count})")
            users_to_kill = self.select_users_to_kill(num_to_kill)
            for user_id in users_to_kill:
                self.kill_user(user_id)

    def select_users_to_kill(self, count: int) -> List[str]:
        """
        Select which users to terminate (oldest first).

        Args:
            count: Number of users to select

        Returns:
            List of user IDs to terminate
        """
        sorted_users = sorted(self.active_users.items(), key=lambda x: x[1]['spawn_time'])
        return [user_id for user_id, _ in sorted_users[:count]]

    def cleanup_expired_users(self):
        """Terminate users whose session has expired."""
        current_time = time.time()
        expired = [
            user_id
            for user_id, info in self.active_users.items()
            if current_time >= info['expiry_time']
        ]

        if expired:
            logger.info(f"Cleaning up {len(expired)} expired user sessions")
            for user_id in expired:
                self.kill_user(user_id)

    def resample_user_qps(self):
        """Resample QPS for all active users."""
        for user_id, user_info in self.active_users.items():
            new_qps = self.sample_user_qps()
            user_info['process'].update_qps(new_qps)
            user_info['qps'] = new_qps
            logger.debug(f"Updated {user_id} QPS: {new_qps:.1f}")

    def check_load_spike(self) -> bool:
        """
        Randomly trigger load spikes.

        Returns:
            True if spike should occur
        """
        spike_config = self.config['load_config'].get('load_spikes', {})
        if not spike_config.get('enabled', False):
            return False

        spike_prob = spike_config['spike_probability_per_minute'] / 60  # Per second
        return random.random() < spike_prob

    def monitor_active_users(self):
        """Check health of active user processes and remove dead ones."""
        dead_users = []
        for user_id, user_info in self.active_users.items():
            if not user_info['process'].is_alive():
                logger.warning(f"{user_id} died unexpectedly!")
                dead_users.append(user_id)

        for user_id in dead_users:
            # Don't restart - this is realistic (users disconnect)
            # Clean up process resources
            user_process = self.active_users[user_id]['process']
            user_process.close()
            del self.active_users[user_id]

    def log_system_state(self):
        """Log current system load state to monitoring file."""
        current_time = time.time()
        total_qps = sum(u['qps'] for u in self.active_users.values())

        state = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': current_time - self.start_time if self.start_time else 0,
            'num_users': len(self.active_users),
            'total_qps': total_qps,
            'user_details': [
                {
                    'user_id': uid,
                    'qps': info['qps'],
                    'age_seconds': current_time - info['spawn_time'],
                    'remaining_seconds': info['expiry_time'] - current_time,
                    'model': info['model'],
                }
                for uid, info in self.active_users.items()
            ],
        }

        # Write to monitoring file
        if self.monitoring_file:
            with open(self.monitoring_file, 'a') as f:
                f.write(json.dumps(state) + '\n')

        # Log summary
        logger.info(
            f"System State: {len(self.active_users)} users, {total_qps:.1f} total QPS, "
            f"elapsed: {state['elapsed_seconds']:.0f}s"
        )

    def _aggregate_results(self):
        """
        Aggregate results from all user processes into system-wide summary.

        This is the key output for stress testing - it shows how the server
        performed under variable load from multiple concurrent users.
        """
        logger.info("=" * 80)
        logger.info("AGGREGATING SYSTEM-WIDE RESULTS")
        logger.info("=" * 80)

        from benchmarking.src.poisson_load_aggregator import PoissonLoadAggregator

        # Create aggregator
        aggregator = PoissonLoadAggregator(
            results_dir=str(self.results_dir),
            time_bucket_seconds=300,  # 5-minute buckets for time-series
        )

        # Load all user responses
        aggregator.load_all_user_responses()
        aggregator.load_config()

        if not aggregator.all_responses:
            logger.warning("No responses to aggregate!")
            return

        # Generate comprehensive summary
        logger.info(f"Aggregating {len(aggregator.all_responses)} total responses from {len(aggregator.user_responses)} users")
        summary = aggregator.generate_aggregate_summary()

        # Write aggregate summary
        aggregator.write_summary(summary, 'poisson_load_aggregate_summary.json')
        logger.info(f"✓ Wrote aggregate summary: {self.results_dir}/poisson_load_aggregate_summary.json")

        # Write simple text report
        report = aggregator.generate_simple_report()
        print("\n" + report)

        # Write report to file
        report_path = self.results_dir / 'poisson_load_aggregate_report.txt'
        with open(report_path, 'w') as f:
            f.write(report)
        logger.info(f"✓ Wrote text report: {report_path}")

        logger.info("=" * 80)
        logger.info("AGGREGATION COMPLETE")
        logger.info("=" * 80)

    def run_load_generation(self):
        """
        Main orchestration loop.

        Runs for test_duration_hours, continuously:
        - Sampling number of users
        - Spawning/killing users
        - Resampling QPS
        - Cleaning up expired sessions
        - Monitoring health
        """
        self.start_time = time.time()
        test_duration = self.config['load_config']['test_duration_hours'] * 3600

        user_resample_interval = self.config['load_config']['resampling']['user_count_interval_seconds']
        qps_resample_interval = self.config['load_config']['resampling']['user_qps_interval_seconds']

        last_user_resample = self.start_time
        last_qps_resample = self.start_time
        last_state_log = self.start_time

        logger.info(
            f"Starting Poisson load generation for {self.config['load_config']['test_duration_hours']} hours"
        )

        # Initial user spawn
        initial_count = self.sample_user_count()
        logger.info(f"Initial user count: {initial_count}")
        self.adjust_user_count(initial_count)

        # Main loop
        while time.time() - self.start_time < test_duration:
            current_time = time.time()

            # Check for load spike
            if self.check_load_spike():
                spike_config = self.config['load_config']['load_spikes']
                logger.warning("⚡ LOAD SPIKE TRIGGERED ⚡")
                spike_multiplier = spike_config['spike_multiplier']
                spike_users = int(self.sample_user_count() * spike_multiplier)
                self.adjust_user_count(spike_users)
                time.sleep(spike_config['spike_duration_seconds'])
                # Spike ends, will resample normally

            # Cleanup expired user sessions
            self.cleanup_expired_users()

            # Resample number of concurrent users
            if current_time - last_user_resample >= user_resample_interval:
                target_users = self.sample_user_count(current_time)
                self.adjust_user_count(target_users)
                last_user_resample = current_time

            # Resample QPS for active users
            if current_time - last_qps_resample >= qps_resample_interval:
                self.resample_user_qps()
                last_qps_resample = current_time

            # Monitor health
            self.monitor_active_users()

            # Log state periodically (every 5 minutes)
            if current_time - last_state_log >= 300:
                self.log_system_state()
                last_state_log = current_time

            # Sleep briefly
            time.sleep(1)

        # Test complete
        logger.info("Test duration complete. Cleaning up all users...")
        for user_id in list(self.active_users.keys()):
            self.kill_user(user_id)

        logger.info("Poisson load generation complete!")

        # Aggregate results from all users
        self._aggregate_results()
