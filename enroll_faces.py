"""
Face Enrollment
================
Builds a database of face embeddings from your reference photos, so the
webcam script can match people against it.

Folder structure expected:

    known_faces/
        Alice/
            photo1.jpg
            photo2.jpg
        Bob/
            photo1.jpg
        Carol/
            photo1.jpg
            photo2.jpg

One subfolder per person (the folder name becomes the label). You can put
1+ photos per person -- more photos (different angles/lighting) = better
matching accuracy. Photos should be reasonably clear, front-facing shots.

Usage:
    python enroll_faces.py --input known_faces --output embeddings.json

Run this once whenever you add/change reference photos, then run
recognize_webcam.py to do the live matching.
"""

import argparse
import json
import os
import shutil

import cv2

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

MODEL_NAME = "Facenet"  # 128-d embeddings, good speed/accuracy balance on CPU
SUPPORTED_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def enroll(input_dir: str, output_path: str):
    if not os.path.isdir(input_dir):
        raise RuntimeError(f"Input folder not found: {input_dir}")

    database = {}  # name -> list of embeddings (one per enrolled photo)

    people = sorted(
        d for d in os.listdir(input_dir)
        if os.path.isdir(os.path.join(input_dir, d))
    )

    if not people:
        raise RuntimeError(
            f"No person subfolders found in {input_dir}. "
            "Expected structure: known_faces/<PersonName>/photo.jpg"
        )

    for person in people:
        person_dir = os.path.join(input_dir, person)
        photos = [
            f for f in sorted(os.listdir(person_dir))
            if f.lower().endswith(SUPPORTED_EXT)
        ]

        if not photos:
            print(f"  [skip] {person}: no image files found")
            continue

        embeddings = []
        for photo in photos:
            photo_path = os.path.join(person_dir, photo)
            try:
                results = DeepFace.represent(
                    photo_path,
                    model_name=MODEL_NAME,
                    detector_backend="opencv",
                    enforce_detection=True,
                )
                # represent() returns a list (one entry per face found);
                # use the first/largest face found in the reference photo.
                embeddings.append(results[0]["embedding"])
                print(f"  [ok]   {person}/{photo}")
            except ValueError as e:
                # DeepFace raises ValueError when it can't find a face
                print(f"  [FAIL] {person}/{photo}: no face detected ({e})")

        if embeddings:
            database[person] = embeddings
        else:
            print(f"  [warn] {person}: no usable photos, skipping this person")

    if not database:
        raise RuntimeError("No faces were successfully enrolled. Check your photos.")

    with open(output_path, "w") as f:
        json.dump({"model": MODEL_NAME, "database": database}, f)

    total_photos = sum(len(v) for v in database.values())
    print(f"\nEnrolled {len(database)} people from {total_photos} photos -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Enroll reference photos into a face database")
    parser.add_argument("--input", default="known_faces",
                         help="Folder containing one subfolder per person (default: known_faces)")
    parser.add_argument("--output", default="embeddings.json",
                         help="Where to save the embeddings database (default: embeddings.json)")
    args = parser.parse_args()

    enroll(args.input, args.output)


if __name__ == "__main__":
    main()