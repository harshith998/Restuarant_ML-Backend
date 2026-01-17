import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Configuration
MAX_TABLES_PER_WAITER = 5
EFFICIENCY_WEIGHT = 1.0      # Base weight for efficiency score
WORKLOAD_PENALTY = 3.0       # Penalty for current table load
TIP_PENALTY = 2.0            # Penalty for already having high tips
TOP_N = 3                    # Number of options to return

# Size brackets for unknown party size routing
SIZE_BRACKETS = [
    {"label": "Small (2)", "min": 2, "max": 2},
    {"label": "Medium (3-4)", "min": 3, "max": 4},
    {"label": "Large (5-8)", "min": 5, "max": 8},
]


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


def filter_tables_by_capacity_range(tables: list, min_cap: int, max_cap: int) -> list:
    """Filter tables that are clean and within capacity range."""
    return [t for t in tables if t["state"] == "clean" and min_cap <= t["capacity"] <= max_cap]


def filter_tables_by_preference(tables: list, preference: str) -> list:
    """Filter tables by type preference."""
    if not preference or preference == "none":
        return tables
    return [t for t in tables if t["type"] == preference]


# =============================================================================
# WAITER FILTERING & SCORING
# =============================================================================

def is_waiter_available(waiter: dict) -> bool:
    """Check if waiter can take more tables."""
    if waiter["status"] in ("on_break", "busy"):
        return False
    if waiter["live_tables"] >= MAX_TABLES_PER_WAITER:
        return False
    return True


def get_available_waiters_for_section(waiters: list, section: str) -> list:
    """Get available waiters in a specific section."""
    return [
        w for w in waiters
        if is_waiter_available(w) and w["section"] == section
    ]


def calculate_waiter_priority(waiter: dict, total_tips: float) -> float:
    """
    Calculate waiter priority score for assignment.
    Higher score = higher priority for next table.
    """
    efficiency = waiter["score"] * EFFICIENCY_WEIGHT
    workload = (waiter["live_tables"] / MAX_TABLES_PER_WAITER) * WORKLOAD_PENALTY

    if total_tips > 0:
        tip_share = (waiter["current_tip_total"] / total_tips) * TIP_PENALTY
    else:
        tip_share = 0

    return efficiency - workload - tip_share


# =============================================================================
# PAIR GENERATION & SCORING
# =============================================================================

def generate_pairs(tables: list, waiters: list) -> list:
    """
    Generate all valid (waiter, table) pairs.
    Each pair includes the waiter, table, and waiter's section must match table's section.
    """
    pairs = []

    for table in tables:
        section = table["section"]
        available_waiters = get_available_waiters_for_section(waiters, section)

        for waiter in available_waiters:
            pairs.append({
                "waiter": waiter,
                "table": table
            })

    return pairs


def score_pairs(pairs: list, all_waiters: list) -> list:
    """
    Score all pairs by waiter priority.
    Tiebreaker: prefer smaller tables (don't waste capacity).
    """
    if not pairs:
        return []

    # Calculate total tips across ALL waiters (not just available ones)
    total_tips = sum(w["current_tip_total"] for w in all_waiters)

    scored = []
    for pair in pairs:
        waiter = pair["waiter"]
        table = pair["table"]
        priority = calculate_waiter_priority(waiter, total_tips)

        scored.append({
            "waiter": waiter,
            "table": table,
            "priority": priority,
            # For sorting: higher priority first, then smaller capacity
            "sort_key": (-priority, table["capacity"])
        })

    # Sort by priority desc, then capacity asc
    scored.sort(key=lambda x: x["sort_key"])

    return scored


