import os
from insightface.app import FaceAnalysis

# weights/face/ sits in project root, alongside other models' weights
# (e.g. weights/anpr/best.pt)
WEIGHTS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "face")

_app = None

def get_app():
    """Loads the model once and reuses it across calls."""
    global _app
    if _app is None:
        _app = FaceAnalysis(name='buffalo_l', root=WEIGHTS_ROOT)
        _app.prepare(ctx_id=-1, det_size=(640, 640))  # -1 = CPU (no CUDA available)
    return _app
