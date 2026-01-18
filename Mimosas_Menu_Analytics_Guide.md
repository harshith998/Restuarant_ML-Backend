# Mimosas Restaurant & Menu Analytics Guide

New features for menu scoring, 86 management, and the Mimosas demo restaurant.

---

## What's New

### 1. Mimosas Demo Restaurant
A fully-populated brunch restaurant with 60 days of order history for testing menu analytics.

### 2. Menu Ranking Endpoints
- `/menu/rankings/top` - Highest scoring menu items
- `/menu/rankings/bottom` - Lowest scoring menu items

### 3. 86 Management Endpoints
- `/menu/86-recommendations` - Items recommended to remove
- `/menu/items/{id}/86` - Mark item unavailable
- `/menu/items/{id}/un-86` - Restore item
- `/menu/items/86d` - List all 86'd items

---

## Switching Between Restaurants

Two restaurants are seeded on startup:

| Restaurant | ID | Description |
|------------|-----|-------------|
| The Golden Fork | Get from `/api/v1/restaurants` | Basic restaurant |
| **Mimosas** | Get from `/api/v1/restaurants` | Full menu + 60 days data |

### Frontend Implementation

```javascript
// 1. Fetch restaurants on app load
const [restaurants, setRestaurants] = useState([]);
const [currentRestaurant, setCurrentRestaurant] = useState(null);

useEffect(() => {
  fetch('/api/v1/restaurants')
    .then(res => res.json())
    .then(data => {
      setRestaurants(data);
      // Auto-select Mimosas for menu testing
      const mimosas = data.find(r => r.name === 'Mimosas');
      if (mimosas) setCurrentRestaurant(mimosas);
    });
}, []);

// 2. Store selection in localStorage
const switchRestaurant = (restaurant) => {
  setCurrentRestaurant(restaurant);
  localStorage.setItem('restaurantId', restaurant.id);
};

// 3. Use in all API calls
const fetchMenuRankings = async () => {
  const res = await fetch(
    `/api/v1/restaurants/${currentRestaurant.id}/menu/rankings/top`
  );
  return res.json();
};
```

### Restaurant Selector Component

```jsx
function RestaurantPicker({ restaurants, current, onChange }) {
  return (
    <select
      value={current?.id || ''}
      onChange={e => onChange(restaurants.find(r => r.id === e.target.value))}
    >
      {restaurants.map(r => (
        <option key={r.id} value={r.id}>
          {r.name} {r.name === 'Mimosas' ? '(Full Menu Data)' : ''}
        </option>
      ))}
    </select>
  );
}
```

---

## Mimosas Restaurant Details

### Staff (5 total)

| Name | Role | Tier | Score |
|------|------|------|-------|
| Maria Garcia | server | strong | 82.0 |
| James Wilson | server | standard | 58.0 |
| Emily Chen | server | standard | 55.0 |
| Carlos Rodriguez | bartender | strong | 78.0 |
| Sophie Kim | host | - | - |

### Sections & Tables

| Section | Tables | Capacity |
|---------|--------|----------|
| Main Dining | M1-M5 | 2-8 seats |
| Outdoor Patio | O1-O3 | 4-6 seats |
| Bar | B1-B3 | 2-4 seats |

### Menu (41 items across 9 categories)

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

### Sample Data Included
- 60 days of shifts
- ~1000+ visits
- ~3000+ order items
- Realistic demand patterns (some items popular, some not)

---

## Menu Ranking API

### Get Top Performers
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

### Get Worst Performers
```http
GET /api/v1/restaurants/{restaurant_id}/menu/rankings/bottom?lookback_days=30&limit=10
```

Same response format, sorted ascending by score.

### Scoring Formula
```
combined_score = (demand_score * 0.5) + (margin_pct * 0.5)

demand_score = (orders_per_day / max_orders_per_day) * 100
margin_pct = ((price - cost) / price) * 100
```

---

## 86 Management API

### Get 86 Recommendations
Items scoring below threshold that should be removed from menu.

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
      "demand_score": 12.0,
      "margin_pct": 66.7,
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

### Un-86 an Item (Restore)
```http
POST /api/v1/restaurants/{restaurant_id}/menu/items/{item_id}/un-86
```

### List All 86'd Items
```http
GET /api/v1/restaurants/{restaurant_id}/menu/items/86d
```

