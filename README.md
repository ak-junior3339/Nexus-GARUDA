# 🛡️ GARUDA: Live Surveillance & Threat Detection Engine
### Hackathon Project Feature Matrix & Technical Architecture

## 🚀 Overview
**GARUDA** is an advanced, autonomous edge-AI computer vision surveillance engine engineered for high-security watchtower deployments. Designed to minimize operator fatigue and eliminate false alarms, Garuda combines real-time object tracking, mathematical geofencing, intelligent behavioral analysis, and automated night-vision enhancements into a unified, lightweight pipeline.

---

## 📑 Core Feature Breakdown

### 1. Multi-Class Object Tracking & Macro Detection
* **Technology:** Powered by **YOLO11s** object detection paired with **ByteTrack** multi-object tracking.
* **Capabilities:** Seamlessly classifies and tracks dynamic targets across high-angle camera feeds, categorizing them into:
  * **Persons (`Class 0`):** Tracked with bounding boxes and unique IDs.
  * **Vehicles (`Class 1`):** Tracked for perimeter and boundary intrusions.
  * **Animals (`Class 2`):** Automatically filtered out or suppressed to prevent false alarms from wildlife.

### 2. Virtual Tripwire & Geofence Perimeter Logic
* **Technology:** Utilizes computational geometry via **Shapely** (`LineString`).
* **Capabilities:** 
  * Dynamically maps virtual perimeter fences using custom coordinate axes (`pt_start` to `pt_end`).
  * Maintains a moving trajectory history (up to 20 frames) for every unique tracking ID.
  * Calculates real-time movement vectors to instantly flag directional intersection (breaches), upgrading the target state from active surveillance to critical threat.

### 3. Smart Stationary & Pacing Loitering Analysis
* **Technology:** Vector displacement calculations using Euclidean distance (`math.hypot`) over time.
* **Capabilities:** 
  * Prevents alarm fatigue by ignoring normal pedestrian or traffic flow across the camera view.
  * Drops an internal "anchor point" for targets lingering on screen past a specific threshold (e.g., 20 seconds).
  * Triggers a **Suspicious Behavior Warning** (Orange alert state) if an individual stays within a tight geographical radius (<150 pixels), catching scouts or loiterers before a breach occurs.

### 4. Autonomous Night-Vision & CLAHE Enhancement
* **Technology:** Contrast Limited Adaptive Histogram Equalization (CLAHE) in the LAB color space.
* **Capabilities:**
  * **Auto-Brightness Sensor:** Continuously polls pixel luminance across raw video frames. 
  * If environmental brightness drops below a specific threshold (e.g., twilight/darkness), **Night Mode triggers automatically** without operator intervention.
  * Enhances dark alleys and shadows tile-by-tile ($8 \times 8$ grid) while restricting noise amplification, preserving crisp detail without washing out bright spots or distorting color spaces.

### 5. Multi-Category Evidence Logging & Auditing
* **Capabilities:** 
  * **Universal Text Logging:** Appends a master record (`all_objects_detected.txt`) tracking every unique object, category, track ID, confidence score, and exact timestamp.
  * **Clean Snapshot Evidentiary Capture:** Automatically silos evidence into structured directories (`breach_logs/person/`, `breach_logs/car/`, `breach_logs/loitering/`).
  * **Smart Anti-Spam & Clean Overlays:** Saves high-resolution frames of the threat *without* obstructing red tripwire lines or HUD banners, and uses memory sets (`logged_intruders`) to ensure exactly **one** snapshot per incident.

### 6. Asynchronous Multi-Modal Alerting & HUD
* **Technology:** Pygame mixer audio engine + OpenCV HUD UI rendering.
* **Capabilities:**
  * **Non-Blocking Audio Alarms:** Plays localized `.wav` siren files asynchronously via background threads to prevent video frame-rate stuttering during critical breaches.
  * **Cooldown Governor:** Implements a strict time cooldown (`ALARM_COOLDOWN = 3.0s`) to prevent audio feedback loops or glitchy spamming while a target crosses the perimeter.
  * **Tactical HUD:** Displays live system states, active alert tickers, night-vision mode indicators, and robust keyboard overrides (`[N]` for manual toggle, `[Q]` to exit).