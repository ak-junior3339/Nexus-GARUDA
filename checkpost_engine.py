"""
==============================================================================
GARUDA: LIVE SURVEILLANCE & THREAT DETECTION ENGINE
==============================================================================
"""

import cv2
import numpy as np
from shapely.geometry import LineString, Point
from ultralytics import YOLO
from collections import defaultdict
import os 
from datetime import datetime
import time
import pygame
import math


# ==============================================================================
#  CONFIGURATING THE SYSTEM FIRST
# ==============================================================================
MODEL_PATH = "best.pt" 
VIDEO_SOURCE = "test-input/15396218_1920_1080_25fps.mp4"                            
NIGHT_MODE_ENABLED = False        
AUTO_NIGHT_MODE = True


LOG_DIR = "breach_logs"
PERSON_LOG_DIR = os.path.join(LOG_DIR, "person")
CAR_LOG_DIR = os.path.join(LOG_DIR, "car")
LOITER_LOG_DIR = os.path.join(LOG_DIR, "loitering")


os.makedirs(LOG_DIR, exist_ok=True)   
os.makedirs(PERSON_LOG_DIR, exist_ok=True)
os.makedirs(CAR_LOG_DIR, exist_ok=True)
os.makedirs(LOITER_LOG_DIR, exist_ok=True)

ALL_OBJECTS_TXT_LOG = os.path.join(LOG_DIR, "all_objects_detected.txt")
if not os.path.exists(ALL_OBJECTS_TXT_LOG):
    with open(ALL_OBJECTS_TXT_LOG, "w") as f:
        f.write("Timestamp, Object_Type, Track_ID, Confidence\n") # Header row

ALARM_PATH = os.path.join("Alert", "alarm.wav")
pygame.mixer.init()
try:
    ALARM_SOUND = pygame.mixer.Sound(ALARM_PATH)
except:
    print(f"Warning: '{ALARM_PATH}' not found! Audio alarm will be muted.")
    ALARM_SOUND = None

LAST_ALARM_TIME = 0           
ALARM_COOLDOWN = 3.0         
# ==============================================================================
# NIGT TIME CAMERA ENHANCEMENT FOR BETTER SUPERVISION USING CLAHE
# ==============================================================================
# At a high level, this function takes a dark, low-contrast image and makes the details 
# visible by stretching the contrast. However, it does this using a very specific sequence 
# of steps to ensure the colors don't become distorted or cartoonish in the process.

def apply_night_vision_enhancement(frame):
    # CLAHE stands for Contrast Limited Adaptive Histogram Equalization.
    # INSTEAD OF WORKING WITH RGB WE WILL USE LAB COLOR SPACE
    # L : LIGHTNESS-how bright or dark a pixel is (from black to white).
    # A : Represents where the pixel falls on a spectrum from Green to Red
    # B : Represents where the pixel falls on a spectrum from Blue to Yellow
    # WE CONVERT BGR -> LAB BECAUSE IF WE INCREASE THE CONTRAST OF BGR IT WILL MESS UP
    # WITH COLOR USING LAB WE ISOLATE BRIGHTNESS L FROM COLRS A , B
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    # We do this so we can perform operations only on the l_channel (the brightness), 
    # leaving the a_channel and b_channel completely untouched.
    l_channel, a_channel, b_channel = cv2.split(lab)
    # (tileGridSize=(8, 8)): Standard contrast adjustments look at the entire image at once. 
    # If an image has a really bright streetlamp and a pitch-black alley, a global adjustment 
    # fails. CLAHE divides the image into a grid of tiny tiles (8x8 pixels here). 
    # It enhances the contrast within each little tile individually, pulling out hidden details 
    # in the dark alley without blinding out the streetlamp.
    # (clipLimit=3.0): Because we are enhancing tiny tiles, any tiny bit of grain or camera 
    # noise in a dark area can accidentally get boosted into huge, ugly bright spots. 
    # The clipLimit acts as a governor. It says, "Enhance the contrast, but if the contrast 
    # in this specific tile exceeds a value of 3.0, clip it and distribute that excess evenly.
    #  This prevents noise amplification.
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
    return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

