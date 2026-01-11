"""
Restaurant Table & Waiter Router
Routes incoming party to best available table AND assigns optimal waiter.
Updates restaurant_state.json after each routing cycle.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Configuration
MAX_TABLES_PER_WAITER = 5
EFFICIENCY_WEIGHT = 1.0      # Base weight for efficiency score
WORKLOAD_PENALTY = 3.0       # Penalty for current table load
TIP_PENALTY = 2.0            # Penalty for already having high tips


def load_json(filename: str) -> dict:
    """Load a JSON file from the data directory."""
    with open(DATA_DIR / filename, "r") as f:
        return json.load(f)


def save_json(filename: str, data: dict):
    """Save data to JSON file."""
    with open(DATA_DIR / filename, "w") as f:
        json.dump(data, f, indent=2)


def merge_ml_state(tables: list, ml_input: dict) -> list:
    """Merge ML predictions into table data."""
    ml_states = {t["table_id"]: t for t in ml_input["tables"]}

    for table in tables:
        ml_data = ml_states.get(table["table_id"])
        if ml_data:
            table["state"] = ml_data["predicted_state"]
            table["state_confidence"] = ml_data["state_confidence"]
        else:
            table["state"] = "unknown"
            table["state_confidence"] = 0.0

    return tables


# =============================================================================
# TABLE FILTERING
# =============================================================================

def filter_tables_by_clean_and_capacity(tables: list, party_size: int) -> list:
    """Filter tables that are clean and have enough capacity."""
    return [t for t in tables if t["state"] == "clean" and t["capacity"] >= party_size]


def filter_tables_by_preference(tables: list, preference: str) -> list:
    """Filter tables by type preference."""
    if not preference or preference == "none":
        return tables
    return [t for t in tables if t["type"] == preference]


def get_sections_from_tables(tables: list) -> set:
    """Get unique sections from a list of tables."""
    return set(t["section"] for t in tables)


def get_tables_in_section(tables: list, section: str) -> list:
    """Get tables in a specific section."""
    return [t for t in tables if t["section"] == section]


# =============================================================================
# WAITER FILTERING & SCORING
# =============================================================================

def is_waiter_available(waiter: dict) -> bool:
    """Check if waiter can take more tables."""
    # Must not be on_break or busy
    if waiter["status"] in ("on_break", "busy"):
        return False
    # Must not be at max capacity
    if waiter["live_tables"] >= MAX_TABLES_PER_WAITER:
        return False
    return True


def filter_available_waiters(waiters: list, valid_sections: set) -> list:
    """Get waiters who are available and in valid sections."""
    return [
        w for w in waiters
        if is_waiter_available(w) and w["section"] in valid_sections
    ]


def calculate_waiter_priority(waiter: dict, total_tips: float) -> float:
    """
    Calculate waiter priority score for assignment.
    Higher score = higher priority for next table.

    Formula:
      priority = efficiency_score * weight
               - (tables / max_tables) * workload_penalty
               - (tip_share) * tip_penalty
    """
    efficiency = waiter["score"] * EFFICIENCY_WEIGHT

    # Workload penalty: 0 tables = 0 penalty, max tables = full penalty
    workload = (waiter["live_tables"] / MAX_TABLES_PER_WAITER) * WORKLOAD_PENALTY

    # Tip penalty: proportion of total tips
    if total_tips > 0:
        tip_share = (waiter["current_tip_total"] / total_tips) * TIP_PENALTY
    else:
        tip_share = 0  # No tips yet, no penalty

    priority = efficiency - workload - tip_share
    return priority


def score_and_rank_waiters(waiters: list) -> list:
    """Score all waiters and return sorted by priority (highest first)."""
    if not waiters:
        return []

    # Calculate total tips for relative scoring
    total_tips = sum(w["current_tip_total"] for w in waiters)

    # Score each waiter
    scored = []
    for w in waiters:
        priority = calculate_waiter_priority(w, total_tips)
        scored.append({
            "waiter": w,
            "priority": priority
        })

    # Sort by priority descending
    scored.sort(key=lambda x: x["priority"], reverse=True)
    return scored


# =============================================================================
# COMBINED ROUTING
# =============================================================================

def route_with_preference(tables: list, waiters: list, party_size: int, preference: str) -> dict:
    """
    Attempt to route with preference.
    Returns dict with success status, candidates, and selected waiter/table.
    """
    result = {
        "success": False,
        "tables_clean_capacity": [],
        "tables_with_preference": [],
        "valid_sections": set(),
        "available_waiters": [],
        "ranked_waiters": [],
        "selected_waiter": None,
        "selected_table": None,
        "used_preference": True
    }

    # Step 1: Filter tables by clean + capacity
    result["tables_clean_capacity"] = filter_tables_by_clean_and_capacity(tables, party_size)
    if not result["tables_clean_capacity"]:
        return result

    # Step 2: Filter by preference
    result["tables_with_preference"] = filter_tables_by_preference(
        result["tables_clean_capacity"], preference
    )

    # If no preference matches, we'll return and let caller handle backtrack
    if not result["tables_with_preference"]:
        result["used_preference"] = False
        return result

    # Step 3: Get sections from preference-matched tables
    result["valid_sections"] = get_sections_from_tables(result["tables_with_preference"])

    # Step 4: Get available waiters in those sections
    result["available_waiters"] = filter_available_waiters(waiters, result["valid_sections"])

    if not result["available_waiters"]:
        # No waiters available in preference sections
        result["used_preference"] = False
        return result

    # Step 5: Score and rank waiters
    result["ranked_waiters"] = score_and_rank_waiters(result["available_waiters"])

    # Step 6: Select best waiter
    result["selected_waiter"] = result["ranked_waiters"][0]["waiter"]

    # Step 7: Select best table in waiter's section
    waiter_section = result["selected_waiter"]["section"]
    tables_in_section = get_tables_in_section(result["tables_with_preference"], waiter_section)

    # Pick smallest table that fits
    tables_in_section.sort(key=lambda t: t["capacity"])
    result["selected_table"] = tables_in_section[0]

    result["success"] = True
    return result


def route_without_preference(tables: list, waiters: list, party_size: int) -> dict:
    """
    Route without preference constraint (backtrack mode).
    """
    result = {
        "success": False,
        "tables_clean_capacity": [],
        "valid_sections": set(),
        "available_waiters": [],
        "ranked_waiters": [],
        "selected_waiter": None,
        "selected_table": None,
        "used_preference": False
    }

    # Step 1: Filter tables by clean + capacity only
    result["tables_clean_capacity"] = filter_tables_by_clean_and_capacity(tables, party_size)
    if not result["tables_clean_capacity"]:
        return result

    # Step 2: Get all sections from valid tables
    result["valid_sections"] = get_sections_from_tables(result["tables_clean_capacity"])

    # Step 3: Get available waiters in those sections
    result["available_waiters"] = filter_available_waiters(waiters, result["valid_sections"])

    if not result["available_waiters"]:
        return result

    # Step 4: Score and rank waiters
    result["ranked_waiters"] = score_and_rank_waiters(result["available_waiters"])

    # Step 5: Select best waiter
    result["selected_waiter"] = result["ranked_waiters"][0]["waiter"]

    # Step 6: Select best table in waiter's section
    waiter_section = result["selected_waiter"]["section"]
    tables_in_section = get_tables_in_section(result["tables_clean_capacity"], waiter_section)

    # Pick smallest table that fits
    tables_in_section.sort(key=lambda t: t["capacity"])
    result["selected_table"] = tables_in_section[0]

    result["success"] = True
    return result


# =============================================================================
# STATE UPDATE
# =============================================================================

def update_restaurant_state(
    restaurant_state: dict,
    ml_input: dict,
    routed_table_id: str,
    routed_waiter_id: str,
    group_id: str
):
    """
    Update restaurant state with:
    1. All table states from ML predictions
    2. Mark routed table as occupied with group_id
    3. Update waiter: increment live_tables, set status to heading_to_table
    """
    ml_states = {t["table_id"]: t for t in ml_input["tables"]}

    # Update tables
    for table in restaurant_state["tables"]:
        table_id = table["table_id"]

        if table_id == routed_table_id:
            table["state"] = "occupied"
            table["current_group_id"] = group_id
        elif table_id in ml_states:
            ml_state = ml_states[table_id]["predicted_state"]
            table["state"] = ml_state
            if ml_state == "clean":
                table["current_group_id"] = None

    # Update waiter
    for waiter in restaurant_state["waiters"]:
        if waiter["id"] == routed_waiter_id:
            waiter["live_tables"] += 1
            waiter["status"] = "heading_to_table"
            break

    return restaurant_state


# =============================================================================
# MAIN ROUTING FUNCTION
# =============================================================================

def route_party():
    """Main routing function."""
    # Load all data
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    ui_input = load_json("ui_input.json")

    # Extract request details
    request = ui_input["request"]
    party_size = request["party_size"]
    preference = request["table_preference"]
    is_reserved = request["is_reserved"]
    group_id = request["group_id"]

    print("=" * 60)
    print("RESTAURANT TABLE & WAITER ROUTER")
    print("=" * 60)
    print(f"\nRequest: {party_size} guests, preference: {preference}, reserved: {is_reserved}")
    print(f"Group ID: {group_id}")
    print()

    # Merge ML state into tables
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    # Show current states
    print("Current Table States (from ML):")
    print("-" * 50)
    for t in tables:
        print(f"  {t['table_id']}: {t['state']:8} (cap: {t['capacity']}, type: {t['type']}, section: {t['section']})")
    print()

    print("Current Waiter States:")
    print("-" * 50)
    for w in waiters:
        avail = "YES" if is_waiter_available(w) else "NO"
        print(f"  {w['id']} {w['name']:6} | section: {w['section']} | tables: {w['live_tables']}/{MAX_TABLES_PER_WAITER} | status: {w['status']:15} | avail: {avail}")
    print()

    # Try routing with preference first
    backtracked = False
    if preference and preference != "none":
        print(f"Attempting routing with preference: {preference}")
        print("-" * 50)
        result = route_with_preference(tables, waiters, party_size, preference)

        if not result["success"]:
            print(f"  No valid waiter+table combo with preference '{preference}'")
            print(f"  BACKTRACKING to no-preference routing...")
            print()
            backtracked = True
            result = route_without_preference(tables, waiters, party_size)
    else:
        print("Routing without preference...")
        print("-" * 50)
        result = route_without_preference(tables, waiters, party_size)

    # Show routing steps
    print()
    print("Routing Details:")
    print("-" * 50)
    clean_cap_ids = [t["table_id"] for t in result["tables_clean_capacity"]]
    print(f"  Clean + capacity >= {party_size}: {clean_cap_ids}")

    if "tables_with_preference" in result and result["tables_with_preference"]:
        pref_ids = [t["table_id"] for t in result["tables_with_preference"]]
        print(f"  With preference '{preference}': {pref_ids}")

    print(f"  Valid sections: {result['valid_sections']}")

    avail_waiter_info = [(w["id"], w["name"], w["section"]) for w in result["available_waiters"]]
    print(f"  Available waiters: {avail_waiter_info}")

    if result["ranked_waiters"]:
        print(f"  Waiter rankings:")
        for rw in result["ranked_waiters"]:
            w = rw["waiter"]
            print(f"    {w['id']} {w['name']:6} | priority: {rw['priority']:.2f} | score: {w['score']} | tables: {w['live_tables']} | tips: ${w['current_tip_total']:.2f}")
    print()

    # Output result
    print("=" * 60)
    if result["success"]:
        table = result["selected_table"]
        waiter = result["selected_waiter"]

        print("RESULT: ROUTING SUCCESSFUL")
        print("=" * 60)
        if backtracked:
            print("  ** Used backtrack (preference unavailable) **")
        print()
        print("  TABLE:")
        print(f"    Table ID:  {table['table_id']}")
        print(f"    Section:   {table['section']}")
        print(f"    Type:      {table['type']}")
        print(f"    Capacity:  {table['capacity']}")
        print()
        print("  WAITER:")
        print(f"    Waiter ID: {waiter['id']}")
        print(f"    Name:      {waiter['name']}")
        print(f"    Section:   {waiter['section']}")
        print(f"    Score:     {waiter['score']}")
        print(f"    Tables:    {waiter['live_tables']} -> {waiter['live_tables'] + 1}")

        # Update and save restaurant state
        updated_state = update_restaurant_state(
            restaurant_state, ml_input,
            table["table_id"], waiter["id"], group_id
        )
        save_json("restaurant_state.json", updated_state)
        print()
        print(">> State updated: restaurant_state.json saved")
    else:
        print("RESULT: ROUTING FAILED")
        print("=" * 60)
        print("  Could not find available table + waiter combination.")
        if not result["tables_clean_capacity"]:
            print("  Reason: No clean tables with sufficient capacity.")
        elif not result["available_waiters"]:
            print("  Reason: No available waiters in valid sections.")

    print()
    return result


if __name__ == "__main__":
    route_party()
