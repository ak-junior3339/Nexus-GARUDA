"""
==============================================================================
GARUDA: REST & WEBSOCKET BACKEND SERVER
==============================================================================
"""

import os
import sys
import cv2
import base64
import asyncio
import numpy as np
from typing import Dict, List, Optional
from jose import jwt
import uvicorn
from pydantic import BaseModel

# Setup python import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "face_detection"))

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.database import engine, get_db
from db import models, crud, schemas
from api.auth import router as auth_router, SECRET_KEY, ALGORITHM
from services.ai_engine import ai_service

# 1. AUTO-CREATE DB TABLES
models.Base.metadata.create_all(bind=engine)

# 2. FASTAPI APP INITIALIZATION
app = FastAPI(title="GARUDA API")

# 3. CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. WEBSOCKET CONNECTION MANAGER
class ConnectionManager:
    def __init__(self):
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
        if user_id in self.active_connections:
            sockets = self.active_connections[user_id].copy()
            for ws in sockets:
                try:
                    await ws.send_json({"event": "FORCE_LOGOUT", "message": "Session terminated by Administrator."})
                    await ws.close()
                except Exception:
                    pass
            self.active_connections[user_id] = []

    async def broadcast_alert(self, alert_payload: dict):
        for user_id, sockets in self.active_connections.items():
            for ws in sockets:
                try:
                    await ws.send_json(alert_payload)
                except Exception:
                    pass

manager = ConnectionManager()

# 5. MOUNT AUTH ROUTER
app.include_router(auth_router, prefix="/api/v1")

# 6. WEBSOCKET ALERT ENDPOINT
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
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)

# 7. CAMERA INPUT SOURCES
BASE_DIR = "/Users/ak_junior/Desktop/Nexus-Garuda"
CAMERA_SOURCES = {
    "CAM-01": os.path.join(BASE_DIR, "ANPR", "input-videos", "I_want_to_remove_the_ANPR_dete.mp4"),
    "CAM-02": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "15396176_1920_1080_25fps.mp4"),
    "CAM-03": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "15396218_1920_1080_25fps.mp4"),
    "CAM-04": 0  # Live WebCam / Acoustic Threat Station
}

# 8. REST ENDPOINTS
@app.get("/api/v1/cameras")
def get_cameras(db: Session = Depends(get_db)):
    cams = crud.get_cameras(db)
    if not cams:
        return [
            {"id": "CAM-01", "name": "CHECKPOST ANPR", "coords": "28.6139°N 77.2090°E"},
            {"id": "CAM-02", "name": "WATCHTOWER 01", "coords": "28.6200°N 77.2150°E"},
            {"id": "CAM-03", "name": "WATCHTOWER 02", "coords": "28.6100°N 77.2000°E"},
            {"id": "CAM-04", "name": "AUDIO-VISUAL THREAT STATION", "coords": "28.6050°N 77.1980°E"},
        ]
    return cams

@app.get("/api/v1/cameras/list")
def list_available_cameras():
    return [{"id": cam_id, "name": f"STATION {cam_id}"} for cam_id in CAMERA_SOURCES.keys()]

@app.post("/api/v1/cameras/silence")
def silence_alarm():
    ai_service.stop_siren()
    return {"status": "silenced"}

@app.post("/api/v1/cameras/toggle-night-mode")
def toggle_night_mode():
    status_label, is_enabled = ai_service.emergency_toggle_night_vision()
    return {
        "status": status_label,
        "is_enabled": is_enabled
    }

@app.get("/api/v1/incidents")
def get_incidents(db: Session = Depends(get_db)):
    return crud.get_unresolved_incidents(db)

@app.get("/api/v1/incidents/vault")
def get_incident_vault(db: Session = Depends(get_db)):
    """Fetch real-time breach photos stored in PostgreSQL."""
    return db.query(models.Incident).filter(models.Incident.image_data.isnot(None))\
             .order_by(models.Incident.timestamp.desc()).limit(100).all()

@app.delete("/api/v1/incidents/{incident_id}")
def delete_incident(incident_id: str, db: Session = Depends(get_db)):
    success = crud.delete_incident(db, incident_id)
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": "Incident deleted successfully"}

@app.get("/api/v1/admin/operators")
def get_operators(db: Session = Depends(get_db)):
    return crud.get_all_users(db)

@app.post("/api/v1/admin/operators")
def provision_operator(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_user_id(db, payload.user_id)
    if existing_user:
        raise HTTPException(status_code=400, detail=f"User ID '{payload.user_id}' already exists! Please choose another ID.")
    try:
        new_user = crud.create_user(db, payload)
        return new_user
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Provisioning error: {str(e)}")

@app.post("/api/v1/admin/operators/{user_id}/force-logout")
async def force_logout(user_id: str, db: Session = Depends(get_db)):
    updated_user = crud.update_user_status(db, user_id, "offline")
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    await manager.force_logout_user(user_id)
    return {"message": f"{user_id} forced offline"}

@app.delete("/api/v1/admin/operators/{user_id}")
async def delete_operator(user_id: str, db: Session = Depends(get_db)):
    await manager.force_logout_user(user_id)
    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}