def get_top_n_options(tables: list, waiters: list, party_size: int, preference: str, n: int = 3) -> dict:
    """
    Get top N routing options with backtracking.

    Strategy:
    1. Generate pairs from preference-matching tables
    2. If < N pairs, backtrack to non-preference tables for remaining slots
    3. Return top N scored pairs
    """
    result = {
        "options": [],
        "tables_clean_capacity": [],
        "tables_with_preference": [],
        "preference_pairs_count": 0,
        "backtrack_pairs_count": 0,
        "has_preference": bool(preference and preference != "none")
    }

    # Step 1: Get all clean tables with sufficient capacity
    result["tables_clean_capacity"] = filter_tables_by_clean_and_capacity(tables, party_size)

    if not result["tables_clean_capacity"]:
        return result

    # Step 2: Filter by preference (if any)
    if result["has_preference"]:
        result["tables_with_preference"] = filter_tables_by_preference(
            result["tables_clean_capacity"], preference
        )
    else:
        result["tables_with_preference"] = result["tables_clean_capacity"]

    # Step 3: Generate and score preference pairs
    preference_pairs = generate_pairs(result["tables_with_preference"], waiters)
    scored_preference = score_pairs(preference_pairs, waiters)
    result["preference_pairs_count"] = len(scored_preference)

    # Mark as using preference
    for pair in scored_preference:
        pair["used_preference"] = result["has_preference"]

    # Step 4: If we need more options, backtrack
    backtrack_pairs = []
    if len(scored_preference) < n and result["has_preference"]:
        # Get tables that are NOT in preference set
        preference_table_ids = {t["table_id"] for t in result["tables_with_preference"]}
        backtrack_tables = [
            t for t in result["tables_clean_capacity"]
            if t["table_id"] not in preference_table_ids
        ]

        if backtrack_tables:
            backtrack_pairs_raw = generate_pairs(backtrack_tables, waiters)
            backtrack_pairs = score_pairs(backtrack_pairs_raw, waiters)
            result["backtrack_pairs_count"] = len(backtrack_pairs)

            # Mark as backtracked
            for pair in backtrack_pairs:
                pair["used_preference"] = False

    # Step 5: Combine and take top N
    all_scored = scored_preference + backtrack_pairs

    # Re-sort combined list
    all_scored.sort(key=lambda x: x["sort_key"])

    # Take top N
    result["options"] = all_scored[:n]

    # Add rank to each option
    for i, option in enumerate(result["options"]):
        option["rank"] = i + 1
        # Remove sort_key from output
        del option["sort_key"]

    return result


def get_top_option_for_size_bracket(tables: list, waiters: list, min_cap: int, max_cap: int, preference: str) -> dict:
    """
    Get top 1 routing option for a specific capacity range.
    Used when party_size is unknown.
    """
    result = {
        "option": None,
        "tables_in_range": [],
        "has_preference": bool(preference and preference != "none")
    }

    # Filter tables by capacity range
    result["tables_in_range"] = filter_tables_by_capacity_range(tables, min_cap, max_cap)

    if not result["tables_in_range"]:
        return result

    # Apply preference filter if specified
    if result["has_preference"]:
        pref_tables = filter_tables_by_preference(result["tables_in_range"], preference)
        if pref_tables:
            candidate_tables = pref_tables
            used_pref = True
        else:
            # Backtrack to all tables in range
            candidate_tables = result["tables_in_range"]
            used_pref = False
    else:
        candidate_tables = result["tables_in_range"]
        used_pref = False

    # Generate and score pairs
    pairs = generate_pairs(candidate_tables, waiters)
    scored = score_pairs(pairs, waiters)

    if scored:
        best = scored[0]
        del best["sort_key"]
        best["used_preference"] = used_pref
        result["option"] = best

    return result


