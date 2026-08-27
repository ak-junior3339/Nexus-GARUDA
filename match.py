import pickle
import numpy as np


def load_known_faces(path="known_faces.pkl"):
    """Load the dictionary of {name: embedding} from disk."""
    with open(path, "rb") as f:
        known_faces = pickle.load(f)
    print("Loaded people:", list(known_faces.keys()))  # DEBUG
    return known_faces


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def identify(embedding, known_faces, threshold=0.5):
    """Compare an embedding against all known faces and return (name, similarity)."""
    best_name, best_sim = "Unknown", -1
    for name, known_emb in known_faces.items():
        sim = cosine_similarity(embedding, known_emb)
        print(f"  Comparing to {name}: {sim:.4f}")  # DEBUG
        if sim > best_sim:
            best_name, best_sim = name, sim
    return (best_name, best_sim) if best_sim >= threshold else ("Unknown", best_sim)