# GARUDA
**Guided AI for Real-time Unified Detection & Alerting**

![Smart India Hackathon](https://img.shields.io/badge/Smart_India_Hackathon-2026-blue?style=for-the-badge)
![Problem Statement](https://img.shields.io/badge/PS_ID-26187-red?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active_Development-green?style=for-the-badge)

Garuda is an AI-driven software platform designed to transform existing, conventional CCTV infrastructure into a cutting-edge intelligent surveillance network. Built for border security forces, it eliminates the need for expensive, proprietary smart-camera hardware by running advanced Computer Vision, Deep Learning, and OCR models directly on standard IP-based live video streams and security feeds.

---

## 🎯 Problem Statement (SIH PS-ID: 26187)

**Background:** Border security forces deploy CCTV cameras at Border Out Posts (BOPs), check posts, and strategic locations. Conventional systems only provide passive video recording, requiring continuous human observation. Advanced functionalities (FRS, ANPR, Intrusion Detection) usually require specialized, costly hardware, making remote deployment difficult.

**Our Solution:** A software-defined surveillance platform that ingests live video streams from standard CCTV cameras and performs real-time video analytics to extract actionable intelligence, providing a highly cost-effective, scalable, and automated monitoring grid.

### Key Capabilities
* [x] Human detection, tracking, and spatial behavior analysis (Loitering/Pacing)
* [x] Vehicle detection, classification, and boundary breach alerting
* [x] Face detection and Facial Recognition (FRS) against secure watchlists
* [x] Automatic Number Plate Recognition (ANPR) with OCR noise suppression and CSV logging
* [x] Virtual fence intrusion detection with interactive coordinate calibration
* [x] Autonomous low-light enhancement (CLAHE in LAB color space) for night operations
* [x] Real-time multi-modal audio alarms and incident event logging

---

## 🧠 AI & Computer Vision Architecture

Garuda utilizes specialized AI pipelines and neural network modules tailored for different border surveillance sectors:

| Sector / Module | Core Technologies & Capabilities |
| :--- | :--- |
| **Watchtower (Perimeter)** | YOLO11 / YOLOv8 object tracking, multi-class classification (Person/Vehicle/Animal with wildlife filtering), virtual tripwire breach detection, and loitering analysis. |
| **Checkpost (ANPR Engine)** | Custom YOLOv8 plate detector (`anprbest.pt`), EasyOCR text extraction, GPU acceleration, plate crop upscaling, and robust regex normalization (`clean_plate`). |
| **Super-Resolution (Upscaling)** | EDSR ($4	imes$) Deep Super-Resolution network for enhancing low-resolution security/surveillance captures and license plates. |
| **Facial Recognition (FRS)** | High-accuracy face detection and embedding verification against registered threat databases (`Archil_facenet`). |
| **Adaptive Night Vision** | Automated scene brightness evaluation and CLAHE (Contrast Limited Adaptive Histogram Equalization) in LAB color space for dark-environment clarity. |

---

## 💻 System Workflow & Dashboard Ecosystem

### 🛡️ User Dashboard (Tactical Command Center)
* **Authentication:** Secure user login with role-based provisioning (accounts provisioned exclusively by Super Admin).
* **Top Navigation Bar:** Garuda Logo, Camera Grid View Toggles, Camera Vision Options (Original, Night Vision, Thermal/Infrared), and Active User Profile with Logout.
* **Main Viewport:** Real-time live camera streams displaying bounding boxes, classification tags, timestamps, and camera geo-locations.
* **Threat Intelligence Feed:** Live incident ticker showing unresolved breach counts, threat category, timestamp, location, AI confidence score, and quick dismissal controls.
* **Deep Analytics:** 
  * **Audit Log Table:** Comprehensive event records tracking Timestamp, Camera ID, Entity Type, Identifier, Confidence, and Action Taken.
  * **Threat Graphs:** 24-Hour Threat Frequency visualization and alert distribution metrics.

### ⚙️ Admin Dashboard (Superuser Console)
* **User Management:** Provision, configure, and de-provision operator accounts.
* **Session Control:** Force terminate active sessions system-wide.
* **Audit Trail:** Deep dive into system events, user actions, and security logs.
* **Console Access:** Secure single-click bridge connecting the Admin Console to the Tactical User Dashboard.

---

# 🛡️ Watchtower Subsystems

## 1. Watchtower Camera — Perimeter Surveillance Engine
An AI-powered perimeter monitoring solution built for high-angle, real-world deployment. Combines object detection, tracking, virtual perimeter logic, and low-light enhancement into an autonomous pipeline.

### ✨ Key Module Features
* **High-Angle Macro Object Detection & Tracking** — Optimized for elevated tower mounts, tracking distant objects reliably across frames using ByteTrack.
* **Wildlife Filtering** — Automatically suppresses false alarms triggered by non-threat fauna crossing the perimeter.
* **Smart Loitering & Pacing Analysis** — Tracks dwell-time via anchor points and Euclidean distance thresholds to flag suspicious stationary behavior.
* **Clean Evidentiary Snapshot Capture** — Automatically saves unaltered image evidence (`person/`, `car/`, `loitering/`) **without HUD or tripwire graphics**, ensuring court-clean archives.
* **Multi-Modal Audio Alarms** — `pygame`-driven alarm engine governed by a cooldown timer to prevent audio spam.
* **Dynamic Tripwire addition** — Admin can integrate a custom tripwire at the time of a new camera regestration we can also change it othertime as well

---

## 2. ANPR (Automatic Number Plate Recognition) Engine
A high-performance vehicle identification pipeline designed to capture, isolate, and read license plates from moving traffic feeds.

### ✨ Key Module Features
* **Custom YOLOv8 Plate Localization** — Trained model (`anprbest.pt`) optimized for diverse lighting and plate angles trained on roboflow universe vehicle data.
* **EasyOCR & GPU Acceleration** — Automatically leverages CUDA-enabled GPUs for high-throughput text reading with graceful CPU fallback.
* **Advanced Text Normalization & Cleaning**:
  * Uppercase enforcement and non-alphanumeric character stripping (`|`, `-`, `[`, `]`).
  * Automatic removal of regional watermarks (e.g., Indian blue `IND` strips).
  * Minimum length validation and confidence thresholding (`DETECTION_CONF_THRESHOLD = 0.4`, `OCR_CONF_THRESHOLD = 0.4`).
* **Deduplicated CSV Logging** — Post-processing `merge_plate_reads` algorithm filters out partial reads and frame-by-frame redundancies, recording the single best high-confidence entry per unique vehicle plate.

---

## 3. EDSR Super-Resolution Upscaling
A deep-learning enhancement utility leveraging the Enhanced Deep Residual Networks for Single Image Super-Resolution ($	ext{EDSR } 4	imes$) to clarify distant security footage and unclear plates.

---

## 👥 Team Nexus

We are a cross-functional team of developers and AI engineers from DAVV, Indore, building Garuda for the Smart India Hackathon.

| Team Member | Core Responsibilities |
| :--- | :--- |
| **Akshat Jain** | Frontend, Backend, Database, Presentation & Documentation |
| **Archil Jakhetiya** | AI & ML Modeling (Facial Recognition & Deep Learning) |
| **Gourvi Jain** | Frontend, Backend, Database, Presentation & Documentation |
| **Harshil Soni** | Backend, Database, Presentation & Documentation |
| **Khushvardhan Johari** | Frontend, Backend, Presentation & Documentation |
| **Aishwarya Kumar Singh (ak_junior)** | AI & ML Modeling (Object Detection & Tracking Pipelines) |

---

## 🌿 Repository Structure & Branching Strategy

This repository follows a strict feature-branch workflow to maintain code integrity during the hackathon sprint:

* `main` : Production-ready stable code and deployment builds.
* `Feature` : Active development branch for Full-Stack dashboard integration.
* `Archil_facenet` : Dedicated branch for training and testing the Facial Recognition pipeline.
* `feature/watchtower-Cam` : Dedicated branch for training and testing the watchtower camera model and boundary engine (Completed).
* `ANPR` : ANPR integration branch featuring optimized frame skip logic and CSV logging.



python backend/main.py
python -m http.server 5500