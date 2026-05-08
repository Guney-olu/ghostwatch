import os


SIMSAT_API_URL = os.getenv("SIMSAT_API_URL", "http://localhost:9005")

MODEL_ID = os.getenv("GHOSTWATCH_MODEL", "LiquidAI/LFM2.5-VL-450M")
HF_TOKEN = os.getenv("HF_TOKEN", None)
LORA_ADAPTER_PATH = os.getenv("LORA_ADAPTER_PATH", None)

USE_FINETUNED_PROMPT = (
    os.getenv("USE_FINETUNED_PROMPT", "").lower() == "true"
    or "ghost" in MODEL_ID.lower()
    or LORA_ADAPTER_PATH is not None
)

DETECTION_CONFIDENCE_THRESHOLD = float(os.getenv("DETECTION_CONFIDENCE", "0.3"))
GHOST_MATCH_RADIUS_KM = float(os.getenv("GHOST_MATCH_RADIUS_KM", "0.5"))
AIS_DARK_PROBABILITY = float(os.getenv("AIS_DARK_PROBABILITY", "0.3"))

DEFAULT_SIZE_KM = float(os.getenv("DEFAULT_SIZE_KM", "5.0"))
DEFAULT_WINDOW_SECONDS = float(os.getenv("DEFAULT_WINDOW_SECONDS", str(10 * 24 * 60 * 60)))

MOCK_MODE = os.getenv("GHOSTWATCH_MOCK_MODE", "false").lower() == "true"

HOST = os.getenv("GHOSTWATCH_HOST", "0.0.0.0")
PORT = int(os.getenv("GHOSTWATCH_PORT", "9010"))
