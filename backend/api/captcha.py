# backend/api/captcha.py

import io
import math
import random
import string
import uuid
from datetime import datetime, timedelta

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# CONFIGURATION
# ============================================================

CAPTCHA_EXPIRY = 600       # 10 minutes
MAX_ATTEMPTS = 5

FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
FONT_PATH_FALLBACK = r"C:\Windows\Fonts\cour.ttf"


# Stores active CAPTCHAs
#
# {
#     "captcha-uuid": {
#         "text": "a7KpX2",
#         "expires_at": datetime(...),
#         "attempts": 0
#     }
# }
#
captcha_store = {}


# ============================================================
# CAPTCHA TEXT
# ============================================================

def generate_captcha_text():

    characters = string.ascii_letters + string.digits

    # Remove confusing characters
    for char in "0OoIl1":
        characters = characters.replace(char, "")

    return "".join(
        random.choices(characters, k=6)
    )


# ============================================================
# ROUGH CHARACTER RENDERER
# ============================================================

def _render_rough_char(
    char: str,
    font_size: int,
    text_color: tuple
) -> Image.Image:

    size = 180

    canvas = Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(canvas)

    # Try Arial first
    try:
        font = ImageFont.truetype(
            FONT_PATH,
            font_size
        )

    # Fall back to Courier New
    except IOError:
        font = ImageFont.truetype(
            FONT_PATH_FALLBACK,
            font_size
        )

    # Get character dimensions
    bbox = draw.textbbox(
        (0, 0),
        char,
        font=font
    )

    char_width = bbox[2] - bbox[0]
    char_height = bbox[3] - bbox[1]

    x = (size - char_width) // 2
    y = (size - char_height) // 2 - bbox[1]

    # Draw character
    draw.text(
        (x, y),
        char,
        font=font,
        fill=(*text_color, 255)
    )

    # --------------------------------------------------------
    # Make character edges rough
    # --------------------------------------------------------

    arr = np.array(canvas)

    alpha = arr[:, :, 3].astype(float)

    noise = np.random.default_rng().uniform(
        0,
        1,
        alpha.shape
    )

    # Remove some anti-aliased edge pixels
    edge_mask = (
        (alpha > 5) &
        (alpha < 250)
    )

    alpha[
        edge_mask & (noise < 0.55)
    ] = 0

    # Punch small holes into solid areas
    solid_mask = alpha >= 250

    alpha[
        solid_mask & (noise < 0.06)
    ] = 0

    arr[:, :, 3] = alpha.clip(
        0,
        255
    ).astype(np.uint8)

    result = Image.fromarray(
        arr,
        "RGBA"
    )

    # --------------------------------------------------------
    # Blur and re-threshold
    # --------------------------------------------------------

    result = result.filter(
        ImageFilter.GaussianBlur(
            radius=0.5
        )
    )

    arr2 = np.array(result)

    alpha2 = arr2[:, :, 3].astype(float)

    alpha2 = np.where(
        alpha2 > 80,
        np.minimum(
            255,
            alpha2 * 1.4
        ),
        0
    )

    arr2[:, :, 3] = alpha2.clip(
        0,
        255
    ).astype(np.uint8)

    result = Image.fromarray(
        arr2,
        "RGBA"
    )

    # --------------------------------------------------------
    # Remove transparent borders
    # --------------------------------------------------------

    bbox = result.getbbox()

    if bbox:

        padding = 4

        result = result.crop(
            (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(
                    result.width,
                    bbox[2] + padding
                ),
                min(
                    result.height,
                    bbox[3] + padding
                )
            )
        )

    return result


# ============================================================
# CREATE CAPTCHA IMAGE
# ============================================================

