"""
==============================================================================
GARUDA: INTEGRATED AI SURVEILLANCE & THREAT DETECTION ENGINE
Combines:
  1. WatchTower YOLO11s Threat Analytics (Intrusions, Loitering, Group Clusters)
  2. Automatic CLAHE Night Vision Enhancement + Emergency 'N' Hotkey Override
  3. Audio Siren & Evidence Snapshot Logging (with Instant Silence Control)
  4. Checkpost ANPR (FRAME_SKIP = 3, is_same_plate, merge_plate_reads)
  5. WatchTower Cameras (CAM-02, CAM-03, CAM-04):
     - Breach Detected (Intruder Person, Vehicle Breach, Loitering, Group Convergence)
     - Live Evidence Frame encoded to Base64 and saved directly to PostgreSQL Database
  6. Checkpost ANPR (CAM-01):
     - Plate Text Logged to CSV & Telemetry Feed ONLY (NO database images)
==============================================================================
"""

import os
import re
import cv2
import csv
import math
import time
import base64
import torch
import pygame
import numpy as np
from datetime import datetime
from collections import defaultdict
from shapely.geometry import LineString
from ultralytics import YOLO

# Database Imports
from db.database import SessionLocal
from db import models

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class GarudaIntegratedAIEngine:
    def __init__(self, base_dir="/Users/ak_junior/Desktop/Nexus-Garuda"):
        self.base_dir = base_dir

        # -------------------------------------------------------------
        # 1. DIRECTORY PATHS
        # -------------------------------------------------------------
        self.WT_MODEL_PATH = os.path.join(base_dir, "WatchTower surveillance", "WTbest.pt")
        self.ANPR_MODEL_PATH = os.path.join(base_dir, "ANPR", "Model", "anprbest.pt")
        self.ALARM_PATH = os.path.join(base_dir, "WatchTower surveillance", "Alert", "alarm.wav")

        self.PARENT_LOG_DIR = os.path.join(base_dir, "Logs")
        self.BREACH_LOG_DIR = os.path.join(self.PARENT_LOG_DIR, "breach_logs")
        self.PERSON_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "person")
        self.CAR_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "car")
        self.LOITER_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "loitering")
        self.GROUP_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "group_clustering")

        for d in [self.PARENT_LOG_DIR, self.BREACH_LOG_DIR, self.PERSON_LOG_DIR, self.CAR_LOG_DIR, self.LOITER_LOG_DIR, self.GROUP_LOG_DIR]:
            os.makedirs(d, exist_ok=True)

        self.ALL_OBJECTS_CSV_LOG = os.path.join(self.PARENT_LOG_DIR, "surveillance_log.csv")
        self.ANPR_DETECTION_CSV = os.path.join(self.PARENT_LOG_DIR, "detection.csv")

        if not os.path.exists(self.ALL_OBJECTS_CSV_LOG):
            with open(self.ALL_OBJECTS_CSV_LOG, "w", newline="") as f:
                csv.writer(f).writerow(["timestamp", "event_type", "object_type", "track_id", "confidence", "details", "evidence_file"])

        # -------------------------------------------------------------
        # 2. AUDIO SIREN
        # -------------------------------------------------------------
        pygame.mixer.init()
        try:
            self.alarm_sound = pygame.mixer.Sound(self.ALARM_PATH)
        except Exception:
            self.alarm_sound = None

        self.last_alarm_time = 0
        self.ALARM_COOLDOWN = 3.0

        # -------------------------------------------------------------
        # 3. YOLO & OCR INITIALIZATION
        # -------------------------------------------------------------
        try:
            self.wt_model = YOLO(self.WT_MODEL_PATH)
        except Exception:
            self.wt_model = YOLO("yolo11s.pt")

        try:
            self.anpr_model = YOLO(self.ANPR_MODEL_PATH)
        except Exception:
            self.anpr_model = YOLO("yolov8n.pt")

        self.reader = None
        if EASYOCR_AVAILABLE:
            try:
                self.reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available())
            except Exception:
                try:
                    self.reader = easyocr.Reader(['en'], gpu=False)
                except Exception:
                    pass

        # -------------------------------------------------------------
        # 4. SURVEILLANCE STATE
        # -------------------------------------------------------------
        self.trajectory_history = defaultdict(list)
        self.anchor_points = {}
        self.seen_all_objects = set()
        self.logged_intruders = set()
        self.logged_vehicles = set()
        self.logged_loiterers = set()

        self.LOITER_TIME_LIMIT = 20.0
        self.LOITER_RADIUS = 150
        self.GROUP_CLUSTER_RADIUS = 120
        self.GROUP_MIN_PEOPLE = 3
        self.GROUP_ALERT_COOLDOWN = 15.0
        self.last_group_alert_time = 0.0

        self.active_alerts = []
        self.frame_index = 0
        self.AUTO_NIGHT_MODE = True
        self.NIGHT_MODE_ENABLED = False

        # ANPR State
        self.FRAME_SKIP = 2
        self.MIN_PLATE_LENGTH = 4
        self.DETECTION_CONF_THRESHOLD = 0.40
        self.OCR_CONF_THRESHOLD = 0.40
        self.anpr_frame_count = 0
        self.anpr_last_box = None
        self.anpr_last_display_str = None
        self.anpr_all_reads = []
        self.anpr_seen_cooldown = {}

        self.tripwire_lines = {
            "CAM-02": LineString([(0, 650), (1920, 650)]),
            "CAM-03": LineString([(350, 0), (350, 1080)]),
            "CAM-04": LineString([(0, 650), (1920, 650)]),
        }

    # -----------------------------------------------------------------
    # WATCHTOWER REAL-TIME DATABASE INSERTION (FRAME -> BASE64 -> DB)
    # -----------------------------------------------------------------
    def save_watchtower_breach_to_db(self, camera_id: str, entity_type: str, identifier: str, confidence: float, frame_bgr: np.ndarray, local_file_path: str = None):
        """
        Saves ONLY Watchtower live breach snapshots (Intruders, Cars, Loitering, Groups) into PostgreSQL.
        """
        try:
            _, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            base64_image = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

            db = SessionLocal()
            try:
                incident = models.Incident(
                    camera_id=camera_id,
                    entity_type=entity_type,
                    identifier=str(identifier),
                    confidence=float(confidence),
                    image_path=local_file_path,
                    image_data=base64_image,
                    status="UNRESOLVED"
                )
                db.add(incident)
                db.commit()
                print(f"🚨 [WATCHTOWER DB SAVED] {entity_type} ({identifier}) from {camera_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️ Failed to save watchtower breach to DB: {e}")

    # -----------------------------------------------------------------
    # SIREN CONTROLS
    # -----------------------------------------------------------------
    def play_siren(self):
        current_time = time.time()
        if (current_time - self.last_alarm_time) > self.ALARM_COOLDOWN:
            self.last_alarm_time = current_time
            if self.alarm_sound:
                self.alarm_sound.play()
            else:
                os.system("afplay /System/Library/Sounds/Submarine.aiff &")

    def stop_siren(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
            os.system("pkill -9 afplay 2>/dev/null")
        except Exception:
            pass

    # -----------------------------------------------------------------
    # NIGHT VISION
    # -----------------------------------------------------------------
    def apply_night_vision_enhancement(self, frame):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l)
        return cv2.cvtColor(cv2.merge((enhanced_l, a, b)), cv2.COLOR_LAB2BGR)

    def emergency_toggle_night_vision(self):
        self.AUTO_NIGHT_MODE = False
        self.NIGHT_MODE_ENABLED = not self.NIGHT_MODE_ENABLED
        status = "MANUAL ON" if self.NIGHT_MODE_ENABLED else "MANUAL OFF"
        return status, self.NIGHT_MODE_ENABLED

    def log_event(self, event_type, object_type, track_id, confidence, details="", evidence_file=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.ALL_OBJECTS_CSV_LOG, "a", newline="") as f:
            csv.writer(f).writerow([timestamp, event_type, object_type, track_id, f"{confidence:.2f}", details, evidence_file])

    def check_group_clustering(self, person_points):
        n = len(person_points)
        if n < self.GROUP_MIN_PEOPLE:
            return set(), []

        parent = list(range(n))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        for i in range(n):
            for j in range(i + 1, n):
                _, pt_i = person_points[i]
                _, pt_j = person_points[j]
                if math.hypot(pt_i[0] - pt_j[0], pt_i[1] - pt_j[1]) <= self.GROUP_CLUSTER_RADIUS:
                    union(i, j)

        clusters_by_root = defaultdict(list)
        for idx, (track_id, _) in enumerate(person_points):
            clusters_by_root[find(idx)].append(track_id)

        qualifying = [m for m in clusters_by_root.values() if len(m) >= self.GROUP_MIN_PEOPLE]
        return {tid for cluster in qualifying for tid in cluster}, qualifying

    def check_breach(self, camera_id, track_id, current_center_pt):
        history = self.trajectory_history[track_id]
        history.append(current_center_pt)
        if len(history) > 20:
            history.pop(0)

        tripwire_line = self.tripwire_lines.get(camera_id, LineString([(0, 540), (1920, 540)]))
        if len(history) >= 2:
            movement_vector = LineString([history[-2], current_center_pt])
            if movement_vector.intersects(tripwire_line):
                return True
        return False

    def check_loitering(self, track_id, current_center_pt):
        current_time = time.time()
        cx, cy = current_center_pt
        if track_id not in self.anchor_points:
            self.anchor_points[track_id] = (current_time, cx, cy)
            return False, 0.0

        start_time, anchor_x, anchor_y = self.anchor_points[track_id]
        duration = current_time - start_time
        if duration < self.LOITER_TIME_LIMIT:
            return False, duration

        if math.hypot(cx - anchor_x, cy - anchor_y) < self.LOITER_RADIUS:
            return True, duration
        else:
            self.anchor_points[track_id] = (current_time, cx, cy)
            return False, 0.0

    # -----------------------------------------------------------------
    # MAIN WATCHTOWER LIVE PROCESSING (CAM-02, CAM-03, CAM-04)
    # -----------------------------------------------------------------
    def process_watchtower_frame(self, raw_frame, camera_id="CAM-02"):
        try:
            self.frame_index += 1
            h, w, _ = raw_frame.shape
            ws_alerts = []

            # Automatic Night Mode
            if self.AUTO_NIGHT_MODE:
                avg_brightness = np.mean(cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY))
                self.NIGHT_MODE_ENABLED = bool(avg_brightness < 60)

            processed_frame = self.apply_night_vision_enhancement(raw_frame) if self.NIGHT_MODE_ENABLED else raw_frame.copy()
            clean_snapshot = processed_frame.copy()

            # Draw Perimeter Fence
            tw_line = self.tripwire_lines.get(camera_id, LineString([(0, int(h * 0.6)), (w, int(h * 0.6))]))
            p1, p2 = tw_line.coords[0], tw_line.coords[1]
            cv2.line(processed_frame, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 0, 255), 2)
            cv2.putText(processed_frame, "RESTRICTED PERIMETER FENCE", (int(p1[0]), max(20, int(p1[1]) - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            results = self.wt_model.track(source=processed_frame, persist=True, conf=0.30, verbose=False)[0]

            if results.boxes is not None and results.boxes.id is not None:
                boxes = results.boxes.xyxy.cpu().numpy()
                track_ids = results.boxes.id.int().cpu().numpy()
                class_ids = results.boxes.cls.int().cpu().numpy()
                confs = results.boxes.conf.cpu().numpy()

                person_points = [
                    (int(tid), ((int(box[0]) + int(box[2])) // 2, (int(box[1]) + int(box[3])) // 2))
                    for box, tid, cid in zip(boxes, track_ids, class_ids) if cid == 0
                ]
                grouped_track_ids, qualifying_clusters = self.check_group_clustering(person_points)
                cluster_size_by_track = {tid: len(cluster) for cluster in qualifying_clusters for tid in cluster}

                # 1. GROUP CONVERGENCE (REAL-TIME SNAPSHOT -> DATABASE)
                if qualifying_clusters:
                    current_time = time.time()
                    if (current_time - self.last_group_alert_time) > self.GROUP_ALERT_COOLDOWN:
                        self.last_group_alert_time = current_time
                        largest = max(qualifying_clusters, key=len)
                        group_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        group_file = f"{self.GROUP_LOG_DIR}/group_{group_ts}.jpg"

                        evidence = clean_snapshot.copy()
                        for box, tid, cid in zip(boxes, track_ids, class_ids):
                            if cid == 0 and int(tid) in largest:
                                gx1, gy1, gx2, gy2 = map(int, box)
                                cv2.rectangle(evidence, (gx1, gy1), (gx2, gy2), (255, 0, 255), 2)
                        cv2.imwrite(group_file, evidence)

                        group_ids_str = ",".join(str(t) for t in largest)
                        self.log_event("Group Convergence", "Person", group_ids_str, 0.95,
                                       details=f"{len(largest)} people converged", evidence_file=group_file)

                        # Save live evidence snapshot directly to PostgreSQL
                        self.save_watchtower_breach_to_db(
                            camera_id=camera_id,
                            entity_type="Group Convergence",
                            identifier=f"GROUP-{len(largest)}PPL",
                            confidence=0.95,
                            frame_bgr=evidence,
                            local_file_path=group_file
                        )

                        ws_alerts.append({
                            "id": f"INC-{int(current_time * 1000)}",
                            "title": f"GROUP CONVERGENCE ({len(largest)} PEOPLE)",
                            "cameraId": camera_id,
                            "confidence": "95.0%",
                            "time": datetime.now().strftime("%H:%M:%S IST"),
                            "siren": False
                        })

                # Process Each Object
                for box, track_id, cls_id, conf in zip(boxes, track_ids, class_ids, confs):
                    x1, y1, x2, y2 = map(int, box)
                    center_pt = ((x1 + x2) // 2, (y1 + y2) // 2)

                    if track_id not in self.seen_all_objects:
                        class_names = {0: "Person", 1: "Vehicle", 2: "Animal"}
                        self.log_event("Detected", class_names.get(cls_id, "Unknown"), track_id, conf)
                        self.seen_all_objects.add(track_id)

                    has_breached = self.check_breach(camera_id, track_id, center_pt)

                    # Class 0: PERSON (INTRUDER OR LOITERING)
                    if cls_id == 0:
                        is_loitering, duration = self.check_loitering(track_id, center_pt)
                        if has_breached:
                            box_color = (0, 0, 255)
                            label = f"ID:{track_id} INTRUDER ({conf:.2f})"
                            self.play_siren()

                            if track_id not in self.logged_intruders:
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                fn = f"{self.PERSON_LOG_DIR}/intruder_{track_id}_{ts}.jpg"
                                evidence = clean_snapshot.copy()
                                cv2.rectangle(evidence, (x1, y1), (x2, y2), (0, 0, 255), 2)
                                cv2.imwrite(fn, evidence)
                                self.log_event("Person Breach", "Person", track_id, conf, details="Crossed fence", evidence_file=fn)
                                self.logged_intruders.add(track_id)

                                # Save live intruder snapshot directly to PostgreSQL
                                self.save_watchtower_breach_to_db(
                                    camera_id=camera_id,
                                    entity_type="Person Breach",
                                    identifier=f"INTRUDER-#{track_id}",
                                    confidence=float(conf),
                                    frame_bgr=evidence,
                                    local_file_path=fn
                                )

                                ws_alerts.append({
                                    "id": f"INC-{int(time.time() * 1000)}",
                                    "title": f"CRITICAL: INTRUDER #{track_id} BREACH",
                                    "cameraId": camera_id,
                                    "confidence": f"{conf * 100:.1f}%",
                                    "time": datetime.now().strftime("%H:%M:%S IST"),
                                    "siren": True
                                })
                        elif track_id in grouped_track_ids:
                            box_color = (255, 0, 255)
                            label = f"ID:{track_id} GROUP ({cluster_size_by_track.get(track_id, 0)} PPL)"
                        elif is_loitering:
                            box_color = (0, 165, 255)
                            label = f"ID:{track_id} SUSPICIOUS ({duration:.0f}s)"
                            if track_id not in self.logged_loiterers:
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                fn = f"{self.LOITER_LOG_DIR}/loiter_{track_id}_{ts}.jpg"
                                evidence = clean_snapshot.copy()
                                cv2.rectangle(evidence, (x1, y1), (x2, y2), box_color, 2)
                                cv2.imwrite(fn, evidence)
                                self.log_event("Loitering", "Person", track_id, conf, details=f"Pacing {duration:.0f}s", evidence_file=fn)
                                self.logged_loiterers.add(track_id)

                                # Save live loitering snapshot directly to PostgreSQL
                                self.save_watchtower_breach_to_db(
                                    camera_id=camera_id,
                                    entity_type="Loitering",
                                    identifier=f"LOITERER-#{track_id}",
                                    confidence=float(conf),
                                    frame_bgr=evidence,
                                    local_file_path=fn
                                )

                                ws_alerts.append({
                                    "id": f"INC-{int(time.time() * 1000)}",
                                    "title": f"SUSPICIOUS LOITERING #{track_id}",
                                    "cameraId": camera_id,
                                    "confidence": f"{conf * 100:.1f}%",
                                    "time": datetime.now().strftime("%H:%M:%S IST"),
                                    "siren": False
                                })
                        else:
                            box_color = (255, 255, 0)
                            label = f"ID:{track_id} PERSON ({conf:.2f})"

                    # Class 1: VEHICLE BREACH
                    elif cls_id == 1:
                        if has_breached:
                            box_color = (0, 140, 255)
                            label = f"ID:{track_id} VEHICLE BREACH ({conf:.2f})"
                            self.play_siren()
                            if track_id not in self.logged_vehicles:
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                fn = f"{self.CAR_LOG_DIR}/vehicle_{track_id}_{ts}.jpg"
                                evidence = clean_snapshot.copy()
                                cv2.rectangle(evidence, (x1, y1), (x2, y2), (0, 140, 255), 2)
                                cv2.imwrite(fn, evidence)
                                self.log_event("Vehicle Breach", "Vehicle", track_id, conf, details="Crossed boundary", evidence_file=fn)
                                self.logged_vehicles.add(track_id)

                                # Save live vehicle breach snapshot directly to PostgreSQL
                                self.save_watchtower_breach_to_db(
                                    camera_id=camera_id,
                                    entity_type="Vehicle Breach",
                                    identifier=f"VEHICLE-#{track_id}",
                                    confidence=float(conf),
                                    frame_bgr=evidence,
                                    local_file_path=fn
                                )

                                ws_alerts.append({
                                    "id": f"INC-{int(time.time() * 1000)}",
                                    "title": f"VEHICLE BREACH #{track_id}",
                                    "cameraId": camera_id,
                                    "confidence": f"{conf * 100:.1f}%",
                                    "time": datetime.now().strftime("%H:%M:%S IST"),
                                    "siren": True
                                })
                        else:
                            box_color = (255, 150, 0)
                            label = f"ID:{track_id} VEHICLE ({conf:.2f})"

                    # Class 2: ANIMAL
                    else:
                        box_color = (0, 255, 0)
                        label = f"ID:{track_id} ANIMAL (FILTERED)"

                    cv2.rectangle(processed_frame, (x1, y1), (x2, y2), box_color, 2)
                    cv2.circle(processed_frame, center_pt, 4, box_color, -1)
                    cv2.putText(processed_frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 2)

                    trail = self.trajectory_history[track_id]
                    for i in range(1, len(trail)):
                        cv2.line(processed_frame, trail[i - 1], trail[i], box_color, 1)

            # HUD Banner
            cv2.rectangle(processed_frame, (0, 0), (w, 32), (20, 20, 20), -1)
            mode_str = f"NIGHT VISION: {'AUTO (ON)' if self.NIGHT_MODE_ENABLED and self.AUTO_NIGHT_MODE else 'AUTO (OFF)' if self.AUTO_NIGHT_MODE else 'MANUAL ON' if self.NIGHT_MODE_ENABLED else 'MANUAL OFF'}"
            cv2.putText(processed_frame, f"GARUDA WATCHTOWER | {mode_str}", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(processed_frame, "[N] Emergency Toggle", (w - 220, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

            return processed_frame, ws_alerts

        except Exception as e:
            print(f"❌ Error in process_watchtower_frame: {e}")
            return raw_frame, []

    # -----------------------------------------------------------------
    # ANPR REAL-TIME PROCESSING (NO DATABASE IMAGES - LOGS ONLY)
    # -----------------------------------------------------------------
    def clean_plate(self, text):
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9]', '', text)
        text = re.sub(r'^(?:IND|IN|I)', '', text)
        return text

    def is_same_plate(self, a, b):
        return a == b

    def merge_plate_reads(self, reads):
        best_by_text = {}
        order = []
        for frame_num, ts, text, conf in reads:
            if len(text) <= self.MIN_PLATE_LENGTH:
                continue
            if text not in best_by_text:
                best_by_text[text] = (frame_num, ts, text, conf)
                order.append(text)
            else:
                _, _, _, best_conf = best_by_text[text]
                if conf > best_conf:
                    best_by_text[text] = (frame_num, ts, text, conf)
        return [(best_by_text[t][0], best_by_text[t][1], best_by_text[t][2]) for t in order]

    def export_final_anpr_summary(self):
        if not self.anpr_all_reads:
            return
        merged = self.merge_plate_reads(self.anpr_all_reads)
        with open(self.ANPR_DETECTION_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame", "timestamp_sec", "plate_text"])
            for frame_num, ts, text in merged:
                writer.writerow([frame_num, f"{ts:.2f}", text])

    def is_valid_alphanumeric_plate(self, text):
        if len(text) <= self.MIN_PLATE_LENGTH:
            return False
        has_letter = any(c.isalpha() for c in text)
        has_digit = any(c.isdigit() for c in text)
        return bool(has_letter and has_digit)

    def draw_overlay(self, frame, box, display_str):
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, display_str, (x1, max(30, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    def process_anpr_frame(self, frame, camera_id="CAM-01"):
        try:
            h, w = frame.shape[:2]
            ws_alerts = []
            self.anpr_frame_count += 1
            fps = 30.0

            if self.anpr_frame_count % self.FRAME_SKIP != 0:
                if self.anpr_last_box is not None:
                    self.draw_overlay(frame, self.anpr_last_box, self.anpr_last_display_str)
                cv2.rectangle(frame, (0, 0), (w, 32), (20, 20, 20), -1)
                cv2.putText(frame, "GARUDA ANPR CHECKPOST SYSTEM | ACTIVE", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                return frame, []

            results = self.anpr_model(frame, conf=self.DETECTION_CONF_THRESHOLD, verbose=False)[0]
            boxes = results.boxes

            if boxes is not None and len(boxes) > 0:
                best_idx = int(boxes.conf.argmax())
                best_box = boxes[best_idx]
                x1, y1, x2, y2 = map(int, best_box.xyxy[0])
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                plate_crop = frame[y1:y2, x1:x2]
                plate_text = None
                ocr_confidence = 0.0
                display_str = "Plate Detected"

                if self.reader and plate_crop.size > 0:
                    if plate_crop.shape[1] < 200 and plate_crop.shape[1] > 0:
                        scale = 200 / plate_crop.shape[1]
                        plate_crop = cv2.resize(plate_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                    gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)

                    ocr_res = self.reader.readtext(gray)
                    if ocr_res and ocr_res[0][2] >= self.OCR_CONF_THRESHOLD:
                        raw_text = ocr_res[0][1]
                        ocr_confidence = float(ocr_res[0][2])
                        cleaned = self.clean_plate(raw_text)

                        if self.is_valid_alphanumeric_plate(cleaned):
                            plate_text = cleaned
                            display_str = f"{plate_text} ({ocr_confidence:.2f})"

                self.anpr_last_box = (x1, y1, x2, y2)
                self.anpr_last_display_str = display_str
                self.draw_overlay(frame, self.anpr_last_box, self.anpr_last_display_str)

                if plate_text:
                    timestamp_sec = self.anpr_frame_count / fps
                    self.anpr_all_reads.append((self.anpr_frame_count, timestamp_sec, plate_text, ocr_confidence))

                    now = time.time()
                    last_logged_time, last_best_conf = self.anpr_seen_cooldown.get(plate_text, (0, 0.0))

                    if (now - last_logged_time > 5.0) or (ocr_confidence > last_best_conf + 0.15):
                        self.anpr_seen_cooldown[plate_text] = (now, ocr_confidence)
                        self.log_event("ANPR Detection", "Vehicle Plate", plate_text, ocr_confidence, details=f"Cleaned Read: {plate_text}")
                        self.export_final_anpr_summary()

                        # Emits only UI telemetry entry — NO database photo insertion
                        ws_alerts.append({
                            "id": f"INC-{int(now * 1000)}",
                            "title": f"LICENSE PLATE: {plate_text}",
                            "cameraId": camera_id,
                            "confidence": f"{ocr_confidence * 100:.1f}%",
                            "time": datetime.now().strftime("%H:%M:%S IST"),
                            "siren": False,
                            "silent": True
                        })
                        print(f"🚗 [ANPR BEST-READ LOGGED]: {plate_text} (Conf: {ocr_confidence:.2f})")

            else:
                self.anpr_last_box = None
                self.anpr_last_display_str = None

            cv2.rectangle(frame, (0, 0), (w, 32), (20, 20, 20), -1)
            cv2.putText(frame, "GARUDA ANPR CHECKPOST SYSTEM | ACTIVE", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            return frame, ws_alerts

        except Exception as e:
            print(f"❌ Error in process_anpr_frame: {e}")
            return frame, []

ai_service = GarudaIntegratedAIEngine()