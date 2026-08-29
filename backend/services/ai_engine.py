"""
==============================================================================
GARUDA: INTEGRATED AI SURVEILLANCE & THREAT DETECTION ENGINE
Combines:
  1. WatchTower YOLO11s Threat Analytics (Intrusions, Loitering, Group Clusters)
  2. Automatic CLAHE Night Vision Enhancement + Emergency 'N' Hotkey Override
  3. Audio Siren & Evidence Snapshot Logging (with Instant Silence Control)
  4. Checkpost ANPR (Strict len > 4 + Alphanumeric Filter + clean_plate)
==============================================================================
"""

import os
import re
import cv2
import csv
import math
import time
import torch
import pygame
import numpy as np
from datetime import datetime
from collections import defaultdict
from shapely.geometry import LineString
from ultralytics import YOLO

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class GarudaIntegratedAIEngine:
    def __init__(self, base_dir="/Users/ak_junior/Desktop/Nexus-Garuda"):
        self.base_dir = base_dir

        # -------------------------------------------------------------
        # 1. DIRECTORY & PATH DEFINITIONS
        # -------------------------------------------------------------
        self.WT_MODEL_PATH = os.path.join(base_dir, "WatchTower surveillance", "WTbest.pt")
        self.ANPR_MODEL_PATH = os.path.join(base_dir, "ANPR", "Model", "anprbest.pt")
        self.ALARM_PATH = os.path.join(base_dir, "WatchTower surveillance", "Alert", "alarm.wav")

        self.LOG_DIR = os.path.join(base_dir, "WatchTower surveillance", "Logs")
        self.BREACH_LOG_DIR = os.path.join(base_dir, "WatchTower surveillance", "breach_logs")
        self.PERSON_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "person")
        self.CAR_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "car")
        self.LOITER_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "loitering")
        self.GROUP_LOG_DIR = os.path.join(self.BREACH_LOG_DIR, "group_clustering")

        for d in [self.LOG_DIR, self.BREACH_LOG_DIR, self.PERSON_LOG_DIR, self.CAR_LOG_DIR, self.LOITER_LOG_DIR, self.GROUP_LOG_DIR]:
            os.makedirs(d, exist_ok=True)

        self.ALL_OBJECTS_CSV_LOG = os.path.join(self.LOG_DIR, "surveillance_log.csv")
        if not os.path.exists(self.ALL_OBJECTS_CSV_LOG):
            with open(self.ALL_OBJECTS_CSV_LOG, "w", newline="") as f:
                csv.writer(f).writerow(["timestamp", "event_type", "object_type", "track_id", "confidence", "details", "evidence_file"])

        # -------------------------------------------------------------
        # 2. AUDIO SIREN INITIALIZATION
        # -------------------------------------------------------------
        pygame.mixer.init()
        try:
            self.alarm_sound = pygame.mixer.Sound(self.ALARM_PATH)
            print(f"✅ Audio siren initialized from: {self.ALARM_PATH}")
        except Exception as e:
            print(f"⚠️ Audio alarm file issue ({e}). Using system audio fallback.")
            self.alarm_sound = None

        self.last_alarm_time = 0
        self.ALARM_COOLDOWN = 3.0

        # -------------------------------------------------------------
        # 3. LOAD YOLO MODELS
        # -------------------------------------------------------------
        print("🚀 Loading WatchTower & ANPR YOLO models...")
        try:
            self.wt_model = YOLO(self.WT_MODEL_PATH)
            print(f"✅ WatchTower weights loaded: {self.WT_MODEL_PATH}")
        except Exception as e:
            print(f"⚠️ WTbest.pt not found ({e}), falling back to yolo11s.pt")
            self.wt_model = YOLO("yolo11s.pt")

        try:
            self.anpr_model = YOLO(self.ANPR_MODEL_PATH)
            print(f"✅ ANPR weights loaded: {self.ANPR_MODEL_PATH}")
        except Exception as e:
            print(f"⚠️ anprbest.pt not found ({e}), falling back to yolov8n.pt")
            self.anpr_model = YOLO("yolov8n.pt")

        # -------------------------------------------------------------
        # 4. ROBUST EASYOCR INITIALIZATION
        # -------------------------------------------------------------
        self.reader = None
        if EASYOCR_AVAILABLE:
            try:
                use_gpu = torch.cuda.is_available()
                self.reader = easyocr.Reader(['en'], gpu=use_gpu)
                print(f"✅ EasyOCR initialized on {'GPU' if use_gpu else 'CPU'}")
            except Exception as e:
                print(f"⚠️ GPU init failed, trying CPU fallback: {e}")
                try:
                    self.reader = easyocr.Reader(['en'], gpu=False)
                    print("✅ EasyOCR initialized on CPU")
                except Exception as e2:
                    print(f"❌ EasyOCR failed to load: {e2}")

        # -------------------------------------------------------------
        # 5. WATCHTOWER & ANPR THREAT STATE
        # -------------------------------------------------------------
        self.trajectory_history = defaultdict(list)
        self.anchor_points = {}
        self.seen_all_objects = set()
        self.logged_intruders = set()
        self.logged_vehicles = set()
        self.logged_loiterers = set()
        self.anpr_seen_cooldown = {} # Plate -> (timestamp, best_conf)

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

        # Configurable tripwires (per camera)
        self.tripwire_lines = {
            "CAM-02": LineString([(0, 650), (1920, 650)]),
            "CAM-03": LineString([(350, 0), (350, 1080)]),
            "CAM-04": LineString([(0, 650), (1920, 650)]),
        }

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
        """Immediately silences any playing alarm audio."""
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
            os.system("pkill -9 afplay 2>/dev/null")
        except Exception as e:
            print(f"Error stopping siren: {e}")

    # -----------------------------------------------------------------
    # NIGHT VISION (AUTOMATIC SENSOR + EMERGENCY MANUAL OVERRIDE)
    # -----------------------------------------------------------------
    def apply_night_vision_enhancement(self, frame):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l_channel)
        enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    def emergency_toggle_night_vision(self):
        """Disables AUTO mode and toggles manual state (Force ON / Force OFF)."""
        self.AUTO_NIGHT_MODE = False
        self.NIGHT_MODE_ENABLED = not self.NIGHT_MODE_ENABLED
        status = "MANUAL ON" if self.NIGHT_MODE_ENABLED else "MANUAL OFF"
        print(f"🚨 [EMERGENCY OVERRIDE] Night Vision set to {status}")
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
        grouped_ids = {tid for cluster in qualifying for tid in cluster}
        return grouped_ids, qualifying

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
    # MAIN WATCHTOWER PROCESSING FUNCTION (CAM-02, CAM-03, CAM-04)
    # -----------------------------------------------------------------
    def process_watchtower_frame(self, raw_frame, camera_id="CAM-02"):
        try:
            self.frame_index += 1
            h, w, _ = raw_frame.shape
            ws_alerts = []

            # 1. Automatic CLAHE Brightness Sensing
            if self.AUTO_NIGHT_MODE:
                avg_brightness = np.mean(cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY))
                self.NIGHT_MODE_ENABLED = bool(avg_brightness < 60)

            # 2. Enhance Frame
            processed_frame = self.apply_night_vision_enhancement(raw_frame) if self.NIGHT_MODE_ENABLED else raw_frame.copy()
            clean_snapshot = processed_frame.copy()

            # Draw Tripwire Line
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

                # Group Clustering Pre-pass
                person_points = [
                    (int(tid), ((int(box[0]) + int(box[2])) // 2, (int(box[1]) + int(box[3])) // 2))
                    for box, tid, cid in zip(boxes, track_ids, class_ids) if cid == 0
                ]
                grouped_track_ids, qualifying_clusters = self.check_group_clustering(person_points)
                cluster_size_by_track = {tid: len(cluster) for cluster in qualifying_clusters for tid in cluster}

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

                        self.log_event("Group Convergence", "Person", ",".join(str(t) for t in largest), 0.0,
                                       details=f"{len(largest)} people converged", evidence_file=group_file)

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

                    # Class 0: PERSON
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

                    # Class 1: VEHICLE
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
    # MAIN ANPR PROCESSING (STRICT LEN > 4 + ALPHANUMERIC FILTER)
    # -----------------------------------------------------------------
    def clean_plate(self, text):
        """
        Normalize raw OCR output into a plate-like string.
        - Uppercase everything.
        - Strip out ANY character that is not A-Z or 0-9.
        - Remove a leading 'IND' / 'IN' / 'I' watermark.
        """
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9]', '', text)
        text = re.sub(r'^(?:IND|IN|I)', '', text)
        return text

    def is_valid_alphanumeric_plate(self, text):
        """
        Alphanumeric Filter:
        1. Length MUST be strictly greater than 4 characters (len > 4).
        2. MUST contain at least one letter (A-Z) AND at least one digit (0-9).
        3. Rejects pure words or pure numbers.
        """
        if len(text) <= 4:
            return False

        has_letter = any(c.isalpha() for c in text)
        has_digit = any(c.isdigit() for c in text)
        if not (has_letter and has_digit):
            return False

        return True

    def process_anpr_frame(self, frame, camera_id="CAM-01"):
        try:
            h, w = frame.shape[:2]
            ws_alerts = []
            
            # Detection threshold 0.40
            results = self.anpr_model(frame, conf=0.40, verbose=False)[0]

            if results.boxes is not None and len(results.boxes) > 0:
                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    det_conf = float(box.conf[0].item())

                    plate_crop = frame[y1:y2, x1:x2]
                    plate_text = ""
                    best_ocr_conf = 0.0

                    if self.reader and plate_crop.size > 0:
                        if plate_crop.shape[1] < 200 and plate_crop.shape[1] > 0:
                            scale = 200 / plate_crop.shape[1]
                            plate_crop = cv2.resize(plate_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)

                        ocr_res = self.reader.readtext(gray)
                        for (_, raw_text, ocr_conf) in ocr_res:
                            # Acceptance threshold >= 0.40
                            if ocr_conf >= 0.40:
                                cleaned = self.clean_plate(raw_text)

                                # Alphanumeric gate (strictly len > 4 AND digits + letters)
                                if self.is_valid_alphanumeric_plate(cleaned):
                                    plate_text = cleaned
                                    best_ocr_conf = ocr_conf
                                    break

                    if plate_text:
                        display_label = f"PLATE: {plate_text} ({best_ocr_conf * 100:.0f}%)"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, display_label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

                        now = time.time()
                        last_logged_time, last_best_conf = self.anpr_seen_cooldown.get(plate_text, (0, 0.0))

                        # Log if new plate, higher confidence, or after 5s video loop
                        if (now - last_logged_time > 5.0) or (best_ocr_conf > last_best_conf + 0.15):
                            self.anpr_seen_cooldown[plate_text] = (now, best_ocr_conf)
                            self.log_event("ANPR Detection", "Vehicle Plate", plate_text, best_ocr_conf, details=f"Cleaned Read: {plate_text}")
                            
                            ws_alerts.append({
                                "id": f"INC-{int(now * 1000)}",
                                "title": f"LICENSE PLATE: {plate_text}",
                                "cameraId": camera_id,
                                "confidence": f"{best_ocr_conf * 100:.1f}%",
                                "time": datetime.now().strftime("%H:%M:%S IST"),
                                "siren": False,
                                "silent": True
                            })
                            print(f"🚗 [ANPR STRICT ALPHANUMERIC LOGGED]: {plate_text} (Conf: {best_ocr_conf:.2f})")
                    else:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 1)

            cv2.rectangle(frame, (0, 0), (w, 32), (20, 20, 20), -1)
            cv2.putText(frame, "GARUDA ANPR CHECKPOST SYSTEM | ACTIVE", (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            return frame, ws_alerts
        except Exception as e:
            print(f"❌ Error in process_anpr_frame: {e}")
            return frame, []

ai_service = GarudaIntegratedAIEngine()