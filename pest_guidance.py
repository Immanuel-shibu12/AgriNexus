"""
Pest, weed & disease guidance — the "Plantix-style" feature.

For the MVP/demo, diagnosis uses a lightweight colour-heuristic on the
uploaded photo (no GPU/model download needed, works fully offline).
In a real product, replace `analyze_image()` internals with a trained
CNN/vision model (e.g. a fine-tuned MobileNet, or a hosted vision LLM
call similar to how ProcureAI's Mim agent calls Groq/Llama 3) — the
rest of the app (knowledge base, UI, logging) stays the same.
"""

from PIL import Image
import numpy as np

KNOWLEDGE_BASE = {
    "yellowing_leaves": {
        "label": "Leaf yellowing (possible nitrogen deficiency or viral infection)",
        "guidance": (
            "Uniform yellowing often indicates nitrogen deficiency — apply recommended top-dress dose. "
            "Yellowing in a mosaic/patchy pattern, especially with stunted growth, may indicate a viral "
            "disease spread by whitefly/aphids — remove affected plants and control the insect vector."
        ),
    },
    "brown_spots": {
        "label": "Brown/dark leaf spots (likely fungal leaf spot or blast)",
        "guidance": (
            "Brown lesions with yellow halos are typical of fungal leaf spot diseases. Improve field "
            "drainage and airflow, avoid overhead irrigation in the evening, and use a recommended "
            "fungicide if spread is rapid. Consult your local Krishi Bhavan/KVK for the exact fungicide."
        ),
    },
    "healthy": {
        "label": "No obvious stress signs detected",
        "guidance": (
            "Leaf colour and texture look within normal range from this photo. Keep monitoring weekly, "
            "especially the undersides of leaves for early pest eggs."
        ),
    },
    "chewed_holes": {
        "label": "Leaf damage pattern (possible caterpillar/insect feeding)",
        "guidance": (
            "Irregular holes or chewed leaf margins suggest caterpillar or beetle feeding. Scout at dusk "
            "when many pests are active, hand-pick if infestation is light, and consider need-based "
            "biopesticide (e.g. neem-based) before resorting to chemical spray."
        ),
    },
}


def analyze_image(pil_image: Image.Image) -> dict:
    """
    Very simple colour-based heuristic (NOT a trained ML model):
      - Dominant yellow/brown tone  -> yellowing_leaves
      - High proportion of dark brown/black pixels -> brown_spots
      - Mostly green, low variance  -> healthy
      - otherwise -> chewed_holes (fallback "check visually" bucket)

    This exists so the feature is *fully functional offline* for a demo.
    Swap this function's body for a real model call for production accuracy.
    """
    img = pil_image.convert("RGB").resize((150, 150))
    arr = np.array(img).astype(float)

    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    green_mask = (g > r) & (g > b) & (g > 60)
    yellow_mask = (r > 140) & (g > 140) & (b < 110)
    brown_dark_mask = (r < 110) & (g < 90) & (b < 80)

    total = arr.shape[0] * arr.shape[1]
    green_ratio = green_mask.sum() / total
    yellow_ratio = yellow_mask.sum() / total
    brown_ratio = brown_dark_mask.sum() / total

    if brown_ratio > 0.12:
        key = "brown_spots"
        confidence = min(0.55 + brown_ratio, 0.9)
    elif yellow_ratio > 0.20:
        key = "yellowing_leaves"
        confidence = min(0.55 + yellow_ratio * 0.5, 0.9)
    elif green_ratio > 0.55:
        key = "healthy"
        confidence = min(0.5 + green_ratio * 0.3, 0.85)
    else:
        key = "chewed_holes"
        confidence = 0.5

    result = dict(KNOWLEDGE_BASE[key])
    result["key"] = key
    result["confidence"] = round(confidence, 2)
    return result
