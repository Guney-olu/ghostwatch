"""Load the merged GhostWatch model from HuggingFace and run ship detection.

Usage:
    # Single image
    python test_inference.py --image path/to/satellite.jpg

    # Batch of images in a folder
    python test_inference.py --image-dir path/to/folder

    # Custom prompt or different repo
    python test_inference.py --image foo.jpg \\
        --repo AryanNsc/LMF2.5-VL-Ghost-V1 \\
        --prompt "Detect all ships in this image."
"""

import torch.utils._pytree as _pt
if not hasattr(_pt, "register_constant"):
    _pt.register_constant = lambda cls: cls

try:
    import torchao.quantization as _taq
    class _StubConfig:
        def __init__(self, *args, **kwargs): pass
    for _name in ["Float8WeightOnlyConfig", "Int4WeightOnlyConfig",
                  "Int8WeightOnlyConfig", "Int8DynamicActivationInt8WeightConfig"]:
        if not hasattr(_taq, _name):
            setattr(_taq, _name, _StubConfig)
except ImportError:
    pass

import argparse
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor


DEFAULT_PROMPT = (
    "Detect all ships and vessels in this satellite image. "
    "Return a JSON array where each element has "
    '"label" and "bbox" [x1, y1, x2, y2] normalized to [0, 1].'
)


def load_model(repo: str, device: str | None = None):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    print(f"[infer] Loading {repo} on {device} ({dtype})")
    t0 = time.time()
    processor = AutoProcessor.from_pretrained(repo, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        repo,
        torch_dtype=dtype,
        device_map=device,
        trust_remote_code=True,
    )
    model.eval()
    print(f"[infer] Loaded in {time.time() - t0:.1f}s")
    return model, processor


def detect(model, processor, image_path: str, prompt: str, max_new_tokens: int = 512) -> str:
    img = Image.open(image_path).convert("RGB")
    if max(img.size) > 384:
        img.thumbnail((384, 384), Image.LANCZOS)

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": prompt},
        ],
    }]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
        )
    elapsed = time.time() - t0

    prompt_len = inputs["input_ids"].shape[1]
    new_tokens = output_ids[0, prompt_len:]
    text = processor.tokenizer.decode(new_tokens, skip_special_tokens=True)

    print(f"[infer] {Path(image_path).name}: {len(new_tokens)} tokens in {elapsed:.1f}s")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="AryanNsc/LMF2.5-VL-Ghost-V1")
    parser.add_argument("--image", help="Single image path")
    parser.add_argument("--image-dir", help="Directory of images for batch")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--device", default=None, help="cuda or cpu (auto-detected if omitted)")
    args = parser.parse_args()

    if not args.image and not args.image_dir:
        parser.error("Provide either --image or --image-dir")

    model, processor = load_model(args.repo, device=args.device)

    if args.image:
        image_paths = [args.image]
    else:
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        image_paths = sorted(
            str(p) for p in Path(args.image_dir).iterdir()
            if p.suffix.lower() in exts
        )
        if not image_paths:
            parser.error(f"No images found in {args.image_dir}")
        print(f"[infer] Found {len(image_paths)} images")

    for p in image_paths:
        print("\n" + "=" * 70)
        print(f"IMAGE: {p}")
        print("=" * 70)
        text = detect(model, processor, p, args.prompt, args.max_new_tokens)
        print(text)


if __name__ == "__main__":
    main()
