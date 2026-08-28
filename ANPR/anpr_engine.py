import cv2
import csv
import re
import torch
import easyocr
from ultralytics import YOLO


# ---------------------------------------------------------------------------
# 1. INITIALIZATION
# ---------------------------------------------------------------------------
# Load the custom-trained YOLOv8 plate-detection model.
print("Loading YOLOv8 custom weights and EasyOCR engine...")
model = YOLO("ANPR/Model/anprbest.pt")

# Automatically use GPU for OCR if one is available, so OCR does not become
# a CPU bottleneck while detection runs on GPU. If no GPU is available,
# this safely falls back to CPU.
USE_GPU = torch.cuda.is_available()
reader = easyocr.Reader(['en'], gpu=USE_GPU)
print(f"EasyOCR running on {'GPU' if USE_GPU else 'CPU'}")

# Minimum YOLO detection confidence to accept a box as a real plate.
DETECTION_CONF_THRESHOLD = 0.4

# Minimum EasyOCR confidence to accept the read text as reliable.
OCR_CONF_THRESHOLD = 0.4

# Process every Nth frame for speed. Detection/OCR only runs on these
# frames; skipped frames reuse the most recent detection so the overlay
# does not flicker on and off.
FRAME_SKIP = 3


# ---------------------------------------------------------------------------
# 2. TEXT CLEANING
# ---------------------------------------------------------------------------
def clean_plate(text):
    """
    Normalize raw OCR output into a plate-like string.
    - Uppercase everything.
    - Strip out ANY character that is not A-Z or 0-9. This removes
      whitespace, dashes, colons, periods, and also stray symbols like
      '|', ']', '[' that EasyOCR sometimes reads from the plate's
      border/frame rather than the actual characters.
    - Remove a leading 'IND' / 'IN' / 'I' watermark sometimes printed on
      Indian plates (the blue IND strip) that OCR occasionally picks up
      as part of the plate text.
    """
    text = text.upper().strip()
    text = re.sub(r'[^A-Z0-9]', '', text)
    text = re.sub(r'^(?:IND|IN|I)', '', text)
    return text


def is_same_plate(a, b):
    """
    Exact-match duplicate check: two reads are considered the same plate
    only if their cleaned text is identical. No fuzzy/partial matching,
    since the model's own detections are trusted directly now.
    """
    return a == b


# ---------------------------------------------------------------------------
# 2B. LENGTH FILTER + EXACT-DUPLICATE REMOVAL
# ---------------------------------------------------------------------------
# Minimum plate text length to be considered a real reading rather than
# OCR noise (a couple of stray characters). Anything longer than this
# is trusted as coming from the model/OCR being right, since strict
# regex validation was rejecting correct reads.
MIN_PLATE_LENGTH = 4


def merge_plate_reads(reads):
    """
    Takes a list of (frame, timestamp_sec, plate_text, ocr_confidence)
    tuples collected across the whole video and:
      1. Keeps only reads longer than MIN_PLATE_LENGTH characters.
      2. Removes exact duplicates, keeping the highest-confidence read
         for each distinct plate text.

    Returns a list of (frame, timestamp_sec, plate_text) for logging,
    one row per distinct plate text, in first-seen order.
    """
    best_by_text = {}   # plate_text -> (frame, ts, text, conf)
    order = []           # preserves first-seen order of each plate_text

    for frame, ts, text, conf in reads:
        if len(text) <= MIN_PLATE_LENGTH:
            continue

        if text not in best_by_text:
            best_by_text[text] = (frame, ts, text, conf)
            order.append(text)
        else:
            _, _, _, best_conf = best_by_text[text]
            if conf > best_conf:
                best_by_text[text] = (frame, ts, text, conf)

    return [(best_by_text[t][0], best_by_text[t][1], best_by_text[t][2]) for t in order]


# ---------------------------------------------------------------------------
# 3. PLATE CROP PREPROCESSING (improves OCR accuracy)
# ---------------------------------------------------------------------------
def preprocess_plate_crop(plate_crop):
    """
    Prepare a cropped plate image for OCR:
    - Upscale small crops. EasyOCR accuracy drops sharply on very small
      images (thin/far-away plates), so we upscale narrow crops to a
      minimum width before reading.
    - Convert to grayscale, which generally improves OCR consistency on
      plate text by removing color-channel noise.
    """
    if plate_crop.size == 0:
        return plate_crop

    h, w = plate_crop.shape[:2]
    min_width = 200
    if w < min_width and w > 0:
        scale = min_width / w
        plate_crop = cv2.resize(
            plate_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )

    gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
    return gray


