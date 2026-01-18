"""
Table State Classification using SAM3
Classifies table images into: clean, dirty, or occupied.

- Occupied: Person detected
- Dirty: No person, but plate(s) detected
- Clean: No person, no plates

Usage:
    python classify_tables.py --input <folder_of_images> [--output <results.json>] [--render]
"""

import argparse
import json
import torch
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from transformers import Sam3Processor, Sam3Model

# Detection thresholds
PERSON_THRESHOLD = 0.5
PLATE_THRESHOLD = 0.4

# =============================================================================
# SAM3 DETECTION
# =============================================================================

def detect_objects(model, processor, image_path, prompt, device, threshold=0.5):
    """Run SAM3 detection for a specific prompt. Returns detections and masks."""
    image = Image.open(image_path).convert("RGB")

    inputs = processor(
        images=image,
        text=prompt,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_instance_segmentation(
        outputs,
        threshold=threshold,
        mask_threshold=0.5,
        target_sizes=inputs.get("original_sizes").tolist()
    )[0]

    masks = results.get("masks", [])
    scores = results.get("scores", [])

    detections = []
    mask_arrays = []
    if masks is not None and len(masks) > 0:
        for i, mask in enumerate(masks):
            score = scores[i].item() if torch.is_tensor(scores[i]) else scores[i]
            detections.append({
                "score": round(score, 4),
                "mask_area": int(mask.sum().item()) if torch.is_tensor(mask) else int(mask.sum())
            })
            # Convert mask to numpy
            if torch.is_tensor(mask):
                mask_arrays.append(mask.cpu().numpy())
            else:
                mask_arrays.append(mask)

    return detections, mask_arrays


def classify_image(model, processor, image_path, device):
    """Classify a single image as clean, dirty, or occupied.

    Returns: (classification, details, masks_dict)
    """
    masks_dict = {"person": [], "plate": []}

    # Check for people first
    person_detections, person_masks = detect_objects(
        model, processor, image_path, "person", device, PERSON_THRESHOLD
    )
    masks_dict["person"] = person_masks

    if person_detections:
        return "occupied", {
            "person_detections": len(person_detections),
            "person_scores": [d["score"] for d in person_detections]
        }, masks_dict

    # No people - check for plates
    plate_detections, plate_masks = detect_objects(
        model, processor, image_path, "plate", device, PLATE_THRESHOLD
    )
    masks_dict["plate"] = plate_masks

    if plate_detections:
        return "dirty", {
            "plate_detections": len(plate_detections),
            "plate_scores": [d["score"] for d in plate_detections]
        }, masks_dict

    return "clean", {}, masks_dict


def render_masks(image_path, masks_dict, classification, output_path):
    """Render masks overlaid on image and save."""
    image = cv2.imread(str(image_path))
    if image is None:
        return False

    overlay = image.copy()

    # Colors: person=red, plate=blue
    colors = {
        "person": (0, 0, 255),   # Red (BGR)
        "plate": (255, 165, 0)   # Orange (BGR)
    }

    # Draw masks
    for obj_type, masks in masks_dict.items():
        color = colors.get(obj_type, (0, 255, 0))
        for mask in masks:
            mask_bool = mask.astype(bool)
            overlay[mask_bool] = color

    # Blend overlay
    result = cv2.addWeighted(image, 0.6, overlay, 0.4, 0)

    # Add classification label
    label_colors = {
        "clean": (0, 255, 0),     # Green
        "dirty": (0, 165, 255),   # Orange
        "occupied": (0, 0, 255)   # Red
    }
    label_color = label_colors.get(classification, (255, 255, 255))

    cv2.putText(result, classification.upper(), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, label_color, 2)

    # Add legend
    y_offset = 60
    for obj_type, masks in masks_dict.items():
        if masks:
            color = colors.get(obj_type, (0, 255, 0))
            cv2.putText(result, f"{obj_type}: {len(masks)}", (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y_offset += 25

    cv2.imwrite(str(output_path), result)
    return True


# =============================================================================
# MAIN
# =============================================================================

def find_images(input_dir):
    """Find all images in the input directory."""
    images = []
    valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']

    input_path = Path(input_dir)

    for img_file in sorted(input_path.iterdir()):
        if img_file.is_file() and img_file.suffix.lower() in valid_extensions:
            images.append({
                "path": img_file,
                "name": img_file.stem
            })

    return images


def main():
    parser = argparse.ArgumentParser(
        description="Classify table images as clean, dirty, or occupied using SAM3"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input folder containing images to classify"
    )
    parser.add_argument(
        "--output", "-o",
        default="classification_results.json",
        help="Output JSON file for results (default: classification_results.json)"
    )
    parser.add_argument(
        "--render", "-r",
        action="store_true",
        help="Output rendered images with mask overlays"
    )
    parser.add_argument(
        "--render-dir",
        default=None,
        help="Directory for rendered images (default: <input>_renders)"
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_file = Path(args.output)
    render_enabled = args.render
    render_dir = Path(args.render_dir) if args.render_dir else input_dir.parent / f"{input_dir.name}_renders"

    print("=" * 60)
    print("Table State Classification (SAM3)")
    print("=" * 60)

    # Validate input
    if not input_dir.exists():
        print(f"ERROR: Input directory not found: {input_dir}")
        return

    # Check for CUDA
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nDevice: {device}")

    if device == "cpu":
        print("WARNING: Running on CPU will be slow. GPU recommended.")

    # Find images
    print(f"\nSearching for images in: {input_dir}")
    images = find_images(input_dir)

    if not images:
        print("ERROR: No images found!")
        return

    print(f"Found {len(images)} image(s) to classify")

    # Create render directory if needed
    if render_enabled:
        render_dir.mkdir(parents=True, exist_ok=True)
        print(f"Render output: {render_dir}")

    # Load SAM3 model
    print("\nLoading SAM3 model (facebook/sam3)...")
    model = Sam3Model.from_pretrained("facebook/sam3")
    processor = Sam3Processor.from_pretrained("facebook/sam3")

    if device == "cuda":
        model = model.to(device, dtype=torch.bfloat16)
    else:
        model = model.to(device)

    model.eval()
    print("Model loaded!")

    # Classify each image
    print(f"\nClassifying {len(images)} images...")
    print("-" * 60)

    results = {
        "input_dir": str(input_dir),
        "render_dir": str(render_dir) if render_enabled else None,
        "summary": {},
        "classifications": []
    }

    counts = {"clean": 0, "dirty": 0, "occupied": 0}

    for i, img_info in enumerate(images):
        image_path = img_info["path"]
        print(f"[{i+1}/{len(images)}] {img_info['name']}...", end=" ")

        try:
            classification, details, masks_dict = classify_image(model, processor, image_path, device)
            counts[classification] += 1

            entry = {
                "image": img_info["name"],
                "file": image_path.name,
                "classification": classification,
                "details": details
            }

            # Render masks if enabled
            if render_enabled:
                render_path = render_dir / f"{img_info['name']}_{classification}.jpg"
                render_masks(image_path, masks_dict, classification, render_path)
                entry["render_file"] = render_path.name

            results["classifications"].append(entry)

            print(f"{classification.upper()}", end="")
            if details:
                if "person_detections" in details:
                    print(f" ({details['person_detections']} person(s))", end="")
                if "plate_detections" in details:
                    print(f" ({details['plate_detections']} plate(s))", end="")
            print()

        except Exception as e:
            print(f"ERROR: {e}")
            results["classifications"].append({
                "image": img_info["name"],
                "file": image_path.name,
                "classification": "error",
                "error": str(e)
            })

    # Summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total = len(images)
    results["summary"] = {
        "total_images": total,
        "clean": counts["clean"],
        "dirty": counts["dirty"],
        "occupied": counts["occupied"],
        "clean_pct": round(100 * counts["clean"] / total, 1) if total > 0 else 0,
        "dirty_pct": round(100 * counts["dirty"] / total, 1) if total > 0 else 0,
        "occupied_pct": round(100 * counts["occupied"] / total, 1) if total > 0 else 0
    }

    print(f"\nTotal images: {total}")
    print(f"  Clean:    {counts['clean']:3d} ({results['summary']['clean_pct']:.1f}%)")
    print(f"  Dirty:    {counts['dirty']:3d} ({results['summary']['dirty_pct']:.1f}%)")
    print(f"  Occupied: {counts['occupied']:3d} ({results['summary']['occupied_pct']:.1f}%)")

    # Save results
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
