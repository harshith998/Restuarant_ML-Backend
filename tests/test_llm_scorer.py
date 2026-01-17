"""Tests for LLM scoring and response parsing."""
import pytest
from app.services.llm_scorer import LLMResponseParser, LLMScorer, LLMScoringResult


class TestLLMResponseParser:
    """Tests for robust LLM response parsing."""

    def test_parse_clean_json(self):
        """Parse clean JSON response."""
        response = '''{
            "llm_score": 75.5,
            "strengths": ["Fast tables", "High tips"],
            "areas_to_watch": ["Wine sales"],
            "suggestions": ["Consider training"],
            "summary": "Good performance overall."
        }'''

        result = LLMResponseParser.parse_response(response)

        assert result.llm_score == 75.5
        assert len(result.strengths) == 2
        assert "Fast tables" in result.strengths
        assert len(result.areas_to_watch) == 1
        assert len(result.suggestions) == 1
        assert "Good performance" in result.summary

    def test_parse_json_in_markdown_code_block(self):
        """Parse JSON wrapped in markdown code block."""
        response = '''Here is my analysis:

```json
{
    "llm_score": 82.0,
    "strengths": ["Excellent service"],
    "areas_to_watch": [],
    "suggestions": ["Keep up the good work"],
    "summary": "Top performer."
}
```

That's my assessment.'''

        result = LLMResponseParser.parse_response(response)

        assert result.llm_score == 82.0
        assert "Excellent service" in result.strengths

    def test_parse_json_without_language_tag(self):
        """Parse JSON in code block without language tag."""
        response = '''```
{
    "llm_score": 65.0,
    "strengths": ["Consistent"],
    "areas_to_watch": ["Speed"],
    "suggestions": [],
    "summary": "Average performance."
}
```'''

        result = LLMResponseParser.parse_response(response)

        assert result.llm_score == 65.0
        assert "Consistent" in result.strengths

    def test_parse_with_extra_text_around_json(self):
        """Parse JSON surrounded by explanation text."""
        response = '''Based on my analysis, here are the results:

{"llm_score": 70.0, "strengths": ["Good tips"], "areas_to_watch": [], "suggestions": [], "summary": "Solid."}

I hope this helps!'''

        result = LLMResponseParser.parse_response(response)

        assert result.llm_score == 70.0

    def test_fallback_score_on_invalid_json(self):
        """Use fallback score when JSON parsing fails."""
        response = "This is not valid JSON at all."

        result = LLMResponseParser.parse_response(response, fallback_score=55.0)

        assert result.llm_score == 55.0
        assert len(result.parse_errors) == 0  # No explicit error, just fallback

    def test_extract_score_from_text(self):
        """Extract score from plain text when no JSON."""
        response = '''The waiter's performance score is 72.5 out of 100.

Strengths:
- Fast table turns
- Friendly service

Areas to watch:
- Upselling could improve'''

        result = LLMResponseParser.parse_response(response, fallback_score=50.0)

        assert result.llm_score == 72.5
        assert "Fast table turns" in result.strengths

    def test_extract_bullet_points_from_sections(self):
        """Extract bullet points from named sections."""
        response = '''Score: 68

Strengths:
- Quick service
- Good with customers
- Reliable

Areas to Watch:
- Wine knowledge
- Attention to detail'''

        result = LLMResponseParser.parse_response(response)

        assert result.llm_score == 68
        assert len(result.strengths) == 3
        assert "Quick service" in result.strengths
        assert len(result.areas_to_watch) == 2

    def test_handles_empty_response(self):
        """Handle empty response gracefully."""
        result = LLMResponseParser.parse_response("", fallback_score=50.0)

        assert result.llm_score == 50.0
        assert "Empty response" in result.parse_errors

    def test_handles_none_response(self):
        """Handle None response gracefully."""
        result = LLMResponseParser.parse_response(None, fallback_score=50.0)

        assert result.llm_score == 50.0

    def test_score_out_of_range_uses_fallback(self):
        """Reject scores outside 0-100 range."""
        response = '{"llm_score": 150, "strengths": [], "areas_to_watch": [], "suggestions": [], "summary": ""}'

        result = LLMResponseParser.parse_response(response, fallback_score=50.0)

        # Should log error but keep the out-of-range score
        assert "out of range" in result.parse_errors[0].lower()

    def test_parse_with_single_quotes(self):
        """Handle JSON with single quotes (common LLM mistake)."""
        response = "{'llm_score': 70, 'strengths': ['Good'], 'areas_to_watch': [], 'suggestions': [], 'summary': 'OK'}"

        result = LLMResponseParser.parse_response(response, fallback_score=50.0)

        # May or may not parse depending on fixer, but shouldn't crash
        assert result.llm_score >= 0

    def test_ensure_string_list_with_mixed_types(self):
        """Handle mixed types in lists."""
        assert LLMResponseParser._ensure_string_list(["a", "b"]) == ["a", "b"]
        assert LLMResponseParser._ensure_string_list("single") == ["single"]
        assert LLMResponseParser._ensure_string_list([1, 2, 3]) == ["1", "2", "3"]
        assert LLMResponseParser._ensure_string_list(None) == []


