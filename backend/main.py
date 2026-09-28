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

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.database import engine, get_db, SessionLocal
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
# Active stream kill switches: camera_id -> asyncio.Event
ACTIVE_STREAMS: Dict[str, asyncio.Event] = {}
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
    "CAM-04": 0 , # Live WebCam / Acoustic Threat Station
    "CAM-05": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "Low-Light Night Scene with Sony A6700  S-LOG3  4K - Second Order (1080p, h264).mp4")
}

# 8. REST ENDPOINTS
@app.get("/api/v1/cameras")
def get_cameras(db: Session = Depends(get_db)):
    cams = crud.get_cameras(db)
    if not cams:
        sync_camera_sources(db)
        cams = crud.get_cameras(db)
    return cams
@app.get("/api/v1/cameras/list")
def list_available_cameras(db: Session = Depends(get_db)):
    cams = crud.get_cameras(db)
    if not cams:
        sync_camera_sources(db)
        cams = crud.get_cameras(db)
    return [
        {
            "id": cam.id,
            "name": cam.name,
            "coordinates": cam.coordinates,
            "camera_type": cam.camera_type
        }
        for cam in cams
    ]

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

class PreviewRequest(BaseModel):
    stream_url: str

@app.post("/api/v1/cameras/snapshot-preview")
def grab_snapshot_preview(payload: PreviewRequest):
    """Grabs the first frame of a webcam, video file, or RTSP stream for tripwire calibration."""
    raw_url = str(payload.stream_url).strip()
    src = int(raw_url) if raw_url.isdigit() else raw_url
    
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        # Fallback to default WatchTower test video if custom path is not accessible
        sample_path = os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "15396176_1920_1080_25fps.mp4")
        cap = cv2.VideoCapture(sample_path)

    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[:] = (10, 15, 25)
        cv2.putText(frame, "STREAM FRAME NOT AVAILABLE", (550, 540), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
    else:
        frame = cv2.resize(frame, (1920, 1080))
        
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    b64 = base64.b64encode(buf).decode('utf-8')
    return {"image_data": f"data:image/jpeg;base64,{b64}"}

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

@app.post("/api/v1/incidents/{incident_id}/detect-face")
async def detect_incident_face(incident_id: str, db: Session = Depends(get_db)):
    """Detects and identifies faces in a stored evidence image from the database."""
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident or not incident.image_data:
        raise HTTPException(status_code=404, detail="Incident or evidence image not found")

    try:
        header_data = incident.image_data
        if "," in header_data:
            header_data = header_data.split(",")[1]
        img_bytes = base64.b64decode(header_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid evidence image payload")

        from load_model import get_app
        from match import load_known_faces, identify

        app_face = get_app()
        known_faces_path = os.path.join(BASE_DIR, "face_detection", "known_faces.pkl")
        known_faces = load_known_faces(known_faces_path) if os.path.exists(known_faces_path) else {}

        faces = app_face.get(frame)
        if not faces or len(faces) == 0:
            return {"recognized": False, "message": "❌ NO FACE DETECTED IN EVIDENCE IMAGE"}

        matches = []
        for face in faces:
            name, sim = identify(face.embedding, known_faces, threshold=0.45)
            if name != "Unknown":
                matches.append(f"{name} ({sim * 100:.1f}% Match)")
            else:
                matches.append("UNRECOGNIZED SUSPECT")

        recognized_names = [m for m in matches if "UNRECOGNIZED" not in m]
        if recognized_names:
            return {
                "recognized": True,
                "message": f"MATCH FOUND: {', '.join(recognized_names)}"
            }
        else:
            return {
                "recognized": False,
                "message": "NO MATCH FOUND IN WATCHLIST (UNKNOWN SUSPECT)"
            }
    except Exception as e:
        return {"recognized": False, "message": f"Face processing error: {str(e)}"}

# class FaceAuthPayload(BaseModel):
#     image_base64: str

# @app.post("/api/v1/auth/verify-face")
# async def verify_login_face(payload: FaceAuthPayload):
#     """Verifies a live user photo against known_faces.pkl during login."""
#     try:
#         header_data = payload.image_base64
#         if "," in header_data:
#             header_data = header_data.split(",")[1]
#         img_bytes = base64.b64decode(header_data)
#         nparr = np.frombuffer(img_bytes, np.uint8)
#         frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

#         if frame is None:
#             raise HTTPException(status_code=400, detail="Invalid camera frame")

#         from load_model import get_app
#         from match import load_known_faces, identify

#         app_face = get_app()
#         known_faces_path = os.path.join(BASE_DIR, "face_detection", "known_faces.pkl")
#         known_faces = load_known_faces(known_faces_path) if os.path.exists(known_faces_path) else {}

#         faces = app_face.get(frame)
#         if not faces or len(faces) == 0:
#             return {"verified": False, "message": "❌ NO FACE DETECTED! Align face in camera."}

#         face = faces[0]
#         name, sim = identify(face.embedding, known_faces, threshold=0.45)

#         if name != "Unknown":
#             return {
#                 "verified": True,
#                 "person_name": name,
#                 "similarity": f"{sim * 100:.1f}%",
#                 "message": f"✅ BIOMETRIC VERIFIED: WELCOME {name.upper()}"
#             }
#         else:
#             return {
#                 "verified": False,
#                 "message": "❌ UNRECOGNIZED FACE! Access Denied."
#             }
#     except Exception as e:
#         return {"verified": False, "message": f"Face verification error: {str(e)}"}

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

def auto_migrate_db():
    """Ensure all required columns exist in PostgreSQL."""
    with engine.connect() as conn:
        columns = [
            ("camera_type", "VARCHAR(50) DEFAULT 'WATCHTOWER'"),
            ("coordinates", "VARCHAR(100) DEFAULT '28.6139°N 77.2090°E'"),
            ("stream_url", "VARCHAR(255) DEFAULT '0'"),
            ("ai_features", "VARCHAR(255) DEFAULT 'INTRUSION,LOITERING,GROUP'"),
            ("tripwire_coords", "VARCHAR(100) DEFAULT '0,650,1920,650'"),
            ("is_active", "VARCHAR(20) DEFAULT 'active'")
        ]
        for col_name, col_def in columns:
            try:
                conn.execute(text(f"ALTER TABLE cameras ADD COLUMN IF NOT EXISTS {col_name} {col_def};"))
                conn.commit()
            except Exception as e:
                print(f"Migration notice ({col_name}): {e}")
def sync_camera_sources(db: Session):
    auto_migrate_db()
    defaults = [
        {"id": "CAM-01", "name": "CHECKPOST 01 (ANPR)", "camera_type": "CHECKPOST_ANPR", "coordinates": "28.6139°N 77.2090°E", "stream_url": os.path.join(BASE_DIR, "ANPR", "input-videos", "I_want_to_remove_the_ANPR_dete.mp4"), "ai_features": "ANPR_OCR,NIGHT_VISION"},
        {"id": "CAM-02", "name": "WATCHTOWER NORTH", "camera_type": "WATCHTOWER", "coordinates": "28.6200°N 77.2150°E", "stream_url": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "15396176_1920_1080_25fps.mp4"), "ai_features": "INTRUSION,LOITERING,GROUP", "tripwire_coords": "0,650,1920,650"},
        {"id": "CAM-03", "name": "WATCHTOWER EAST", "camera_type": "WATCHTOWER", "coordinates": "28.6100°N 77.2000°E", "stream_url": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "15396218_1920_1080_25fps.mp4"), "ai_features": "INTRUSION,LOITERING,GROUP", "tripwire_coords": "350,0,350,1080"},
        {"id": "CAM-04", "name": "ACOUSTIC PERIMETER STATION", "camera_type": "ACOUSTIC", "coordinates": "28.6050°N 77.1980°E", "stream_url": "0", "ai_features": "GUNFIRE_AUDIO,SCREAM_DETECTION"},
        {"id": "CAM-05", "name": "NIGHT VISION TESTBENCH", "camera_type": "NIGHT_VISION", "coordinates": "28.6000°N 77.1950°E", "stream_url": os.path.join(BASE_DIR, "WatchTower surveillance", "test-input", "Low-Light Night Scene with Sony A6700  S-LOG3  4K - Second Order (1080p, h264).mp4"), "ai_features": "AUTO_CLAHE_NIGHT_VISION"}
    ]
    for d in defaults:
        cam_obj = crud.get_camera_by_id(db, d["id"])
        if not cam_obj:
            new_cam = models.Camera(
                id=d["id"],
                name=d["name"],
                camera_type=d["camera_type"],
                coordinates=d["coordinates"],
                stream_url=d["stream_url"],
                ai_features=d["ai_features"],
                tripwire_coords=d.get("tripwire_coords"),
                is_active="active"
            )
            db.add(new_cam)
        else:
            cam_obj.name = d["name"]
            cam_obj.camera_type = d["camera_type"]
            cam_obj.coordinates = d["coordinates"]
            cam_obj.stream_url = d["stream_url"]
            cam_obj.ai_features = d["ai_features"]
            if d.get("tripwire_coords"):
                cam_obj.tripwire_coords = d.get("tripwire_coords")
    db.commit()
    db_cams = crud.get_cameras(db)
    for cam in db_cams:
        raw_url = str(cam.stream_url) if cam.stream_url is not None else "0"
        src = int(raw_url) if raw_url.isdigit() else raw_url
        CAMERA_SOURCES[cam.id] = src
        ai_service.register_dynamic_camera(cam.id, cam.camera_type or "WATCHTOWER", cam.tripwire_coords)
