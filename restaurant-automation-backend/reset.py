"""
Reset all JSON files to their original state for fresh testing.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

ORIGINAL_RESTAURANT_STATE = {
    "floor_map_version": "v1",
    "tables": [
        {"table_id": "A1", "section": "A", "type": "window", "capacity": 2, "state": "clean", "current_group_id": None},
        {"table_id": "A2", "section": "A", "type": "booth", "capacity": 4, "state": "clean", "current_group_id": None},
        {"table_id": "A3", "section": "A", "type": "regular", "capacity": 6, "state": "clean", "current_group_id": None},
        {"table_id": "B1", "section": "B", "type": "window", "capacity": 4, "state": "clean", "current_group_id": None},
        {"table_id": "B2", "section": "B", "type": "booth", "capacity": 6, "state": "clean", "current_group_id": None},
        {"table_id": "B3", "section": "B", "type": "regular", "capacity": 8, "state": "clean", "current_group_id": None},
        {"table_id": "C1", "section": "C", "type": "window", "capacity": 3, "state": "clean", "current_group_id": None},
        {"table_id": "C2", "section": "C", "type": "booth", "capacity": 4, "state": "clean", "current_group_id": None},
        {"table_id": "C3", "section": "C", "type": "regular", "capacity": 5, "state": "clean", "current_group_id": None},
        {"table_id": "D1", "section": "D", "type": "bar", "capacity": 2, "state": "clean", "current_group_id": None},
        {"table_id": "D2", "section": "D", "type": "booth", "capacity": 5, "state": "clean", "current_group_id": None},
        {"table_id": "D3", "section": "D", "type": "bar", "capacity": 3, "state": "clean", "current_group_id": None}
    ],
    "waiters": [
        {"id": "W1", "name": "Sarah", "score": 8.5, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "A"},
        {"id": "W2", "name": "Mike", "score": 7.2, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "A"},
        {"id": "W3", "name": "Emma", "score": 9.1, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "B"},
        {"id": "W4", "name": "Jake", "score": 6.8, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "B"},
        {"id": "W5", "name": "Lisa", "score": 8.0, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "C"},
        {"id": "W6", "name": "Tom", "score": 7.5, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "C"},
        {"id": "W7", "name": "Anna", "score": 8.8, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "D"},
        {"id": "W8", "name": "Chris", "score": 7.0, "current_tip_total": 0.00, "live_tables": 0, "status": "available", "section": "D"}
    ],
    "cleaners": [
        {"id": "CL1", "name": "Roberto", "status": "idle"},
        {"id": "CL2", "name": "Maria", "status": "idle"}
    ],
    "hosts": [
        {"id": "H1", "name": "Jennifer", "on_duty": True}
    ]
}

ORIGINAL_ML_INPUT = {
    "camera_id": "CAM_MAIN_01",
    "frame_timestamp": "2026-01-11T18:30:00Z",
    "tables": [
        {"table_id": "A1", "predicted_state": "clean", "state_confidence": 0.95, "last_state_change": "2026-01-11T18:25:00Z"},
        {"table_id": "A2", "predicted_state": "occupied", "state_confidence": 0.98, "last_state_change": "2026-01-11T18:10:00Z"},
        {"table_id": "A3", "predicted_state": "clean", "state_confidence": 0.92, "last_state_change": "2026-01-11T18:20:00Z"},
        {"table_id": "B1", "predicted_state": "dirty", "state_confidence": 0.89, "last_state_change": "2026-01-11T18:28:00Z"},
        {"table_id": "B2", "predicted_state": "clean", "state_confidence": 0.94, "last_state_change": "2026-01-11T18:15:00Z"},
        {"table_id": "B3", "predicted_state": "clean", "state_confidence": 0.97, "last_state_change": "2026-01-11T18:22:00Z"},
        {"table_id": "C1", "predicted_state": "occupied", "state_confidence": 0.99, "last_state_change": "2026-01-11T17:45:00Z"},
        {"table_id": "C2", "predicted_state": "clean", "state_confidence": 0.91, "last_state_change": "2026-01-11T18:18:00Z"},
        {"table_id": "C3", "predicted_state": "dirty", "state_confidence": 0.87, "last_state_change": "2026-01-11T18:29:00Z"},
        {"table_id": "D1", "predicted_state": "clean", "state_confidence": 0.96, "last_state_change": "2026-01-11T18:12:00Z"},
        {"table_id": "D2", "predicted_state": "clean", "state_confidence": 0.93, "last_state_change": "2026-01-11T18:08:00Z"},
        {"table_id": "D3", "predicted_state": "occupied", "state_confidence": 0.97, "last_state_change": "2026-01-11T18:00:00Z"}
    ]
}

ORIGINAL_UI_INPUT = {
    "host": {
        "id": "H1",
        "name": "Jennifer"
    },
    "request": {
        "group_id": "GRP_20260111_001",
        "party_size": 4,
        "is_reserved": False,
        "table_preference": "booth",
        "requested_time": "2026-01-11T18:30:00Z"
    },
    "floor_map_version": "v1"
}


def save_json(filename: str, data: dict):
    """Save data to JSON file."""
    with open(DATA_DIR / filename, "w") as f:
        json.dump(data, f, indent=2)


def reset_all():
    """Reset all JSON files to original state."""
    print("Resetting all data files...")

    save_json("restaurant_state.json", ORIGINAL_RESTAURANT_STATE)
    print("  ✓ restaurant_state.json")

    save_json("ml_input.json", ORIGINAL_ML_INPUT)
    print("  ✓ ml_input.json")

    save_json("ui_input.json", ORIGINAL_UI_INPUT)
    print("  ✓ ui_input.json")

    print("\nAll files reset to original state!")


if __name__ == "__main__":
    reset_all()
