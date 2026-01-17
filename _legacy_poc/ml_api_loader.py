"""
ML Classification Pipeline

Takes cropped table images from video segmentation and classifies each table's state
(clean/occupied/dirty) using a hosted ML model.

Flow:
1. Receive cropped table images (from video segmentation script)
2. Send each image to ML classification model (Railway/Lambda)
3. Collect all predictions async
4. Form ml_input JSON for the table router
"""

import asyncio
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Try to import aiohttp, but allow fallback for testing
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("Warning: aiohttp not installed. Only mock mode available.")
    print("Install with: pip install aiohttp")

# =============================================================================
# CONFIGURATION - UPDATE THESE WITH ACTUAL ENDPOINTS
# =============================================================================

# Option 1: Railway hosted model
RAILWAY_ENDPOINT = "https://your-model.up.railway.app/predict"

# Option 2: AWS Lambda hosted model
LAMBDA_ENDPOINT = "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/classify"

# Which endpoint to use: "railway" or "lambda"
ACTIVE_ENDPOINT = "railway"

# Request timeout (seconds)
REQUEST_TIMEOUT = 30

# Camera ID (for ml_input JSON)
CAMERA_ID = "CAM_MAIN_01"


# =============================================================================
# PLACEHOLDER: Image Input from Video Segmentation
# =============================================================================

def get_table_images_from_segmentation() -> dict:
    """
    PLACEHOLDER: Get cropped table images from video segmentation script.

    In production, this would receive images via:
    - API call from segmentation service
    - Message queue (Redis, RabbitMQ, etc.)
    - Shared storage (S3, local filesystem)

    Returns:
        dict: {table_id: image_data} where image_data is bytes or base64 string

    Example return:
    {
        "A1": <image_bytes>,
        "A2": <image_bytes>,
        ...
    }
    """
    # PLACEHOLDER - replace with actual implementation
    # This simulates receiving images for all tables

    table_ids = [
        "A1", "A2", "A3",
        "B1", "B2", "B3",
        "C1", "C2", "C3",
        "D1", "D2", "D3"
    ]

    # In production: receive actual image bytes from segmentation
    # For now, return placeholder indicating where images would come from
    return {
        table_id: f"<image_bytes_for_{table_id}>"
        for table_id in table_ids
    }


def load_image_from_file(image_path: str) -> bytes:
    """
    Helper: Load image from file path.
    Use this if segmentation saves images to disk.
    """
    with open(image_path, "rb") as f:
        return f.read()


def encode_image_base64(image_bytes: bytes) -> str:
    """Convert image bytes to base64 string for API transmission."""
    return base64.b64encode(image_bytes).decode("utf-8")


# =============================================================================
# ML MODEL API CLIENTS
# =============================================================================

async def classify_image_railway(
    session,  # aiohttp.ClientSession
    table_id: str,
    image_data: bytes
) -> dict:
    """
    Send image to Railway-hosted classification model.

    Expected API contract:
    - POST request with JSON body
    - Body: {"image": "<base64_encoded_image>"}
    - Response: {"state": "clean|occupied|dirty", "confidence": 0.0-1.0}
    """
    url = RAILWAY_ENDPOINT

    payload = {
        "image": encode_image_base64(image_data) if isinstance(image_data, bytes) else image_data,
        "table_id": table_id  # Optional: for logging on server side
    }

    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    "table_id": table_id,
                    "predicted_state": result.get("state", "unknown"),
                    "state_confidence": result.get("confidence", 0.0),
                    "success": True
                }
            else:
                error_text = await response.text()
                return {
                    "table_id": table_id,
                    "predicted_state": "unknown",
                    "state_confidence": 0.0,
                    "success": False,
                    "error": f"HTTP {response.status}: {error_text}"
                }
    except asyncio.TimeoutError:
        return {
            "table_id": table_id,
            "predicted_state": "unknown",
            "state_confidence": 0.0,
            "success": False,
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "table_id": table_id,
            "predicted_state": "unknown",
            "state_confidence": 0.0,
            "success": False,
            "error": str(e)
        }


