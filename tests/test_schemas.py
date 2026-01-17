"""
Tests for Pydantic schemas.

These tests verify schema validation catches real-world input errors:
- Invalid party sizes
- Missing required fields
- Enum validation
- Field constraints
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate, RestaurantRead
from app.schemas.section import SectionCreate, SectionRead
from app.schemas.table import TableCreate, TableStateUpdate, TableType, TableState
from app.schemas.waiter import WaiterCreate, WaiterUpdate, WaiterTier
from app.schemas.waitlist import WaitlistCreate, TablePreference, WaitlistStatus
from app.schemas.visit import VisitCreate, VisitUpdate
from app.schemas.routing import RouteRequest, RouteResponse


class TestRestaurantSchemas:
    """Tests for Restaurant schema validation."""

    def test_valid_restaurant_create(self):
        """Test creating a restaurant with valid data."""
        data = RestaurantCreate(
            name="Test Restaurant",
            timezone="America/Los_Angeles",
            config={"routing": {"mode": "section"}},
        )
        assert data.name == "Test Restaurant"

    def test_restaurant_name_required(self):
        """Test that restaurant name is required."""
        with pytest.raises(ValidationError) as exc_info:
            RestaurantCreate(timezone="America/New_York")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_restaurant_name_min_length(self):
        """Test that empty restaurant names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RestaurantCreate(name="")

        errors = exc_info.value.errors()
        assert any("min_length" in str(e) for e in errors)

    def test_restaurant_update_partial(self):
        """Test that update schema allows partial updates."""
        data = RestaurantUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.timezone is None
        assert data.config is None


class TestTableSchemas:
    """Tests for Table schema validation."""

    def test_valid_table_create(self):
        """Test creating a table with valid data."""
        data = TableCreate(
            restaurant_id=uuid4(),
            table_number="T1",
            capacity=4,
            table_type=TableType.TABLE,
        )
        assert data.capacity == 4
        assert data.table_type == TableType.TABLE

    def test_table_capacity_bounds(self):
        """Test that table capacity must be between 1 and 20."""
        # Too small
        with pytest.raises(ValidationError):
            TableCreate(
                restaurant_id=uuid4(),
                table_number="T1",
                capacity=0,
                table_type=TableType.TABLE,
            )

        # Too large
        with pytest.raises(ValidationError):
            TableCreate(
                restaurant_id=uuid4(),
                table_number="T1",
                capacity=25,
                table_type=TableType.TABLE,
            )

    def test_table_type_enum(self):
        """Test that table type must be valid enum value."""
        with pytest.raises(ValidationError):
            TableCreate(
                restaurant_id=uuid4(),
                table_number="T1",
                capacity=4,
                table_type="invalid_type",
            )

    def test_table_state_update_source(self):
        """Test that state update source must be ml, host, or system."""
        # Valid sources
        for source in ["ml", "host", "system"]:
            data = TableStateUpdate(state=TableState.OCCUPIED, source=source)
            assert data.source == source

        # Invalid source
        with pytest.raises(ValidationError):
            TableStateUpdate(state=TableState.OCCUPIED, source="invalid")

    def test_table_state_confidence_bounds(self):
        """Test that confidence must be between 0 and 1."""
        with pytest.raises(ValidationError):
            TableStateUpdate(
                state=TableState.OCCUPIED,
                source="ml",
                confidence=1.5,  # Invalid: > 1
            )


