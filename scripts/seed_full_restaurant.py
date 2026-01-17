from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import random

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import (
    Restaurant, Section, Table, Waiter, Shift,
    MenuItem, OrderItem, Ingredient, Recipe, KitchenStation, Visit
)


async def seed_data():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        print("🌱 Seeding restaurant data...")
        
        restaurant = Restaurant(name="The Golden Fork", timezone="America/New_York", config={})
        session.add(restaurant)
        await session.flush()
        
        sections = [
            Section(restaurant_id=restaurant.id, name="Main Floor", is_active=True),
            Section(restaurant_id=restaurant.id, name="Bar", is_active=True),
            Section(restaurant_id=restaurant.id, name="Patio", is_active=True),
        ]
        session.add_all(sections)
        await session.flush()
        
        tables = []
        for i in range(1, 11):
            tables.append(Table(
                restaurant_id=restaurant.id,
                section_id=random.choice(sections).id,
                table_number=f"T{i}",
                capacity=random.choice([2, 4, 6]),
                table_type=random.choice(["table", "booth"]),
                state="clean"
            ))
        session.add_all(tables)
        await session.flush()
        
        waiters = [
            Waiter(restaurant_id=restaurant.id, name="Alice", tier="strong"),
            Waiter(restaurant_id=restaurant.id, name="Bob", tier="standard"),
            Waiter(restaurant_id=restaurant.id, name="Carol", tier="standard"),
        ]
        session.add_all(waiters)
        await session.flush()
        
        now = datetime.utcnow()
        shifts = []
        for waiter, section in zip(waiters, sections):
            shift = Shift(
                restaurant_id=restaurant.id,
                waiter_id=waiter.id,
                section_id=section.id,
                clock_in=now - timedelta(hours=3),
                status="active",
                tables_served=random.randint(2, 8),
                total_covers=random.randint(10, 40),
                total_tips=random.uniform(50, 200),
            )
            shifts.append(shift)
        session.add_all(shifts)
        await session.flush()
        
        ingredients = [
            Ingredient(restaurant_id=restaurant.id, name="Chicken Breast", category="Protein", unit="lb", cost_per_unit=3.50, supplier="Sysco", par_level=50, current_stock=32),
            Ingredient(restaurant_id=restaurant.id, name="Ground Beef", category="Protein", unit="lb", cost_per_unit=4.00, supplier="Sysco", par_level=40, current_stock=25),
            Ingredient(restaurant_id=restaurant.id, name="Salmon Fillet", category="Protein", unit="lb", cost_per_unit=8.00, supplier="Fresh Catch", par_level=20, current_stock=15),
            Ingredient(restaurant_id=restaurant.id, name="Mixed Greens", category="Vegetable", unit="lb", cost_per_unit=2.00, supplier="Local Farm", par_level=20, current_stock=18),
            Ingredient(restaurant_id=restaurant.id, name="Tomatoes", category="Vegetable", unit="lb", cost_per_unit=1.50, supplier="Local Farm", par_level=15, current_stock=12),
            Ingredient(restaurant_id=restaurant.id, name="Burger Buns", category="Bread", unit="each", cost_per_unit=0.30, supplier="Bakery", par_level=100, current_stock=80),
            Ingredient(restaurant_id=restaurant.id, name="Cheddar Cheese", category="Dairy", unit="lb", cost_per_unit=5.00, supplier="Sysco", par_level=10, current_stock=7),
            Ingredient(restaurant_id=restaurant.id, name="Olive Oil", category="Condiment", unit="cup", cost_per_unit=0.50, supplier="Sysco", par_level=20, current_stock=15),
        ]
        session.add_all(ingredients)
        await session.flush()
        
        menu_items = [
            MenuItem(restaurant_id=restaurant.id, name="Grilled Chicken Salad", category="Entrees", price=14.99, cost=4.50, is_available=True),
            MenuItem(restaurant_id=restaurant.id, name="Classic Burger", category="Entrees", price=12.99, cost=3.75, is_available=True),
            MenuItem(restaurant_id=restaurant.id, name="Salmon Bowl", category="Entrees", price=18.99, cost=7.50, is_available=True),
            MenuItem(restaurant_id=restaurant.id, name="Caesar Salad", category="Salads", price=9.99, cost=2.50, is_available=True),
            MenuItem(restaurant_id=restaurant.id, name="Cheeseburger Deluxe", category="Entrees", price=14.99, cost=4.25, is_available=True),
        ]
        session.add_all(menu_items)
        await session.flush()
        
        recipes = [
            Recipe(menu_item_id=menu_items[0].id, ingredient_id=ingredients[0].id, quantity=0.375, unit="lb", notes="Grilled"),
            Recipe(menu_item_id=menu_items[0].id, ingredient_id=ingredients[3].id, quantity=0.125, unit="lb"),
            Recipe(menu_item_id=menu_items[1].id, ingredient_id=ingredients[1].id, quantity=0.25, unit="lb"),
            Recipe(menu_item_id=menu_items[1].id, ingredient_id=ingredients[5].id, quantity=1, unit="each"),
            Recipe(menu_item_id=menu_items[2].id, ingredient_id=ingredients[2].id, quantity=0.5, unit="lb"),
            Recipe(menu_item_id=menu_items[4].id, ingredient_id=ingredients[1].id, quantity=0.25, unit="lb"),
            Recipe(menu_item_id=menu_items[4].id, ingredient_id=ingredients[6].id, quantity=0.125, unit="lb"),
        ]
        session.add_all(recipes)
        await session.flush()
        
        stations = [
            KitchenStation(restaurant_id=restaurant.id, name="Grill", is_active=True, max_concurrent_orders=8),
            KitchenStation(restaurant_id=restaurant.id, name="Fryer", is_active=True, max_concurrent_orders=10),
            KitchenStation(restaurant_id=restaurant.id, name="Salad Bar", is_active=True, max_concurrent_orders=12),
        ]
        session.add_all(stations)
        await session.flush()
        
        visits = []
        for day_offset in range(30):
            visit_date = now - timedelta(days=day_offset)
            for _ in range(random.randint(20, 50)):
                visit = Visit(
                    restaurant_id=restaurant.id,
                    table_id=random.choice(tables).id,
                    waiter_id=random.choice(waiters).id,
                    shift_id=random.choice(shifts).id,
                    party_size=random.randint(2, 6),
                    seated_at=visit_date,
                    cleared_at=visit_date + timedelta(minutes=random.randint(30, 90)),
                    subtotal=random.uniform(30, 100),
                    tax=random.uniform(3, 10),
                    tip=random.uniform(5, 20),
                )
                visits.append(visit)

        session.add_all(visits)
        await session.flush()

        # Now create order items with valid visit IDs
        order_items_list = []
        for visit in visits:
            for _ in range(random.randint(1, 3)):
                menu_item = random.choice(menu_items)
                order_items_list.append(OrderItem(
                    visit_id=visit.id,
                    menu_item_id=menu_item.id,
                    quantity=random.randint(1, 2),
                    unit_price=menu_item.price,
                    total_price=menu_item.price * random.randint(1, 2),
                    ordered_at=visit.seated_at
                ))

        session.add_all(order_items_list)
        await session.commit()
        
        print(f"✅ Restaurant, {len(sections)} sections, {len(tables)} tables, {len(waiters)} waiters")
        print(f"✅ {len(ingredients)} ingredients, {len(menu_items)} menu items, {len(recipes)} recipes")
        print(f"✅ {len(stations)} kitchen stations, {len(visits)} visits, {len(order_items_list)} orders")
        print("🎉 Database seeded!")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_data())
