"""
==============================================================================
GARUDA: REAL-TIME AI SURVEILLANCE & THREAT DETECTION ENGINE
Features:
  1. High-Yield Raw Video ANPR (CLAHE Preprocessing, Multi-Plate Detection)
  2. Frame Skipping (FRAME_SKIP = 3) with Multi-Box Caching
  3. Strict State Code Resolution & OCR Disambiguation (DL, MH, KA, HR, UP, BH, etc.)
  4. Positional Digit/Letter Correction (O<->0, I<->1, S<->5, Z<->2, B<->8)
  5. Zero-Garbage Two-Tier Grammar:
     - Tier 1: Full Indian Plates (State + RTO + Series + 4 Digits)
     - Tier 2: Valid Head/Tail Partials (e.g. DL01A** or **AB1234)
  6. WatchTower Threat Detection (Intruder, Vehicle Breach, Loiter, Group)
  7. Real-Time PostgreSQL Evidence Snapshots (Base64)
  8. Rolling CSV Retention (Max 2,000 entries -> trims oldest 1,000)
  9. Emergency Night Vision Override (CLAHE) & Audio Siren System
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
    def __init__(self, base_dir="/Users/khush07/Nexus-GARUDA/Nexus-GARUDA"):
        self.base_dir = base_dir

        # -------------------------------------------------------------
        # 1. DIRECTORY PATHS & LOG SETUP
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
            with open(self.ALL_OBJECTS_CSV_LOG, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["timestamp", "event_type", "object_type", "track_id", "confidence", "details", "evidence_file"])

        if not os.path.exists(self.ANPR_DETECTION_CSV):
            with open(self.ANPR_DETECTION_CSV, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["frame", "timestamp_sec", "plate_text"])

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
            # self.anpr_model = YOLO("yolov8n.pt")
            print("Cannot load state of art model :)")

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

        # Raw Video ANPR Settings (Track-Independent)
        self.FRAME_SKIP = 4
        self.MIN_PLATE_LENGTH = 4
        self.DETECTION_CONF_THRESHOLD = 0.25
        self.OCR_CONF_THRESHOLD = 0.25
        self.anpr_frame_count = 0
        self.anpr_last_boxes = []
        self.anpr_all_reads = []
        self.anpr_seen_cooldown = {}

        self.tripwire_lines = {
            "CAM-02": LineString([(0, 650), (1920, 650)]),
            "CAM-03": LineString([(350, 0), (350, 1080)]),
            "CAM-04": LineString([(0, 0), (0, 0)]),
        }

        # Master lookup of valid Indian State / UT / National Codes
        self.VALID_STATE_PREFIXES = {
            'AN', 'AP', 'AR', 'AS', 'BR', 'CG', 'CH', 'DD', 'DN', 'DL', 'DN', 'GA', 'GJ', 
            'HR', 'HP', 'JH', 'JK', 'KA', 'KL', 'LA', 'LD', 'MH', 'ML', 'MN', 'MP', 
            'MZ', 'NL', 'OD', 'OR', 'PB', 'PY', 'RJ', 'SK', 'TN', 'TR', 'TS', 'UK', 
            'UA', 'UP', 'WB', 'BH'
        }

        # Frequent OCR Confusion Map for First 2 State Code Letters
        self.STATE_OCR_CORRECTIONS = {
            '0L': 'DL', 'QL': 'DL', 'OL': 'DL', 'DI': 'DL',
            'NH': 'MH', '0H': 'MH', 'MI': 'MH',
            'K4': 'KA', 'K8': 'KA', 'KR': 'KA',
            '8H': 'BH', '8R': 'BR', '8B': 'PB',
            'H8': 'HR', 'H4': 'HR',
            'U8': 'UP', '0P': 'UP', '0K': 'UK',
            '1N': 'TN', 'TI': 'TN', 'TM': 'TN',
            'W8': 'WB', 'V8': 'WB',
            'G1': 'GJ', 'G0': 'GJ',
            'R1': 'RJ', 'R0': 'RJ',
            'C6': 'CG', 'C0': 'CH',
            'A5': 'AS', 'A1': 'AP', 'T5': 'TS',
        }

        # Positional mappings for letter/digit ambiguity
        self.CHAR_TO_DIGIT = {'O': '0', 'D': '0', 'Q': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '6'}
        self.CHAR_TO_LETTER = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '6': 'G'}

        # Common roadside noise words to reject immediately
        self.GARBAGE_WORDS = {
            'CARRIER', 'STOP', 'POLICE', 'ARMY', 'NAVY', 'INDIA', 'HSRP', 'DIESEL',
            'PETROL', 'CNG', 'SPEED', 'LIMIT', 'HIGHWAY', 'TOLL', 'TRUCK', 'CAB',
            'TAXI', 'AUTO', 'GOODS', 'PUBLIC', 'PRIVATE', 'PRESS', 'GOVT'
        }

    # -----------------------------------------------------------------
    # ROLLING CSV LOG RETENTION (MAX 2,000 ROWS -> PURGE OLDEST 1,000)
    # -----------------------------------------------------------------
    def _trim_csv_if_needed(self, file_path, header, max_rows=2000, keep_rows=1000):
        """
        Maintains CSV files at a maximum of 2,000 entries.
        When 2,000 entries are reached, the oldest 1,000 entries are purged,
        retaining the clean CSV header and the latest 1,000 entries.
        """
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            
            if len(rows) > max_rows:
                trimmed = [header] + rows[-keep_rows:]
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(trimmed)
                print(f"🧹 [CSV ROTATION] Trimmed {os.path.basename(file_path)}: Retained latest {keep_rows} rows.")
        except Exception as e:
            print(f"⚠️ Error trimming {file_path}: {e}")

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
        """Logs raw tracking and surveillance events with auto-rotation at 2,000 rows."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.ALL_OBJECTS_CSV_LOG, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([timestamp, event_type, object_type, track_id, f"{confidence:.2f}", details, evidence_file])

        self._trim_csv_if_needed(
            self.ALL_OBJECTS_CSV_LOG,
            header=["timestamp", "event_type", "object_type", "track_id", "confidence", "details", "evidence_file"],
            max_rows=2000,
            keep_rows=1000
        )

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
    # ENHANCED RAW VIDEO ANPR ENGINE (STATE RESOLUTION + DISAMBIGUATION)
    # -----------------------------------------------------------------
    def resolve_state_code(self, raw_prefix):
        """
        Validates and auto-corrects the 2-letter State Prefix.
        Returns: (is_valid: bool, corrected_prefix: str)
        """
        raw_prefix = raw_prefix.upper()
        
        # 1. Direct valid match
        if raw_prefix in self.VALID_STATE_PREFIXES:
            return True, raw_prefix
            
        # 2. Known OCR substitution map
        if raw_prefix in self.STATE_OCR_CORRECTIONS:
            return True, self.STATE_OCR_CORRECTIONS[raw_prefix]
            
        # 3. Positional Fallback check (if 1 character was slightly skewed)
        for valid in self.VALID_STATE_PREFIXES:
            if (raw_prefix[0] == valid[0] and raw_prefix[1] in {'0', '1', '8', 'I', 'O', 'B'}) or \
               (raw_prefix[1] == valid[1] and raw_prefix[0] in {'0', '1', '8', 'I', 'O', 'B'}):
                return True, valid
                
        return False, raw_prefix

    def correct_positional_ocr(self, text):
        """
        Applies positional OCR character correction to resolve letter/digit confusions:
        - Positions 0 & 1: State Letters (e.g. '0L' -> 'DL', '1N' -> 'TN', '8H' -> 'BH')
        - Positions 2 & 3: RTO Digits (e.g. 'O1' -> '01', 'I2' -> '12')
        - Last 4 characters: Digits (e.g. 'AB123O' -> 'AB1230', '4S21' -> '4521')
        """
        if len(text) < 4:
            return text

        chars = list(text)

        # 1. State Code Correction (First 2 chars)
        prefix = "".join(chars[:2])
        is_valid_state, resolved_prefix = self.resolve_state_code(prefix)
        if is_valid_state:
            chars[0], chars[1] = resolved_prefix[0], resolved_prefix[1]
        else:
            for i in [0, 1]:
                if chars[i].isdigit() and chars[i] in self.CHAR_TO_LETTER:
                    chars[i] = self.CHAR_TO_LETTER[chars[i]]

        # 2. RTO Number Correction (Positions 2 & 3 must be digits)
        if len(chars) >= 6:
            for i in [2, 3]:
                if chars[i].isalpha() and chars[i] in self.CHAR_TO_DIGIT:
                    chars[i] = self.CHAR_TO_DIGIT[chars[i]]

        # 3. Tail Digits Correction (Last 4 characters must be digits for full plates)
        if len(chars) >= 8:
            tail_start = len(chars) - 4
            for i in range(tail_start, len(chars)):
                if chars[i].isalpha() and chars[i] in self.CHAR_TO_DIGIT:
                    chars[i] = self.CHAR_TO_DIGIT[chars[i]]

        return "".join(chars)

    def clean_plate(self, text):
        """Standardizes characters, strips watermarks, and fixes OCR confusions."""
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9]', '', text)
        text = re.sub(r'^(?:IND|IN|I)', '', text)  # Strip standard HSRP watermark
        
        # Apply intelligent positional correction
        corrected = self.correct_positional_ocr(text)
        return corrected

    def is_same_plate(self, a, b):
        return a == b

    def merge_plate_reads(self, reads):
        best_by_text = {}
        order = []
        for frame_num, ts, text, conf in reads:
            if len(text) < self.MIN_PLATE_LENGTH:
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
        """Appends and trims ANPR detections to detection.csv."""
        if not self.anpr_all_reads:
            return
        merged = self.merge_plate_reads(self.anpr_all_reads)
        
        file_exists = os.path.exists(self.ANPR_DETECTION_CSV)
        with open(self.ANPR_DETECTION_CSV, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists or os.path.getsize(self.ANPR_DETECTION_CSV) == 0:
                writer.writerow(["frame", "timestamp_sec", "plate_text"])
            for frame_num, ts, text in merged:
                writer.writerow([frame_num, f"{ts:.2f}", text])

        self._trim_csv_if_needed(
            self.ANPR_DETECTION_CSV,
            header=["frame", "timestamp_sec", "plate_text"],
            max_rows=2000,
            keep_rows=1000
        )

    def classify_plate_candidate(self, text, conf):
        """
        High-Precision Two-Tier Plate Grammar Validator:
        - Tier 1: Strict Full Plate (Valid State + RTO Digits + Series + 4 Digits)
        - Tier 2: Guarded Partial Plate (Only valid Head-Partials or Tail-Partials)
        """
        cleaned = self.clean_plate(text)
        
        # 1. Length sanity check (Standard Indian plates are 5 to 10 chars)
        if len(cleaned) < 5 or len(cleaned) > 10:
            return False, False, cleaned

        # 2. Reject common roadside noise words
        for bad_word in self.GARBAGE_WORDS:
            if bad_word in cleaned:
                return False, False, cleaned

        # 3. Reject repetitive pattern clones (e.g. 'AAAAAA', '111111', 'ABABAB')
        if len(set(cleaned)) < 4:
            return False, False, cleaned

        letter_count = sum(1 for c in cleaned if c.isalpha())
        digit_count = sum(1 for c in cleaned if c.isdigit())
        
        # Must have at least 1 letter and at least 1 digit
        if letter_count < 1 or digit_count < 1:
            return False, False, cleaned

        state_prefix = cleaned[:2]
        is_valid_state, resolved_state = self.resolve_state_code(state_prefix)

        # -------------------------------------------------------------
        # TIER 1: STRICT FULL PLATE (Length 8 to 10)
        # e.g., DL01AB1234, MH12DE1433, KA05S8425, BH22AA1234
        # -------------------------------------------------------------
        if len(cleaned) >= 8 and is_valid_state:
            # Pattern: 2 State Letters + 1-2 RTO Digits + 0-3 Series Letters + 3-4 Digits
            full_regex = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}$'
            full_candidate = resolved_state + cleaned[2:]
            if re.match(full_regex, full_candidate) and full_candidate[2:4].isdigit():
                return True, True, full_candidate

        # -------------------------------------------------------------
        # TIER 2: GUARDED PARTIAL PLATE (Length 5 to 7)
        # Zero-Garbage Checks: Must be either a Head-Partial or Tail-Partial
        # -------------------------------------------------------------
        if 5 <= len(cleaned) <= 7:
            # Case A: Head-Partial (Starts with Valid State + RTO Digit)
            # e.g., DL01A, MH12DE, KA05S
            if is_valid_state and cleaned[2].isdigit():
                head_candidate = resolved_state + cleaned[2:]
                return True, False, f"{head_candidate}** [PARTIAL]"

            # Case B: Tail-Partial (1-2 Series Letters + 3-4 Registration Digits)
            # e.g., AB1234, DE1433, S8425
            tail_regex = r'^[A-Z]{1,2}[0-9]{3,4}$'
            if re.match(tail_regex, cleaned):
                return True, False, f"**{cleaned} [PARTIAL]"

        return False, False, cleaned

    def preprocess_plate_for_ocr(self, crop):
        """Enhancement: Upscaling + CLAHE Contrast boost + Bilateral smoothing."""
        if crop.size == 0:
            return crop
        h, w = crop.shape[:2]
        if w < 240:
            scale = 240 / max(1, w)
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)
        return filtered

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
            now = time.time()

            # -------------------------------------------------------------
            # FRAME SKIPPING (FRAME_SKIP = 3) WITH BOUNDING BOX CACHE
            # -------------------------------------------------------------
            if self.anpr_frame_count % self.FRAME_SKIP != 0:
                for cached_box, cached_str in self.anpr_last_boxes:
                    self.draw_overlay(frame, cached_box, cached_str)
                cv2.rectangle(frame, (0, 0), (w, 32), (20, 20, 20), -1)
                cv2.putText(frame, "GARUDA ANPR CHECKPOST SYSTEM | ACTIVE", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                return frame, []

            # 1. High Sensitivity Detection Threshold (0.25)
            results = self.anpr_model(frame, conf=self.DETECTION_CONF_THRESHOLD, verbose=False)[0]
            boxes = results.boxes

            current_boxes = []

            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)

                    plate_crop = frame[y1:y2, x1:x2]
                    plate_text = None
                    ocr_confidence = 0.0
                    display_str = "Scanning Plate..."

                    if self.reader and plate_crop.size > 0:
                        processed_crop = self.preprocess_plate_for_ocr(plate_crop)
                        ocr_res = self.reader.readtext(
                            processed_crop, 
                            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                            paragraph=False
                        )
                        
                        if ocr_res and len(ocr_res) > 0:
                            raw_text = "".join([res[1] for res in ocr_res])
                            ocr_confidence = float(max([res[2] for res in ocr_res]))

                            if ocr_confidence >= self.OCR_CONF_THRESHOLD:
                                is_valid, is_full, formatted_text = self.classify_plate_candidate(raw_text, ocr_confidence)
                                if is_valid:
                                    plate_text = formatted_text
                                    display_str = f"{plate_text} ({ocr_confidence:.2f})"

                    current_boxes.append(((x1, y1, x2, y2), display_str))
                    self.draw_overlay(frame, (x1, y1, x2, y2), display_str)

                    # Cooldown-gated logging based on plate text (not track ID)
                    if plate_text:
                        timestamp_sec = self.anpr_frame_count / fps
                        last_logged_time, last_best_conf = self.anpr_seen_cooldown.get(plate_text, (0, 0.0))

                        # Log once per car / plate, or when a higher confidence read occurs
                        if (now - last_logged_time > 4.5) or (ocr_confidence > last_best_conf + 0.15):
                            self.anpr_seen_cooldown[plate_text] = (now, ocr_confidence)
                            self.anpr_all_reads.append((self.anpr_frame_count, timestamp_sec, plate_text, ocr_confidence))
                            
                            self.log_event("ANPR Detection", "Vehicle Plate", plate_text, ocr_confidence, details=f"Read: {plate_text}")
                            self.export_final_anpr_summary()

                            ws_alerts.append({
                                "id": f"INC-{int(now * 1000)}",
                                "title": f"LICENSE PLATE: {plate_text}",
                                "cameraId": camera_id,
                                "confidence": f"{ocr_confidence * 100:.1f}%",
                                "time": datetime.now().strftime("%H:%M:%S IST"),
                                "siren": False,
                                "silent": True
                            })
                            print(f"🚗 [ANPR READ LOGGED]: {plate_text} (Conf: {ocr_confidence:.2f})")

                self.anpr_last_boxes = current_boxes
            else:
                self.anpr_last_boxes = []

            cv2.rectangle(frame, (0, 0), (w, 32), (20, 20, 20), -1)
            cv2.putText(frame, "GARUDA ANPR CHECKPOST SYSTEM | ACTIVE", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            return frame, ws_alerts

        except Exception as e:
            print(f"❌ Error in process_anpr_frame: {e}")
            return frame, []

ai_service = GarudaIntegratedAIEngine()