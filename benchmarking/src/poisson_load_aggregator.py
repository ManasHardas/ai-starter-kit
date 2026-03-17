"""
Poisson Load Result Aggregator

This module aggregates results from multiple transient user processes created by the
PoissonLoadGenerator. Each user process generates its own JSONL file with individual
responses. This aggregator combines them into unified system-wide metrics.

Key features:
- Loads responses from all user JSONL files
- Calculates aggregate statistics (mean, stddev, quantiles)
- Generates time-series analysis (load over time)
- Analyzes load distribution across users
- Creates comprehensive summary reports

Usage:
    aggregator = PoissonLoadAggregator(results_dir='./results')
    aggregator.load_all_user_responses()
    summary = aggregator.generate_aggregate_summary()
    aggregator.write_summary(summary, 'aggregate_summary.json')
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesBucket:
    """Represents metrics for a time window (e.g., 5-minute bucket)."""

    start_time: float
    end_time: float
    num_requests: int
    num_users: int
    avg_qps: float
    total_errors: int

    # Latency metrics
    avg_ttft: float
    p50_ttft: float
    p95_ttft: float
    p99_ttft: float

    avg_e2e_latency: float
    p50_e2e_latency: float
    p95_e2e_latency: float
    p99_e2e_latency: float

    # Throughput metrics
    avg_output_throughput: float
    avg_total_throughput: float


@dataclass
class UserMetrics:
    """Aggregated metrics for a single user."""

    user_id: str
    num_requests: int
    avg_qps: float
    session_duration: float

    # Latency stats
    avg_ttft: float
    p95_ttft: float
    avg_e2e_latency: float
    p95_e2e_latency: float

    # Throughput stats
    avg_output_throughput: float

    # Error count
    num_errors: int


class PoissonLoadAggregator:
    """Aggregates results from multiple transient user processes."""

    def __init__(
        self,
        results_dir: str,
        time_bucket_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize aggregator.

        Args:
            results_dir: Directory containing user JSONL files
            time_bucket_seconds: Size of time buckets for time-series analysis
        """
        self.results_dir = Path(results_dir)
        self.time_bucket_seconds = time_bucket_seconds

        # Storage for loaded responses
        self.all_responses: List[Dict[str, Any]] = []
        self.user_responses: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # Metadata
        self.test_start_time: Optional[float] = None
        self.test_end_time: Optional[float] = None
        self.config: Optional[Dict[str, Any]] = None

    def find_user_jsonl_files(self) -> List[Path]:
        """Find all user JSONL files in results directory (searches recursively)."""
        if not self.results_dir.exists():
            logger.warning(f"Results directory does not exist: {self.results_dir}")
            return []

        # Pattern: endurance_<user_id>_*_individual_responses.jsonl
        # Search recursively to find files in user subdirectories
        jsonl_files = list(self.results_dir.rglob("endurance_*_individual_responses.jsonl"))

        logger.info(f"Found {len(jsonl_files)} user JSONL files")
        return jsonl_files

    def load_user_jsonl(self, file_path: Path) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Load responses from a user's JSONL file.

        Args:
            file_path: Path to user's JSONL file

        Returns:
            Tuple of (user_id, list of response dicts)
        """
        responses = []
        user_id = None

        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        response = json.loads(line)
                        responses.append(response)

                        # Extract user_id from the response if available
                        if user_id is None and 'user_name' in response:
                            user_id = response['user_name']

                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse line {line_num} in {file_path}: {e}"
                        )
                        continue

        except Exception as e:
            logger.error(f"Failed to load JSONL file {file_path}: {e}")
            return user_id or f"unknown_{file_path.stem}", []

        # Fallback: extract from parent directory name if user_name not found in responses
        if not user_id:
            parent_dir = file_path.parent.name
            if parent_dir.startswith('user_'):
                user_id = parent_dir.replace('user_', '')
            else:
                user_id = f"unknown_{file_path.stem}"

        logger.info(f"Loaded {len(responses)} responses from {user_id}")
        return user_id, responses

    def load_all_user_responses(self):
        """Load responses from all user JSONL files."""
        jsonl_files = self.find_user_jsonl_files()

        if not jsonl_files:
            logger.warning("No user JSONL files found")
            return

        # Load each user's responses
        for file_path in jsonl_files:
            user_id, responses = self.load_user_jsonl(file_path)

            if responses:
                self.user_responses[user_id] = responses
                self.all_responses.extend(responses)

        logger.info(
            f"Loaded {len(self.all_responses)} total responses from "
            f"{len(self.user_responses)} users"
        )

        # Extract test timeframe
        if self.all_responses:
            timestamps = [
                r.get('client_start_timestamp', 0)
                for r in self.all_responses
            ]
            self.test_start_time = min(timestamps)
            self.test_end_time = max(timestamps)

    def load_config(self) -> Optional[Dict[str, Any]]:
        """Load the Poisson load configuration if available."""
        config_path = self.results_dir / 'poisson_config.json'

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info("Loaded Poisson load configuration")
                return self.config
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")

        return None

    def calculate_metric_statistics(
        self,
        values: List[float],
        metric_name: str = "metric"
    ) -> Dict[str, float]:
        """
        Calculate statistics for a metric.

        Args:
            values: List of metric values
            metric_name: Name for logging

        Returns:
            Dict with mean, stddev, min, max, quantiles
        """
        if not values:
            logger.warning(f"No values for {metric_name}")
            return {
                'mean': 0.0,
                'stddev': 0.0,
                'min': 0.0,
                'max': 0.0,
                'p50': 0.0,
                'p75': 0.0,
                'p90': 0.0,
                'p95': 0.0,
                'p99': 0.0,
            }

        values_array = np.array(values)

        return {
            'mean': float(np.mean(values_array)),
            'stddev': float(np.std(values_array)),
            'min': float(np.min(values_array)),
            'max': float(np.max(values_array)),
            'p50': float(np.percentile(values_array, 50)),
            'p75': float(np.percentile(values_array, 75)),
            'p90': float(np.percentile(values_array, 90)),
            'p95': float(np.percentile(values_array, 95)),
            'p99': float(np.percentile(values_array, 99)),
        }

    def calculate_aggregate_metrics(self) -> Dict[str, Any]:
        """Calculate system-wide aggregate metrics."""
        if not self.all_responses:
            logger.warning("No responses to aggregate")
            return {}

        # Extract metric values
        ttft_values = [
            r['client_ttft_s']
            for r in self.all_responses
            if 'client_ttft_s' in r and r['client_ttft_s'] is not None
        ]

        e2e_latency_values = [
            r['client_end_to_end_latency_s']
            for r in self.all_responses
            if 'client_end_to_end_latency_s' in r and r['client_end_to_end_latency_s'] is not None
        ]

        output_throughput_values = [
            r.get('output_throughput_token_per_s', 0)
            for r in self.all_responses
            if r.get('output_throughput_token_per_s') is not None
        ]

        total_throughput_values = [
            r.get('total_throughput_token_per_s', 0)
            for r in self.all_responses
            if r.get('total_throughput_token_per_s') is not None
        ]

        # Count errors
        error_count = sum(
            1 for r in self.all_responses
            if r.get('error_code') or r.get('error_msg')
        )

        # Calculate statistics
        metrics = {
            'total_requests': len(self.all_responses),
            'successful_requests': len(self.all_responses) - error_count,
            'failed_requests': error_count,
            'error_rate': error_count / len(self.all_responses) if self.all_responses else 0.0,

            'ttft_s': self.calculate_metric_statistics(ttft_values, 'TTFT'),
            'end_to_end_latency_s': self.calculate_metric_statistics(
                e2e_latency_values, 'E2E Latency'
            ),
            'output_throughput_token_per_s': self.calculate_metric_statistics(
                output_throughput_values, 'Output Throughput'
            ),
            'total_throughput_token_per_s': self.calculate_metric_statistics(
                total_throughput_values, 'Total Throughput'
            ),
        }

        # Calculate test duration
        if self.test_start_time and self.test_end_time:
            test_duration = self.test_end_time - self.test_start_time
            metrics['test_duration_seconds'] = test_duration
            metrics['test_duration_hours'] = test_duration / 3600
            metrics['average_qps'] = len(self.all_responses) / test_duration if test_duration > 0 else 0.0

        return metrics

    def generate_time_series_analysis(self) -> List[TimeSeriesBucket]:
        """
        Generate time-series analysis with bucketed metrics.

        Returns:
            List of TimeSeriesBucket objects
        """
        if not self.all_responses or not self.test_start_time:
            return []

        # Create buckets
        test_duration = self.test_end_time - self.test_start_time
        num_buckets = int(np.ceil(test_duration / self.time_bucket_seconds))

        buckets = []

        for i in range(num_buckets):
            bucket_start = self.test_start_time + (i * self.time_bucket_seconds)
            bucket_end = bucket_start + self.time_bucket_seconds

            # Filter responses in this bucket
            bucket_responses = [
                r for r in self.all_responses
                if bucket_start <= r.get('client_start_timestamp', 0) < bucket_end
            ]

            if not bucket_responses:
                # Empty bucket
                buckets.append(TimeSeriesBucket(
                    start_time=bucket_start,
                    end_time=bucket_end,
                    num_requests=0,
                    num_users=0,
                    avg_qps=0.0,
                    total_errors=0,
                    avg_ttft=0.0,
                    p50_ttft=0.0,
                    p95_ttft=0.0,
                    p99_ttft=0.0,
                    avg_e2e_latency=0.0,
                    p50_e2e_latency=0.0,
                    p95_e2e_latency=0.0,
                    p99_e2e_latency=0.0,
                    avg_output_throughput=0.0,
                    avg_total_throughput=0.0,
                ))
                continue

            # Count unique users in bucket
            unique_users = set()
            for r in bucket_responses:
                # Try to extract user_id from response metadata
                user_name = r.get('user_name') or r.get('metadata', {}).get('user_name')
                if user_name:
                    unique_users.add(user_name)

            # Extract metrics
            ttft_values = [
                r['client_ttft_s'] for r in bucket_responses
                if 'client_ttft_s' in r and r['client_ttft_s'] is not None
            ]

            e2e_values = [
                r['client_end_to_end_latency_s'] for r in bucket_responses
                if 'client_end_to_end_latency_s' in r and r['client_end_to_end_latency_s'] is not None
            ]

            output_throughput = [
                r.get('output_throughput_token_per_s', 0) for r in bucket_responses
                if r.get('output_throughput_token_per_s') is not None
            ]

            total_throughput = [
                r.get('total_throughput_token_per_s', 0) for r in bucket_responses
                if r.get('total_throughput_token_per_s') is not None
            ]

            error_count = sum(
                1 for r in bucket_responses
                if r.get('error_code') or r.get('error_msg')
            )

            # Calculate QPS for this bucket
            bucket_qps = len(bucket_responses) / self.time_bucket_seconds

            # Create bucket
            bucket = TimeSeriesBucket(
                start_time=bucket_start,
                end_time=bucket_end,
                num_requests=len(bucket_responses),
                num_users=len(unique_users),
                avg_qps=bucket_qps,
                total_errors=error_count,
                avg_ttft=float(np.mean(ttft_values)) if ttft_values else 0.0,
                p50_ttft=float(np.percentile(ttft_values, 50)) if ttft_values else 0.0,
                p95_ttft=float(np.percentile(ttft_values, 95)) if ttft_values else 0.0,
                p99_ttft=float(np.percentile(ttft_values, 99)) if ttft_values else 0.0,
                avg_e2e_latency=float(np.mean(e2e_values)) if e2e_values else 0.0,
                p50_e2e_latency=float(np.percentile(e2e_values, 50)) if e2e_values else 0.0,
                p95_e2e_latency=float(np.percentile(e2e_values, 95)) if e2e_values else 0.0,
                p99_e2e_latency=float(np.percentile(e2e_values, 99)) if e2e_values else 0.0,
                avg_output_throughput=float(np.mean(output_throughput)) if output_throughput else 0.0,
                avg_total_throughput=float(np.mean(total_throughput)) if total_throughput else 0.0,
            )

            buckets.append(bucket)

        logger.info(f"Generated {len(buckets)} time-series buckets")
        return buckets

    def analyze_user_distribution(self) -> List[UserMetrics]:
        """
        Analyze load distribution across users.

        Returns:
            List of UserMetrics objects
        """
        user_metrics_list = []

        for user_id, responses in self.user_responses.items():
            if not responses:
                continue

            # Extract timestamps
            timestamps = [r.get('client_start_timestamp', 0) for r in responses]
            session_start = min(timestamps)
            session_end = max(timestamps)
            session_duration = session_end - session_start

            # Calculate QPS
            avg_qps = len(responses) / session_duration if session_duration > 0 else 0.0

            # Extract metrics
            ttft_values = [
                r['client_ttft_s'] for r in responses
                if 'client_ttft_s' in r and r['client_ttft_s'] is not None
            ]

            e2e_values = [
                r['client_end_to_end_latency_s'] for r in responses
                if 'client_end_to_end_latency_s' in r and r['client_end_to_end_latency_s'] is not None
            ]

            output_throughput = [
                r.get('output_throughput_token_per_s', 0) for r in responses
                if r.get('output_throughput_token_per_s') is not None
            ]

            error_count = sum(
                1 for r in responses
                if r.get('error_code') or r.get('error_msg')
            )

            # Create user metrics
            user_metrics = UserMetrics(
                user_id=user_id,
                num_requests=len(responses),
                avg_qps=avg_qps,
                session_duration=session_duration,
                avg_ttft=float(np.mean(ttft_values)) if ttft_values else 0.0,
                p95_ttft=float(np.percentile(ttft_values, 95)) if ttft_values else 0.0,
                avg_e2e_latency=float(np.mean(e2e_values)) if e2e_values else 0.0,
                p95_e2e_latency=float(np.percentile(e2e_values, 95)) if e2e_values else 0.0,
                avg_output_throughput=float(np.mean(output_throughput)) if output_throughput else 0.0,
                num_errors=error_count,
            )

            user_metrics_list.append(user_metrics)

        # Sort by number of requests descending
        user_metrics_list.sort(key=lambda x: x.num_requests, reverse=True)

        logger.info(f"Analyzed {len(user_metrics_list)} users")
        return user_metrics_list

    def generate_aggregate_summary(self) -> Dict[str, Any]:
        """
        Generate comprehensive aggregate summary.

        Returns:
            Complete summary dict ready for JSON serialization
        """
        logger.info("Generating aggregate summary...")

        # Load config if not already loaded
        if not self.config:
            self.load_config()

        # Calculate all components
        aggregate_metrics = self.calculate_aggregate_metrics()
        time_series = self.generate_time_series_analysis()
        user_distribution = self.analyze_user_distribution()

        # Build summary
        summary = {
            'test_type': 'poisson_load',
            'test_start_time': self.test_start_time,
            'test_end_time': self.test_end_time,

            'configuration': self.config or {},

            'aggregate_metrics': aggregate_metrics,

            'time_series_analysis': {
                'bucket_size_seconds': self.time_bucket_seconds,
                'num_buckets': len(time_series),
                'buckets': [asdict(bucket) for bucket in time_series],
            },

            'user_distribution': {
                'total_users': len(self.user_responses),
                'users': [asdict(user) for user in user_distribution],
            },

            'load_profile': self._calculate_load_profile(time_series),
        }

        logger.info("Aggregate summary generated")
        return summary

    def _calculate_load_profile(self, time_series: List[TimeSeriesBucket]) -> Dict[str, Any]:
        """Calculate high-level load profile statistics."""
        if not time_series:
            return {}

        qps_values = [bucket.avg_qps for bucket in time_series]
        user_counts = [bucket.num_users for bucket in time_series]

        return {
            'avg_qps': float(np.mean(qps_values)),
            'min_qps': float(np.min(qps_values)),
            'max_qps': float(np.max(qps_values)),
            'stddev_qps': float(np.std(qps_values)),

            'avg_concurrent_users': float(np.mean(user_counts)),
            'min_concurrent_users': int(np.min(user_counts)),
            'max_concurrent_users': int(np.max(user_counts)),

            'qps_variability_coefficient': float(np.std(qps_values) / np.mean(qps_values)) if np.mean(qps_values) > 0 else 0.0,
        }

    def write_summary(self, summary: Dict[str, Any], filename: str = 'aggregate_summary.json'):
        """Write summary to JSON file."""
        output_path = self.results_dir / filename

        try:
            with open(output_path, 'w') as f:
                json.dump(summary, f, indent=2)

            logger.info(f"Wrote aggregate summary to {output_path}")
        except Exception as e:
            logger.error(f"Failed to write summary: {e}")
            raise

    def generate_simple_report(self) -> str:
        """Generate a simple text report for quick viewing."""
        if not self.all_responses:
            return "No data to report"

        metrics = self.calculate_aggregate_metrics()
        user_dist = self.analyze_user_distribution()

        report_lines = [
            "=" * 80,
            "POISSON LOAD TEST AGGREGATE REPORT",
            "=" * 80,
            "",
            f"Test Duration: {metrics.get('test_duration_hours', 0):.2f} hours",
            f"Total Requests: {metrics['total_requests']:,}",
            f"Successful: {metrics['successful_requests']:,}",
            f"Failed: {metrics['failed_requests']:,}",
            f"Error Rate: {metrics['error_rate'] * 100:.2f}%",
            f"Average QPS: {metrics.get('average_qps', 0):.2f}",
            "",
            "LATENCY METRICS:",
            f"  TTFT - Mean: {metrics['ttft_s']['mean']:.3f}s, P95: {metrics['ttft_s']['p95']:.3f}s, P99: {metrics['ttft_s']['p99']:.3f}s",
            f"  E2E  - Mean: {metrics['end_to_end_latency_s']['mean']:.3f}s, P95: {metrics['end_to_end_latency_s']['p95']:.3f}s, P99: {metrics['end_to_end_latency_s']['p99']:.3f}s",
            "",
            "THROUGHPUT METRICS:",
            f"  Output - Mean: {metrics['output_throughput_token_per_s']['mean']:.2f} tok/s",
            f"  Total  - Mean: {metrics['total_throughput_token_per_s']['mean']:.2f} tok/s",
            "",
            f"USER DISTRIBUTION ({len(user_dist)} total users):",
        ]

        # Show top 10 users
        for i, user in enumerate(user_dist[:10], 1):
            report_lines.append(
                f"  {i:2d}. {user.user_id}: {user.num_requests:,} requests, "
                f"{user.avg_qps:.2f} QPS, {user.session_duration:.0f}s session"
            )

        report_lines.extend([
            "",
            "=" * 80,
        ])

        return "\n".join(report_lines)


def main():
    """CLI for testing the aggregator."""
    import argparse

    parser = argparse.ArgumentParser(description='Aggregate Poisson load test results')
    parser.add_argument(
        '--results-dir',
        type=str,
        required=True,
        help='Directory containing user JSONL files'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='aggregate_summary.json',
        help='Output filename for summary'
    )
    parser.add_argument(
        '--time-bucket-seconds',
        type=int,
        default=300,
        help='Time bucket size for time-series analysis (default: 300s = 5 min)'
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create aggregator
    aggregator = PoissonLoadAggregator(
        results_dir=args.results_dir,
        time_bucket_seconds=args.time_bucket_seconds,
    )

    # Load responses
    aggregator.load_all_user_responses()

    if not aggregator.all_responses:
        logger.error("No responses loaded. Exiting.")
        return

    # Generate summary
    summary = aggregator.generate_aggregate_summary()
    aggregator.write_summary(summary, args.output)

    # Print simple report
    report = aggregator.generate_simple_report()
    print("\n" + report)


if __name__ == '__main__':
    main()
