import argparse
import time
from collections import deque

import cv2
from load_model import get_app
from match import load_known_faces, identify


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
    parser = argparse.ArgumentParser(description="Real-time face recognition against known_faces.pkl")
    parser.add_argument("--db", default="known_faces.pkl", help="Path to known faces pickle file")
    parser.add_argument("--source", default="0", help="Webcam index, video file, or stream URL")
    parser.add_argument("--threshold", type=float, default=0.5,
                         help="Cosine similarity threshold to accept a match (0-1, default 0.5). "
                              "Higher = stricter (fewer false matches, may miss real matches).")
    parser.add_argument("--skip-frames", type=int, default=1,
                         help="Only run detection+recognition every Nth frame (default 1 = every frame); "
                              "boxes are redrawn from the last result on skipped frames. "
                              "Raise this (e.g. 3) if FPS is low.")
    parser.add_argument("--headless", action="store_true", help="Don't open a display window")
    args = parser.parse_args()

    app = get_app()
    known_faces = load_known_faces(args.db)

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    fps_tracker = FPSTracker()
    print("Starting recognition. Press 'q' to quit (if a window is shown).")

    frame_idx = 0
    # Cache of (name, sim, box) tuples from the last frame that actually ran
    # detection+recognition; reused on skipped frames to keep boxes on screen.
    cached_results = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Stream ended or frame not read.")
                break

            frame_idx += 1
            run_recognition = (frame_idx % max(1, args.skip_frames)) == 1 or args.skip_frames <= 1

            if run_recognition:
                cached_results = []
                faces = app.get(frame)
                for face in faces:
                    box = face.bbox.astype(int)
                    name, sim = identify(face.embedding, known_faces, threshold=args.threshold)
                    cached_results.append((name, sim, box))

            for (name, sim, box) in cached_results:
                color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                cv2.putText(frame, f"{name} ({sim:.2f})", (box[0], box[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            fps_tracker.tick()
            cv2.putText(frame, f"FPS: {fps_tracker.fps():.1f}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

            if args.headless:
                print(f"\rFPS: {fps_tracker.fps():5.1f} | Faces: {len(cached_results)}", end="")
            else:
                cv2.imshow("Face ID", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
        print("\nStopped.")


if __name__ == "__main__":
    main()