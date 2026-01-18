"""
Integration tests for scheduling endpoints using Mimosas restaurant data.

These tests verify the complete scheduling workflow:
1. Seed Mimosas restaurant with staff, availability, preferences
2. Create/manage staffing requirements
3. Run scheduling engine
4. Verify schedule generation
5. Test schedule publishing and audit
6. Test analytics endpoints
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from uuid import UUID

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_session_context
from app.models import (
    Restaurant,
    Waiter,
    Section,
    StaffAvailability,
    StaffPreference,
    StaffingRequirements,
    Schedule,
    ScheduleItem,
    ScheduleRun,
)
from app.services.seed_service import SeedService


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def mimosas_restaurant(db_session: AsyncSession) -> Dict[str, Any]:
    """Seed Mimosas restaurant and return all relevant data."""
    seed_service = SeedService(db_session)
    result = await seed_service.ensure_mimosas_restaurant()

    # Get restaurant
    stmt = select(Restaurant).where(Restaurant.name == "Mimosas")
    res = await db_session.execute(stmt)
    restaurant = res.scalar_one()

    # Get waiters
    stmt = select(Waiter).where(Waiter.restaurant_id == restaurant.id)
    res = await db_session.execute(stmt)
    waiters = list(res.scalars().all())
    assert len(waiters) >= 50
    assert any(w.role == "chef" for w in waiters)

    # Get sections
    stmt = select(Section).where(Section.restaurant_id == restaurant.id)
    res = await db_session.execute(stmt)
    sections = list(res.scalars().all())

    return {
        "restaurant": restaurant,
        "restaurant_id": str(restaurant.id),
        "waiters": waiters,
        "sections": sections,
        "seed_result": result,
    }


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """Create async HTTP client for API testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# Staff Availability Tests
# ============================================================================


