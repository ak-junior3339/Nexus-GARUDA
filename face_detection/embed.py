import cv2, pickle, os, numpy as np
from load_model import get_app

app = get_app()
DB_PATH = "face_detection/known_faces.pkl"
PHOTOS_DIR = "face_detection/enroll_photos"

known_faces = {}
if os.path.exists(DB_PATH):
    with open(DB_PATH, "rb") as f:
        known_faces = pickle.load(f)

def enroll_person(name, folder_path):
    embeddings = []
    for fname in os.listdir(folder_path):
        fpath = os.path.join(folder_path, fname)
        img = cv2.imread(fpath)
        if img is None:
            print(f"  Skipped (unreadable): {fname}")
            continue
        faces = app.get(img)
        if len(faces) == 0:
            print(f"  Skipped (no face): {fname}")
            continue
        embeddings.append(faces[0].embedding)
        print(f"  Used: {fname}")

    if not embeddings:
        print(f"No usable photos for {name}")
        return

    # average embeddings across all photos for a more robust identity vector
    known_faces[name] = np.mean(embeddings, axis=0)
    print(f"Enrolled: {name} ({len(embeddings)} photos)")

# auto-enroll everyone with a subfolder under enroll_photos/
for person_name in os.listdir(PHOTOS_DIR):
    person_folder = os.path.join(PHOTOS_DIR, person_name)
    if os.path.isdir(person_folder):
        print(f"Enrolling {person_name}...")
        enroll_person(person_name, person_folder)

with open(DB_PATH, "wb") as f:
    pickle.dump(known_faces, f)

print(f"\nSaved {len(known_faces)} people to {DB_PATH}")