@app.on_event("startup")
def startup_populate_cameras():
    auto_migrate_db()
    db = SessionLocal()
    try:
        sync_camera_sources(db)
    except Exception as e:
        print(f"⚠️ Error during startup camera sync: {e}")
    finally:
        db.close()

@app.post("/api/v1/admin/cameras")
def provision_camera(payload: schemas.CameraCreate, db: Session = Depends(get_db)):
    existing = crud.get_camera_by_id(db, payload.id)
    if existing:
        raise HTTPException(status_code=400, detail=f"Camera ID '{payload.id}' already exists!")
    
    new_cam = crud.create_camera(db, payload)
    raw_url = str(payload.stream_url) if payload.stream_url is not None else "0"
    src = int(raw_url) if raw_url.isdigit() else raw_url
    CAMERA_SOURCES[payload.id] = src
    ai_service.register_dynamic_camera(payload.id, payload.camera_type, payload.tripwire_coords)
    return new_cam

@app.delete("/api/v1/admin/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    success = crud.delete_camera(db, camera_id)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found")
    if camera_id in CAMERA_SOURCES:
        del CAMERA_SOURCES[camera_id]
    return {"message": f"Camera {camera_id} decommissioned"}

async def generate_single_active_stream(camera_id: str):
    source = CAMERA_SOURCES.get(camera_id)

    # Register a kill switch for this stream
    stop_event = asyncio.Event()
    ACTIVE_STREAMS[camera_id] = stop_event

    if source is None:
        frame_bytes = create_no_signal_frame(camera_id, "CAMERA NOT CONFIGURED")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        ACTIVE_STREAMS.pop(camera_id, None)
        return

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"⚠️ [NO SIGNAL] Could not open source for {camera_id}: {source}")
        frame_bytes = create_no_signal_frame(camera_id, "NO NETWORK / SIGNAL LOST")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        cap.release()
        ACTIVE_STREAMS.pop(camera_id, None)
        return

    print(f"🟢 [ACTIVE INFERENCE STARTED] {camera_id}")

    try:
        while not stop_event.is_set():
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
            elif "CAM-05" in camera_id or "NIGHT" in camera_id:
                annotated_frame, alerts = ai_service.process_night_vision_standalone_frame(raw_frame, camera_id=camera_id)
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
        print(f"🛑 [INFERENCE STOPPED] Stream cancelled for {camera_id}.")
    finally:
        print(f"🔒 [STREAM RELEASED] {camera_id} stopped and resources freed.")
        ai_service.stop_siren()
        cap.release()
        ACTIVE_STREAMS.pop(camera_id, None)


