# Shire AI

One of our teammates' dad owns a restaurant. The hardest part isn't cooking—it's running the floor.

Friday night: 47 covers, 6 servers, 3 tables need busing, a party of 8 just walked in, and someone called in sick for tomorrow. Every decision is manual. Every mistake costs money.

Enterprises have Palantir. Restaurants have clipboards and gut instinct.

**We built the operational intelligence layer that restaurants never had.**

---

## What We Built

Shire AI combines computer vision, fairness-aware optimization, and LLM-powered analytics into a unified platform.

### 🎥 Real-Time Table State Classification

We mounted cameras above the dining floor and built a vision pipeline that classifies every table as **clean**, **occupied**, or **dirty**—in real-time, at 15+ FPS.

**The technical challenge:** CCTV frames are noisy, lighting changes constantly, and consecutive frames are nearly identical (causing train/test leakage if you're not careful).

**Our solution:** We fine-tuned a frozen DINOv2 Vision Transformer with a custom attention-pooling head that learns *which image patches matter*—plates, people, dishes—ignoring background clutter. We implemented **group-based data splitting** to ensure temporal independence and **N-frame consensus** to eliminate classification jitter.

$$\text{state} = \text{mode}(\text{predictions}_{t-N:t}) \quad \text{where } N=5$$

For zero-shot deployment (no labeled data needed), we also built a SAM3-based classifier using text-prompted segmentation: detect "person" → occupied; detect "plate" with no person → dirty.

### ⚖️ Fairness-First Waiter Routing

Traditional table assignment optimizes for speed. We optimize for **fairness**.

Our routing algorithm scores waiters using a priority function that penalizes both overwork *and* undertipping:

$$\text{priority} = w_e \cdot \text{efficiency} - w_w \cdot \frac{\text{tables}}{\text{max}} - w_t \cdot \frac{\text{tips}_i}{\text{tips}_{\text{total}}} - \text{recency}$$

**The key innovation:** An **underserved override** that detects when a waiter has fallen below 50% of average covers *and* 50% of average tips, then boosts their priority. This mathematically guarantees that no server gets systematically left behind during a shift.

### 📊 Server Performance Intelligence

We compute Z-score normalized performance metrics across three dimensions:

$$\text{score} = 0.3 \cdot z_{\text{turn\_time}}^{-1} + 0.4 \cdot z_{\text{tip\_pct}} + 0.3 \cdot z_{\text{covers}}$$

Waiters are automatically tiered (Strong ≥ p75, Standard, Developing < p25), and an LLM generates personalized coaching: *"Your table turn times improved 12% this month. Consider upselling appetizers to boost check averages."*

### 🗓️ AI-Powered Scheduling

Building a weekly schedule manually takes hours. Our engine does it in seconds.

**Demand forecasting** uses exponentially-decayed historical averages ($0.85^{\text{weeks\_ago}}$) to predict hourly covers. The **score-and-rank algorithm** then assigns shifts by optimizing:

$$\text{score} = 0.5 \cdot \text{constraints} + 0.3 \cdot (\text{fairness} + 50) + 0.2 \cdot \text{preferences}$$

We enforce a **Gini coefficient < 0.25** to ensure equitable hours distribution—no one gets all the prime Friday shifts while others get Monday mornings. Every assignment comes with LLM-generated reasoning: *"Assigned to Alex because they requested evening shifts and this improves hours fairness by 8%."*

### 💬 Review Sentiment Analysis

We scrape reviews from Yelp and Google (with anti-bot detection) and run them through ByteDance Seed 1.6 for **5-category opinion extraction**: food, service, atmosphere, value, cleanliness. Negative reviews are auto-flagged for manager attention before they become patterns.

### 🍽️ Menu Intelligence

Every menu item gets a composite score:

$$\text{score} = 0.5 \cdot (\text{orders/day})_{\text{norm}} + 0.5 \cdot \frac{\text{price} - \text{cost}}{\text{price}}$$

High-demand, low-margin items get pricing recommendations (+10-15%). Underperformers (score < 25) are flagged for "86" removal with auto-generated reasoning.

---

## How We Built It

- **Backend:** FastAPI + SQLAlchemy with fully async database operations
- **ML Pipeline:** PyTorch + HuggingFace (DINOv2, SAM3), deployed on RunPod GPUs
- **Video Processing:** FFmpeg for frame extraction, OpenCV for bounding box crops
- **Database:** PostgreSQL with pre-computed metric rollups (hourly/daily/weekly)
- **Frontend:** React + TypeScript + Zustand for real-time floor plan visualization
- **LLM Integration:** OpenRouter API (ByteDance Seed 1.6, Claude) for insights generation
- **Live Integration:** Direct integration with Swann security cameras—frames sampled at 1 FPS, sent to cloud GPU, predictions overlaid back onto the security display

---

## Challenges We Faced

**Data leakage in video ML:** Consecutive CCTV frames are 99% identical. Standard random splits caused our validation accuracy to be artificially inflated. We solved this with group-based splitting by session+timestamp+table.

**Imbalanced classes:** "Occupied" tables vastly outnumber "clean" and "dirty." We combined focal loss, class weighting, and mixup augmentation to handle the imbalance.

**Fairness vs. efficiency tradeoff:** Optimizing purely for efficiency means your best servers get slammed while others stand idle. We spent significant time tuning the penalty weights to balance tip fairness without sacrificing customer experience.

**Real-time performance:** Processing 15+ FPS on live video while maintaining sub-second latency required careful batching and GPU memory management.

---

## What We Learned

Building for restaurants taught us that **operational complexity scales non-linearly**. A 50-seat restaurant isn't twice as hard to manage as a 25-seat one—it's five times harder. The combinatorial explosion of tables × servers × time slots × customer preferences creates a problem space that humans simply cannot optimize manually.

We also learned that **fairness is a first-class engineering constraint**, not an afterthought. When tips are distributed unfairly, staff turnover increases, morale drops, and service quality suffers. Encoding fairness directly into our algorithms—via Gini coefficients, underserved overrides, and balanced scheduling—produces better outcomes for everyone.

---

## Impact

A single restaurant running Shire AI could:
- **Reduce table turn times** by eliminating manual state tracking
- **Increase waiter retention** through fairer tip distribution
- **Save 3+ hours/week** on schedule creation
- **Catch negative review trends** before they become reputation damage
- **Optimize menu pricing** to maximize margin without guesswork

We built the operational intelligence layer that restaurants have never had—the Palantir for the service industry.

---

*Built with ❤️ by Cameron Kuperman, Harshith Guduru, Alex Tabaku, and Ben Tang*