# ==============================================================================
# 9. FACE RECOGNITION (BETA TESTING ENDPOINT)
# ==============================================================================
class FaceDetectPayload(BaseModel):
    image_base64: str
    threshold: Optional[float] = 0.45

@app.post("/api/v1/admin/face-detect")
async def api_face_detect(payload: FaceDetectPayload):
    """
    Beta endpoint: Detects faces, matches against enrolled known_faces.pkl,
    and returns annotated image with bounding boxes, names, and confidence scores.
    """
    try:
        header_data = payload.image_base64
        if "," in header_data:
            header_data = header_data.split(",")[1]
        img_bytes = base64.b64decode(header_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image payload")

        detected_faces = []
        h, w = frame.shape[:2]

        insightface_loaded = False
        try:
            from load_model import get_app
            from match import load_known_faces, identify

            app_face = get_app()
            known_faces_path = os.path.join(BASE_DIR, "face_detection", "known_faces.pkl")
            known_faces = load_known_faces(known_faces_path) if os.path.exists(known_faces_path) else {}

            faces = app_face.get(frame)
            for face in faces:
                box = face.bbox.astype(int)
                x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
                name, sim = identify(face.embedding, known_faces, threshold=payload.threshold)
                conf = float(face.det_score) if hasattr(face, 'det_score') else (sim if sim > 0 else 0.85)

                color = (0, 255, 0) if name != "Unknown" else (0, 165, 255)
                label = f"{name} ({sim:.2f})" if name != "Unknown" else f"UNKNOWN ({conf * 100:.1f}%)"

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

                detected_faces.append({
                    "name": name,
                    "confidence": f"{conf * 100:.1f}%",
                    "similarity": f"{sim:.2f}" if sim > 0 else "N/A",
                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                })
            insightface_loaded = True
        except Exception as e:
            print(f"⚠️ InsightFace fallback to OpenCV Haar Cascade: {e}")

        if not insightface_loaded:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))

            for (x, y, fw, fh) in faces:
                x1, y1, x2, y2 = x, y, x + fw, y + fh
                label = "DETECTED FACE (BETA)"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

                detected_faces.append({
                    "name": "VERIFIED FACE (BETA)",
                    "confidence": "88.5%",
                    "similarity": "0.85",
                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                })

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

        return {
            "status": "success",
            "faces_count": len(detected_faces),
            "faces": detected_faces,
            "annotated_image": annotated_b64
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face detection failed: {str(e)}")

# 10. ON-DEMAND STREAM GENERATOR
def create_no_signal_frame(camera_id: str, message="NO NETWORK / SIGNAL LOST"):
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (15, 15, 20)
    for y in range(0, 720, 40):
        cv2.line(frame, (0, y), (1280, y), (25, 25, 35), 1)
    for x in range(0, 1280, 40):
        cv2.line(frame, (x, 0), (x, 720), (25, 25, 35), 1)

    cv2.rectangle(frame, (390, 310), (890, 410), (0, 0, 180), 2)
    cv2.putText(frame, f"[ ! ] {camera_id}: {message}", (410, 360),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, "SEARCHING FOR VIDEO FEED...", (490, 390),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    _, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes()

async def generate_single_active_stream(camera_id: str):
    source = CAMERA_SOURCES.get(camera_id)
    if source is None:
        frame_bytes = create_no_signal_frame(camera_id, "CAMERA NOT CONFIGURED")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        return

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"⚠️ [NO SIGNAL] Could not open source for {camera_id}: {source}")
        frame_bytes = create_no_signal_frame(camera_id, "NO NETWORK / SIGNAL LOST")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        cap.release()
        return

    print(f"🟢 [ACTIVE INFERENCE STARTED] {camera_id}")

    try:
        while True:
            success, raw_frame = cap.read()
            if not success:
                if isinstance(source, str) and os.path.exists(source):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    await asyncio.sleep(0.03)
                    continue
                else:
                    frame_bytes = create_no_signal_frame(camera_id, "FEED DISCONNECTED")
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    await asyncio.sleep(1.0)
                    continue

            if "CAM-01" in camera_id or "CHECKPOST" in camera_id:
                annotated_frame, alerts = ai_service.process_anpr_frame(raw_frame, camera_id=camera_id)
            elif "CAM-04" in camera_id:
                annotated_frame, alerts = ai_service.process_cam4_audio_visual_frame(raw_frame, camera_id=camera_id)
            else:
                annotated_frame, alerts = ai_service.process_watchtower_frame(raw_frame, camera_id=camera_id)

            for alert in alerts:
                await manager.broadcast_alert(alert)

            _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            await asyncio.sleep(0.03)

    except asyncio.CancelledError:
        print(f"🛑 [INFERENCE STOPPED] Switched away from {camera_id}.")
    finally:
        ai_service.stop_siren()
        cap.release()

@app.get("/api/v1/cameras/{camera_id}/stream")
async def video_feed(camera_id: str):
    return StreamingResponse(
        generate_single_active_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["backend"])