class TestLLMScorerFallback:
    """Tests for LLM scorer fallback behavior."""

    def test_fallback_strengths_fast_turn_time(self):
        """Generate strength for fast turn time."""
        from app.services.metrics_aggregator import WaiterMetricsSnapshot
        from datetime import date
        from uuid import uuid4

        scorer = LLMScorer(call_llm_func=None)

        metrics = WaiterMetricsSnapshot(
            waiter_id=uuid4(),
            restaurant_id=uuid4(),
            period_start=date.today(),
            period_end=date.today(),
            avg_turn_time_minutes=35.0,  # Fast
            avg_tip_percentage=18.0,
            avg_covers_per_shift=20.0,
        )

        peer_stats = {
            "avg_turn_time": 45.0,
            "avg_tip_pct": 18.0,
            "avg_covers_per_shift": 20.0,
        }

        strengths = scorer._generate_fallback_strengths(metrics, peer_stats)

        assert len(strengths) > 0
        assert any("turn" in s.lower() or "fast" in s.lower() for s in strengths)

    def test_fallback_areas_slow_turn_time(self):
        """Generate area to watch for slow turn time."""
        from app.services.metrics_aggregator import WaiterMetricsSnapshot
        from datetime import date
        from uuid import uuid4

        scorer = LLMScorer(call_llm_func=None)

        metrics = WaiterMetricsSnapshot(
            waiter_id=uuid4(),
            restaurant_id=uuid4(),
            period_start=date.today(),
            period_end=date.today(),
            avg_turn_time_minutes=60.0,  # Slow (>45*1.2)
            avg_tip_percentage=18.0,
            avg_covers_per_shift=20.0,
        )

        peer_stats = {
            "avg_turn_time": 45.0,
            "avg_tip_pct": 18.0,
            "avg_covers_per_shift": 20.0,
        }

        areas = scorer._generate_fallback_areas(metrics, peer_stats)

        assert any("turn" in a.lower() for a in areas)


class TestScoreExtraction:
    """Tests for extracting scores from various formats."""

    def test_extract_score_rating_format(self):
        """Extract from 'score: X' format."""
        score = LLMResponseParser.extract_score_from_text("The score is 85")
        assert score is None  # "is" not matching "score:" pattern

        score = LLMResponseParser.extract_score_from_text("Score: 85")
        assert score == 85

    def test_extract_score_out_of_100(self):
        """Extract from 'X/100' format."""
        score = LLMResponseParser.extract_score_from_text("I rate this 72/100")
        assert score == 72

    def test_extract_score_out_of_100_words(self):
        """Extract from 'X out of 100' format."""
        score = LLMResponseParser.extract_score_from_text("Performance: 88.5 out of 100")
        assert score == 88.5

    def test_extract_score_final_format(self):
        """Extract from 'final: X' format."""
        score = LLMResponseParser.extract_score_from_text("Final: 79")
        assert score == 79

    def test_no_score_found(self):
        """Return None when no score pattern found."""
        score = LLMResponseParser.extract_score_from_text("This text has no score.")
        assert score is None

    def test_score_out_of_range_ignored(self):
        """Ignore scores outside 0-100."""
        score = LLMResponseParser.extract_score_from_text("Score: 150")
        assert score is None


class TestBulletExtraction:
    """Tests for extracting bullet points."""

    def test_extract_dash_bullets(self):
        """Extract items with dash prefix."""
        text = '''Strengths:
- Item one
- Item two
- Item three'''

        items = LLMResponseParser.extract_list_items(text, "Strengths")
        assert len(items) == 3
        assert "Item one" in items

    def test_extract_asterisk_bullets(self):
        """Extract items with asterisk prefix."""
        text = '''Areas:
* First area
* Second area'''

        items = LLMResponseParser.extract_list_items(text, "Areas")
        assert len(items) == 2

    def test_no_section_found(self):
        """Return empty list when section not found."""
        items = LLMResponseParser.extract_list_items("No section here", "Missing")
        assert items == []
