"""Combine HRSC2016 + ShipRSImageNet + MASATI v2 into a unified VLM training set.

Each dataset contributes complementary signal:
  * HRSC2016 (~1k)        — multi-class ship taxonomy, high-res aerial
  * ShipRSImageNet (~3.4k) — fine-grained ship classes (50+ types), satellite
  * MASATI v2 (~2.5k)      — maritime aerial at Sentinel-2-comparable resolution

With 5x augmentation (flip / rotate / brightness) the combined corpus is ~35k
samples. Output is JSONL where each line is one (image, prompt, response) row.

Usage:
    python multi_dataset.py \\
        --hrsc ./data/HRSC2016 \\
        --shiprs ./data/ShipRSImageNet \\
        --masati ./data/masati-v2 \\
        --output ./data/ship_combined \\
        --augment 5
"""

import argparse
import csv
import json
import random
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from prepare_dataset import (
    convert_hrsc2016,
    _write_sample,
    _apply_augmentation,
    _hrsc_class_to_label,
)


def convert_shiprs_imagenet(
    root: str,
    output_dir: str,
    output_jsonl,
    out_images: Path,
    augment: int = 1,
    rng: random.Random = None,
):
    rng = rng or random.Random(42)
    root_path = Path(root)

    yaml_path = root_path / "data.yaml"
    class_names = None
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path) as yf:
                meta = yaml.safe_load(yf)
                class_names = meta.get("names")
        except Exception:
            pass

    if not class_names:
        print(f"[shiprs] SKIP — could not load data.yaml from {root}")
        return 0

    base_count, aug_count = 0, 0

    for split in ["train", "valid", "test"]:
        images_dir = root_path / split / "images"
        labels_dir = root_path / split / "labels"
        if not images_dir.exists() or not labels_dir.exists():
            continue

        for label_file in sorted(labels_dir.glob("*.txt")):
            img_path = None
            for ext in [".jpg", ".jpeg", ".png", ".bmp"]:
                candidate = images_dir / f"{label_file.stem}{ext}"
                if candidate.exists():
                    img_path = candidate
                    break
            if not img_path:
                continue

            try:
                img = Image.open(img_path).convert("RGB")
            except Exception:
                continue

            detections = []
            with open(label_file) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) != 5:
                        continue
                    try:
                        cls = int(parts[0])
                        cx, cy, w, h = map(float, parts[1:])
                    except ValueError:
                        continue

                    if cls < 0 or cls >= len(class_names):
                        continue

                    label = class_names[cls].lower().replace("-", "_").replace(" ", "_")
                    bbox = [
                        round(max(0, cx - w / 2), 4),
                        round(max(0, cy - h / 2), 4),
                        round(min(1, cx + w / 2), 4),
                        round(min(1, cy + h / 2), 4),
                    ]
                    detections.append({"label": label, "bbox": bbox})

            if not detections:
                continue

            base_name = f"shiprs_{split}_{label_file.stem}.jpg"
            img.save(out_images / base_name, "JPEG", quality=92)
            _write_sample(output_jsonl, f"images/{base_name}", detections)
            base_count += 1

            for aug_idx in range(1, augment):
                aug_img, aug_dets = _apply_augmentation(img, detections, aug_idx, rng)
                if aug_img is None:
                    continue
                aug_name = f"shiprs_{split}_{label_file.stem}_aug{aug_idx}.jpg"
                aug_img.save(out_images / aug_name, "JPEG", quality=92)
                _write_sample(output_jsonl, f"images/{aug_name}", aug_dets)
                aug_count += 1

    print(f"[shiprs] Wrote {base_count} base + {aug_count} augmented = {base_count + aug_count} samples")
    return base_count + aug_count


