"""
Checkpoint management infrastructure for endurance testing.

This module provides checkpoint management, rolling statistics calculation,
and state persistence for long-running benchmarking tests.
"""

import json
import os
import random
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import filelock


@dataclass
class CheckpointState:
    """State container for checkpoint data."""

    run_uuid: str
    start_time: float  # monotonic time
    start_timestamp: str  # ISO 8601 timestamp
    last_checkpoint_time: float  # monotonic time
    total_requests_completed: int
    total_requests_started: int
    test_duration_hours: float
    qps: float
    qps_distribution: str
    num_input_tokens: int
    num_output_tokens: int
    model_name: str
    rolling_stats_state: Dict[str, Any]
    completed: bool = False
    end_time: Optional[float] = None
    end_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointState':
        """Create CheckpointState from dictionary."""
        return cls(**data)


class RollingStatsCalculator:
    """
    Calculates rolling statistics using Welford's online algorithm for mean/variance
    and reservoir sampling for quantile approximation.

    This approach prevents memory accumulation while maintaining statistical accuracy.
    """

    def __init__(self, reservoir_size: int = 10000):
        """
        Initialize the rolling statistics calculator.

        Args:
            reservoir_size: Maximum number of samples to keep for quantile calculations.
        """
        self.reservoir_size = reservoir_size
        # Welford's algorithm state: {metric: {'count': n, 'mean': M, 'M2': M2, 'min': min, 'max': max}}
        self.welford_state: Dict[str, Dict[str, float]] = {}
        # Reservoir samples: {metric: [sample1, sample2, ...]}
        self.reservoir: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def update(self, metric: str, value: float) -> None:
        """
        Add a new data point for a metric.

        Args:
            metric: Name of the metric.
            value: Value to add.
        """
        with self.lock:
            # Initialize metric state if needed
            if metric not in self.welford_state:
                self.welford_state[metric] = {
                    'count': 0,
                    'mean': 0.0,
                    'M2': 0.0,
                    'min': float('inf'),
                    'max': float('-inf'),
                }
                self.reservoir[metric] = []

            # Update Welford's algorithm state
            state = self.welford_state[metric]
            state['count'] += 1
            delta = value - state['mean']
            state['mean'] += delta / state['count']
            delta2 = value - state['mean']
            state['M2'] += delta * delta2
            state['min'] = min(state['min'], value)
            state['max'] = max(state['max'], value)

            # Update reservoir using reservoir sampling
            reservoir = self.reservoir[metric]
            if len(reservoir) < self.reservoir_size:
                reservoir.append(value)
            else:
                # Replace random element with probability k/n
                j = random.randint(0, state['count'] - 1)
                if j < self.reservoir_size:
                    reservoir[j] = value

    def get_statistics(self, metric: str) -> Dict[str, Any]:
        """
        Get current statistics for a metric.

        Args:
            metric: Name of the metric.

        Returns:
            Dictionary with mean, stddev, min, max, and quantiles.
        """
        with self.lock:
            if metric not in self.welford_state:
                return {}

            state = self.welford_state[metric]
            count = state['count']

            if count == 0:
                return {}

            result = {
                'mean': round(state['mean'], 4),
                'min': round(state['min'], 4),
                'max': round(state['max'], 4),
            }

            # Calculate standard deviation
            if count > 1:
                variance = state['M2'] / (count - 1)
                result['stddev'] = round(variance**0.5, 4)
            else:
                result['stddev'] = 0.0

            # Calculate quantiles from reservoir
            reservoir = self.reservoir[metric]
            if reservoir:
                sorted_samples = sorted(reservoir)
                quantiles = {}
                for q, name in [(0.5, 'p50'), (0.75, 'p75'), (0.9, 'p90'), (0.95, 'p95'), (0.99, 'p99')]:
                    idx = int(q * len(sorted_samples))
                    if idx >= len(sorted_samples):
                        idx = len(sorted_samples) - 1
                    quantiles[name] = round(sorted_samples[idx], 4)
                result['quantiles'] = quantiles

            return result

    def get_all_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all metrics."""
        return {metric: self.get_statistics(metric) for metric in self.welford_state.keys()}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for checkpointing."""
        with self.lock:
            return {
                'reservoir_size': self.reservoir_size,
                'welford_state': self.welford_state.copy(),
                'reservoir': {k: v.copy() for k, v in self.reservoir.items()},
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RollingStatsCalculator':
        """Restore state from checkpoint."""
        calculator = cls(reservoir_size=data['reservoir_size'])
        calculator.welford_state = data['welford_state'].copy()
        calculator.reservoir = {k: v.copy() for k, v in data['reservoir'].items()}
        return calculator


class CheckpointManager:
    """
    Manages checkpoint state persistence with atomic writes and file locking.
    """

    def __init__(self, checkpoint_dir: str, run_uuid: str):
        """
        Initialize the checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoint files.
            run_uuid: Unique identifier for this test run.
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.run_uuid = run_uuid
        self.checkpoint_file = self.checkpoint_dir / f'checkpoint_{run_uuid}.json'
        self.lock_file = self.checkpoint_dir / f'checkpoint_{run_uuid}.lock'
        self.lock = filelock.FileLock(str(self.lock_file), timeout=10)

    def save_checkpoint(self, state: CheckpointState) -> None:
        """
        Save checkpoint state atomically using temp file + rename pattern.

        Args:
            state: Checkpoint state to save.
        """
        with self.lock:
            # Write to temporary file first
            temp_file = self.checkpoint_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w') as f:
                    json.dump(state.to_dict(), f, indent=2)
                # Atomic rename
                temp_file.replace(self.checkpoint_file)
            except Exception as e:
                # Clean up temp file on error
                if temp_file.exists():
                    temp_file.unlink()
                raise e

    def load_checkpoint(self) -> Optional[CheckpointState]:
        """
        Load checkpoint state from disk.

        Returns:
            CheckpointState if found, None otherwise.
        """
        if not self.checkpoint_file.exists():
            return None

        try:
            with self.lock:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                return CheckpointState.from_dict(data)
        except Exception as e:
            print(f'Warning: Failed to load checkpoint: {e}')
            return None

    def delete_checkpoint(self) -> None:
        """Delete checkpoint file after successful completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as e:
            print(f'Warning: Failed to delete checkpoint: {e}')

    def checkpoint_exists(self) -> bool:
        """Check if a checkpoint file exists."""
        return self.checkpoint_file.exists()
