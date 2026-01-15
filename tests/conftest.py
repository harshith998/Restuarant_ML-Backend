"""
Pytest configuration and fixtures.

This module provides fixtures that simulate real-world restaurant scenarios:
- A restaurant with multiple sections (Bar, Main Floor, Patio)
- Multiple waiters with different skill levels
- Tables of various types and capacities
- Active shifts for waiters
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import (
    Restaurant,
    Section,
    Table,
    Waiter,
    Shift,
    WaitlistEntry,
    Visit,
    MenuItem,
    OrderItem,
)


# Use SQLite for testing (in-memory)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_restaurant(db_session: AsyncSession) -> Restaurant:
    """
    Create a sample restaurant with realistic configuration.

    This represents "The Golden Fork" - a mid-sized restaurant with:
    - Section-based waiter assignment
    - Standard routing weights
    """
    restaurant = Restaurant(
        id=uuid4(),
        name="The Golden Fork",
        timezone="America/New_York",
        config={
            "routing": {
                "mode": "section",
                "max_tables_per_waiter": 5,
                "efficiency_weight": 1.0,
                "workload_penalty": 3.0,
                "tip_penalty": 2.0,
                "recency_penalty_minutes": 5,
                "recency_penalty_weight": 1.5,
            },
            "alerts": {
                "understaffed_threshold": 1.2,
                "overstaffed_threshold": 0.5,
            },
        },
    )
    db_session.add(restaurant)
    await db_session.commit()
    await db_session.refresh(restaurant)
    return restaurant


@pytest_asyncio.fixture
async def sample_sections(
    db_session: AsyncSession, sample_restaurant: Restaurant
) -> list[Section]:
    """
    Create sections that mirror a real restaurant layout:
    - Bar: High-turnover, smaller parties
    - Main Floor: Standard dining
    - Patio: Seasonal outdoor seating
    """
    sections = [
        Section(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Bar",
            is_active=True,
        ),
        Section(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Main Floor",
            is_active=True,
        ),
        Section(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Patio",
            is_active=True,
        ),
    ]
    for section in sections:
        db_session.add(section)
    await db_session.commit()
    for section in sections:
        await db_session.refresh(section)
    return sections


@pytest_asyncio.fixture
async def sample_tables(
    db_session: AsyncSession,
    sample_restaurant: Restaurant,
    sample_sections: list[Section],
) -> list[Table]:
    """
    Create tables with realistic distribution:
    - Bar: B1-B4 (2-seat bar stools)
    - Main Floor: T1-T6 (4-6 seat tables), B1-B2 (booths for 4)
    - Patio: P1-P3 (4-seat outdoor tables)
    """
    bar, main, patio = sample_sections

    tables = [
        # Bar section - small, high turnover (bar_area location)
        Table(restaurant_id=sample_restaurant.id, section_id=bar.id, table_number="B1", capacity=2, table_type="bar", location="bar_area", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=bar.id, table_number="B2", capacity=2, table_type="bar", location="bar_area", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=bar.id, table_number="B3", capacity=2, table_type="bar", location="bar_area", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=bar.id, table_number="B4", capacity=2, table_type="bar", location="bar_area", state="occupied"),

        # Main floor - mixed seating (inside location)
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="T1", capacity=4, table_type="table", location="inside", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="T2", capacity=4, table_type="table", location="inside", state="dirty"),
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="T3", capacity=6, table_type="table", location="inside", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="T4", capacity=4, table_type="table", location="inside", state="occupied"),
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="Booth1", capacity=4, table_type="booth", location="inside", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=main.id, table_number="Booth2", capacity=4, table_type="booth", location="inside", state="clean"),

        # Patio - outdoor seating (patio/outside location)
        Table(restaurant_id=sample_restaurant.id, section_id=patio.id, table_number="P1", capacity=4, table_type="table", location="patio", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=patio.id, table_number="P2", capacity=4, table_type="table", location="outside", state="clean"),
        Table(restaurant_id=sample_restaurant.id, section_id=patio.id, table_number="P3", capacity=4, table_type="table", location="patio", state="unavailable"),  # Closed for cleaning
    ]

    for table in tables:
        table.id = uuid4()
        db_session.add(table)
    await db_session.commit()
    for table in tables:
        await db_session.refresh(table)
    return tables


@pytest_asyncio.fixture
async def sample_waiters(
    db_session: AsyncSession, sample_restaurant: Restaurant
) -> list[Waiter]:
    """
    Create waiters with varied experience levels:
    - Alice: Strong performer, high tips
    - Bob: Standard performer
    - Carol: Developing, newer employee
    - Dave: Standard, currently on break
    """
    waiters = [
        Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Alice",
            email="alice@restaurant.com",
            tier="strong",
            composite_score=85.0,
            total_shifts=150,
            total_covers=2500,
            total_tips=45000.00,
        ),
        Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Bob",
            email="bob@restaurant.com",
            tier="standard",
            composite_score=55.0,
            total_shifts=80,
            total_covers=1200,
            total_tips=18000.00,
        ),
        Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Carol",
            email="carol@restaurant.com",
            tier="developing",
            composite_score=35.0,
            total_shifts=20,
            total_covers=250,
            total_tips=3500.00,
        ),
        Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Dave",
            email="dave@restaurant.com",
            tier="standard",
            composite_score=50.0,
            total_shifts=60,
            total_covers=900,
            total_tips=12000.00,
        ),
    ]

    for waiter in waiters:
        db_session.add(waiter)
    await db_session.commit()
    for waiter in waiters:
        await db_session.refresh(waiter)
    return waiters


@pytest_asyncio.fixture
async def sample_shifts(
    db_session: AsyncSession,
    sample_restaurant: Restaurant,
    sample_sections: list[Section],
    sample_waiters: list[Waiter],
) -> list[Shift]:
    """
    Create active shifts for tonight's dinner service:
    - Alice: Bar section, 2 tables served, $45 tips so far
    - Bob: Main Floor, 3 tables served, $62 tips
    - Carol: Main Floor, 1 table served, $15 tips (newer)
    - Dave: Patio, on break
    """
    bar, main, patio = sample_sections
    alice, bob, carol, dave = sample_waiters
    now = datetime.utcnow()

    shifts = [
        Shift(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            waiter_id=alice.id,
            section_id=bar.id,
            clock_in=now - timedelta(hours=3),
            status="active",
            tables_served=2,
            total_covers=6,
            total_tips=45.00,
            total_sales=180.00,
        ),
        Shift(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            waiter_id=bob.id,
            section_id=main.id,
            clock_in=now - timedelta(hours=4),
            status="active",
            tables_served=3,
            total_covers=10,
            total_tips=62.00,
            total_sales=280.00,
        ),
        Shift(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            waiter_id=carol.id,
            section_id=main.id,
            clock_in=now - timedelta(hours=2),
            status="active",
            tables_served=1,
            total_covers=3,
            total_tips=15.00,
            total_sales=75.00,
        ),
        Shift(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            waiter_id=dave.id,
            section_id=patio.id,
            clock_in=now - timedelta(hours=3),
            status="on_break",
            tables_served=2,
            total_covers=7,
            total_tips=38.00,
            total_sales=190.00,
        ),
    ]

    for shift in shifts:
        db_session.add(shift)
    await db_session.commit()
    for shift in shifts:
        await db_session.refresh(shift)
    return shifts


@pytest_asyncio.fixture
async def sample_waitlist(
    db_session: AsyncSession, sample_restaurant: Restaurant
) -> list[WaitlistEntry]:
    """
    Create waitlist entries representing current queue:
    - Johnson family (4 people, wants booth) - waiting 10 min
    - Smith party (2 people, no preference) - waiting 5 min
    - Garcia party (6 people, any table) - just arrived
    """
    now = datetime.utcnow()

    entries = [
        WaitlistEntry(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            party_name="Johnson",
            party_size=4,
            table_preference="booth",
            notes="Birthday dinner",
            checked_in_at=now - timedelta(minutes=10),
            quoted_wait_minutes=15,
            status="waiting",
        ),
        WaitlistEntry(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            party_name="Smith",
            party_size=2,
            table_preference="none",
            checked_in_at=now - timedelta(minutes=5),
            quoted_wait_minutes=10,
            status="waiting",
        ),
        WaitlistEntry(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            party_name="Garcia",
            party_size=6,
            table_preference="table",
            checked_in_at=now,
            quoted_wait_minutes=20,
            status="waiting",
        ),
    ]

    for entry in entries:
        db_session.add(entry)
    await db_session.commit()
    for entry in entries:
        await db_session.refresh(entry)
    return entries
