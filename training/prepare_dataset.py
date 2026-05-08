"""Convert HRSC2016 (or any COCO ship dataset) to VLM fine-tuning JSONL.

Supports:
  * HRSC2016 PASCAL-VOC-style XML annotations
  * Generic COCO JSON
  * 5x augmentation (hflip, vflip, 90° rotate, brightness/contrast)

Output schema (one JSON line per sample):
  {
    "image": "images/0001.jpg",
    "conversations": [
      {"from": "human", "value": "Detect all ships ..."},
      {"from": "gpt", "value": "[{\\"label\\": \\"cargo_ship\\", \\"bbox\\": [...]}, ...]"}
    ]
  }
"""

import json
import os
import random
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


def convert_hrsc2016(
    hrsc_root: str,
    output_dir: str,
    max_samples: int | None = None,
    augment: int = 1,
) -> str:
    images_dir = Path(hrsc_root) / "AllImages"
    annots_dir = Path(hrsc_root) / "Annotations"
    out_path = Path(output_dir)
    out_images = out_path / "images"
    out_images.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_path / "train.jsonl"
    base_count = 0
    aug_count = 0
    rng = random.Random(42)

    with open(jsonl_path, "w") as f:
        for xml_file in sorted(annots_dir.glob("*.xml")):
            if max_samples and base_count >= max_samples:
                break

            tree = ET.parse(xml_file)
            root = tree.getroot()

            filename = root.findtext("Img_FileName")
            if not filename:
                filename = f"{xml_file.stem}.bmp"

            img_path = images_dir / filename
            if not img_path.exists():
                for ext in [".jpg", ".jpeg", ".png", ".bmp"]:
                    alt = images_dir / f"{xml_file.stem}{ext}"
                    if alt.exists():
                        img_path = alt
                        break
                else:
                    continue

            img = Image.open(img_path).convert("RGB")
            img_w, img_h = img.size

            base_detections = []
            for obj in root.iter("HRSC_Object"):
                class_id = obj.findtext("Class_ID", "")
                xmin = obj.findtext("box_xmin")
                ymin = obj.findtext("box_ymin")
                xmax = obj.findtext("box_xmax")
                ymax = obj.findtext("box_ymax")

                if not all([xmin, ymin, xmax, ymax]):
                    continue

                bbox = [
                    float(xmin) / img_w, float(ymin) / img_h,
                    float(xmax) / img_w, float(ymax) / img_h,
                ]
                bbox = [round(max(0.0, min(1.0, v)), 4) for v in bbox]
                label = _hrsc_class_to_label(class_id)
                base_detections.append({"label": label, "bbox": bbox})

            if not base_detections:
                continue

            base_name = f"{xml_file.stem}.jpg"
            img.save(out_images / base_name, "JPEG", quality=92)
            _write_sample(f, f"images/{base_name}", base_detections)
            base_count += 1

            for aug_idx in range(1, augment):
                aug_img, aug_dets = _apply_augmentation(img, base_detections, aug_idx, rng)
                if aug_img is None:
                    continue
                aug_name = f"{xml_file.stem}_aug{aug_idx}.jpg"
                aug_img.save(out_images / aug_name, "JPEG", quality=92)
                _write_sample(f, f"images/{aug_name}", aug_dets)
                aug_count += 1

    total = base_count + aug_count
    print(f"[prepare_dataset] Wrote {total} samples ({base_count} base + {aug_count} augmented) to {jsonl_path}")
    return str(jsonl_path)


def _write_sample(f, image_rel_path: str, detections: list):
    response = json.dumps(detections)
    sample = {
        "image": image_rel_path,
        "conversations": [
            {
                "from": "human",
                "value": (
                    "Detect all ships and vessels in this satellite image. "
                    "Return a JSON array where each element has "
                    '"label" and "bbox" [x1, y1, x2, y2] normalized to [0, 1].'
                ),
            },
            {"from": "gpt", "value": response},
        ],
    }
    f.write(json.dumps(sample) + "\n")


def _apply_augmentation(img: Image.Image, detections: list, aug_idx: int, rng: random.Random):
    """Apply augmentation #aug_idx (1=hflip, 2=vflip, 3=rotate90, 4=brightness/contrast)."""
    new_detections = []
    new_img = img

    if aug_idx == 1:
        new_img = ImageOps.mirror(img)
        for d in detections:
            x1, y1, x2, y2 = d["bbox"]
            new_detections.append({
                "label": d["label"],
                "bbox": [round(1 - x2, 4), y1, round(1 - x1, 4), y2],
            })
    elif aug_idx == 2:
        new_img = ImageOps.flip(img)
        for d in detections:
            x1, y1, x2, y2 = d["bbox"]
            new_detections.append({
                "label": d["label"],
                "bbox": [x1, round(1 - y2, 4), x2, round(1 - y1, 4)],
            })
    elif aug_idx == 3:
        new_img = img.transpose(Image.Transpose.ROTATE_270)
        for d in detections:
            x1, y1, x2, y2 = d["bbox"]
            new_detections.append({
                "label": d["label"],
                "bbox": [round(1 - y2, 4), x1, round(1 - y1, 4), x2],
            })
    elif aug_idx == 4:
        b = ImageEnhance.Brightness(img).enhance(rng.uniform(0.7, 1.3))
        new_img = ImageEnhance.Contrast(b).enhance(rng.uniform(0.8, 1.2))
        new_detections = detections
    else:
        return None, None

    return new_img, new_detections


