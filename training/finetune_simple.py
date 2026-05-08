"""LoRA fine-tuning of LFM2.5-VL-450M on ship-detection data.

Plain HuggingFace + PEFT, bf16 (no quantization). The 450M model fits in
T4's 16GB without 4-bit weights

Usage:
    python finetune_simple.py \\
        --dataset data/ship_combined/train.jsonl \\
        --output models/ship-detector-lora \\
        --epochs 2
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

import peft.import_utils as _piu
_piu.is_torchao_available = lambda: False
import peft.tuners.lora.torchao as _ptlt
_ptlt.is_torchao_available = lambda: False

import argparse
import json
from pathlib import Path

import torch
from PIL import Image as PILImage
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
    Trainer,
    TrainingArguments,
)


def load_jsonl_dataset(jsonl_path: str) -> Dataset:
    data_dir = Path(jsonl_path).parent
    samples = []
    with open(jsonl_path) as f:
        for line in f:
            sample = json.loads(line.strip())
            img_path = data_dir / sample["image"]
            if img_path.exists():
                samples.append({
                    "image_path": str(img_path),
                    "user_text": sample["conversations"][0]["value"],
                    "assistant_text": sample["conversations"][1]["value"],
                })
    return Dataset.from_list(samples)


class VLMCollator:
    MAX_SIDE = 384
    MAX_TOKENS = 1024

    def __init__(self, processor):
        self.processor = processor

    def __call__(self, batch):
        all_messages = []
        prompt_only_messages = []
        for item in batch:
            img = PILImage.open(item["image_path"]).convert("RGB")
            if max(img.size) > self.MAX_SIDE:
                img.thumbnail((self.MAX_SIDE, self.MAX_SIDE), PILImage.LANCZOS)
            full = [
                {"role": "user", "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": item["user_text"]},
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": item["assistant_text"]},
                ]},
            ]
            all_messages.append(full)
            prompt_only_messages.append([full[0]])

        inputs = self.processor.apply_chat_template(
            all_messages,
            add_generation_prompt=False,
            tokenize=True, return_dict=True, return_tensors="pt", padding=True,
        )
        prompt_inputs = self.processor.apply_chat_template(
            prompt_only_messages,
            add_generation_prompt=True,
            tokenize=True, return_dict=True, return_tensors="pt", padding=True,
        )

        if inputs["input_ids"].shape[1] > self.MAX_TOKENS:
            for k in inputs:
                if hasattr(inputs[k], "shape") and len(inputs[k].shape) >= 2 \
                        and inputs[k].shape[1] >= inputs["input_ids"].shape[1]:
                    inputs[k] = inputs[k][:, :self.MAX_TOKENS]

        labels = inputs["input_ids"].clone()
        pad_id = self.processor.tokenizer.pad_token_id if hasattr(self.processor, "tokenizer") else None
        if pad_id is not None:
            labels[labels == pad_id] = -100
        for i, prompt_ids in enumerate(prompt_inputs["input_ids"]):
            non_pad_len = (prompt_ids != pad_id).sum().item() if pad_id is not None else len(prompt_ids)
            labels[i, :non_pad_len] = -100

        inputs["labels"] = labels
        return inputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="LiquidAI/LFM2.5-VL-450M")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-rank", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=32)
    args = parser.parse_args()

    print(f"[finetune] Loading processor + model: {args.model}")
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    lora_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print(f"[finetune] Loading dataset: {args.dataset}")
    dataset = load_jsonl_dataset(args.dataset)
    print(f"[finetune] Dataset size: {len(dataset)}")

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        bf16=True,
        logging_steps=10,
        save_steps=200,
        save_total_limit=2,
        gradient_checkpointing=True,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=VLMCollator(processor),
    )

    print("[finetune] Starting training...")
    trainer.train(resume_from_checkpoint=True)

    print(f"[finetune] Saving LoRA adapter to: {args.output}")
    model.save_pretrained(args.output)
    processor.save_pretrained(args.output)
    print("[finetune] Done.")


if __name__ == "__main__":
    main()
