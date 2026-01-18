# Parallel Work Coordination Guide

**Goal:** Implement chatbot feature across 3 Claude terminals in parallel
**Total Time:** 4-5 hours with parallelization (vs 12-14 hours sequential)

---

## Quick Start

### Step 1: Assign Tracks

| Terminal | Track | File | Time | Can Start |
|----------|-------|------|------|-----------|
| Terminal 1 | Track A | [PARALLEL_TRACK_A_GEMINI.md](PARALLEL_TRACK_A_GEMINI.md) | 3-4h | Immediately |
| Terminal 2 | Track B | [PARALLEL_TRACK_B_CONTEXT.md](PARALLEL_TRACK_B_CONTEXT.md) | 4-5h | Immediately |
| Terminal 3 | Track C | [PARALLEL_TRACK_C_ENDPOINT.md](PARALLEL_TRACK_C_ENDPOINT.md) | 4-5h | After A+B Hour 3 |

### Step 2: Open Terminals

```bash
# Terminal 1
cd /path/to/Restuarant_ML-Backend
# Read PARALLEL_TRACK_A_GEMINI.md
# Start with Hour 1

# Terminal 2
cd /path/to/Restuarant_ML-Backend
# Read PARALLEL_TRACK_B_CONTEXT.md
# Start with Hour 1

# Terminal 3 (wait until Hour 3-4)
cd /path/to/Restuarant_ML-Backend
# Read PARALLEL_TRACK_C_ENDPOINT.md
# Start when A & B are ready
```

---

## Track Dependencies

```
┌─────────────┐     ┌─────────────┐
│  Track A    │     │  Track B    │
│  (Gemini)   │     │  (Context)  │
│             │     │             │
│  INDEPENDENT│     │  INDEPENDENT│
└──────┬──────┘     └──────┬──────┘
       │                   │
       │   Both complete   │
       └────────┬──────────┘
                │
                ▼
        ┌───────────────┐
        │   Track C     │
        │  (Endpoint)   │
        │               │
        │  INTEGRATES   │
        │    A + B      │
        └───────────────┘
```

**Key Points:**
- Track A and B are **completely independent** - start both simultaneously
- Track C **depends on both** - start when A & B are ~75% done (Hour 3-4)
- Track C can do stub work while waiting for A & B to finish

---

## Hourly Coordination Schedule

### Hours 1-2: Parallel Foundation

**Terminal 1 (Track A):**
- ✅ Install google-generativeai
- ✅ Update config.py
- ✅ Create gemini_client.py basic structure

**Terminal 2 (Track B):**
- ✅ Create chatbot_context.py
- ✅ Implement review data fetching

**Terminal 3:**
- ⏸️ Wait (or review plans)

---

### Hours 3-4: Core Implementation

**Terminal 1 (Track A):**
- ✅ Complete stream_gemini_response()
- ✅ Complete build_prompt()
- ✅ Run manual tests

**Terminal 2 (Track B):**
- ✅ Add menu data query
- ✅ Add staff data query
- ✅ Add revenue + scheduling queries

**Terminal 3 (Track C):**
- ▶️ START NOW
- ✅ Create chatbot.py with schemas
- ✅ Implement stub endpoint
- ✅ Register router in main.py

---

### Hours 5-6: Integration

**Terminal 1 (Track A):**
- ✅ COMPLETE ✓
- 📤 Handoff `gemini_client.py` to Track C

**Terminal 2 (Track B):**
- ✅ Run manual tests
- ✅ COMPLETE ✓
- 📤 Handoff `chatbot_context.py` to Track C

**Terminal 3 (Track C):**
- ✅ Integrate context assembly (Track B)
- ✅ Integrate Gemini client (Track A)
- ✅ Test full flow

---

### Hours 7-8: Testing & Completion

**All Terminals:**
- Terminal 3 leads final testing
- Terminals 1 & 2 assist with bug fixes if needed
- Document and verify

---

## Communication Protocol

### Handoff Checklist

When Track A or B completes, notify Track C:

**Track A → Track C:**
```
✅ Track A Complete
📁 File: app/services/gemini_client.py
🔧 Functions:
   - stream_gemini_response(prompt: str)
   - build_prompt(context: dict, message: str, history: list)
✔️ Tested: Yes
🐛 Known Issues: None
```

**Track B → Track C:**
```
✅ Track B Complete
📁 File: app/services/chatbot_context.py
🔧 Functions:
   - assemble_restaurant_context(restaurant_id: UUID, session: AsyncSession)
✔️ Tested: Yes (with restaurant_id: YOUR-UUID)
🐛 Known Issues: None
```