async def classify_image_lambda(
    session,  # aiohttp.ClientSession
    table_id: str,
    image_data: bytes
) -> dict:
    """
    Send image to AWS Lambda-hosted classification model.

    Expected API contract (API Gateway + Lambda):
    - POST request with JSON body
    - Body: {"image_base64": "<base64_encoded_image>"}
    - Response: {"prediction": "clean|occupied|dirty", "confidence": 0.0-1.0}

    Note: Lambda has different response format than Railway example
    """
    url = LAMBDA_ENDPOINT

    payload = {
        "image_base64": encode_image_base64(image_data) if isinstance(image_data, bytes) else image_data,
        "table_id": table_id
    }

    headers = {
        "Content-Type": "application/json",
        # Add API key if required:
        # "x-api-key": "your-api-key-here"
    }

    try:
        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as response:
            if response.status == 200:
                result = await response.json()
                # Lambda response format might differ
                return {
                    "table_id": table_id,
                    "predicted_state": result.get("prediction", result.get("state", "unknown")),
                    "state_confidence": result.get("confidence", 0.0),
                    "success": True
                }
            else:
                error_text = await response.text()
                return {
                    "table_id": table_id,
                    "predicted_state": "unknown",
                    "state_confidence": 0.0,
                    "success": False,
                    "error": f"HTTP {response.status}: {error_text}"
                }
    except asyncio.TimeoutError:
        return {
            "table_id": table_id,
            "predicted_state": "unknown",
            "state_confidence": 0.0,
            "success": False,
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "table_id": table_id,
            "predicted_state": "unknown",
            "state_confidence": 0.0,
            "success": False,
            "error": str(e)
        }


async def classify_image(
    session,  # aiohttp.ClientSession
    table_id: str,
    image_data: bytes
) -> dict:
    """
    Route to appropriate ML endpoint based on configuration.
    """
    if ACTIVE_ENDPOINT == "railway":
        return await classify_image_railway(session, table_id, image_data)
    elif ACTIVE_ENDPOINT == "lambda":
        return await classify_image_lambda(session, table_id, image_data)
    else:
        raise ValueError(f"Unknown endpoint type: {ACTIVE_ENDPOINT}")


# =============================================================================
# ASYNC CLASSIFICATION PIPELINE
# =============================================================================