def convert_coco_ships(
    coco_json: str,
    images_dir: str,
    output_dir: str,
    ship_category_names: list[str] | None = None,
    max_samples: int | None = None,
) -> str:
    with open(coco_json) as f:
        coco = json.load(f)

    cat_lookup = {c["id"]: c["name"] for c in coco["categories"]}
    if ship_category_names:
        valid_cats = {
            cid for cid, name in cat_lookup.items() if name.lower() in [s.lower() for s in ship_category_names]
        }
    else:
        valid_cats = set(cat_lookup.keys())

    img_lookup = {img["id"]: img for img in coco["images"]}
    img_anns: dict[int, list] = {}
    for ann in coco["annotations"]:
        if ann["category_id"] in valid_cats:
            img_anns.setdefault(ann["image_id"], []).append(ann)

    out_path = Path(output_dir)
    out_images = out_path / "images"
    out_images.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_path / "train.jsonl"
    count = 0

    with open(jsonl_path, "w") as f:
        for img_id, anns in sorted(img_anns.items()):
            if max_samples and count >= max_samples:
                break

            img_info = img_lookup[img_id]
            img_w, img_h = img_info["width"], img_info["height"]
            src_path = Path(images_dir) / img_info["file_name"]
            if not src_path.exists():
                continue

            out_img_name = f"{img_id:012d}.jpg"
            img = Image.open(src_path).convert("RGB")
            img.save(out_images / out_img_name, "JPEG", quality=95)

            detections = []
            for ann in anns:
                x, y, w, h = ann["bbox"]
                bbox = [
                    round(x / img_w, 4),
                    round(y / img_h, 4),
                    round((x + w) / img_w, 4),
                    round((y + h) / img_h, 4),
                ]
                bbox = [max(0.0, min(1.0, v)) for v in bbox]
                label = cat_lookup[ann["category_id"]].lower().replace(" ", "_")
                detections.append({"label": label, "bbox": bbox})

            response_text = json.dumps(detections)
            sample = {
                "image": f"images/{out_img_name}",
                "conversations": [
                    {
                        "from": "human",
                        "value": (
                            "Detect all ships and vessels in this satellite image. "
                            "Return a JSON array where each element has "
                            '"label" and "bbox" [x1, y1, x2, y2] normalized to [0, 1].'
                        ),
                    },
                    {"from": "gpt", "value": response_text},
                ],
            }
            f.write(json.dumps(sample) + "\n")
            count += 1

    print(f"[prepare_dataset] Wrote {count} samples to {jsonl_path}")
    return str(jsonl_path)


def _hrsc_class_to_label(class_id: str) -> str:
    """Map HRSC2016 class IDs (e.g. '100000018') to readable vessel labels."""
    mapping = {
        "100000001": "ship",
        "100000002": "aircraft_carrier",
        "100000003": "warcraft",
        "100000004": "merchant_ship",
        "100000005": "nimitz_carrier",
        "100000006": "enterprise_carrier",
        "100000007": "arleigh_burke_destroyer",
        "100000008": "whidbey_island_landing",
        "100000009": "perry_frigate",
        "100000010": "sanantonio_landing",
        "100000011": "ticonderoga_cruiser",
        "100000012": "kitty_hawk_carrier",
        "100000013": "kuznetsov_carrier",
        "100000014": "abukuma_frigate",
        "100000015": "austen_landing",
        "100000016": "tarawa_assault",
        "100000017": "blue_ridge_command",
        "100000018": "container_ship",
        "100000019": "oxcart_carrier",
        "100000020": "car_carrier",
        "100000022": "hovercraft",
        "100000024": "yacht",
        "100000025": "container_ship",
        "100000026": "cruise_ship",
        "100000027": "submarine",
        "100000028": "lute_frigate",
        "100000029": "medical_ship",
        "100000030": "car_carrier_v2",
        "100000031": "ford_carrier",
        "100000032": "midway_carrier",
        "100000033": "invincible_carrier",
    }
    return mapping.get(class_id, "unknown_vessel")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare ship detection dataset for VLM fine-tuning")
    parser.add_argument("--format", choices=["hrsc2016", "coco"], required=True)
    parser.add_argument("--input", required=True, help="Dataset root or COCO JSON path")
    parser.add_argument("--images-dir", help="Images directory (COCO only)")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--augment", type=int, default=1,
                        help="Augmentation multiplier (1=none, 5=5x via flips/rotate/jitter)")

    args = parser.parse_args()

    if args.format == "hrsc2016":
        convert_hrsc2016(args.input, args.output, args.max_samples, augment=args.augment)
    elif args.format == "coco":
        if not args.images_dir:
            parser.error("--images-dir required for COCO format")
        convert_coco_ships(args.input, args.images_dir, args.output, max_samples=args.max_samples)
