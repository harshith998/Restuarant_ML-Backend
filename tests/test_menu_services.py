from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.services.menu_optimization_service import MenuOptimizationService
from app.services.inventory_service import InventoryService
from app.services.kitchen_routing_service import KitchenRoutingService
from app.models import (
    Restaurant, MenuItem, OrderItem, Visit, Ingredient,
    Recipe, KitchenStation, Table, Waiter, Shift
)


@pytest.mark.asyncio
async def test_menu_optimization_pricing_recommendations(db_session):
    """Test pricing recommendations based on demand and margin."""
    # Create test data
    restaurant = Restaurant(name="Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # High demand, low margin item
    chicken_salad = MenuItem(
        restaurant_id=restaurant.id,
        name="Chicken Salad",
        category="Entrees",
        price=14.99,
        cost=8.00,  # ~47% margin
        is_available=True,
    )
    
    # Low demand, low margin item
    unpopular_item = MenuItem(
        restaurant_id=restaurant.id,
        name="Unpopular Dish",
        category="Entrees",
        price=12.99,
        cost=8.50,  # ~35% margin
        is_available=True,
    )
    
    db_session.add_all([chicken_salad, unpopular_item])
    await db_session.flush()

    # Create visits and orders (30 days of history)
    table = Table(
        restaurant_id=restaurant.id,
        table_number="T1",
        capacity=4,
        table_type="table",
        state="clean",
    )
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(
        restaurant_id=restaurant.id,
        waiter_id=waiter.id,
        clock_in=datetime.utcnow(),
        status="active",
    )
    db_session.add(shift)
    await db_session.flush()

    # Create 200 orders for chicken salad (high demand)
    for i in range(200):
        visit = Visit(
            restaurant_id=restaurant.id,
            table_id=table.id,
            waiter_id=waiter.id,
            shift_id=shift.id,
            party_size=2,
            seated_at=datetime.utcnow() - timedelta(days=i % 30),
        )
        db_session.add(visit)
        await db_session.flush()
        
        order = OrderItem(
            visit_id=visit.id,
            menu_item_id=chicken_salad.id,
            quantity=1,
            unit_price=chicken_salad.price,
            total_price=chicken_salad.price,
            ordered_at=visit.seated_at,
        )
        db_session.add(order)

    # Create 20 orders for unpopular item (low demand)
    for i in range(20):
        visit = Visit(
            restaurant_id=restaurant.id,
            table_id=table.id,
            waiter_id=waiter.id,
            shift_id=shift.id,
            party_size=2,
            seated_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(visit)
        await db_session.flush()
        
        order = OrderItem(
            visit_id=visit.id,
            menu_item_id=unpopular_item.id,
            quantity=1,
            unit_price=unpopular_item.price,
            total_price=unpopular_item.price,
            ordered_at=visit.seated_at,
        )
        db_session.add(order)

    await db_session.commit()

    # Test service
    service = MenuOptimizationService(db_session)
    recommendations = await service.get_pricing_recommendations(restaurant.id)

    assert len(recommendations) >= 2
    
    # Find chicken salad recommendation
    chicken_rec = next((r for r in recommendations if r["item_name"] == "Chicken Salad"), None)
    assert chicken_rec is not None
    assert chicken_rec["action"] == "increase"  # High demand, low margin
    assert chicken_rec["suggested_price"] > chicken_rec["current_price"]

    # Find unpopular item recommendation
    unpopular_rec = next((r for r in recommendations if r["item_name"] == "Unpopular Dish"), None)
    assert unpopular_rec is not None
    assert unpopular_rec["action"] == "remove"  # Low demand, low margin


@pytest.mark.asyncio
async def test_inventory_shopping_list(db_session):
    """Test shopping list generation based on usage."""
    # Create test data
    restaurant = Restaurant(name="Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # Ingredient with low stock
    chicken = Ingredient(
        restaurant_id=restaurant.id,
        name="Chicken Breast",
        category="Protein",
        unit="lb",
        cost_per_unit=3.50,
        supplier="Sysco",
        par_level=50,
        current_stock=10,  # Below par
    )
    
    db_session.add(chicken)
    await db_session.flush()

    # Menu item using chicken
    chicken_dish = MenuItem(
        restaurant_id=restaurant.id,
        name="Grilled Chicken",
        price=14.99,
        cost=5.00,
        is_available=True,
    )
    db_session.add(chicken_dish)
    await db_session.flush()

    # Recipe linking them
    recipe = Recipe(
        menu_item_id=chicken_dish.id,
        ingredient_id=chicken.id,
        quantity=0.5,  # 0.5 lb per dish
        unit="lb",
    )
    db_session.add(recipe)
    await db_session.flush()

    # Create historical orders
    table = Table(
        restaurant_id=restaurant.id,
        table_number="T1",
        capacity=4,
        table_type="table",
        state="clean",
    )
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(
        restaurant_id=restaurant.id,
        waiter_id=waiter.id,
        clock_in=datetime.utcnow(),
        status="active",
    )
    db_session.add(shift)
    await db_session.flush()

    # 60 orders over 30 days = 2 per day avg
    for i in range(60):
        visit = Visit(
            restaurant_id=restaurant.id,
            table_id=table.id,
            waiter_id=waiter.id,
            shift_id=shift.id,
            party_size=2,
            seated_at=datetime.utcnow() - timedelta(days=i % 30),
        )
        db_session.add(visit)
        await db_session.flush()
        
        order = OrderItem(
            visit_id=visit.id,
            menu_item_id=chicken_dish.id,
            quantity=1,
            unit_price=chicken_dish.price,
            total_price=chicken_dish.price,
            ordered_at=visit.seated_at,
        )
        db_session.add(order)

    await db_session.commit()

    # Test service
    service = InventoryService(db_session)
    shopping_list = await service.generate_shopping_list(restaurant.id, forecast_days=7)

    assert shopping_list["total_items"] >= 1
    assert shopping_list["total_cost"] > 0
    
    chicken_item = next((i for i in shopping_list["ingredients"] if i["name"] == "Chicken Breast"), None)
    assert chicken_item is not None
    assert chicken_item["quantity_to_order"] > 0
    assert chicken_item["urgency"] == "high"  # Below 50% of par


@pytest.mark.asyncio
async def test_kitchen_routing(db_session):
    """Test kitchen routing assigns items to correct stations."""
    # Create test data
    restaurant = Restaurant(name="Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # Kitchen stations
    grill = KitchenStation(
        restaurant_id=restaurant.id,
        name="Grill",
        is_active=True,
        max_concurrent_orders=8,
    )
    salad_bar = KitchenStation(
        restaurant_id=restaurant.id,
        name="Salad Bar",
        is_active=True,
        max_concurrent_orders=10,
    )
    db_session.add_all([grill, salad_bar])
    await db_session.flush()

    # Ingredients
    chicken = Ingredient(
        restaurant_id=restaurant.id,
        name="Chicken",
        category="Protein",
        unit="lb",
        cost_per_unit=3.50,
        supplier="Sysco",
        par_level=50,
        current_stock=30,
    )
    greens = Ingredient(
        restaurant_id=restaurant.id,
        name="Greens",
        category="Vegetable",
        unit="lb",
        cost_per_unit=2.00,
        supplier="Local",
        par_level=20,
        current_stock=15,
    )
    db_session.add_all([chicken, greens])
    await db_session.flush()

    # Menu items
    grilled_chicken = MenuItem(
        restaurant_id=restaurant.id,
        name="Grilled Chicken",
        price=14.99,
        is_available=True,
    )
    caesar_salad = MenuItem(
        restaurant_id=restaurant.id,
        name="Caesar Salad",
        price=9.99,
        is_available=True,
    )
    db_session.add_all([grilled_chicken, caesar_salad])
    await db_session.flush()

    # Recipes
    recipe1 = Recipe(menu_item_id=grilled_chicken.id, ingredient_id=chicken.id, quantity=0.5, unit="lb")
    recipe2 = Recipe(menu_item_id=caesar_salad.id, ingredient_id=greens.id, quantity=0.25, unit="lb")
    db_session.add_all([recipe1, recipe2])
    await db_session.flush()

    # Visit with orders
    table = Table(
        restaurant_id=restaurant.id,
        table_number="T1",
        capacity=4,
        table_type="table",
        state="clean",
    )
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(
        restaurant_id=restaurant.id,
        waiter_id=waiter.id,
        clock_in=datetime.utcnow(),
        status="active",
    )
    db_session.add(shift)
    await db_session.flush()

    visit = Visit(
        restaurant_id=restaurant.id,
        table_id=table.id,
        waiter_id=waiter.id,
        shift_id=shift.id,
        party_size=2,
        seated_at=datetime.utcnow(),
    )
    db_session.add(visit)
    await db_session.flush()

    # Order items
    order1 = OrderItem(
        visit_id=visit.id,
        menu_item_id=grilled_chicken.id,
        quantity=2,
        unit_price=grilled_chicken.price,
        total_price=grilled_chicken.price * 2,
        ordered_at=visit.seated_at,
    )
    order2 = OrderItem(
        visit_id=visit.id,
        menu_item_id=caesar_salad.id,
        quantity=1,
        unit_price=caesar_salad.price,
        total_price=caesar_salad.price,
        ordered_at=visit.seated_at,
    )
    db_session.add_all([order1, order2])
    await db_session.commit()

    # Test service
    service = KitchenRoutingService(db_session)
    routing = await service.route_visit_to_stations(visit.id)

    assert routing["total_items"] == 2
    assert len(routing["station_assignments"]) >= 2
    
    # Check grill station has chicken
    grill_station = next((s for s in routing["station_assignments"] if s["station_name"] == "Grill"), None)
    assert grill_station is not None
    assert len(grill_station["items"]) >= 1

    # Check batch recommendations for 2 chicken items
    assert len(routing["batch_recommendations"]) >= 1


###############################################################################
# API ENDPOINT TESTS - Phase 2: Full HTTP Request/Response Testing
###############################################################################
"""
These tests verify the complete API layer:
- HTTP request → routing → service → database → response
- Response schema validation
- Error handling (404s, etc.)
"""

from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_pricing_recommendations_api_endpoint(db_session):
    """Test GET /menu/pricing-recommendations API endpoint end-to-end."""
    # Create test data
    restaurant = Restaurant(name="API Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # High demand item
    popular_item = MenuItem(
        restaurant_id=restaurant.id,
        name="Popular Burger",
        category="Entrees",
        price=12.99,
        cost=6.00,
        is_available=True,
    )
    db_session.add(popular_item)
    await db_session.flush()

    # Create orders to generate demand
    table = Table(
        restaurant_id=restaurant.id,
        table_number="T1",
        capacity=4,
        table_type="table",
        state="clean",
    )
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(
        restaurant_id=restaurant.id,
        waiter_id=waiter.id,
        clock_in=datetime.utcnow(),
        status="active",
    )
    db_session.add(shift)
    await db_session.flush()

    # Create 200 orders (high demand: 200/30 = 6.67 orders/day)
    for i in range(200):
        visit = Visit(
            restaurant_id=restaurant.id,
            table_id=table.id,
            waiter_id=waiter.id,
            shift_id=shift.id,
            party_size=2,
            seated_at=datetime.utcnow() - timedelta(days=i % 30),
        )
        db_session.add(visit)
        await db_session.flush()

        order = OrderItem(
            visit_id=visit.id,
            menu_item_id=popular_item.id,
            quantity=1,
            unit_price=popular_item.price,
            total_price=popular_item.price,
            ordered_at=visit.seated_at,
        )
        db_session.add(order)

    await db_session.commit()

    # Test HTTP API endpoint
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/restaurants/{restaurant.id}/menu/pricing-recommendations",
            params={"lookback_days": 30}
        )

    # Validate HTTP response
    assert response.status_code == 200
    data = response.json()

    assert "restaurant_id" in data
    assert "total_recommendations" in data
    assert "recommendations" in data
    assert data["analysis_period_days"] == 30
    assert data["total_recommendations"] >= 1

    # Validate response schema
    rec = data["recommendations"][0]
    assert "item_name" in rec
    assert "current_price" in rec
    assert "action" in rec
    assert rec["action"] in ["increase", "decrease", "maintain", "remove"]


@pytest.mark.asyncio
async def test_top_sellers_api_endpoint(db_session):
    """Test GET /menu/top-sellers API endpoint."""
    restaurant = Restaurant(name="API Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    items = [
        MenuItem(restaurant_id=restaurant.id, name="Expensive Steak", price=29.99, is_available=True),
        MenuItem(restaurant_id=restaurant.id, name="Cheap Fries", price=3.99, is_available=True),
    ]
    db_session.add_all(items)
    await db_session.flush()

    table = Table(restaurant_id=restaurant.id, table_number="T1", capacity=4, table_type="table", state="clean")
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(restaurant_id=restaurant.id, waiter_id=waiter.id, clock_in=datetime.utcnow(), status="active")
    db_session.add(shift)
    await db_session.flush()

    # Create orders for both items
    for item in items:
        for i in range(10):
            visit = Visit(
                restaurant_id=restaurant.id,
                table_id=table.id,
                waiter_id=waiter.id,
                shift_id=shift.id,
                party_size=2,
                seated_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(visit)
            await db_session.flush()

            order = OrderItem(
                visit_id=visit.id,
                menu_item_id=item.id,
                quantity=1,
                unit_price=item.price,
                total_price=item.price,
                ordered_at=visit.seated_at,
            )
            db_session.add(order)

    await db_session.commit()

    # Test HTTP endpoint
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/restaurants/{restaurant.id}/menu/top-sellers",
            params={"period_days": 7, "limit": 10}
        )

    assert response.status_code == 200
    data = response.json()

    assert "top_sellers" in data
    assert len(data["top_sellers"]) == 2

    # Steak should be #1 by revenue
    assert data["top_sellers"][0]["item_name"] == "Expensive Steak"
    assert data["top_sellers"][0]["total_revenue"] > data["top_sellers"][1]["total_revenue"]


@pytest.mark.asyncio
async def test_shopping_list_api_endpoint(db_session):
    """Test GET /inventory/shopping-list API endpoint."""
    restaurant = Restaurant(name="API Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # Low stock ingredient
    chicken = Ingredient(
        restaurant_id=restaurant.id,
        name="Chicken Breast",
        category="Protein",
        unit="lb",
        cost_per_unit=3.50,
        supplier="Sysco",
        par_level=50,
        current_stock=10,
    )
    db_session.add(chicken)
    await db_session.flush()

    chicken_dish = MenuItem(restaurant_id=restaurant.id, name="Grilled Chicken", price=14.99, is_available=True)
    db_session.add(chicken_dish)
    await db_session.flush()

    recipe = Recipe(menu_item_id=chicken_dish.id, ingredient_id=chicken.id, quantity=0.5, unit="lb")
    db_session.add(recipe)
    await db_session.flush()

    # Create historical orders
    table = Table(restaurant_id=restaurant.id, table_number="T1", capacity=4, table_type="table", state="clean")
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(restaurant_id=restaurant.id, waiter_id=waiter.id, clock_in=datetime.utcnow(), status="active")
    db_session.add(shift)
    await db_session.flush()

    for i in range(30):
        visit = Visit(
            restaurant_id=restaurant.id,
            table_id=table.id,
            waiter_id=waiter.id,
            shift_id=shift.id,
            party_size=2,
            seated_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(visit)
        await db_session.flush()

        order = OrderItem(
            visit_id=visit.id,
            menu_item_id=chicken_dish.id,
            quantity=1,
            unit_price=chicken_dish.price,
            total_price=chicken_dish.price,
            ordered_at=visit.seated_at,
        )
        db_session.add(order)

    await db_session.commit()

    # Test HTTP endpoint
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/restaurants/{restaurant.id}/inventory/shopping-list",
            params={"forecast_days": 7}
        )

    assert response.status_code == 200
    data = response.json()

    assert "ingredients" in data
    assert "total_cost" in data
    assert data["total_items"] >= 1

    chicken_item = next((i for i in data["ingredients"] if i["name"] == "Chicken Breast"), None)
    assert chicken_item is not None
    assert chicken_item["quantity_to_order"] > 0
    assert chicken_item["urgency"] == "high"


@pytest.mark.asyncio
async def test_stock_alerts_api_endpoint(db_session):
    """Test GET /inventory/stock-alerts API endpoint."""
    restaurant = Restaurant(name="API Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    low_stock = Ingredient(
        restaurant_id=restaurant.id,
        name="Tomatoes",
        category="Vegetables",
        unit="lb",
        cost_per_unit=2.00,
        supplier="Local Farm",
        par_level=30,
        current_stock=5,
    )
    good_stock = Ingredient(
        restaurant_id=restaurant.id,
        name="Flour",
        category="Grains",
        unit="lb",
        cost_per_unit=1.50,
        supplier="Bulk Foods",
        par_level=100,
        current_stock=120,
    )
    db_session.add_all([low_stock, good_stock])
    await db_session.commit()

    # Test HTTP endpoint
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/restaurants/{restaurant.id}/inventory/stock-alerts"
        )

    assert response.status_code == 200
    data = response.json()

    assert "low_stock_items" in data
    assert data["total_alerts"] == 1

    alert = data["low_stock_items"][0]
    assert alert["name"] == "Tomatoes"
    assert alert["urgency"] == "critical"


@pytest.mark.asyncio
async def test_kitchen_routing_api_endpoint(db_session):
    """Test POST /kitchen/visits/{visit_id}/route API endpoint."""
    restaurant = Restaurant(name="API Test Restaurant", timezone="America/New_York", config={})
    db_session.add(restaurant)
    await db_session.flush()

    # Kitchen stations
    grill = KitchenStation(restaurant_id=restaurant.id, name="Grill", is_active=True, max_concurrent_orders=8)
    salad_bar = KitchenStation(restaurant_id=restaurant.id, name="Salad Bar", is_active=True, max_concurrent_orders=10)
    db_session.add_all([grill, salad_bar])
    await db_session.flush()

    # Ingredients
    chicken = Ingredient(
        restaurant_id=restaurant.id, name="Chicken", category="Protein",
        unit="lb", cost_per_unit=3.50, supplier="Sysco", par_level=50, current_stock=30
    )
    greens = Ingredient(
        restaurant_id=restaurant.id, name="Greens", category="Vegetable",
        unit="lb", cost_per_unit=2.00, supplier="Local", par_level=20, current_stock=15
    )
    db_session.add_all([chicken, greens])
    await db_session.flush()

    # Menu items
    grilled_chicken = MenuItem(restaurant_id=restaurant.id, name="Grilled Chicken", price=14.99, is_available=True)
    caesar_salad = MenuItem(restaurant_id=restaurant.id, name="Caesar Salad", price=9.99, is_available=True)
    db_session.add_all([grilled_chicken, caesar_salad])
    await db_session.flush()

    # Recipes
    recipe1 = Recipe(menu_item_id=grilled_chicken.id, ingredient_id=chicken.id, quantity=0.5, unit="lb")
    recipe2 = Recipe(menu_item_id=caesar_salad.id, ingredient_id=greens.id, quantity=0.25, unit="lb")
    db_session.add_all([recipe1, recipe2])
    await db_session.flush()

    # Visit with orders
    table = Table(restaurant_id=restaurant.id, table_number="T1", capacity=4, table_type="table", state="clean")
    waiter = Waiter(restaurant_id=restaurant.id, name="Test Waiter")
    db_session.add_all([table, waiter])
    await db_session.flush()

    shift = Shift(restaurant_id=restaurant.id, waiter_id=waiter.id, clock_in=datetime.utcnow(), status="active")
    db_session.add(shift)
    await db_session.flush()

    visit = Visit(
        restaurant_id=restaurant.id,
        table_id=table.id,
        waiter_id=waiter.id,
        shift_id=shift.id,
        party_size=2,
        seated_at=datetime.utcnow(),
    )
    db_session.add(visit)
    await db_session.flush()

    order1 = OrderItem(
        visit_id=visit.id, menu_item_id=grilled_chicken.id, quantity=2,
        unit_price=grilled_chicken.price, total_price=grilled_chicken.price * 2, ordered_at=visit.seated_at
    )
    order2 = OrderItem(
        visit_id=visit.id, menu_item_id=caesar_salad.id, quantity=1,
        unit_price=caesar_salad.price, total_price=caesar_salad.price, ordered_at=visit.seated_at
    )
    db_session.add_all([order1, order2])
    await db_session.commit()

    # Test HTTP endpoint
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/kitchen/visits/{visit.id}/route")

    assert response.status_code == 200
    data = response.json()

    assert "station_assignments" in data
    assert "batch_recommendations" in data
    assert data["total_items"] == 2
    assert len(data["station_assignments"]) >= 1
    assert len(data["batch_recommendations"]) >= 1


@pytest.mark.asyncio
async def test_kitchen_routing_api_404_error(db_session):
    """Test POST /kitchen/visits/{visit_id}/route returns 404 for invalid visit."""
    from uuid import uuid4
    fake_visit_id = uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/kitchen/visits/{fake_visit_id}/route")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
