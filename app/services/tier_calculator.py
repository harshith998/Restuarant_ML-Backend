"""Service for calculating waiter tiers using Z-score normalization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.services.metrics_aggregator import WaiterMetricsSnapshot


@dataclass
class ZScoreResult:
    """Z-score calculation results for a waiter."""

    turn_time_zscore: float
    tip_pct_zscore: float
    covers_zscore: float
    math_score: float  # Final PRD formula score (0-100)


@dataclass
class TierResult:
    """Tier assignment result."""

    tier: str  # strong, standard, developing
    percentile: float  # 0-100
    score: float


class TierCalculator:
    """
    Calculates waiter tiers using Z-score normalization and PRD formula.

    PRD Formula (Section 4.5):
    score = (normalized_turn_time * 0.3)      # Lower is better
          + (normalized_tip_pct * 0.4)        # Higher is better
          + (normalized_covers * 0.3)         # Higher is better

    Tier Assignment (Appendix A):
    - score >= p75 -> "strong"
    - score >= p25 -> "standard"
    - score < p25 -> "developing"
    """

    # PRD weights
    TURN_TIME_WEIGHT = 0.3
    TIP_PCT_WEIGHT = 0.4
    COVERS_WEIGHT = 0.3

    # Score range
    MIN_SCORE = 0.0
    MAX_SCORE = 100.0

    def calculate_zscore(
        self,
        value: float,
        mean: float,
        std: float,
        invert: bool = False,
    ) -> float:
        """
        Calculate Z-score for a value.

        Args:
            value: The value to normalize
            mean: Population mean
            std: Population standard deviation
            invert: If True, lower values are better (e.g., turn time)

        Returns:
            Z-score (standard deviations from mean)
        """
        if std == 0:
            std = 1.0

        zscore = (value - mean) / std

        if invert:
            zscore = -zscore  # Flip so lower values give positive z-scores

        return zscore

    def zscore_to_normalized(self, zscore: float, scale: float = 100.0) -> float:
        """
        Convert Z-score to 0-100 normalized scale.

        Maps Z-scores roughly to:
        - z = -2 -> ~0
        - z = 0 -> ~50
        - z = +2 -> ~100
        """
        # Sigmoid-like transformation centered at 0
        # This ensures scores stay in 0-100 range
        import math

        # Clamp extreme z-scores
        zscore = max(-3, min(3, zscore))

        # Transform: maps -3..+3 to roughly 0..100
        normalized = 50 + (zscore * 16.67)

        return max(0, min(scale, normalized))

    def calculate_math_score(
        self,
        metrics: WaiterMetricsSnapshot,
        peer_stats: Dict[str, float],
    ) -> ZScoreResult:
        """
        Calculate the PRD formula math score using Z-score normalization.

        Args:
            metrics: Waiter's metrics snapshot
            peer_stats: Peer statistics for normalization

        Returns:
            ZScoreResult with component scores and final math score
        """
        # Calculate Z-scores
        turn_time_z = self.calculate_zscore(
            value=metrics.avg_turn_time_minutes,
            mean=peer_stats.get("avg_turn_time", 45.0),
            std=peer_stats.get("std_turn_time", 10.0),
            invert=True,  # Lower turn time is better
        )

        tip_pct_z = self.calculate_zscore(
            value=metrics.avg_tip_percentage,
            mean=peer_stats.get("avg_tip_pct", 18.0),
            std=peer_stats.get("std_tip_pct", 3.0),
            invert=False,  # Higher tip % is better
        )

        covers_z = self.calculate_zscore(
            value=metrics.avg_covers_per_shift,
            mean=peer_stats.get("avg_covers_per_shift", 20.0),
            std=peer_stats.get("std_covers_per_shift", 5.0),
            invert=False,  # Higher covers is better
        )

        # Convert Z-scores to normalized 0-100 scale
        turn_time_norm = self.zscore_to_normalized(turn_time_z)
        tip_pct_norm = self.zscore_to_normalized(tip_pct_z)
        covers_norm = self.zscore_to_normalized(covers_z)

        # Apply PRD weights
        math_score = (
            turn_time_norm * self.TURN_TIME_WEIGHT +
            tip_pct_norm * self.TIP_PCT_WEIGHT +
            covers_norm * self.COVERS_WEIGHT
        )

        # Clamp to valid range
        math_score = max(self.MIN_SCORE, min(self.MAX_SCORE, math_score))

        return ZScoreResult(
            turn_time_zscore=round(turn_time_z, 2),
            tip_pct_zscore=round(tip_pct_z, 2),
            covers_zscore=round(covers_z, 2),
            math_score=round(math_score, 2),
        )

    def calculate_percentiles(
        self,
        scores: List[float],
    ) -> Dict[str, float]:
        """
        Calculate percentile thresholds from a list of scores.

        Returns:
            {"p25": float, "p50": float, "p75": float}
        """
        if not scores:
            return {"p25": 25.0, "p50": 50.0, "p75": 75.0}

        sorted_scores = sorted(scores)
        n = len(sorted_scores)

        def percentile(p: float) -> float:
            idx = (p / 100) * (n - 1)
            lower = int(idx)
            upper = min(lower + 1, n - 1)
            weight = idx - lower
            return sorted_scores[lower] * (1 - weight) + sorted_scores[upper] * weight

        return {
            "p25": percentile(25),
            "p50": percentile(50),
            "p75": percentile(75),
        }

    def assign_tier(
        self,
        score: float,
        percentiles: Dict[str, float],
    ) -> TierResult:
        """
        Assign tier based on score and percentile thresholds.

        Args:
            score: The composite score (0-100)
            percentiles: Dict with p25 and p75 thresholds

        Returns:
            TierResult with tier assignment
        """
        p25 = percentiles.get("p25", 25.0)
        p75 = percentiles.get("p75", 75.0)

        # Calculate which percentile this score falls into
        if score >= p75:
            tier = "strong"
            # Estimate percentile (75-100 range)
            if p75 < 100:
                pct = 75 + ((score - p75) / (100 - p75)) * 25
            else:
                pct = 100.0
        elif score >= p25:
            tier = "standard"
            # Estimate percentile (25-75 range)
            if p75 > p25:
                pct = 25 + ((score - p25) / (p75 - p25)) * 50
            else:
                pct = 50.0
        else:
            tier = "developing"
            # Estimate percentile (0-25 range)
            if p25 > 0:
                pct = (score / p25) * 25
            else:
                pct = 0.0

        return TierResult(
            tier=tier,
            percentile=round(max(0, min(100, pct)), 1),
            score=score,
        )

    def calculate_all_tiers(
        self,
        metrics_list: List[WaiterMetricsSnapshot],
        peer_stats: Dict[str, float],
    ) -> List[Tuple[WaiterMetricsSnapshot, ZScoreResult, TierResult]]:
        """
        Calculate tiers for all waiters.

        Args:
            metrics_list: List of waiter metrics
            peer_stats: Peer statistics for Z-score calculation

        Returns:
            List of (metrics, zscore_result, tier_result) tuples
        """
        results = []

        # First pass: calculate all math scores
        scored = []
        for metrics in metrics_list:
            zscore_result = self.calculate_math_score(metrics, peer_stats)
            scored.append((metrics, zscore_result))

        # Calculate percentiles from all scores
        all_scores = [s[1].math_score for s in scored]
        percentiles = self.calculate_percentiles(all_scores)

        # Second pass: assign tiers
        for metrics, zscore_result in scored:
            tier_result = self.assign_tier(zscore_result.math_score, percentiles)
            results.append((metrics, zscore_result, tier_result))

        return results

    def get_tier_distribution(
        self,
        tier_results: List[TierResult],
    ) -> Dict[str, int]:
        """Get count of waiters in each tier."""
        distribution = {"strong": 0, "standard": 0, "developing": 0}
        for result in tier_results:
            if result.tier in distribution:
                distribution[result.tier] += 1
        return distribution
