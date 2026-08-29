# backend/seed.py
from db.database import SessionLocal, engine
from db import models
from passlib.context import CryptContext

# 1. CREATE ALL TABLES IF THEY DON'T EXIST YET
print("Creating database tables...")
models.Base.metadata.create_all(bind=engine)

# 2. HASH CONFIG & DB SESSION
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()

# 3. SEED THE ADMIN
print("Checking for existing admin...")
if not db.query(models.User).filter(models.User.user_id == "ID-0001").first():
    admin = models.User(
        user_id="ID-0001",
        password_hash=pwd_context.hash("admin123"),
        full_name="SUPERADMIN ROOT",
        role="admin",
        clearance_level="SUPERADMIN ROOT",
        status="offline"
    )
    db.add(admin)
    db.commit()
    print("✅ Superadmin created! (User: ID-0001 | Pass: admin123)")
else:
    print("⚠️ Admin already exists. You are good to go!")

db.close()