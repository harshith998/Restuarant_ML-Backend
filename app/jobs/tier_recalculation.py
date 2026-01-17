"""
Weekly tier recalculation job - Cron entry point.

Usage:
    # Run via cron (e.g., Sundays at 3am):
    0 3 * * 0 cd /app && python -m app.jobs.tier_recalculation

    # Or run directly:
    python -m app.jobs.tier_recalculation

    # With specific restaurant:
    python -m app.jobs.tier_recalculation --restaurant-id <uuid>

    # Without LLM (math-only scoring):
    python -m app.jobs.tier_recalculation --no-llm
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Callable, Optional
from uuid import UUID

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tier-recalculation")


async def run_weekly_tier_job(
    restaurant_id: Optional[UUID] = None,
    use_llm: bool = True,
    call_llm_func: Optional[Callable] = None,
    llm_model: Optional[str] = None,
) -> dict:
    """
    Main entry point for weekly tier recalculation.

    Can be called from cron, scheduler, or programmatically.

    Args:
        restaurant_id: Specific restaurant, or None for all
        use_llm: Whether to use LLM scoring
        call_llm_func: The call_llm function to use
        llm_model: LLM model identifier

    Returns:
        Dict with job results
    """
    from app.database import get_session_context
    from app.services.tier_job import TierRecalculationJob

    logger.info("Starting weekly tier recalculation job...")

    async with get_session_context() as session:
        job = TierRecalculationJob(
            session=session,
            call_llm_func=call_llm_func,
            llm_model=llm_model,
        )

        result = await job.run(
            restaurant_id=restaurant_id,
            use_llm=use_llm,
        )

        return {
            "success": result.success,
            "waiters_processed": result.waiters_processed,
            "waiters_updated": result.waiters_updated,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }


async def run_with_llm(
    restaurant_id: Optional[UUID] = None,
    llm_model: str = "bytedance-seed/seed-1.6",
) -> dict:
    """
    Run tier recalculation with LLM scoring.

    This version attempts to import and use the call_llm function.

    Args:
        restaurant_id: Specific restaurant, or None for all
        llm_model: LLM model to use

    Returns:
        Dict with job results
    """
    # Try to import call_llm function
    call_llm_func = None
    try:
        # Attempt to import from expected location
        # Adjust this import based on where call_llm is defined
        from app.services.llm_client import call_llm
        call_llm_func = call_llm
        logger.info(f"Using LLM model: {llm_model}")
    except ImportError:
        logger.warning(
            "call_llm function not found, using math-only scoring. "
            "To enable LLM scoring, implement call_llm in app/services/llm_client.py"
        )

    return await run_weekly_tier_job(
        restaurant_id=restaurant_id,
        use_llm=call_llm_func is not None,
        call_llm_func=call_llm_func,
        llm_model=llm_model,
    )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run weekly tier recalculation job"
    )
    parser.add_argument(
        "--restaurant-id",
        type=str,
        default=None,
        help="Specific restaurant UUID (default: all restaurants)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM scoring, use math-only",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="bytedance-seed/seed-1.6",
        help="LLM model to use for scoring",
    )

    args = parser.parse_args()

    # Parse restaurant ID
    restaurant_id = None
    if args.restaurant_id:
        try:
            restaurant_id = UUID(args.restaurant_id)
        except ValueError:
            logger.error(f"Invalid restaurant ID: {args.restaurant_id}")
            sys.exit(1)

    # Run the job
    if args.no_llm:
        result = asyncio.run(
            run_weekly_tier_job(
                restaurant_id=restaurant_id,
                use_llm=False,
            )
        )
    else:
        result = asyncio.run(
            run_with_llm(
                restaurant_id=restaurant_id,
                llm_model=args.llm_model,
            )
        )

    # Log results
    if result["success"]:
        logger.info(
            f"Job completed successfully: "
            f"{result['waiters_processed']} processed, "
            f"{result['waiters_updated']} updated, "
            f"{result['duration_seconds']:.1f}s"
        )
        sys.exit(0)
    else:
        logger.error(f"Job failed with errors: {result['errors']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
