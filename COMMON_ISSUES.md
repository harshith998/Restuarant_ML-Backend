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

### Mutable Column Defaults
**Problem**: Using `default=dict` or `default=[]` in mapped columns shares a single
mutable object across instances, causing state leakage.
**Solution**: Use a callable factory like `default=lambda: {}` or a dedicated
factory function to create a new object per instance.

### Async Session Delete
**Problem**: `session.delete()` is synchronous on `AsyncSession`; awaiting it
raises a runtime error.
**Solution**: Call `session.delete(entry)` without `await`, then commit/flush.

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

### Response Model Mismatch
**Problem**: Endpoints declare `response_model` but return raw dicts on some
paths, causing inconsistent validation and response shapes.
**Solution**: Always return model instances (or validate dicts into models)
across all branches to match the declared response type.

## Docker

### Volume Permissions
(To be populated as issues arise)

---

## How to Add Issues

When you encounter an issue:
1. Add it under the appropriate category
2. Include **Problem** and **Solution**
3. Add code examples if helpful
