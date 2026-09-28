from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import io

from db.database import get_db
from db import crud, schemas
# Import the captcha generator and image fetcher
from .captcha import verify_captcha, generate_captcha, get_captcha_image

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "change-this-later"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha_answer: str

# ==================================================
# 1. CAPTCHA ENDPOINTS
# ==================================================
@router.get("/captcha/generate")
def api_generate_captcha():
    """Creates a new CAPTCHA and returns its ID."""
    captcha_id = generate_captcha()
    return {"captcha_id": captcha_id}

@router.get("/captcha/image/{captcha_id}")
def api_get_captcha_image(captcha_id: str):
    """Returns the actual PNG image for the given CAPTCHA ID."""
    image = get_captcha_image(captcha_id)
    if not image:
        raise HTTPException(status_code=404, detail="CAPTCHA not found or expired.")
    
    # Convert PIL Image to bytes to send over HTTP
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# ==================================================
# 2. LOGIN ENDPOINT
# ==================================================
@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # 1. Verify CAPTCHA
    captcha_valid, captcha_message = verify_captcha(data.captcha_id, data.captcha_answer)
    if not captcha_valid:
        raise HTTPException(status_code=400, detail=captcha_message)

    # 2. Fetch user from PostgreSQL
    user = crud.get_user_by_user_id(db, data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid User ID or Password")
        
    # 3. Verify Bcrypt Password
    if not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid User ID or Password")
        
    # 4. Generate JWT Token
    payload = {
        "sub": user.user_id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # 5. Log the session in the Audit Table
    audit_record = schemas.AuditLogCreate(
        user_id=user.id,
        action_category="SESSION",
        event_details="Authenticated successfully",
        target_system="Command Center"
    )
    crud.create_audit_log(db, log=audit_record)
    
    # --- ADD THIS LINE TO ACTIVATE THE USER ---
    crud.update_user_status(db, user.user_id, "online")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "full_name": user.full_name,
        "role": user.role
    }


@router.post("/logout")
def logout():
    """Acknowledge logout for the stateless JWT authentication flow."""
    return {"message": "Successfully logged out"}

import os
import sys
import cv2
import base64
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "face_detection"))

class FaceAuthPayload(BaseModel):
    image_base64: str

@router.post("/verify-face")
async def verify_login_face(payload: FaceAuthPayload):
    """Verifies a live user photo against known_faces.pkl during login."""
    try:
        header_data = payload.image_base64
        if "," in header_data:
            header_data = header_data.split(",")[1]
        img_bytes = base64.b64decode(header_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid camera frame")

        from load_model import get_app
        from match import load_known_faces, identify

        app_face = get_app()
        BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        known_faces_path = os.path.join(BASE_DIR, "face_detection", "known_faces.pkl")
        known_faces = load_known_faces(known_faces_path) if os.path.exists(known_faces_path) else {}

        faces = app_face.get(frame)
        if not faces or len(faces) == 0:
            return {"verified": False, "message": "❌ NO FACE DETECTED! Align your face in camera."}

        face = faces[0]
        name, sim = identify(face.embedding, known_faces, threshold=0.45)

        if name != "Unknown":
            return {
                "verified": True,
                "person_name": name,
                "similarity": f"{sim * 100:.1f}%",
                "message": f"✅ BIOMETRIC VERIFIED: WELCOME {name.upper()}"
            }
        else:
            return {
                "verified": False,
                "message": "❌ UNRECOGNIZED FACE! Access Denied."
            }
    except Exception as e:
        return {"verified": False, "message": f"Face verification error: {str(e)}"}