def convert_masati_v2(
    root: str,
    output_jsonl,
    out_images: Path,
    augment: int = 1,
    rng: random.Random = None,
):
    rng = rng or random.Random(42)
    root_path = Path(root)
    images_dir = root_path / "images"
    labels_dir = root_path / "labels"

    if not images_dir.exists() or not labels_dir.exists():
        for sub in root_path.iterdir():
            if sub.is_dir() and (sub / "images").exists() and (sub / "labels").exists():
                images_dir = sub / "images"
                labels_dir = sub / "labels"
                break

    if not images_dir.exists() or not labels_dir.exists():
        print(f"[masati] SKIP — could not find images/ + labels/ in {root}")
        return 0

    yaml_path = root_path / "data.yaml"
    masati_names = None
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path) as yf:
                meta = yaml.safe_load(yf)
                masati_names = meta.get("names")
                if isinstance(masati_names, dict):
                    masati_names = [masati_names[i] for i in sorted(masati_names.keys())]
        except Exception:
            pass

    default_names = ["ship", "detail", "multi", "coast", "water", "land", "coast_ship"]
    if not masati_names:
        masati_names = default_names

    SKIP_CLASSES = {"water", "land", "coast"}

    base_count, aug_count = 0, 0

    for label_file in sorted(labels_dir.glob("*.txt")):
        img_path = None
        for ext in [".png", ".jpg", ".jpeg", ".bmp"]:
            candidate = images_dir / f"{label_file.stem}{ext}"
            if candidate.exists():
                img_path = candidate
                break
        if not img_path:
            continue

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            continue

        detections = []
        with open(label_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 5:
                    continue
                try:
                    cls = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:])
                except ValueError:
                    continue

                if cls < 0 or cls >= len(masati_names):
                    continue
                label = masati_names[cls].lower().replace("-", "_").replace(" ", "_")
                if label in SKIP_CLASSES:
                    continue

                bbox = [
                    round(max(0, cx - w / 2), 4),
                    round(max(0, cy - h / 2), 4),
                    round(min(1, cx + w / 2), 4),
                    round(min(1, cy + h / 2), 4),
                ]
                detections.append({"label": label, "bbox": bbox})

        if not detections:
            continue

        base_name = f"masati_{label_file.stem}.jpg"
        img.save(out_images / base_name, "JPEG", quality=92)
        _write_sample(output_jsonl, f"images/{base_name}", detections)
        base_count += 1

        for aug_idx in range(1, augment):
            aug_img, aug_dets = _apply_augmentation(img, detections, aug_idx, rng)
            if aug_img is None:
                continue
            aug_name = f"masati_{label_file.stem}_aug{aug_idx}.jpg"
            aug_img.save(out_images / aug_name, "JPEG", quality=92)
            _write_sample(output_jsonl, f"images/{aug_name}", aug_dets)
            aug_count += 1

    print(f"[masati] Wrote {base_count} base + {aug_count} augmented = {base_count + aug_count} samples")
    return base_count + aug_count


def convert_airbus_ships(
    root: str,
    output_dir: str,
    output_jsonl,
    out_images: Path,
    augment: int = 1,
    max_samples: int = 10000,
    rng: random.Random = None,
):
    rng = rng or random.Random(42)
    csv_path = Path(root) / "train_ship_segmentations_v2.csv"
    images_dir = Path(root) / "train_v2"

    if not csv_path.exists():
        print(f"[airbus] SKIP — {csv_path} not found")
        return 0
    if not images_dir.exists():
        print(f"[airbus] SKIP — {images_dir} not found")
        return 0

    image_rles: dict[str, list[str]] = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            img_id = row["ImageId"]
            rle = row.get("EncodedPixels") or ""
            if rle.strip():
                image_rles.setdefault(img_id, []).append(rle.strip())

    base_count, aug_count = 0, 0
    image_ids = list(image_rles.keys())
    rng.shuffle(image_ids)

    for img_id in image_ids:
        if base_count >= max_samples:
            break
        img_path = images_dir / img_id
        if not img_path.exists():
            continue

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            continue
        img_w, img_h = img.size

        detections = []
        for rle in image_rles[img_id]:
            bbox = _rle_to_bbox(rle, img_w, img_h)
            if bbox is None:
                continue
            detections.append({"label": "ship", "bbox": bbox})

        if not detections:
            continue

        base_name = f"airbus_{img_id.replace('.jpg', '')}.jpg"
        img.save(out_images / base_name, "JPEG", quality=92)
        _write_sample(output_jsonl, f"images/{base_name}", detections)
        base_count += 1

        for aug_idx in range(1, augment):
            aug_img, aug_dets = _apply_augmentation(img, detections, aug_idx, rng)
            if aug_img is None:
                continue
            aug_name = f"airbus_{img_id.replace('.jpg', '')}_aug{aug_idx}.jpg"
            aug_img.save(out_images / aug_name, "JPEG", quality=92)
            _write_sample(output_jsonl, f"images/{aug_name}", aug_dets)
            aug_count += 1

    print(f"[airbus] Wrote {base_count} base + {aug_count} augmented = {base_count + aug_count} samples")
    return base_count + aug_count


