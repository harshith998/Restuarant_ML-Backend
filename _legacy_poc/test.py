"""
Test suite for the restaurant table router.
Tests all major use cases.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Import router functions
from table_router import (
    load_json, save_json, merge_ml_state,
    filter_tables_by_clean_and_capacity,
    filter_tables_by_capacity_range,
    filter_tables_by_preference,
    is_waiter_available,
    get_available_waiters_for_section,
    calculate_waiter_priority,
    generate_pairs,
    score_pairs,
    get_top_n_options,
    get_top_option_for_size_bracket,
    get_options_for_unknown_size,
    update_restaurant_state,
    MAX_TABLES_PER_WAITER
)

from reset import ORIGINAL_RESTAURANT_STATE, ORIGINAL_ML_INPUT, ORIGINAL_UI_INPUT


def reset_state():
    """Reset all JSON files to original state."""
    save_json("restaurant_state.json", ORIGINAL_RESTAURANT_STATE)
    save_json("ml_input.json", ORIGINAL_ML_INPUT)
    save_json("ui_input.json", ORIGINAL_UI_INPUT)


def print_test_header(name):
    print()
    print("=" * 70)
    print(f"TEST: {name}")
    print("=" * 70)


def print_result(passed, message=""):
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status} {message}")
    return passed


# =============================================================================
# TEST CASES
# =============================================================================

def test_table_filtering():
    """Test table filtering by clean state, capacity, and preference."""
    print_test_header("Table Filtering")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)

    passed = True

    # Test 1: Filter clean tables with capacity >= 4
    clean_cap_4 = filter_tables_by_clean_and_capacity(tables, 4)
    clean_ids = [t["table_id"] for t in clean_cap_4]
    # Expected: A3(6), B2(6), B3(8), C2(4), D2(5) - clean tables with cap >= 4
    expected = ["A3", "B2", "B3", "C2", "D2"]
    passed &= print_result(
        set(clean_ids) == set(expected),
        f"Clean + cap >= 4: got {clean_ids}, expected {expected}"
    )

    # Test 2: Filter by preference (booth)
    booths = filter_tables_by_preference(clean_cap_4, "booth")
    booth_ids = [t["table_id"] for t in booths]
    expected_booths = ["B2", "C2", "D2"]
    passed &= print_result(
        set(booth_ids) == set(expected_booths),
        f"Booth preference: got {booth_ids}, expected {expected_booths}"
    )

    # Test 3: Filter by preference "none" returns all
    no_pref = filter_tables_by_preference(clean_cap_4, "none")
    passed &= print_result(
        len(no_pref) == len(clean_cap_4),
        f"No preference returns all: {len(no_pref)} == {len(clean_cap_4)}"
    )

    # Test 4: Capacity range filter
    range_tables = filter_tables_by_capacity_range(tables, 3, 4)
    range_ids = [t["table_id"] for t in range_tables]
    # Tables with cap 3-4 that are clean: C2(4), D3(3-occupied), A1(2-no), etc
    # Clean ones: C2(4) only in that range based on ML
    passed &= print_result(
        "C2" in range_ids,
        f"Capacity range 3-4: got {range_ids}"
    )

    return passed


def test_waiter_availability():
    """Test waiter availability checks."""
    print_test_header("Waiter Availability")

    passed = True

    # Test available waiter
    available_waiter = {
        "id": "W1", "status": "available", "live_tables": 2
    }
    passed &= print_result(
        is_waiter_available(available_waiter) == True,
        "Available waiter with 2 tables is available"
    )

    # Test on_break waiter
    on_break_waiter = {
        "id": "W2", "status": "on_break", "live_tables": 0
    }
    passed &= print_result(
        is_waiter_available(on_break_waiter) == False,
        "On-break waiter is NOT available"
    )

    # Test busy waiter
    busy_waiter = {
        "id": "W3", "status": "busy", "live_tables": 1
    }
    passed &= print_result(
        is_waiter_available(busy_waiter) == False,
        "Busy waiter is NOT available"
    )

    # Test waiter at max capacity
    maxed_waiter = {
        "id": "W4", "status": "available", "live_tables": MAX_TABLES_PER_WAITER
    }
    passed &= print_result(
        is_waiter_available(maxed_waiter) == False,
        f"Waiter at max ({MAX_TABLES_PER_WAITER}) tables is NOT available"
    )

    # Test heading_to_table waiter (should be available)
    heading_waiter = {
        "id": "W5", "status": "heading_to_table", "live_tables": 2
    }
    passed &= print_result(
        is_waiter_available(heading_waiter) == True,
        "Heading-to-table waiter is available"
    )

    return passed


def test_waiter_priority_scoring():
    """Test waiter priority calculation."""
    print_test_header("Waiter Priority Scoring")

    passed = True

    # Waiter with high score, no tables, no tips
    waiter1 = {"score": 9.0, "live_tables": 0, "current_tip_total": 0}
    priority1 = calculate_waiter_priority(waiter1, total_tips=0)
    passed &= print_result(
        priority1 == 9.0,
        f"High score, 0 tables, 0 tips: priority = {priority1} (expected 9.0)"
    )

    # Waiter with same score but more tables
    waiter2 = {"score": 9.0, "live_tables": 2, "current_tip_total": 0}
    priority2 = calculate_waiter_priority(waiter2, total_tips=0)
    passed &= print_result(
        priority2 < priority1,
        f"Same score, 2 tables: priority = {priority2:.2f} < {priority1}"
    )

    # Waiter with tips (50% of total)
    waiter3 = {"score": 9.0, "live_tables": 0, "current_tip_total": 50}
    priority3 = calculate_waiter_priority(waiter3, total_tips=100)
    passed &= print_result(
        priority3 < priority1,
        f"Same score, 50% tips: priority = {priority3:.2f} < {priority1}"
    )

    # Lower score waiter beats high score waiter with load
    waiter_low = {"score": 7.0, "live_tables": 0, "current_tip_total": 0}
    waiter_high_loaded = {"score": 9.0, "live_tables": 3, "current_tip_total": 50}
    priority_low = calculate_waiter_priority(waiter_low, total_tips=100)
    priority_high_loaded = calculate_waiter_priority(waiter_high_loaded, total_tips=100)
    passed &= print_result(
        priority_low > priority_high_loaded,
        f"Unloaded low-score ({priority_low:.2f}) > loaded high-score ({priority_high_loaded:.2f})"
    )

    return passed


def test_pair_generation():
    """Test waiter-table pair generation."""
    print_test_header("Pair Generation")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    # Get clean tables with capacity >= 4
    clean_tables = filter_tables_by_clean_and_capacity(tables, 4)

    # Generate pairs
    pairs = generate_pairs(clean_tables, waiters)

    passed &= print_result(
        len(pairs) > 0,
        f"Generated {len(pairs)} pairs"
    )

    # Each pair should have waiter section matching table section
    section_match = all(
        p["waiter"]["section"] == p["table"]["section"]
        for p in pairs
    )
    passed &= print_result(
        section_match,
        "All pairs have matching waiter/table sections"
    )

    return passed


def test_top_3_routing_with_preference():
    """Test top 3 routing with preference."""
    print_test_header("Top 3 Routing with Preference (booth)")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    result = get_top_n_options(tables, waiters, party_size=4, preference="booth", n=3)

    passed &= print_result(
        len(result["options"]) == 3,
        f"Got {len(result['options'])} options (expected 3)"
    )

    # Check that options are ranked
    ranks = [o["rank"] for o in result["options"]]
    passed &= print_result(
        ranks == [1, 2, 3],
        f"Options ranked correctly: {ranks}"
    )

    # Check priorities are descending
    priorities = [o["priority"] for o in result["options"]]
    passed &= print_result(
        priorities == sorted(priorities, reverse=True),
        f"Priorities descending: {[f'{p:.2f}' for p in priorities]}"
    )

    # Print options for visibility
    for opt in result["options"]:
        pref = "PREF" if opt["used_preference"] else "BACKTRACK"
        print(f"    #{opt['rank']}: {opt['table']['table_id']} + {opt['waiter']['name']} ({pref})")

    return passed


def test_top_3_routing_with_backtrack():
    """Test backtracking when preference has fewer options."""
    print_test_header("Top 3 Routing with Backtrack (window preference)")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    # Window tables with cap >= 4: only A1(2-no), B1(4-dirty), C1(3-occupied)
    # So no clean window tables with cap >= 4 -> should backtrack
    result = get_top_n_options(tables, waiters, party_size=4, preference="window", n=3)

    passed &= print_result(
        len(result["options"]) > 0,
        f"Got {len(result['options'])} options despite no matching preference"
    )

    # All should be backtracked
    all_backtracked = all(not o["used_preference"] for o in result["options"])
    passed &= print_result(
        all_backtracked,
        "All options are backtracked (no preference match)"
    )

    for opt in result["options"]:
        pref = "PREF" if opt["used_preference"] else "BACKTRACK"
        print(f"    #{opt['rank']}: {opt['table']['table_id']} + {opt['waiter']['name']} ({pref})")

    return passed


def test_unknown_party_size():
    """Test routing with unknown party size."""
    print_test_header("Unknown Party Size Routing")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    result = get_options_for_unknown_size(tables, waiters, preference="booth")

    passed &= print_result(
        result["mode"] == "unknown_party_size",
        "Mode is 'unknown_party_size'"
    )

    passed &= print_result(
        len(result["options"]) > 0,
        f"Got {len(result['options'])} size bracket options"
    )

    # Each option should have size_bracket label
    has_brackets = all("size_bracket" in o for o in result["options"])
    passed &= print_result(
        has_brackets,
        "All options have size_bracket label"
    )

    for opt in result["options"]:
        pref = "PREF" if opt.get("used_preference") else "NO PREF"
        print(f"    #{opt['rank']}: {opt['size_bracket']} -> {opt['table']['table_id']} + {opt['waiter']['name']} ({pref})")

    return passed


def test_state_update():
    """Test that state updates correctly after routing."""
    print_test_header("State Update After Routing")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")

    passed = True

    # Get initial state
    initial_table = next(t for t in restaurant_state["tables"] if t["table_id"] == "C2")
    initial_waiter = next(w for w in restaurant_state["waiters"] if w["id"] == "W5")

    passed &= print_result(
        initial_table["state"] == "clean",
        f"Initial table C2 state: {initial_table['state']}"
    )
    passed &= print_result(
        initial_waiter["live_tables"] == 0,
        f"Initial waiter W5 tables: {initial_waiter['live_tables']}"
    )

    # Update state
    updated = update_restaurant_state(
        restaurant_state, ml_input,
        routed_table_id="C2",
        routed_waiter_id="W5",
        group_id="TEST_GROUP"
    )

    # Check updates
    updated_table = next(t for t in updated["tables"] if t["table_id"] == "C2")
    updated_waiter = next(w for w in updated["waiters"] if w["id"] == "W5")

    passed &= print_result(
        updated_table["state"] == "occupied",
        f"Updated table C2 state: {updated_table['state']}"
    )
    passed &= print_result(
        updated_table["current_group_id"] == "TEST_GROUP",
        f"Updated table C2 group_id: {updated_table['current_group_id']}"
    )
    passed &= print_result(
        updated_waiter["live_tables"] == 1,
        f"Updated waiter W5 tables: {updated_waiter['live_tables']}"
    )
    passed &= print_result(
        updated_waiter["status"] == "heading_to_table",
        f"Updated waiter W5 status: {updated_waiter['status']}"
    )

    return passed


def test_ml_state_merge():
    """Test that ML states override restaurant state."""
    print_test_header("ML State Merge")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")

    passed = True

    # Before merge, all tables are "clean" in restaurant_state
    before = restaurant_state["tables"][0]["state"]
    passed &= print_result(
        before == "clean",
        f"Before merge, A1 state: {before}"
    )

    # After merge, states come from ML
    tables = merge_ml_state(restaurant_state["tables"], ml_input)

    # A2 should be occupied per ML
    a2 = next(t for t in tables if t["table_id"] == "A2")
    passed &= print_result(
        a2["state"] == "occupied",
        f"After merge, A2 state: {a2['state']} (from ML)"
    )

    # B1 should be dirty per ML
    b1 = next(t for t in tables if t["table_id"] == "B1")
    passed &= print_result(
        b1["state"] == "dirty",
        f"After merge, B1 state: {b1['state']} (from ML)"
    )

    return passed


def test_no_preference():
    """Test routing with no preference."""
    print_test_header("Routing with No Preference")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    result = get_top_n_options(tables, waiters, party_size=4, preference="none", n=3)

    passed &= print_result(
        len(result["options"]) == 3,
        f"Got {len(result['options'])} options with no preference"
    )

    # With no preference, used_preference should be False but not "backtracked"
    # (since there was no preference to backtrack from)
    for opt in result["options"]:
        print(f"    #{opt['rank']}: {opt['table']['table_id']} ({opt['table']['type']}) + {opt['waiter']['name']}")

    return passed


def test_routing_failure():
    """Test routing when no tables available."""
    print_test_header("Routing Failure - No Tables")

    reset_state()
    restaurant_state = load_json("restaurant_state.json")
    ml_input = load_json("ml_input.json")
    tables = merge_ml_state(restaurant_state["tables"], ml_input)
    waiters = restaurant_state["waiters"]

    passed = True

    # Party of 10 - no tables have capacity >= 10
    result = get_top_n_options(tables, waiters, party_size=10, preference="none", n=3)

    passed &= print_result(
        len(result["options"]) == 0,
        f"No options for party of 10 (max table is 8)"
    )

    passed &= print_result(
        len(result["tables_clean_capacity"]) == 0,
        "No tables with sufficient capacity"
    )

    return passed


# =============================================================================
# RUN ALL TESTS
# =============================================================================

def run_all_tests():
    print()
    print("#" * 70)
    print("#  RESTAURANT ROUTER TEST SUITE")
    print("#" * 70)

    tests = [
        ("Table Filtering", test_table_filtering),
        ("Waiter Availability", test_waiter_availability),
        ("Waiter Priority Scoring", test_waiter_priority_scoring),
        ("Pair Generation", test_pair_generation),
        ("ML State Merge", test_ml_state_merge),
        ("Top 3 with Preference", test_top_3_routing_with_preference),
        ("Top 3 with Backtrack", test_top_3_routing_with_backtrack),
        ("No Preference", test_no_preference),
        ("Unknown Party Size", test_unknown_party_size),
        ("State Update", test_state_update),
        ("Routing Failure", test_routing_failure),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n  ✗ EXCEPTION: {e}")
            results.append((name, False))

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    for name, passed in results:
        status = "✓" if passed else "✗"
        print(f"  {status} {name}")

    print()
    print(f"  Total: {passed_count}/{total_count} tests passed")
    print()

    # Reset state after tests
    reset_state()
    print("  (State reset to original)")

    return passed_count == total_count


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
