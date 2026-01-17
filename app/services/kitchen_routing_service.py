from __future__ import annotations

from typing import Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.kitchen_station import KitchenStation
from app.models.menu import MenuItem, OrderItem
from app.models.visit import Visit
from app.models.recipe import Recipe
"""
from live order items in queue and current kitchen info routes chefs to batch prep stations.

takes order items (live), menu items, recipes, ingredients, and kitchen stations

When order comes in:
1. Map menu items to stations:
   - Primary ingredient category determines station
   - Protein → Grill
   - Fried items → Fryer
   - Salads/Cold → Salad Bar
   - Desserts → Dessert Station

2. Group by prep task:
   - Identify common ingredients across items
   - Example: 3 chicken dishes → batch prep chicken

3. Batch optimization:
   - If 3+ items use same ingredient → suggest batch prep
   - If station at capacity → queue or suggest splitting

4. Priority routing:
   - Larger party sizes get priority
   - Time-sensitive items (apps before entrees)

Output: Station assignments with batch grouping and prep instructions
"""
"""Kitchen station routing and prep optimization service."""


class KitchenRoutingService:
    """Service for routing orders to kitchen stations."""

    # Map ingredient categories to stations
    CATEGORY_TO_STATION = {
        "Protein": "Grill",
        "Fried": "Fryer",
        "Vegetable": "Salad Bar",
        "Salad": "Salad Bar",
        "Dessert": "Dessert",
        "Bread": "General",
        "Dairy": "General",
        "Condiment": "General",
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    async def route_visit_to_stations(self, visit_id: UUID) -> Dict:
        """
        Route all items in a visit to appropriate kitchen stations.

        Returns dict with station assignments and batch recommendations.
        """
        # Get visit with order items
        stmt = (
            select(Visit)
            .options(
                selectinload(Visit.order_items)
                .selectinload(OrderItem.menu_item)
                .selectinload(MenuItem.recipes)
                .selectinload(Recipe.ingredient)
            )
            .where(Visit.id == visit_id)
        )

        result = await self.session.execute(stmt)
        visit = result.scalar_one_or_none()

        if not visit:
            raise ValueError(f"Visit {visit_id} not found")

        # Get all kitchen stations
        stations_stmt = select(KitchenStation).where(
            KitchenStation.restaurant_id == visit.restaurant_id
        ).where(KitchenStation.is_active == True)
        
        stations_result = await self.session.execute(stations_stmt)
        stations = {s.name: s for s in stations_result.scalars().all()}

        # Route items to stations
        station_tasks = {}
        ingredient_groups = {}

        for order_item in visit.order_items:
            menu_item = order_item.menu_item

            # Determine station from primary ingredient
            station_name = "General"
            primary_ingredient = None

            if menu_item.recipes:
                # Use first recipe's ingredient category
                primary_ingredient = menu_item.recipes[0].ingredient
                station_name = self.CATEGORY_TO_STATION.get(
                    primary_ingredient.category, "General"
                )

            # Initialize station task list
            if station_name not in station_tasks:
                station_tasks[station_name] = {
                    "station_name": station_name,
                    "station_id": str(stations[station_name].id) if station_name in stations else None,
                    "items": [],
                    "prep_groups": {},
                }

            # Add item to station
            item_data = {
                "order_item_id": str(order_item.id),
                "menu_item_name": menu_item.name,
                "quantity": order_item.quantity,
                "modifiers": order_item.modifiers or {},
                "primary_ingredient": primary_ingredient.name if primary_ingredient else "N/A",
            }

            station_tasks[station_name]["items"].append(item_data)

            # Group by ingredient for batch prep
            if primary_ingredient:
                ing_name = primary_ingredient.name
                if ing_name not in ingredient_groups:
                    ingredient_groups[ing_name] = []
                ingredient_groups[ing_name].append(item_data)

        # Identify batch opportunities
        batch_recommendations = []
        for ingredient, items in ingredient_groups.items():
            total_qty = sum(item["quantity"] for item in items)
            if len(items) >= 2 or total_qty >= 2:
                batch_recommendations.append({
                    "ingredient": ingredient,
                    "item_count": len(items),
                    "total_quantity": total_qty,
                    "recommendation": f"Batch prep {ingredient} for {len(items)} items",
                    "items": [item["menu_item_name"] for item in items],
                })

        return {
            "visit_id": str(visit_id),
            "party_size": visit.party_size,
            "table_number": visit.table.table_number if visit.table else "N/A",
            "station_assignments": list(station_tasks.values()),
            "batch_recommendations": batch_recommendations,
            "total_items": len(visit.order_items),
        }
