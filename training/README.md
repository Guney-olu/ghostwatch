# Fine-tuning LFM2.5-VL for ship detection

This folder documents how the GhostWatch detection model was trained. The final
checkpoint lives on HuggingFace at **[AryanNsc/LMF2.5-VL-Ghost-V1](https://huggingface.co/AryanNsc/LMF2.5-VL-Ghost-V1)** —
the production app loads it directly without any LoRA juggling.

## Why fine-tune?

The base [LiquidAI/LFM2.5-VL-450M](https://huggingface.co/LiquidAI/LFM2.5-VL-450M) is
strong at general vision-language tasks but unreliable on **10-meter-resolution
Sentinel-2 imagery**. Ships there look like a few bright pixels against dark
water — the model would describe them in prose ("there are 5 ships") instead of
emitting structured bounding boxes. We needed it to consistently output
`[{"label": "boat", "bbox": [x1,y1,x2,y2]}, ...]` for every image.

## Datasets

| Dataset | Samples | Format | Why we used it |
|---|---|---|---|
| [HRSC2016](https://www.kaggle.com/datasets/guofeng/hrsc2016) | ~1,000 | PASCAL-VOC XML | Multi-class ship taxonomy (33 ship types), high-res aerial |
| [ShipRSImageNet](https://www.kaggle.com/datasets/kallusrujanreddy/shiprsimagenet) | ~3,400 | YOLO + `data.yaml` | Fine-grained classes (50+ ship variants) on satellite imagery |
| [MASATI v2](https://www.kaggle.com/datasets/louisaberdeen/masati-v2) | ~2,500 | YOLO + `data.yaml` | Maritime aerial at Sentinel-2-comparable resolution |

After 5× augmentation (horizontal flip, vertical flip, 90° rotate, brightness/contrast)
the combined corpus reached **~35,000 training samples**. We subsampled to ~8,000
for the final 2-epoch run on a single T4 to keep training under 3 hours.


## Pipeline

```
Kaggle datasets ──▶ multi_dataset.py ──▶ ship_combined/
                                           ├── images/
                                           └── train.jsonl
                                                   │
                                                   ▼
                                         finetune_simple.py
                                                   │
                                                   ▼
                                         models/ship-detector-lora/
                                         (LoRA adapter, ~50 MB)
                                                   │
                                                   ▼
                                          merge_and_push.py
                                                   │
                                                   ▼
                                  HuggingFace Hub (merged 900 MB model)
```

## Training config

| Parameter | Value | Notes |
|---|---|---|
| Base model | `LiquidAI/LFM2.5-VL-450M` | 450M params, fits T4 in bf16 |
| Method | LoRA via PEFT (no quantization) | Plain HF `Trainer` |
| LoRA rank / alpha | 8 / 32 | LoRA dropout 0.05 |
| Target modules | q/k/v/o + gate/up/down | All attention + MLP projections in LM |
| Batch / grad-accum | 1 / 4 (effective 4) | T4 16 GB, ~1024 max tokens |
| LR / schedule | 2e-4 / cosine, warmup 0.1 | Standard LoRA |
| Precision | bf16 | No 4-bit weights |
| Epochs | 2 | ~3,984 steps on 8k subsample |
| Hardware | Single T4 (16 GB) | ~2h45m wall clock |
| Final loss | **0.62** (started ~1.3) | Smooth cosine descent, no spikes |

Two non-obvious tricks made training stable:

1. **Prompt masking** in `VLMCollator` — we set `labels[:prompt_len] = -100` so
   loss only counts the assistant's response tokens. Without this, loss collapses
   from 11 → 0.17 in 100 steps (the model just memorized the prompt).
2. **Image downsize cap** — every image is `thumbnail((384, 384))` before the
   processor runs. Some HRSC images are 6000×4000; without the cap we'd OOM on
   the encoder and hit a wall around step 900.

## Reproduce it

### 1. Get the datasets

```bash
mkdir -p data && cd data

kaggle datasets download -d guofeng/hrsc2016 && unzip -q hrsc2016.zip
[ -d "HRSC2016 MS" ] && mv "HRSC2016 MS" HRSC2016

kaggle datasets download -d kallusrujanreddy/shiprsimagenet && unzip -q shiprsimagenet.zip -d ShipRSImageNet

kaggle datasets download -d louisaberdeen/masati-v2 && mkdir -p masati-v2 && unzip -q masati-v2.zip -d masati-v2

cd ..
```

### 2. Build the combined dataset

```bash
python multi_dataset.py \
  --hrsc data/HRSC2016 \
  --shiprs data/ShipRSImageNet \
  --masati data/masati-v2 \
  --output data/ship_combined \
  --augment 5
```

### 3. Fine-tune (T4 GPU, ~3 hours)

```bash
python finetune_simple.py \
  --dataset data/ship_combined/train.jsonl \
  --output models/ship-detector-lora \
  --epochs 2 --batch-size 1 --grad-accum 4 --lora-rank 8
```

### 4. Merge LoRA into base + push to HF

```bash
export HF_TOKEN=hf_xxx
python merge_and_push.py \
  --adapter models/ship-detector-lora/checkpoint-3984 \
  --repo <your-username>/LMF2.5-VL-Ghost-V1
```

### 5. Test

```bash
python test_inference.py --image ship_test.jpeg
```

You should get back a JSON array of `{"label", "bbox"}` detections.

## Files

| File | Purpose |
|---|---|
| [multi_dataset.py](multi_dataset.py) | Combine HRSC2016 + ShipRSImageNet + MASATI v2 into one JSONL |
| [prepare_dataset.py](prepare_dataset.py) | HRSC2016 + COCO converters used by `multi_dataset.py` |
| [finetune_simple.py](finetune_simple.py) | LoRA trainer (HF + PEFT, bf16, prompt-masked SFT) |
| [merge_and_push.py](merge_and_push.py) | Fuse LoRA into base weights, upload merged model to HF Hub |
| [test_inference.py](test_inference.py) | Standalone sanity check — load from HF and detect on one image |
| `ship_test.jpeg` | Sample satellite image for `test_inference.py` |
