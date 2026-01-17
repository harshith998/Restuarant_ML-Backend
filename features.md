# Features & Requirements

## 1. Segmentation
### 1.1 Table Segmentation
*   **Method**: Finetune Dino on manually annotated frames.
*   **Input**: Raw video of CCTV footage.
*   **Output**: Segmentation mesh coordinates (for calculating presence) + Table ID.

### 1.2 People Segmentation
*   **Method**: Off-the-shelf segmenting models.
*   **Output**: Mesh coordinates (to compare human mesh pos vs table mesh pos for counting people). Specificity can be low (box mesh).

## 2. Data Annotation
### Overview
Label table states from CCTV footage to train clean/dirty classifier.

### Process
1.  **Cropping**: Generate one video per table (e.g., `table_01.mp4`) from raw footage.
2.  **Manual Labeling**: Watch recordings and log states: `state` (empty_clean, occupied, empty_dirty), `start`, `end`.
3.  **Output**: Labeled clips for training.

## 3. Classification
### Methods
*   **ML**: CNN or Dino model with MLP head.
*   **Deterministic**: If people segments intersect table segments => Occupied.
*   **Hybrid**: Deterministic for used/unused, ML for clean/unclean.

## 4. Backend
### Inputs
*   **Staff Info**: ID, name, clock status, live tips, experience enum.
*   **Table Info**: State (from ML), number of people.
*   **New Seating Info**: Party size (manual entry from host).

### Outputs
*   **Host Route**: Table assignments.
*   **Waiter Route**: Waiter assignments.
*   **Cleaner Route**: Cleaning tasks.

### Methodology/Flow
1.  Ingest positional data (segmentation) and inputs.
2.  Run ML classification every N frames for table state.
3.  **Routing Algorithm**:
    *   **Waiter Selection**: Greedy algorithm. Score = `(Avg Latency * Efficiency) * (1 / Tips Made)`. 
    *   *Bias*: Prioritize efficient workers but ensure fair tips.
    *   *Penalty*: Score / 2 for every extra table managed.
    *   **Host Routing**: Random 'open table' accommodating size within routed waiter section.

### Data Structures

#### Stored Data (JSON)
*   **Waiters**: ID, Name, Score, Current Tips, Live Tables, Status (available/busy/break/heading), Section.
*   **Cleaners**: ID, Name, Status.
*   **Hosts**: ID, Name, On Duty.

#### ML Input (JSON)
*   Camera ID, Timestamp.
*   **Tables**: ID, Predicted State (clean/occupied/dirty), Confidence, Last State Change.

#### UI Input (JSON)
*   **Host**: ID, Name.
*   **Request**: Group ID, Party Size, Is Reserved, Preference (Window/Bar/Booth), Requested Time.
*   **Floor Map Version**.

#### UI Output (JSON)
*   **Route**: ID, Routed Table (ID, Section), Routed Waiter (ID, Name), Routed Cleaner (ID).

## 5. Frontend
### Host iPad
*   **Floor Plan**: Live table states (color-coded).
*   **Actions**: "Seat Party" button (recommends table + assigns waiter).
*   **Info**: Wait time estimates.

### Server/Cleaner View
*   **Task Queue**: Next table to serve/clean.
*   **Stats**: Tables served, tips.
*   *Note*: Copy Toast UI style.

## 6. Smart Integrations & Analytics
*   **Business Analytics**: Peak times, server performance (throughput - latency).
*   **Kitchen Integration**: Grouping items, stopping double seating via timer/points.
*   **Inventory/Supplier**: Ingredient usage tracking, ordering suggestions.
*   **Customer Insights**: "For You" feed, proactive suggestions, chatbot for tasks ("86 avocado toast").

### Advanced Features (Potential)
*   **Interaction Time**: Analysis for quality service.
*   **Hazard Monitor**: Detect spills/hazards.
*   **Dwell Time & Turn rate**: Analysis of actual sitting time vs check time.
*   **Ready-to-Order Detection**: Computer vision to spot customers looking for service.

## 7. Platform Features (Ref: Kibsi/OpenTable/Toast)
*   **Reservation Management**: Online booking, widgets, SMS reminders, deposits, waitlist.
*   **Table Management**: Floor plans, smart assignment, turn time analysis.
*   **CRM**: Guest profiles (visit history, spend, preferences, tags).
*   **Marketing**: Email campaigns, win-back, feedback loops.
*   **Staff Ops**: Shift planning, extensive permissions, multi-location support.
*   **Diner App**: Loyalty points, discovery, reviews.