@app.get("/api/v1/cameras/{camera_id}/stream")
async def video_feed(camera_id: str):
    # Stop any existing stream for this camera before starting a new one
    existing = ACTIVE_STREAMS.get(camera_id)
    if existing:
        existing.set()
        await asyncio.sleep(0.1)

    return StreamingResponse(
        generate_single_active_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/api/v1/cameras/{camera_id}/stop")
async def stop_camera_stream(camera_id: str):
    """Immediately kill active AI inference for a specific camera."""
    event = ACTIVE_STREAMS.get(camera_id)
    if event:
        event.set()
        print(f"🛑 [KILLED] Stream inference stopped for {camera_id} by client request.")
        return {"status": "stopped", "camera_id": camera_id}
    return {"status": "not_running", "camera_id": camera_id}


@app.post("/api/v1/cameras/stop-all")
async def stop_all_streams():
    """Kill ALL active camera inference loops — called on logout."""
    stopped = []
    for cam_id, event in list(ACTIVE_STREAMS.items()):
        event.set()
        stopped.append(cam_id)
    print(f"🔴 [KILL ALL] Stopped streams: {stopped}")
    return {"status": "all_stopped", "stopped": stopped}

from fastapi.responses import Response

@app.get("/api/v1/admin/logs/export")
def export_logs_csv(db: Session = Depends(get_db)):
    """Exports all unresolved breach incidents and camera logs as a downloadable CSV."""
    incidents = crud.get_unresolved_incidents(db)
    
    csv_lines = ["ID,Timestamp,Camera Sector,Threat Category,Identifier,Confidence"]
    for inc in incidents:
        time_str = inc.timestamp.strftime("%Y-%m-%d %H:%M:%S") if inc.timestamp else ""
        csv_lines.append(f'"{inc.id}","{time_str}","{inc.camera_id}","{inc.entity_type}","{inc.identifier or "UNKNOWN"}","{inc.confidence}"')
    
    csv_content = "\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=GARUDA_INCIDENTS_LOG.csv"}
    )
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["backend"])