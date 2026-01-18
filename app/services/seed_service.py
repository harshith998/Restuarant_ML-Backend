"""Service for seeding default data to handle cold start scenarios."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, time
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restaurant import Restaurant
from app.models.section import Section
from app.models.table import Table
from app.models.waiter import Waiter
from app.models.shift import Shift
from app.models.visit import Visit
from app.models.menu import MenuItem, OrderItem
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.models.kitchen_station import KitchenStation
from app.models.scheduling import StaffAvailability, StaffPreference, StaffingRequirements

logger = logging.getLogger(__name__)


# Default restaurant config
DEFAULT_RESTAURANT_CONFIG = {
    "routing": {
        "mode": "section",
        "max_tables_per_waiter": 5,
        "efficiency_weight": 1.0,
        "workload_penalty": 3.0,
        "tip_penalty": 2.0,
        "recency_penalty_minutes": 5,
        "recency_penalty_weight": 1.5,
    },
    "alerts": {
        "understaffed_threshold": 1.2,
        "overstaffed_threshold": 0.5,
    },
}

# Default waiter profiles for cold start
DEFAULT_WAITERS = [
    {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "tier": "strong",
        "composite_score": 78.5,
        "total_shifts": 45,
        "total_covers": 892,
        "total_tips": 4250.75,
        "total_tables_served": 312,
        "total_sales": 28450.00,
    },
    {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "tier": "standard",
        "composite_score": 55.0,
        "total_shifts": 38,
        "total_covers": 654,
        "total_tips": 2890.50,
        "total_tables_served": 245,
        "total_sales": 19250.00,
    },
    {
        "name": "Carol Williams",
        "email": "carol@example.com",
        "tier": "standard",
        "composite_score": 52.0,
        "total_shifts": 32,
        "total_covers": 520,
        "total_tips": 2150.25,
        "total_tables_served": 198,
        "total_sales": 15600.00,
    },
    {
        "name": "Dave Brown",
        "email": "dave@example.com",
        "tier": "developing",
        "composite_score": 35.0,
        "total_shifts": 18,
        "total_covers": 285,
        "total_tips": 980.00,
        "total_tables_served": 95,
        "total_sales": 7850.00,
    },
]

# Default sections
DEFAULT_SECTIONS = [
    {"name": "Main Floor", "is_active": True},
    {"name": "Patio", "is_active": True},
    {"name": "Bar", "is_active": True},
]

# Default tables per section
DEFAULT_TABLES = {
    "Main Floor": [
        {"table_number": "T1", "capacity": 4, "table_type": "table"},
        {"table_number": "T2", "capacity": 4, "table_type": "table"},
        {"table_number": "T3", "capacity": 6, "table_type": "table"},
        {"table_number": "T4", "capacity": 2, "table_type": "table"},
        {"table_number": "B1", "capacity": 4, "table_type": "booth"},
        {"table_number": "B2", "capacity": 6, "table_type": "booth"},
    ],
    "Patio": [
        {"table_number": "P1", "capacity": 4, "table_type": "table"},
        {"table_number": "P2", "capacity": 4, "table_type": "table"},
        {"table_number": "P3", "capacity": 2, "table_type": "table"},
    ],
    "Bar": [
        {"table_number": "BAR1", "capacity": 2, "table_type": "bar"},
        {"table_number": "BAR2", "capacity": 2, "table_type": "bar"},
        {"table_number": "BAR3", "capacity": 4, "table_type": "bar"},
    ],
}


# ============================================================
# MIMOSAS RESTAURANT CONFIGURATION
# ============================================================

MIMOSAS_RESTAURANT_CONFIG = {
    "routing": {
        "mode": "section",
        "max_tables_per_waiter": 4,
        "efficiency_weight": 1.0,
        "workload_penalty": 3.0,
        "tip_penalty": 2.0,
        "recency_penalty_minutes": 5,
        "recency_penalty_weight": 1.5,
    },
    "alerts": {
        "understaffed_threshold": 1.2,
        "overstaffed_threshold": 0.5,
    },
}

MIMOSAS_SECTIONS = [
    {"name": "Main Dining", "is_active": True},
    {"name": "Outdoor Patio", "is_active": True},
    {"name": "Bar", "is_active": True},
]

MIMOSAS_TABLES = {
    "Main Dining": [
        {"table_number": "M1", "capacity": 4, "table_type": "table"},
        {"table_number": "M2", "capacity": 4, "table_type": "table"},
        {"table_number": "M3", "capacity": 6, "table_type": "table"},
        {"table_number": "M4", "capacity": 2, "table_type": "table"},
        {"table_number": "M5", "capacity": 8, "table_type": "table"},
    ],
    "Outdoor Patio": [
        {"table_number": "O1", "capacity": 4, "table_type": "table"},
        {"table_number": "O2", "capacity": 4, "table_type": "table"},
        {"table_number": "O3", "capacity": 6, "table_type": "table"},
    ],
    "Bar": [
        {"table_number": "B1", "capacity": 2, "table_type": "bar"},
        {"table_number": "B2", "capacity": 2, "table_type": "bar"},
        {"table_number": "B3", "capacity": 4, "table_type": "high_top"},
    ],
}

# ============================================================
# MIMOSAS FULL STAFF (50 employees)
# ============================================================

MIMOSAS_WAITERS = [
    # ==================== SERVERS (13) ====================
    # Strong Tier (4)
    {
        "name": "Maria Garcia",
        "email": "maria@mimosas.com",
        "phone": "555-0101",
        "role": "server",
        "tier": "strong",
        "composite_score": 82.0,
        "total_shifts": 180,
        "total_covers": 3650,
        "total_tips": 18500.00,
        "total_tables_served": 1320,
        "total_sales": 125000.00,
    },
    {
        "name": "Daniel Martinez",
        "email": "daniel@mimosas.com",
        "phone": "555-0102",
        "role": "server",
        "tier": "strong",
        "composite_score": 79.0,
        "total_shifts": 165,
        "total_covers": 3200,
        "total_tips": 16200.00,
        "total_tables_served": 1180,
        "total_sales": 112000.00,
    },
    {
        "name": "Jessica Thompson",
        "email": "jessica@mimosas.com",
        "phone": "555-0103",
        "role": "server",
        "tier": "strong",
        "composite_score": 77.0,
        "total_shifts": 150,
        "total_covers": 2900,
        "total_tips": 14800.00,
        "total_tables_served": 1050,
        "total_sales": 98000.00,
    },
    {
        "name": "Kevin O'Brien",
        "email": "kevin@mimosas.com",
        "phone": "555-0104",
        "role": "server",
        "tier": "strong",
        "composite_score": 75.0,
        "total_shifts": 140,
        "total_covers": 2700,
        "total_tips": 13500.00,
        "total_tables_served": 980,
        "total_sales": 92000.00,
    },
    # Standard Tier (7)
    {
        "name": "James Wilson",
        "email": "james@mimosas.com",
        "phone": "555-0105",
        "role": "server",
        "tier": "standard",
        "composite_score": 62.0,
        "total_shifts": 120,
        "total_covers": 2200,
        "total_tips": 10200.00,
        "total_tables_served": 800,
        "total_sales": 75000.00,
    },
    {
        "name": "Emily Chen",
        "email": "emily@mimosas.com",
        "phone": "555-0106",
        "role": "server",
        "tier": "standard",
        "composite_score": 58.0,
        "total_shifts": 110,
        "total_covers": 1900,
        "total_tips": 8800.00,
        "total_tables_served": 690,
        "total_sales": 65000.00,
    },
    {
        "name": "Aisha Johnson",
        "email": "aisha@mimosas.com",
        "phone": "555-0107",
        "role": "server",
        "tier": "standard",
        "composite_score": 56.0,
        "total_shifts": 105,
        "total_covers": 1800,
        "total_tips": 8200.00,
        "total_tables_served": 650,
        "total_sales": 61000.00,
    },
    {
        "name": "Tyler Brooks",
        "email": "tyler@mimosas.com",
        "phone": "555-0108",
        "role": "server",
        "tier": "standard",
        "composite_score": 54.0,
        "total_shifts": 100,
        "total_covers": 1700,
        "total_tips": 7800.00,
        "total_tables_served": 620,
        "total_sales": 58000.00,
    },
    {
        "name": "Nina Patel",
        "email": "nina@mimosas.com",
        "phone": "555-0109",
        "role": "server",
        "tier": "standard",
        "composite_score": 52.0,
        "total_shifts": 85,
        "total_covers": 1400,
        "total_tips": 6500.00,
        "total_tables_served": 510,
        "total_sales": 48000.00,
    },
    {
        "name": "Marcus Lee",
        "email": "marcus@mimosas.com",
        "phone": "555-0110",
        "role": "server",
        "tier": "standard",
        "composite_score": 51.0,
        "total_shifts": 95,
        "total_covers": 1600,
        "total_tips": 7200.00,
        "total_tables_served": 580,
        "total_sales": 54000.00,
    },
    {
        "name": "Hannah White",
        "email": "hannah@mimosas.com",
        "phone": "555-0111",
        "role": "server",
        "tier": "standard",
        "composite_score": 50.0,
        "total_shifts": 75,
        "total_covers": 1200,
        "total_tips": 5500.00,
        "total_tables_served": 440,
        "total_sales": 42000.00,
    },
    {
        "name": "Derek Johnson",
        "email": "derek@mimosas.com",
        "phone": "555-0112",
        "role": "server",
        "tier": "standard",
        "composite_score": 48.0,
        "total_shifts": 70,
        "total_covers": 1100,
        "total_tips": 5000.00,
        "total_tables_served": 400,
        "total_sales": 38000.00,
    },
    # Developing Tier (1)
    {
        "name": "Ashley Rivera",
        "email": "ashley@mimosas.com",
        "phone": "555-0113",
        "role": "server",
        "tier": "developing",
        "composite_score": 42.0,
        "total_shifts": 45,
        "total_covers": 720,
        "total_tips": 3200.00,
        "total_tables_served": 260,
        "total_sales": 25000.00,
    },
    # ==================== BARTENDERS (4) ====================
    {
        "name": "Carlos Rodriguez",
        "email": "carlos@mimosas.com",
        "phone": "555-0201",
        "role": "bartender",
        "tier": "strong",
        "composite_score": 80.0,
        "total_shifts": 160,
        "total_covers": 1800,
        "total_tips": 14500.00,
        "total_tables_served": 680,
        "total_sales": 105000.00,
    },
    {
        "name": "Sophia Turner",
        "email": "sophia@mimosas.com",
        "phone": "555-0202",
        "role": "bartender",
        "tier": "strong",
        "composite_score": 76.0,
        "total_shifts": 145,
        "total_covers": 1600,
        "total_tips": 12800.00,
        "total_tables_served": 600,
        "total_sales": 92000.00,
    },
    {
        "name": "Jake Morrison",
        "email": "jake@mimosas.com",
        "phone": "555-0203",
        "role": "bartender",
        "tier": "standard",
        "composite_score": 55.0,
        "total_shifts": 100,
        "total_covers": 1100,
        "total_tips": 8200.00,
        "total_tables_served": 420,
        "total_sales": 62000.00,
    },
    {
        "name": "Mia Collins",
        "email": "mia@mimosas.com",
        "phone": "555-0204",
        "role": "bartender",
        "tier": "standard",
        "composite_score": 52.0,
        "total_shifts": 80,
        "total_covers": 880,
        "total_tips": 6500.00,
        "total_tables_served": 330,
        "total_sales": 48000.00,
    },
    # ==================== HOSTS (3) ====================
    {
        "name": "Sophie Kim",
        "email": "sophie@mimosas.com",
        "phone": "555-0301",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 140,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Ethan Park",
        "email": "ethan@mimosas.com",
        "phone": "555-0302",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 120,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Olivia Brown",
        "email": "olivia@mimosas.com",
        "phone": "555-0303",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 95,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== BUSSERS (2) ====================
    {
        "name": "Luis Hernandez",
        "email": "luis@mimosas.com",
        "phone": "555-0401",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 130,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Emma Clark",
        "email": "emma@mimosas.com",
        "phone": "555-0402",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 100,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== RUNNERS (1) ====================
    {
        "name": "Miguel Santos",
        "email": "miguel@mimosas.com",
        "phone": "555-0501",
        "role": "runner",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 125,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== ADDITIONAL SERVERS (10) ====================
    {
        "name": "Olivia Nguyen",
        "email": "olivia.nguyen@mimosas.com",
        "phone": "555-0117",
        "role": "server",
        "tier": "standard",
        "composite_score": 57.0,
        "total_shifts": 90,
        "total_covers": 1500,
        "total_tips": 6800.00,
        "total_tables_served": 520,
        "total_sales": 52000.00,
    },
    {
        "name": "Ethan Brooks",
        "email": "ethan.brooks@mimosas.com",
        "phone": "555-0118",
        "role": "server",
        "tier": "developing",
        "composite_score": 44.0,
        "total_shifts": 55,
        "total_covers": 820,
        "total_tips": 3600.00,
        "total_tables_served": 290,
        "total_sales": 30000.00,
    },
    {
        "name": "Sophia Patel",
        "email": "sophia.patel@mimosas.com",
        "phone": "555-0119",
        "role": "server",
        "tier": "standard",
        "composite_score": 59.0,
        "total_shifts": 100,
        "total_covers": 1650,
        "total_tips": 7200.00,
        "total_tables_served": 560,
        "total_sales": 56000.00,
    },
    {
        "name": "Lucas Reed",
        "email": "lucas.reed@mimosas.com",
        "phone": "555-0120",
        "role": "server",
        "tier": "standard",
        "composite_score": 53.0,
        "total_shifts": 78,
        "total_covers": 1200,
        "total_tips": 5200.00,
        "total_tables_served": 410,
        "total_sales": 42000.00,
    },
    {
        "name": "Ava Robinson",
        "email": "ava.robinson@mimosas.com",
        "phone": "555-0121",
        "role": "server",
        "tier": "standard",
        "composite_score": 56.0,
        "total_shifts": 92,
        "total_covers": 1480,
        "total_tips": 6900.00,
        "total_tables_served": 500,
        "total_sales": 51000.00,
    },
    {
        "name": "Noah Bennett",
        "email": "noah.bennett@mimosas.com",
        "phone": "555-0122",
        "role": "server",
        "tier": "standard",
        "composite_score": 55.0,
        "total_shifts": 85,
        "total_covers": 1350,
        "total_tips": 6000.00,
        "total_tables_served": 460,
        "total_sales": 46000.00,
    },
    {
        "name": "Isabella Cruz",
        "email": "isabella.cruz@mimosas.com",
        "phone": "555-0123",
        "role": "server",
        "tier": "strong",
        "composite_score": 70.0,
        "total_shifts": 125,
        "total_covers": 2200,
        "total_tips": 9800.00,
        "total_tables_served": 780,
        "total_sales": 82000.00,
    },
    {
        "name": "Mason Hughes",
        "email": "mason.hughes@mimosas.com",
        "phone": "555-0124",
        "role": "server",
        "tier": "standard",
        "composite_score": 52.0,
        "total_shifts": 70,
        "total_covers": 1100,
        "total_tips": 4900.00,
        "total_tables_served": 390,
        "total_sales": 39000.00,
    },
    {
        "name": "Chloe Park",
        "email": "chloe.park@mimosas.com",
        "phone": "555-0125",
        "role": "server",
        "tier": "developing",
        "composite_score": 43.0,
        "total_shifts": 48,
        "total_covers": 720,
        "total_tips": 3200.00,
        "total_tables_served": 250,
        "total_sales": 26000.00,
    },
    {
        "name": "Jackson Price",
        "email": "jackson.price@mimosas.com",
        "phone": "555-0126",
        "role": "server",
        "tier": "standard",
        "composite_score": 54.0,
        "total_shifts": 76,
        "total_covers": 1180,
        "total_tips": 5100.00,
        "total_tables_served": 400,
        "total_sales": 40500.00,
    },
    # ==================== ADDITIONAL BARTENDERS (4) ====================
    {
        "name": "Riley Morgan",
        "email": "riley.morgan@mimosas.com",
        "phone": "555-0205",
        "role": "bartender",
        "tier": "strong",
        "composite_score": 74.0,
        "total_shifts": 120,
        "total_covers": 1400,
        "total_tips": 9800.00,
        "total_tables_served": 520,
        "total_sales": 78000.00,
    },
    {
        "name": "Lena Ortiz",
        "email": "lena.ortiz@mimosas.com",
        "phone": "555-0206",
        "role": "bartender",
        "tier": "standard",
        "composite_score": 58.0,
        "total_shifts": 95,
        "total_covers": 980,
        "total_tips": 7400.00,
        "total_tables_served": 360,
        "total_sales": 56000.00,
    },
    {
        "name": "Owen Shaw",
        "email": "owen.shaw@mimosas.com",
        "phone": "555-0207",
        "role": "bartender",
        "tier": "standard",
        "composite_score": 56.0,
        "total_shifts": 88,
        "total_covers": 920,
        "total_tips": 6900.00,
        "total_tables_served": 330,
        "total_sales": 52000.00,
    },
    {
        "name": "Harper Cole",
        "email": "harper.cole@mimosas.com",
        "phone": "555-0208",
        "role": "bartender",
        "tier": "developing",
        "composite_score": 47.0,
        "total_shifts": 70,
        "total_covers": 760,
        "total_tips": 5200.00,
        "total_tables_served": 280,
        "total_sales": 42000.00,
    },
    # ==================== ADDITIONAL HOSTS (3) ====================
    {
        "name": "Layla Price",
        "email": "layla.price@mimosas.com",
        "phone": "555-0305",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 80,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Carter Young",
        "email": "carter.young@mimosas.com",
        "phone": "555-0306",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 75,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Stella James",
        "email": "stella.james@mimosas.com",
        "phone": "555-0307",
        "role": "host",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 68,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== ADDITIONAL BUSSERS (4) ====================
    {
        "name": "Adrian Flores",
        "email": "adrian.flores@mimosas.com",
        "phone": "555-0403",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 70,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Bella Ortiz",
        "email": "bella.ortiz@mimosas.com",
        "phone": "555-0404",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 66,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Nolan Kim",
        "email": "nolan.kim@mimosas.com",
        "phone": "555-0405",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 62,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Piper Scott",
        "email": "piper.scott@mimosas.com",
        "phone": "555-0406",
        "role": "busser",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 58,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== ADDITIONAL RUNNERS (3) ====================
    {
        "name": "Diego Reyes",
        "email": "diego.reyes@mimosas.com",
        "phone": "555-0502",
        "role": "runner",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 60,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Hazel Brooks",
        "email": "hazel.brooks@mimosas.com",
        "phone": "555-0503",
        "role": "runner",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 56,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Trent Lawson",
        "email": "trent.lawson@mimosas.com",
        "phone": "555-0504",
        "role": "runner",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 52,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    # ==================== CHEFS (3) ====================
    {
        "name": "Marco Alvarez",
        "email": "marco.alvarez@mimosas.com",
        "phone": "555-0601",
        "role": "chef",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 140,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Priya Nair",
        "email": "priya.nair@mimosas.com",
        "phone": "555-0602",
        "role": "chef",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 132,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
    {
        "name": "Elliot Zhang",
        "email": "elliot.zhang@mimosas.com",
        "phone": "555-0603",
        "role": "chef",
        "tier": None,
        "composite_score": 50.0,
        "total_shifts": 120,
        "total_covers": 0,
        "total_tips": 0,
        "total_tables_served": 0,
        "total_sales": 0,
    },
]

# ============================================================
# MIMOSAS STAFF AVAILABILITY PATTERNS
# Format: name -> list of {day, start, end, type}
# day: 0=Mon-6=Sun, type: "available", "preferred", "unavailable"
# ============================================================

MIMOSAS_STAFF_AVAILABILITY = {
    # ==================== SERVERS ====================
    # Strong tier - full time, flexible
    "Maria Garcia": {
        "days": [0, 1, 3, 4, 5, 6],  # Off Wed (day 2)
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],  # Prefers weekends
    },
    "Daniel Martinez": {
        "days": [0, 1, 2, 3, 4, 5],  # Off Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [0, 1, 2],  # Prefers weekday mornings
    },
    "Jessica Thompson": {
        "days": [0, 2, 3, 4, 5, 6],  # Off Tue
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],  # Weekends
    },
    "Kevin O'Brien": {
        "days": [1, 2, 3, 4, 5, 6],  # Off Mon
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [4, 5],  # Fri-Sat
    },
    # Standard tier - regular part-time
    "James Wilson": {
        "days": [0, 1, 2, 3, 4],  # Off weekends
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [1, 2, 3],
    },
    "Emily Chen": {
        "days": [0, 1, 2, 3, 5, 6],  # Off Thu
        "start": time(7, 0),
        "end": time(12, 0),  # Mornings only
        "preferred_days": [5, 6],
    },
    "Aisha Johnson": {
        "days": [0, 1, 3, 4, 5],  # Off Tue, Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [0, 1],
    },
    "Tyler Brooks": {
        "days": [1, 2, 3, 4, 5, 6],  # Off Mon
        "start": time(10, 0),
        "end": time(16, 0),  # Late starts
        "preferred_days": [5, 6],
    },
    "Nina Patel": {
        "days": [4, 5, 6],  # Weekends + Fri only
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Marcus Lee": {
        "days": [0, 1, 2, 3, 4],  # Weekdays only
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [1, 2, 3],
    },
    "Hannah White": {
        "days": [0, 1, 2, 3],  # Mon-Thu only
        "start": time(7, 0),
        "end": time(12, 0),  # Mornings only
        "preferred_days": [0, 1],
    },
    "Derek Johnson": {
        "days": [1, 2, 3, 4, 5],  # Tue-Sat
        "start": time(11, 0),
        "end": time(16, 0),  # Afternoons
        "preferred_days": [4, 5],
    },
    # Developing tier - limited availability (students, new hires)
    "Ashley Rivera": {
        "days": [0, 2, 4, 5, 6],  # Scattered
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Brandon Kim": {
        "days": [0, 1, 2, 3],  # Weekdays early week
        "start": time(7, 0),
        "end": time(12, 0),  # Mornings (class in PM)
        "preferred_days": [0, 1],
    },
    "Chloe Adams": {
        "days": [5, 6],  # Weekends only
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Dylan Foster": {
        "days": [4, 5, 6],  # Fri-Sun only (student)
        "start": time(10, 0),
        "end": time(16, 0),
        "preferred_days": [5],
    },
    # ==================== BARTENDERS ====================
    "Carlos Rodriguez": {
        "days": [0, 1, 3, 4, 5, 6],  # Off Tue
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Sophia Turner": {
        "days": [0, 2, 3, 4, 5, 6],  # Off Tue
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [4, 5, 6],
    },
    "Jake Morrison": {
        "days": [0, 1, 2, 3, 5],  # Off Thu, Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [0, 1, 2],
    },
    "Mia Collins": {
        "days": [3, 4, 5, 6],  # Thu-Sun
        "start": time(10, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    # ==================== HOSTS ====================
    "Sophie Kim": {
        "days": [0, 1, 2, 3, 4, 5, 6],  # Every day
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Ethan Park": {
        "days": [0, 1, 2, 3, 4, 5],  # Off Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [4, 5],
    },
    "Olivia Brown": {
        "days": [0, 1, 3, 4, 5, 6],  # Off Tue
        "start": time(7, 0),
        "end": time(14, 0),
        "preferred_days": [5, 6],
    },
    "Noah Garcia": {
        "days": [4, 5, 6],  # Weekends + Fri
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    # ==================== BUSSERS ====================
    "Luis Hernandez": {
        "days": [0, 1, 2, 3, 4, 5],  # Off Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [4, 5],
    },
    "Emma Clark": {
        "days": [0, 1, 2, 4, 5, 6],  # Off Wed
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Jason Lee": {
        "days": [0, 1, 2, 3, 4],  # Weekdays
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [0, 1, 2],
    },
    "Ava Martinez": {
        "days": [2, 3, 4, 5, 6],  # Wed-Sun
        "start": time(10, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Ryan Cooper": {
        "days": [0, 1, 5, 6],  # Mon, Tue, Weekend
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Isabella Wright": {
        "days": [1, 2, 3, 4, 5],  # Tue-Sat
        "start": time(7, 0),
        "end": time(14, 0),
        "preferred_days": [4, 5],
    },
    "Chris Taylor": {
        "days": [5, 6],  # Weekends only
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Zoe Anderson": {
        "days": [4, 5, 6],  # Fri-Sun
        "start": time(10, 0),
        "end": time(16, 0),
        "preferred_days": [5],
    },
    # ==================== RUNNERS ====================
    "Miguel Santos": {
        "days": [0, 1, 2, 3, 4, 5],  # Off Sun
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [4, 5],
    },
    "Grace Lee": {
        "days": [0, 1, 2, 4, 5, 6],  # Off Wed
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Austin Miller": {
        "days": [0, 1, 2, 3, 4],  # Weekdays
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [0, 1, 2],
    },
    "Lily Chen": {
        "days": [2, 3, 4, 5, 6],  # Wed-Sun
        "start": time(10, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Jordan Davis": {
        "days": [0, 1, 5, 6],  # Mon, Tue, Weekend
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
    "Maya Wilson": {
        "days": [5, 6],  # Weekends only
        "start": time(7, 0),
        "end": time(16, 0),
        "preferred_days": [5, 6],
    },
}

# ============================================================
# MIMOSAS STAFF PREFERENCES
# ============================================================

MIMOSAS_STAFF_PREFERENCES = {
    # ==================== SERVERS ====================
    "Maria Garcia": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 32,
        "avoid_clopening": False, "preferred_sections": ["Main Dining", "Outdoor Patio"],
        "shift_types": ["morning", "closing"],
    },
    "Daniel Martinez": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 32,
        "avoid_clopening": False, "preferred_sections": ["Main Dining"],
        "shift_types": ["morning"],
    },
    "Jessica Thompson": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 28,
        "avoid_clopening": False, "preferred_sections": ["Outdoor Patio"],
        "shift_types": ["morning", "closing"],
    },
    "Kevin O'Brien": {
        "max_shifts": 4, "max_hours": 36, "min_hours": 24,
        "avoid_clopening": True, "preferred_sections": ["Bar"],
        "shift_types": ["closing"],
    },
    "James Wilson": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 24,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Emily Chen": {
        "max_shifts": 4, "max_hours": 24, "min_hours": 16,
        "avoid_clopening": True, "preferred_sections": ["Outdoor Patio"],
        "shift_types": ["morning"],
    },
    "Aisha Johnson": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": False, "preferred_sections": ["Main Dining"],
        "shift_types": ["morning", "closing"],
    },
    "Tyler Brooks": {
        "max_shifts": 4, "max_hours": 28, "min_hours": 20,
        "avoid_clopening": True, "preferred_sections": ["Bar"],
        "shift_types": ["closing"],
    },
    "Nina Patel": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 16,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Marcus Lee": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 24,
        "avoid_clopening": False, "preferred_sections": ["Main Dining"],
        "shift_types": ["morning"],
    },
    "Hannah White": {
        "max_shifts": 3, "max_hours": 18, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning"],
    },
    "Derek Johnson": {
        "max_shifts": 3, "max_hours": 20, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["closing"],
    },
    "Ashley Rivera": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Brandon Kim": {
        "max_shifts": 3, "max_hours": 18, "min_hours": 10,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning"],
    },
    "Chloe Adams": {
        "max_shifts": 2, "max_hours": 16, "min_hours": 8,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Dylan Foster": {
        "max_shifts": 2, "max_hours": 14, "min_hours": 8,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["closing"],
    },
    # ==================== BARTENDERS ====================
    "Carlos Rodriguez": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 32,
        "avoid_clopening": False, "preferred_sections": ["Bar"],
        "shift_types": ["morning", "closing"],
    },
    "Sophia Turner": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 28,
        "avoid_clopening": False, "preferred_sections": ["Bar"],
        "shift_types": ["morning", "closing"],
    },
    "Jake Morrison": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": True, "preferred_sections": ["Bar"],
        "shift_types": ["morning"],
    },
    "Mia Collins": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": ["Bar"],
        "shift_types": ["closing"],
    },
    # ==================== HOSTS ====================
    "Sophie Kim": {
        "max_shifts": 6, "max_hours": 40, "min_hours": 30,
        "avoid_clopening": False, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Ethan Park": {
        "max_shifts": 5, "max_hours": 36, "min_hours": 24,
        "avoid_clopening": False, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Olivia Brown": {
        "max_shifts": 4, "max_hours": 28, "min_hours": 16,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning"],
    },
    "Noah Garcia": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    # ==================== BUSSERS ====================
    "Luis Hernandez": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 28,
        "avoid_clopening": False, "preferred_sections": ["Main Dining"],
        "shift_types": ["morning", "closing"],
    },
    "Emma Clark": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": False, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Jason Lee": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": True, "preferred_sections": ["Main Dining"],
        "shift_types": ["morning"],
    },
    "Ava Martinez": {
        "max_shifts": 3, "max_hours": 20, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["closing"],
    },
    "Ryan Cooper": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": ["Outdoor Patio"],
        "shift_types": ["morning", "closing"],
    },
    "Isabella Wright": {
        "max_shifts": 3, "max_hours": 20, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning"],
    },
    "Chris Taylor": {
        "max_shifts": 2, "max_hours": 16, "min_hours": 8,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Zoe Anderson": {
        "max_shifts": 2, "max_hours": 14, "min_hours": 8,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["closing"],
    },
    # ==================== RUNNERS ====================
    "Miguel Santos": {
        "max_shifts": 5, "max_hours": 40, "min_hours": 28,
        "avoid_clopening": False, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Grace Lee": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": False, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Austin Miller": {
        "max_shifts": 4, "max_hours": 32, "min_hours": 20,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning"],
    },
    "Lily Chen": {
        "max_shifts": 3, "max_hours": 20, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["closing"],
    },
    "Jordan Davis": {
        "max_shifts": 3, "max_hours": 24, "min_hours": 12,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
    "Maya Wilson": {
        "max_shifts": 2, "max_hours": 16, "min_hours": 8,
        "avoid_clopening": True, "preferred_sections": [],
        "shift_types": ["morning", "closing"],
    },
}

MIMOSAS_KITCHEN_STATIONS = [
    {"name": "Grill", "max_concurrent_orders": 8},
    {"name": "Egg Station", "max_concurrent_orders": 12},
    {"name": "Waffle/Griddle", "max_concurrent_orders": 10},
    {"name": "Cold Prep", "max_concurrent_orders": 15},
]

# Full menu from the PDF with costs
MIMOSAS_MENU_ITEMS = [
    # Great For Sharing
    {"name": "French Beignets", "category": "Great For Sharing", "price": 9.84, "cost": 2.50},
    {"name": "Cast Iron Blueberry Biscuits", "category": "Great For Sharing", "price": 11.78, "cost": 3.20},
    # Lighten Up
    {"name": "Yogurt Parfait", "category": "Lighten Up", "price": 13.58, "cost": 4.00},
    # Artisan Breakfast
    {"name": "Artisan Breakfast", "category": "Artisan Breakfast", "price": 14.59, "cost": 4.50},
    # Benny Sends Me (Eggs Benedict)
    {"name": "Classic Benedict", "category": "Benny Sends Me", "price": 16.62, "cost": 5.00},
    {"name": "Pastrami Salmon Benedict", "category": "Benny Sends Me", "price": 18.29, "cost": 7.50},
    {"name": "Holy Crab!! Benedict", "category": "Benny Sends Me", "price": 18.70, "cost": 8.00},
    {"name": "Home Hash Benedict", "category": "Benny Sends Me", "price": 17.66, "cost": 5.50},
    {"name": "Florentine Benedict", "category": "Benny Sends Me", "price": 15.79, "cost": 4.80},
    # Shrimp & Grits
    {"name": "Classic Shrimp & Grits", "category": "Shrimp & Grits", "price": 18.99, "cost": 7.00},
    {"name": "New Orleans Shrimp & Grits", "category": "Shrimp & Grits", "price": 18.32, "cost": 7.20},
    # Farm Fresh Classics
    {"name": "Breakfast Essentials", "category": "Farm Fresh Classics", "price": 13.79, "cost": 4.00},
    {"name": "Breakfast Sandwich", "category": "Farm Fresh Classics", "price": 14.89, "cost": 4.50},
    {"name": "Black Angus Steak & Eggs", "category": "Farm Fresh Classics", "price": 19.78, "cost": 8.50},
    # Fully Worth The Calories
    {"name": "Creme Brulee French Toast", "category": "Fully Worth The Calories", "price": 15.99, "cost": 4.00},
    {"name": "Salted Caramel Banana French Toast", "category": "Fully Worth The Calories", "price": 15.99, "cost": 4.20},
    {"name": "Cookie Dough Stuffed French Toast", "category": "Fully Worth The Calories", "price": 15.58, "cost": 4.00},
    {"name": "Lemon Blueberry Goat Cheese", "category": "Fully Worth The Calories", "price": 15.99, "cost": 4.50},
    {"name": "Croissant French Toast", "category": "Fully Worth The Calories", "price": 15.59, "cost": 4.30},
    {"name": "Mimosa's Orange Cream Waffle", "category": "Fully Worth The Calories", "price": 16.79, "cost": 4.00},
    # Signature Breakfast
    {"name": "Crab & Avocado Toast", "category": "Signature Breakfast", "price": 17.99, "cost": 7.50},
    {"name": "Traditional Avocado Toast", "category": "Signature Breakfast", "price": 12.99, "cost": 4.00},
    {"name": "Vegetarian Taco Skillet", "category": "Signature Breakfast", "price": 16.87, "cost": 5.00},
    {"name": "Fried Lobster & Waffles", "category": "Signature Breakfast", "price": 22.79, "cost": 10.50},
    {"name": "Chicken & Waffles", "category": "Signature Breakfast", "price": 17.29, "cost": 5.50},
    {"name": "Double Trouble", "category": "Signature Breakfast", "price": 15.78, "cost": 5.00},
    {"name": "Southern Chicken Biscuit", "category": "Signature Breakfast", "price": 15.99, "cost": 5.00},
    {"name": "Breakfast Smash Burger", "category": "Signature Breakfast", "price": 15.29, "cost": 5.50},
    {"name": "Birria Hash", "category": "Signature Breakfast", "price": 17.89, "cost": 6.50},
    # For The Love Of Eggs
    {"name": "Chunky Lobster Scram-Blette", "category": "For The Love Of Eggs", "price": 20.79, "cost": 9.50},
    {"name": "Tuscan Scram-Blette", "category": "For The Love Of Eggs", "price": 15.78, "cost": 5.00},
    {"name": "Bacon Avocado Omelette", "category": "For The Love Of Eggs", "price": 15.99, "cost": 5.50},
    {"name": "Spinach & Feta Omelette", "category": "For The Love Of Eggs", "price": 15.79, "cost": 4.50},
    {"name": "Lobster Me! Omelette", "category": "For The Love Of Eggs", "price": 19.87, "cost": 9.00},
    {"name": "Caprese Omelette", "category": "For The Love Of Eggs", "price": 16.89, "cost": 5.00},
    {"name": "Let Me Do Me!", "category": "For The Love Of Eggs", "price": 12.00, "cost": 4.00},
    # Skillets
    {"name": "Santa Fe Skillet", "category": "Skillets", "price": 15.99, "cost": 5.00},
    {"name": "Corn Beef Hash Skillet", "category": "Skillets", "price": 16.99, "cost": 5.50},
    {"name": "Texas Steak Skillet", "category": "Skillets", "price": 17.59, "cost": 7.00},
    {"name": "Gypsy Skillet", "category": "Skillets", "price": 16.99, "cost": 5.50},
    # Lunch Plates
    {"name": "Grilled Chicken Sandwich", "category": "Lunch Plates", "price": 16.49, "cost": 5.50},
    {"name": "Short Rib Melt", "category": "Lunch Plates", "price": 18.49, "cost": 6.50},
    {"name": "Turkey Avocado Club", "category": "Lunch Plates", "price": 15.99, "cost": 5.00},
    {"name": "Blackened Salmon BLT", "category": "Lunch Plates", "price": 18.99, "cost": 7.50},
    {"name": "Garden Veggie Wrap", "category": "Lunch Plates", "price": 14.29, "cost": 4.20},
    {"name": "Brunch Burger", "category": "Lunch Plates", "price": 17.49, "cost": 6.00},
    {"name": "Nashville Hot Chicken Sandwich", "category": "Lunch Plates", "price": 17.99, "cost": 6.30},
    {"name": "Steak Frites", "category": "Lunch Plates", "price": 22.99, "cost": 9.00},
    # Salads
    {"name": "Cobb Salad", "category": "Salads", "price": 16.49, "cost": 5.00},
    {"name": "Southwest Chicken Salad", "category": "Salads", "price": 16.99, "cost": 5.50},
    {"name": "Mediterranean Chop Salad", "category": "Salads", "price": 15.99, "cost": 4.80},
    {"name": "Kale Caesar", "category": "Salads", "price": 14.49, "cost": 4.00},
    {"name": "Strawberry Spinach Salad", "category": "Salads", "price": 15.49, "cost": 4.50},
    {"name": "Shrimp Louie Salad", "category": "Salads", "price": 18.49, "cost": 7.00},
    # Sides
    {"name": "Truffle Fries", "category": "Sides", "price": 8.99, "cost": 2.50},
    {"name": "Sweet Potato Fries", "category": "Sides", "price": 7.99, "cost": 2.00},
    {"name": "Seasonal Fruit Bowl", "category": "Sides", "price": 6.99, "cost": 2.00},
    {"name": "House Made Chips", "category": "Sides", "price": 5.99, "cost": 1.50},
    {"name": "Side Bacon", "category": "Sides", "price": 6.49, "cost": 2.50},
    {"name": "Side Sausage", "category": "Sides", "price": 6.49, "cost": 2.50},
    # Kids
    {"name": "Kids Pancakes", "category": "Kids", "price": 7.99, "cost": 2.00},
    {"name": "Kids Scramble", "category": "Kids", "price": 7.49, "cost": 2.00},
    {"name": "Kids Chicken Tenders", "category": "Kids", "price": 8.99, "cost": 3.00},
    {"name": "Kids Grilled Cheese", "category": "Kids", "price": 7.49, "cost": 2.00},
    {"name": "Kids Mac & Cheese", "category": "Kids", "price": 7.99, "cost": 2.50},
    # Desserts
    {"name": "Beignet Trio", "category": "Desserts", "price": 8.99, "cost": 2.20},
    {"name": "Bananas Foster Bread Pudding", "category": "Desserts", "price": 9.99, "cost": 2.80},
    {"name": "Chocolate Lava Cake", "category": "Desserts", "price": 10.49, "cost": 3.00},
    {"name": "Cheesecake Jar", "category": "Desserts", "price": 9.49, "cost": 2.60},
    {"name": "Seasonal Pie", "category": "Desserts", "price": 8.49, "cost": 2.30},
    # Coffee & Tea
    {"name": "Cold Brew", "category": "Coffee & Tea", "price": 5.49, "cost": 0.80},
    {"name": "Latte", "category": "Coffee & Tea", "price": 5.99, "cost": 0.90},
    {"name": "Cappuccino", "category": "Coffee & Tea", "price": 5.99, "cost": 0.90},
    {"name": "Matcha Latte", "category": "Coffee & Tea", "price": 6.49, "cost": 1.10},
    {"name": "Iced Tea", "category": "Coffee & Tea", "price": 3.99, "cost": 0.40},
    {"name": "Fresh Lemonade", "category": "Coffee & Tea", "price": 4.49, "cost": 0.60},
    # Cocktails
    {"name": "Classic Mimosa", "category": "Cocktails", "price": 12.00, "cost": 3.50},
    {"name": "Blood Orange Mimosa", "category": "Cocktails", "price": 13.00, "cost": 3.80},
    {"name": "Lavender Collins", "category": "Cocktails", "price": 12.50, "cost": 3.60},
    {"name": "Espresso Martini", "category": "Cocktails", "price": 14.00, "cost": 4.20},
    {"name": "Old Fashioned", "category": "Cocktails", "price": 13.50, "cost": 3.90},
    {"name": "Paloma", "category": "Cocktails", "price": 12.50, "cost": 3.70},
    # Beer & Wine
    {"name": "House Red", "category": "Beer & Wine", "price": 9.00, "cost": 2.50},
    {"name": "House White", "category": "Beer & Wine", "price": 9.00, "cost": 2.50},
    {"name": "Local IPA", "category": "Beer & Wine", "price": 7.50, "cost": 2.20},
    {"name": "Wheat Ale", "category": "Beer & Wine", "price": 7.00, "cost": 2.00},
]

# Popularity weights for sample order generation (higher = more orders)
# Items with weight < 0.3 will almost never be ordered and should get 86'd
MIMOSAS_ITEM_POPULARITY = {
    # ==================== TOP SELLERS ====================
    "Fried Lobster & Waffles": 3.5,  # Signature item - STAR
    "Mimosa's Orange Cream Waffle": 3.0,  # House special - STAR
    "Classic Benedict": 2.8,
    "Chunky Lobster Scram-Blette": 2.5,
    "Chicken & Waffles": 2.5,
    "Classic Shrimp & Grits": 2.3,
    "Crab & Avocado Toast": 2.0,
    "Black Angus Steak & Eggs": 1.8,
    "Creme Brulee French Toast": 1.8,
    "Pastrami Salmon Benedict": 1.6,

    # ==================== AVERAGE PERFORMERS ====================
    "New Orleans Shrimp & Grits": 1.2,
    "Breakfast Sandwich": 1.1,
    "Southern Chicken Biscuit": 1.0,
    "French Beignets": 1.0,

    # ==================== UNDERPERFORMERS (will show in bottom rankings) ====================
    "Florentine Benedict": 0.6,
    "Gypsy Skillet": 0.5,
    "Corn Beef Hash Skillet": 0.5,

    # ==================== 86 CANDIDATES (should get flagged for removal) ====================
    "Let Me Do Me!": 0.15,  # Almost no one orders this
    "Yogurt Parfait": 0.18,  # Health food at a brunch place
    "Artisan Breakfast": 0.2,  # Generic, unexciting
    "Lemon Blueberry Goat Cheese": 0.22,  # Too niche
    "Vegetarian Taco Skillet": 0.25,  # Doesn't fit menu theme
    "Garden Veggie Wrap": 0.2,
    "Matcha Latte": 0.25,
    "Seasonal Pie": 0.28,
    "House Made Chips": 0.25,

    # ==================== NEW MENU HIGHLIGHTS ====================
    "Classic Mimosa": 3.2,
    "Brunch Burger": 2.1,
    "Nashville Hot Chicken Sandwich": 1.8,
    "Short Rib Melt": 1.6,
    "Cobb Salad": 1.4,
    "Espresso Martini": 1.9,
}

MIMOSAS_INGREDIENTS = [
    {"name": "Eggs", "category": "Dairy", "unit": "each", "cost_per_unit": 0.35, "par_level": 200, "supplier": "Farm Fresh Co"},
    {"name": "Applewood Bacon", "category": "Meat", "unit": "lb", "cost_per_unit": 8.50, "par_level": 20, "supplier": "Premium Meats"},
    {"name": "Lobster Tail", "category": "Seafood", "unit": "each", "cost_per_unit": 12.00, "par_level": 15, "supplier": "Ocean Catch"},
    {"name": "Crab Meat", "category": "Seafood", "unit": "lb", "cost_per_unit": 18.00, "par_level": 10, "supplier": "Ocean Catch"},
    {"name": "Shrimp", "category": "Seafood", "unit": "lb", "cost_per_unit": 14.00, "par_level": 15, "supplier": "Ocean Catch"},
    {"name": "Avocado", "category": "Produce", "unit": "each", "cost_per_unit": 1.50, "par_level": 30, "supplier": "Fresh Farms"},
    {"name": "Brioche Bread", "category": "Bakery", "unit": "loaf", "cost_per_unit": 4.50, "par_level": 10, "supplier": "Artisan Bakery"},
    {"name": "English Muffins", "category": "Bakery", "unit": "pack", "cost_per_unit": 3.00, "par_level": 15, "supplier": "Artisan Bakery"},
    {"name": "Croissants", "category": "Bakery", "unit": "each", "cost_per_unit": 2.00, "par_level": 20, "supplier": "Artisan Bakery"},
    {"name": "Cheddar Cheese", "category": "Dairy", "unit": "lb", "cost_per_unit": 6.00, "par_level": 10, "supplier": "Dairy Direct"},
    {"name": "Feta Cheese", "category": "Dairy", "unit": "lb", "cost_per_unit": 8.00, "par_level": 5, "supplier": "Dairy Direct"},
    {"name": "Goat Cheese", "category": "Dairy", "unit": "lb", "cost_per_unit": 10.00, "par_level": 5, "supplier": "Dairy Direct"},
    {"name": "Spinach", "category": "Produce", "unit": "lb", "cost_per_unit": 4.00, "par_level": 10, "supplier": "Fresh Farms"},
    {"name": "Grits", "category": "Dry Goods", "unit": "lb", "cost_per_unit": 2.50, "par_level": 15, "supplier": "Pantry Supply"},
    {"name": "Maple Syrup", "category": "Condiments", "unit": "bottle", "cost_per_unit": 8.00, "par_level": 10, "supplier": "Vermont Finest"},
    {"name": "Hollandaise Mix", "category": "Sauce", "unit": "packet", "cost_per_unit": 3.00, "par_level": 20, "supplier": "Pantry Supply"},
    {"name": "Chicken Breast", "category": "Meat", "unit": "lb", "cost_per_unit": 5.50, "par_level": 15, "supplier": "Premium Meats"},
    {"name": "Black Angus Steak", "category": "Meat", "unit": "lb", "cost_per_unit": 18.00, "par_level": 10, "supplier": "Premium Meats"},
    {"name": "Corned Beef", "category": "Meat", "unit": "lb", "cost_per_unit": 12.00, "par_level": 8, "supplier": "Premium Meats"},
    {"name": "Belgian Waffle Mix", "category": "Dry Goods", "unit": "lb", "cost_per_unit": 3.50, "par_level": 20, "supplier": "Pantry Supply"},
    {"name": "Blueberries", "category": "Produce", "unit": "pint", "cost_per_unit": 4.00, "par_level": 15, "supplier": "Fresh Farms"},
    {"name": "Strawberries", "category": "Produce", "unit": "pint", "cost_per_unit": 3.50, "par_level": 15, "supplier": "Fresh Farms"},
    {"name": "Heavy Cream", "category": "Dairy", "unit": "quart", "cost_per_unit": 5.00, "par_level": 10, "supplier": "Dairy Direct"},
    {"name": "Salted Caramel Sauce", "category": "Sauce", "unit": "bottle", "cost_per_unit": 6.00, "par_level": 8, "supplier": "Gourmet Pantry"},
    {"name": "Smoked Salmon", "category": "Seafood", "unit": "lb", "cost_per_unit": 22.00, "par_level": 5, "supplier": "Ocean Catch"},
]


class SeedService:
    """
    Service for seeding default data.

    Handles cold start scenarios by creating default restaurants,
    waiters, sections, and tables when the database is empty.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_default_data(self) -> dict:
        """
        Ensure default data exists for cold start.

        Creates both The Golden Fork and Mimosas restaurants
        if no data exists.

        Returns:
            Dict with created/existing counts
        """
        result = {
            "restaurants_created": 0,
            "sections_created": 0,
            "tables_created": 0,
            "waiters_created": 0,
            "menu_items_created": 0,
            "already_seeded": False,
            "mimosas": None,
        }

        # Check if any restaurants exist
        restaurant_count = await self._count_restaurants()
        if restaurant_count > 0:
            result["already_seeded"] = True
            logger.info("Database already has data, checking for Mimosas...")

            # Still ensure Mimosas exists (idempotent)
            mimosas_result = await self.ensure_mimosas_restaurant()
            result["mimosas"] = mimosas_result
            if mimosas_result.get("created"):
                result["restaurants_created"] += 1
                result["sections_created"] += mimosas_result.get("sections_created", 0)
                result["tables_created"] += mimosas_result.get("tables_created", 0)
                result["waiters_created"] += mimosas_result.get("waiters_created", 0)
                result["menu_items_created"] += mimosas_result.get("menu_items_created", 0)

            return result

        logger.info("Cold start detected, seeding default data...")

        # Create default restaurant (The Golden Fork)
        restaurant = await self._create_default_restaurant()
        result["restaurants_created"] = 1

        # Create sections
        sections = await self._create_default_sections(restaurant.id)
        result["sections_created"] = len(sections)

        # Create tables
        tables_created = 0
        for section in sections:
            tables = await self._create_default_tables(
                restaurant_id=restaurant.id,
                section_id=section.id,
                section_name=section.name,
            )
            tables_created += len(tables)
        result["tables_created"] = tables_created

        # Create waiters
        waiters = await self._create_default_waiters(restaurant.id)
        result["waiters_created"] = len(waiters)

        await self.session.commit()

        # Also create Mimosas restaurant with full data
        mimosas_result = await self.ensure_mimosas_restaurant()
        result["mimosas"] = mimosas_result
        if mimosas_result.get("created"):
            result["restaurants_created"] += 1
            result["sections_created"] += mimosas_result.get("sections_created", 0)
            result["tables_created"] += mimosas_result.get("tables_created", 0)
            result["waiters_created"] += mimosas_result.get("waiters_created", 0)
            result["menu_items_created"] += mimosas_result.get("menu_items_created", 0)

        logger.info(
            f"Seed complete: {result['restaurants_created']} restaurants, "
            f"{result['sections_created']} sections, "
            f"{result['tables_created']} tables, "
            f"{result['waiters_created']} waiters, "
            f"{result['menu_items_created']} menu items"
        )

        return result

    async def ensure_restaurant_has_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """
        Ensure a restaurant has at least one waiter.

        If no waiters exist, creates default waiters.

        Args:
            restaurant_id: The restaurant ID

        Returns:
            List of waiters (existing or newly created)
        """
        # Check existing waiters
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        waiters = list(result.scalars().all())

        if waiters:
            return waiters

        # Create default waiters
        logger.info(f"No waiters found for restaurant {restaurant_id}, creating defaults")
        waiters = await self._create_default_waiters(restaurant_id)
        await self.session.commit()

        return waiters

    async def create_sample_shifts_and_visits(
        self,
        restaurant_id: UUID,
        days_back: int = 30,
    ) -> dict:
        """
        Create sample shifts and visits for testing.

        Useful for development/demo environments.

        Args:
            restaurant_id: The restaurant ID
            days_back: Number of days of history to create

        Returns:
            Dict with created counts
        """
        result = {
            "shifts_created": 0,
            "visits_created": 0,
        }

        # Get waiters and tables
        waiters = await self._get_restaurant_waiters(restaurant_id)
        tables = await self._get_restaurant_tables(restaurant_id)

        if not waiters or not tables:
            logger.warning("No waiters or tables found, skipping sample data")
            return result

        # Create shifts and visits for past days
        import random

        for day_offset in range(days_back, 0, -1):
            shift_date = datetime.utcnow() - timedelta(days=day_offset)

            # Create shift for each waiter
            for waiter in waiters:
                # Random chance of working this day
                if random.random() > 0.6:
                    continue

                shift = Shift(
                    restaurant_id=restaurant_id,
                    waiter_id=waiter.id,
                    clock_in=shift_date.replace(hour=16, minute=0),
                    clock_out=shift_date.replace(hour=23, minute=0),
                    status="ended",
                    tables_served=0,
                    total_covers=0,
                    total_tips=Decimal("0"),
                    total_sales=Decimal("0"),
                )
                self.session.add(shift)
                await self.session.flush()
                result["shifts_created"] += 1

                # Create random visits for this shift
                num_visits = random.randint(3, 8)
                for v in range(num_visits):
                    table = random.choice(tables)
                    party_size = random.randint(2, min(6, table.capacity))
                    check_amount = Decimal(str(random.uniform(40, 150)))
                    tip_pct = random.uniform(0.15, 0.25)
                    tip = check_amount * Decimal(str(tip_pct))

                    visit = Visit(
                        restaurant_id=restaurant_id,
                        table_id=table.id,
                        waiter_id=waiter.id,
                        shift_id=shift.id,
                        party_size=party_size,
                        seated_at=shift_date.replace(hour=17 + v),
                        cleared_at=shift_date.replace(hour=18 + v),
                        subtotal=check_amount,
                        tax=check_amount * Decimal("0.08"),
                        total=check_amount * Decimal("1.08"),
                        tip=tip,
                        tip_percentage=Decimal(str(tip_pct * 100)),
                    )
                    self.session.add(visit)

                    # Update shift totals
                    shift.tables_served += 1
                    shift.total_covers += party_size
                    shift.total_tips += tip
                    shift.total_sales += check_amount

                    # Update waiter lifetime stats
                    waiter.total_covers += party_size
                    waiter.total_tips = Decimal(str(waiter.total_tips)) + tip
                    waiter.total_tables_served += 1
                    waiter.total_sales = Decimal(str(waiter.total_sales)) + check_amount

                    result["visits_created"] += 1

        await self.session.commit()

        logger.info(
            f"Created sample data: {result['shifts_created']} shifts, "
            f"{result['visits_created']} visits"
        )

        return result

    async def _count_restaurants(self) -> int:
        """Count total restaurants."""
        stmt = select(func.count(Restaurant.id))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _create_default_restaurant(self) -> Restaurant:
        """Create the default restaurant."""
        restaurant = Restaurant(
            name="The Golden Fork",
            timezone="America/New_York",
            config=DEFAULT_RESTAURANT_CONFIG,
        )
        self.session.add(restaurant)
        await self.session.flush()
        return restaurant

    async def _create_default_sections(
        self,
        restaurant_id: UUID,
    ) -> List[Section]:
        """Create default sections for a restaurant."""
        sections = []
        for section_data in DEFAULT_SECTIONS:
            section = Section(
                restaurant_id=restaurant_id,
                name=section_data["name"],
                is_active=section_data["is_active"],
            )
            self.session.add(section)
            sections.append(section)

        await self.session.flush()
        return sections

    async def _create_default_tables(
        self,
        restaurant_id: UUID,
        section_id: UUID,
        section_name: str,
    ) -> List[Table]:
        """Create default tables for a section."""
        tables = []
        table_configs = DEFAULT_TABLES.get(section_name, [])

        for table_data in table_configs:
            table = Table(
                restaurant_id=restaurant_id,
                section_id=section_id,
                table_number=table_data["table_number"],
                capacity=table_data["capacity"],
                table_type=table_data["table_type"],
                state="clean",
            )
            self.session.add(table)
            tables.append(table)

        await self.session.flush()
        return tables

    async def _create_default_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """Create default waiters for a restaurant."""
        await self._ensure_waiter_role_column()
        waiters = []
        for waiter_data in DEFAULT_WAITERS:
            waiter = Waiter(
                restaurant_id=restaurant_id,
                name=waiter_data["name"],
                email=waiter_data["email"],
                tier=waiter_data["tier"],
                composite_score=Decimal(str(waiter_data["composite_score"])),
                total_shifts=waiter_data.get("total_shifts", 0),
                total_covers=waiter_data.get("total_covers", 0),
                total_tips=Decimal(str(waiter_data.get("total_tips", 0))),
                total_tables_served=waiter_data.get("total_tables_served", 0),
                total_sales=Decimal(str(waiter_data.get("total_sales", 0))),
            )
            self.session.add(waiter)
            waiters.append(waiter)

        await self.session.flush()
        return waiters

    async def _ensure_waiter_role_column(self) -> None:
        """Ensure legacy databases have the waiters.role column."""
        # Check the database dialect
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind else "sqlite"

        if dialect_name == "sqlite":
            # SQLite: Check if column exists via pragma
            result = await self.session.execute(text("PRAGMA table_info(waiters)"))
            columns = [row[1] for row in result.fetchall()]
            if "role" not in columns:
                await self.session.execute(
                    text("ALTER TABLE waiters ADD COLUMN role VARCHAR(20) DEFAULT 'server'")
                )
        else:
            # PostgreSQL: Use IF NOT EXISTS syntax
            await self.session.execute(
                text(
                    "ALTER TABLE waiters "
                    "ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'server'"
                )
            )

    async def _get_restaurant_waiters(
        self,
        restaurant_id: UUID,
    ) -> List[Waiter]:
        """Get all active waiters for a restaurant."""
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_restaurant_tables(
        self,
        restaurant_id: UUID,
    ) -> List[Table]:
        """Get all active tables for a restaurant."""
        stmt = (
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .where(Table.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_first_restaurant(self) -> Optional[Restaurant]:
        """Get the first restaurant if one exists."""
        stmt = select(Restaurant).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def seed_demo(
        self,
        days_back: int = 30,
        run_tier_calculation: bool = True,
    ) -> dict:
        """
        One-stop demo seeding for frontend development.

        This method does everything needed to get a working demo:
        1. Creates default restaurant if none exists (or uses existing)
        2. Creates waiters if none exist for the restaurant
        3. Creates sample shifts and visits for the past N days
        4. Optionally runs tier calculation to populate insights

        Args:
            days_back: Number of days of history to create (default 30)
            run_tier_calculation: Whether to run tier calculation after seeding

        Returns:
            Dict with all info the frontend needs to start using the API
        """
        result = {
            "success": True,
            "message": "",
            "restaurant_id": None,
            "restaurant_name": None,
            "waiters": [],
            "shifts_created": 0,
            "visits_created": 0,
            "days_of_history": days_back,
            "tiers_calculated": False,
        }

        # Step 1: Get or create restaurant
        restaurant = await self._get_first_restaurant()
        created_new = False

        if restaurant is None:
            # Create default restaurant with sections, tables, waiters
            await self._create_default_restaurant_with_all()
            await self.session.commit()
            restaurant = await self._get_first_restaurant()
            created_new = True
            logger.info(f"Created new restaurant: {restaurant.name}")
        else:
            logger.info(f"Using existing restaurant: {restaurant.name}")

        result["restaurant_id"] = restaurant.id
        result["restaurant_name"] = restaurant.name

        # Step 2: Ensure waiters exist
        waiters = await self.ensure_restaurant_has_waiters(restaurant.id)
        result["waiters"] = [
            {
                "id": w.id,
                "name": w.name,
                "tier": w.tier,
                "composite_score": float(w.composite_score) if w.composite_score else 50.0,
            }
            for w in waiters
        ]

        # Step 3: Check if we need to create sample data
        # Only create sample data if we just created the restaurant
        # or if there are very few visits
        visit_count = await self._count_visits(restaurant.id)

        if visit_count < 10:
            logger.info(f"Creating {days_back} days of sample data...")
            sample_result = await self.create_sample_shifts_and_visits(
                restaurant_id=restaurant.id,
                days_back=days_back,
            )
            result["shifts_created"] = sample_result["shifts_created"]
            result["visits_created"] = sample_result["visits_created"]
        else:
            logger.info(f"Restaurant already has {visit_count} visits, skipping sample data")

        # Step 4: Run tier calculation if requested
        if run_tier_calculation:
            try:
                from app.services.tier_job import TierRecalculationJob

                job = TierRecalculationJob(session=self.session)
                tier_result = await job.run(restaurant_id=restaurant.id, use_llm=False)
                result["tiers_calculated"] = tier_result.success

                # Refresh waiter data after tier calculation
                waiters = await self._get_restaurant_waiters(restaurant.id)
                result["waiters"] = [
                    {
                        "id": w.id,
                        "name": w.name,
                        "tier": w.tier,
                        "composite_score": float(w.composite_score) if w.composite_score else 50.0,
                    }
                    for w in waiters
                ]
            except Exception as e:
                logger.warning(f"Tier calculation failed: {e}")
                result["tiers_calculated"] = False

        # Build message
        if created_new:
            result["message"] = (
                f"Created demo restaurant '{restaurant.name}' with "
                f"{len(result['waiters'])} waiters and {result['visits_created']} visits"
            )
        else:
            result["message"] = (
                f"Using existing restaurant '{restaurant.name}' with "
                f"{len(result['waiters'])} waiters"
            )
            if result["visits_created"] > 0:
                result["message"] += f" (added {result['visits_created']} sample visits)"

        return result

    async def _create_default_restaurant_with_all(self) -> Restaurant:
        """Create default restaurant with all related data."""
        # Create restaurant
        restaurant = await self._create_default_restaurant()

        # Create sections
        sections = await self._create_default_sections(restaurant.id)

        # Create tables for each section
        for section in sections:
            await self._create_default_tables(
                restaurant_id=restaurant.id,
                section_id=section.id,
                section_name=section.name,
            )

        # Create waiters
        await self._create_default_waiters(restaurant.id)

        return restaurant

    async def _count_visits(self, restaurant_id: UUID) -> int:
        """Count visits for a restaurant."""
        stmt = select(func.count(Visit.id)).where(Visit.restaurant_id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ============================================================
    # MIMOSAS RESTAURANT SEEDING
    # ============================================================

    async def ensure_mimosas_restaurant(self) -> dict:
        """
        Ensure Mimosas restaurant exists with full data.

        Creates a complete, fully-functional demo restaurant with:
        - Restaurant, sections, tables
        - Waiters with availability and preferences
        - Full menu with 41 items
        - Kitchen stations and ingredients
        - 60 days of sample shifts, visits, and orders

        Idempotent - checks if Mimosas exists before creating.

        Returns:
            Dict with creation status and counts
        """
        result = {
            "created": False,
            "restaurant_id": None,
            "restaurant_name": "Mimosas",
            "sections_created": 0,
            "tables_created": 0,
            "waiters_created": 0,
            "menu_items_created": 0,
            "kitchen_stations_created": 0,
            "ingredients_created": 0,
            "shifts_created": 0,
            "visits_created": 0,
            "order_items_created": 0,
        }

        # Check if Mimosas already exists
        stmt = select(Restaurant).where(Restaurant.name == "Mimosas")
        existing = await self.session.execute(stmt)
        restaurant = existing.scalar_one_or_none()

        if restaurant:
            result["restaurant_id"] = restaurant.id
            result["already_exists"] = True
            logger.info("Mimosas restaurant already exists")
            return result

        logger.info("Creating Mimosas restaurant with full data...")

        # Create Mimosas restaurant
        restaurant = Restaurant(
            name="Mimosas",
            timezone="America/Los_Angeles",
            config=MIMOSAS_RESTAURANT_CONFIG,
        )
        self.session.add(restaurant)
        await self.session.flush()

        result["restaurant_id"] = restaurant.id
        result["created"] = True

        # Create sections
        sections = await self._create_mimosas_sections(restaurant.id)
        result["sections_created"] = len(sections)

        # Create tables
        section_map = {s.name: s for s in sections}
        for section in sections:
            tables = await self._create_mimosas_tables(
                restaurant.id, section.id, section.name
            )
            result["tables_created"] += len(tables)

        # Create waiters
        waiters = await self._create_mimosas_waiters(restaurant.id)
        result["waiters_created"] = len(waiters)

        # Create staff availability
        await self._create_mimosas_staff_availability(restaurant.id, waiters)

        # Create staff preferences
        await self._create_mimosas_staff_preferences(restaurant.id, waiters, section_map)

        # Create staffing requirements
        await self._create_mimosas_staffing_requirements(restaurant.id)

        # Create kitchen stations
        stations = await self._create_mimosas_kitchen_stations(restaurant.id)
        result["kitchen_stations_created"] = len(stations)

        # Create ingredients
        ingredients = await self._create_mimosas_ingredients(restaurant.id)
        result["ingredients_created"] = len(ingredients)

        # Create menu items
        menu_items = await self._create_mimosas_menu(restaurant.id)
        result["menu_items_created"] = len(menu_items)

        # Create sample data (60 days of shifts, visits, order items)
        sample_result = await self._create_mimosas_sample_data(
            restaurant.id, waiters, menu_items, days_back=60
        )
        result["shifts_created"] = sample_result["shifts_created"]
        result["visits_created"] = sample_result["visits_created"]
        result["order_items_created"] = sample_result["order_items_created"]

        await self.session.commit()

        logger.info(
            f"Created Mimosas: {result['sections_created']} sections, "
            f"{result['tables_created']} tables, {result['waiters_created']} waiters, "
            f"{result['menu_items_created']} menu items, {result['visits_created']} visits"
        )

        return result

    async def _create_mimosas_sections(self, restaurant_id: UUID) -> List[Section]:
        """Create Mimosas sections."""
        sections = []
        for section_data in MIMOSAS_SECTIONS:
            section = Section(
                restaurant_id=restaurant_id,
                name=section_data["name"],
                is_active=section_data["is_active"],
            )
            self.session.add(section)
            sections.append(section)
        await self.session.flush()
        return sections

    async def _create_mimosas_tables(
        self, restaurant_id: UUID, section_id: UUID, section_name: str
    ) -> List[Table]:
        """Create Mimosas tables for a section."""
        tables = []
        table_configs = MIMOSAS_TABLES.get(section_name, [])
        for table_data in table_configs:
            table = Table(
                restaurant_id=restaurant_id,
                section_id=section_id,
                table_number=table_data["table_number"],
                capacity=table_data["capacity"],
                table_type=table_data["table_type"],
                state="clean",
            )
            self.session.add(table)
            tables.append(table)
        await self.session.flush()
        return tables

    async def _create_mimosas_waiters(self, restaurant_id: UUID) -> List[Waiter]:
        """Create all Mimosas staff (50 employees across all roles)."""
        await self._ensure_waiter_role_column()
        waiters = []
        for waiter_data in MIMOSAS_WAITERS:
            waiter = Waiter(
                restaurant_id=restaurant_id,
                name=waiter_data["name"],
                email=waiter_data["email"],
                phone=waiter_data.get("phone"),
                role=waiter_data.get("role", "server"),
                tier=waiter_data.get("tier"),  # Can be None for non-performance roles
                composite_score=Decimal(str(waiter_data["composite_score"])),
                total_shifts=waiter_data.get("total_shifts", 0),
                total_covers=waiter_data.get("total_covers", 0),
                total_tips=Decimal(str(waiter_data.get("total_tips", 0))),
                total_tables_served=waiter_data.get("total_tables_served", 0),
                total_sales=Decimal(str(waiter_data.get("total_sales", 0))),
            )
            self.session.add(waiter)
            waiters.append(waiter)
        await self.session.flush()
        logger.info(f"Created {len(waiters)} Mimosas staff members")
        return waiters

    def _generate_default_availability_slots(self, role: str, index: int) -> List[dict]:
        """Generate realistic availability slots by role."""
        patterns: List[List[dict]] = []

        if role == "server":
            patterns = [
                [{"days": [0, 1, 2, 3, 5], "start": time(10, 0), "end": time(16, 0), "preferred_days": [5]}],
                [{"days": [1, 2, 3, 4, 5, 6], "start": time(16, 0), "end": time(23, 0), "preferred_days": [4, 5]}],
                [{"days": [5, 6], "start": time(9, 0), "end": time(15, 0), "preferred_days": [5, 6]}],
                [{"days": [0, 1, 2, 3, 4], "start": time(11, 0), "end": time(19, 0), "preferred_days": [2, 3]}],
                [{"days": [3, 4, 5, 6], "start": time(14, 0), "end": time(22, 0), "preferred_days": [4, 5]}],
            ]
        elif role == "bartender":
            patterns = [
                [{"days": [3, 4, 5, 6], "start": time(16, 0), "end": time(23, 59), "preferred_days": [4, 5]}],
                [{"days": [2, 3, 4, 5, 6], "start": time(15, 0), "end": time(23, 0), "preferred_days": [4, 5]}],
                [{"days": [4, 5, 6], "start": time(14, 0), "end": time(23, 59), "preferred_days": [5, 6]}],
            ]
        elif role == "host":
            patterns = [
                [{"days": [0, 1, 2, 3], "start": time(10, 0), "end": time(16, 0), "preferred_days": [1, 2]}],
                [{"days": [3, 4, 5, 6], "start": time(16, 0), "end": time(22, 0), "preferred_days": [4, 5]}],
                [{"days": [4, 5, 6], "start": time(9, 0), "end": time(15, 0), "preferred_days": [5, 6]}],
            ]
        elif role == "busser":
            patterns = [
                [{"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "preferred_days": [1, 2]}],
                [{"days": [3, 4, 5, 6], "start": time(17, 0), "end": time(22, 0), "preferred_days": [4, 5]}],
                [{"days": [5, 6], "start": time(9, 0), "end": time(15, 0), "preferred_days": [5, 6]}],
                [{"days": [1, 2, 3, 4, 5], "start": time(12, 0), "end": time(18, 0), "preferred_days": [3, 4]}],
            ]
        elif role == "runner":
            patterns = [
                [{"days": [3, 4, 5, 6], "start": time(17, 0), "end": time(22, 0), "preferred_days": [4, 5]}],
                [{"days": [4, 5, 6], "start": time(18, 0), "end": time(23, 0), "preferred_days": [5, 6]}],
                [{"days": [2, 3, 4, 5, 6], "start": time(16, 0), "end": time(21, 0), "preferred_days": [4, 5]}],
            ]
        elif role == "chef":
            patterns = [
                [{"days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(16, 0), "preferred_days": [0, 1]}],
                [{"days": [2, 3, 4, 5, 6], "start": time(14, 0), "end": time(22, 0), "preferred_days": [4, 5]}],
                [{"days": [4, 5, 6], "start": time(10, 0), "end": time(18, 0), "preferred_days": [5, 6]}],
            ]
        else:
            patterns = [[{"days": [0, 1, 2, 3, 4], "start": time(10, 0), "end": time(18, 0), "preferred_days": [2, 3]}]]

        return patterns[index % len(patterns)]

    def _get_mimosas_availability_slots(self, waiter: Waiter, index: int) -> List[dict]:
        """Resolve availability slots for a waiter, with intelligent defaults."""
        avail_data = MIMOSAS_STAFF_AVAILABILITY.get(waiter.name)
        if avail_data:
            if "slots" in avail_data:
                slots = avail_data["slots"]
            else:
                slots = [{
                    "days": avail_data["days"],
                    "start": avail_data["start"],
                    "end": avail_data["end"],
                    "preferred_days": avail_data.get("preferred_days", []),
                }]
        else:
            slots = self._generate_default_availability_slots(waiter.role, index)

        service_roles = {"server", "bartender", "host", "busser", "runner"}
        if waiter.role in service_roles and all(slot["end"] <= time(16, 0) for slot in slots):
            if waiter.role == "bartender":
                evening = {"days": slots[0]["days"], "start": time(16, 0), "end": time(23, 59), "preferred_days": slots[0].get("preferred_days", [])}
            elif waiter.role == "runner":
                evening = {"days": slots[0]["days"], "start": time(17, 0), "end": time(22, 0), "preferred_days": slots[0].get("preferred_days", [])}
            else:
                evening = {"days": slots[0]["days"], "start": time(17, 0), "end": time(22, 0), "preferred_days": slots[0].get("preferred_days", [])}
            slots.append(evening)

        return slots

    def _generate_default_preferences(
        self,
        waiter: Waiter,
        index: int,
        section_map: dict,
    ) -> dict:
        """Generate default scheduling preferences for staff."""
        role = waiter.role
        sections = list(section_map.keys())
        preferred_sections = []
        if sections and role in ("server", "bartender"):
            preferred_sections = [sections[index % len(sections)]]

        if role in ("server", "bartender"):
            full_time = index % 3 != 0
            return {
                "max_shifts": 5 if full_time else 3,
                "max_hours": 40 if full_time else 24,
                "min_hours": 28 if full_time else 12,
                "avoid_clopening": index % 2 == 0,
                "preferred_sections": preferred_sections,
                "shift_types": ["morning", "evening", "closing"] if full_time else ["morning", "closing"],
            }
        elif role in ("host", "busser", "runner"):
            return {
                "max_shifts": 4,
                "max_hours": 28,
                "min_hours": 12,
                "avoid_clopening": True,
                "preferred_sections": preferred_sections,
                "shift_types": ["morning", "evening"],
            }
        else:
            return {
                "max_shifts": 5,
                "max_hours": 40,
                "min_hours": 20,
                "avoid_clopening": False,
                "preferred_sections": preferred_sections,
                "shift_types": ["morning", "evening"],
            }

    async def _create_mimosas_staff_availability(
        self, restaurant_id: UUID, waiters: List[Waiter]
    ) -> None:
        """Create detailed staff availability for Mimosas (full service hours)."""
        for index, waiter in enumerate(waiters):
            slots = self._get_mimosas_availability_slots(waiter, index)
            for slot in slots:
                available_days = slot["days"]
                start_time = slot["start"]
                end_time = slot["end"]
                preferred_days = slot.get("preferred_days", [])

                for day in available_days:
                    avail_type = "preferred" if day in preferred_days else "available"
                    availability = StaffAvailability(
                        waiter_id=waiter.id,
                        restaurant_id=restaurant_id,
                        day_of_week=day,
                        start_time=start_time,
                        end_time=end_time,
                        availability_type=avail_type,
                    )
                    self.session.add(availability)

        await self.session.flush()

    async def _create_mimosas_staff_preferences(
        self, restaurant_id: UUID, waiters: List[Waiter], section_map: dict
    ) -> None:
        """Create staff scheduling preferences for all Mimosas staff."""
        for index, waiter in enumerate(waiters):
            pref_data = MIMOSAS_STAFF_PREFERENCES.get(waiter.name)
            if not pref_data:
                pref_data = self._generate_default_preferences(waiter, index, section_map)

            # Get preferred sections by name and convert to IDs
            section_names = pref_data.get("preferred_sections", [])
            preferred_section_ids = []
            for section_name in section_names:
                section = section_map.get(section_name)
                if section:
                    preferred_section_ids.append(str(section.id))

            preference = StaffPreference(
                waiter_id=waiter.id,
                restaurant_id=restaurant_id,
                preferred_roles=[waiter.role],
                preferred_shift_types=pref_data.get("shift_types", ["morning", "closing"]),
                preferred_sections=preferred_section_ids,
                max_shifts_per_week=pref_data.get("max_shifts", 5),
                max_hours_per_week=pref_data.get("max_hours", 40),
                min_hours_per_week=pref_data.get("min_hours", 20),
                avoid_clopening=pref_data.get("avoid_clopening", False),
            )
            self.session.add(preference)

        await self.session.flush()

    async def _create_mimosas_staffing_requirements(self, restaurant_id: UUID) -> None:
        """Create comprehensive staffing requirements for a full-service restaurant."""
        requirements = [
            # ==================== MON-THU LUNCH (11am-3pm) ====================
            {"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "role": "server", "min": 3, "max": 4, "prime": False},
            {"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "role": "bartender", "min": 1, "max": 1, "prime": False},
            {"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "role": "host", "min": 1, "max": 1, "prime": False},
            {"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "role": "busser", "min": 1, "max": 1, "prime": False},
            {"days": [0, 1, 2, 3], "start": time(11, 0), "end": time(15, 0), "role": "runner", "min": 1, "max": 1, "prime": False},

            # ==================== MON-THU DINNER (5pm-10pm) ====================
            {"days": [0, 1, 2, 3], "start": time(17, 0), "end": time(22, 0), "role": "server", "min": 4, "max": 5, "prime": True},
            {"days": [0, 1, 2, 3], "start": time(17, 0), "end": time(22, 0), "role": "bartender", "min": 1, "max": 2, "prime": True},
            {"days": [0, 1, 2, 3], "start": time(17, 0), "end": time(22, 0), "role": "host", "min": 1, "max": 1, "prime": True},
            {"days": [0, 1, 2, 3], "start": time(17, 0), "end": time(22, 0), "role": "busser", "min": 1, "max": 1, "prime": True},
            {"days": [0, 1, 2, 3], "start": time(17, 0), "end": time(22, 0), "role": "runner", "min": 1, "max": 2, "prime": True},

            # ==================== FRIDAY LUNCH (11am-3pm) ====================
            {"days": [4], "start": time(11, 0), "end": time(15, 0), "role": "server", "min": 4, "max": 5, "prime": True},
            {"days": [4], "start": time(11, 0), "end": time(15, 0), "role": "bartender", "min": 1, "max": 2, "prime": True},
            {"days": [4], "start": time(11, 0), "end": time(15, 0), "role": "host", "min": 1, "max": 1, "prime": True},
            {"days": [4], "start": time(11, 0), "end": time(15, 0), "role": "busser", "min": 1, "max": 2, "prime": True},
            {"days": [4], "start": time(11, 0), "end": time(15, 0), "role": "runner", "min": 1, "max": 1, "prime": True},

            # ==================== FRIDAY DINNER (5pm-11pm) ====================
            {"days": [4], "start": time(17, 0), "end": time(23, 0), "role": "server", "min": 6, "max": 7, "prime": True},
            {"days": [4], "start": time(17, 0), "end": time(23, 0), "role": "bartender", "min": 2, "max": 3, "prime": True},
            {"days": [4], "start": time(17, 0), "end": time(23, 0), "role": "host", "min": 1, "max": 1, "prime": True},
            {"days": [4], "start": time(17, 0), "end": time(23, 0), "role": "busser", "min": 2, "max": 2, "prime": True},
            {"days": [4], "start": time(17, 0), "end": time(23, 0), "role": "runner", "min": 2, "max": 2, "prime": True},

            # ==================== SATURDAY BRUNCH (9am-3pm) ====================
            {"days": [5], "start": time(9, 0), "end": time(15, 0), "role": "server", "min": 5, "max": 6, "prime": True},
            {"days": [5], "start": time(9, 0), "end": time(15, 0), "role": "bartender", "min": 2, "max": 2, "prime": True},
            {"days": [5], "start": time(9, 0), "end": time(15, 0), "role": "host", "min": 2, "max": 2, "prime": True},
            {"days": [5], "start": time(9, 0), "end": time(15, 0), "role": "busser", "min": 1, "max": 1, "prime": True},
            {"days": [5], "start": time(9, 0), "end": time(15, 0), "role": "runner", "min": 1, "max": 1, "prime": True},

            # ==================== SATURDAY DINNER (5pm-11pm) ====================
            {"days": [5], "start": time(17, 0), "end": time(23, 0), "role": "server", "min": 7, "max": 8, "prime": True},
            {"days": [5], "start": time(17, 0), "end": time(23, 0), "role": "bartender", "min": 3, "max": 3, "prime": True},
            {"days": [5], "start": time(17, 0), "end": time(23, 0), "role": "host", "min": 2, "max": 2, "prime": True},
            {"days": [5], "start": time(17, 0), "end": time(23, 0), "role": "busser", "min": 2, "max": 2, "prime": True},
            {"days": [5], "start": time(17, 0), "end": time(23, 0), "role": "runner", "min": 2, "max": 2, "prime": True},

            # ==================== SUNDAY BRUNCH (9am-3pm) ====================
            {"days": [6], "start": time(9, 0), "end": time(15, 0), "role": "server", "min": 5, "max": 6, "prime": True},
            {"days": [6], "start": time(9, 0), "end": time(15, 0), "role": "bartender", "min": 2, "max": 2, "prime": True},
            {"days": [6], "start": time(9, 0), "end": time(15, 0), "role": "host", "min": 2, "max": 2, "prime": True},
            {"days": [6], "start": time(9, 0), "end": time(15, 0), "role": "busser", "min": 1, "max": 1, "prime": True},
            {"days": [6], "start": time(9, 0), "end": time(15, 0), "role": "runner", "min": 1, "max": 1, "prime": True},

            # ==================== SUNDAY DINNER (5pm-9pm) ====================
            {"days": [6], "start": time(17, 0), "end": time(21, 0), "role": "server", "min": 4, "max": 5, "prime": True},
            {"days": [6], "start": time(17, 0), "end": time(21, 0), "role": "bartender", "min": 2, "max": 2, "prime": True},
            {"days": [6], "start": time(17, 0), "end": time(21, 0), "role": "host", "min": 1, "max": 1, "prime": True},
            {"days": [6], "start": time(17, 0), "end": time(21, 0), "role": "busser", "min": 1, "max": 1, "prime": True},
            {"days": [6], "start": time(17, 0), "end": time(21, 0), "role": "runner", "min": 1, "max": 1, "prime": True},
        ]

        for req in requirements:
            for day in req["days"]:
                staffing = StaffingRequirements(
                    restaurant_id=restaurant_id,
                    day_of_week=day,
                    start_time=req["start"],
                    end_time=req["end"],
                    role=req["role"],
                    min_staff=req["min"],
                    max_staff=req.get("max"),
                    is_prime_shift=req["prime"],
                )
                self.session.add(staffing)

        await self.session.flush()

    async def _create_mimosas_kitchen_stations(self, restaurant_id: UUID) -> List[KitchenStation]:
        """Create Mimosas kitchen stations."""
        stations = []
        for station_data in MIMOSAS_KITCHEN_STATIONS:
            station = KitchenStation(
                restaurant_id=restaurant_id,
                name=station_data["name"],
                max_concurrent_orders=station_data["max_concurrent_orders"],
                is_active=True,
            )
            self.session.add(station)
            stations.append(station)
        await self.session.flush()
        return stations

    async def _create_mimosas_ingredients(self, restaurant_id: UUID) -> List[Ingredient]:
        """Create Mimosas ingredients."""
        ingredients = []
        for ing_data in MIMOSAS_INGREDIENTS:
            ingredient = Ingredient(
                restaurant_id=restaurant_id,
                name=ing_data["name"],
                category=ing_data["category"],
                unit=ing_data["unit"],
                cost_per_unit=Decimal(str(ing_data["cost_per_unit"])),
                par_level=ing_data["par_level"],
                current_stock=Decimal(str(ing_data["par_level"] * random.uniform(0.1, 0.95))),  # Varied stock levels
                supplier=ing_data["supplier"],
            )
            self.session.add(ingredient)
            ingredients.append(ingredient)
        await self.session.flush()
        return ingredients

    async def _create_mimosas_menu(self, restaurant_id: UUID) -> List[MenuItem]:
        """Create Mimosas menu items."""
        menu_items = []
        for item_data in MIMOSAS_MENU_ITEMS:
            menu_item = MenuItem(
                restaurant_id=restaurant_id,
                name=item_data["name"],
                category=item_data["category"],
                price=Decimal(str(item_data["price"])),
                cost=Decimal(str(item_data["cost"])),
                is_available=True,
            )
            self.session.add(menu_item)
            menu_items.append(menu_item)
        await self.session.flush()
        return menu_items

    async def _create_mimosas_sample_data(
        self,
        restaurant_id: UUID,
        waiters: List[Waiter],
        menu_items: List[MenuItem],
        days_back: int = 60,
    ) -> dict:
        """
        Create 60 days of sample shifts, visits, and order items.

        This generates realistic data for menu scoring to work properly.
        """
        import random

        result = {
            "shifts_created": 0,
            "visits_created": 0,
            "order_items_created": 0,
        }

        # Get tables
        tables = await self._get_restaurant_tables(restaurant_id)
        if not tables:
            logger.warning("No tables found for Mimosas, skipping sample data")
            return result

        # Build popularity weights for menu items
        item_weights = []
        for item in menu_items:
            weight = MIMOSAS_ITEM_POPULARITY.get(item.name, 1.0)
            item_weights.append((item, weight))

        # Filter to performance-tracked waiters only (servers, bartenders) for order data
        tracked_waiters = [w for w in waiters if w.role in ("server", "bartender")]

        if not tracked_waiters:
            logger.warning("No servers or bartenders found for sample data")
            return result

        waiter_slots = {}
        for idx, waiter in enumerate(tracked_waiters):
            waiter_slots[waiter.id] = self._get_mimosas_availability_slots(waiter, idx)

        for day_offset in range(days_back, 0, -1):
            shift_date = datetime.utcnow() - timedelta(days=day_offset)
            day_of_week = shift_date.weekday()
            is_friday = day_of_week == 4
            is_weekend = day_of_week in (5, 6)

            for waiter in tracked_waiters:
                slots = waiter_slots.get(waiter.id, [])
                if not any(day_of_week in slot["days"] for slot in slots):
                    continue

                work_probability = 0.75 if is_weekend else (0.7 if is_friday else 0.55)
                if random.random() > work_probability:
                    continue

                if is_weekend:
                    shift_type = random.choices(["brunch", "dinner"], weights=[0.45, 0.55])[0]
                elif is_friday:
                    shift_type = random.choices(["lunch", "dinner"], weights=[0.4, 0.6])[0]
                else:
                    shift_type = random.choices(["lunch", "dinner"], weights=[0.5, 0.5])[0]

                if shift_type == "brunch":
                    start_hour, end_hour = 9, 15
                elif shift_type == "lunch":
                    start_hour, end_hour = 11, 15
                else:
                    start_hour = 17
                    end_hour = 23 if day_of_week in (4, 5) else (21 if day_of_week == 6 else 22)

                shift = Shift(
                    restaurant_id=restaurant_id,
                    waiter_id=waiter.id,
                    clock_in=shift_date.replace(hour=start_hour, minute=0, second=0, microsecond=0),
                    clock_out=shift_date.replace(hour=end_hour, minute=0, second=0, microsecond=0),
                    status="ended",
                    tables_served=0,
                    total_covers=0,
                    total_tips=Decimal("0"),
                    total_sales=Decimal("0"),
                )
                self.session.add(shift)
                await self.session.flush()
                result["shifts_created"] += 1

                if shift_type in ("brunch", "lunch"):
                    visit_range = (10, 20) if is_weekend else (6, 12)
                else:
                    visit_range = (16, 28) if (is_weekend or is_friday) else (10, 18)

                num_visits = random.randint(*visit_range)
                for _ in range(num_visits):
                    table = random.choice(tables)
                    party_size = random.randint(2, min(6, table.capacity))

                    if shift_type == "dinner":
                        peak_hours = [18, 19, 20, 21]
                        hour = random.choice(peak_hours)
                        if is_friday or day_of_week == 5:
                            hour = random.choice([19, 20, 21])
                    else:
                        hour = random.randint(start_hour + 1, min(end_hour - 1, start_hour + 4))

                    seated_time = shift_date.replace(hour=hour, minute=random.randint(0, 45))
                    cleared_time = seated_time + timedelta(minutes=random.randint(45, 95))

                    visit = Visit(
                        restaurant_id=restaurant_id,
                        table_id=table.id,
                        waiter_id=waiter.id,
                        shift_id=shift.id,
                        party_size=party_size,
                        seated_at=seated_time,
                        cleared_at=cleared_time,
                        subtotal=Decimal("0"),
                        tax=Decimal("0"),
                        total=Decimal("0"),
                        tip=Decimal("0"),
                    )
                    self.session.add(visit)
                    await self.session.flush()
                    result["visits_created"] += 1

                    # Create order items (1-4 per person in party)
                    num_orders = random.randint(party_size, party_size * 2)
                    visit_subtotal = Decimal("0")

                    for _ in range(num_orders):
                        # Weighted random selection
                        total_weight = sum(w for _, w in item_weights)
                        r = random.uniform(0, total_weight)
                        cumulative = 0
                        selected_item = menu_items[0]
                        for item, weight in item_weights:
                            cumulative += weight
                            if r <= cumulative:
                                selected_item = item
                                break

                        quantity = random.randint(1, 2)
                        unit_price = selected_item.price
                        total_price = unit_price * quantity

                        order_item = OrderItem(
                            visit_id=visit.id,
                            menu_item_id=selected_item.id,
                            quantity=quantity,
                            unit_price=unit_price,
                            total_price=total_price,
                        )
                        self.session.add(order_item)
                        visit_subtotal += total_price
                        result["order_items_created"] += 1

                    # Update visit totals
                    tax = visit_subtotal * Decimal("0.0825")
                    total = visit_subtotal + tax
                    tip_pct = Decimal(str(random.uniform(0.18, 0.22)))
                    tip = visit_subtotal * tip_pct

                    visit.subtotal = visit_subtotal
                    visit.tax = tax
                    visit.total = total
                    visit.tip = tip
                    visit.tip_percentage = tip_pct * 100

                    # Update shift totals
                    shift.tables_served += 1
                    shift.total_covers += party_size
                    shift.total_tips += tip
                    shift.total_sales += visit_subtotal

        await self.session.flush()

        logger.info(
            f"Created Mimosas sample data: {result['shifts_created']} shifts, "
            f"{result['visits_created']} visits, {result['order_items_created']} order items"
        )

        return result
