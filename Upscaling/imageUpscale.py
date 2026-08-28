"""
upscale_image.py

Standalone script that upscales a single image using a pretrained deep
learning super-resolution model (ESPCN), then saves the result so it can
be fed into a face detection model.

Unlike a plain resize (cv2.resize), this uses a trained neural network
that has learned to reconstruct plausible high-frequency detail (edges,
textures) rather than just interpolating pixels, which generally helps
face detectors pick up smaller/blurrier faces.

Requires:
    pip install opencv-contrib-python
    (opencv-contrib-python includes the dnn_superres module used below;
    the plain 'opencv-python' package does NOT include it.)

Model file:
    This script uses ESPCN_x4.pb (Efficient Sub-Pixel CNN, 4x upscale).
    It is small (~100 KB) and fast, which makes it a good default for a
    pre-processing step rather than a heavy general-purpose upscaler.
    Other options (EDSR, FSRCNN, LapSRN) exist and produce sharper
    results at the cost of speed, if you want to swap the model later.
"""

import os
import ssl
import urllib.request

import cv2


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
# Where the pretrained model file lives locally. If it is not found here,
# the script downloads it automatically on first run.
MODEL_PATH = "Upscaling/models/ESPCN_x4.pb"
MODEL_URL = "https://github.com/fannymonori/TF-ESPCN/raw/master/export/ESPCN_x4.pb"

# Which super-resolution algorithm the model file corresponds to, and
# the upscale factor it was trained for. These must match the model
# file above (ESPCN_x4.pb -> algorithm 'espcn', scale 4).
SR_ALGORITHM = "espcn"
SR_SCALE = 4


# ---------------------------------------------------------------------------
# MODEL DOWNLOAD (runs once, if the model file is not already present)
# ---------------------------------------------------------------------------
def ensure_model_downloaded(model_path, model_url):
    """
    Downloads the pretrained super-resolution model if it is missing.

    Uses certifi's CA certificate bundle explicitly, rather than relying
    on the system default, because some Python installs (notably the
    python.org installer on macOS) do not have their SSL certificates
    wired up correctly out of the box, which causes
    CERTIFICATE_VERIFY_FAILED errors on any HTTPS download otherwise.
    """
    if os.path.exists(model_path):
        return

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    print(f"Model not found locally. Downloading from {model_url} ...")

    try:
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        # certifi is not installed; fall back to the system default
        # context. If this fails with a certificate error, run:
        #   pip install certifi
        ssl_context = ssl.create_default_context()

    with urllib.request.urlopen(model_url, context=ssl_context) as response:
        data = response.read()
    with open(model_path, "wb") as f:
        f.write(data)

    print(f"Model downloaded to {model_path}")


# ---------------------------------------------------------------------------
# SUPER-RESOLUTION UPSCALING
# ---------------------------------------------------------------------------
def upscale_image(input_path, output_path, model_path=MODEL_PATH):
    """
    Loads an image, runs it through the super-resolution model, and
    saves the upscaled result.

    Args:
        input_path (str): path to the source image.
        output_path (str): where to save the upscaled image.
        model_path (str): path to the .pb super-resolution model file.
    """
    ensure_model_downloaded(model_path, MODEL_URL)

    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image at: {input_path}")

    # Set up the super-resolution engine and load the trained model.
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(model_path)
    sr.setModel(SR_ALGORITHM, SR_SCALE)

    # Run the actual upscale. This is the slow step (a forward pass
    # through the neural network), proportional to image size.
    print(f"Upscaling {input_path} by {SR_SCALE}x using {SR_ALGORITHM.upper()} ...")
    upscaled = sr.upsample(image)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cv2.imwrite(output_path, upscaled)

    original_h, original_w = image.shape[:2]
    new_h, new_w = upscaled.shape[:2]
    print(f"Original size: {original_w}x{original_h}")
    print(f"Upscaled size: {new_w}x{new_h}")
    print(f"Saved upscaled image to: {output_path}")

    return upscaled


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    upscale_image(
        input_path="Upscaling/input/input.jpg",
        output_path="Upscaling/output/output_upscaled.jpg",
    )