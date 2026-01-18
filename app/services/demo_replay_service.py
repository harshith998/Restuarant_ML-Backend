from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select

from app.database import get_session_context
from app.models.restaurant import Restaurant
from app.models.table import Table
from app.models.metrics import TableStateLog
from app.websocket.demo import demo_ws_manager

LOGGER = logging.getLogger("demo-replay")


@dataclass
class DemoCameraState:
    camera_id: str
    results_path: str
    total_frames: int
    current_frame_index: int = -1
    last_timestamp_s: Optional[float] = None


@dataclass
class DemoSessionState:
    session_id: UUID
    restaurant_id: UUID
    speed: float
    overwrite: bool
    mapping_mode: str
    started_at: datetime
    running: bool
    stop_event: asyncio.Event
    camera_states: Dict[str, DemoCameraState]
    tasks: List[asyncio.Task]
    warnings: List[str]


class DemoReplayManager:
    """Manages demo replay sessions."""

    def __init__(self) -> None:
        self._session: Optional[DemoSessionState] = None
        self._lock = asyncio.Lock()

    async def initiate(
        self,
        restaurant_id: UUID,
        demos: List[Dict[str, Any]],
        speed: float = 1.0,
        overwrite: bool = True,
        mapping_mode: str = "auto",
    ) -> DemoSessionState:
        async with self._lock:
            if self._session and self._session.running:
                # Avoid deadlock: stop in-place while holding the lock.
                await self._stop_unlocked()

            warnings: List[str] = []
            session_id = uuid4()
            stop_event = asyncio.Event()
            camera_states: Dict[str, DemoCameraState] = {}
            tasks: List[asyncio.Task] = []

            async with get_session_context() as session:
                await self._ensure_restaurant(session, restaurant_id)
                db_table_numbers = await self._get_db_table_numbers(session, restaurant_id)

            for demo in demos:
                camera_id = demo["camera_id"]
                results_path = self._resolve_path(demo["results_path"])

                camera_states[camera_id] = DemoCameraState(
                    camera_id=camera_id,
                    results_path=str(results_path),
                    total_frames=0,
                )

                task = asyncio.create_task(
                    self._run_camera_task(
                        restaurant_id=restaurant_id,
                        camera_state=camera_states[camera_id],
                        results_path=results_path,
                        table_map_override=demo.get("table_map"),
                        db_table_numbers=db_table_numbers,
                        speed=speed,
                        overwrite=overwrite,
                        mapping_mode=mapping_mode,
                        stop_event=stop_event,
                    )
                )
                tasks.append(task)

            self._session = DemoSessionState(
                session_id=session_id,
                restaurant_id=restaurant_id,
                speed=speed,
                overwrite=overwrite,
                mapping_mode=mapping_mode,
                started_at=datetime.utcnow(),
                running=True,
                stop_event=stop_event,
                camera_states=camera_states,
                tasks=tasks,
                warnings=warnings,
            )

            return self._session

    async def _stop_unlocked(self) -> None:
        if not self._session:
            return
        self._session.stop_event.set()
        for task in self._session.tasks:
            if not task.done():
                task.cancel()
        self._session.running = False

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_unlocked()

    def get_status(self) -> Optional[DemoSessionState]:
        return self._session

    async def _ensure_restaurant(self, session, restaurant_id: UUID) -> None:
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Restaurant {restaurant_id} not found")

    async def _get_db_table_numbers(self, session, restaurant_id: UUID) -> List[str]:
        stmt = select(Table.table_number).where(Table.restaurant_id == restaurant_id)
        result = await session.execute(stmt)
        return sorted([row[0] for row in result.all()])

    def _resolve_path(self, results_path: str) -> Path:
        path = Path(results_path)
        if path.is_absolute():
            return path
        repo_root = Path(__file__).resolve().parents[2]
        return (repo_root / path).resolve()

    def _load_results(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise ValueError(f"Results file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _extract_table_numbers(self, results: Dict[str, Any]) -> Set[str]:
        frames = results.get("frame_results", [])
        if not frames:
            return set()
        table_numbers: Set[str] = set()
        for table in frames[0].get("tables", []):
            table_num = table.get("table_number")
            if table_num:
                table_numbers.add(table_num)
        return table_numbers

    async def _append_warning(self, message: str) -> None:
        async with self._lock:
            if self._session:
                self._session.warnings.append(message)

    def _build_table_mapping(
        self,
        table_numbers: Iterable[str],
        db_table_numbers: List[str],
        explicit_map: Optional[Dict[str, str]],
        mapping_mode: str,
    ) -> Tuple[Dict[str, str], List[str]]:
        warnings: List[str] = []
        json_numbers = sorted(set(table_numbers))
        db_numbers = sorted(set(db_table_numbers))

        if explicit_map:
            mapping = {}
            for json_num, db_num in explicit_map.items():
                if json_num not in json_numbers:
                    warnings.append(f"Mapping key {json_num} not found in JSON")
                    continue
                if db_num not in db_numbers:
                    warnings.append(f"Mapping target {db_num} not found in DB")
                    continue
                mapping[json_num] = db_num
            return mapping, warnings

        if mapping_mode == "direct_only":
            if set(json_numbers) != set(db_numbers):
                raise ValueError("JSON table numbers do not match DB table numbers")
            return {num: num for num in json_numbers}, warnings

        # Auto mapping: direct if exact match, else map by index order.
        if set(json_numbers) == set(db_numbers):
            return {num: num for num in json_numbers}, warnings

        if not db_numbers:
            raise ValueError("No tables found in DB for auto-mapping")

        mapping: Dict[str, str] = {}
        for idx, json_num in enumerate(json_numbers):
            if idx >= len(db_numbers):
                warnings.append(f"No DB table available for {json_num}")
                continue
            mapping[json_num] = db_numbers[idx]

        if len(json_numbers) > len(db_numbers):
            warnings.append(
                f"JSON has {len(json_numbers)} tables but DB has {len(db_numbers)}"
            )

        return mapping, warnings

    async def _run_camera_replay(
        self,
        restaurant_id: UUID,
        camera_state: DemoCameraState,
        results: Dict[str, Any],
        table_map: Dict[str, str],
        speed: float,
        overwrite: bool,
        stop_event: asyncio.Event,
    ) -> None:
        frames = results.get("frame_results", [])
        if not frames:
            return

        prev_timestamp_s: Optional[float] = None

        async with get_session_context() as session:
            table_lookup = await self._fetch_tables(session, restaurant_id, table_map)

            for frame in frames:
                if stop_event.is_set():
                    break

                timestamp_s = frame.get("timestamp_s")
                if prev_timestamp_s is not None and timestamp_s is not None:
                    delay = max(0.0, (timestamp_s - prev_timestamp_s) / speed)
                    if delay > 0:
                        await asyncio.sleep(delay)
                prev_timestamp_s = timestamp_s

                updates = []
                for table in frame.get("tables", []):
                    json_table_num = table.get("table_number")
                    if not json_table_num or json_table_num not in table_map:
                        continue
                    db_table_num = table_map[json_table_num]
                    db_table = table_lookup.get(db_table_num)
                    if not db_table:
                        continue

                    new_state = self._pick_state(table)
                    if not new_state:
                        continue

                    confidence = table.get("confidence")
                    updates.append((db_table, new_state, confidence))

                if updates:
                    for db_table, new_state, confidence in updates:
                        if not overwrite and db_table.state == new_state:
                            continue
                        if db_table.state == new_state:
                            continue

                        log = TableStateLog(
                            table_id=db_table.id,
                            previous_state=db_table.state,
                            new_state=new_state,
                            confidence=confidence,
                            source="demo",
                        )
                        session.add(log)
                        db_table.state = new_state
                        db_table.state_confidence = confidence
                        db_table.state_updated_at = datetime.utcnow()

                        await demo_ws_manager.broadcast({
                            "type": "table.state",
                            "camera_id": camera_state.camera_id,
                            "table_id": str(db_table.id),
                            "table_number": db_table.table_number,
                            "state": new_state,
                            "confidence": confidence,
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                    await session.commit()

                camera_state.current_frame_index = frame.get("frame_index", -1)
                camera_state.last_timestamp_s = timestamp_s

    async def _run_camera_task(
        self,
        restaurant_id: UUID,
        camera_state: DemoCameraState,
        results_path: Path,
        table_map_override: Optional[Dict[str, str]],
        db_table_numbers: List[str],
        speed: float,
        overwrite: bool,
        mapping_mode: str,
        stop_event: asyncio.Event,
    ) -> None:
        try:
            results = self._load_results(results_path)
        except Exception as exc:
            await self._append_warning(f"{camera_state.camera_id}: {exc}")
            return

        camera_state.total_frames = len(results.get("frame_results", []))

        table_numbers = self._extract_table_numbers(results)
        if not table_numbers:
            await self._append_warning(
                f"{camera_state.camera_id}: No table numbers found in JSON"
            )
            return

        try:
            mapping, mapping_warnings = self._build_table_mapping(
                table_numbers=table_numbers,
                db_table_numbers=db_table_numbers,
                explicit_map=table_map_override,
                mapping_mode=mapping_mode,
            )
        except Exception as exc:
            await self._append_warning(f"{camera_state.camera_id}: {exc}")
            return

        for warning in mapping_warnings:
            await self._append_warning(f"{camera_state.camera_id}: {warning}")

        if not mapping:
            await self._append_warning(
                f"{camera_state.camera_id}: No table mappings resolved"
            )
            return

        await self._run_camera_replay(
            restaurant_id=restaurant_id,
            camera_state=camera_state,
            results=results,
            table_map=mapping,
            speed=speed,
            overwrite=overwrite,
            stop_event=stop_event,
        )

    async def _fetch_tables(
        self,
        session,
        restaurant_id: UUID,
        table_map: Dict[str, str],
    ) -> Dict[str, Table]:
        db_table_numbers = list(set(table_map.values()))
        stmt = (
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .where(Table.table_number.in_(db_table_numbers))
        )
        result = await session.execute(stmt)
        tables = result.scalars().all()
        return {table.table_number: table for table in tables}

    def _pick_state(self, table_data: Dict[str, Any]) -> Optional[str]:
        smoothed = table_data.get("smoothed_state")
        if smoothed and smoothed != "unknown":
            return smoothed
        raw_state = table_data.get("raw_state")
        if raw_state and raw_state != "unknown":
            return raw_state
        return None


demo_replay_manager = DemoReplayManager()
