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

### Checkpost Camera Features : - 
#### *High-Angle Macro Object Detection & Tracking
#### *Multi-Class Classification (Persons, Vehicles, Animals with wildlife filtering)
#### *Virtual Tripwire & Geofence Perimeter Intrusion Logic
#### *Smart Stationary & Pacing Loitering Analysis
#### *Autonomous Night-Vision & CLAHE Enhancement (LAB Color Space)
#### *Universal Text Logging (all_objects_detected.txt)
#### *Multi-Category Evidence Snapshot Logging (person/, car/, loitering/)
#### *Clean Anti-Spam Evidentiary Capture (Without HUD/Tripwire overlays)
#### *Asynchronous Multi-Modal Audio Alarms (pygame integration with cooldown governor)
#### *Tactical HUD & Real-Time Alert Ticker
#### *Keyboard Override Controls ([n] for Night Mode, [q] to Exit)

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
