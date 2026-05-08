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

import peft.import_utils as _piu
_piu.is_torchao_available = lambda: False
import peft.tuners.lora.torchao as _ptlt
_ptlt.is_torchao_available = lambda: False

import argparse
import os
import shutil
from pathlib import Path

import torch
from huggingface_hub import HfApi, login
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, help="Path to LoRA adapter checkpoint dir")
    parser.add_argument("--base-model", default="LiquidAI/LFM2.5-VL-450M")
    parser.add_argument("--repo", required=True, help="HuggingFace repo ID to push to")
    parser.add_argument("--merged-dir", default="./ship-detector-merged")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    adapter_path = Path(args.adapter)
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_path}")

    merged_dir = Path(args.merged_dir)
    if merged_dir.exists():
        print(f"[merge] Removing existing {merged_dir}")
        shutil.rmtree(merged_dir)
    merged_dir.mkdir(parents=True, exist_ok=True)

    print(f"[merge] Loading base model: {args.base_model}")
    processor = AutoProcessor.from_pretrained(args.base_model, trust_remote_code=True)
    base = AutoModelForImageTextToText.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"[merge] Loading LoRA adapter: {adapter_path}")
    model = PeftModel.from_pretrained(base, str(adapter_path))

    print("[merge] Merging LoRA weights into base model...")
    model = model.merge_and_unload()

    print(f"[merge] Saving merged model to: {merged_dir}")
    model.save_pretrained(str(merged_dir), safe_serialization=True)
    processor.save_pretrained(str(merged_dir))

    readme = merged_dir / "README.md"
    readme.write_text(f"""---
base_model: {args.base_model}
library_name: transformers
tags:
- ship-detection
- satellite-imagery
- vision-language
- lfm2-vl
- ghostwatch
---

# {args.repo}

Fine-tuned [{args.base_model}](https://huggingface.co/{args.base_model}) for maritime
ship detection in satellite imagery. Trained on a combined corpus of HRSC2016,
ShipRSImageNet, and MASATI v2.

The LoRA adapter has been **merged into the base weights** — load it directly:

```python
from transformers import AutoModelForImageTextToText, AutoProcessor

model = AutoModelForImageTextToText.from_pretrained(
    "{args.repo}",
    torch_dtype="bfloat16",
    device_map="auto",
    trust_remote_code=True,
)
processor = AutoProcessor.from_pretrained("{args.repo}", trust_remote_code=True)
```
""")

    size_mb = sum(f.stat().st_size for f in merged_dir.rglob("*") if f.is_file()) / 1e6
    print(f"[merge] Merged model size: {size_mb:.0f} MB")

    if args.no_upload:
        print(f"[merge] --no-upload set; merged model is at {merged_dir}")
        return

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        login(token=token, add_to_git_credential=False)
    else:
        print("[merge] HF_TOKEN not set — calling interactive login()")
        login()

    api = HfApi()
    print(f"[merge] Ensuring repo exists: {args.repo}")
    api.create_repo(repo_id=args.repo, repo_type="model", exist_ok=True, private=args.private)

    print(f"[merge] Uploading {merged_dir} → {args.repo}")
    api.upload_folder(
        folder_path=str(merged_dir),
        repo_id=args.repo,
        repo_type="model",
        commit_message="Upload merged LFM2.5-VL ship detector",
    )

    print(f"[merge] Done. View at: https://huggingface.co/{args.repo}")


if __name__ == "__main__":
    main()