class TestWaitlistSchemas:
    """Tests for Waitlist schema validation."""

    def test_valid_waitlist_create(self):
        """Test creating a waitlist entry with valid data."""
        data = WaitlistCreate(
            restaurant_id=uuid4(),
            party_name="Johnson",
            party_size=4,
            table_preference=TablePreference.BOOTH,
            quoted_wait_minutes=15,
        )
        assert data.party_size == 4
        assert data.table_preference == TablePreference.BOOTH

    def test_party_size_bounds(self):
        """Test that party size must be between 1 and 20."""
        # Valid edge cases
        small = WaitlistCreate(restaurant_id=uuid4(), party_size=1)
        large = WaitlistCreate(restaurant_id=uuid4(), party_size=20)
        assert small.party_size == 1
        assert large.party_size == 20

        # Invalid
        with pytest.raises(ValidationError):
            WaitlistCreate(restaurant_id=uuid4(), party_size=0)

        with pytest.raises(ValidationError):
            WaitlistCreate(restaurant_id=uuid4(), party_size=21)

    def test_table_preference_enum(self):
        """Test that table preference must be valid enum."""
        # All valid preferences
        for pref in TablePreference:
            data = WaitlistCreate(
                restaurant_id=uuid4(),
                party_size=2,
                table_preference=pref,
            )
            assert data.table_preference == pref

    def test_quoted_wait_non_negative(self):
        """Test that quoted wait time cannot be negative."""
        with pytest.raises(ValidationError):
            WaitlistCreate(
                restaurant_id=uuid4(),
                party_size=2,
                quoted_wait_minutes=-5,
            )


class TestVisitSchemas:
    """Tests for Visit schema validation."""

    def test_valid_visit_create(self):
        """Test creating a visit with all required fields."""
        now = datetime.utcnow()
        data = VisitCreate(
            restaurant_id=uuid4(),
            table_id=uuid4(),
            waiter_id=uuid4(),
            shift_id=uuid4(),
            party_size=4,
            seated_at=now,
        )
        assert data.party_size == 4

    def test_visit_update_payment(self):
        """Test updating visit with payment information."""
        data = VisitUpdate(
            subtotal=95.50,
            tax=7.64,
            total=103.14,
            tip=20.00,
            pos_transaction_id="TXN_12345",
        )
        assert data.total == 103.14
        assert data.tip == 20.00

    def test_visit_payment_non_negative(self):
        """Test that payment amounts cannot be negative."""
        with pytest.raises(ValidationError):
            VisitUpdate(total=-10.00)

        with pytest.raises(ValidationError):
            VisitUpdate(tip=-5.00)


class TestRoutingSchemas:
    """Tests for Routing schema validation."""

    def test_route_request_with_waitlist(self):
        """Test routing request with waitlist ID."""
        data = RouteRequest(waitlist_id=uuid4())
        assert data.waitlist_id is not None
        assert data.party_size is None

    def test_route_request_with_party_info(self):
        """Test routing request with direct party info."""
        data = RouteRequest(
            party_size=4,
            table_preference=TablePreference.BOOTH,
        )
        assert data.party_size == 4
        assert data.table_preference == TablePreference.BOOTH

    def test_route_response_success(self):
        """Test successful routing response."""
        from app.schemas.routing import MatchDetails
        data = RouteResponse(
            success=True,
            table_id=uuid4(),
            table_number="T1",
            table_type="booth",
            table_location="inside",
            table_capacity=4,
            waiter_id=uuid4(),
            waiter_name="Alice",
            section_id=uuid4(),
            section_name="Main Floor",
            match_details=MatchDetails(type_matched=True, location_matched=False, capacity_fit=4),
        )
        assert data.success is True
        assert data.table_number == "T1"
        assert data.match_details.type_matched is True

    def test_route_response_failure(self):
        """Test failed routing response."""
        data = RouteResponse(
            success=False,
            message="No available tables with sufficient capacity",
        )
        assert data.success is False
        assert data.table_id is None


class TestWaiterSchemas:
    """Tests for Waiter schema validation."""

    def test_valid_waiter_create(self):
        """Test creating a waiter with valid data."""
        data = WaiterCreate(
            restaurant_id=uuid4(),
            name="Alice Johnson",
            email="alice@restaurant.com",
            phone="555-1234",
        )
        assert data.name == "Alice Johnson"

    def test_waiter_email_validation(self):
        """Test that email must be valid format."""
        with pytest.raises(ValidationError):
            WaiterCreate(
                restaurant_id=uuid4(),
                name="Test Waiter",
                email="invalid-email",
            )

    def test_waiter_name_required(self):
        """Test that waiter name is required."""
        with pytest.raises(ValidationError):
            WaiterCreate(restaurant_id=uuid4())