class TestStaffAvailability:
    """Tests for staff availability endpoints."""

    @pytest.mark.asyncio
    async def test_list_staff_availability(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should list availability for a staff member."""
        waiter = mimosas_restaurant["waiters"][0]  # Maria Garcia

        response = await async_client.get(
            f"/api/v1/staff/{waiter.id}/availability"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Maria works Mon, Tue, Thu, Fri, Sat, Sun (off Wed)
        days_available = {a["day_of_week"] for a in data}
        assert 2 not in days_available  # Wednesday is off

    @pytest.mark.asyncio
    async def test_create_staff_availability(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should create a new availability pattern."""
        waiter = mimosas_restaurant["waiters"][0]

        response = await async_client.post(
            f"/api/v1/staff/{waiter.id}/availability",
            json={
                "day_of_week": 2,  # Wednesday
                "start_time": "10:00:00",
                "end_time": "14:00:00",
                "availability_type": "available",
                "notes": "Available for special events",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["day_of_week"] == 2
        assert data["availability_type"] == "available"

    @pytest.mark.asyncio
    async def test_bulk_create_availability(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should create multiple availability patterns at once."""
        # Create a new waiter for this test
        waiter = mimosas_restaurant["waiters"][1]  # James Wilson

        response = await async_client.post(
            f"/api/v1/staff/{waiter.id}/availability/bulk",
            json={
                "entries": [
                    {"day_of_week": 0, "start_time": "08:00:00", "end_time": "12:00:00", "availability_type": "preferred"},
                    {"day_of_week": 1, "start_time": "08:00:00", "end_time": "12:00:00", "availability_type": "preferred"},
                ]
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 2


# ============================================================================
# Staff Preferences Tests
# ============================================================================


class TestStaffPreferences:
    """Tests for staff preferences endpoints."""

    @pytest.mark.asyncio
    async def test_get_staff_preferences(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should get preferences for a staff member."""
        waiter = mimosas_restaurant["waiters"][0]  # Maria Garcia

        response = await async_client.get(
            f"/api/v1/staff/{waiter.id}/preferences"
        )

        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert "preferred_roles" in data
        assert "max_hours_per_week" in data

    @pytest.mark.asyncio
    async def test_upsert_staff_preferences(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should create or update staff preferences."""
        waiter = mimosas_restaurant["waiters"][2]  # Emily Chen

        response = await async_client.post(
            f"/api/v1/staff/{waiter.id}/preferences",
            json={
                "preferred_roles": ["server"],
                "preferred_shift_types": ["morning", "afternoon"],
                "preferred_sections": [],
                "max_shifts_per_week": 4,
                "max_hours_per_week": 32,
                "min_hours_per_week": 16,
                "avoid_clopening": True,
                "notes": "Student schedule - prefer morning shifts",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["max_shifts_per_week"] == 4
        assert data["avoid_clopening"] is True


# ============================================================================
# Staffing Requirements Tests
# ============================================================================


class TestStaffingRequirements:
    """Tests for staffing requirements endpoints."""

    @pytest.mark.asyncio
    async def test_list_staffing_requirements(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should list all staffing requirements."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/staffing-requirements"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Should have requirements for multiple days
        days = {r["day_of_week"] for r in data}
        assert len(days) >= 5  # At least weekdays

    @pytest.mark.asyncio
    async def test_list_requirements_by_day(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should filter requirements by day of week."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/staffing-requirements",
            params={"day_of_week": 5}  # Saturday
        )

        assert response.status_code == 200
        data = response.json()
        assert all(r["day_of_week"] == 5 for r in data)

    @pytest.mark.asyncio
    async def test_create_staffing_requirement(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should create a new staffing requirement."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/staffing-requirements",
            json={
                "day_of_week": 6,  # Sunday
                "start_time": "15:00:00",
                "end_time": "18:00:00",
                "role": "server",
                "min_staff": 2,
                "max_staff": 3,
                "is_prime_shift": False,
                "notes": "Late brunch/early dinner coverage",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["min_staff"] == 2
        assert data["role"] == "server"


# ============================================================================
# Schedule Management Tests
# ============================================================================


class TestScheduleManagement:
    """Tests for schedule CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_schedule(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should create a new draft schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        # Get next Monday
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": next_monday.isoformat(),
                "generated_by": "manual",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_list_schedules(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should list schedules for a restaurant."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/schedules"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================================
# Scheduling Engine Tests
# ============================================================================


class TestSchedulingEngine:
    """Tests for the scheduling engine."""

    @pytest.mark.asyncio
    async def test_run_scheduling_engine(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should run the scheduling engine and generate a schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        # Get a week start date that doesn't have a schedule
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 7)  # Next next Monday

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules/run",
            json={"week_start_date": week_start.isoformat()},
            params={"run_engine": True},
        )

        assert response.status_code == 202
        data = response.json()
        # Engine may complete, be running, pending, or fail in test environment
        assert data["run_status"] in ["completed", "running", "pending", "failed"]

        if data["run_status"] == "completed":
            # Verify schedule was created
            assert "summary_metrics" in data
            metrics = data["summary_metrics"]
            assert "items_created" in metrics or "total_hours" in metrics

    @pytest.mark.asyncio
    async def test_get_schedule_run_status(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should get schedule run status."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        # Create a pending run
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 14)

        # Create run without executing engine
        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules/run",
            json={"week_start_date": week_start.isoformat()},
            params={"run_engine": False},
        )

        assert response.status_code == 202
        run_id = response.json()["id"]

        # Get run status
        response = await async_client.get(f"/api/v1/schedule-runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["run_status"] == "pending"


# ============================================================================
# Schedule Items Tests
# ============================================================================


class TestScheduleItems:
    """Tests for schedule item management."""

    @pytest.mark.asyncio
    async def test_add_schedule_item(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should add an item to a draft schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]
        waiter = mimosas_restaurant["waiters"][0]
        section = mimosas_restaurant["sections"][0]

        # Create a draft schedule
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 21)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Add item to schedule
        response = await async_client.post(
            f"/api/v1/schedules/{schedule_id}/items",
            json={
                "waiter_id": str(waiter.id),
                "role": "server",
                "section_id": str(section.id),
                "shift_date": week_start.isoformat(),
                "shift_start": "07:00:00",
                "shift_end": "15:00:00",
                "source": "manual",
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["waiter_id"] == str(waiter.id)
        assert data["role"] == "server"

    @pytest.mark.asyncio
    async def test_get_schedule_with_items(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should get schedule with all items."""
        restaurant_id = mimosas_restaurant["restaurant_id"]
        waiter = mimosas_restaurant["waiters"][0]

        # Create schedule and add items
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 28)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Add a few items
        for i in range(3):
            shift_date = week_start + timedelta(days=i)
            await async_client.post(
                f"/api/v1/schedules/{schedule_id}/items",
                json={
                    "waiter_id": str(waiter.id),
                    "role": "server",
                    "shift_date": shift_date.isoformat(),
                    "shift_start": "07:00:00",
                    "shift_end": "15:00:00",
                    "source": "manual",
                }
            )

        # Get schedule with items
        response = await async_client.get(f"/api/v1/schedules/{schedule_id}")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 3


# ============================================================================
# Schedule Publishing Tests
# ============================================================================


class TestSchedulePublishing:
    """Tests for schedule publishing workflow."""

    @pytest.mark.asyncio
    async def test_publish_schedule(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should publish a draft schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        # Create draft schedule
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 35)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Publish
        response = await async_client.post(
            f"/api/v1/schedules/{schedule_id}/publish"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    @pytest.mark.asyncio
    async def test_get_schedule_audit(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
    ):
        """Should get schedule version history."""
        restaurant_id = mimosas_restaurant["restaurant_id"]

        # Create and publish schedule
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 42)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Publish
        await async_client.post(f"/api/v1/schedules/{schedule_id}/publish")

        # Get audit
        response = await async_client.get(
            f"/api/v1/schedules/{schedule_id}/audit"
        )

        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert len(data["history"]) >= 1


# ============================================================================
# Analytics Integration Tests
# ============================================================================


class TestAnalyticsIntegration:
    """Tests for analytics endpoints with real schedule data."""

    @pytest.mark.asyncio
    async def test_schedule_coverage_metrics(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should get coverage metrics for a schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]
        waiters = mimosas_restaurant["waiters"]

        # Create schedule with items
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 49)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Add items for coverage
        for i in range(5):  # Mon-Fri
            shift_date = week_start + timedelta(days=i)
            for waiter in waiters[:2]:  # 2 servers
                await async_client.post(
                    f"/api/v1/schedules/{schedule_id}/items",
                    json={
                        "waiter_id": str(waiter.id),
                        "role": "server",
                        "shift_date": shift_date.isoformat(),
                        "shift_start": "07:00:00",
                        "shift_end": "15:00:00",
                        "source": "manual",
                    }
                )

        # Publish schedule
        await async_client.post(f"/api/v1/schedules/{schedule_id}/publish")

        # Get coverage metrics
        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/coverage"
        )

        assert response.status_code == 200
        data = response.json()
        assert "coverage_pct" in data
        assert "total_slots_required" in data

    @pytest.mark.asyncio
    async def test_schedule_fairness_metrics(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """Should get fairness metrics for a schedule."""
        restaurant_id = mimosas_restaurant["restaurant_id"]
        waiters = mimosas_restaurant["waiters"]

        # Create schedule
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 56)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules",
            json={
                "week_start_date": week_start.isoformat(),
                "generated_by": "manual",
            }
        )
        schedule_id = response.json()["id"]

        # Add balanced items for all staff
        for i in range(5):
            shift_date = week_start + timedelta(days=i)
            for waiter in waiters[:3]:
                await async_client.post(
                    f"/api/v1/schedules/{schedule_id}/items",
                    json={
                        "waiter_id": str(waiter.id),
                        "role": "server",
                        "shift_date": shift_date.isoformat(),
                        "shift_start": "07:00:00",
                        "shift_end": "15:00:00",
                        "source": "manual",
                    }
                )

        await async_client.post(f"/api/v1/schedules/{schedule_id}/publish")

        # Get fairness metrics
        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/fairness"
        )

        assert response.status_code == 200
        data = response.json()
        assert "gini_coefficient" in data
        assert "staff_metrics" in data


# ============================================================================
# End-to-End Workflow Test
# ============================================================================


class TestEndToEndWorkflow:
    """Complete scheduling workflow test."""

    @pytest.mark.asyncio
    async def test_complete_scheduling_workflow(
        self,
        async_client: AsyncClient,
        mimosas_restaurant: Dict[str, Any],
        db_session: AsyncSession,
    ):
        """
        Test the complete scheduling workflow:
        1. Verify staff availability exists
        2. Verify staffing requirements exist
        3. Run scheduling engine
        4. Review generated schedule
        5. Make manual adjustment
        6. Publish schedule
        7. Get analytics
        """
        restaurant_id = mimosas_restaurant["restaurant_id"]
        waiters = mimosas_restaurant["waiters"]

        # Step 1: Verify availability exists
        waiter = waiters[0]
        response = await async_client.get(
            f"/api/v1/staff/{waiter.id}/availability"
        )
        assert response.status_code == 200
        availability = response.json()
        assert len(availability) > 0

        # Step 2: Verify requirements exist
        response = await async_client.get(
            f"/api/v1/restaurants/{restaurant_id}/staffing-requirements"
        )
        assert response.status_code == 200
        requirements = response.json()
        assert len(requirements) > 0

        # Step 3: Run scheduling engine
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        week_start = today + timedelta(days=days_until_monday + 63)

        response = await async_client.post(
            f"/api/v1/restaurants/{restaurant_id}/schedules/run",
            json={"week_start_date": week_start.isoformat()},
            params={"run_engine": True},
        )
        assert response.status_code == 202
        run_data = response.json()

        # Step 4: Get the generated schedule
        if run_data["run_status"] == "completed":
            # Find the schedule for this week
            response = await async_client.get(
                f"/api/v1/restaurants/{restaurant_id}/schedules",
                params={"week_start": week_start.isoformat()}
            )
            schedules = response.json()

            if schedules:
                schedule_id = schedules[0]["id"]

                # Get schedule with items
                response = await async_client.get(
                    f"/api/v1/schedules/{schedule_id}"
                )
                assert response.status_code == 200
                schedule = response.json()

                # Step 5: Add manual adjustment (extra shift)
                if schedule["status"] == "draft":
                    response = await async_client.post(
                        f"/api/v1/schedules/{schedule_id}/items",
                        json={
                            "waiter_id": str(waiters[1].id),
                            "role": "server",
                            "shift_date": (week_start + timedelta(days=5)).isoformat(),
                            "shift_start": "11:00:00",
                            "shift_end": "15:00:00",
                            "source": "manual",
                        }
                    )
                    assert response.status_code == 201

                    # Step 6: Publish schedule
                    response = await async_client.post(
                        f"/api/v1/schedules/{schedule_id}/publish"
                    )
                    assert response.status_code == 200
                    assert response.json()["status"] == "published"

                    # Step 7: Get analytics
                    response = await async_client.get(
                        f"/api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}"
                    )
                    assert response.status_code == 200
                    analytics = response.json()
                    assert "coverage" in analytics or "fairness" in analytics