# ==============================================================================
#  VIRTUAL TRIPWIRE & GEOFENCING CLASS
# ==============================================================================
class VirtualTripwireEngine:
    def __init__(self, pt_start=(60, 320), pt_end=(580, 320)):
        self.tripwire_line = LineString([pt_start, pt_end]) # INTIALIZING A MATHEMATICAL LINE
        self.trajectory_history = defaultdict(list) # MEMORY TO REMEBER WHERE THE OBJECTS HAVE BEEN
        self.active_alerts = []
        self.frame_index = 0
        self.logged_intruders = set()
        self.logged_vehicles = set()
        self.logged_loiterers = set()

        self.anchor_points = {}          
        self.LOITER_TIME_LIMIT = 20.0    
        self.LOITER_RADIUS = 150
    def check_breach(self, track_id, current_center_pt):
        # YOLO tracker assigns a unique track_id to every object 
        # (e.g., Person #4, Car #12), the system uses a dictionary to remember where 
        # each specific object has been. This line fetches the list of ALL THE past (x, y) 
        # coordinates for whichever object the AI is currently looking at.
        history = self.trajectory_history[track_id]
        # NOW FOR THE SPECIFIC OBJECT WE STORE THE CURRENT COORDINATES RESPECTIVELY
        history.append(current_center_pt)

        # WE CHECK WHEHER OUR history  IS NOT GROWING TOO HUGE (<20) AND IF IT IS 
        # WE SIMPLY POP A VALUE TO ACCOMODATE ANOTHER ONE
        if len(history) > 20:
            history.pop(0)

        # NOW WE WILL DETECT FOR BREACH 
        # IF THAT PATICULAR OBJECT HAS 2 PREVIOUS COORDINATES WE FETCH IT TO CALCULATE THE
        # MOVEMENT VECTOR
        # WE USED LINE STRING TO CALCULATE MOVEMET VECTOR BETWEEN PREVIOUS AND CURRENT
        # THEN WE CHECK WHETHER THE THE MOVEMENT VECTOR INTERSECTS THE TRIPWIRE IF YES 
        # BREACH ELSE SAB CHANGA SI!
        if len(history) >= 2:
            prev_pt = history[-2]
            movement_vector = LineString([prev_pt, current_center_pt])
            if movement_vector.intersects(self.tripwire_line):
                return True
        return False

    def check_loitering(self, track_id, current_center_pt):
        """Checks if a person is standing still or pacing in a small area."""
        current_time = time.time()
        cx, cy = current_center_pt
        
        # if it see's the object first time we will just anchor it 
        if track_id not in self.anchor_points:
            self.anchor_points[track_id] = (current_time, cx, cy)
            return False, 0.0
        
        # or else we just take start_time and points from anchor points
        start_time, anchor_x, anchor_y = self.anchor_points[track_id]
        duration = current_time - start_time
        
        # if the duration of them being less than time limit then do nothing
        if duration < self.LOITER_TIME_LIMIT:
            return False, duration
            
        # if the object is in the frame for greater than time limit then calculate distance 
        # cx - anchor_x: Measures the horizontal distance between the two points.cy - anchor_y: 
        # Measures the vertical distance between the two points.math.hypot(): 
        # Computes the Euclidean distance (the length of the hypotenuse of a right triangle) 
        # using the Pythagorean theorem (underRoot(a**2 + b**2))
        distance_moved = math.hypot(cx - anchor_x, cy - anchor_y)
        
        if distance_moved < self.LOITER_RADIUS:
            # object is  pacing or standing still!
            return True, duration
        else:
            # object walked a long distance. They are just passing by.
            # Reset their anchor to their current spot so we can check if they stop walking later.
            self.anchor_points[track_id] = (current_time, cx, cy)
            return False, 0.0

    def trigger_alert(self, text, color=(0, 0, 255), display_duration_frames=60):
        self.active_alerts.append({
            "message": text,
            "color": color,
            "expiry_frame": self.frame_index + display_duration_frames
        })

