from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Dict, List
from jose import jwt
import uvicorn

from db.database import engine, get_db
from db import models, crud, schemas
from api.auth import router as auth_router, SECRET_KEY, ALGORITHM

# 1. AUTO-CREATE DATABASE TABLES
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="GARUDA API")

# 2. CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. WEBSOCKET CONNECTION MANAGER
class ConnectionManager:
    def __init__(self):
        # Maps user_id -> List of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)

    async def force_logout_user(self, user_id: str):
        """Sends a FORCE_LOGOUT signal to all active sockets of a specific user."""
        if user_id in self.active_connections:
            sockets = self.active_connections[user_id].copy()
            for ws in sockets:
                try:
                    await ws.send_json({"event": "FORCE_LOGOUT", "message": "Session terminated by Administrator."})
                    await ws.close()
                except Exception:
                    pass
            self.active_connections[user_id] = []

manager = ConnectionManager()

# 4. MOUNT ROUTERS
app.include_router(auth_router, prefix="/api/v1")

# 5. WEBSOCKET ENDPOINT FOR REAL-TIME ALERTS & SESSION CONTROL
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket, token: str = None):
    user_id = "UNKNOWN"
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub", "UNKNOWN")
        except Exception:
            pass

    await manager.connect(user_id, websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)

# 6. DASHBOARD & ADMIN ENDPOINTS
@app.get("/api/v1/cameras")
def get_cameras(db: Session = Depends(get_db)):
    cams = crud.get_cameras(db)
    if not cams:
        return [
            {"id": "CAM-01", "name": "CHECKPOST SOUTH", "coords": "28.6139°N 77.2090°E"},
            {"id": "CAM-02", "name": "WATCHTOWER NORTH", "coords": "28.6200°N 77.2150°E"}
        ]
    return cams

@app.get("/api/v1/incidents")
def get_incidents(db: Session = Depends(get_db)):
    return crud.get_unresolved_incidents(db)

@app.get("/api/v1/admin/operators")
def get_operators(db: Session = Depends(get_db)):
    return crud.get_all_users(db)

@app.post("/api/v1/admin/operators")
def provision_operator(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_user_id(db, payload.user_id)
    if existing_user:
        raise HTTPException(status_code=400, detail="User ID already exists!")
    return crud.create_user(db, payload)

@app.post("/api/v1/admin/operators/{user_id}/force-logout")
async def force_logout(user_id: str, db: Session = Depends(get_db)):
    """Change operator status to offline AND send instant WebSocket kill signal."""
    updated_user = crud.update_user_status(db, user_id, "offline")
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Broadcast force logout signal to user's active session
    await manager.force_logout_user(user_id)
    return {"message": f"{user_id} forced offline"}

@app.delete("/api/v1/admin/operators/{user_id}")
async def delete_operator(user_id: str, db: Session = Depends(get_db)):
    """Permanently delete an operator and disconnect their session."""
    await manager.force_logout_user(user_id)
    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)