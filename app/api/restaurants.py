"""
REST API endpoints for restaurant management.
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.restaurant import Restaurant
from app.schemas.restaurant import RestaurantCreate, RestaurantRead, RestaurantUpdate

router = APIRouter(prefix="/api/v1", tags=["restaurants"])


@router.get("/restaurants", response_model=List[RestaurantRead])
async def list_restaurants(
    session: AsyncSession = Depends(get_session),
) -> List[RestaurantRead]:
    """Get all restaurants."""
    result = await session.execute(
        select(Restaurant).order_by(Restaurant.name)
    )
    restaurants = result.scalars().all()
    return [RestaurantRead.model_validate(r) for r in restaurants]


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantRead)
async def get_restaurant(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> RestaurantRead:
    """Get a restaurant by ID."""
    result = await session.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    return RestaurantRead.model_validate(restaurant)


@router.post("/restaurants", response_model=RestaurantRead)
async def create_restaurant(
    data: RestaurantCreate,
    session: AsyncSession = Depends(get_session),
) -> RestaurantRead:
    """Create a new restaurant."""
    restaurant = Restaurant(
        name=data.name,
        timezone=data.timezone or "America/New_York",
        config=data.config or {},
    )
    session.add(restaurant)
    await session.commit()
    await session.refresh(restaurant)

    return RestaurantRead.model_validate(restaurant)


@router.patch("/restaurants/{restaurant_id}", response_model=RestaurantRead)
async def update_restaurant(
    restaurant_id: UUID,
    data: RestaurantUpdate,
    session: AsyncSession = Depends(get_session),
) -> RestaurantRead:
    """Update a restaurant."""
    result = await session.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(restaurant, field, value)

    await session.commit()
    await session.refresh(restaurant)

    return RestaurantRead.model_validate(restaurant)


@router.get("/restaurants/{restaurant_id}/config")
async def get_restaurant_config(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get restaurant configuration including routing settings."""
    result = await session.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    config = restaurant.config or {}

    return {
        "restaurant_id": str(restaurant_id),
        "name": restaurant.name,
        "timezone": restaurant.timezone,
        "routing": config.get("routing", {
            "mode": "section",
            "max_tables_per_waiter": 5,
        }),
        "raw_config": config,
    }
