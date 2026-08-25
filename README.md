# (Garuda) - Watchtower Cam 

This branch (`feature/Watchtower-cam`) contains the local video analytics engine optimized for high-angle, long-distance (50–200m) border surveillance. It processes live or pre-recorded feeds to detect, track, and classify threats using a custom-trained YOLO model (VisDrone + COCO Animals).

## 🚀 Features in this Branch

* **Unified 3-Class Detection:** Specifically trained to detect Persons (Critical), Vehicles (Warning), and Animals (Suppressed False Alarms) from a steep watchtower perspective.
* **Dynamic Threat Geofencing:** Utilizes `shapely` to draw a virtual perimeter. Objects are tracked using ByteTrack, and a "PERSON" is only reclassified as an "INTRUDER" once they physically cross the defined boundary.
* **Software Night-Vision (CLAHE):** Real-time contrast enhancement in the LAB color space to pull human silhouettes out of pitch-black CCTV feeds without distorting the video stream.

## 🛠️ Setup & Installation

**1. Install Dependencies**
Ensure your local Python environment has the necessary computer vision and geometry libraries installed:
```bash
pip install ultralytics opencv-python numpy shapely