# ==============================================================================
# MAIN VIDEO ANALYTICS LOOP
# ==============================================================================
def run_surveillance_pipeline():
    global NIGHT_MODE_ENABLED,AUTO_NIGHT_MODE,LAST_ALARM_TIME
    print("🚀 Loading YOLO11s Surveillance Model...")
    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        # model = YOLO("yolo11s.pt")
        print("Couldn't find or load the model")

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    tripwire_engine = VirtualTripwireEngine(pt_start=(350,0), pt_end=(350, 1080)) # 15396218_1920_1080_25fps.mp4
    #tripwire_engine = VirtualTripwireEngine(pt_start=(0,1080), pt_end=(3840, 1080))# 15105513_3840_2160_30fps
    seen_all_objects = set()
    while cap.isOpened():
        ret, raw_frame = cap.read()
        if not ret: break

        tripwire_engine.frame_index += 1
        h, w, _ = raw_frame.shape

        if AUTO_NIGHT_MODE:
            # Calculate average brightness of the frame (0 is black, 255 is white)
            avg_brightness = np.mean(cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY))
            NIGHT_MODE_ENABLED = avg_brightness < 60  # Turn on if scene is dark

        processed_frame = apply_night_vision_enhancement(raw_frame) if NIGHT_MODE_ENABLED else raw_frame.copy()
        clean_snapshot = processed_frame.copy()
        results = model.track(source=processed_frame, persist=True, tracker="bytetrack.yaml", conf=0.30, verbose=False)[0]

        p1 = tripwire_engine.tripwire_line.coords[0]
        p2 = tripwire_engine.tripwire_line.coords[1]
        cv2.line(processed_frame, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 0, 255), 2)
        cv2.putText(processed_frame, "RESTRICTED PERIMETER FENCE", (int(p1[0]), int(p1[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        if results.boxes.id is not None:
            boxes = results.boxes.xyxy.cpu().numpy()
            track_ids = results.boxes.id.int().cpu().numpy()
            class_ids = results.boxes.cls.int().cpu().numpy()
            confs = results.boxes.conf.cpu().numpy()

            for box, track_id, cls_id, conf in zip(boxes, track_ids, class_ids, confs):
                x1, y1, x2, y2 = map(int, box)
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                center_pt = (center_x, center_y)

                if track_id not in seen_all_objects:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Map the numerical cls_id (0, 1, 2) to a readable word
                    class_names = {0: "Person", 1: "Vehicle", 2: "Animal"}
                    obj_type = class_names.get(cls_id, "Unknown")
                    
                    with open(ALL_OBJECTS_TXT_LOG, "a") as f:
                        f.write(f"{timestamp}, {obj_type}, ID:{track_id}, Conf:{conf:.2f}\n")
                        
                    seen_all_objects.add(track_id)
                    print(f"LOGGED: {obj_type} #{track_id} detected on camera.")

                has_breached = tripwire_engine.check_breach(track_id, center_pt)

                if cls_id == 0:
                    is_loitering, duration = tripwire_engine.check_loitering(track_id, center_pt)
                    if has_breached:
                        # What happens AFTER they cross the line
                        box_color = (0, 0, 255) # Red Box
                        label = f"ID:{track_id} INTRUDER ({conf:.2f})"
                        tripwire_engine.trigger_alert(f"CRITICAL: Human ID #{track_id} breached!", color=(0, 0, 255))

                        current_time = time.time()
                        if (current_time - LAST_ALARM_TIME) > ALARM_COOLDOWN:
                            if ALARM_SOUND:
                                ALARM_SOUND.play() 
                            LAST_ALARM_TIME = current_time

                        if track_id not in tripwire_engine.logged_intruders:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{PERSON_LOG_DIR}/intruder_{track_id}_{timestamp}.jpg"
                            
                            # Draw detection box on clean snapshot (without red tripwire)
                            evidence_frame = clean_snapshot.copy()
                            cv2.rectangle(evidence_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                            cv2.putText(evidence_frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                            
                            cv2.imwrite(filename, evidence_frame)
                            print(f"📸 [PERSON LOGGED]: {filename}")
                            tripwire_engine.logged_intruders.add(track_id)
                    
                    elif is_loitering:
                        box_color = (0, 165, 255) # Orange
                        label = f"ID:{track_id} SUSPICIOUS ({duration:.0f}s)"
                        
                        if track_id not in tripwire_engine.logged_loiterers:
                            tripwire_engine.trigger_alert(f"SUSPICIOUS: ID #{track_id} is stationary/pacing near border!", color=(0, 165, 255))
                            
                            img_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{LOITER_LOG_DIR}/loiterer_{track_id}_{img_timestamp}.jpg"
                            
                            evidence_frame = clean_snapshot.copy()
                            cv2.rectangle(evidence_frame, (x1, y1), (x2, y2), box_color, 2)
                            cv2.putText(evidence_frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)
                            cv2.imwrite(filename, evidence_frame)
                            print(f"[SUSPICIOUS BEHAVIOR]: {filename}")
                            
                            tripwire_engine.logged_loiterers.add(track_id)

                    else:
                        box_color = (255, 255, 0) # Cyan/Yellow Box (Watching)
                        label = f"ID:{track_id} PERSON ({conf:.2f})"
                elif cls_id == 1:
                    if has_breached:
                        box_color = (0, 140, 255)
                        label = f"ID:{track_id} VEHICLE BREACH ({conf:.2f})"
                        tripwire_engine.trigger_alert(f"⚠️ VEHICLE: ID #{track_id} crossed boundary line.", color=(0, 140, 255))
                        
                        current_time = time.time()
                        if (current_time - LAST_ALARM_TIME) > ALARM_COOLDOWN:
                            if ALARM_SOUND:
                                ALARM_SOUND.play() 
                            LAST_ALARM_TIME = current_time

                        # Save Vehicle Evidence
                        if track_id not in tripwire_engine.logged_vehicles:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{CAR_LOG_DIR}/vehicle_{track_id}_{timestamp}.jpg"
                            
                            # Draw detection box on clean snapshot (without red tripwire)
                            evidence_frame = clean_snapshot.copy()
                            cv2.rectangle(evidence_frame, (x1, y1), (x2, y2), (0, 140, 255), 2)
                            cv2.putText(evidence_frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)
                            
                            cv2.imwrite(filename, evidence_frame)
                            print(f"[CAR LOGGED]: {filename}")
                            tripwire_engine.logged_vehicles.add(track_id)
                    else:
                        box_color = (255, 150, 0)
                        label = f"ID:{track_id} VEHICLE ({conf:.2f})"
                else:
                    box_color = (0, 255, 0)
                    label = f"ID:{track_id} ANIMAL (FILTERED)"
                    if has_breached: tripwire_engine.trigger_alert(f"FALSE ALARM: Animal ID #{track_id} suppressed.", color=(0, 255, 0))

                cv2.rectangle(processed_frame, (x1, y1), (x2, y2), box_color, 2)
                cv2.circle(processed_frame, center_pt, 4, box_color, -1)
                cv2.putText(processed_frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 2)

                trail = tripwire_engine.trajectory_history[track_id]
                for i in range(1, len(trail)):
                    cv2.line(processed_frame, trail[i - 1], trail[i], box_color, 1)

        cv2.rectangle(processed_frame, (0, 0), (w, 38), (20, 20, 20), -1)
        mode_text = f"NIGHT VISION: {'AUTO (ON)' if NIGHT_MODE_ENABLED and AUTO_NIGHT_MODE else 'ON' if NIGHT_MODE_ENABLED else 'OFF'}"
        cv2.putText(processed_frame, f"GARUDA | {mode_text}", (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(processed_frame, "[N] Toggle Night  |  [Q] Quit", (w - 260, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        tripwire_engine.active_alerts = [a for a in tripwire_engine.active_alerts if a["expiry_frame"] > tripwire_engine.frame_index]
        for idx, alert in enumerate(tripwire_engine.active_alerts[-3:]):
            y_pos = 70 + (idx * 30)
            cv2.rectangle(processed_frame, (10, y_pos - 20), (w - 10, y_pos + 6), (10, 10, 10), -1)
            cv2.putText(processed_frame, alert["message"], (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.52, alert["color"], 2)

        cv2.imshow("BorderGuard AI", processed_frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord('n'): 
            AUTO_NIGHT_MODE = False
            NIGHT_MODE_ENABLED = not NIGHT_MODE_ENABLED

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_surveillance_pipeline()