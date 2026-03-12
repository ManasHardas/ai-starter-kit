"""
Unit tests for endurance testing infrastructure.
"""

import json
import os
import statistics
import tempfile
import unittest
from pathlib import Path

from benchmarking.src.checkpoint_manager import (
    CheckpointManager,
    CheckpointState,
    RollingStatsCalculator,
)


class TestRollingStatsCalculator(unittest.TestCase):
    """Test RollingStatsCalculator for accuracy and consistency."""

    def test_mean_calculation(self):
        """Test that rolling mean matches Python statistics mean."""
        calc = RollingStatsCalculator(reservoir_size=1000)
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        for val in values:
            calc.update('test_metric', val)

        stats = calc.get_statistics('test_metric')
        expected_mean = statistics.mean(values)

        self.assertAlmostEqual(stats['mean'], expected_mean, places=4)

    def test_min_max_calculation(self):
        """Test that min and max are correctly tracked."""
        calc = RollingStatsCalculator(reservoir_size=1000)
        values = [5.0, 2.0, 8.0, 1.0, 9.0, 3.0]

        for val in values:
            calc.update('test_metric', val)

        stats = calc.get_statistics('test_metric')

        self.assertEqual(stats['min'], 1.0)
        self.assertEqual(stats['max'], 9.0)

    def test_stddev_calculation(self):
        """Test that standard deviation is calculated correctly."""
        calc = RollingStatsCalculator(reservoir_size=1000)
        values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]

        for val in values:
            calc.update('test_metric', val)

        stats = calc.get_statistics('test_metric')
        expected_std = statistics.stdev(values)  # Sample standard deviation

        self.assertAlmostEqual(stats['stddev'], expected_std, places=4)

    def test_quantile_approximation(self):
        """Test that quantiles are reasonably approximated."""
        calc = RollingStatsCalculator(reservoir_size=100)
        values = list(range(1, 101))  # 1 to 100

        for val in values:
            calc.update('test_metric', float(val))

        stats = calc.get_statistics('test_metric')

        # Check that p50 is close to 50 (within 5% tolerance)
        self.assertGreater(stats['quantiles']['p50'], 45)
        self.assertLess(stats['quantiles']['p50'], 55)

        # Check that p90 is close to 90
        self.assertGreater(stats['quantiles']['p90'], 85)
        self.assertLess(stats['quantiles']['p90'], 95)

    def test_multiple_metrics(self):
        """Test tracking multiple metrics simultaneously."""
        calc = RollingStatsCalculator(reservoir_size=1000)

        calc.update('metric1', 10.0)
        calc.update('metric2', 20.0)
        calc.update('metric1', 15.0)
        calc.update('metric2', 25.0)

        stats1 = calc.get_statistics('metric1')
        stats2 = calc.get_statistics('metric2')

        self.assertEqual(stats1['mean'], 12.5)
        self.assertEqual(stats2['mean'], 22.5)

    def test_serialization(self):
        """Test that calculator can be serialized and restored."""
        calc = RollingStatsCalculator(reservoir_size=100)

        for i in range(50):
            calc.update('test_metric', float(i))

        # Serialize
        state = calc.to_dict()

        # Restore
        calc2 = RollingStatsCalculator.from_dict(state)
        stats2 = calc2.get_statistics('test_metric')

        # Original stats
        stats1 = calc.get_statistics('test_metric')

        self.assertEqual(stats1['mean'], stats2['mean'])
        self.assertEqual(stats1['min'], stats2['min'])
        self.assertEqual(stats1['max'], stats2['max'])

    def test_large_dataset(self):
        """Test with large dataset to verify reservoir sampling."""
        calc = RollingStatsCalculator(reservoir_size=1000)

        # Add 10,000 values
        for i in range(10000):
            calc.update('test_metric', float(i))

        stats = calc.get_statistics('test_metric')

        # Mean should be close to 4999.5
        expected_mean = 4999.5
        self.assertGreater(stats['mean'], expected_mean - 100)
        self.assertLess(stats['mean'], expected_mean + 100)

        # Min should be 0, max should be 9999
        self.assertEqual(stats['min'], 0.0)
        self.assertEqual(stats['max'], 9999.0)


