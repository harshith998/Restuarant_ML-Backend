"""Service for generating LLM-enhanced schedule insights."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Schedule, ScheduleInsights, ScheduleItem, Waiter
from app.services.fairness_calculator import FairnessReport
from app.services.llm_scorer import LLMResponseParser
from app.services.schedule_analytics import (
    CoverageMetrics,
    ScheduleAnalyticsService,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Dataclass Results
# ============================================================================


@dataclass
class ScheduleInsight:
    """Single insight about a schedule."""

    category: str  # coverage, fairness, pattern
    severity: str  # info, warning, critical
    message: str
    affected_staff: List[UUID] = field(default_factory=list)
    affected_staff_names: List[str] = field(default_factory=list)
    metric_value: Optional[float] = None
    recommendation: Optional[str] = None


@dataclass
class ScheduleInsightsReport:
    """Complete insights report for a schedule."""

    schedule_id: UUID
    week_start: date
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Categorized insights
    coverage_insights: List[ScheduleInsight] = field(default_factory=list)
    fairness_insights: List[ScheduleInsight] = field(default_factory=list)
    pattern_insights: List[ScheduleInsight] = field(default_factory=list)

    # Counts
    total_insights: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    # LLM summary
    llm_summary: Optional[str] = None
    llm_model: Optional[str] = None


# ============================================================================
# LLM Helper Functions
# ============================================================================


async def call_llm(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> str:
    """
    Call OpenRouter LLM API.

    Args:
        prompt: The prompt to send
        model: Model identifier (defaults to settings.llm_model)
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature

    Returns:
        Response text from the LLM
    """
    settings = get_settings()

    if not settings.llm_enabled:
        raise RuntimeError("LLM is disabled")

    if not settings.llm_api_key:
        raise RuntimeError("LLM API key not configured")

    model = model or settings.llm_model

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://restaurant-intel.app",
        "X-Title": "Restaurant Intelligence Platform",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.llm_api_base}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        # Extract content from OpenAI-compatible response
        return data["choices"][0]["message"]["content"]


# ============================================================================
# Service
# ============================================================================


class ScheduleInsightsService:
    """
    LLM-enhanced insights generation for schedules.

    Generates actionable insights about:
    - Coverage gaps
    - Fairness issues
    - Scheduling patterns (clopening, consecutive days)
    - Performance concerns
    """

    DEFAULT_MODEL = "bytedance-seed/seed-1.6"
    CACHE_EXPIRY_HOURS = 24
    CLOPENING_MIN_HOURS = 10  # Minimum hours between shifts to avoid clopening

    def __init__(
        self,
        session: AsyncSession,
        call_llm_func: Optional[callable] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize insights service.

        Args:
            session: Database session
            call_llm_func: Optional custom LLM function (for testing)
            model: LLM model to use
        """
        self.session = session
        self._call_llm = call_llm_func or call_llm
        self.model = model or self.DEFAULT_MODEL
        self.analytics = ScheduleAnalyticsService(session)

    async def generate_insights(
        self,
        schedule_id: UUID,
        use_llm: bool = True,
        force_refresh: bool = False,
    ) -> ScheduleInsightsReport:
        """
        Generate comprehensive insights for a schedule.

        Steps:
        1. Check cache (ScheduleInsights model) first
        2. If expired or missing, generate fresh insights
        3. Optionally enhance with LLM summary

        Args:
            schedule_id: The schedule to analyze
            use_llm: Whether to use LLM for summary generation
            force_refresh: Force regeneration even if cached

        Returns:
            ScheduleInsightsReport with categorized insights
        """
        # Load schedule
        schedule = await self._load_schedule(schedule_id)
        if not schedule:
            return ScheduleInsightsReport(
                schedule_id=schedule_id,
                week_start=date.today(),
            )

        # Check cache
        if not force_refresh:
            cached = await self._get_cached_insights(schedule_id)
            if cached and not cached.needs_refresh(schedule.version):
                return self._convert_cached_to_report(cached, schedule)

        # Generate fresh insights
        coverage = await self.analytics.get_coverage_metrics(schedule_id)
        fairness = await self.analytics.get_fairness_metrics(schedule_id)

        # Detect patterns
        coverage_insights = await self._detect_coverage_gaps(coverage)
        fairness_insights = await self._detect_fairness_issues(fairness)
        pattern_insights = await self._detect_clopening_patterns(schedule_id)

        # Count by severity
        all_insights = coverage_insights + fairness_insights + pattern_insights
        critical_count = sum(1 for i in all_insights if i.severity == "critical")
        warning_count = sum(1 for i in all_insights if i.severity == "warning")
        info_count = sum(1 for i in all_insights if i.severity == "info")

        # Build report
        report = ScheduleInsightsReport(
            schedule_id=schedule_id,
            week_start=schedule.week_start_date,
            coverage_insights=coverage_insights,
            fairness_insights=fairness_insights,
            pattern_insights=pattern_insights,
            total_insights=len(all_insights),
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
        )

        # Generate LLM summary if requested and available
        if use_llm and all_insights:
            try:
                summary = await self._generate_llm_summary(report, coverage, fairness)
                report.llm_summary = summary
                report.llm_model = self.model
            except Exception as e:
                logger.warning(f"LLM summary generation failed: {e}")

        # Cache the results
        await self._cache_insights(schedule, report, coverage, fairness)

        return report

    async def _detect_coverage_gaps(
        self,
        coverage: CoverageMetrics,
    ) -> List[ScheduleInsight]:
        """
        Generate insights about coverage gaps.

        Flags:
        - Overall coverage below 90% (warning)
        - Overall coverage below 80% (critical)
        - Specific days with low coverage
        - Specific shifts consistently understaffed
        """
        insights = []

        # Overall coverage
        if coverage.coverage_pct < 80:
            insights.append(ScheduleInsight(
                category="coverage",
                severity="critical",
                message=f"Overall coverage is critically low at {coverage.coverage_pct}%",
                metric_value=coverage.coverage_pct,
                recommendation="Add more staff assignments to meet minimum requirements",
            ))
        elif coverage.coverage_pct < 90:
            insights.append(ScheduleInsight(
                category="coverage",
                severity="warning",
                message=f"Overall coverage is below target at {coverage.coverage_pct}%",
                metric_value=coverage.coverage_pct,
                recommendation="Consider adding staff to understaffed shifts",
            ))

        # Daily coverage issues
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for daily in coverage.daily_coverage:
            if daily.coverage_pct < 80:
                insights.append(ScheduleInsight(
                    category="coverage",
                    severity="warning",
                    message=f"{day_names[daily.day_of_week]} coverage is low at {daily.coverage_pct}%",
                    metric_value=daily.coverage_pct,
                    recommendation=f"Add staff for {day_names[daily.day_of_week]}",
                ))

        # Understaffed slots
        if len(coverage.understaffed_slots) > 3:
            total_shortfall = sum(s.shortfall for s in coverage.understaffed_slots)
            insights.append(ScheduleInsight(
                category="coverage",
                severity="warning",
                message=f"{len(coverage.understaffed_slots)} time slots are understaffed (total shortfall: {total_shortfall} positions)",
                metric_value=float(total_shortfall),
                recommendation="Review staffing requirements or add more assignments",
            ))

        # Shift type coverage
        for shift_type, pct in coverage.shift_coverage.items():
            if pct < 80:
                insights.append(ScheduleInsight(
                    category="coverage",
                    severity="warning",
                    message=f"{shift_type.title()} shift coverage is low at {pct}%",
                    metric_value=pct,
                    recommendation=f"Add more staff for {shift_type} shifts",
                ))

        return insights

    async def _detect_fairness_issues(
        self,
        fairness: FairnessReport,
    ) -> List[ScheduleInsight]:
        """
        Generate insights about fairness issues.

        Flags:
        - High Gini coefficient (>0.25)
        - Staff with significantly more/fewer hours than average
        - Uneven prime shift distribution
        """
        insights = []

        # Gini coefficient
        if fairness.gini_coefficient > 0.30:
            insights.append(ScheduleInsight(
                category="fairness",
                severity="critical",
                message=f"Hours distribution is highly unequal (Gini: {fairness.gini_coefficient:.2f})",
                metric_value=fairness.gini_coefficient,
                recommendation="Redistribute hours more evenly across staff",
            ))
        elif fairness.gini_coefficient > 0.25:
            insights.append(ScheduleInsight(
                category="fairness",
                severity="warning",
                message=f"Hours distribution is somewhat unequal (Gini: {fairness.gini_coefficient:.2f})",
                metric_value=fairness.gini_coefficient,
                recommendation="Consider balancing hours among staff",
            ))

        # Prime shift Gini
        if fairness.prime_shift_gini > 0.30:
            insights.append(ScheduleInsight(
                category="fairness",
                severity="warning",
                message=f"Prime shifts (Fri/Sat evening) are unevenly distributed (Gini: {fairness.prime_shift_gini:.2f})",
                metric_value=fairness.prime_shift_gini,
                recommendation="Rotate prime shifts more fairly among staff",
            ))

        # Individual staff issues
        if fairness.staff_metrics:
            avg_hours = sum(s.weekly_hours for s in fairness.staff_metrics) / len(fairness.staff_metrics)

            overworked = [s for s in fairness.staff_metrics if s.weekly_hours > avg_hours * 1.3]
            underworked = [s for s in fairness.staff_metrics if s.weekly_hours < avg_hours * 0.7]

            if overworked:
                names = [s.name for s in overworked]
                insights.append(ScheduleInsight(
                    category="fairness",
                    severity="warning",
                    message=f"{len(overworked)} staff member(s) have significantly more hours than average",
                    affected_staff=[s.waiter_id for s in overworked],
                    affected_staff_names=names,
                    recommendation=f"Consider redistributing hours from: {', '.join(names)}",
                ))

            if underworked:
                names = [s.name for s in underworked]
                insights.append(ScheduleInsight(
                    category="fairness",
                    severity="info",
                    message=f"{len(underworked)} staff member(s) have significantly fewer hours than average",
                    affected_staff=[s.waiter_id for s in underworked],
                    affected_staff_names=names,
                    recommendation=f"Consider adding shifts for: {', '.join(names)}",
                ))

        # Existing fairness issues from calculator
        for issue in fairness.fairness_issues:
            insights.append(ScheduleInsight(
                category="fairness",
                severity="warning",
                message=issue,
            ))

        return insights

    async def _detect_clopening_patterns(
        self,
        schedule_id: UUID,
    ) -> List[ScheduleInsight]:
        """
        Detect close-open (clopening) patterns.

        A clopening is when staff works a closing shift followed by
        an opening shift with less than 10 hours between.
        """
        insights = []

        # Load schedule items with waiter info
        stmt = (
            select(ScheduleItem)
            .where(ScheduleItem.schedule_id == schedule_id)
            .options(selectinload(ScheduleItem.waiter))
            .order_by(ScheduleItem.waiter_id, ScheduleItem.shift_date, ScheduleItem.shift_start)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        if not items:
            return insights

        # Group by waiter
        by_waiter: Dict[UUID, List[ScheduleItem]] = {}
        for item in items:
            if item.waiter_id not in by_waiter:
                by_waiter[item.waiter_id] = []
            by_waiter[item.waiter_id].append(item)

        # Check for clopening patterns
        clopening_staff = []
        clopening_count = 0

        for waiter_id, waiter_items in by_waiter.items():
            # Sort by date and time
            waiter_items.sort(key=lambda x: (x.shift_date, x.shift_start))

            for i in range(len(waiter_items) - 1):
                current = waiter_items[i]
                next_shift = waiter_items[i + 1]

                # Calculate hours between shifts
                current_end = datetime.combine(current.shift_date, current.shift_end)
                # Handle overnight shifts
                if current.shift_end < current.shift_start:
                    current_end = datetime.combine(
                        current.shift_date + timedelta(days=1),
                        current.shift_end
                    )

                next_start = datetime.combine(next_shift.shift_date, next_shift.shift_start)
                hours_between = (next_start - current_end).total_seconds() / 3600

                if 0 < hours_between < self.CLOPENING_MIN_HOURS:
                    clopening_count += 1
                    if current.waiter and current.waiter.name not in clopening_staff:
                        clopening_staff.append(current.waiter.name)

        if clopening_count > 0:
            severity = "critical" if clopening_count >= 3 else "warning"
            insights.append(ScheduleInsight(
                category="pattern",
                severity=severity,
                message=f"{clopening_count} clopening pattern(s) detected ({len(clopening_staff)} staff affected)",
                affected_staff_names=clopening_staff,
                metric_value=float(clopening_count),
                recommendation="Ensure at least 10 hours between closing and opening shifts",
            ))

        # Check for consecutive days
        for waiter_id, waiter_items in by_waiter.items():
            dates_worked = sorted(set(item.shift_date for item in waiter_items))
            if len(dates_worked) >= 6:
                waiter_name = waiter_items[0].waiter.name if waiter_items[0].waiter else "Unknown"
                insights.append(ScheduleInsight(
                    category="pattern",
                    severity="warning",
                    message=f"{waiter_name} is scheduled for {len(dates_worked)} consecutive days",
                    affected_staff_names=[waiter_name],
                    metric_value=float(len(dates_worked)),
                    recommendation="Consider giving at least one day off per week",
                ))

        return insights

    async def _generate_llm_summary(
        self,
        report: ScheduleInsightsReport,
        coverage: CoverageMetrics,
        fairness: FairnessReport,
    ) -> str:
        """
        Generate LLM-enhanced summary of insights.

        Returns:
            Human-readable summary paragraph
        """
        prompt = self._build_summary_prompt(report, coverage, fairness)

        try:
            response = await self._call_llm(
                prompt=prompt,
                model=self.model,
                max_tokens=500,
                temperature=0.5,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._generate_fallback_summary(report)

    def _build_summary_prompt(
        self,
        report: ScheduleInsightsReport,
        coverage: CoverageMetrics,
        fairness: FairnessReport,
    ) -> str:
        """Build prompt for LLM summary generation."""
        insights_text = []

        for insight in report.coverage_insights[:3]:
            insights_text.append(f"- [{insight.severity.upper()}] {insight.message}")

        for insight in report.fairness_insights[:3]:
            insights_text.append(f"- [{insight.severity.upper()}] {insight.message}")

        for insight in report.pattern_insights[:3]:
            insights_text.append(f"- [{insight.severity.upper()}] {insight.message}")

        prompt = f"""You are a restaurant scheduling analyst. Summarize the following schedule insights in 2-3 sentences for a manager.

Schedule for week of {report.week_start}:
- Coverage: {coverage.coverage_pct}%
- Fairness (Gini): {fairness.gini_coefficient:.2f}
- Critical issues: {report.critical_count}
- Warnings: {report.warning_count}

Key insights:
{chr(10).join(insights_text) if insights_text else "No significant issues detected."}

Provide a brief, actionable summary that highlights the most important points. Be concise and direct."""

        return prompt

    def _generate_fallback_summary(self, report: ScheduleInsightsReport) -> str:
        """Generate summary without LLM."""
        parts = []

        if report.critical_count > 0:
            parts.append(f"{report.critical_count} critical issue(s) require immediate attention")

        if report.warning_count > 0:
            parts.append(f"{report.warning_count} warning(s) should be reviewed")

        if not parts:
            return "No significant scheduling issues detected."

        return ". ".join(parts) + "."

    # =========================================================================
    # Cache Methods
    # =========================================================================

    async def _get_cached_insights(self, schedule_id: UUID) -> Optional[ScheduleInsights]:
        """Get cached insights from database."""
        stmt = select(ScheduleInsights).where(ScheduleInsights.schedule_id == schedule_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _cache_insights(
        self,
        schedule: Schedule,
        report: ScheduleInsightsReport,
        coverage: CoverageMetrics,
        fairness: FairnessReport,
    ) -> None:
        """Cache insights to database."""
        # Check if exists
        existing = await self._get_cached_insights(schedule.id)

        if existing:
            # Update existing
            existing.coverage_pct = coverage.coverage_pct
            existing.gini_coefficient = fairness.gini_coefficient
            existing.avg_preference_score = None  # Will be set separately
            existing.critical_count = report.critical_count
            existing.warning_count = report.warning_count
            existing.info_count = report.info_count
            existing.coverage_insights = [self._insight_to_dict(i) for i in report.coverage_insights]
            existing.fairness_insights = [self._insight_to_dict(i) for i in report.fairness_insights]
            existing.pattern_insights = [self._insight_to_dict(i) for i in report.pattern_insights]
            existing.llm_summary = report.llm_summary
            existing.llm_model = report.llm_model
            existing.schedule_version = schedule.version
            existing.generated_at = datetime.utcnow()
            existing.expires_at = datetime.utcnow() + timedelta(hours=self.CACHE_EXPIRY_HOURS)
        else:
            # Create new
            new_cache = ScheduleInsights(
                schedule_id=schedule.id,
                restaurant_id=schedule.restaurant_id,
                coverage_pct=coverage.coverage_pct,
                gini_coefficient=fairness.gini_coefficient,
                critical_count=report.critical_count,
                warning_count=report.warning_count,
                info_count=report.info_count,
                coverage_insights=[self._insight_to_dict(i) for i in report.coverage_insights],
                fairness_insights=[self._insight_to_dict(i) for i in report.fairness_insights],
                pattern_insights=[self._insight_to_dict(i) for i in report.pattern_insights],
                llm_summary=report.llm_summary,
                llm_model=report.llm_model,
                schedule_version=schedule.version,
            )
            self.session.add(new_cache)

        await self.session.commit()

    def _insight_to_dict(self, insight: ScheduleInsight) -> Dict[str, Any]:
        """Convert insight to dictionary for JSON storage."""
        return {
            "category": insight.category,
            "severity": insight.severity,
            "message": insight.message,
            "affected_staff": [str(s) for s in insight.affected_staff],
            "affected_staff_names": insight.affected_staff_names,
            "metric_value": insight.metric_value,
            "recommendation": insight.recommendation,
        }

    def _dict_to_insight(self, data: Dict[str, Any]) -> ScheduleInsight:
        """Convert dictionary to insight."""
        return ScheduleInsight(
            category=data.get("category", "unknown"),
            severity=data.get("severity", "info"),
            message=data.get("message", ""),
            affected_staff=[UUID(s) for s in data.get("affected_staff", [])],
            affected_staff_names=data.get("affected_staff_names", []),
            metric_value=data.get("metric_value"),
            recommendation=data.get("recommendation"),
        )

    def _convert_cached_to_report(
        self,
        cached: ScheduleInsights,
        schedule: Schedule,
    ) -> ScheduleInsightsReport:
        """Convert cached insights to report."""
        return ScheduleInsightsReport(
            schedule_id=cached.schedule_id,
            week_start=schedule.week_start_date,
            generated_at=cached.generated_at,
            coverage_insights=[self._dict_to_insight(d) for d in (cached.coverage_insights or [])],
            fairness_insights=[self._dict_to_insight(d) for d in (cached.fairness_insights or [])],
            pattern_insights=[self._dict_to_insight(d) for d in (cached.pattern_insights or [])],
            total_insights=cached.critical_count + cached.warning_count + cached.info_count,
            critical_count=cached.critical_count,
            warning_count=cached.warning_count,
            info_count=cached.info_count,
            llm_summary=cached.llm_summary,
            llm_model=cached.llm_model,
        )

    async def _load_schedule(self, schedule_id: UUID) -> Optional[Schedule]:
        """Load a schedule."""
        stmt = (
            select(Schedule)
            .where(Schedule.id == schedule_id)
            .options(selectinload(Schedule.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
