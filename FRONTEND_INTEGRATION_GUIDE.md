# Review Management System - Frontend Integration Guide

**Restaurant:** Mimosas Southern Bar and Grill (Myrtle Beach)
**System:** Yelp Review Analysis with LLM-Powered Categorization
**Version:** 1.0
**Last Updated:** January 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [TypeScript Interfaces](#typescript-interfaces)
4. [API Endpoints Reference](#api-endpoints-reference)
5. [User Workflows](#user-workflows)
6. [State Management Recommendations](#state-management-recommendations)
7. [Error Handling](#error-handling)
8. [Polling & Real-time Updates](#polling--real-time-updates)
9. [Example Implementations](#example-implementations)

---

## Overview

### System Purpose

The Review Management System ingests Yelp reviews, uses AI to categorize them into 5 key areas, and provides actionable insights for restaurant managers.

### Key Features

- **Bulk Review Ingestion**: Upload scraped Yelp reviews as JSON
- **AI-Powered Analysis**: Automatic categorization into 5 categories (Food, Service, Atmosphere, Value, Cleanliness)
- **Real-time Statistics**: Rating distributions, averages, review counts
- **Manager Dashboard Data**: Category opinions with sentiment analysis
- **Manual Triggers**: Force re-analysis of pending reviews

### Data Flow

```
┌─────────────────┐
│  Scraper Tool   │ (Separate - outputs reviews.json)
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  POST /ingest   │─────▶│  Background LLM  │─────▶│  Categorized    │
│  (Upload JSON)  │      │  Processing      │      │  Reviews Ready  │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                                             │
                         ┌───────────────────────────────────┤
                         ▼                                   ▼
                  ┌─────────────┐                    ┌─────────────┐
                  │ GET /stats  │                    │ GET /summary│
                  │ (Numbers)   │                    │ (AI Insights)│
                  └─────────────┘                    └─────────────┘
```

---

## Quick Start

### Base URL

```
Production: https://your-domain.com/api/v1/reviews
Development: http://localhost:8000/api/v1/reviews
```

### Authentication

Currently: **None** (open API)
Future: JWT Bearer tokens

### Getting Started in 3 Steps

```typescript
// 1. Upload reviews
const uploadResponse = await fetch(
  `/api/v1/reviews/${restaurantId}/ingest`,
  {
    method: 'POST',
    body: formData, // File input with reviews.json
  }
);

// 2. Poll for stats (updates in real-time as reviews are processed)
const stats = await fetch(`/api/v1/reviews/${restaurantId}/stats`);

// 3. Display AI insights
const summary = await fetch(`/api/v1/reviews/${restaurantId}/summary`);
```

---

## Reviews Restaurant Aliasing (Two IDs, One Reviews Dataset)

If your frontend can switch between two restaurant IDs but you want **both**
IDs to show the same reviews, set an alias mapping for reviews only.

### 1. Find the two restaurant IDs

```bash
curl http://localhost:8000/api/v1/restaurants
```

Pick a canonical reviews ID (the one that already has reviews) and the alias
ID (the one returning empty).

### 2. Set the alias mapping

Set `REVIEWS_RESTAURANT_ALIASES` as JSON where the **key** is the alias ID and
the **value** is the canonical reviews ID:

```bash
export REVIEWS_RESTAURANT_ALIASES='{"alias_uuid":"canonical_uuid"}'
```

Or put the same line in your `.env` file.

### 3. Restart the backend

The mapping is read on startup, so restart the API after setting it.

### 4. Verify from the frontend

Use both restaurant IDs against the reviews endpoints:

```
GET /api/v1/reviews/{restaurant_id}/stats
GET /api/v1/reviews/{restaurant_id}/summary
GET /api/v1/reviews/{restaurant_id}/reviews?skip=0&limit=50
```

Both IDs should now return identical reviews data. This aliasing is **reviews
only**; all other API endpoints still use each restaurant ID separately.

---

## TypeScript Interfaces

### Core Data Types

```typescript
/**
 * Single review from Yelp (for ingestion)
 */
interface ReviewCreate {
  platform: string;              // "yelp"
  review_identifier: string;     // Unique ID (e.g., "yelp_a1b2c3d4e5f6")
  rating: number;                // 1-5 stars
  text: string;                  // Review content
  review_date: string;           // ISO 8601 timestamp
}

/**
 * Full review object (after processing)
 */
interface ReviewRead {
  id: string;                    // UUID
  platform: string;              // "yelp"
  rating: number;                // 1-5 stars
  text: string;                  // Review content
  review_date: string;           // ISO 8601 timestamp

  // AI-generated fields (null until processed)
  sentiment_score: number | null;      // -1.0 to 1.0
  category_opinions: CategoryOpinions | null;
  overall_summary: string | null;
  needs_attention: boolean;      // True if negative sentiment

  // Status tracking
  status: 'pending' | 'categorized' | 'dismissed';
  created_at: string;            // When ingested
}

/**
 * Rating distribution breakdown
 */
interface RatingDistribution {
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
}

/**
 * Aggregate statistics (no AI, pure SQL)
 */
interface ReviewStats {
  overall_average: number;       // e.g., 4.2
  total_reviews: number;
  reviews_this_month: number;
  rating_distribution: RatingDistribution;
}

/**
 * AI-generated category opinions
 */
interface CategoryOpinions {
  food: string;                  // Narrative statement
  service: string;
  atmosphere: string;
  value: string;
  cleanliness: string;
}

/**
 * Complete AI summary with insights
 */
interface ReviewSummary {
  category_opinions: CategoryOpinions;
  overall_summary: string;       // 2-3 sentence summary
  needs_attention: boolean;      // True if negative themes detected
}

/**
 * Response from categorization trigger
 */
interface CategorizationResult {
  processed: number;             // Reviews categorized
  batches: number;               // Number of batches
  pending_remaining: number;     // Reviews still pending
}

/**
 * Response from ingest endpoint
 */
interface IngestResponse {
  added: number;                 // New reviews added
  total_submitted: number;       // Total in uploaded file
  status: 'categorizing' | 'no_new_reviews';
}
```

---

## API Endpoints Reference

### 1. Ingest Reviews

**Upload scraped reviews for processing**

```
POST /api/v1/reviews/{restaurant_id}/ingest
```

**Request**

- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Body**: File upload with field name `file`

**File Format** (JSON array):

```json
[
  {
    "platform": "yelp",
    "review_identifier": "yelp_a1b2c3d4e5f6",
    "rating": 5,
    "text": "Amazing southern food! The shrimp and grits were incredible...",
    "review_date": "2024-01-15T00:00:00Z"
  },
  {
    "platform": "yelp",
    "review_identifier": "yelp_f6e5d4c3b2a1",
    "rating": 2,
    "text": "Service was extremely slow. Waited 45 minutes for our food...",
    "review_date": "2024-01-10T00:00:00Z"
  }
]
```

**Response**

```typescript
interface IngestResponse {
  added: number;
  total_submitted: number;
  status: 'categorizing' | 'no_new_reviews';
}
```

**Example Response**:

```json
{
  "added": 75,
  "total_submitted": 75,
  "status": "categorizing"
}
```

**Status Codes**:

- `200`: Success
- `400`: Invalid JSON format or validation error
- `404`: Restaurant not found

**Notes**:

- Duplicate reviews (by `review_identifier`) are automatically skipped
- LLM categorization starts automatically in background
- Processing happens in batches of 25 reviews
- No need to wait for completion - use polling to check progress

---

### 2. Get Review Statistics

**Fetch aggregate statistics (real-time, no AI)**

```
GET /api/v1/reviews/{restaurant_id}/stats
```

**Request**

- **Method**: `GET`
- **Query Parameters**: None

**Response**

```typescript
interface ReviewStats {
  overall_average: number;
  total_reviews: number;
  reviews_this_month: number;
  rating_distribution: RatingDistribution;
}
```

**Example Response**:

```json
{
  "overall_average": 4.2,
  "total_reviews": 75,
  "reviews_this_month": 12,
  "rating_distribution": {
    "five_star": 45,
    "four_star": 15,
    "three_star": 8,
    "two_star": 5,
    "one_star": 2
  }
}
```

**Status Codes**:

- `200`: Success
- `404`: Restaurant not found

**Use Cases**:

- Dashboard header stats
- Rating distribution charts
- Real-time counter updates

**Performance**: < 50ms (pure SQL aggregation)

---

### 3. Get AI Summary

**Fetch LLM-generated category insights**

```
GET /api/v1/reviews/{restaurant_id}/summary
```

**Request**

- **Method**: `GET`
- **Query Parameters**: None

**Response**

```typescript
interface ReviewSummary {
  category_opinions: CategoryOpinions;
  overall_summary: string;
  needs_attention: boolean;
}
```

**Example Response**:

```json
{
  "category_opinions": {
    "food": "Customers consistently praise the shrimp and grits as exceptional, with many noting the authentic southern flavors and generous portions.",
    "service": "Service receives mixed feedback, with some highlighting friendly staff while others mention slow response times during peak hours.",
    "atmosphere": "The casual, welcoming ambiance is frequently mentioned as perfect for family gatherings and celebrations.",
    "value": "Most reviewers feel the pricing is fair given the portion sizes and quality of food.",
    "cleanliness": "Generally positive comments about restaurant cleanliness, though a few mention restroom maintenance issues."
  },
  "overall_summary": "Mimosas receives strong praise for authentic southern cuisine, particularly seafood dishes. While the atmosphere and value are well-regarded, service consistency could be improved during busy periods.",
  "needs_attention": false
}
```

**Status Codes**:

- `200`: Success
- `404`: Restaurant not found

**When No Data Available**:

```json
{
  "category_opinions": {
    "food": "Not enough data",
    "service": "Not enough data",
    "atmosphere": "Not enough data",
    "value": "Not enough data",
    "cleanliness": "Not enough data"
  },
  "overall_summary": "No reviews have been analyzed yet.",
  "needs_attention": false
}
```

**Use Cases**:

- Manager dashboard "Insights" panel
- Category breakdown cards
- Alert banners when `needs_attention: true`

**Data Freshness**: Returns most recent batch categorization

---

### 4. Get Review List

**Fetch paginated raw reviews**

```
GET /api/v1/reviews/{restaurant_id}/reviews
```

**Request**

- **Method**: `GET`
- **Query Parameters**:
  - `skip` (optional, default: `0`) - Offset for pagination
  - `limit` (optional, default: `50`, max: `200`) - Results per page

**Response**

```typescript
type ReviewList = ReviewRead[];
```

**Example Response**:

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "platform": "yelp",
    "rating": 5,
    "text": "Amazing food and service! Highly recommend the shrimp and grits.",
    "review_date": "2024-01-15T12:00:00Z",
    "sentiment_score": 0.8,
    "category_opinions": {
      "food": "Excellent quality",
      "service": "Attentive and friendly",
      "atmosphere": "Welcoming",
      "value": "Great portions",
      "cleanliness": "Very clean"
    },
    "overall_summary": "Positive dining experience with exceptional food quality.",
    "needs_attention": false,
    "status": "categorized",
    "created_at": "2024-01-16T10:00:00Z"
  }
]
```

**Status Codes**:

- `200`: Success
- `404`: Restaurant not found

**Pagination Example**:

```typescript
// Page 1 (first 50 reviews)
GET /api/v1/reviews/{id}/reviews?skip=0&limit=50

// Page 2 (next 50 reviews)
GET /api/v1/reviews/{id}/reviews?skip=50&limit=50

// Page 3
GET /api/v1/reviews/{id}/reviews?skip=100&limit=50
```

**Use Cases**:

- Review list table with pagination
- Infinite scroll feed
- Export functionality

**Sorting**: Reviews ordered by `review_date DESC` (newest first)

---

### 5. Trigger Manual Categorization

**Force LLM processing of pending reviews**

```
POST /api/v1/reviews/{restaurant_id}/categorize
```

**Request**

- **Method**: `POST`
- **Body**: None

**Response**

```typescript
interface CategorizationResult {
  processed: number;
  batches: number;
  pending_remaining: number;
  message?: string;
}
```

**Example Response**:

```json
{
  "processed": 75,
  "batches": 3,
  "pending_remaining": 0
}
```

**When No Pending Reviews**:

```json
{
  "processed": 0,
  "batches": 0,
  "pending_remaining": 0,
  "message": "No pending reviews"
}
```

**Status Codes**:

- `200`: Success (even if no reviews to process)
- `404`: Restaurant not found

**Use Cases**:

- "Refresh Analysis" button
- Admin panel for re-processing
- Testing/debugging

**Processing Time**: Synchronous - waits for all batches to complete (~5-10 seconds per batch of 25)

---

## User Workflows

### Workflow 1: Manager Views Dashboard (Initial Load)

**Goal**: Display current review statistics and AI insights

```typescript
async function loadDashboard(restaurantId: string) {
  try {
    // 1. Fetch stats for header cards
    const statsResponse = await fetch(
      `/api/v1/reviews/${restaurantId}/stats`
    );
    const stats: ReviewStats = await statsResponse.json();

    // Update UI: Overall average, total count, distribution chart
    displayStats(stats);

    // 2. Fetch AI summary for insights panel
    const summaryResponse = await fetch(
      `/api/v1/reviews/${restaurantId}/summary`
    );
    const summary: ReviewSummary = await summaryResponse.json();

    // Update UI: Category cards, overall summary
    displayInsights(summary);

    // 3. Show alert if attention needed
    if (summary.needs_attention) {
      showAlert('Some reviews require management attention');
    }

  } catch (error) {
    handleError(error);
  }
}
```

**UI Components**:

- **Header Stats Card**: Overall average, total reviews, this month count
- **Rating Distribution Chart**: Bar chart showing 1-5 star breakdown
- **Category Insights Panel**: 5 cards (Food, Service, Atmosphere, Value, Cleanliness)
- **Overall Summary Box**: AI-generated summary with needs_attention badge

---

### Workflow 2: Upload New Reviews

**Goal**: Ingest scraped Yelp reviews and trigger AI analysis

```typescript
async function uploadReviews(restaurantId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    // 1. Upload file
    const response = await fetch(
      `/api/v1/reviews/${restaurantId}/ingest`,
      {
        method: 'POST',
        body: formData,
      }
    );

    const result: IngestResponse = await response.json();

    // 2. Show success message
    showNotification(
      `${result.added} new reviews uploaded. AI analysis in progress...`
    );

    // 3. Start polling for updates
    if (result.status === 'categorizing') {
      pollForUpdates(restaurantId);
    }

  } catch (error) {
    handleError(error);
  }
}

// Poll stats every 5 seconds to show progress
function pollForUpdates(restaurantId: string) {
  const interval = setInterval(async () => {
    const stats = await fetch(`/api/v1/reviews/${restaurantId}/stats`);
    const data: ReviewStats = await stats.json();

    updateStatsDisplay(data);

    // Stop polling after 2 minutes (all batches should be done)
    // Or implement proper completion check
  }, 5000);

  // Clear after 2 minutes
  setTimeout(() => clearInterval(interval), 120000);
}
```

**UI Flow**:

1. **File Input**: Accept `.json` file upload
2. **Loading State**: Show spinner during upload
3. **Success Toast**: Display number of reviews added
4. **Progress Indicator**: "AI analysis in progress..." banner
5. **Auto-refresh**: Poll stats endpoint to show live updates

---

### Workflow 3: View Individual Reviews

**Goal**: Display paginated list of reviews with AI data

```typescript
interface ReviewTableProps {
  restaurantId: string;
}

function ReviewTable({ restaurantId }: ReviewTableProps) {
  const [reviews, setReviews] = useState<ReviewRead[]>([]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const pageSize = 50;

  async function loadReviews(pageNum: number) {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/reviews/${restaurantId}/reviews?skip=${pageNum * pageSize}&limit=${pageSize}`
      );
      const data: ReviewRead[] = await response.json();
      setReviews(data);
    } catch (error) {
      handleError(error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReviews(page);
  }, [page]);

  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Rating</th>
            <th>Review</th>
            <th>Sentiment</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map(review => (
            <tr key={review.id}>
              <td>{formatDate(review.review_date)}</td>
              <td>{renderStars(review.rating)}</td>
              <td>{truncate(review.text, 100)}</td>
              <td>{renderSentiment(review.sentiment_score)}</td>
              <td>
                <Badge status={review.status} />
                {review.needs_attention && <AlertIcon />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Pagination
        currentPage={page}
        onPageChange={setPage}
        hasMore={reviews.length === pageSize}
      />
    </div>
  );
}
```

**UI Components**:

- **Review Table**: Sortable columns
- **Pagination**: Page numbers or infinite scroll
- **Status Badges**: `pending` (gray), `categorized` (green), `dismissed` (red)
- **Sentiment Indicator**: Color-coded score (-1.0 to 1.0)
- **Expand Row**: Click to see full review text + category opinions

---

### Workflow 4: Force Re-Analysis

**Goal**: Manually trigger LLM categorization

```typescript
async function reAnalyzeReviews(restaurantId: string) {
  try {
    setLoading(true);

    const response = await fetch(
      `/api/v1/reviews/${restaurantId}/categorize`,
      { method: 'POST' }
    );

    const result: CategorizationResult = await response.json();

    if (result.processed === 0) {
      showNotification('No pending reviews to process');
    } else {
      showNotification(
        `Processed ${result.processed} reviews in ${result.batches} batches`
      );

      // Refresh summary
      await loadDashboard(restaurantId);
    }

  } catch (error) {
    handleError(error);
  } finally {
    setLoading(false);
  }
}
```

**UI Element**: "Refresh Analysis" button in insights panel header

---

## State Management Recommendations

### Option 1: React Context (Simple)

```typescript
interface ReviewContextValue {
  stats: ReviewStats | null;
  summary: ReviewSummary | null;
  loading: boolean;
  error: string | null;
  refreshData: () => Promise<void>;
}

const ReviewContext = createContext<ReviewContextValue | null>(null);

export function ReviewProvider({ restaurantId, children }) {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshData() {
    setLoading(true);
    setError(null);

    try {
      const [statsRes, summaryRes] = await Promise.all([
        fetch(`/api/v1/reviews/${restaurantId}/stats`),
        fetch(`/api/v1/reviews/${restaurantId}/summary`),
      ]);

      setStats(await statsRes.json());
      setSummary(await summaryRes.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshData();
  }, [restaurantId]);

  return (
    <ReviewContext.Provider value={{ stats, summary, loading, error, refreshData }}>
      {children}
    </ReviewContext.Provider>
  );
}
```

### Option 2: Redux Toolkit (Scalable)

```typescript
// store/reviewSlice.ts
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

export const fetchStats = createAsyncThunk(
  'reviews/fetchStats',
  async (restaurantId: string) => {
    const response = await fetch(`/api/v1/reviews/${restaurantId}/stats`);
    return response.json();
  }
);

export const fetchSummary = createAsyncThunk(
  'reviews/fetchSummary',
  async (restaurantId: string) => {
    const response = await fetch(`/api/v1/reviews/${restaurantId}/summary`);
    return response.json();
  }
);

const reviewSlice = createSlice({
  name: 'reviews',
  initialState: {
    stats: null,
    summary: null,
    loading: false,
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchStats.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchStats.fulfilled, (state, action) => {
        state.stats = action.payload;
        state.loading = false;
      })
      .addCase(fetchStats.rejected, (state, action) => {
        state.error = action.error.message;
        state.loading = false;
      });
  },
});

export default reviewSlice.reducer;
```

### Option 3: TanStack Query (Recommended)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// Fetch stats
export function useReviewStats(restaurantId: string) {
  return useQuery({
    queryKey: ['reviews', restaurantId, 'stats'],
    queryFn: async () => {
      const res = await fetch(`/api/v1/reviews/${restaurantId}/stats`);
      if (!res.ok) throw new Error('Failed to fetch stats');
      return res.json() as Promise<ReviewStats>;
    },
    refetchInterval: 30000, // Auto-refresh every 30 seconds
  });
}

// Fetch summary
export function useReviewSummary(restaurantId: string) {
  return useQuery({
    queryKey: ['reviews', restaurantId, 'summary'],
    queryFn: async () => {
      const res = await fetch(`/api/v1/reviews/${restaurantId}/summary`);
      if (!res.ok) throw new Error('Failed to fetch summary');
      return res.json() as Promise<ReviewSummary>;
    },
  });
}

// Upload reviews
export function useUploadReviews(restaurantId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`/api/v1/reviews/${restaurantId}/ingest`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Upload failed');
      return res.json() as Promise<IngestResponse>;
    },
    onSuccess: () => {
      // Invalidate cache to trigger refetch
      queryClient.invalidateQueries({ queryKey: ['reviews', restaurantId] });
    },
  });
}
```

**Recommendation**: Use **TanStack Query** for built-in caching, auto-refetch, and optimistic updates.

---

## Error Handling

### Error Response Format

```typescript
interface ErrorResponse {
  detail: string;
}
```

### Common Errors

| Status Code | Meaning | Example Response |
|-------------|---------|------------------|
| 400 | Bad Request | `{ "detail": "Invalid JSON file" }` |
| 404 | Not Found | `{ "detail": "Restaurant not found" }` |
| 422 | Validation Error | `{ "detail": [{"loc": ["rating"], "msg": "ensure this value is less than or equal to 5"}] }` |
| 500 | Server Error | `{ "detail": "Internal server error" }` |

### Error Handling Pattern

```typescript
async function fetchWithErrorHandling(url: string, options?: RequestInit) {
  try {
    const response = await fetch(url, options);

    if (!response.ok) {
      const error: ErrorResponse = await response.json();

      switch (response.status) {
        case 400:
          throw new ValidationError(error.detail);
        case 404:
          throw new NotFoundError(error.detail);
        case 422:
          throw new ValidationError(formatValidationErrors(error.detail));
        default:
          throw new Error(error.detail || 'Unknown error');
      }
    }

    return response.json();
  } catch (error) {
    if (error instanceof TypeError) {
      // Network error
      throw new NetworkError('Cannot connect to server');
    }
    throw error;
  }
}

// Custom error classes
class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}

class NotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NotFoundError';
  }
}

class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}
```

### User-Friendly Error Messages

```typescript
function getErrorMessage(error: unknown): string {
  if (error instanceof ValidationError) {
    return 'The uploaded file contains invalid data. Please check the format.';
  }

  if (error instanceof NotFoundError) {
    return 'Restaurant not found. Please check the ID.';
  }

  if (error instanceof NetworkError) {
    return 'Cannot connect to server. Please check your internet connection.';
  }

  return 'An unexpected error occurred. Please try again.';
}
```

---

## Polling & Real-time Updates

### When to Poll

- After uploading reviews (until categorization completes)
- On dashboard page (for live stats updates)

### Polling Strategy

```typescript
class ReviewPoller {
  private intervalId: number | null = null;
  private restaurantId: string;
  private callback: (stats: ReviewStats) => void;

