# GARUDA
**Guided AI for Real-time Unified Detection & Alerting**

![Smart India Hackathon](https://img.shields.io/badge/Smart_India_Hackathon-2026-blue?style=for-the-badge)
![Problem Statement](https://img.shields.io/badge/PS_ID-26187-red?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active_Development-green?style=for-the-badge)

Garuda is an AI-driven software platform designed to transform existing, conventional CCTV infrastructure into a cutting-edge intelligent surveillance network. Built for border security forces, it eliminates the need for expensive, proprietary smart-camera hardware by running advanced Computer Vision, Deep Learning, and OCR models directly on standard IP-based live video streams and security feeds.

---

## Problem Statement (SIH PS-ID: 26187)

**Background:** Border security forces deploy CCTV cameras at Border Out Posts (BOPs), check posts, and strategic locations. Conventional systems only provide passive video recording, requiring continuous human observation. Advanced functionalities (FRS, ANPR, Intrusion Detection) usually require specialized, costly hardware, making remote deployment difficult.

**Our Solution:** A software-defined surveillance platform that ingests live video streams from standard CCTV cameras and performs real-time video analytics to extract actionable intelligence, providing a highly cost-effective, scalable, and automated monitoring grid.

### Key Capabilities
* [x] **Human & Intrusion Tracking**: Real-time trajectory tracing with virtual tripwire perimeter breach detection.
* [x] **Loitering & Pacing Analytics**: Dwell-time monitoring using Euclidean anchor drift calculations.
* [x] **Group Convergence Detection**: Spatial graph clustering to identify suspicious human gatherings ($\ge 3$ persons).
* [x] **High-Yield Raw Video ANPR**: Multi-plate detection with bicubic upscaling, CLAHE contrast boost, and bilateral filtering.
* [x] **Positional OCR & State Disambiguation**: Auto-correction for all 36 Indian State/UT codes (`DL`, `MH`, `KA`, `BH`, etc.) and digit/letter swaps (`0` $\leftrightarrow$ `O`, `1` $\leftrightarrow$ `I`).
* [x] **Two-Tier Zero-Garbage Plate Grammar**: Distinguishes verified full plates from guarded partial snippets while discarding roadside noise.
* [x] **Cloud Evidence Vault**: Real-time Base64 photographic snapshot persistence to PostgreSQL (Neon Cloud) for high-priority security breaches.
* [x] **Autonomous Night Vision**: Real-time LAB-space CLAHE enhancement with manual hotkey override (`[N]`).
* [x] **Memory-Safe Log Rotation**: Auto-pruning buffers keeping CSV logs and UI alert tickers performant indefinitely.

---

## AI & Computer Vision Architecture

Garuda utilizes specialized AI pipelines and neural network modules tailored for different border surveillance sectors:

| Sector / Module | Core Technologies & Architecture | Real-Time Output |
| :--- | :--- | :--- |
| **CAM-01 (Checkpost ANPR)** | Custom YOLOv8 Plate Detector (`anprbest.pt`), EasyOCR, CLAHE + Bilateral Preprocessing, Positional OCR Disambiguation. | Live plate overlay, telemetry feed, and auto-rotated `detection.csv`. |
| **CAM-02 / 03 / 04 (Watchtower)** | Custom YOLO11/v8 (`WTbest.pt`), ByteTrack trajectory tracking, Shapely polygon intersection, Union-Find clustering. | Intruder alerts, audio siren triggers, and Base64 court-admissible snapshots in PostgreSQL. |
| **Super-Resolution (Upscaler)** | EDSR ($4\times$) Deep Super-Resolution network for enhancing low-resolution security/surveillance captures and license plates. | Enhanced high-fidelity plate & suspect crops. |
| **Facial Recognition (FRS)** | High-accuracy face detection and embedding verification against registered threat databases. | Suspect identity matching and watchlist alerts. |
| **Adaptive Night Vision** | Automated scene brightness evaluation and CLAHE in LAB color space for dark-environment clarity. | Low-light contrast-enhanced video stream. |

---

## System Workflow & Dashboard Ecosystem

```
               [ IP Camera Network / RTSP / Video Feeds ]
                                  │
                                  ▼
                     [ FastAPI High-Speed Backend ]
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
       [ CAM-01: ANPR Engine ]          [ CAM-02..04: Watchtower Engine ]
       • Bicubic + CLAHE Crop           • Perimeter Tripwire Breach
       • State Code Resolution          • Loitering Anchor Tracking
       • Zero-Garbage Grammar           • Group Convergence (Graph)
       • Frame-Skip Caching             • Adaptive Night Vision (LAB)
                 │                                 │
                 ├────────────────┬────────────────┤
                 ▼                ▼                ▼
        [ Telemetry Stream ] [ PostgreSQL ] [ Audio Siren ]
          (WebSocket UI)      (Evidence DB)   (Local Alarm)
```

### Operator Dashboard (Tactical Command Center)
* **Live HUD Viewport**: Real-time 30 FPS multi-camera feed displaying tactical overlays, bounding boxes, target velocity vectors, and camera geo-locations.
* **Threat Intelligence Feed**: Live incident ticker showing unresolved breach counts, threat category, timestamp, location, and AI confidence score.
* **Rolling Telemetry Buffer**: Automatically purges the oldest 100 entries whenever the active alert list reaches 200 items to maintain 60 FPS UI rendering.
* **Tactical Night Vision**: Automated dark-scene compensation with instant manual hotkey toggle (`[N]`).
* **Silent Sector Muting**: Independent mute switches per camera sector to prevent siren interference during coordinated actions.

### Admin Console & Evidence Vault (`admin.html`)
* **Unified Evidence Vault**:
  * **Table Dossier View**: Comprehensive incident table with inline thumbnails, camera source, confidence, timestamp, and one-click global deletion.
  * **Card Gallery View**: High-resolution image dossier with instant full-screen modal inspection.
* **Role-Based Operator Provisioning**: Provision and manage `OPERATOR` and `ADMIN` credentials with bcrypt password hashing.
* **Active Session Control**: Real-time operator status tracking and forced session de-authentication.
* **Cross-Origin Resilient API**: Dynamic host resolution matching `window.location.hostname` with automatic backend failover.

---

## Watchtower Subsystems

### 1. Watchtower Perimeter Surveillance Engine
An AI-powered perimeter monitoring solution built for high-angle, real-world deployment. Combines object detection, tracking, virtual perimeter logic, and low-light enhancement into an autonomous pipeline.
* **High-Angle Tracking** — Optimized for elevated tower mounts, tracking distant objects reliably across frames using ByteTrack.
* **Wildlife Filtering** — Automatically suppresses false alarms triggered by non-threat fauna crossing the perimeter.
* **Smart Loitering & Pacing Analysis** — Tracks dwell-time via anchor points and Euclidean distance thresholds to flag suspicious stationary behavior ($>20\text{s}$).
* **Group Convergence Engine** — Disjoint-set union (Union-Find) clustering algorithm detecting 3+ individuals converging within a 120px radius.
* **PostgreSQL Photographic Snapshots** — High-priority breaches (Intruders, Vehicles, Loiterers, Groups) are immediately encoded as Base64 images and committed to PostgreSQL for courtroom-admissible auditing.

---

### 2. High-Yield Raw Video ANPR Engine
A high-performance vehicle identification pipeline designed to capture, isolate, and read license plates from moving traffic feeds without relying on flaky tracking IDs.

```
[ Raw Vehicle Feed ] ──> [ YOLO Plate Localization ] ──> [ Bicubic + CLAHE + Bilateral ]
                                                                     │
                                                                     ▼
[ Clean UI / CSV ] <── [ Zero-Garbage Two-Tier ] <── [ Positional State Disambiguation ]
```

* **Optical Preprocessing**: Crops are upscaled to $\ge 240\text{px}$, equalized with CLAHE (ClipLimit 2.5), and smoothed using Bilateral Filters.
* **State Code Resolution**: Matches and auto-corrects all 36 Indian State/UT and Bharat Series codes (`0L` $\rightarrow$ `DL`, `8H` $\rightarrow$ `BH`, `K4` $\rightarrow$ `KA`, `NH` $\rightarrow$ `MH`, `1N` $\rightarrow$ `TN`).
* **Positional Letter/Digit Swapping**: Enforces digits on positions 2–3 (RTO) and tail positions (`143O` $\rightarrow$ `1430`, `842S` $\rightarrow$ `8425`, `O1` $\rightarrow$ `01`).
* **Two-Tier Grammar Filter**:
  * **Tier 1 (Full Plate)**: `[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}` (e.g. `DL01AB1234`).
  * **Tier 2 (Guarded Partial)**: Valid State head-partials (`DL01A** [PARTIAL]`) or series tail-partials (`**AB1234 [PARTIAL]`).
  * **Noise Rejection**: Strips roadside terms (`STOP`, `CARRIER`, `POLICE`, `DIESEL`, `HSRP`) and repetitive artifacts.
* **Frame-Skip Caching (`FRAME_SKIP = 3`)**: Bounding boxes and labels are cached in RAM on non-inference frames, slashing CPU/GPU load by 66% while maintaining a flicker-free 30 FPS stream.
* **Self-Pruning CSV Retention**: Automatically purges the oldest 1,000 entries when `detection.csv` or `surveillance_log.csv` reaches 2,000 entries.

---

## 👥 Team Nexus (DAVV, Indore)

| Team Member | Core Responsibilities |
| :--- | :--- |
| **Akshat Jain** | Frontend UI/UX and Captcha |
| **Archil Jakhetiya** | AI & ML Modeling (Facial Recognition)|
| **Gourvi Jain** | Frontend UI/UX Engineering, Database Schema |
| **Harshil Soni** | Frontend and Auth |
| **Khushvardhan Johari** | Frontend, Backend & Database |
| **Aishwarya Kumar Singh (ak_junior)** | Computer Vision Architect, Admin Evidence Vault, AI - Web Integration (Watchtower & ANPR Engine Pipelines) |

---

## Repository Structure & Branching Strategy

* `main` : Production-ready stable release and deployment builds.
* `Feature` : Active development branch for Full-Stack dashboard integration.
* `Archil_facenet` : Dedicated branch for training and testing the Facial Recognition pipeline.
* `feature/watchtower-Cam` : Watchtower camera model and virtual perimeter tripwire engine.
* `ANPR` : High-yield ANPR engine featuring raw-video OCR preprocessing and zero-garbage grammar.

---

## Quickstart & Setup Guide

### 1. Prerequisites
- Python 3.10+
- PyTorch with CUDA (or MPS on macOS / CPU fallback)
- PostgreSQL (or Neon Cloud instance)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/YourOrg/Nexus-Garuda.git
cd Nexus-Garuda

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables (`.env`)
Create a `.env` file inside the `backend/` directory:
```env
DATABASE_URL=postgresql://user:password@your-neon-host.neon.tech/garuda-db?sslmode=require
SECRET_KEY=your_super_secret_jwt_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### 4. Running the System
```bash
# Terminal 1: Launch FastAPI Backend Server
cd backend
python main.py

# Terminal 2: Launch Tactical Frontend (from project root)
python -m http.server 5500
```
Open `http://localhost:5500/frontend/login.html` in your browser.



### todo : 
* 1- Adding audio based features (Gunshots,Crown noise)
* 2- Facial recognition
* 3- admin logs
* 4- Group convergence coordinates 
* 5-  Multi-Camera Cross-Tracking (Re-ID): Implement lightweight feature vector embeddings (Re-Identification) to track the same suspect across multiple BOP camera feeds without needing facial recognition.
* 6- Directional Threat Vectoring: Calculate real-time speed, heading angle, and predicted path (e.g., "Target moving 12 km/h SSW toward Post 4"), elevating raw bounding boxes into military tactical telemetry.