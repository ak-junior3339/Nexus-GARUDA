from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

from ..db.db_operations import get_user_from_db

from .captcha import verify_captcha

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# ==================================================
# PASSWORD HASHING
# ==================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# ==================================================
# JWT CONFIGURATION
# ==================================================

SECRET_KEY = "change-this-later"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ==================================================
# LOGIN REQUEST
# ==================================================

class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha_answer: str

# ==================================================
# LOGIN
# ==================================================

@router.post("/login")
def login(data: LoginRequest):

    # ------------------------------------------
    # 1. Verify CAPTCHA
    # ------------------------------------------

    captcha_valid, captcha_message = verify_captcha(
        data.captcha_id,
        data.captcha_answer
    )

    if not captcha_valid:
        raise HTTPException(
            status_code=400,
            detail=captcha_message
        )

    # ------------------------------------------
    # 2. Fetch user from database
    # ------------------------------------------

    user = get_user_from_db(data.username)  #--> from db/db_operations.py

    if user is None:
        raise HTTPException(status_code=401,detail="Invalid username or password")

    # ------------------------------------------
    # 3. Check password
    # ------------------------------------------

    if not pwd_context.verify(
        data.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # ------------------------------------------
    # 4. Create JWT
    # ------------------------------------------

    payload = {
        "sub": user["username"],
        "exp": datetime.utcnow()
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    # ------------------------------------------
    # 5. Return token
    # ------------------------------------------

    return {
        "access_token": token,
        "token_type": "bearer"
    }