  constructor(restaurantId: string, callback: (stats: ReviewStats) => void) {
    this.restaurantId = restaurantId;
    this.callback = callback;
  }

  start(intervalMs: number = 5000) {
    if (this.intervalId) return; // Already running

    this.intervalId = window.setInterval(async () => {
      try {
        const response = await fetch(
          `/api/v1/reviews/${this.restaurantId}/stats`
        );
        const stats: ReviewStats = await response.json();
        this.callback(stats);
      } catch (error) {
        console.error('Polling error:', error);
      }
    }, intervalMs);
  }

  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }
}

// Usage
const poller = new ReviewPoller(restaurantId, (stats) => {
  updateUI(stats);
});

poller.start(5000); // Poll every 5 seconds

// Stop when component unmounts
useEffect(() => {
  return () => poller.stop();
}, []);
```

### Exponential Backoff (Optional)

```typescript
class SmartPoller {
  private baseInterval = 5000;
  private maxInterval = 60000;
  private currentInterval = 5000;
  private unchangedCount = 0;

  async poll() {
    const stats = await fetchStats();

    if (hasChanged(stats)) {
      // Data changed - reset to fast polling
      this.currentInterval = this.baseInterval;
      this.unchangedCount = 0;
    } else {
      // No change - slow down polling
      this.unchangedCount++;
      if (this.unchangedCount > 3) {
        this.currentInterval = Math.min(
          this.currentInterval * 1.5,
          this.maxInterval
        );
      }
    }

    setTimeout(() => this.poll(), this.currentInterval);
  }
}
```

### Alternative: Server-Sent Events (Future)

```typescript
// If backend implements SSE in the future
const eventSource = new EventSource(
  `/api/v1/reviews/${restaurantId}/stream`
);

