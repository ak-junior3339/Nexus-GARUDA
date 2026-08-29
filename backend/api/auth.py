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