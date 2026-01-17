"""Tests for tier calculation logic."""
import pytest
from datetime import date
from uuid import uuid4

from app.services.tier_calculator import TierCalculator, ZScoreResult, TierResult
from app.services.metrics_aggregator import WaiterMetricsSnapshot


class TestZScoreCalculation:
    """Tests for Z-score calculation."""

    def setup_method(self):
        self.calculator = TierCalculator()

    def test_zscore_at_mean(self):
        """Z-score at mean should be 0."""
        zscore = self.calculator.calculate_zscore(
            value=50.0, mean=50.0, std=10.0
        )
        assert zscore == 0.0

    def test_zscore_above_mean(self):
        """Z-score above mean should be positive."""
        zscore = self.calculator.calculate_zscore(
            value=60.0, mean=50.0, std=10.0
        )
        assert zscore == 1.0

    def test_zscore_below_mean(self):
        """Z-score below mean should be negative."""
        zscore = self.calculator.calculate_zscore(
            value=40.0, mean=50.0, std=10.0
        )
        assert zscore == -1.0

    def test_zscore_inverted_for_turn_time(self):
        """Inverted Z-score (lower is better) flips the sign."""
        # Faster turn time (40) than average (50) should give positive Z
        zscore = self.calculator.calculate_zscore(
            value=40.0, mean=50.0, std=10.0, invert=True
        )
        assert zscore == 1.0  # Positive because faster is better

    def test_zscore_handles_zero_std(self):
        """Z-score with zero std should use 1.0 as default."""
        zscore = self.calculator.calculate_zscore(
            value=60.0, mean=50.0, std=0.0
        )
        assert zscore == 10.0  # (60-50)/1.0


class TestZScoreNormalization:
    """Tests for converting Z-scores to 0-100 scale."""

    def setup_method(self):
        self.calculator = TierCalculator()

    def test_zscore_zero_maps_to_50(self):
        """Z-score of 0 (at mean) should map to ~50."""
        normalized = self.calculator.zscore_to_normalized(0.0)
        assert normalized == 50.0

    def test_positive_zscore_above_50(self):
        """Positive Z-score should map above 50."""
        normalized = self.calculator.zscore_to_normalized(1.0)
        assert normalized > 50.0
        assert normalized < 100.0

    def test_negative_zscore_below_50(self):
        """Negative Z-score should map below 50."""
        normalized = self.calculator.zscore_to_normalized(-1.0)
        assert normalized < 50.0
        assert normalized > 0.0

    def test_extreme_zscore_clamped(self):
        """Extreme Z-scores should be clamped to valid range."""
        high = self.calculator.zscore_to_normalized(5.0)
        low = self.calculator.zscore_to_normalized(-5.0)

        assert 0 <= high <= 100
        assert 0 <= low <= 100


class TestMathScoreCalculation:
    """Tests for PRD formula math score calculation."""

    def setup_method(self):
        self.calculator = TierCalculator()
        self.peer_stats = {
            "avg_turn_time": 45.0,
            "std_turn_time": 10.0,
            "avg_tip_pct": 18.0,
            "std_tip_pct": 3.0,
            "avg_covers_per_shift": 20.0,
            "std_covers_per_shift": 5.0,
        }

    def _create_metrics(
        self,
        turn_time: float = 45.0,
        tip_pct: float = 18.0,
        covers: float = 20.0,
    ) -> WaiterMetricsSnapshot:
        """Helper to create metrics snapshot."""
        return WaiterMetricsSnapshot(
            waiter_id=uuid4(),
            restaurant_id=uuid4(),
            period_start=date.today(),
            period_end=date.today(),
            avg_turn_time_minutes=turn_time,
            avg_tip_percentage=tip_pct,
            avg_covers_per_shift=covers,
        )

    def test_average_waiter_gets_middle_score(self):
        """Waiter at all averages should get ~50 score."""
        metrics = self._create_metrics(
            turn_time=45.0,  # At average
            tip_pct=18.0,    # At average
            covers=20.0,     # At average
        )
        result = self.calculator.calculate_math_score(metrics, self.peer_stats)

        assert 45 <= result.math_score <= 55  # Around 50

    def test_excellent_waiter_gets_high_score(self):
        """Waiter excelling in all metrics should get high score."""
        metrics = self._create_metrics(
            turn_time=30.0,  # Fast (lower is better)
            tip_pct=25.0,    # High tips
            covers=30.0,     # High volume
        )
        result = self.calculator.calculate_math_score(metrics, self.peer_stats)

        assert result.math_score > 60

    def test_struggling_waiter_gets_low_score(self):
        """Waiter struggling in all metrics should get low score."""
        metrics = self._create_metrics(
            turn_time=60.0,  # Slow
            tip_pct=12.0,    # Low tips
            covers=12.0,     # Low volume
        )
        result = self.calculator.calculate_math_score(metrics, self.peer_stats)

        assert result.math_score < 40

    def test_zscore_components_returned(self):
        """Result should include Z-score components."""
        metrics = self._create_metrics()
        result = self.calculator.calculate_math_score(metrics, self.peer_stats)

        assert hasattr(result, 'turn_time_zscore')
        assert hasattr(result, 'tip_pct_zscore')
        assert hasattr(result, 'covers_zscore')


