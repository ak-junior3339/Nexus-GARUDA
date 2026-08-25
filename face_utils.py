from insightface.app import FaceAnalysis

_app = None

def get_app():
    """Loads the model once and reuses it across calls."""
    global _app
    if _app is None:
        _app = FaceAnalysis(name='buffalo_l')
        _app.prepare(ctx_id=-1, det_size=(640, 640))  # ctx_id=0 if you have GPU
    return _app