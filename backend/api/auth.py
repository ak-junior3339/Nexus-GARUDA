from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# Password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# JWT configuration
SECRET_KEY = "change-this-later"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# Request model for login  (expect JSON body with username and password)
class LoginRequest(BaseModel):
    username: str
    password: str


# -------------------------
# Login
# -------------------------

@router.post("/login")
def login(data: LoginRequest):
    # Fetch user from db
    user = get_user_from_db(data.username)  # Replace with actual DB call

    # User doesn't exist
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Check password
    if not pwd_context.verify(
        data.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Create JWT payload
    payload = {
        "sub": user["username"],
        "exp": datetime.utcnow()
        + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }

    # Create token
    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }