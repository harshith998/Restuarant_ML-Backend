"""Service for seeding default data to handle cold start scenarios."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restaurant import Restaurant
from app.models.section import Section
from app.models.table import Table
from app.models.waiter import Waiter
from app.models.shift import Shift
from app.models.visit import Visit

logger = logging.getLogger(__name__)


# Default restaurant config
DEFAULT_RESTAURANT_CONFIG = {
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
}

# Default waiter profiles for cold start
DEFAULT_WAITERS = [
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "tier": "strong",
        "composite_score": 78.5,
        "total_shifts": 45,
        "total_covers": 892,
        "total_tips": 4250.75,
        "total_tables_served": 312,
        "total_sales": 28450.00,
    },
    {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "tier": "standard",
        "composite_score": 55.0,
        "total_shifts": 38,
        "total_covers": 654,
        "total_tips": 2890.50,
        "total_tables_served": 245,
        "total_sales": 19250.00,
    },
    {
        "name": "Carol Williams",
        "email": "carol@example.com",
        "tier": "standard",
        "composite_score": 52.0,
        "total_shifts": 32,
        "total_covers": 520,
        "total_tips": 2150.25,
        "total_tables_served": 198,
        "total_sales": 15600.00,
    },
    {
        "name": "Dave Brown",
        "email": "dave@example.com",
        "tier": "developing",
        "composite_score": 35.0,
        "total_shifts": 18,
        "total_covers": 285,
        "total_tips": 980.00,
        "total_tables_served": 95,
        "total_sales": 7850.00,
    },
]

# Default sections
DEFAULT_SECTIONS = [
    {"name": "Main Floor", "is_active": True},
    {"name": "Patio", "is_active": True},
    {"name": "Bar", "is_active": True},
]

# Default tables per section
DEFAULT_TABLES = {
    "Main Floor": [
        {"table_number": "T1", "capacity": 4, "table_type": "table"},
        {"table_number": "T2", "capacity": 4, "table_type": "table"},
        {"table_number": "T3", "capacity": 6, "table_type": "table"},
        {"table_number": "T4", "capacity": 2, "table_type": "table"},
        {"table_number": "B1", "capacity": 4, "table_type": "booth"},
        {"table_number": "B2", "capacity": 6, "table_type": "booth"},
    ],
    "Patio": [
        {"table_number": "P1", "capacity": 4, "table_type": "table"},
        {"table_number": "P2", "capacity": 4, "table_type": "table"},
        {"table_number": "P3", "capacity": 2, "table_type": "table"},
    ],
    "Bar": [
        {"table_number": "BAR1", "capacity": 2, "table_type": "bar"},
        {"table_number": "BAR2", "capacity": 2, "table_type": "bar"},
        {"table_number": "BAR3", "capacity": 4, "table_type": "bar"},
    ],
}


class SeedService:
    """
    Service for seeding default data.

    Handles cold start scenarios by creating default restaurants,
    waiters, sections, and tables when the database is empty.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_default_data(self) -> dict:
        """
        Ensure default data exists for cold start.

        Creates a default restaurant with sections, tables, and waiters
        if no data exists.

        Returns:
            Dict with created/existing counts
        """
        result = {
            "restaurants_created": 0,
            "sections_created": 0,
            "tables_created": 0,
            "waiters_created": 0,
            "already_seeded": False,
        }

        # Check if any restaurants exist
        restaurant_count = await self._count_restaurants()
        if restaurant_count > 0:
            result["already_seeded"] = True
            logger.info("Database already has data, skipping seed")
            return result

        logger.info("Cold start detected, seeding default data...")

        # Create default restaurant
        restaurant = await self._create_default_restaurant()
        result["restaurants_created"] = 1

        # Create sections
        sections = await self._create_default_sections(restaurant.id)
        result["sections_created"] = len(sections)

        # Create tables
        tables_created = 0
        for section in sections:
            tables = await self._create_default_tables(
                restaurant_id=restaurant.id,
                section_id=section.id,
                section_name=section.name,
            )
            tables_created += len(tables)
        result["tables_created"] = tables_created

        # Create waiters
        waiters = await self._create_default_waiters(restaurant.id)
        result["waiters_created"] = len(waiters)

        await self.session.commit()

        logger.info(
            f"Seed complete: {result['restaurants_created']} restaurants, "
            f"{result['sections_created']} sections, "
            f"{result['tables_created']} tables, "
            f"{result['waiters_created']} waiters"
        )

        return result

    async def ensure_restaurant_has_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """
        Ensure a restaurant has at least one waiter.

        If no waiters exist, creates default waiters.

        Args:
            restaurant_id: The restaurant ID

        Returns:
            List of waiters (existing or newly created)
        """
        # Check existing waiters
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        waiters = list(result.scalars().all())

        if waiters:
            return waiters

        # Create default waiters
        logger.info(f"No waiters found for restaurant {restaurant_id}, creating defaults")
        waiters = await self._create_default_waiters(restaurant_id)
        await self.session.commit()

        return waiters

    async def create_sample_shifts_and_visits(
        self,
        restaurant_id: UUID,
        days_back: int = 30,
    ) -> dict:
        """
        Create sample shifts and visits for testing.

        Useful for development/demo environments.

        Args:
            restaurant_id: The restaurant ID
            days_back: Number of days of history to create

        Returns:
            Dict with created counts
        """
        result = {
            "shifts_created": 0,
            "visits_created": 0,
        }

        # Get waiters and tables
        waiters = await self._get_restaurant_waiters(restaurant_id)
        tables = await self._get_restaurant_tables(restaurant_id)

        if not waiters or not tables:
            logger.warning("No waiters or tables found, skipping sample data")
            return result

        # Create shifts and visits for past days
        import random

        for day_offset in range(days_back, 0, -1):
            shift_date = datetime.utcnow() - timedelta(days=day_offset)

            # Create shift for each waiter
            for waiter in waiters:
                # Random chance of working this day
                if random.random() > 0.6:
                    continue

                shift = Shift(
                    restaurant_id=restaurant_id,
                    waiter_id=waiter.id,
                    clock_in=shift_date.replace(hour=16, minute=0),
                    clock_out=shift_date.replace(hour=23, minute=0),
                    status="ended",
                    tables_served=0,
                    total_covers=0,
                    total_tips=Decimal("0"),
                    total_sales=Decimal("0"),
                )
                self.session.add(shift)
                await self.session.flush()
                result["shifts_created"] += 1

                # Create random visits for this shift
                num_visits = random.randint(3, 8)
                for v in range(num_visits):
                    table = random.choice(tables)
                    party_size = random.randint(2, min(6, table.capacity))
                    check_amount = Decimal(str(random.uniform(40, 150)))
                    tip_pct = random.uniform(0.15, 0.25)
                    tip = check_amount * Decimal(str(tip_pct))

                    visit = Visit(
                        restaurant_id=restaurant_id,
                        table_id=table.id,
                        waiter_id=waiter.id,
                        shift_id=shift.id,
                        party_size=party_size,
                        seated_at=shift_date.replace(hour=17 + v),
                        cleared_at=shift_date.replace(hour=18 + v),
                        subtotal=check_amount,
                        tax=check_amount * Decimal("0.08"),
                        total=check_amount * Decimal("1.08"),
                        tip=tip,
                        tip_percentage=Decimal(str(tip_pct * 100)),
                    )
                    self.session.add(visit)

                    # Update shift totals
                    shift.tables_served += 1
                    shift.total_covers += party_size
                    shift.total_tips += tip
                    shift.total_sales += check_amount

                    # Update waiter lifetime stats
                    waiter.total_covers += party_size
                    waiter.total_tips = Decimal(str(waiter.total_tips)) + tip
                    waiter.total_tables_served += 1
                    waiter.total_sales = Decimal(str(waiter.total_sales)) + check_amount

                    result["visits_created"] += 1

        await self.session.commit()

        logger.info(
            f"Created sample data: {result['shifts_created']} shifts, "
            f"{result['visits_created']} visits"
        )

        return result

    async def _count_restaurants(self) -> int:
        """Count total restaurants."""
        stmt = select(func.count(Restaurant.id))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _create_default_restaurant(self) -> Restaurant:
        """Create the default restaurant."""
        restaurant = Restaurant(
            name="The Golden Fork",
            timezone="America/New_York",
            config=DEFAULT_RESTAURANT_CONFIG,
        )
        self.session.add(restaurant)
        await self.session.flush()
        return restaurant

    async def _create_default_sections(
        self,
        restaurant_id: UUID,
    ) -> List[Section]:
        """Create default sections for a restaurant."""
        sections = []
        for section_data in DEFAULT_SECTIONS:
            section = Section(
                restaurant_id=restaurant_id,
                name=section_data["name"],
                is_active=section_data["is_active"],
            )
            self.session.add(section)
            sections.append(section)

        await self.session.flush()
        return sections

    async def _create_default_tables(
        self,
        restaurant_id: UUID,
        section_id: UUID,
        section_name: str,
    ) -> List[Table]:
        """Create default tables for a section."""
        tables = []
        table_configs = DEFAULT_TABLES.get(section_name, [])

        for table_data in table_configs:
            table = Table(
                restaurant_id=restaurant_id,
                section_id=section_id,
                table_number=table_data["table_number"],
                capacity=table_data["capacity"],
                table_type=table_data["table_type"],
                state="clean",
            )
            self.session.add(table)
            tables.append(table)

        await self.session.flush()
        return tables

    async def _create_default_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """Create default waiters for a restaurant."""
        await self._ensure_waiter_role_column()
        waiters = []
        for waiter_data in DEFAULT_WAITERS:
            waiter = Waiter(
                restaurant_id=restaurant_id,
                name=waiter_data["name"],
                email=waiter_data["email"],
                tier=waiter_data["tier"],
                composite_score=Decimal(str(waiter_data["composite_score"])),
                total_shifts=waiter_data.get("total_shifts", 0),
                total_covers=waiter_data.get("total_covers", 0),
                total_tips=Decimal(str(waiter_data.get("total_tips", 0))),
                total_tables_served=waiter_data.get("total_tables_served", 0),
                total_sales=Decimal(str(waiter_data.get("total_sales", 0))),
            )
            self.session.add(waiter)
            waiters.append(waiter)

        await self.session.flush()
        return waiters

    async def _ensure_waiter_role_column(self) -> None:
        """Ensure legacy databases have the waiters.role column."""
        await self.session.execute(
            text(
                "ALTER TABLE waiters "
                "ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'server'"
            )
        )

    async def _get_restaurant_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """Get all active waiters for a restaurant."""
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_restaurant_tables(
        self,
        restaurant_id: UUID,
    ) -> List[Table]:
        """Get all active tables for a restaurant."""
        stmt = (
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .where(Table.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_first_restaurant(self) -> Optional[Restaurant]:
        """Get the first restaurant if one exists."""
        stmt = select(Restaurant).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def seed_demo(
        self,
        days_back: int = 30,
        run_tier_calculation: bool = True,
    ) -> dict:
        """
        One-stop demo seeding for frontend development.

        This method does everything needed to get a working demo:
        1. Creates default restaurant if none exists (or uses existing)
        2. Creates waiters if none exist for the restaurant
        3. Creates sample shifts and visits for the past N days
        4. Optionally runs tier calculation to populate insights

        Args:
            days_back: Number of days of history to create (default 30)
            run_tier_calculation: Whether to run tier calculation after seeding

        Returns:
            Dict with all info the frontend needs to start using the API
        """
        result = {
            "success": True,
            "message": "",
            "restaurant_id": None,
            "restaurant_name": None,
            "waiters": [],
            "shifts_created": 0,
            "visits_created": 0,
            "days_of_history": days_back,
            "tiers_calculated": False,
        }

        # Step 1: Get or create restaurant
        restaurant = await self._get_first_restaurant()
        created_new = False

        if restaurant is None:
            # Create default restaurant with sections, tables, waiters
            await self._create_default_restaurant_with_all()
            await self.session.commit()
            restaurant = await self._get_first_restaurant()
            created_new = True
            logger.info(f"Created new restaurant: {restaurant.name}")
        else:
            logger.info(f"Using existing restaurant: {restaurant.name}")

        result["restaurant_id"] = restaurant.id
        result["restaurant_name"] = restaurant.name

        # Step 2: Ensure waiters exist
        waiters = await self.ensure_restaurant_has_waiters(restaurant.id)
        result["waiters"] = [
            {
                "id": w.id,
                "name": w.name,
                "tier": w.tier,
                "composite_score": float(w.composite_score) if w.composite_score else 50.0,
            }
            for w in waiters
        ]

        # Step 3: Check if we need to create sample data
        # Only create sample data if we just created the restaurant
        # or if there are very few visits
        visit_count = await self._count_visits(restaurant.id)

        if visit_count < 10:
            logger.info(f"Creating {days_back} days of sample data...")
            sample_result = await self.create_sample_shifts_and_visits(
                restaurant_id=restaurant.id,
                days_back=days_back,
            )
            result["shifts_created"] = sample_result["shifts_created"]
            result["visits_created"] = sample_result["visits_created"]
        else:
            logger.info(f"Restaurant already has {visit_count} visits, skipping sample data")

        # Step 4: Run tier calculation if requested
        if run_tier_calculation:
            try:
                from app.services.tier_job import TierRecalculationJob

                job = TierRecalculationJob(session=self.session)
                tier_result = await job.run(restaurant_id=restaurant.id, use_llm=False)
                result["tiers_calculated"] = tier_result.success

                # Refresh waiter data after tier calculation
                waiters = await self._get_restaurant_waiters(restaurant.id)
                result["waiters"] = [
                    {
                        "id": w.id,
                        "name": w.name,
                        "tier": w.tier,
                        "composite_score": float(w.composite_score) if w.composite_score else 50.0,
                    }
                    for w in waiters
                ]
            except Exception as e:
                logger.warning(f"Tier calculation failed: {e}")
                result["tiers_calculated"] = False

        # Build message
        if created_new:
            result["message"] = (
                f"Created demo restaurant '{restaurant.name}' with "
                f"{len(result['waiters'])} waiters and {result['visits_created']} visits"
            )
        else:
            result["message"] = (
                f"Using existing restaurant '{restaurant.name}' with "
                f"{len(result['waiters'])} waiters"
            )
            if result["visits_created"] > 0:
                result["message"] += f" (added {result['visits_created']} sample visits)"

        return result

    async def _create_default_restaurant_with_all(self) -> Restaurant:
        """Create default restaurant with all related data."""
        # Create restaurant
        restaurant = await self._create_default_restaurant()

        # Create sections
        sections = await self._create_default_sections(restaurant.id)

        # Create tables for each section
        for section in sections:
            await self._create_default_tables(
                restaurant_id=restaurant.id,
                section_id=section.id,
                section_name=section.name,
            )

        # Create waiters
        await self._create_default_waiters(restaurant.id)

        return restaurant

    async def _count_visits(self, restaurant_id: UUID) -> int:
        """Count visits for a restaurant."""
        stmt = select(func.count(Visit.id)).where(Visit.restaurant_id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()