**Response:**
```json
{
  "restaurant_id": "uuid",
  "total_86d": 2,
  "items": [
    {
      "id": "uuid",
      "name": "Let Me Do Me!",
      "category": "For The Love Of Eggs",
      "price": 12.00,
      "is_available": false,
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

## Frontend Integration Examples

### Menu Dashboard Component

```jsx
function MenuDashboard({ restaurantId }) {
  const [topItems, setTopItems] = useState([]);
  const [bottomItems, setBottomItems] = useState([]);
  const [recommendations, setRecommendations] = useState([]);

  useEffect(() => {
    // Fetch all data in parallel
    Promise.all([
      fetch(`/api/v1/restaurants/${restaurantId}/menu/rankings/top?limit=5`),
      fetch(`/api/v1/restaurants/${restaurantId}/menu/rankings/bottom?limit=5`),
      fetch(`/api/v1/restaurants/${restaurantId}/menu/86-recommendations`)
    ])
    .then(responses => Promise.all(responses.map(r => r.json())))
    .then(([top, bottom, recs]) => {
      setTopItems(top.items);
      setBottomItems(bottom.items);
      setRecommendations(recs.recommendations);
    });
  }, [restaurantId]);

  return (
    <div>
      <TopPerformersCard items={topItems} />
      <BottomPerformersCard items={bottomItems} />
      <EightySixRecommendations items={recommendations} />
    </div>
  );
}
```

### 86 Button with Confirmation

```jsx
function EightySixButton({ restaurantId, item, onSuccess }) {
  const [loading, setLoading] = useState(false);

  const handle86 = async () => {
    if (!confirm(`86 "${item.name}"? It will be removed from the menu.`)) {
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/restaurants/${restaurantId}/menu/items/${item.id}/86`,
        { method: 'POST' }
      );
      const data = await res.json();
      if (data.success) {
        onSuccess(data);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <button onClick={handle86} disabled={loading}>
      {loading ? 'Processing...' : '86 Item'}
    </button>
  );
}
```

### Score Color Helper

```javascript
const getScoreColor = (score) => {
  if (score >= 70) return '#22c55e'; // green
  if (score >= 40) return '#eab308'; // yellow
  return '#ef4444'; // red
};

const getScoreLabel = (score) => {
  if (score >= 70) return 'Strong';
  if (score >= 40) return 'Average';
  return 'Weak';
};
```

### Score Badge Component

```jsx
function ScoreBadge({ score }) {
  const color = getScoreColor(score);
  const label = getScoreLabel(score);

  return (
    <span style={{
      backgroundColor: color,
      color: 'white',
      padding: '2px 8px',
      borderRadius: '4px',
      fontSize: '12px'
    }}>
      {score.toFixed(1)} ({label})
    </span>
  );
}
```

---

## Testing Workflow

### 1. Get Mimosas Restaurant ID
```bash
curl http://localhost:8000/api/v1/restaurants | jq '.[] | select(.name=="Mimosas")'
```

### 2. View Top Performers
```bash
curl "http://localhost:8000/api/v1/restaurants/{MIMOSAS_ID}/menu/rankings/top?limit=5"
```

### 3. View 86 Recommendations
```bash
curl "http://localhost:8000/api/v1/restaurants/{MIMOSAS_ID}/menu/86-recommendations"
```

### 4. 86 an Item
```bash
curl -X POST "http://localhost:8000/api/v1/restaurants/{MIMOSAS_ID}/menu/items/{ITEM_ID}/86"
```

### 5. Check 86'd Items
```bash
curl "http://localhost:8000/api/v1/restaurants/{MIMOSAS_ID}/menu/items/86d"
```

### 6. Restore Item
```bash
curl -X POST "http://localhost:8000/api/v1/restaurants/{MIMOSAS_ID}/menu/items/{ITEM_ID}/un-86"
```

---

## Expected Test Results with Mimosas

**Top Performers (high demand + good margin):**
- Fried Lobster & Waffles
- Mimosa's Orange Cream Waffle
- Classic Benedict
- Chunky Lobster Scram-Blette

**86 Candidates (low demand):**
- Let Me Do Me! (~0.3 orders/day)
- Yogurt Parfait (~0.4 orders/day)
- Artisan Breakfast (~0.5 orders/day)

---

## Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/menu/rankings/top` | GET | Best performers |
| `/menu/rankings/bottom` | GET | Worst performers |
| `/menu/86-recommendations` | GET | Items to consider removing |
| `/menu/items/{id}/86` | POST | Mark unavailable |
| `/menu/items/{id}/un-86` | POST | Restore availability |
| `/menu/items/86d` | GET | List unavailable items |

All endpoints are prefixed with `/api/v1/restaurants/{restaurant_id}`