eventSource.addEventListener('stats_updated', (event) => {
  const stats: ReviewStats = JSON.parse(event.data);
  updateUI(stats);
});

eventSource.addEventListener('categorization_complete', (event) => {
  showNotification('All reviews have been analyzed!');
});
```

**Note**: Not currently implemented - use polling for now.

---

## Example Implementations

### Complete Dashboard Component (React + TypeScript)

```typescript
import React, { useEffect, useState } from 'react';

interface DashboardProps {
  restaurantId: string;
}

export function ReviewDashboard({ restaurantId }: DashboardProps) {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, [restaurantId]);

  async function loadData() {
    setLoading(true);
    setError(null);

    try {
      const [statsRes, summaryRes] = await Promise.all([
        fetch(`/api/v1/reviews/${restaurantId}/stats`),
        fetch(`/api/v1/reviews/${restaurantId}/summary`),
      ]);

      if (!statsRes.ok || !summaryRes.ok) {
        throw new Error('Failed to load data');
      }

      setStats(await statsRes.json());
      setSummary(await summaryRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <LoadingSpinner />;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={loadData} />;
  }

  if (!stats || !summary) {
    return <EmptyState message="No review data available" />;
  }

  return (
    <div className="review-dashboard">
      {/* Header Stats */}
      <div className="stats-grid">
        <StatCard
          title="Overall Rating"
          value={stats.overall_average.toFixed(1)}
          icon="⭐"
          trend="+0.2 this month"
        />
        <StatCard
          title="Total Reviews"
          value={stats.total_reviews.toString()}
          icon="💬"
        />
        <StatCard
          title="This Month"
          value={stats.reviews_this_month.toString()}
          icon="📅"
        />
      </div>

      {/* Rating Distribution Chart */}
      <div className="chart-section">
        <h2>Rating Distribution</h2>
        <RatingChart distribution={stats.rating_distribution} />
      </div>

      {/* AI Insights */}
      <div className="insights-section">
        <div className="section-header">
          <h2>AI-Powered Insights</h2>
          {summary.needs_attention && (
            <AlertBadge>Needs Attention</AlertBadge>
          )}
        </div>

        <div className="category-grid">
          {Object.entries(summary.category_opinions).map(([category, opinion]) => (
            <CategoryCard
              key={category}
              category={category}
              opinion={opinion}
            />
          ))}
        </div>

        <div className="summary-box">
          <h3>Overall Summary</h3>
          <p>{summary.overall_summary}</p>
        </div>
      </div>
    </div>
  );
}

// Reusable components
function StatCard({ title, value, icon, trend }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <h3>{title}</h3>
        <div className="stat-value">{value}</div>
        {trend && <div className="stat-trend">{trend}</div>}
      </div>
    </div>
  );
}