def create_captcha_image(
    captcha_text: str
) -> Image.Image:

    width = 260
    height = 90

    background_color = (
        185,
        220,
        220
    )

    image = Image.new(
        "RGB",
        (width, height),
        background_color
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # Background dots
    # --------------------------------------------------------

    for _ in range(35):

        x = random.randint(
            0,
            width
        )

        y = random.randint(
            0,
            height
        )

        radius = random.randint(
            1,
            2
        )

        color = random.choice([
            (175, 210, 210),
            (180, 213, 213),
            (185, 215, 215)
        ])

        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius
            ),
            fill=color
        )

    # --------------------------------------------------------
    # Font sizes
    # --------------------------------------------------------

    large = [72, 65, 70]
    small = [35, 30, 32]

    random.shuffle(large)
    random.shuffle(small)

    font_sizes = [
        large[0],
        small[0],
        large[1],
        small[1],
        large[2],
        small[2]
    ]

    random.shuffle(font_sizes)

    # --------------------------------------------------------
    # Character positions
    # --------------------------------------------------------

    x_positions = [
        int(width * position)
        for position in [
            0.09,
            0.25,
            0.42,
            0.58,
            0.75,
            0.92
        ]
    ]

    # --------------------------------------------------------
    # Text colors
    # --------------------------------------------------------

    text_colors = [
        (18, 35, 100),
        (22, 42, 110),
        (14, 28, 88),
        (28, 48, 115)
    ]

    # --------------------------------------------------------
    # Draw characters
    # --------------------------------------------------------

    for i, char in enumerate(captcha_text):

        text_color = random.choice(
            text_colors
        )

        char_image = _render_rough_char(
            char,
            font_sizes[i],
            text_color
        )

        # --------------------------------------------
        # Horizontal squeeze/stretch
        # --------------------------------------------

        scale_x = random.uniform(
            0.90,
            1.10
        )

        char_image = char_image.resize(
            (
                int(
                    char_image.width *
                    scale_x
                ),
                char_image.height
            ),
            Image.Resampling.LANCZOS
        )

        # --------------------------------------------
        # Rotate character
        # --------------------------------------------

        angle = random.randint(
            -28,
            28
        )

        rotated = char_image.rotate(
            angle,
            expand=True,
            resample=Image.Resampling.BICUBIC
        )

        # Remove transparent border
        bbox = rotated.getbbox()

        if bbox:
            rotated = rotated.crop(
                bbox
            )

        # --------------------------------------------
        # Arc / wave effect
        # --------------------------------------------

        t = i / (
            len(captcha_text) - 1
        )

        arc_lift = (
            math.sin(
                t * math.pi
            ) * 16
        )

        x = (
            x_positions[i]
            - rotated.width // 2
            + random.randint(-4, 4)
        )

        y = (
            height // 2
            - int(arc_lift)
            - rotated.height // 2
            + random.randint(-4, 4)
        )

        # Keep inside image
        x = max(
            0,
            min(
                x,
                width - rotated.width
            )
        )

        y = max(
            0,
            min(
                y,
                height - rotated.height
            )
        )

        # Paste character
        image.paste(
            rotated,
            (x, y),
            rotated
        )

    # --------------------------------------------------------
    # Foreground dots
    # --------------------------------------------------------

    draw = ImageDraw.Draw(image)

    for _ in range(12):

        x = random.randint(
            0,
            width
        )

        y = random.randint(
            0,
            height
        )

        draw.ellipse(
            (
                x - 1,
                y - 1,
                x + 1,
                y + 1
            ),
            fill=(168, 205, 205)
        )

    return image


# ============================================================
# CLEANUP EXPIRED CAPTCHAS
# ============================================================

def cleanup_expired_captchas():

    now = datetime.now()

    expired_ids = [
        captcha_id
        for captcha_id, data
        in captcha_store.items()
        if now > data["expires_at"]
    ]

    for captcha_id in expired_ids:
        del captcha_store[captcha_id]


# ============================================================
# GENERATE CAPTCHA
# ============================================================

def generate_captcha():

    cleanup_expired_captchas()

    captcha_id = str(
        uuid.uuid4()
    )

    captcha_text = generate_captcha_text()

    captcha_store[captcha_id] = {
        "text": captcha_text,

        "expires_at": (
            datetime.now()
            + timedelta(
                seconds=CAPTCHA_EXPIRY
            )
        ),

        "attempts": 0
    }

    return captcha_id


# ============================================================
# GET CAPTCHA IMAGE
# ============================================================

def get_captcha_image(
    captcha_id: str
):

    if captcha_id not in captcha_store:
        return None

    data = captcha_store[captcha_id]

    # Check expiry
    if datetime.now() > data["expires_at"]:

        del captcha_store[captcha_id]

        return None

    return create_captcha_image(
        data["text"]
    )


# ============================================================
# VERIFY CAPTCHA
# ============================================================

def verify_captcha(
    captcha_id: str,
    user_input: str
):

    if captcha_id not in captcha_store:

        return (
            False,
            "CAPTCHA not found or expired."
        )

    data = captcha_store[captcha_id]

    # --------------------------------------------------------
    # Expiry
    # --------------------------------------------------------

    if datetime.now() > data["expires_at"]:

        del captcha_store[captcha_id]

        return (
            False,
            "CAPTCHA expired."
        )

    # --------------------------------------------------------
    # Attempt limit
    # --------------------------------------------------------

    if data["attempts"] >= MAX_ATTEMPTS:

        del captcha_store[captcha_id]

        return (
            False,
            "Too many attempts. Generate a new CAPTCHA."
        )

    # Count attempt
    data["attempts"] += 1

    # --------------------------------------------------------
    # Verify answer
    # --------------------------------------------------------

    if user_input.strip().lower() == data["text"].lower():

        # CAPTCHA is one-time use
        del captcha_store[captcha_id]

        return (
            True,
            "CAPTCHA verified successfully."
        )

    remaining = (MAX_ATTEMPTS - data["attempts"])

    return (
        False,
        f"Incorrect CAPTCHA. "
        f"{remaining} attempts remaining."
    )