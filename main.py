import cv2, pickle, numpy as np
from face_utils import get_app

app = get_app()

with open("known_faces.pkl", "rb") as f:
    known_faces = pickle.load(f)

print("Loaded people:", list(known_faces.keys()))  # DEBUG

def identify(embedding, threshold=0.5):
    best_name, best_sim = "Unknown", -1
    for name, known_emb in known_faces.items():
        sim = np.dot(embedding, known_emb) / (np.linalg.norm(embedding) * np.linalg.norm(known_emb))
        print(f"  Comparing to {name}: {sim:.4f}")  # DEBUG
        if sim > best_sim:
            best_name, best_sim = name, sim
    return (best_name, best_sim) if best_sim >= threshold else ("Unknown", best_sim)

cap = cv2.VideoCapture(0)
while True:
    ret, frame = cap.read()
    if not ret:
        break
    faces = app.get(frame)
    for face in faces:
        box = face.bbox.astype(int)
        name, sim = identify(face.embedding)
        cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        cv2.putText(frame, f"{name} ({sim:.2f})", (box[0], box[1]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("Face ID", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()