class TestCheckpointManager(unittest.TestCase):
    """Test CheckpointManager for save/load functionality."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.run_uuid = 'test-uuid-12345'

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_checkpoint(self):
        """Test basic checkpoint save and load."""
        manager = CheckpointManager(self.temp_dir, self.run_uuid)

        # Create checkpoint state
        state = CheckpointState(
            run_uuid=self.run_uuid,
            start_time=100.0,
            start_timestamp='2024-01-01T00:00:00Z',
            last_checkpoint_time=200.0,
            total_requests_completed=500,
            total_requests_started=510,
            test_duration_hours=12.0,
            qps=10.0,
            qps_distribution='constant',
            num_input_tokens=1000,
            num_output_tokens=500,
            model_name='test-model',
            rolling_stats_state={},
            completed=False,
        )

        # Save checkpoint
        manager.save_checkpoint(state)

        # Verify file exists
        self.assertTrue(manager.checkpoint_exists())

        # Load checkpoint
        loaded_state = manager.load_checkpoint()

        self.assertIsNotNone(loaded_state)
        self.assertEqual(loaded_state.run_uuid, self.run_uuid)
        self.assertEqual(loaded_state.total_requests_completed, 500)
        self.assertEqual(loaded_state.qps, 10.0)
        self.assertEqual(loaded_state.model_name, 'test-model')

    def test_checkpoint_does_not_exist(self):
        """Test loading when no checkpoint exists."""
        manager = CheckpointManager(self.temp_dir, 'non-existent-uuid')

        self.assertFalse(manager.checkpoint_exists())
        loaded_state = manager.load_checkpoint()
        self.assertIsNone(loaded_state)

    def test_delete_checkpoint(self):
        """Test checkpoint deletion."""
        manager = CheckpointManager(self.temp_dir, self.run_uuid)

        state = CheckpointState(
            run_uuid=self.run_uuid,
            start_time=100.0,
            start_timestamp='2024-01-01T00:00:00Z',
            last_checkpoint_time=200.0,
            total_requests_completed=500,
            total_requests_started=510,
            test_duration_hours=12.0,
            qps=10.0,
            qps_distribution='constant',
            num_input_tokens=1000,
            num_output_tokens=500,
            model_name='test-model',
            rolling_stats_state={},
            completed=False,
        )

        manager.save_checkpoint(state)
        self.assertTrue(manager.checkpoint_exists())

        manager.delete_checkpoint()
        self.assertFalse(manager.checkpoint_exists())

    def test_atomic_write(self):
        """Test that writes are atomic (no partial writes)."""
        manager = CheckpointManager(self.temp_dir, self.run_uuid)

        state = CheckpointState(
            run_uuid=self.run_uuid,
            start_time=100.0,
            start_timestamp='2024-01-01T00:00:00Z',
            last_checkpoint_time=200.0,
            total_requests_completed=500,
            total_requests_started=510,
            test_duration_hours=12.0,
            qps=10.0,
            qps_distribution='constant',
            num_input_tokens=1000,
            num_output_tokens=500,
            model_name='test-model',
            rolling_stats_state={},
            completed=False,
        )

        manager.save_checkpoint(state)

        # Verify checkpoint file can be parsed as valid JSON
        checkpoint_file = Path(self.temp_dir) / f'checkpoint_{self.run_uuid}.json'
        with open(checkpoint_file, 'r') as f:
            data = json.load(f)
            self.assertEqual(data['run_uuid'], self.run_uuid)

        # Verify no temp file remains
        temp_file = Path(self.temp_dir) / f'checkpoint_{self.run_uuid}.tmp'
        self.assertFalse(temp_file.exists())

    def test_checkpoint_with_rolling_stats(self):
        """Test checkpoint with rolling statistics state."""
        manager = CheckpointManager(self.temp_dir, self.run_uuid)

        # Create rolling stats
        calc = RollingStatsCalculator(reservoir_size=100)
        for i in range(10):
            calc.update('test_metric', float(i))

        state = CheckpointState(
            run_uuid=self.run_uuid,
            start_time=100.0,
            start_timestamp='2024-01-01T00:00:00Z',
            last_checkpoint_time=200.0,
            total_requests_completed=10,
            total_requests_started=10,
            test_duration_hours=1.0,
            qps=1.0,
            qps_distribution='constant',
            num_input_tokens=100,
            num_output_tokens=50,
            model_name='test-model',
            rolling_stats_state=calc.to_dict(),
            completed=False,
        )

        manager.save_checkpoint(state)
        loaded_state = manager.load_checkpoint()

        # Restore rolling stats
        calc2 = RollingStatsCalculator.from_dict(loaded_state.rolling_stats_state)
        stats = calc2.get_statistics('test_metric')

        self.assertEqual(stats['mean'], 4.5)  # mean of 0-9


class TestCheckpointState(unittest.TestCase):
    """Test CheckpointState dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = CheckpointState(
            run_uuid='test-uuid',
            start_time=100.0,
            start_timestamp='2024-01-01T00:00:00Z',
            last_checkpoint_time=200.0,
            total_requests_completed=500,
            total_requests_started=510,
            test_duration_hours=12.0,
            qps=10.0,
            qps_distribution='constant',
            num_input_tokens=1000,
            num_output_tokens=500,
            model_name='test-model',
            rolling_stats_state={},
        )

        state_dict = state.to_dict()

        self.assertEqual(state_dict['run_uuid'], 'test-uuid')
        self.assertEqual(state_dict['qps'], 10.0)
        self.assertEqual(state_dict['total_requests_completed'], 500)

    def test_from_dict(self):
        """Test creation from dictionary."""
        state_dict = {
            'run_uuid': 'test-uuid',
            'start_time': 100.0,
            'start_timestamp': '2024-01-01T00:00:00Z',
            'last_checkpoint_time': 200.0,
            'total_requests_completed': 500,
            'total_requests_started': 510,
            'test_duration_hours': 12.0,
            'qps': 10.0,
            'qps_distribution': 'constant',
            'num_input_tokens': 1000,
            'num_output_tokens': 500,
            'model_name': 'test-model',
            'rolling_stats_state': {},
            'completed': False,
            'end_time': None,
            'end_timestamp': None,
        }

        state = CheckpointState.from_dict(state_dict)

        self.assertEqual(state.run_uuid, 'test-uuid')
        self.assertEqual(state.qps, 10.0)
        self.assertEqual(state.total_requests_completed, 500)


if __name__ == '__main__':
    unittest.main()
