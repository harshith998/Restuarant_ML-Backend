# Generative AI Usage

We integrated two LLM APIs for distinct operational intelligence tasks:

## ByteDance Seed 1.6 (via OpenRouter)

**Review Sentiment Analysis**
- Batch-processes scraped Yelp/Google reviews (25 reviews/batch)
- Extracts 5-category opinions: food, service, atmosphere, value, cleanliness
- Flags reviews requiring manager attention
- Why: Cost-effective for high-volume text classification with structured JSON output

**Server Performance Insights**
- Generates personalized coaching for each waiter based on Z-score metrics
- Outputs strengths, areas to watch, and actionable suggestions
- Why: Transforms raw statistics into human-readable feedback that managers can act on

## Gemini

**Scheduling Reasoning**
- Generates natural-language explanations for each shift assignment
- Example: *"Assigned to Alex because they requested evening shifts and this improves hours fairness by 8%"*
- Why: Transparency—managers can understand and trust algorithmic decisions

**Menu Intelligence**
- Produces reasoning for 86 (removal) recommendations
- Explains pricing suggestions with demand/margin context
- Why: Bridges the gap between optimization math and operational intuition

---

**Why Generative AI?**

Raw metrics don't change behavior. A dashboard showing "turn time: 47 min" means nothing without context. LLMs translate data into *decisions*: what to do, why it matters, and how to improve. This is the difference between a reporting tool and an intelligence platform.
