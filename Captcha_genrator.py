from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import random
import string
import io
import uuid
import math
from datetime import datetime, timedelta

app = FastAPI(title="CAPTCHA Login API", version="1.0.0")

# Store CAPTCHA data in memory
captcha_store = {}

CAPTCHA_EXPIRY = 600       # 10 minutes
MAX_ATTEMPTS = 5

# Font path — FreeSerifBoldItalic gives the natural lean and serif serifs
# closest to the reference hand-drawn look
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
FONT_PATH_FALLBACK = r"C:\Windows\Fonts\cour.ttf" # Courier New


# --------------------------------------------------
# Models
# --------------------------------------------------

class CaptchaResponse(BaseModel):
    captcha_id: str
    message: str


class VerifyRequest(BaseModel):
    captcha_id: str
    user_input: str


class VerifyResponse(BaseModel):
    valid: bool
    message: str


# --------------------------------------------------
# CAPTCHA TEXT
# --------------------------------------------------

def generate_captcha_text():
    characters = string.ascii_letters + string.digits

    # Avoid confusing characters
    characters = characters.replace("0", "")
    characters = characters.replace("O", "")
    characters = characters.replace("o", "")
    characters = characters.replace("I", "")
    characters = characters.replace("l", "")
    characters = characters.replace("1", "")

    return "".join(random.choices(characters, k=6))


# --------------------------------------------------
# ROUGH CHARACTER RENDERER
# --------------------------------------------------

def _render_rough_char(char: str, font_size: int, text_color: tuple) -> Image.Image:
    """
    Render a single character with a rough, eroded ink texture that
    mimics the hand-distressed look of the reference CAPTCHA image.

    Steps:
      1. Draw the character on a transparent canvas using a bold-italic
         serif font (naturally looks more handwritten than sans-serif).
      2. Erode the alpha channel: randomly zero edge pixels (~55%) and
         punch small random holes in solid areas (~6%).
      3. Apply a light Gaussian blur then re-threshold alpha so edges
         look ragged rather than smooth.
      4. Tight-crop transparent borders so the caller knows the real size.
    """

    sz = 180   # large canvas; transparent border removed later
    canvas = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    drw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except IOError:
        font = ImageFont.truetype(FONT_PATH_FALLBACK, font_size)

    bbox = drw.textbbox((0, 0), char, font=font)
    cw = bbox[2] - bbox[0]
    ch = bbox[3] - bbox[1]
    cx = (sz - cw) // 2
    cy = (sz - ch) // 2 - bbox[1]
    drw.text((cx, cy), char, font=font, fill=(*text_color, 255))

    # -----------------------------------------
    # Alpha erosion — creates the rough ink look
    # -----------------------------------------

    arr = np.array(canvas)
    alpha = arr[:, :, 3].astype(float)
    noise = np.random.default_rng().uniform(0, 1, alpha.shape)

    # Edge pixels (anti-aliased, 5–249): aggressively remove ~55%
    edge_mask = (alpha > 5) & (alpha < 250)
    alpha[edge_mask & (noise < 0.55)] = 0

    # Solid interior: randomly punch small holes (~6%)
    solid_mask = alpha >= 250
    alpha[solid_mask & (noise < 0.06)] = 0

    arr[:, :, 3] = alpha.clip(0, 255).astype(np.uint8)
    result = Image.fromarray(arr, "RGBA")

    # -----------------------------------------
    # Blur → re-threshold: smooths the noise into
    # natural-looking ragged edges, not random dots
    # -----------------------------------------

    result = result.filter(ImageFilter.GaussianBlur(radius=0.5))
    arr2 = np.array(result)
    a2 = arr2[:, :, 3].astype(float)
    a2 = np.where(a2 > 80, np.minimum(255, a2 * 1.4), 0)
    arr2[:, :, 3] = a2.clip(0, 255).astype(np.uint8)
    result = Image.fromarray(arr2, "RGBA")

    # -----------------------------------------
    # Tight crop — remove transparent padding
    # -----------------------------------------

    bbox2 = result.getbbox()
    if bbox2:
        pad = 4
        result = result.crop((
            max(0, bbox2[0] - pad),
            max(0, bbox2[1] - pad),
            min(result.width,  bbox2[2] + pad),
            min(result.height, bbox2[3] + pad),
        ))

    return result


# --------------------------------------------------
# CAPTCHA IMAGE
# --------------------------------------------------