def get_options_for_unknown_size(tables: list, waiters: list, preference: str) -> dict:
    """
    When party_size is unknown, return top 1 option for each size bracket.
    """
    result = {
        "mode": "unknown_party_size",
        "options": [],
        "brackets": SIZE_BRACKETS
    }

    for bracket in SIZE_BRACKETS:
        bracket_result = get_top_option_for_size_bracket(
            tables, waiters,
            bracket["min"], bracket["max"],
            preference
        )

        if bracket_result["option"]:
            option = bracket_result["option"]
            option["size_bracket"] = bracket["label"]
            option["capacity_range"] = f"{bracket['min']}-{bracket['max']}"
            result["options"].append(option)

    # Add rank
    for i, option in enumerate(result["options"]):
        option["rank"] = i + 1

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
    """Main routing function. Returns top 3 options, commits #1."""
    # Load all data
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    ui_input = load_json("ui_input.json")

    # Extract request details
    request = ui_input["request"]
    party_size = request.get("party_size")  # Can be None or 0
    preference = request.get("table_preference", "none")
    is_reserved = request.get("is_reserved", False)
    group_id = request["group_id"]

    # Check if party_size is unknown
    unknown_size = party_size is None or party_size == 0

    print("=" * 60)
    print("RESTAURANT TABLE & WAITER ROUTER")
    print("=" * 60)
    if unknown_size:
        print(f"\nRequest: UNKNOWN party size, preference: {preference}, reserved: {is_reserved}")
        print("  -> Will return best option for each size bracket")
    else:
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

    # Branch based on whether party_size is known
    if unknown_size:
        # Unknown party size: return top 1 for each size bracket
        result = get_options_for_unknown_size(tables, waiters, preference)

        print("Routing Mode: UNKNOWN PARTY SIZE")
        print("-" * 50)
        print(f"  Size brackets: {[b['label'] for b in SIZE_BRACKETS]}")
        print()

        # Output results
        print("=" * 60)
        if result["options"]:
            print(f"TOP OPTIONS BY SIZE BRACKET ({len(result['options'])} found)")
            print("=" * 60)

            for option in result["options"]:
                table = option["table"]
                waiter = option["waiter"]
                rank = option["rank"]
                bracket = option["size_bracket"]
                pref_tag = "" if option.get("used_preference") else " [NO PREF MATCH]"

                print()
                print(f"  OPTION #{rank}: {bracket}{pref_tag}")
                print(f"  {'-' * 40}")
                print(f"    Table:    {table['table_id']} ({table['type']}, cap: {table['capacity']}, section: {table['section']})")
                print(f"    Waiter:   {waiter['id']} {waiter['name']} (score: {waiter['score']}, tables: {waiter['live_tables']})")
                print(f"    Priority: {option['priority']:.2f}")

            print()
            print("=" * 60)
            print("NO AUTO-COMMIT (party size unknown)")
            print("=" * 60)
            print("  Host must confirm party size to commit a routing.")
        else:
            print("RESULT: ROUTING FAILED")
            print("=" * 60)
            print("  Could not find options for any size bracket.")

    else:
        # Known party size: return top 3 options
        result = get_top_n_options(tables, waiters, party_size, preference, TOP_N)

        # Show routing details
        print("Routing Details:")
        print("-" * 50)
        clean_cap_ids = [t["table_id"] for t in result["tables_clean_capacity"]]
        print(f"  Clean + capacity >= {party_size}: {clean_cap_ids}")

        if result["has_preference"]:
            pref_ids = [t["table_id"] for t in result["tables_with_preference"]]
            print(f"  With preference '{preference}': {pref_ids}")
            print(f"  Preference pairs found: {result['preference_pairs_count']}")
            if result["backtrack_pairs_count"] > 0:
                print(f"  Backtrack pairs added: {result['backtrack_pairs_count']}")
        print()

        # Output results
        print("=" * 60)
        if result["options"]:
            print(f"TOP {len(result['options'])} ROUTING OPTIONS")
            print("=" * 60)

            for option in result["options"]:
                table = option["table"]
                waiter = option["waiter"]
                rank = option["rank"]
                pref_tag = "" if option["used_preference"] else " [BACKTRACK]"

                print()
                print(f"  OPTION #{rank}{pref_tag}")
                print(f"  {'-' * 40}")
                print(f"    Table:    {table['table_id']} ({table['type']}, cap: {table['capacity']}, section: {table['section']})")
                print(f"    Waiter:   {waiter['id']} {waiter['name']} (score: {waiter['score']}, tables: {waiter['live_tables']})")
                print(f"    Priority: {option['priority']:.2f}")

            # Commit option #1
            best = result["options"][0]
            best_table = best["table"]
            best_waiter = best["waiter"]

            print()
            print("=" * 60)
            print("COMMITTING OPTION #1")
            print("=" * 60)
            print(f"  Table:  {best_table['table_id']} -> occupied")
            print(f"  Waiter: {best_waiter['name']} tables: {best_waiter['live_tables']} -> {best_waiter['live_tables'] + 1}")

            # Update and save restaurant state
            updated_state = update_restaurant_state(
                restaurant_state, ml_input,
                best_table["table_id"], best_waiter["id"], group_id
            )
            save_json("restaurant_state.json", updated_state)
            print()
            print(">> State updated: restaurant_state.json saved")
        else:
            print("RESULT: ROUTING FAILED")
            print("=" * 60)
            print("  Could not find any valid table + waiter combination.")
            if not result["tables_clean_capacity"]:
                print("  Reason: No clean tables with sufficient capacity.")
            else:
                print("  Reason: No available waiters for valid tables.")

    print()
    return result


if __name__ == "__main__":
    route_party()
