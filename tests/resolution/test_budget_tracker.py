"""Tests for BudgetTracker and BudgetConfig."""

from unittest.mock import patch

from src.open_source_risk_model.resolution.budget_tracker import (
    BudgetConfig,
    BudgetTracker,
)


class TestBudgetConfigDefaults:
    def test_default_global_budget(self):
        config = BudgetConfig()
        assert config.global_budget == 200

    def test_default_min_delay_ms(self):
        config = BudgetConfig()
        assert config.min_delay_ms == 100

    def test_default_per_ecosystem_empty(self):
        config = BudgetConfig()
        assert config.per_ecosystem == {}


class TestCanMakeCall:
    def test_returns_true_when_under_budget(self):
        tracker = BudgetTracker(BudgetConfig(global_budget=10))
        assert tracker.can_make_call("pypi") is True

    def test_returns_false_when_global_budget_exhausted(self):
        tracker = BudgetTracker(BudgetConfig(global_budget=2))
        tracker.record_call("pypi")
        tracker.record_call("pypi")
        assert tracker.can_make_call("pypi") is False

    def test_returns_false_when_per_ecosystem_budget_exhausted(self):
        tracker = BudgetTracker(
            BudgetConfig(global_budget=200, per_ecosystem={"pypi": 1})
        )
        tracker.record_call("pypi")
        assert tracker.can_make_call("pypi") is False

    def test_per_ecosystem_overrides_global_budget(self):
        """Per-ecosystem budget of 1 exhausted, but global budget of 200 is not."""
        tracker = BudgetTracker(
            BudgetConfig(global_budget=200, per_ecosystem={"pypi": 1})
        )
        tracker.record_call("pypi")
        # pypi is exhausted via per-ecosystem limit
        assert tracker.can_make_call("pypi") is False
        # npm still uses global budget, which is not exhausted
        assert tracker.can_make_call("npm") is True


class TestRecordCall:
    def test_increments_global_and_per_ecosystem(self):
        tracker = BudgetTracker(BudgetConfig(global_budget=10))
        tracker.record_call("pypi")
        tracker.record_call("npm")
        tracker.record_call("pypi")
        assert tracker.api_calls_made == 3
        assert tracker._per_ecosystem_used["pypi"] == 2
        assert tracker._per_ecosystem_used["npm"] == 1


class TestApiCallsMade:
    def test_reflects_total_calls_across_ecosystems(self):
        tracker = BudgetTracker(BudgetConfig(global_budget=100))
        tracker.record_call("pypi")
        tracker.record_call("npm")
        tracker.record_call("pypi")
        tracker.record_call("npm")
        assert tracker.api_calls_made == 4

    def test_starts_at_zero(self):
        tracker = BudgetTracker(BudgetConfig())
        assert tracker.api_calls_made == 0


class TestWaitIfNeeded:
    @patch("src.open_source_risk_model.resolution.budget_tracker.time.sleep")
    @patch("src.open_source_risk_model.resolution.budget_tracker.time.monotonic")
    def test_sleeps_when_calls_too_close(self, mock_monotonic, mock_sleep):
        """When elapsed time < min_delay_ms, wait_if_needed should sleep."""
        # First call at t=1.0
        mock_monotonic.return_value = 1.0
        tracker = BudgetTracker(BudgetConfig(min_delay_ms=100))
        tracker.wait_if_needed("pypi")
        mock_sleep.assert_not_called()  # first call, no previous timestamp

        # Second call at t=1.05 (50ms later, less than 100ms min_delay)
        mock_monotonic.return_value = 1.05
        tracker.wait_if_needed("pypi")
        mock_sleep.assert_called_once()
        sleep_arg = mock_sleep.call_args[0][0]
        assert 0.04 < sleep_arg < 0.06  # should sleep ~50ms

    @patch("src.open_source_risk_model.resolution.budget_tracker.time.sleep")
    @patch("src.open_source_risk_model.resolution.budget_tracker.time.monotonic")
    def test_no_sleep_when_enough_time_elapsed(self, mock_monotonic, mock_sleep):
        """When elapsed time >= min_delay_ms, wait_if_needed should not sleep."""
        # First call at t=1.0
        mock_monotonic.return_value = 1.0
        tracker = BudgetTracker(BudgetConfig(min_delay_ms=100))
        tracker.wait_if_needed("pypi")

        # Second call at t=1.2 (200ms later, more than 100ms min_delay)
        mock_monotonic.return_value = 1.2
        tracker.wait_if_needed("pypi")
        mock_sleep.assert_not_called()