# ---------------------------------------------------------------------------
# 4. RUN DETECTION + OCR ON A SINGLE FRAME
# ---------------------------------------------------------------------------
def detect_and_read_plate(frame):
    """
    Runs YOLO detection on the frame, picks the highest-confidence box,
    crops it, preprocesses it, and runs OCR on the crop.

    Returns:
        box (tuple or None): (x1, y1, x2, y2) of the best detected plate,
            or None if nothing was detected.
        display_str (str or None): text to overlay on the frame,
            or None if nothing was detected.
        plate_text (str or None): cleaned plate text (for logging),
            or None if OCR did not produce a confident read.
        ocr_confidence (float): confidence of the OCR read, 0.0 if none.
    """
    results = model.predict(frame, conf=DETECTION_CONF_THRESHOLD, verbose=False)
    boxes = results[0].boxes

    if len(boxes) == 0:
        return None, None, None, 0.0

    # Pick the box with the highest detection confidence rather than
    # assuming boxes[0] is the best one (YOLO does not guarantee order).
    best_idx = int(boxes.conf.argmax())
    best_box = boxes[best_idx]
    x1, y1, x2, y2 = map(int, best_box.xyxy[0])

    # Clamp coordinates to stay inside the frame boundaries.
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return None, None, None, 0.0

    plate_crop = frame[y1:y2, x1:x2]
    processed_crop = preprocess_plate_crop(plate_crop)

    ocr_results = reader.readtext(processed_crop)

    plate_text = None
    ocr_confidence = 0.0
    if ocr_results and ocr_results[0][2] >= OCR_CONF_THRESHOLD:
        raw_text = ocr_results[0][1]
        ocr_confidence = ocr_results[0][2]
        plate_text = clean_plate(raw_text)
        display_str = f"{plate_text} ({ocr_confidence:.2f})"
    else:
        # A plate was detected by YOLO but OCR was not confident enough
        # to trust the text, so just label it generically.
        display_str = "Plate Detected"

    return (x1, y1, x2, y2), display_str, plate_text, ocr_confidence


# ---------------------------------------------------------------------------
# 5. DRAW OVERLAY ON A FRAME
# ---------------------------------------------------------------------------
def draw_overlay(frame, box, display_str):
    """Draws the bounding box and label text onto the frame in place."""
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        frame,
        display_str,
        (x1, max(30, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )


# ---------------------------------------------------------------------------
# 6. MAIN VIDEO PROCESSING LOOP
# ---------------------------------------------------------------------------
def process_video(video_path, output_path, log_path=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

    # Collect every confident OCR read here as (frame, timestamp_sec,
    # plate_text, ocr_confidence). Nothing is filtered or deduplicated
    # during the loop, so a partial/half read is never lost. Merging
    # and picking the best version of each plate happens once, after
    # the whole video has been processed (see merge_plate_reads).
    all_reads = []

    frame_count = 0

    # Cache of the most recent detection, reused on skipped frames so the
    # overlay does not flicker on/off every FRAME_SKIP frames.
    last_box = None
    last_display_str = None

    print("Processing video stream... Press Ctrl+C in terminal to exit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1

        # On skipped frames, redraw the last known detection (if any)
        # instead of writing a bare frame, to avoid overlay flicker.
        if frame_count % FRAME_SKIP != 0:
            if last_box is not None:
                draw_overlay(frame, last_box, last_display_str)
            out.write(frame)
            continue

        box, display_str, plate_text, ocr_confidence = detect_and_read_plate(frame)

        if box is not None:
            draw_overlay(frame, box, display_str)
            last_box, last_display_str = box, display_str

            # Record every confident read, no filtering or dedup here.
            # Merging partial/duplicate reads into one "best" plate per
            # vehicle happens once, after the full video is processed.
            if plate_text:
                timestamp_sec = frame_count / fps
                all_reads.append((frame_count, timestamp_sec, plate_text, ocr_confidence))
        else:
            # Nothing detected this frame; clear the cache so skipped
            # frames stop drawing a stale box once the plate is gone.
            last_box, last_display_str = None, None

        out.write(frame)

        # Periodic progress update for long videos.
        if frame_count % 30 == 0:
            print(f"Processing frame {frame_count}/{total_frames}")

    cap.release()
    out.release()

    # Merge all collected reads into one row per distinct physical
    # plate, keeping the most complete/highest-confidence read for each,
    # then write the CSV once here (instead of row-by-row during the
    # loop). This is what guarantees "no redundancy, best possible
    # plate" in the final log.
    if log_path:
        merged = merge_plate_reads(all_reads)
        with open(log_path, "w", newline="") as log_file:
            csv_writer = csv.writer(log_file)
            csv_writer.writerow(["frame", "timestamp_sec", "plate_text"])
            for frame_num, ts, text in merged:
                csv_writer.writerow([frame_num, f"{ts:.2f}", text])

    print(f"Processing complete! Saved output video to: {output_path}")
    if log_path:
        print(f"Detection log saved to: {log_path}")


# ---------------------------------------------------------------------------
# 7. ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    process_video(
        "ANPR/input-videos/ANPR India Detection Demo - SmartCow - SmartCow (1080p, h264).mp4",
        "ANPR/output-videos/result.mp4",
        log_path="ANPR/output-videos/detections.csv",
    )