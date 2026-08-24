"""
Real-time Face Recognition (Webcam Matching)
=============================================
Matches faces seen on the webcam against the database built by enroll_faces.py.

Pipeline per frame:
    1. DeepFace detects + aligns faces in the frame (same detector/alignment
       used during enrollment -- this consistency matters a lot for accuracy).
    2. Each detected face gets an embedding (Facenet model).
    3. Embedding is compared (cosine similarity) against every enrolled
       person's embeddings; best match above the threshold wins.

Usage:
    python enroll_faces.py --input known_faces --output embeddings.json   # once
    python recognize_webcam.py --db embeddings.json                       # then this

    python recognize_webcam.py --source 1              # different webcam
    python recognize_webcam.py --threshold 0.5          # stricter/looser matching
    python recognize_webcam.py --headless               # no display window

Press 'q' to quit the display window.
"""

import argparse
import json
import os
import shutil
import time
from collections import deque

import cv2
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIRED_CASCADES = ["haarcascade_frontalface_default.xml", "haarcascade_eye.xml"]


def ensure_opencv_cascades():
    """
    DeepFace's 'opencv' detector looks for cascade XML files directly inside
    the installed cv2 package's data/ folder. Some opencv-python wheels
    (notably some Windows builds) ship without these files. If they're
    missing, copy them in from the copies bundled next to this script.
    """
    cv2_data_dir = os.path.join(os.path.dirname(cv2.__file__), "data")
    os.makedirs(cv2_data_dir, exist_ok=True)

    for filename in REQUIRED_CASCADES:
        dest = os.path.join(cv2_data_dir, filename)
        if os.path.isfile(dest):
            continue

        source = os.path.join(SCRIPT_DIR, filename)
        if not os.path.isfile(source):
            raise RuntimeError(
                f"Missing required file: {filename}\n"
                f"Expected it next to this script at: {source}\n"
                "Download it and place it in the same folder as this script."
            )

        shutil.copy(source, dest)
        print(f"[setup] Copied {filename} into {cv2_data_dir}")


ensure_opencv_cascades()

from deepface import DeepFace  # noqa: E402  (import after cascade setup)

DETECTOR_BACKEND = "opencv"  # must match the backend used in enroll_faces.py


def load_database(db_path: str):
    if not os.path.isfile(db_path):
        raise RuntimeError(
            f"Embeddings database not found: {db_path}\n"
            "Run enroll_faces.py first to create it."
        )
    with open(db_path) as f:
        data = json.load(f)

    model_name = data["model"]
    # Flatten to two parallel arrays for fast vectorized comparison:
    # names[i] corresponds to embeddings[i]
    names = []
    vectors = []
    for person, embeddings in data["database"].items():
        for emb in embeddings:
            names.append(person)
            vectors.append(emb)

    return model_name, names, np.array(vectors, dtype="float32")


def cosine_similarity(query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    """query: (D,)  vectors: (N, D)  -> similarities: (N,)"""
    query_norm = query / (np.linalg.norm(query) + 1e-10)
    vec_norms = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10)
    return vec_norms @ query_norm


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
    try:
        return int(src)
    except ValueError:
        return src


def main():
    parser = argparse.ArgumentParser(description="Real-time face recognition against enrolled photos")
    parser.add_argument("--db", default="embeddings.json", help="Path to embeddings database")
    parser.add_argument("--source", default="0", help="Webcam index, video file, or stream URL")
    parser.add_argument("--threshold", type=float, default=0.4,
                         help="Cosine similarity threshold to accept a match (0-1, default 0.4). "
                              "Higher = stricter (fewer false matches, may miss real matches).")
    parser.add_argument("--skip-frames", type=int, default=3,
                         help="Only run detection+recognition every Nth frame (default 3); "
                              "boxes are redrawn from the last result on skipped frames. "
                              "Set to 1 to process every frame. Raise this if FPS is low.")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    model_name, names, vectors = load_database(args.db)
    print(f"Loaded {len(names)} reference embeddings for {len(set(names))} people "
          f"(model: {model_name})")

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    fps_tracker = FPSTracker()
    print("Starting recognition. Press 'q' to quit (if a window is shown).")

    frame_idx = 0
    # Cache of (label, color, score, x, y, w, h) tuples from the last frame
    # that actually ran detection+recognition; reused on skipped frames.
    cached_boxes = []

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Stream ended or frame not read.")
                break

            frame_idx += 1
            run_recognition = (frame_idx % max(1, args.skip_frames)) == 1 or args.skip_frames <= 1

            if run_recognition:
                try:
                    results = DeepFace.represent(
                        frame,
                        model_name=model_name,
                        detector_backend=DETECTOR_BACKEND,
                        enforce_detection=False,
                    )
                except Exception:
                    results = []

                # DeepFace.represent with enforce_detection=False returns one
                # low-confidence "face" even when nothing is there; filter those out.
                faces_found = [r for r in results if r.get("face_confidence", 1.0) > 0]

                cached_boxes = []
                for r in faces_found:
                    area = r["facial_area"]
                    x, y, w, h = area["x"], area["y"], area["w"], area["h"]

                    query_emb = np.array(r["embedding"], dtype="float32")
                    sims = cosine_similarity(query_emb, vectors)
                    best_idx = int(np.argmax(sims))
                    score = float(sims[best_idx])

                    if score >= args.threshold:
                        label = names[best_idx]
                        color = (0, 200, 0)  # green for match
                    else:
                        label = "Unknown"
                        color = (0, 0, 220)  # red for unknown

                    cached_boxes.append((label, color, score, x, y, w, h))

            # Draw the current (possibly cached, from a previous frame) boxes.
            for (label, color, score, x, y, w, h) in cached_boxes:
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                text = f"{label} ({score:.2f})"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(frame, (x, y - th - 10), (x + tw + 4, y), color, -1)
                cv2.putText(frame, text, (x + 2, y - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

            fps_tracker.tick()
            cv2.putText(frame, f"FPS: {fps_tracker.fps():.1f}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

            if args.headless:
                print(f"\rFPS: {fps_tracker.fps():5.1f} | Faces: {len(cached_boxes)}", end="")
            else:
                cv2.imshow("Face Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
        print("\nStopped.")


if __name__ == "__main__":
    main()