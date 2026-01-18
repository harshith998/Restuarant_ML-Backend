# Frontend API Integration Guide

Complete guide for integrating with the Restaurant Intelligence Platform API.

## Table of Contents
1. [Getting Started](#getting-started)
2. [Switching Between Restaurants](#switching-between-restaurants)
3. [Restaurant API](#restaurant-api)
4. [Sections & Tables API](#sections--tables-api)
5. [Waiters API](#waiters-api)
6. [Shifts API](#shifts-api)
7. [Visits API](#visits-api)
8. [Menu Analytics API](#menu-analytics-api)
9. [Routing API](#routing-api)
10. [Waitlist API](#waitlist-api)
11. [Inventory API](#inventory-api)
12. [Scheduling API](#scheduling-api)
13. [Analytics API](#analytics-api)

---

## Getting Started

### Base URL
```
http://localhost:8000/api/v1
```

### Available Demo Restaurants

On startup, the system creates two demo restaurants:

| Restaurant | Description | Use Case |
|------------|-------------|----------|
| **The Golden Fork** | Basic restaurant with waiters, sections, tables | Simple testing |
| **Mimosas** | Full brunch restaurant with 41 menu items, 60 days of order history, complete staff | Menu analytics, scoring, 86 testing |

### First Steps

1. **Get list of restaurants:**
```bash
curl http://localhost:8000/api/v1/restaurants
```

2. **Store the restaurant_id** you want to work with
3. **Use that ID in all subsequent API calls**

---

## Switching Between Restaurants

The frontend should allow users to switch between restaurants. Here's how:

### 1. Fetch All Restaurants
```javascript
const response = await fetch('/api/v1/restaurants');
const restaurants = await response.json();

// Returns:
// [
//   { "id": "uuid-1", "name": "The Golden Fork", ... },
//   { "id": "uuid-2", "name": "Mimosas", ... }
// ]
```

### 2. Store Selected Restaurant
```javascript
// In your app state/context
const [currentRestaurant, setCurrentRestaurant] = useState(null);

// When user selects a restaurant
const switchRestaurant = (restaurant) => {
  setCurrentRestaurant(restaurant);
  localStorage.setItem('selectedRestaurantId', restaurant.id);
};
```

### 3. Use Restaurant ID in All Calls
```javascript
// All API calls use the current restaurant ID
const getWaiters = async () => {
  const res = await fetch(`/api/v1/restaurants/${currentRestaurant.id}/waiters`);
  return res.json();
};

const getMenuRankings = async () => {
  const res = await fetch(`/api/v1/restaurants/${currentRestaurant.id}/menu/rankings/top`);
  return res.json();
};
```

### 4. Restaurant Selector Component Example
```jsx
function RestaurantSelector({ restaurants, current, onSelect }) {
  return (
    <select
      value={current?.id || ''}
      onChange={(e) => onSelect(restaurants.find(r => r.id === e.target.value))}
    >
      <option value="">Select Restaurant</option>
      {restaurants.map(r => (
        <option key={r.id} value={r.id}>{r.name}</option>
      ))}
    </select>
  );
}
```

### Why Use Mimosas for Testing?
- **41 real menu items** from an actual restaurant menu
- **60 days of order history** with ~1000 visits and ~3000 order items
- **Menu scoring works** - items have realistic demand patterns
- **86 recommendations available** - low-performing items flagged
- **Full staff setup** - servers, bartender, host with availability

---

## Restaurant API

### List All Restaurants
```http
GET /api/v1/restaurants
```

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Mimosas",
    "timezone": "America/Los_Angeles",
    "config": {
      "routing": { "mode": "section", "max_tables_per_waiter": 4 },
      "alerts": { "understaffed_threshold": 1.2 }
    },
    "created_at": "2024-01-15T10:00:00Z"
  }
]
```

### Get Single Restaurant
```http
GET /api/v1/restaurants/{restaurant_id}
```

### Create Restaurant
```http
POST /api/v1/restaurants
Content-Type: application/json

{
  "name": "My Restaurant",
  "timezone": "America/New_York"
}
```

### Update Restaurant
```http
PATCH /api/v1/restaurants/{restaurant_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "config": { "routing": { "mode": "rotation" } }
}
```

---

## Sections & Tables API

### Get Sections
```http
GET /api/v1/restaurants/{restaurant_id}/sections
```

**Response:**
```json
[
  { "id": "uuid", "name": "Main Dining", "is_active": true },
  { "id": "uuid", "name": "Outdoor Patio", "is_active": true },
  { "id": "uuid", "name": "Bar", "is_active": true }
]
```

### Get Tables
```http
GET /api/v1/restaurants/{restaurant_id}/tables
```

**Response:**
```json
[
  {
    "id": "uuid",
    "table_number": "M1",
    "section_id": "uuid",
    "capacity": 4,
    "table_type": "table",
    "state": "clean",
    "is_active": true
  }
]
```

### Update Table State
```http
PATCH /api/v1/restaurants/{restaurant_id}/tables/{table_id}/state
Content-Type: application/json

{
  "state": "occupied",
  "source": "host"
}
```

**Table States:** `clean`, `occupied`, `dirty`, `unavailable`

---

## Waiters API

### Get All Waiters
```http
GET /api/v1/restaurants/{restaurant_id}/waiters
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Maria Garcia",
    "email": "maria@mimosas.com",
    "role": "server",
    "tier": "strong",
    "composite_score": 82.0,
    "total_shifts": 120,
    "total_covers": 2450,
    "total_tips": 12500.00,
    "is_active": true
  }
]
```

### Get Waiter by ID
```http
GET /api/v1/restaurants/{restaurant_id}/waiters/{waiter_id}
```

### Create Waiter
```http
POST /api/v1/restaurants/{restaurant_id}/waiters
Content-Type: application/json

{
  "name": "New Server",
  "email": "new@restaurant.com",
  "role": "server"
}
```

**Roles:** `server`, `bartender`, `host`, `busser`, `runner`

---

## Shifts API

### Get Active Shifts
```http
GET /api/v1/restaurants/{restaurant_id}/shifts?status=active
```

### Get Shift Details
```http
GET /api/v1/restaurants/{restaurant_id}/shifts/{shift_id}
```

**Response:**
```json
{
  "id": "uuid",
  "waiter_id": "uuid",
  "clock_in": "2024-01-15T07:00:00Z",
  "clock_out": null,
  "status": "active",
  "tables_served": 5,
  "total_covers": 18,
  "total_tips": 245.50,
  "total_sales": 1250.00
}
```

### Clock In
```http
POST /api/v1/restaurants/{restaurant_id}/shifts
Content-Type: application/json

{
  "waiter_id": "uuid"
}
```

### Clock Out
```http
POST /api/v1/restaurants/{restaurant_id}/shifts/{shift_id}/clock-out
```

---

## Visits API

### Get Active Visits
```http
GET /api/v1/restaurants/{restaurant_id}/visits?active=true
```

### Get Visit Details
```http
GET /api/v1/restaurants/{restaurant_id}/visits/{visit_id}
```

**Response:**
```json
{
  "id": "uuid",
  "table_id": "uuid",
  "waiter_id": "uuid",
  "party_size": 4,
  "seated_at": "2024-01-15T12:30:00Z",
  "cleared_at": null,
  "subtotal": 85.50,
  "tax": 7.05,
  "total": 92.55,
  "tip": 17.10,
  "tip_percentage": 20.0
}
```

### Clear Visit (Party Left)
```http
POST /api/v1/restaurants/{restaurant_id}/visits/{visit_id}/clear
```

### Transfer Visit to Another Waiter
```http
POST /api/v1/restaurants/{restaurant_id}/visits/{visit_id}/transfer?new_waiter_id={uuid}
```

---

## Menu Analytics API

### Pricing Recommendations
```http
GET /api/v1/restaurants/{restaurant_id}/menu/pricing-recommendations?lookback_days=30
```

**Response:**
```json
{
  "restaurant_id": "uuid",
  "analysis_period_days": 30,
  "total_recommendations": 5,
  "recommendations": [
    {
      "item_id": "uuid",
      "item_name": "French Beignets",
      "current_price": 9.84,
      "suggested_price": 11.02,
      "action": "increase",
      "reason": "High demand with low profit margin",
      "current_margin": 74.6,
      "demand_score": 8.5
    }
  ]
}
```

### Top Sellers
```http
GET /api/v1/restaurants/{restaurant_id}/menu/top-sellers?period_days=7&limit=10
```

### Top Ranked Items (by Score)
```http
GET /api/v1/restaurants/{restaurant_id}/menu/rankings/top?lookback_days=30&limit=10
```

**Response:**
```json
{
  "restaurant_id": "uuid",
  "analysis_period_days": 30,
  "total_items": 10,
  "items": [
    {
      "id": "uuid",
      "name": "Fried Lobster & Waffles",
      "category": "Signature Breakfast",
      "price": 22.79,
      "cost": 10.50,
      "is_available": true,
      "combined_score": 87.5,
      "demand_score": 85.0,
      "margin_pct": 53.9,
      "orders_per_day": 6.2,
      "times_ordered": 186,
      "rank": 1
    }
  ]
}
```

### Bottom Ranked Items
```http
GET /api/v1/restaurants/{restaurant_id}/menu/rankings/bottom?lookback_days=30&limit=10
```

### 86 Recommendations
```http
GET /api/v1/restaurants/{restaurant_id}/menu/86-recommendations?score_threshold=25.0
```

**Response:**
```json
{
  "restaurant_id": "uuid",
  "analysis_period_days": 30,
  "score_threshold": 25.0,
  "total_recommendations": 2,
  "recommendations": [
    {
      "id": "uuid",
      "name": "Let Me Do Me!",
      "category": "For The Love Of Eggs",
      "price": 12.00,
      "combined_score": 18.5,
      "orders_per_day": 0.3,
      "reason": "Very low demand (0.3 orders/day)"
    }
  ]
}
```

### 86 an Item
```http
POST /api/v1/restaurants/{restaurant_id}/menu/items/{item_id}/86
```

**Response:**
```json
{
  "success": true,
  "item_id": "uuid",
  "name": "Let Me Do Me!",
  "is_available": false,
  "message": "'Let Me Do Me!' has been 86'd"
}
```

### Un-86 an Item
```http
POST /api/v1/restaurants/{restaurant_id}/menu/items/{item_id}/un-86
```

### List All 86'd Items
```http
GET /api/v1/restaurants/{restaurant_id}/menu/items/86d
```

---

## Routing API

### Get Routing Suggestion
```http
POST /api/v1/restaurants/{restaurant_id}/routing/suggest
Content-Type: application/json

{
  "party_size": 4,
  "preference": "booth"
}
```

**Response:**
```json
{
  "table": {
    "id": "uuid",
    "table_number": "B1",
    "capacity": 4
  },
  "waiter": {
    "id": "uuid",
    "name": "Maria Garcia",
    "tier": "strong"
  },
  "score": 85.5,
  "reasoning": "Best match for party size with available strong-tier server"
}
```

### Seat Party
```http
POST /api/v1/restaurants/{restaurant_id}/routing/seat?table_id={uuid}&waiter_id={uuid}&party_size=4
```

### Switch Routing Mode
```http
POST /api/v1/restaurants/{restaurant_id}/routing/mode?mode=rotation
```

**Modes:** `section`, `rotation`

---

## Waitlist API

### Get Waitlist
```http
GET /api/v1/restaurants/{restaurant_id}/waitlist
```

### Add to Waitlist
```http
POST /api/v1/restaurants/{restaurant_id}/waitlist
Content-Type: application/json

{
  "party_name": "Johnson",
  "party_size": 4,
  "phone": "555-1234",
  "preference": "booth"
}
```

### Remove from Waitlist
```http
DELETE /api/v1/restaurants/{restaurant_id}/waitlist/{entry_id}
```

### Seat from Waitlist
```http
POST /api/v1/restaurants/{restaurant_id}/waitlist/{entry_id}/seat?table_id={uuid}&waiter_id={uuid}
```

---

## Inventory API

### Get Shopping List
```http
GET /api/v1/restaurants/{restaurant_id}/inventory/shopping-list?forecast_days=7
```

### Get Ingredient Status
```http
GET /api/v1/restaurants/{restaurant_id}/inventory/ingredients
```

### Update Stock Level
```http
PATCH /api/v1/restaurants/{restaurant_id}/inventory/ingredients/{ingredient_id}
Content-Type: application/json

{
  "current_stock": 150
}
```

---

## Scheduling API

### Get Staff Availability
```http
GET /api/v1/restaurants/{restaurant_id}/scheduling/availability?waiter_id={uuid}
```

### Get Staffing Requirements
```http
GET /api/v1/restaurants/{restaurant_id}/scheduling/requirements
```

### Generate Schedule
```http
POST /api/v1/restaurants/{restaurant_id}/scheduling/generate
Content-Type: application/json

{
  "week_start_date": "2024-01-15"
}
```

### Get Schedule
```http
GET /api/v1/restaurants/{restaurant_id}/scheduling/schedules?week_start_date=2024-01-15
```

---

## Analytics API

### Get Restaurant Dashboard
```http
GET /api/v1/restaurants/{restaurant_id}/analytics/dashboard
```

### Get Waiter Performance
```http
GET /api/v1/restaurants/{restaurant_id}/analytics/waiters?period_days=30
```

### Get Revenue Analytics
```http
GET /api/v1/restaurants/{restaurant_id}/analytics/revenue?period_days=30
```

---

## Error Handling

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource doesn't exist |
| 422 | Validation Error - Check request body |
| 500 | Server Error - Contact support |

---

## Frontend Integration Tips

### 1. Score Color Coding
```javascript
const getScoreColor = (score) => {
  if (score >= 70) return 'green';
  if (score >= 40) return 'yellow';
  return 'red';
};
```

### 2. 86 Confirmation Flow
```javascript
const handle86Item = async (itemId, itemName) => {
  const confirmed = await showConfirmDialog(
    `Are you sure you want to 86 "${itemName}"?`
  );
  if (confirmed) {
    await fetch(`/api/v1/restaurants/${restaurantId}/menu/items/${itemId}/86`, {
      method: 'POST'
    });
    refreshMenuList();
  }
};
```

### 3. Polling for Real-time Updates
```javascript
// Poll active visits every 30 seconds
useEffect(() => {
  const interval = setInterval(async () => {
    const visits = await fetchActiveVisits();
    setActiveVisits(visits);
  }, 30000);
  return () => clearInterval(interval);
}, [restaurantId]);
```

### 4. Restaurant Context Provider
```jsx
const RestaurantContext = createContext(null);

export function RestaurantProvider({ children }) {
  const [restaurant, setRestaurant] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedId = localStorage.getItem('selectedRestaurantId');
    if (savedId) {
      fetchRestaurant(savedId).then(setRestaurant);
    }
    setLoading(false);
  }, []);

  return (
    <RestaurantContext.Provider value={{ restaurant, setRestaurant, loading }}>
      {children}
    </RestaurantContext.Provider>
  );
}
```

---

## Quick Reference: Mimosas Menu Categories

| Category | Items | Price Range |
|----------|-------|-------------|
| Great For Sharing | 2 | $9.84 - $11.78 |
| Lighten Up | 1 | $13.58 |
| Benny Sends Me | 5 | $15.79 - $18.70 |
| Shrimp & Grits | 2 | $18.32 - $18.99 |
| Farm Fresh Classics | 3 | $13.79 - $19.78 |
| Fully Worth The Calories | 6 | $15.58 - $16.79 |
| Signature Breakfast | 9 | $12.99 - $22.79 |
| For The Love Of Eggs | 7 | $12.00 - $20.79 |
| Skillets | 4 | $15.99 - $17.59 |

**Total: 41 menu items**

---

## Need Help?

- Check `/api/v1/docs` for interactive Swagger documentation
- Review error responses for specific guidance
- Contact backend team for API issues
