"""Whisper model metadata for UI (names, descriptions, relative speed/accuracy)."""

WHISPER_MODELS = [
    {
        "id": "tiny",
        "label": "Tiny",
        "params": "39M",
        "speed": "~10× faster than large",
        "accuracy": "Lowest — good for clear speech, drafts",
        "disk": "~150 MB",
    },
    {
        "id": "base",
        "label": "Base",
        "params": "74M",
        "speed": "~7× faster than large",
        "accuracy": "Low — general purpose, quick passes",
        "disk": "~300 MB",
    },
    {
        "id": "small",
        "label": "Small",
        "params": "244M",
        "speed": "~4× faster than large",
        "accuracy": "Medium — daily use, good balance",
        "disk": "~1 GB",
    },
    {
        "id": "medium",
        "label": "Medium",
        "params": "769M",
        "speed": "~2× faster than large",
        "accuracy": "High — when accuracy matters",
        "disk": "~3 GB",
    },
    {
        "id": "large-v2",
        "label": "Large v2",
        "params": "1.5B",
        "speed": "1× (baseline)",
        "accuracy": "Very high — challenging audio",
        "disk": "~6 GB",
    },
    {
        "id": "large-v3",
        "label": "Large v3",
        "params": "1.5B",
        "speed": "1× (baseline)",
        "accuracy": "Best — multi-speaker, noise, all languages",
        "disk": "~6 GB",
    },
]

# Valid model IDs for whisper.load_model()
VALID_MODEL_IDS = [m["id"] for m in WHISPER_MODELS]
