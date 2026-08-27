"""
test_video.py

Runs face detection + recognition (identity matching against
known_faces.pkl) on an uploaded video file. Draws bounding boxes +
names on each frame, and either displays it live or saves an
annotated output video.

Speed options:
    --frame-skip N     only run detection every Nth frame (default 1 = every frame)
    --det-size N       detector input size, smaller = faster but may miss small faces (default 640)
    --no-display       skip live preview window (faster, useful for long videos)

Usage:
    python test_video.py video.mp4
    python test_video.py video.mp4 --save output.mp4 --frame-skip 3 --det-size 320 --no-display
"""

import argparse
import cv2
import pickle
import os
import numpy as np
from insightface.app import FaceAnalysis


def get_app(det_size=640):
    """Loads the full model pack (detection + recognition + attributes)."""
    app = FaceAnalysis(name="buffalo_l")
    app.prepare(ctx_id=-1, det_size=(det_size, det_size))
    return app


def load_known_faces(db_path="known_faces.pkl"):
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            return pickle.load(f)
    return {}


def identify(embedding, known_faces, threshold=0.5):
    best_name, best_sim = "Unknown", -1
    for name, known_emb in known_faces.items():
        sim = np.dot(embedding, known_emb) / (
            np.linalg.norm(embedding) * np.linalg.norm(known_emb)
        )
        if sim > best_sim:
            best_name, best_sim = name, sim
    return (best_name, best_sim) if best_sim >= threshold else ("Unknown", best_sim)


def process_video(video_path, save_path=None, display=True, min_face_size=0,
                   frame_skip=1, det_size=640):
    app = get_app(det_size=det_size)
    known_faces = load_known_faces()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Could not open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    writer = None
    if save_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(save_path, fourcc, fps, (width, height))

    frame_idx = 0
    total_detections = 0
    last_faces = []  # reuse last detection result on skipped frames

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        run_detection = (frame_idx % frame_skip == 0) or frame_idx == 1

        if run_detection:
            faces = app.get(frame)
            last_faces = faces
        else:
            faces = last_faces  # draw boxes from the last processed frame

        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            if min_face_size and (w < min_face_size or h < min_face_size):
                continue

            if run_detection:
                total_detections += 1
            name, sim = identify(face.embedding, known_faces)

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{name} ({sim:.2f})"
            cv2.putText(frame, label, (x1, max(y1 - 10, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.putText(frame, f"Frame {frame_idx}/{total_frames}  Faces: {len(faces)}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        if writer:
            writer.write(frame)

        if display:
            cv2.imshow("Face Detection - Video Test", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    if writer:
        writer.release()
    if display:
        cv2.destroyAllWindows()

    print(f"\nProcessed {frame_idx} frames ({frame_idx // frame_skip} ran detection), "
          f"{total_detections} total face detections.")
    if save_path:
        print(f"Saved annotated video to: {save_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--save", default=None, help="Path to save annotated output video")
    parser.add_argument("--no-display", action="store_true", help="Don't show live preview window")
    parser.add_argument("--min-face-size", type=int, default=0, help="Skip faces smaller than this (pixels)")
    parser.add_argument("--frame-skip", type=int, default=1,
                         help="Run detection every Nth frame (default 1 = every frame). "
                              "Boxes are reused for skipped frames.")
    parser.add_argument("--det-size", type=int, default=640,
                         help="Detector input size (default 640). Try 320 for faster, less accurate detection.")
    args = parser.parse_args()

    process_video(
        args.video_path,
        save_path=args.save,
        display=not args.no_display,
        min_face_size=args.min_face_size,
        frame_skip=args.frame_skip,
        det_size=args.det_size,
    )