from __future__ import annotations

import logging
from uuid import UUID

from app.config import get_settings

logger = logging.getLogger(__name__)


def resolve_reviews_restaurant_id(restaurant_id: str) -> UUID:
    """Resolve restaurant_id for reviews only, allowing alias mapping."""
    settings = get_settings()
    aliases = settings.reviews_restaurant_alias_map
    canonical = aliases.get(restaurant_id, restaurant_id)
    try:
        return UUID(canonical)
    except ValueError as exc:
        logger.error("Invalid reviews restaurant_id: %s", restaurant_id)
        raise ValueError(f"Invalid restaurant_id: {restaurant_id}") from exc
