from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restaurant import Restaurant


async def resolve_restaurant_id(
    restaurant_id: str,
    session: AsyncSession,
) -> UUID:
    """Resolve restaurant_id, supporting 'default' for demo usage."""
    if restaurant_id == "default":
        # Prefer Mimosas if present, otherwise fall back to first restaurant.
        stmt = select(Restaurant).where(Restaurant.name == "Mimosas")
        result = await session.execute(stmt)
        restaurant = result.scalar_one_or_none()
        if restaurant:
            return restaurant.id

        result = await session.execute(
            select(Restaurant).order_by(Restaurant.id).limit(1)
        )
        restaurant = result.scalar_one_or_none()
        if restaurant:
            return restaurant.id

        raise ValueError("No restaurants found")

    try:
        return UUID(restaurant_id)
    except ValueError as exc:
        raise ValueError(f"Invalid restaurant_id: {restaurant_id}") from exc