---

## Git Workflow (Optional)

If using git branches for coordination:

```bash
# Terminal 1
git checkout -b feature/chatbot-gemini-client
# ... do work ...
git add app/services/gemini_client.py requirements.txt app/config.py
git commit -m "Add Gemini streaming client"
git push origin feature/chatbot-gemini-client

# Terminal 2
git checkout -b feature/chatbot-context-assembly
# ... do work ...
git add app/services/chatbot_context.py
git commit -m "Add restaurant context assembly"
git push origin feature/chatbot-context-assembly

# Terminal 3 (after A & B are merged or available)
git checkout -b feature/chatbot-endpoint
# Pull changes from A & B if needed
# ... do work ...
git add app/api/chatbot.py app/main.py app/api/__init__.py
git commit -m "Add chatbot streaming endpoint"
git push origin feature/chatbot-endpoint
```

**Alternative:** Work on same branch with file locking (terminals work on different files)

---

## Testing Checkpoints

### Checkpoint 1: Track A Complete (Hour 3-4)

```bash
# Terminal 1 runs:
python test_gemini_manual.py

# Expected output:
# ✅ API connects
# ✅ Streaming works
# ✅ Prompt builds correctly
```

### Checkpoint 2: Track B Complete (Hour 5)

```bash
# Terminal 2 runs:
python test_context_manual.py

# Expected output:
# ✅ Review data loaded
# ✅ Menu items found
# ✅ Staff data loaded
# ✅ Revenue calculated
```

### Checkpoint 3: Track C Integration (Hour 6)

```bash
# Terminal 3 runs:
uvicorn app.main:app --reload

# In another terminal:
curl -X POST http://localhost:8000/api/v1/chat/{id}/message \
  -H "Content-Type: application/json" \
  -d '{"message": "How are my reviews?"}'

# Expected output:
# ✅ SSE stream starts
# ✅ Content chunks arrive
# ✅ Response mentions actual data
# ✅ Stream ends cleanly
```

---

## Rollback Plan

If Track C discovers issues with Track A or B:

1. **Issue in Track A (Gemini):**
   - Terminal 1 fixes `gemini_client.py`
   - Terminal 3 pulls changes
   - Retry test

2. **Issue in Track B (Context):**
   - Terminal 2 fixes `chatbot_context.py`
   - Terminal 3 pulls changes
   - Retry test

3. **Issue in Track C (Endpoint):**
   - Terminal 3 fixes `chatbot.py`
   - Retry test

---

## Success Criteria

All tracks complete when:

- [ ] Track A: Gemini client streams responses
- [ ] Track B: Context assembly returns all 6 data sources
- [ ] Track C: Chat endpoint works end-to-end
- [ ] Manual test: Chat about reviews, menu, staff works
- [ ] Error handling: Invalid requests handled gracefully
- [ ] Documentation: All files documented

---

## Time Savings

**Sequential (single developer):**
- Track A: 4 hours
- Track B: 5 hours
- Track C: 5 hours
- **Total: 14 hours**

**Parallel (3 terminals):**
- Tracks A + B: 5 hours (simultaneous)
- Track C: 3 hours (after A+B ready)
- **Total: ~5-6 hours**

**Savings: 8-9 hours (60% faster!)**

---

## Quick Reference

| Need | Command |
|------|---------|
| Test Gemini | `python test_gemini_manual.py` |
| Test Context | `python test_context_manual.py` |
| Start Server | `uvicorn app.main:app --reload` |
| Test Endpoint | `curl -X POST http://localhost:8000/api/v1/chat/{id}/message -H "Content-Type: application/json" -d '{"message": "test"}'` |
| View API Docs | http://localhost:8000/docs |
| Check Logs | `tail -f logs/app.log` (if logging configured) |

---

## Contact Points

If terminals get blocked:

- **Track A blocked?** Check `GOOGLE_API_KEY` is set
- **Track B blocked?** Verify database is running, restaurant exists
- **Track C blocked?** Ensure A + B files exist and import correctly

---

## Final Integration Test

When all tracks complete, run this full test:

```bash
# Terminal 1: Start server
uvicorn app.main:app --reload

# Terminal 2: Test chat flow
curl -X POST http://localhost:8000/api/v1/chat/{restaurant_id}/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Give me a summary of my restaurant performance",
    "history": []
  }'

# Verify response includes:
# ✅ Review data (stars, count)
# ✅ Menu data (top items)
# ✅ Staff data (team size, top performer)
# ✅ Revenue data (today's sales)
# ✅ Coherent, helpful response
```

---

**Good luck! 🚀**