function CategoryCard({ category, opinion }) {
  const categoryIcons = {
    food: '🍽️',
    service: '👥',
    atmosphere: '🏛️',
    value: '💰',
    cleanliness: '✨',
  };

  return (
    <div className="category-card">
      <div className="category-header">
        <span className="category-icon">{categoryIcons[category]}</span>
        <h3>{category.charAt(0).toUpperCase() + category.slice(1)}</h3>
      </div>
      <p className="category-opinion">{opinion}</p>
    </div>
  );
}

function RatingChart({ distribution }: { distribution: RatingDistribution }) {
  const total = Object.values(distribution).reduce((sum, count) => sum + count, 0);

  return (
    <div className="rating-chart">
      {[5, 4, 3, 2, 1].map((stars) => {
        const key = `${['one', 'two', 'three', 'four', 'five'][stars - 1]}_star` as keyof RatingDistribution;
        const count = distribution[key];
        const percentage = total > 0 ? (count / total) * 100 : 0;

        return (
          <div key={stars} className="rating-bar">
            <span className="star-label">{stars} ⭐</span>
            <div className="bar-container">
              <div
                className="bar-fill"
                style={{ width: `${percentage}%` }}
              />
            </div>
            <span className="count-label">{count}</span>
          </div>
        );
      })}
    </div>
  );
}
```

### File Upload Component

```typescript
export function ReviewUploader({ restaurantId }: { restaurantId: string }) {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.json')) {
      alert('Please upload a JSON file');
      return;
    }

    setUploading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(
        `/api/v1/reviews/${restaurantId}/ingest`,
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) {
        const error: ErrorResponse = await response.json();
        throw new Error(error.detail);
      }

      const data: IngestResponse = await response.json();
      setResult(data);

      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

    } catch (error) {
      alert(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="uploader">
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileUpload}
        disabled={uploading}
      />

      {uploading && (
        <div className="upload-progress">
          <Spinner />
          <span>Uploading reviews...</span>
        </div>
      )}

      {result && (
        <div className="upload-result">
          <h4>Upload Complete</h4>
          <p>{result.added} new reviews added</p>
          <p>{result.total_submitted - result.added} duplicates skipped</p>
          {result.status === 'categorizing' && (
            <p className="processing">AI analysis in progress...</p>
          )}
        </div>
      )}
    </div>
  );
}
```

### Custom Hooks (React)

```typescript
// useReviewStats.ts
export function useReviewStats(restaurantId: string, pollInterval?: number) {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/reviews/${restaurantId}/stats`);
      if (!response.ok) throw new Error('Failed to fetch stats');
      const data: ReviewStats = await response.json();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Unknown error'));
    } finally {
      setLoading(false);
    }
  }, [restaurantId]);

  useEffect(() => {
    fetchStats();

    if (pollInterval) {
      const interval = setInterval(fetchStats, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchStats, pollInterval]);

  return { stats, loading, error, refetch: fetchStats };
}

// Usage
function MyComponent() {
  const { stats, loading, error, refetch } = useReviewStats(
    'restaurant-id',
    5000 // Poll every 5 seconds
  );

  if (loading) return <Spinner />;
  if (error) return <Error message={error.message} />;
  if (!stats) return null;

  return <StatsDisplay stats={stats} onRefresh={refetch} />;
}
```

---

## Appendix: Complete Type Definitions

```typescript
// types/reviews.ts

/**
 * Review creation payload (for ingestion)
 */
export interface ReviewCreate {
  platform: string;
  review_identifier: string;
  rating: number;
  text: string;
  review_date: string;
}

/**
 * Full review object with AI data
 */
export interface ReviewRead {
  id: string;
  platform: string;
  rating: number;
  text: string;
  review_date: string;
  sentiment_score: number | null;
  category_opinions: CategoryOpinions | null;
  overall_summary: string | null;
  needs_attention: boolean;
  status: ReviewStatus;
  created_at: string;
}

/**
 * Review processing status
 */
export type ReviewStatus = 'pending' | 'categorized' | 'dismissed';

/**
 * Star rating distribution
 */
export interface RatingDistribution {
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
}

/**
 * Aggregate review statistics
 */
export interface ReviewStats {
  overall_average: number;
  total_reviews: number;
  reviews_this_month: number;
  rating_distribution: RatingDistribution;
}

/**
 * AI-generated category insights
 */
export interface CategoryOpinions {
  food: string;
  service: string;
  atmosphere: string;
  value: string;
  cleanliness: string;
}

/**
 * Complete AI summary
 */
export interface ReviewSummary {
  category_opinions: CategoryOpinions;
  overall_summary: string;
  needs_attention: boolean;
}

/**
 * Categorization processing result
 */
export interface CategorizationResult {
  processed: number;
  batches: number;
  pending_remaining: number;
  message?: string;
}

/**
 * Ingest endpoint response
 */
export interface IngestResponse {
  added: number;
  total_submitted: number;
  status: 'categorizing' | 'no_new_reviews';
}

/**
 * API error response
 */
export interface ErrorResponse {
  detail: string | ValidationError[];
}

/**
 * Validation error detail
 */
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}
```

---

## FAQ

### Q: How long does AI categorization take?

**A**: ~5-10 seconds per batch of 25 reviews. For 75 reviews (3 batches), expect ~30 seconds total.

### Q: What happens if I upload duplicates?

**A**: Duplicates (by `review_identifier`) are automatically skipped. The response will show `added < total_submitted`.

### Q: Can I re-analyze reviews?

**A**: Yes, use `POST /{restaurant_id}/categorize` to force re-processing. Note: This will overwrite existing AI data.

### Q: How often should I poll for updates?

**A**: Every 5-10 seconds during active categorization. Consider exponential backoff for longer polling sessions.

### Q: What if `category_opinions` is null?

**A**: Review hasn't been categorized yet. Display a "Pending analysis" badge or wait for background processing to complete.

### Q: Can I filter reviews by status?

**A**: Not yet implemented. Future enhancement: `GET /reviews?status=categorized`

### Q: Is there a way to export reviews?

**A**: Fetch all reviews with pagination and convert to CSV/Excel on frontend.

---

## Support & Contact

For backend API issues:
- Check `COMMON_ISSUES.md` in the repository
- Review `REVIEW_SYSTEM_PLAN.md` for implementation details

For frontend integration questions:
- Refer to this guide
- Check API endpoint responses for validation errors
- Use browser DevTools Network tab to debug requests

---

**End of Frontend Integration Guide**

*Last updated: January 2025*
