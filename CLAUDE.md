# Restaurant Intelligence Platform

## Related Documentation
- **PROGRESS.md** - Current state, what's done, next steps for handoff
- **COMMON_ISSUES.md** - Known issues and solutions
- **PRD.md** - Full product requirements
- **SERVICES.md** - External service specs

## Engineering Principles
- **DRY** - Extract shared logic to services/utils
- **SOLID**:
  - Single Responsibility - One class/function = one job
  - Open/Closed - Extend behavior without modifying existing code
  - Liskov Substitution - Subtypes must be substitutable
  - Interface Segregation - Small, focused interfaces
  - Dependency Inversion - Depend on abstractions, not concretions
- **KISS** - Keep implementations simple
- **YAGNI** - Don't build until needed
- **Separation of Concerns** - Models, schemas, services, routes in separate layers

## Code Standards
- Async/await for all DB operations
- Type hints everywhere
- Pydantic for validation at boundaries
- Repository pattern for DB access
- Service layer for business logic
- Use `from __future__ import annotations` for forward references

## Project Structure
```
app/
├── __init__.py
├── main.py              # FastAPI app entry
├── config.py            # Settings/environment
├── database.py          # DB connection/session
├── models/              # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── api/                 # Route handlers
├── services/            # Business logic
└── websocket/           # WebSocket handlers
```

## Agent Protocol
1. Read PROGRESS.md first to understand current state
2. Check COMMON_ISSUES.md for known pitfalls
3. Update PROGRESS.md after completing work
4. Add any new issues to COMMON_ISSUES.md

## Key PRD References
- **Schema**: PRD.md Section 5 (PostgreSQL tables)
- **Routing Algorithm**: PRD.md Section 4.2
- **API Endpoints**: PRD.md Section 6
- **Waiter Scoring**: PRD.md Appendix A

## Testing Philosophy

Tests simulate **real-world restaurant scenarios**, not abstract unit tests:

### Test Data Principles
- **Realistic fixtures**: "The Golden Fork" restaurant with Bar, Main Floor, Patio sections
- **Varied waiter skill levels**: Alice (strong), Bob (standard), Carol (developing), Dave (on break)
- **Mixed table states**: Clean, occupied, dirty, unavailable
- **Active shifts**: With real tips, covers, tables served

### What Tests Should Cover
1. **Happy paths**: Standard operations work correctly
2. **Edge cases**: Boundary conditions (party of 1, party of 20)
3. **Real scenarios**: Seating from waitlist, completing visits, payments
4. **Validation**: Schema rejects invalid real-world input

### Test Organization
```
tests/
├── conftest.py      # Fixtures: restaurant, sections, tables, waiters, shifts
├── test_models.py   # SQLAlchemy model tests
├── test_schemas.py  # Pydantic validation tests
└── test_*.py        # Additional test modules
```

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_models.py

# Run specific test
pytest tests/test_models.py::TestTableModel::test_find_available_tables_for_party
```

## Common Commands
```bash
# Start PostgreSQL
docker-compose up -d db

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload

# Generate migration
alembic revision --autogenerate -m "description"

# Run tests
pytest
```
