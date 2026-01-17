"""Service for forecasting restaurant demand using weighted historical averages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit


@dataclass
class HourlyForecast:
    """Predicted demand for a specific hour on a specific day."""

    day_of_week: int  # 0=Monday, 6=Sunday
    hour: int  # 0-23
    predicted_covers: float
    confidence_low: float
    confidence_high: float
    trend_adjustment: float  # +/- % from baseline


@dataclass
class DailyForecast:
    """Predicted demand for a full day."""

    date: date
    day_of_week: int
    total_predicted_covers: float
    peak_hour: int
    hourly_forecasts: List[HourlyForecast] = field(default_factory=list)


@dataclass
class WeeklyForecast:
    """Predicted demand for a full week."""

    week_start: date
    restaurant_id: UUID
    overall_trend: str  # "increasing", "stable", "decreasing"
    trend_pct: float  # e.g., +5.2% or -3.1%
    total_predicted_covers: float
    daily_forecasts: List[DailyForecast] = field(default_factory=list)
    hourly_forecasts: List[HourlyForecast] = field(default_factory=list)


@dataclass
class DailyAccuracy:
    """Forecast accuracy for a single day."""

    date: date
    predicted_covers: float
    actual_covers: int
    absolute_error: float
    percentage_error: float


@dataclass
class ForecastAccuracy:
    """Forecast vs actual comparison for a week."""

    week_start: date
    restaurant_id: UUID
    mape: float  # Mean Absolute Percentage Error
    mape_rating: str  # excellent, good, fair, poor
    total_predicted_covers: float
    total_actual_covers: int
    variance_pct: float
    daily_accuracy: List[DailyAccuracy] = field(default_factory=list)


@dataclass
class AccuracyTrend:
    """Historical forecast accuracy trends."""

    restaurant_id: UUID
    weeks: List[ForecastAccuracy] = field(default_factory=list)
    avg_mape: float = 0.0
    trend_direction: str = "stable"  # improving, stable, declining


class DemandForecaster:
    """
    Forecasts restaurant demand using weighted historical averages and trend prediction.

    Algorithm:
    1. Gather historical visit data (last 8-12 weeks, configurable)
    2. Calculate weighted averages (recent weeks weighted higher using exponential decay)
    3. Detect trends using linear regression on weekly totals
    4. Apply trend adjustment to forecast
    5. Return hourly cover predictions with confidence bands
    """

    # Weights decay exponentially: most recent week = 1.0, each prior week *= decay_factor
    DECAY_FACTOR = 0.85
    DEFAULT_LOOKBACK_WEEKS = 8
    CONFIDENCE_BAND_MULTIPLIER = 0.20  # +/- 20% for confidence bands

    def __init__(self, session: AsyncSession):
        self.session = session

    async def forecast_week(
        self,
        restaurant_id: UUID,
        week_start: date,
        lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    ) -> WeeklyForecast:
        """
        Generate hourly demand forecast for a week.

        Args:
            restaurant_id: The restaurant to forecast for
            week_start: Monday of the week to forecast
            lookback_weeks: Number of weeks of historical data to use

        Returns:
            WeeklyForecast with hourly predictions and trend information
        """
        # Get historical data
        historical_data = await self._get_historical_covers(
            restaurant_id,
            week_start,
            lookback_weeks,
        )

        # Calculate weighted averages by day and hour
        weighted_averages = self._calculate_weighted_averages(
            historical_data,
            lookback_weeks,
        )

        # Calculate trend from weekly totals
        trend_pct, trend_label = self._calculate_trend(historical_data)

        # Generate forecasts
        hourly_forecasts = []
        daily_forecasts = []
        total_predicted = 0.0

        for day_offset in range(7):
            forecast_date = week_start + timedelta(days=day_offset)
            day_of_week = forecast_date.weekday()

            day_total = 0.0
            peak_hour = 0
            peak_covers = 0.0
            day_hourly = []

            for hour in range(24):
                base_prediction = weighted_averages.get((day_of_week, hour), 0.0)

                # Apply trend adjustment
                adjusted = base_prediction * (1 + trend_pct / 100)

                # Calculate confidence bands
                confidence_low = adjusted * (1 - self.CONFIDENCE_BAND_MULTIPLIER)
                confidence_high = adjusted * (1 + self.CONFIDENCE_BAND_MULTIPLIER)

                forecast = HourlyForecast(
                    day_of_week=day_of_week,
                    hour=hour,
                    predicted_covers=round(adjusted, 1),
                    confidence_low=round(confidence_low, 1),
                    confidence_high=round(confidence_high, 1),
                    trend_adjustment=round(trend_pct, 1),
                )
                hourly_forecasts.append(forecast)
                day_hourly.append(forecast)

                day_total += adjusted
                if adjusted > peak_covers:
                    peak_covers = adjusted
                    peak_hour = hour

            daily_forecast = DailyForecast(
                date=forecast_date,
                day_of_week=day_of_week,
                total_predicted_covers=round(day_total, 1),
                peak_hour=peak_hour,
                hourly_forecasts=day_hourly,
            )
            daily_forecasts.append(daily_forecast)
            total_predicted += day_total

        return WeeklyForecast(
            week_start=week_start,
            restaurant_id=restaurant_id,
            overall_trend=trend_label,
            trend_pct=round(trend_pct, 1),
            total_predicted_covers=round(total_predicted, 1),
            daily_forecasts=daily_forecasts,
            hourly_forecasts=hourly_forecasts,
        )

    async def forecast_day(
        self,
        restaurant_id: UUID,
        forecast_date: date,
        lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    ) -> DailyForecast:
        """
        Generate hourly demand forecast for a single day.

        Args:
            restaurant_id: The restaurant to forecast for
            forecast_date: The date to forecast
            lookback_weeks: Number of weeks of historical data to use

        Returns:
            DailyForecast with hourly predictions
        """
        # Get historical data for this day of week
        historical_data = await self._get_historical_covers(
            restaurant_id,
            forecast_date,
            lookback_weeks,
        )

        weighted_averages = self._calculate_weighted_averages(
            historical_data,
            lookback_weeks,
        )
        trend_pct, _ = self._calculate_trend(historical_data)

        day_of_week = forecast_date.weekday()
        hourly_forecasts = []
        total = 0.0
        peak_hour = 0
        peak_covers = 0.0

        for hour in range(24):
            base_prediction = weighted_averages.get((day_of_week, hour), 0.0)
            adjusted = base_prediction * (1 + trend_pct / 100)

            forecast = HourlyForecast(
                day_of_week=day_of_week,
                hour=hour,
                predicted_covers=round(adjusted, 1),
                confidence_low=round(adjusted * 0.8, 1),
                confidence_high=round(adjusted * 1.2, 1),
                trend_adjustment=round(trend_pct, 1),
            )
            hourly_forecasts.append(forecast)
            total += adjusted

            if adjusted > peak_covers:
                peak_covers = adjusted
                peak_hour = hour

        return DailyForecast(
            date=forecast_date,
            day_of_week=day_of_week,
            total_predicted_covers=round(total, 1),
            peak_hour=peak_hour,
            hourly_forecasts=hourly_forecasts,
        )

    async def _get_historical_covers(
        self,
        restaurant_id: UUID,
        reference_date: date,
        lookback_weeks: int,
    ) -> List[Tuple[date, int, int, int]]:
        """
        Get historical cover counts grouped by date and hour.

        Returns:
            List of (date, day_of_week, hour, cover_count) tuples
        """
        start_date = reference_date - timedelta(weeks=lookback_weeks)
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(reference_date, time.max)

        # Query visits with seated_at, group by date and hour
        stmt = (
            select(
                func.date(Visit.seated_at).label("visit_date"),
                func.extract("dow", Visit.seated_at).label("day_of_week"),
                func.extract("hour", Visit.seated_at).label("hour"),
                func.sum(Visit.party_size).label("covers"),
            )
            .where(Visit.restaurant_id == restaurant_id)
            .where(Visit.seated_at >= start_dt)
            .where(Visit.seated_at < end_dt)
            .group_by(
                func.date(Visit.seated_at),
                func.extract("dow", Visit.seated_at),
                func.extract("hour", Visit.seated_at),
            )
            .order_by(func.date(Visit.seated_at))
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        # Convert PostgreSQL dow (0=Sunday) to Python weekday (0=Monday)
        data = []
        for row in rows:
            visit_date = row.visit_date
            pg_dow = int(row.day_of_week)  # 0=Sunday in PostgreSQL
            py_dow = (pg_dow - 1) % 7 if pg_dow > 0 else 6  # Convert to 0=Monday
            hour = int(row.hour)
            covers = int(row.covers or 0)
            data.append((visit_date, py_dow, hour, covers))

        return data

    def _calculate_weighted_averages(
        self,
        historical_data: List[Tuple[date, int, int, int]],
        lookback_weeks: int,
    ) -> Dict[Tuple[int, int], float]:
        """
        Calculate weighted averages by (day_of_week, hour).

        More recent weeks are weighted higher using exponential decay.

        Returns:
            Dict mapping (day_of_week, hour) to weighted average covers
        """
        if not historical_data:
            return {}

        # Group by (day_of_week, hour) with week weights
        today = date.today()
        weighted_sums: Dict[Tuple[int, int], float] = {}
        weight_totals: Dict[Tuple[int, int], float] = {}

        for visit_date, day_of_week, hour, covers in historical_data:
            weeks_ago = (today - visit_date).days // 7
            weight = self.DECAY_FACTOR ** weeks_ago

            key = (day_of_week, hour)
            weighted_sums[key] = weighted_sums.get(key, 0.0) + (covers * weight)
            weight_totals[key] = weight_totals.get(key, 0.0) + weight

        # Calculate weighted averages
        averages = {}
        for key in weighted_sums:
            if weight_totals[key] > 0:
                averages[key] = weighted_sums[key] / weight_totals[key]
            else:
                averages[key] = 0.0

        return averages

    def _calculate_trend(
        self,
        historical_data: List[Tuple[date, int, int, int]],
    ) -> Tuple[float, str]:
        """
        Calculate trend using linear regression on weekly totals.

        Returns:
            (trend_pct, trend_label) where trend_label is "increasing", "stable", or "decreasing"
        """
        if not historical_data:
            return 0.0, "stable"

        # Group covers by week
        weekly_totals: Dict[int, int] = {}
        today = date.today()

        for visit_date, _, _, covers in historical_data:
            week_num = (today - visit_date).days // 7
            weekly_totals[week_num] = weekly_totals.get(week_num, 0) + covers

        if len(weekly_totals) < 2:
            return 0.0, "stable"

        # Simple linear regression
        weeks = sorted(weekly_totals.keys())
        n = len(weeks)
        sum_x = sum(weeks)
        sum_y = sum(weekly_totals[w] for w in weeks)
        sum_xy = sum(w * weekly_totals[w] for w in weeks)
        sum_x2 = sum(w * w for w in weeks)

        # Calculate slope
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0, "stable"

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        # Calculate average and trend percentage
        avg_covers = sum_y / n if n > 0 else 1.0
        if avg_covers == 0:
            avg_covers = 1.0

        # Slope is change per week; convert to percentage of average
        trend_pct = (slope / avg_covers) * 100

        # Note: slope is negative for increasing trend because weeks_ago decreases as time moves forward
        trend_pct = -trend_pct  # Invert so positive = increasing

        # Classify trend
        if trend_pct > 3:
            label = "increasing"
        elif trend_pct < -3:
            label = "decreasing"
        else:
            label = "stable"

        return trend_pct, label

    async def get_peak_hours(
        self,
        restaurant_id: UUID,
        day_of_week: int,
        lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    ) -> List[Tuple[int, float]]:
        """
        Get the peak hours for a specific day of week.

        Returns:
            List of (hour, avg_covers) sorted by covers descending
        """
        today = date.today()
        historical_data = await self._get_historical_covers(
            restaurant_id,
            today,
            lookback_weeks,
        )

        weighted_averages = self._calculate_weighted_averages(
            historical_data,
            lookback_weeks,
        )

        # Filter to requested day and sort by covers
        day_hours = [
            (hour, covers)
            for (dow, hour), covers in weighted_averages.items()
            if dow == day_of_week
        ]

        return sorted(day_hours, key=lambda x: x[1], reverse=True)

    async def compare_forecast_to_actual(
        self,
        restaurant_id: UUID,
        week_start: date,
    ) -> ForecastAccuracy:
        """
        Compare forecast predictions to actual covers for a past week.

        Calculates MAPE (Mean Absolute Percentage Error) and provides
        daily breakdown of forecast accuracy.

        Args:
            restaurant_id: The restaurant to analyze
            week_start: Monday of the week to compare

        Returns:
            ForecastAccuracy with MAPE and daily breakdown
        """
        # Get the forecast that would have been made for this week
        forecast = await self.forecast_week(restaurant_id, week_start)

        # Get actual covers from Visit records
        actual_covers_by_day = await self._get_actual_covers_by_day(
            restaurant_id,
            week_start,
        )

        daily_accuracy = []
        total_predicted = 0.0
        total_actual = 0
        percentage_errors = []

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for i, daily_forecast in enumerate(forecast.daily_forecasts):
            day_date = daily_forecast.date
            predicted = daily_forecast.total_predicted_covers
            actual = actual_covers_by_day.get(day_date, 0)

            total_predicted += predicted
            total_actual += actual

            # Calculate absolute error and percentage error
            absolute_error = abs(actual - predicted)

            # Handle division by zero for percentage error
            if actual > 0:
                percentage_error = (absolute_error / actual) * 100
            elif predicted > 0:
                percentage_error = 100.0  # 100% error if predicted but no actual
            else:
                percentage_error = 0.0  # Both zero = perfect match

            percentage_errors.append(percentage_error)

            daily_accuracy.append(DailyAccuracy(
                date=day_date,
                predicted_covers=round(predicted, 1),
                actual_covers=actual,
                absolute_error=round(absolute_error, 1),
                percentage_error=round(percentage_error, 1),
            ))

        # Calculate MAPE
        mape = self._calculate_mape(percentage_errors)
        mape_rating = self._rate_mape(mape)

        # Calculate overall variance percentage
        if total_actual > 0:
            variance_pct = ((total_predicted - total_actual) / total_actual) * 100
        elif total_predicted > 0:
            variance_pct = 100.0
        else:
            variance_pct = 0.0

        return ForecastAccuracy(
            week_start=week_start,
            restaurant_id=restaurant_id,
            mape=round(mape, 1),
            mape_rating=mape_rating,
            total_predicted_covers=round(total_predicted, 1),
            total_actual_covers=total_actual,
            variance_pct=round(variance_pct, 1),
            daily_accuracy=daily_accuracy,
        )

    async def get_accuracy_trends(
        self,
        restaurant_id: UUID,
        weeks: int = 8,
    ) -> AccuracyTrend:
        """
        Get historical forecast accuracy trends.

        Shows how forecast accuracy has changed over time.

        Args:
            restaurant_id: The restaurant to analyze
            weeks: Number of weeks of history

        Returns:
            AccuracyTrend with historical MAPE values
        """
        today = date.today()
        # Find the most recent Monday (or today if it's Monday)
        days_since_monday = today.weekday()
        current_week_start = today - timedelta(days=days_since_monday)

        # Go back to get completed weeks only
        week_accuracies = []
        mape_values = []

        for week_offset in range(1, weeks + 1):  # Start from 1 to skip current incomplete week
            week_start = current_week_start - timedelta(weeks=week_offset)

            try:
                accuracy = await self.compare_forecast_to_actual(
                    restaurant_id,
                    week_start,
                )

                # Only include weeks with actual data
                if accuracy.total_actual_covers > 0:
                    week_accuracies.append(accuracy)
                    mape_values.append(accuracy.mape)
            except Exception:
                # Skip weeks that fail (e.g., no data)
                continue

        if not week_accuracies:
            return AccuracyTrend(
                restaurant_id=restaurant_id,
                trend_direction="stable",
                avg_mape=0.0,
            )

        # Reverse to get chronological order (oldest first)
        week_accuracies.reverse()
        mape_values.reverse()

        # Calculate average MAPE
        avg_mape = sum(mape_values) / len(mape_values)

        # Determine trend direction
        trend_direction = "stable"
        if len(mape_values) >= 3:
            first_half = mape_values[:len(mape_values)//2]
            second_half = mape_values[len(mape_values)//2:]

            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)

            diff = second_avg - first_avg
            # Lower MAPE = improving, higher MAPE = declining
            if diff < -3:
                trend_direction = "improving"
            elif diff > 3:
                trend_direction = "declining"

        return AccuracyTrend(
            restaurant_id=restaurant_id,
            weeks=week_accuracies,
            avg_mape=round(avg_mape, 1),
            trend_direction=trend_direction,
        )

    async def _get_actual_covers_by_day(
        self,
        restaurant_id: UUID,
        week_start: date,
    ) -> Dict[date, int]:
        """
        Get actual cover counts by day for a week.

        Args:
            restaurant_id: The restaurant to query
            week_start: Monday of the week

        Returns:
            Dict mapping date to total covers
        """
        week_end = week_start + timedelta(days=7)
        start_dt = datetime.combine(week_start, time.min)
        end_dt = datetime.combine(week_end, time.min)

        stmt = (
            select(
                func.date(Visit.seated_at).label("visit_date"),
                func.sum(Visit.party_size).label("covers"),
            )
            .where(Visit.restaurant_id == restaurant_id)
            .where(Visit.seated_at >= start_dt)
            .where(Visit.seated_at < end_dt)
            .group_by(func.date(Visit.seated_at))
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return {row.visit_date: int(row.covers or 0) for row in rows}

    def _calculate_mape(self, percentage_errors: List[float]) -> float:
        """
        Calculate Mean Absolute Percentage Error.

        MAPE = (1/n) * sum(|percentage_error|)

        Args:
            percentage_errors: List of percentage errors for each period

        Returns:
            MAPE as a percentage (0 = perfect, lower = better)
        """
        if not percentage_errors:
            return 0.0

        return sum(percentage_errors) / len(percentage_errors)

    def _rate_mape(self, mape: float) -> str:
        """
        Convert MAPE to human-readable rating.

        Args:
            mape: Mean Absolute Percentage Error

        Returns:
            Rating: excellent (<10), good (<20), fair (<30), poor (>=30)
        """
        if mape < 10:
            return "excellent"
        elif mape < 20:
            return "good"
        elif mape < 30:
            return "fair"
        else:
            return "poor"
