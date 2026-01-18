"""LLM-powered waiter scoring and insights generation with robust parsing."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.waiter import Waiter
from app.services.metrics_aggregator import WaiterMetricsSnapshot
from app.services.tier_calculator import ZScoreResult
from app.services.llm_client import call_llm, LLMError

logger = logging.getLogger(__name__)

# System prompt for waiter scoring
WAITER_SCORING_SYSTEM_PROMPT = """You are a restaurant analytics expert specializing in waiter performance evaluation.

Your task is to analyze waiter metrics and provide:
1. A performance score (0-100) based on the data provided
2. Key strengths (3-5 points)
3. Areas that need attention (1-3 points, or none if performing excellently)
4. Actionable suggestions for improvement (1-2 recommendations)
5. A brief summary (2-3 sentences)

Scoring methodology context:
- Turn time: Lower is better (faster table turnover)
- Tip percentage: Higher is better (customer satisfaction indicator)
- Covers per shift: Higher is better (efficiency indicator)
- Z-scores show standard deviations from peer average (positive = above average)

Always respond with valid JSON in the exact format specified."""


@dataclass
class LLMScoringResult:
    """Result from LLM scoring."""

    llm_score: float
    strengths: List[str] = field(default_factory=list)
    areas_to_watch: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    summary: str = ""
    raw_response: str = ""
    parse_errors: List[str] = field(default_factory=list)
    model_used: str = ""


class LLMResponseParser:
    """
    Robust parser for LLM responses.

    Handles various output formats:
    - Clean JSON
    - JSON with markdown code blocks
    - Partial/malformed JSON
    - Plain text responses
    """

    @staticmethod
    def extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from LLM response, handling various formats.

        Tries multiple extraction strategies in order of preference.
        """
        if not response:
            return None

        # Strategy 1: Direct JSON parse
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code blocks
        code_block_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # ```json ... ```
            r'```\s*([\s\S]*?)\s*```',       # ``` ... ```
            r'`([\s\S]*?)`',                  # ` ... `
        ]

        for pattern in code_block_patterns:
            matches = re.findall(pattern, response)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Strategy 3: Find JSON object in response
        json_patterns = [
            r'\{[\s\S]*"llm_score"[\s\S]*\}',  # Look for object with llm_score
            r'\{[\s\S]*"strengths"[\s\S]*\}',   # Look for object with strengths
            r'\{[^{}]*\}',                       # Any simple JSON object
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, response)
            for match in matches:
                try:
                    # Try to fix common JSON issues
                    fixed = LLMResponseParser._fix_json_string(match)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

        return None

    @staticmethod
    def _fix_json_string(json_str: str) -> str:
        """Attempt to fix common JSON formatting issues."""
        # Replace single quotes with double quotes
        fixed = re.sub(r"'([^']*)':", r'"\1":', json_str)
        fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)

        # Remove trailing commas
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

        # Escape unescaped newlines in strings
        fixed = re.sub(r'(?<!\\)\n', r'\\n', fixed)

        return fixed

    @staticmethod
    def extract_score_from_text(response: str) -> Optional[float]:
        """Extract score from plain text response."""
        patterns = [
            r'(?:score|rating)[:\s]+(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(?:/\s*100|out of 100)',
            r'(?:final|overall)[:\s]+(\d+(?:\.\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, response.lower())
            if match:
                try:
                    score = float(match.group(1))
                    if 0 <= score <= 100:
                        return score
                except ValueError:
                    continue

        return None

    @staticmethod
    def extract_list_items(response: str, section_name: str) -> List[str]:
        """Extract bullet points from a named section."""
        # Find section header
        pattern = rf'{section_name}[:\s]*([\s\S]*?)(?=\n[A-Z]|\n\n\n|\Z)'
        match = re.search(pattern, response, re.IGNORECASE)

        if not match:
            return []

        section_text = match.group(1)

        # Extract bullet points
        bullets = re.findall(r'[-*•]\s*(.+?)(?=\n|$)', section_text)

        # Clean up
        return [b.strip() for b in bullets if b.strip()]

    @classmethod
    def parse_response(
        cls,
        response: str,
        fallback_score: float = 50.0,
    ) -> LLMScoringResult:
        """
        Parse LLM response with multiple fallback strategies.

        Args:
            response: Raw LLM response text
            fallback_score: Score to use if parsing fails

        Returns:
            LLMScoringResult with extracted data
        """
        result = LLMScoringResult(
            llm_score=fallback_score,
            raw_response=response,
        )

        if not response:
            result.parse_errors.append("Empty response")
            return result

        # Try JSON extraction first
        json_data = cls.extract_json_from_response(response)

        if json_data:
            # Successfully parsed JSON
            try:
                if "llm_score" in json_data:
                    score = float(json_data["llm_score"])
                    if 0 <= score <= 100:
                        result.llm_score = score
                    else:
                        result.parse_errors.append(f"Score {score} out of range")

                if "strengths" in json_data:
                    result.strengths = cls._ensure_string_list(json_data["strengths"])

                if "areas_to_watch" in json_data:
                    result.areas_to_watch = cls._ensure_string_list(json_data["areas_to_watch"])

                if "suggestions" in json_data:
                    result.suggestions = cls._ensure_string_list(json_data["suggestions"])

                if "summary" in json_data:
                    result.summary = str(json_data.get("summary", ""))

                return result

            except Exception as e:
                result.parse_errors.append(f"JSON value extraction failed: {e}")

        # Fallback: Try text extraction
        text_score = cls.extract_score_from_text(response)
        if text_score is not None:
            result.llm_score = text_score

        # Extract sections from text
        if not result.strengths:
            result.strengths = cls.extract_list_items(response, "strengths")

        if not result.areas_to_watch:
            result.areas_to_watch = cls.extract_list_items(response, "areas")

        if not result.suggestions:
            result.suggestions = cls.extract_list_items(response, "suggestions")

        # If still empty, try to find any bullet points
        if not result.strengths and not result.areas_to_watch:
            all_bullets = re.findall(r'[-*•]\s*(.+?)(?=\n|$)', response)
            if all_bullets:
                # Heuristic: positive items likely strengths, negative likely areas
                for bullet in all_bullets[:5]:
                    if any(word in bullet.lower() for word in ['improve', 'lower', 'concern', 'watch']):
                        result.areas_to_watch.append(bullet.strip())
                    else:
                        result.strengths.append(bullet.strip())

        if not result.summary:
            # Use first paragraph as summary
            paragraphs = response.split('\n\n')
            for p in paragraphs:
                p = p.strip()
                if len(p) > 50 and not p.startswith('{'):
                    result.summary = p[:500]
                    break

        return result

    @staticmethod
    def _ensure_string_list(value: Any) -> List[str]:
        """Ensure value is a list of strings."""
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str):
            return [value]
        return []


