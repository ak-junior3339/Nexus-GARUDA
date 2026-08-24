"""
Real-time Face Detection System
================================
Uses OpenCV's built-in Haar Cascade classifier — no extra model downloads,
no dependency version issues. Works with webcam, video files, or RTSP/CCTV streams.

Usage:
    python face_detection.py                      # default webcam (index 0)
    python face_detection.py --source 1            # different webcam
    python face_detection.py --source video.mp4    # video file
    python face_detection.py --source rtsp://...   # CCTV / IP camera stream
    python face_detection.py --save output.mp4      # save annotated output
    python face_detection.py --headless             # no display window (e.g. on a server)

Press 'q' to quit the display window.
"""

import argparse
import os
import time
from collections import deque

import cv2

# Directory this script lives in (so the bundled cascade file is found
# regardless of the current working directory the script is run from).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CASCADE = os.path.join(SCRIPT_DIR, "haarcascade_frontalface_default.xml")


class FaceDetector:
    def __init__(self, scale_factor: float = 1.1, min_neighbors: int = 5, min_size: int = 40):
        """
        scale_factor: how much the image size is reduced at each scale (1.05-1.3 typical;
                      smaller = more accurate but slower)
        min_neighbors: how many overlapping detections are required to keep a face
                       (higher = fewer false positives, may miss some faces)
        min_size: minimum face size in pixels to detect
        """
        # Prefer the cascade bundled next to this script — some opencv-python
        # wheels (e.g. headless variants) ship without cv2.data.haarcascades files.
        candidates = [LOCAL_CASCADE, cv2.data.haarcascades + "haarcascade_frontalface_default.xml"]

        cascade_path = None
        for path in candidates:
            if os.path.isfile(path):
                cascade_path = path
                break

        if cascade_path is None:
            raise RuntimeError(
                "Could not find haarcascade_frontalface_default.xml.\n"
                f"Checked: {candidates}\n"
                "Make sure the XML file is in the same folder as this script."
            )

        self.cascade = cv2.CascadeClassifier(cascade_path)
        if self.cascade.empty():
            raise RuntimeError(f"Found file but OpenCV could not parse it: {cascade_path}")

        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.min_size = (min_size, min_size)

    def detect(self, frame_bgr):
        """Returns list of detections: [{'bbox': (x, y, w, h)}]"""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)  # improves detection in uneven lighting

        faces = self.cascade.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=self.min_size,
        )

        return [{"bbox": (int(x), int(y), int(w), int(h))} for (x, y, w, h) in faces]


def draw_detections(frame, detections):
    for det in detections:
        x, y, w, h = det["bbox"]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 220, 0), 2)
    return frame


class FPSTracker:
    def __init__(self, window=30):
        self.times = deque(maxlen=window)

    def tick(self):
        self.times.append(time.time())

    def fps(self):
        if len(self.times) < 2:
            return 0.0
        return (len(self.times) - 1) / (self.times[-1] - self.times[0])


def parse_source(src: str):
    """Allow numeric webcam indices as well as file paths / stream URLs."""
    try:
        return int(src)
    except ValueError:
        return src


def main():
    parser = argparse.ArgumentParser(description="Real-time face detection")
    parser.add_argument("--source", default="0",
                         help="Webcam index, video file path, or RTSP/HTTP stream URL")
    parser.add_argument("--min-neighbors", type=int, default=5,
                         help="Higher = fewer false positives, may miss faces (default 5)")
    parser.add_argument("--min-size", type=int, default=40,
                         help="Minimum face size in pixels (default 40)")
    parser.add_argument("--save", default=None,
                         help="Path to save annotated output video (e.g. out.mp4)")
    parser.add_argument("--headless", action="store_true",
                         help="Run without a display window (prints detection counts)")
    args = parser.parse_args()

    source = parse_source(args.source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    detector = FaceDetector(min_neighbors=args.min_neighbors, min_size=args.min_size)
    fps_tracker = FPSTracker()

    writer = None
    if args.save:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 20
        writer = cv2.VideoWriter(args.save, fourcc, src_fps, (w, h))

    print("Starting face detection. Press 'q' to quit (if a window is shown).")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Stream ended or frame not read.")
                break

            detections = detector.detect(frame)
            frame = draw_detections(frame, detections)

            fps_tracker.tick()
            fps = fps_tracker.fps()
            cv2.putText(frame, f"FPS: {fps:.1f}  Faces: {len(detections)}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

            if writer:
                writer.write(frame)

            if args.headless:
                print(f"\rFPS: {fps:5.1f} | Faces detected: {len(detections)}", end="")
            else:
                cv2.imshow("Face Detection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        if writer:
            writer.release()
        if not args.headless:
            cv2.destroyAllWindows()
        print("\nStopped.")


if __name__ == "__main__":
    main()