"""Vessel detection using Liquid AI's LFM2.5-VL vision-language model."""

import random
from io import BytesIO

from PIL import Image

from ghostwatch import config
from ghostwatch.detector.prompt_templates import (
    FINETUNED_PROMPT,
    GROUNDING_PROMPT,
    MARITIME_ANALYSIS_PROMPT,
    SCENE_DESCRIPTION_PROMPT,
    Detection,
    parse_detection_response,
)
from ghostwatch.detector.bbox_utils import non_max_suppression


class VesselDetector:
    """Detects vessels in satellite imagery using Liquid AI VLMs."""

    def __init__(self):
        self.model = None
        self.processor = None
        self._loaded = False

        if config.MOCK_MODE:
            print("[GhostWatch] Running in MOCK MODE — no model loaded")
        else:
            self._load_model()

    def _load_model(self):
        """Load the VLM model and processor from HuggingFace."""
        from transformers import AutoModelForImageTextToText, AutoProcessor
        import torch

        print(f"[GhostWatch] Loading model: {config.MODEL_ID}")

        model_kwargs = {"device_map": "auto", "dtype": torch.bfloat16}
        if config.HF_TOKEN:
            model_kwargs["token"] = config.HF_TOKEN

        self.processor = AutoProcessor.from_pretrained(
            config.MODEL_ID,
            token=config.HF_TOKEN,
        )
        self.model = AutoModelForImageTextToText.from_pretrained(
            config.MODEL_ID,
            **model_kwargs,
        )

        if config.LORA_ADAPTER_PATH:
            from peft import PeftModel
            print(f"[GhostWatch] Loading LoRA adapter: {config.LORA_ADAPTER_PATH}")
            self.model = PeftModel.from_pretrained(self.model, config.LORA_ADAPTER_PATH)

        self._loaded = True
        print("[GhostWatch] Model loaded successfully")

    def detect(self, image: Image.Image) -> list[Detection]:
        """Run vessel detection on a satellite image.

        Args:
            image: PIL Image of satellite imagery

        Returns:
            List of Detection objects with label, confidence, and bbox
        """
        if config.MOCK_MODE:
            return self._mock_detect()

        if not self._loaded:
            raise RuntimeError("Model not loaded")

        if config.USE_FINETUNED_PROMPT:
            detections = self._run_inference(image, FINETUNED_PROMPT)
        else:
            detections = self._run_inference(image, GROUNDING_PROMPT)
            detections = [d for d in detections if d.confidence > 0.01]

            if not detections:
                detections = self._run_inference(image, MARITIME_ANALYSIS_PROMPT)
                detections = [d for d in detections if d.confidence > 0.01]

            if not detections:
                detections = self._run_inference(image, SCENE_DESCRIPTION_PROMPT)

        detections = non_max_suppression(detections, iou_threshold=0.5)
        detections = [d for d in detections if d.confidence >= config.DETECTION_CONFIDENCE_THRESHOLD]

        return detections

    def _run_inference(self, image: Image.Image, prompt: str) -> list[Detection]:
        """Run a single VLM inference pass."""
        import torch

        if config.USE_FINETUNED_PROMPT and max(image.size) > 384:
            image = image.copy()
            image.thumbnail((384, 384), Image.LANCZOS)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                do_sample=False,
            )

        input_len = inputs["input_ids"].shape[1]
        raw_text = self.processor.decode(output_ids[0][input_len:], skip_special_tokens=True)

        return parse_detection_response(raw_text)

    def _mock_detect(self) -> list[Detection]:
        """Return synthetic detections for development/demo without GPU."""
        rng = random.Random(42)
        num_vessels = rng.randint(2, 6)
        labels = ["cargo_ship", "tanker", "fishing_boat", "unknown_vessel", "patrol_vessel"]
        detections = []

        for i in range(num_vessels):
            cx = rng.uniform(0.1, 0.9)
            cy = rng.uniform(0.1, 0.9)
            w = rng.uniform(0.02, 0.08)
            h = rng.uniform(0.01, 0.05)
            detections.append(Detection(
                label=rng.choice(labels),
                confidence=round(rng.uniform(0.5, 0.98), 2),
                bbox=[
                    max(0, cx - w / 2),
                    max(0, cy - h / 2),
                    min(1, cx + w / 2),
                    min(1, cy + h / 2),
                ],
            ))

        return detections

    @property
    def is_ready(self) -> bool:
        return self._loaded or config.MOCK_MODE

    def detect_from_bytes(self, image_bytes: bytes) -> list[Detection]:
        """Convenience: detect from raw image bytes."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        return self.detect(image)
