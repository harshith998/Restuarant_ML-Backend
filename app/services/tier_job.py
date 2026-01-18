"""Weekly tier recalculation job orchestrator."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.restaurant import Restaurant
from app.models.waiter import Waiter
from app.models.insights import WaiterInsights
from app.services.metrics_aggregator import MetricsAggregator
from app.services.tier_calculator import TierCalculator
from app.services.llm_scorer import LLMScorer, LLMScoringResult

logger = logging.getLogger(__name__)


@dataclass
class TierJobResult:
    """Result from tier recalculation job."""

    success: bool
    waiters_processed: int = 0
    waiters_updated: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class TierRecalculationJob:
    """
    Weekly job to recalculate all waiter tiers.

    Flow:
    1. Get all active waiters (or specific restaurant)
    2. Compute 30-day metrics for each
    3. Calculate math scores with Z-normalization
    4. Call LLM for each waiter (optional)
    5. Determine percentiles and assign tiers
    6. Save WaiterInsights records
    7. Update Waiter.tier and Waiter.composite_score
    """

    def __init__(
        self,
        session: AsyncSession,
    ):
        """
        Initialize the tier recalculation job.

        Args:
            session: Database session
        """
        self.session = session
        self.metrics_aggregator = MetricsAggregator(session)
        self.tier_calculator = TierCalculator()
        self.llm_scorer = LLMScorer()

    async def run(
        self,
        restaurant_id: Optional[UUID] = None,
        use_llm: bool = True,
        days: int = 30,
    ) -> TierJobResult:
        """
        Main entry point for tier recalculation.

        Args:
            restaurant_id: Specific restaurant, or None for all
            use_llm: Whether to use LLM for scoring
            days: Lookback window in days

        Returns:
            TierJobResult with stats
        """
        result = TierJobResult(
            success=False,
            started_at=datetime.utcnow(),
        )

        try:
            # Get restaurants to process
            if restaurant_id:
                restaurants = [await self._get_restaurant(restaurant_id)]
                restaurants = [r for r in restaurants if r is not None]
            else:
                restaurants = await self._get_all_restaurants()

            if not restaurants:
                result.errors.append("No restaurants found")
                result.completed_at = datetime.utcnow()
                return result

            # Process each restaurant
            for restaurant in restaurants:
                try:
                    processed, updated, errors = await self._process_restaurant(
                        restaurant=restaurant,
                        use_llm=use_llm,
                        days=days,
                    )
                    result.waiters_processed += processed
                    result.waiters_updated += updated
                    result.errors.extend(errors)
                except Exception as e:
                    logger.error(f"Error processing restaurant {restaurant.id}: {e}")
                    result.errors.append(f"Restaurant {restaurant.name}: {str(e)}")

            result.success = len(result.errors) == 0
            result.completed_at = datetime.utcnow()

            logger.info(
                f"Tier recalculation complete: "
                f"{result.waiters_processed} processed, "
                f"{result.waiters_updated} updated, "
                f"{len(result.errors)} errors"
            )

            return result

        except Exception as e:
            logger.error(f"Tier recalculation job failed: {e}")
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
            return result

    async def run_for_waiter(
        self,
        waiter_id: UUID,
        use_llm: bool = True,
        days: int = 30,
    ) -> TierJobResult:
        """
        Recalculate tier for a single waiter.

        Args:
            waiter_id: The waiter to recalculate
            use_llm: Whether to use LLM scoring
            days: Lookback window

        Returns:
            TierJobResult
        """
        result = TierJobResult(
            success=False,
            started_at=datetime.utcnow(),
        )

        try:
            waiter = await self._get_waiter(waiter_id)
            if waiter is None:
                result.errors.append(f"Waiter {waiter_id} not found")
                result.completed_at = datetime.utcnow()
                return result

            # Get peer stats for context
            peer_stats = await self.metrics_aggregator.compute_peer_stats(
                restaurant_id=waiter.restaurant_id,
                days=days,
            )

            # Compute this waiter's metrics
            metrics = await self.metrics_aggregator.compute_waiter_metrics(
                waiter_id=waiter_id,
                days=days,
            )

            # Calculate math score
            zscore_result = self.tier_calculator.calculate_math_score(
                metrics=metrics,
                peer_stats=peer_stats,
            )

            # Get monthly trends
            monthly_trends = await self.metrics_aggregator.get_monthly_trends(
                waiter_id=waiter_id,
                months=6,
            )

            # LLM scoring (optional)
            llm_result: Optional[LLMScoringResult] = None
            if use_llm:
                llm_result = await self.llm_scorer.score_waiter(
                    waiter=waiter,
                    metrics=metrics,
                    math_score=zscore_result.math_score,
                    zscore_result=zscore_result,
                    peer_stats=peer_stats,
                    monthly_trends=monthly_trends,
                )

            # Determine final score (LLM score if available, else math score)
            final_score = llm_result.llm_score if llm_result else zscore_result.math_score

            # Get percentiles from all waiters in restaurant
            all_metrics = await self.metrics_aggregator.compute_all_waiter_metrics(
                restaurant_id=waiter.restaurant_id,
                days=days,
            )
            all_scores = []
            for m in all_metrics:
                zr = self.tier_calculator.calculate_math_score(m, peer_stats)
                all_scores.append(zr.math_score)

            percentiles = self.tier_calculator.calculate_percentiles(all_scores)
            tier_result = self.tier_calculator.assign_tier(final_score, percentiles)

            # Save insights
            await self._save_insights(
                waiter=waiter,
                metrics=metrics,
                zscore_result=zscore_result,
                llm_result=llm_result,
                tier=tier_result.tier,
                final_score=final_score,
                monthly_trends=monthly_trends,
            )

            # Update waiter
            waiter.tier = tier_result.tier
            waiter.composite_score = final_score
            waiter.tier_updated_at = datetime.utcnow()

            await self.session.commit()

            result.success = True
            result.waiters_processed = 1
            result.waiters_updated = 1
            result.completed_at = datetime.utcnow()

            return result

        except Exception as e:
            logger.error(f"Error recalculating waiter {waiter_id}: {e}")
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
            return result

    async def _process_restaurant(
        self,
        restaurant: Restaurant,
        use_llm: bool,
        days: int,
    ) -> tuple[int, int, List[str]]:
        """Process all waiters in a restaurant."""
        processed = 0
        updated = 0
        errors = []

        # Get all waiter metrics
        all_metrics = await self.metrics_aggregator.compute_all_waiter_metrics(
            restaurant_id=restaurant.id,
            days=days,
        )

        if not all_metrics:
            return processed, updated, errors

        # Get peer stats
        peer_stats = await self.metrics_aggregator.compute_peer_stats(
            restaurant_id=restaurant.id,
            days=days,
        )

        # Calculate all scores for percentile calculation
        all_scored = self.tier_calculator.calculate_all_tiers(all_metrics, peer_stats)

        # Extract just scores for percentile calculation
        all_scores = [s[1].math_score for s in all_scored]
        percentiles = self.tier_calculator.calculate_percentiles(all_scores)

        # Process each waiter
        for metrics, zscore_result, tier_result in all_scored:
            try:
                waiter = await self._get_waiter(metrics.waiter_id)
                if waiter is None:
                    continue

                processed += 1

                # Get monthly trends
                monthly_trends = await self.metrics_aggregator.get_monthly_trends(
                    waiter_id=waiter.id,
                    months=6,
                )

                # LLM scoring (optional)
                llm_result: Optional[LLMScoringResult] = None
                if use_llm:
                    try:
                        llm_result = await self.llm_scorer.score_waiter(
                            waiter=waiter,
                            metrics=metrics,
                            math_score=zscore_result.math_score,
                            zscore_result=zscore_result,
                            peer_stats=peer_stats,
                            monthly_trends=monthly_trends,
                        )
                    except Exception as e:
                        logger.warning(f"LLM scoring failed for {waiter.id}: {e}")
                        errors.append(f"LLM error for {waiter.name}: {str(e)}")

                # Determine final score
                final_score = llm_result.llm_score if llm_result else zscore_result.math_score

                # Recalculate tier with final score
                final_tier_result = self.tier_calculator.assign_tier(final_score, percentiles)

                # Save insights
                await self._save_insights(
                    waiter=waiter,
                    metrics=metrics,
                    zscore_result=zscore_result,
                    llm_result=llm_result,
                    tier=final_tier_result.tier,
                    final_score=final_score,
                    monthly_trends=monthly_trends,
                )

                # Update waiter
                waiter.tier = final_tier_result.tier
                waiter.composite_score = final_score
                waiter.tier_updated_at = datetime.utcnow()

                updated += 1

            except Exception as e:
                logger.error(f"Error processing waiter {metrics.waiter_id}: {e}")
                errors.append(f"Waiter {metrics.waiter_id}: {str(e)}")

        # Commit all changes
        await self.session.commit()

        return processed, updated, errors

    async def _save_insights(
        self,
        waiter: Waiter,
        metrics,
        zscore_result,
        llm_result: Optional[LLMScoringResult],
        tier: str,
        final_score: float,
        monthly_trends: dict,
    ) -> WaiterInsights:
        """Save or update waiter insights."""
        today = date.today()

        # Check for existing insights for this period
        stmt = (
            select(WaiterInsights)
            .where(WaiterInsights.waiter_id == waiter.id)
            .where(WaiterInsights.period_start == metrics.period_start)
        )
        result = await self.session.execute(stmt)
        insights = result.scalar_one_or_none()

        if insights is None:
            insights = WaiterInsights(
                waiter_id=waiter.id,
                restaurant_id=waiter.restaurant_id,
                period_start=metrics.period_start,
            )
            self.session.add(insights)

        # Update fields
        insights.math_score = zscore_result.math_score
        insights.llm_score = llm_result.llm_score if llm_result else None
        insights.composite_score = final_score
        insights.tier = tier

        insights.turn_time_zscore = zscore_result.turn_time_zscore
        insights.tip_pct_zscore = zscore_result.tip_pct_zscore
        insights.covers_zscore = zscore_result.covers_zscore

        if llm_result:
            insights.strengths = llm_result.strengths
            insights.areas_to_watch = llm_result.areas_to_watch
            insights.suggestions = llm_result.suggestions
            insights.llm_summary = llm_result.summary
            insights.llm_model = llm_result.model_used

        insights.monthly_trends = monthly_trends
        insights.metrics_snapshot = {
            "avg_turn_time_minutes": metrics.avg_turn_time_minutes,
            "avg_tip_percentage": metrics.avg_tip_percentage,
            "avg_covers_per_shift": metrics.avg_covers_per_shift,
            "total_tips": metrics.total_tips,
            "total_covers": metrics.total_covers,
            "tables_served": metrics.tables_served,
            "shifts_worked": metrics.shifts_worked,
        }

        insights.period_end = metrics.period_end
        insights.computed_at = datetime.utcnow()

        # Flag modified for JSON columns
        flag_modified(insights, "strengths")
        flag_modified(insights, "areas_to_watch")
        flag_modified(insights, "suggestions")
        flag_modified(insights, "monthly_trends")
        flag_modified(insights, "metrics_snapshot")

        await self.session.flush()

        return insights

    async def _get_restaurant(self, restaurant_id: UUID) -> Optional[Restaurant]:
        """Get restaurant by ID."""
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_all_restaurants(self) -> List[Restaurant]:
        """Get all active restaurants."""
        stmt = select(Restaurant)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_waiter(self, waiter_id: UUID) -> Optional[Waiter]:
        """Get waiter by ID."""
        stmt = select(Waiter).where(Waiter.id == waiter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