def _rle_to_bbox(rle_str: str, w: int, h: int) -> list[float] | None:
    """Convert Kaggle RLE (run-length encoded mask) to a normalized bbox.

    Airbus RLE format: pairs of (start_pixel, run_length), 1-indexed, column-major.
    """
    try:
        pairs = list(map(int, rle_str.split()))
    except ValueError:
        return None
    if len(pairs) < 2 or len(pairs) % 2 != 0:
        return None

    starts = pairs[0::2]
    lengths = pairs[1::2]

    xs, ys = [], []
    for s, l in zip(starts, lengths):
        for offset in (0, l - 1):
            p = s + offset - 1
            x = p // h
            y = p % h
            xs.append(x)
            ys.append(y)

    if not xs or not ys:
        return None

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_max += 1
    y_max += 1

    return [
        round(max(0, min(1, x_min / w)), 4),
        round(max(0, min(1, y_min / h)), 4),
        round(max(0, min(1, x_max / w)), 4),
        round(max(0, min(1, y_max / h)), 4),
    ]


def _normalize_ship_label(name: str) -> str:
    """Map ShipRSImageNet class names to GhostWatch labels."""
    name_lower = name.lower().replace("-", "_").replace(" ", "_")
    if any(k in name_lower for k in ["cargo", "container", "merchant"]):
        return "cargo_ship"
    if any(k in name_lower for k in ["tanker", "oil"]):
        return "tanker"
    if any(k in name_lower for k in ["fishing", "trawler"]):
        return "fishing_boat"
    if any(k in name_lower for k in ["patrol", "warship", "destroyer", "frigate", "cruiser", "carrier", "submarine"]):
        return "patrol_vessel"
    if any(k in name_lower for k in ["yacht", "sailboat"]):
        return "sailboat"
    if any(k in name_lower for k in ["ferry", "passenger", "cruise"]):
        return "passenger_ferry"
    if "tug" in name_lower:
        return "tugboat"
    return "unknown_vessel"


def main():
    parser = argparse.ArgumentParser(description="Build combined ship dataset for VLM fine-tuning")
    parser.add_argument("--hrsc", help="Path to HRSC2016 dataset root")
    parser.add_argument("--shiprs", help="Path to ShipRSImageNet dataset root")
    parser.add_argument("--airbus", help="Path to Airbus Ship Detection dataset root")
    parser.add_argument("--masati", help="Path to MASATI v2 dataset root")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--augment", type=int, default=5, help="Augmentation multiplier")
    parser.add_argument("--airbus-max", type=int, default=10000, help="Max base samples from Airbus")

    args = parser.parse_args()

    output_path = Path(args.output)
    out_images = output_path / "images"
    out_images.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_path / "train.jsonl"
    rng = random.Random(42)
    total = 0

    with open(jsonl_path, "w") as f:
        if args.hrsc:
            print(f"\n=== HRSC2016 ===")
            from prepare_dataset import convert_hrsc2016 as _conv
            import tempfile, shutil
            with tempfile.TemporaryDirectory() as tmpdir:
                _conv(args.hrsc, tmpdir, augment=args.augment)
                tmp_jsonl = Path(tmpdir) / "train.jsonl"
                tmp_images = Path(tmpdir) / "images"
                if tmp_jsonl.exists():
                    n = 0
                    with open(tmp_jsonl) as src:
                        for line in src:
                            sample = json.loads(line)
                            old_img = sample["image"]
                            new_name = f"hrsc_{Path(old_img).name}"
                            shutil.copy(Path(tmpdir) / old_img, out_images / new_name)
                            sample["image"] = f"images/{new_name}"
                            f.write(json.dumps(sample) + "\n")
                            n += 1
                    print(f"[hrsc] Merged {n} samples")
                    total += n

        if args.shiprs:
            print(f"\n=== ShipRSImageNet ===")
            n = convert_shiprs_imagenet(args.shiprs, args.output, f, out_images, args.augment, rng)
            total += n

        if args.airbus:
            print(f"\n=== Airbus Ship Detection ===")
            n = convert_airbus_ships(args.airbus, args.output, f, out_images, args.augment, args.airbus_max, rng)
            total += n

        if args.masati:
            print(f"\n=== MASATI v2 ===")
            n = convert_masati_v2(args.masati, f, out_images, args.augment, rng)
            total += n

    print(f"\n========================================")
    print(f"  TOTAL SAMPLES: {total}")
    print(f"  Output:        {jsonl_path}")
    print(f"========================================\n")


if __name__ == "__main__":
    main()
