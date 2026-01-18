"""Demo replay API endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.table import Table
from app.schemas.demo import (
    DemoInitiateRequest,
    DemoInitiateResponse,
    DemoSeededWaiter,
    DemoSummaryResponse,
    DemoSummaryTable,
    DemoSummaryWaiter,
    DemoStatusResponse,
    DemoStopResponse,
)
from app.services.demo_replay_service import demo_replay_manager
from app.services.routing_service import RoutingService
from app.services.seed_service import SeedService
from app.services.waiter_service import WaiterService
from app.services.restaurant_resolver import resolve_restaurant_id

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])
summary_router = APIRouter(prefix="/api/v1", tags=["demo"])


@router.post("/initiate", response_model=DemoInitiateResponse)
async def initiate_demo(
    request: DemoInitiateRequest,
    session: AsyncSession = Depends(get_session),
) -> DemoInitiateResponse:
    """Start demo replay from precomputed results."""
    try:
        resolved_restaurant_id = await resolve_restaurant_id(
            request.restaurant_id, session
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    seeded_waiters = []
    if request.seed_shift_snapshot and request.seed_shift_snapshot.enabled:
        seed_service = SeedService(session)
        seeded = await seed_service.seed_active_shift_snapshot(
            restaurant_id=resolved_restaurant_id,
            waiter_specs=[
                waiter.model_dump()
                for waiter in request.seed_shift_snapshot.waiters
            ],
        )
        seeded_waiters = [
            DemoSeededWaiter(
                waiter_id=item["waiter_id"],
                shift_id=item["shift_id"],
                name=item["name"],
                current_tables=item["current_tables"],
            )
            for item in seeded
        ]

    try:
        session_state = await demo_replay_manager.initiate(
            restaurant_id=resolved_restaurant_id,
            demos=[demo.model_dump() for demo in request.demos],
            speed=request.speed,
            overwrite=request.overwrite,
            mapping_mode=request.mapping_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return DemoInitiateResponse(
        status="started",
        session_id=session_state.session_id,
        camera_count=len(session_state.camera_states),
        mapping_mode=session_state.mapping_mode,
        warnings=session_state.warnings,
        seeded_waiters=seeded_waiters,
    )


@router.post("/stop", response_model=DemoStopResponse)
async def stop_demo() -> DemoStopResponse:
    """Stop active demo replay."""
    await demo_replay_manager.stop()
    return DemoStopResponse(status="stopped")


@router.get("/status", response_model=DemoStatusResponse)
async def demo_status() -> DemoStatusResponse:
    """Get current demo replay status."""
    session_state = demo_replay_manager.get_status()
    if not session_state:
        return DemoStatusResponse(status="idle")

    return DemoStatusResponse(
        status="running" if session_state.running else "stopped",
        session_id=session_state.session_id,
        running=session_state.running,
        started_at=session_state.started_at,
        speed=session_state.speed,
        cameras=[
            {
                "camera_id": state.camera_id,
                "results_path": state.results_path,
                "total_frames": state.total_frames,
                "current_frame_index": state.current_frame_index,
                "last_timestamp_s": state.last_timestamp_s,
            }
            for state in session_state.camera_states.values()
        ],
    )


@summary_router.get(
    "/restaurants/{restaurant_id}/demo/summary",
    response_model=DemoSummaryResponse,
)
async def demo_summary(
    restaurant_id: str,
    min_capacity: int = Query(1, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> DemoSummaryResponse:
    """Return ranked waiters and available tables for demo host UI."""
    seed_service = SeedService(session)
    try:
        resolved_restaurant_id = await resolve_restaurant_id(restaurant_id, session)
    except ValueError as exc:
        if "No restaurants found" in str(exc):
            await seed_service.ensure_default_data()
            resolved_restaurant_id = await resolve_restaurant_id(restaurant_id, session)
        else:
            raise HTTPException(status_code=400, detail=str(exc))

    routing_service = RoutingService(session)
    restaurant = await routing_service._get_restaurant(resolved_restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    config = routing_service._get_routing_config(restaurant)

    waiter_service = WaiterService(session)
    active_waiters = await waiter_service.get_active_waiters(resolved_restaurant_id)
    if not active_waiters:
        await seed_service.seed_active_shift_snapshot(
            restaurant_id=resolved_restaurant_id
        )

    available_waiters = await waiter_service.get_available_waiters(
        restaurant_id=resolved_restaurant_id,
        section_ids=None,
        max_tables=config.max_tables_per_waiter,
    )

    shift_ids = {}
    for waiter in available_waiters:
        shift = await waiter_service.get_active_shift_for_waiter(waiter.id)
        if shift:
            shift_ids[waiter.id] = shift.id

    ranked_waiters = await waiter_service.score_and_rank_waiters(
        waiters=available_waiters,
        config=config,
        shift_ids=shift_ids,
    )

    stmt = (
        select(Table)
        .where(Table.restaurant_id == resolved_restaurant_id)
        .where(Table.state == "clean")
        .where(Table.is_active == True)  # noqa: E712
        .where(Table.capacity >= min_capacity)
        .options(selectinload(Table.section))
        .order_by(Table.capacity, Table.table_number)
    )
    result = await session.execute(stmt)
    tables = result.scalars().all()

    table_payload = [
        DemoSummaryTable(
            table_id=table.id,
            table_number=table.table_number,
            capacity=table.capacity,
            table_type=table.table_type,
            location=table.location,
            section_id=table.section_id,
            section_name=table.section.name if table.section else None,
        )
        for table in tables
    ]

    waiter_payload = [
        DemoSummaryWaiter(
            waiter_id=waiter.id,
            name=waiter.name,
            tier=waiter.tier,
            section_id=waiter.section_id,
            status=waiter.status,
            current_tables=waiter.current_tables,
            current_covers=waiter.current_covers,
            current_tips=float(waiter.current_tips),
            priority_score=score,
            rank=idx + 1,
        )
        for idx, (waiter, score) in enumerate(ranked_waiters)
    ]

    return DemoSummaryResponse(
        generated_at=datetime.utcnow(),
        routing_mode=config.mode,
        open_tables_count=len(table_payload),
        tables=table_payload,
        waiters=waiter_payload,
    )
