"""
download_weights.py

Downloads the InsightFace buffalo_l model pack (SCRFD detector,
ArcFace recognition, landmarks, attributes) into weights/face/,
alongside other models' weights (e.g. weights/anpr/best.pt).

Run this ONCE, from the project root:
    python download_weights.py

After this, get_app() in load_model.py loads from this local folder
every time — no re-download on future runs.
"""

import os
from insightface.app import FaceAnalysis

WEIGHTS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "face")


def download_weights():
    os.makedirs(WEIGHTS_ROOT, exist_ok=True)
    print(f"Downloading/verifying buffalo_l weights into: {WEIGHTS_ROOT}")
    app = FaceAnalysis(name="buffalo_l", root=WEIGHTS_ROOT)
    app.prepare(ctx_id=-1, det_size=(640, 640))
    print("Done. Model files:")
    model_dir = os.path.join(WEIGHTS_ROOT, "models", "buffalo_l")
    for fname in os.listdir(model_dir):
        print(f"  {fname}")


if __name__ == "__main__":
    download_weights()
