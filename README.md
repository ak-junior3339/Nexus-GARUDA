# GARUDA
**Guided AI for Real-time Unified Detection & Alerting**

![Smart India Hackathon](https://img.shields.io/badge/Smart_India_Hackathon-2026-blue?style=for-the-badge)
![Problem Statement](https://img.shields.io/badge/PS_ID-26187-red?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-In_Development-green?style=for-the-badge)

Garuda is an AI-driven software platform designed to transform existing, conventional CCTV infrastructure into a cutting-edge intelligent surveillance network. Built for border security forces, it eliminates the need for expensive, proprietary smart-camera hardware by running advanced Computer Vision and Deep Learning models directly on standard IP-based live video streams.

---

## 🎯 Problem Statement (SIH PS-ID: 26187)

**Background:** Border security forces deploy CCTV cameras at Border Out Posts (BOPs), check posts, and strategic locations. Conventional systems only provide passive video recording, requiring continuous human observation. Advanced functionalities (FRS, ANPR, Intrusion Detection) usually require specialized, costly hardware, making remote deployment difficult.

**Our Solution:** A software-defined surveillance platform that ingests live video streams from standard CCTV cameras and performs real-time video analytics to extract actionable intelligence, providing a highly cost-effective, scalable, and automated monitoring grid.

### Key Capabilities
* [x] Human detection and tracking
* [x] Vehicle detection and classification
* [x] Face detection and Facial Recognition (FRS)
* [x] Automatic Number Plate Recognition (ANPR)
* [x] Virtual fence intrusion detection
* [x] Suspicious activity & night-time movement detection
* [x] Real-time alert generation and event logging

---

## 🧠 AI & Computer Vision Models

Garuda utilizes specialized AI models tailored for different surveillance sectors:

| Sector / Module | Capabilities |
| :--- | :--- |
| **Watchtower** | Person Detection, Vehicle Detection. |
| **Checkpost** | Person Detection, Vehicle Detection, Facial Recognition. |
| **ANPR Engine** | Optical Character Recognition for Vehicle Number Plate Detection. |
| **Facial Recognition** | High-accuracy face recognition against a registered watchlist. |
| **Virtual Tripwire** | Interactive spatial boundary detection with real-time logging. |

---

## 💻 System Workflow & Features

### 🌟 Top Features
* **Auto Night Vision Switch:** Automatically detects low-light environments and toggles the camera feed to high-contrast night vision mode using (CLAHE).

### 🛡️ User Dashboard (Command Center)
* **Authentication:** Secure user login (Accounts can *only* be provisioned by an Admin).
* **Top Navigation (Mainbar):** Garuda Logo, Camera Grid View Toggles, Camera Vision Options (Original, Night Vision, Heat/Infrared), and Active User Profile with Logout.
* **Main Viewport (Left Sidebar/Center):** Actual live camera feeds displaying real-time AI bounding boxes/detections, overlaid with Timestamp and Camera Location.
* **Threat Intelligence (Right Sidebar):** Real-time incident feed showing unresolved incident count, threat name, time, location, AI confidence score, and a "Dismiss" action button.
* **Deep Analytics (Bottom Bar):** 
  * **Audit Log:** Table displaying Time, Camera ID, Entity Type, Identifier, Confidence, and Action Taken.
  * **Threat Graphs:** 24-Hour Threat Frequency line chart (Alerts per hour).

### ⚙️ Admin Dashboard (Superuser Console)
* **User Management:** Create, provision, and delete operator accounts.
* **Session Control:** Force log out any active user system-wide.
* **Audit Trail:** View comprehensive system and user activity logs.
* **Console Access:** Secure redirect bridging the Admin Console to the standard User Tactical Dashboard.

---

# 🛡️ Watchtower Camera — Intelligent Perimeter Surveillance System
 
An AI-powered checkpost/border surveillance solution built for **high-angle, real-world deployment**. It combines object detection, tracking, virtual perimeter logic, and low-light enhancement into a single autonomous monitoring pipeline — with clean evidentiary logging and real-time tactical alerts.
 
---
 
## ✨ Key Features
 
### 🎯 Detection & Tracking
- **High-Angle Macro Object Detection & Tracking** — Optimized for elevated/eatchtower camera mounts, tracking small and distant objects reliably across frames.
- **Multi-Class Classification** — Distinguishes between **Persons**, **Vehicles**, and **Animals**, with built-in wildlife filtering to suppress false alarms from non-threat fauna.
### 🚧 Perimeter Intelligence
- **Virtual Tripwire & Geofence Logic** — Define custom intrusion lines and zones; triggers alerts the moment a tracked object crosses a boundary.
- **Smart Loitering Analysis** — Detects both **stationary loitering** and **pacing behavior**, flagging suspicious dwell-time patterns near the perimeter.
### 🌗 Low-Light Adaptability
- **Autonomous Night-Vision & CLAHE Enhancement** — Automatically enhances low-light frames using **CLAHE in LAB color space** for improved detection accuracy after dark.
### 📝 Logging & Evidence Capture
- **Universal Text Logging** — Every detection event is timestamped and logged to `all_objects_detected.txt`.
- **Multi-Category Evidence Snapshots** — Organized image capture into dedicated folders:
  - `person/`
  - `car/`
  - `loitering/`
- **Clean Anti-Spam Evidentiary Capture** — Snapshots are saved **without HUD or tripwire overlays**, ensuring evidence images stay court-clean, plus cooldown logic to prevent duplicate spam captures.
### 🔊 Alerts & Interface
- **Asynchronous Multi-Modal Audio Alarms** — `pygame`-based alarm engine with a **cooldown governor** to prevent overlapping/spammy alerts.
- **Tactical HUD & Real-Time Alert Ticker** — Live on-screen overlay showing detection status, active alerts, and a scrolling ticker feed.
- **Keyboard Override Controls**:
  | Key | Action |
  |-----|--------|
  | `n` | Toggle Night Mode |
  | `q` | Exit Application |

  ## 🧠 How It Works
 
1. **Capture** — Feed is pulled from the checkpost camera (RTSP/USB/IP source).
2. **Enhance** — If light levels drop, CLAHE (LAB space) auto-enhances the frame.
3. **Detect & Classify** — Objects are detected and classified (person/vehicle/animal), with wildlife filtered out of alerting logic.
4. **Track** — Objects are tracked frame-to-frame for trajectory and dwell-time analysis.
5. **Geofence Check** — Tripwire/zone crossings trigger intrusion alerts.
6. **Loitering Check** — Stationary/pacing behavior beyond a time threshold triggers a loitering alert.
7. **Alert** — Audio alarm fires asynchronously (cooldown-governed) + HUD ticker updates.
8. **Log & Capture** — Event is logged to text file; a clean (overlay-free) snapshot is saved to the relevant evidence folder.
---
 
## 📌 Notes
- Evidence snapshots are intentionally captured **without HUD/tripwire graphics overlaid**, keeping them suitable as unaltered visual evidence.
- Wildlife filtering helps reduce false-positive alerts in rural/forested checkpost deployments.
---

## 👥 Team Nexus

We are a cross-functional team of developers and AI engineers from DAVV, Indore, building Garuda.

| Team Member | Core Responsibilities |
| :--- | :--- |
| **Akshat Jain** | Frontend, Backend, Database, PPT |
| **Archil Jakhetiya** | AI & ML Modeling |
| **Gourvi Jain** | Frontend, Backend, Database, PPT |
| **Harshil Soni** | Backend, Database, PPT |
| **Khushvardhan Johari** | Frontend, Backend, PPT |
| **Aishwarya Kumar Singh (AK)** | AI & ML Modeling |

---

## 🌿 Repository Structure & Branching

This repository follows a strict feature-branch workflow to maintain code integrity during the hackathon sprint.

* `main` : Production-ready stable code.
* `Feature` : Active development branch for Full-Stack dashboard integration.
* `Archil_facenet` : Dedicated branch for training and testing the Facial Recognition pipeline.
* `feature/watchtower-Cam` : Dedicated branch for training and testing the watchtower camera Model and Engine (Completed)

---