def create_captcha_image(captcha_text: str) -> Image.Image:

    width = 260
    height = 90

    bg_color = (185, 220, 220)

    image = Image.new(
        "RGB",
        (width, height),
        bg_color
    )

    draw = ImageDraw.Draw(image)

    # -----------------------------------------
    # Subtle background dots
    # -----------------------------------------

    for _ in range(35):

        x = random.randint(0, width)
        y = random.randint(0, height)

        radius = random.randint(1, 2)

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

    # -----------------------------------------
    # Font sizes
    # Alternate large (60-75) and small (28-38) so the
    # size contrast matches the reference image style
    # -----------------------------------------

    large = [72, 65, 70]
    small = [35, 30, 32]
    random.shuffle(large)
    random.shuffle(small)

    # Interleave: L S L S L S (or shuffled)
    font_sizes = [large[0], small[0], large[1], small[1], large[2], small[2]]
    random.shuffle(font_sizes)

    # -----------------------------------------
    # X positions — evenly spaced across the image
    # -----------------------------------------

    x_positions = [
        int(width * p)
        for p in [0.09, 0.25, 0.42, 0.58, 0.75, 0.92]
    ]

    # -----------------------------------------
    # Draw characters
    # -----------------------------------------

    for i, char in enumerate(captcha_text):

        # Slightly varying shades of navy blue
        text_colors = [
            (18, 35, 100),
            (22, 42, 110),
            (14, 28,  88),
            (28, 48, 115)
        ]
        text_color = random.choice(text_colors)

        ch_img = _render_rough_char(char, font_sizes[i], text_color)

        # -----------------------------------------
        # Slight horizontal squeeze / stretch
        # -----------------------------------------

        scale_x = random.uniform(0.90, 1.10)
        ch_img = ch_img.resize(
            (int(ch_img.width * scale_x), ch_img.height),
            Image.Resampling.LANCZOS
        )

        # -----------------------------------------
        # Rotation — more dramatic than before to
        # match the heavily tilted reference characters
        # -----------------------------------------

        angle = random.randint(-28, 28)

        rotated = ch_img.rotate(
            angle,
            expand=True,
            resample=Image.Resampling.BICUBIC
        )

        # Crop transparent border again after rotation
        bbox3 = rotated.getbbox()
        if bbox3:
            rotated = rotated.crop(bbox3)

        # -----------------------------------------
        # Arc baseline — sin curve so middle characters
        # rise up and outer ones sit lower, matching
        # the wave layout in the reference image
        # -----------------------------------------

        t = i / (len(captcha_text) - 1)
        arc_lift = math.sin(t * math.pi) * 16

        x = x_positions[i] - rotated.width  // 2 + random.randint(-4, 4)
        y = (
            height // 2
            - int(arc_lift)
            - rotated.height // 2
            + random.randint(-4, 4)
        )

        # -----------------------------------------
        # Keep character inside image bounds
        # -----------------------------------------

        x = max(0, min(x, width  - rotated.width))
        y = max(0, min(y, height - rotated.height))

        image.paste(
            rotated,
            (x, y),
            rotated
        )

    # -----------------------------------------
    # Subtle foreground dots
    # -----------------------------------------

    draw = ImageDraw.Draw(image)

    for _ in range(12):

        x = random.randint(0, width)
        y = random.randint(0, height)

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


# --------------------------------------------------
# CLEANUP
# --------------------------------------------------

def cleanup_expired_captchas():

    now = datetime.now()

    expired_ids = [
        captcha_id
        for captcha_id, data in captcha_store.items()
        if now > data["expires_at"]
    ]

    for captcha_id in expired_ids:
        del captcha_store[captcha_id]


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.get("/")
async def home():
    return FileResponse("static/index.html")


# --------------------------------------------------
# GENERATE CAPTCHA
# --------------------------------------------------

@app.get("/captcha/generate", response_model=CaptchaResponse)
async def generate_captcha():

    cleanup_expired_captchas()

    captcha_id = str(uuid.uuid4())

    captcha_text = generate_captcha_text()

    captcha_store[captcha_id] = {
        "text": captcha_text,
        "expires_at": datetime.now() + timedelta(
            seconds=CAPTCHA_EXPIRY
        ),
        "attempts": 0
    }

    return CaptchaResponse(
        captcha_id=captcha_id,
        message="CAPTCHA generated successfully."
    )


# --------------------------------------------------
# GET CAPTCHA IMAGE
# --------------------------------------------------

@app.get("/captcha/image/{captcha_id}")
async def get_captcha_image(captcha_id: str):

    if captcha_id not in captcha_store:
        raise HTTPException(
            status_code=404,
            detail="CAPTCHA not found or expired"
        )

    captcha_data = captcha_store[captcha_id]

    if datetime.now() > captcha_data["expires_at"]:

        del captcha_store[captcha_id]

        raise HTTPException(
            status_code=410,
            detail="CAPTCHA expired"
        )

    image = create_captcha_image(
        captcha_data["text"]
    )

    img_io = io.BytesIO()

    image.save(
        img_io,
        format="PNG"
    )

    img_io.seek(0)

    return StreamingResponse(
        img_io,
        media_type="image/png"
    )


# --------------------------------------------------
# VERIFY CAPTCHA
# --------------------------------------------------

@app.post("/captcha/verify", response_model=VerifyResponse)
async def verify_captcha(request: VerifyRequest):

    captcha_id = request.captcha_id
    user_input = request.user_input.strip()

    if captcha_id not in captcha_store:
        raise HTTPException(
            status_code=404,
            detail="CAPTCHA not found or expired"
        )

    captcha_data = captcha_store[captcha_id]

    # Expiry check
    if datetime.now() > captcha_data["expires_at"]:

        del captcha_store[captcha_id]

        raise HTTPException(
            status_code=410,
            detail="CAPTCHA expired"
        )

    # Attempt limit
    if captcha_data["attempts"] >= MAX_ATTEMPTS:

        del captcha_store[captcha_id]

        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Generate a new CAPTCHA."
        )

    captcha_data["attempts"] += 1

    # Case-insensitive verification
    if user_input.lower() == captcha_data["text"].lower():

        del captcha_store[captcha_id]

        return VerifyResponse(
            valid=True,
            message="CAPTCHA verified successfully!"
        )

    remaining = MAX_ATTEMPTS - captcha_data["attempts"]

    return VerifyResponse(
        valid=False,
        message=f"Incorrect CAPTCHA. {remaining} attempts remaining."
    )


# --------------------------------------------------
# RUN SERVER
# --------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000
    )