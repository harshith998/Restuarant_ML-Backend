# Common Issues & Solutions

## Database

### Connection Issues
(To be populated as issues arise)

### Migration Conflicts
(To be populated as issues arise)

## SQLAlchemy

### Circular Imports
**Problem**: Models importing each other causes circular import errors.
**Solution**: Use `from __future__ import annotations` and string references for relationships.

### N+1 Query Problems
**Problem**: Lazy loading causes multiple queries.
**Solution**: Use `selectinload()` or `joinedload()` for eager loading.

## Pydantic

### Forward References
**Problem**: Model A references Model B before B is defined.
**Solution**: Use string annotations and call `model_rebuild()` after all models defined.

## Alembic

### Autogenerate Missing Changes
**Problem**: `--autogenerate` doesn't detect all changes.
**Solution**: Ensure all models are imported in `alembic/env.py`.

## FastAPI

### Async Session Issues
(To be populated as issues arise)

## Docker

### Volume Permissions
(To be populated as issues arise)

---

## How to Add Issues

When you encounter an issue:
1. Add it under the appropriate category
2. Include **Problem** and **Solution**
3. Add code examples if helpful