async def classify_all_tables(table_images: dict) -> list:
    """
    Classify all table images concurrently.

    Args:
        table_images: {table_id: image_data} dict

    Returns:
        List of classification results
    """
    async with aiohttp.ClientSession() as session:
        tasks = [
            classify_image(session, table_id, image_data)
            for table_id, image_data in table_images.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions that weren't caught
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                table_id = list(table_images.keys())[i]
                processed_results.append({
                    "table_id": table_id,
                    "predicted_state": "unknown",
                    "state_confidence": 0.0,
                    "success": False,
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        return processed_results


# =============================================================================
# ML INPUT JSON FORMATION
# =============================================================================

def form_ml_input_json(
    classification_results: list,
    camera_id: str = CAMERA_ID,
    timestamp: Optional[str] = None
) -> dict:
    """
    Form the ml_input JSON structure expected by the table router.

    Args:
        classification_results: List of classification results from ML model
        camera_id: Camera identifier
        timestamp: ISO timestamp (defaults to now)

    Returns:
        ml_input dict ready for table router
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    ml_input = {
        "camera_id": camera_id,
        "frame_timestamp": timestamp,
        "tables": []
    }

    for result in classification_results:
        table_entry = {
            "table_id": result["table_id"],
            "predicted_state": result["predicted_state"],
            "state_confidence": result["state_confidence"],
            "last_state_change": timestamp  # In production, track actual state changes
        }
        ml_input["tables"].append(table_entry)

    # Sort by table_id for consistency
    ml_input["tables"].sort(key=lambda t: t["table_id"])

    return ml_input


# =============================================================================
# MAIN PIPELINE
# =============================================================================

async def run_classification_pipeline(table_images: Optional[dict] = None) -> dict:
    """
    Main pipeline: receive images -> classify all -> form ml_input JSON.

    Args:
        table_images: Optional dict of {table_id: image_data}
                     If None, will call get_table_images_from_segmentation()

    Returns:
        ml_input dict ready for table router
    """
    # Step 1: Get images (from segmentation or provided)
    if table_images is None:
        print("Getting table images from segmentation...")
        table_images = get_table_images_from_segmentation()

    print(f"Classifying {len(table_images)} tables...")

    # Step 2: Classify all tables concurrently
    results = await classify_all_tables(table_images)

    # Step 3: Report any failures
    failures = [r for r in results if not r.get("success", False)]
    if failures:
        print(f"Warning: {len(failures)} classification(s) failed:")
        for f in failures:
            print(f"  - {f['table_id']}: {f.get('error', 'unknown error')}")

    successes = [r for r in results if r.get("success", False)]
    print(f"Successfully classified {len(successes)}/{len(results)} tables")

    # Step 4: Form ml_input JSON
    ml_input = form_ml_input_json(results)

    return ml_input


def run_classification_pipeline_sync(table_images: Optional[dict] = None) -> dict:
    """
    Synchronous wrapper for the classification pipeline.
    Use this if calling from non-async code.
    """
    return asyncio.run(run_classification_pipeline(table_images))


# =============================================================================
# MOCK CLASSIFIER FOR TESTING
# =============================================================================

async def classify_image_mock(
    session,  # aiohttp.ClientSession (unused in mock)
    table_id: str,
    image_data: bytes
) -> dict:
    """
    Mock classifier for testing without actual ML model.
    Returns deterministic results based on table_id.
    """
    # Simulate some network delay
    await asyncio.sleep(0.1)

    # Mock predictions (matches our test ML input)
    mock_states = {
        "A1": ("clean", 0.95),
        "A2": ("occupied", 0.98),
        "A3": ("clean", 0.92),
        "B1": ("dirty", 0.89),
        "B2": ("clean", 0.94),
        "B3": ("clean", 0.97),
        "C1": ("occupied", 0.99),
        "C2": ("clean", 0.91),
        "C3": ("dirty", 0.87),
        "D1": ("clean", 0.96),
        "D2": ("clean", 0.93),
        "D3": ("occupied", 0.97),
    }

    state, confidence = mock_states.get(table_id, ("unknown", 0.0))

    return {
        "table_id": table_id,
        "predicted_state": state,
        "state_confidence": confidence,
        "success": True
    }


async def run_mock_pipeline() -> dict:
    """
    Run pipeline with mock classifier (for testing).
    No external dependencies required.
    """
    table_images = get_table_images_from_segmentation()

    # Use mock classifier (no aiohttp session needed for mock)
    results = []
    for table_id, image_data in table_images.items():
        result = await classify_image_mock(None, table_id, image_data)
        results.append(result)

    ml_input = form_ml_input_json(results)
    return ml_input


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("ML CLASSIFICATION PIPELINE")
    print("=" * 60)
    print()

    # Check for --mock flag
    use_mock = "--mock" in sys.argv

    if use_mock:
        print("Running with MOCK classifier (no actual ML calls)")
        print()
        ml_input = asyncio.run(run_mock_pipeline())
    else:
        if not AIOHTTP_AVAILABLE:
            print("ERROR: aiohttp required for real ML calls.")
            print("       Install with: pip install aiohttp")
            print("       Or use --mock flag for testing.")
            sys.exit(1)

        print(f"Active endpoint: {ACTIVE_ENDPOINT.upper()}")
        print(f"Endpoint URL: {RAILWAY_ENDPOINT if ACTIVE_ENDPOINT == 'railway' else LAMBDA_ENDPOINT}")
        print()
        print("NOTE: This will fail without actual ML endpoints configured.")
        print("      Use --mock flag for testing without ML model.")
        print()
        ml_input = run_classification_pipeline_sync()

    print()
    print("=" * 60)
    print("GENERATED ML_INPUT JSON")
    print("=" * 60)
    print(json.dumps(ml_input, indent=2))