class TestTierAssignment:
    """Tests for tier assignment based on percentiles."""

    def setup_method(self):
        self.calculator = TierCalculator()

    def test_high_score_gets_strong_tier(self):
        """Score above p75 should be 'strong'."""
        percentiles = {"p25": 40.0, "p50": 50.0, "p75": 60.0}
        result = self.calculator.assign_tier(75.0, percentiles)

        assert result.tier == "strong"
        assert result.percentile > 75

    def test_middle_score_gets_standard_tier(self):
        """Score between p25 and p75 should be 'standard'."""
        percentiles = {"p25": 40.0, "p50": 50.0, "p75": 60.0}
        result = self.calculator.assign_tier(50.0, percentiles)

        assert result.tier == "standard"
        assert 25 <= result.percentile <= 75

    def test_low_score_gets_developing_tier(self):
        """Score below p25 should be 'developing'."""
        percentiles = {"p25": 40.0, "p50": 50.0, "p75": 60.0}
        result = self.calculator.assign_tier(30.0, percentiles)

        assert result.tier == "developing"
        assert result.percentile < 25

    def test_boundary_at_p75(self):
        """Score exactly at p75 should be 'strong'."""
        percentiles = {"p25": 40.0, "p50": 50.0, "p75": 60.0}
        result = self.calculator.assign_tier(60.0, percentiles)

        assert result.tier == "strong"

    def test_boundary_at_p25(self):
        """Score exactly at p25 should be 'standard'."""
        percentiles = {"p25": 40.0, "p50": 50.0, "p75": 60.0}
        result = self.calculator.assign_tier(40.0, percentiles)

        assert result.tier == "standard"


class TestPercentileCalculation:
    """Tests for percentile calculation."""

    def setup_method(self):
        self.calculator = TierCalculator()

    def test_percentiles_with_normal_distribution(self):
        """Percentiles for evenly distributed scores."""
        scores = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        percentiles = self.calculator.calculate_percentiles(scores)

        assert percentiles["p25"] < percentiles["p50"]
        assert percentiles["p50"] < percentiles["p75"]

    def test_percentiles_empty_list(self):
        """Empty list should return defaults."""
        percentiles = self.calculator.calculate_percentiles([])

        assert percentiles["p25"] == 25.0
        assert percentiles["p50"] == 50.0
        assert percentiles["p75"] == 75.0

    def test_percentiles_single_value(self):
        """Single value should return that value for all percentiles."""
        percentiles = self.calculator.calculate_percentiles([50.0])

        assert percentiles["p25"] == 50.0
        assert percentiles["p75"] == 50.0


class TestTierDistribution:
    """Tests for tier distribution counting."""

    def setup_method(self):
        self.calculator = TierCalculator()

    def test_distribution_counts_correctly(self):
        """Distribution should count tiers correctly."""
        tier_results = [
            TierResult(tier="strong", percentile=80, score=80),
            TierResult(tier="strong", percentile=85, score=85),
            TierResult(tier="standard", percentile=50, score=50),
            TierResult(tier="standard", percentile=55, score=55),
            TierResult(tier="standard", percentile=60, score=60),
            TierResult(tier="developing", percentile=20, score=20),
        ]

        distribution = self.calculator.get_tier_distribution(tier_results)

        assert distribution["strong"] == 2
        assert distribution["standard"] == 3
        assert distribution["developing"] == 1