class LLMScorer:
    """
    LLM-powered waiter scoring and insights generation.

    Uses call_llm from llm_client to interact with OpenRouter API.
    """

    def __init__(self):
        """Initialize LLM scorer."""
        pass

    async def score_waiter(
        self,
        waiter: Waiter,
        metrics: WaiterMetricsSnapshot,
        math_score: float,
        zscore_result: ZScoreResult,
        peer_stats: Dict[str, float],
        monthly_trends: Optional[Dict[str, Dict]] = None,
    ) -> LLMScoringResult:
        """
        Generate LLM-powered score and insights for a waiter.

        Args:
            waiter: The waiter model
            metrics: Computed metrics snapshot
            math_score: PRD formula math score
            zscore_result: Z-score calculation results
            peer_stats: Peer statistics for context
            monthly_trends: Optional monthly trend data

        Returns:
            LLMScoringResult with score and insights
        """
        user_prompt = self._build_user_prompt(
            waiter=waiter,
            metrics=metrics,
            math_score=math_score,
            zscore_result=zscore_result,
            peer_stats=peer_stats,
            monthly_trends=monthly_trends,
        )

        # Call LLM
        try:
            response = await call_llm(
                system_prompt=WAITER_SCORING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,  # Lower for more consistent scoring
                max_tokens=1000,
                response_format="json",
            )

            # Response is already parsed as dict by call_llm
            result = LLMScoringResult(
                llm_score=float(response.get("llm_score", math_score)),
                strengths=response.get("strengths", []),
                areas_to_watch=response.get("areas_to_watch", []),
                suggestions=response.get("suggestions", []),
                summary=response.get("summary", ""),
                raw_response=json.dumps(response),
                model_used="openrouter",
            )

            # Validate score range
            if not 0 <= result.llm_score <= 100:
                result.llm_score = math_score
                result.parse_errors.append(f"Score out of range, using math score")

            return result

        except LLMError as e:
            logger.error(f"LLM scoring failed: {e}")
            return LLMScoringResult(
                llm_score=math_score,
                strengths=self._generate_fallback_strengths(metrics, peer_stats),
                areas_to_watch=self._generate_fallback_areas(metrics, peer_stats),
                suggestions=["Continue current performance"],
                summary=f"LLM analysis unavailable: {str(e)}",
                parse_errors=[str(e)],
                model_used="fallback",
            )
        except Exception as e:
            logger.error(f"LLM scoring failed unexpectedly: {e}")
            return LLMScoringResult(
                llm_score=math_score,
                strengths=self._generate_fallback_strengths(metrics, peer_stats),
                areas_to_watch=[],
                suggestions=[],
                summary=f"LLM analysis unavailable: {str(e)}",
                parse_errors=[str(e)],
                model_used="fallback",
            )

    def _build_user_prompt(
        self,
        waiter: Waiter,
        metrics: WaiterMetricsSnapshot,
        math_score: float,
        zscore_result: ZScoreResult,
        peer_stats: Dict[str, float],
        monthly_trends: Optional[Dict[str, Dict]] = None,
    ) -> str:
        """Build the user prompt with waiter data for LLM analysis."""
        # Calculate tenure
        tenure_years = 0.0
        if waiter.created_at:
            tenure_days = (datetime.utcnow() - waiter.created_at).days
            tenure_years = round(tenure_days / 365.25, 1)

        # Format trends
        trends_summary = "No trend data available."
        if monthly_trends:
            trend_lines = []
            for month, data in sorted(monthly_trends.items())[-3:]:
                trend_lines.append(
                    f"  - {month}: ${data.get('tips', 0):.0f} tips, "
                    f"{data.get('covers', 0)} covers"
                )
            if trend_lines:
                trends_summary = "\n".join(trend_lines)

        prompt = f"""Analyze this waiter's performance data:

## Waiter Profile
Name: {waiter.name}
Tenure: {tenure_years} years
Current Tier: {waiter.tier}
Math Score: {math_score:.1f}/100

## Z-Score Breakdown
- Turn Time Z-Score: {zscore_result.turn_time_zscore:+.2f} ({"faster" if zscore_result.turn_time_zscore > 0 else "slower"} than average)
- Tip % Z-Score: {zscore_result.tip_pct_zscore:+.2f} ({"higher" if zscore_result.tip_pct_zscore > 0 else "lower"} than average)
- Covers Z-Score: {zscore_result.covers_zscore:+.2f} ({"more" if zscore_result.covers_zscore > 0 else "fewer"} than average)

## 30-Day Metrics
- Avg Turn Time: {metrics.avg_turn_time_minutes:.0f} min (peer avg: {peer_stats.get('avg_turn_time', 45):.0f} min)
- Tip Percentage: {metrics.avg_tip_percentage:.1f}% (peer avg: {peer_stats.get('avg_tip_pct', 18):.1f}%)
- Covers/Shift: {metrics.avg_covers_per_shift:.1f} (peer avg: {peer_stats.get('avg_covers_per_shift', 20):.1f})
- Tables Served: {metrics.tables_served}
- Total Tips: ${metrics.total_tips:.2f}
- Shifts Worked: {metrics.shifts_worked}

## Recent Monthly Trends
{trends_summary}

Respond with JSON in this exact format:
{{
  "llm_score": <float between 0 and 100>,
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "areas_to_watch": ["area 1"],
  "suggestions": ["suggestion 1"],
  "summary": "<2-3 sentence analysis>"
}}"""

        return prompt

    def _generate_fallback_strengths(
        self,
        metrics: WaiterMetricsSnapshot,
        peer_stats: Dict[str, float],
    ) -> List[str]:
        """Generate strengths based on metrics when LLM is unavailable."""
        strengths = []

        # Check turn time
        if metrics.avg_turn_time_minutes < peer_stats.get("avg_turn_time", 45):
            diff = peer_stats.get("avg_turn_time", 45) - metrics.avg_turn_time_minutes
            strengths.append(f"Fast table turns ({metrics.avg_turn_time_minutes:.0f}min avg, {diff:.0f}min faster than peers)")

        # Check tip percentage
        if metrics.avg_tip_percentage > peer_stats.get("avg_tip_pct", 18):
            strengths.append(f"High tip percentage ({metrics.avg_tip_percentage:.1f}%)")

        # Check covers
        if metrics.avg_covers_per_shift > peer_stats.get("avg_covers_per_shift", 20):
            strengths.append(f"High volume ({metrics.avg_covers_per_shift:.0f} covers/shift)")

        # Add generic strength if none found
        if not strengths:
            strengths.append("Consistent performance")

        return strengths[:5]

    def _generate_fallback_areas(
        self,
        metrics: WaiterMetricsSnapshot,
        peer_stats: Dict[str, float],
    ) -> List[str]:
        """Generate areas to watch based on metrics when LLM is unavailable."""
        areas = []

        # Check if significantly below average
        if metrics.avg_turn_time_minutes > peer_stats.get("avg_turn_time", 45) * 1.2:
            areas.append("Table turn time above average")

        if metrics.avg_tip_percentage < peer_stats.get("avg_tip_pct", 18) * 0.8:
            areas.append("Tip percentage below peer average")

        if metrics.avg_covers_per_shift < peer_stats.get("avg_covers_per_shift", 20) * 0.8:
            areas.append("Covers per shift below average")

        return areas[:3]
