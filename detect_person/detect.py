import cv2
import numpy as np
import time
from collections import deque

import requests
from pathlib import Path

from config import (
    ROOM_ID,
    OCCUPANCY_API_URL,
    API_KEY,
    HEARTBEAT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)

# ==========================================================
# CONFIG
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
PROTOTXT = str(BASE_DIR / "deploy.prototxt")
MODEL = str(BASE_DIR / "mobilenet_iter_73000.caffemodel")

CAMERA_INDEX = 0

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Chỉ chạy AI mỗi N frame
SKIP_FRAMES = 5

# Ngưỡng confidence
CONFIDENCE_THRESHOLD = 0.5

# Lọc kết quả
HISTORY_LENGTH = 10
MIN_POSITIVE = 3

SHOW_WINDOW = True

# ==========================================================
# CLASSES
# ==========================================================

CLASSES = [
    "background",
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor"
]

# ==========================================================
# OCCUPANCY API
# ==========================================================

if not ROOM_ID or ROOM_ID == "YOUR_ROOM_ID":
    raise RuntimeError(
        "Chưa cấu hình ROOM_ID. Hãy sửa detect_person/config.py "
        "hoặc đặt biến môi trường DETECT_ROOM_ID."
    )


def send_occupancy(occupied, person_count=0, confidence=None):
    """Gửi trạng thái phòng lên Smart Rental API."""
    payload = {
        "room_id": ROOM_ID,
        "occupied": bool(occupied),
        "person_count": int(person_count),
        "source": "computer_vision",
    }

    if confidence is not None:
        payload["confidence"] = float(confidence)

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-Occupancy-API-Key"] = API_KEY

    try:
        response = requests.post(
            OCCUPANCY_API_URL,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.ok:
            print(
                f"[API] room={ROOM_ID} "
                f"occupied={bool(occupied)} "
                f"person_count={int(person_count)}"
            )
            return True

        print(
            f"[API ERROR] HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    except requests.RequestException as exc:
        print(f"[API ERROR] Cannot update occupancy: {exc}")

    return False


# ==========================================================
# LOAD MODEL
# ==========================================================

print("Loading MobileNet SSD...")

net = cv2.dnn.readNetFromCaffe(
    PROTOTXT,
    MODEL
)

print("Model loaded.")

# ==========================================================
# CAMERA
# ==========================================================

cap = cv2.VideoCapture(CAMERA_INDEX)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    raise RuntimeError("Cannot open camera")

# ==========================================================
# HISTORY
# ==========================================================

history = deque(maxlen=HISTORY_LENGTH)

frame_count = 0

last_presence = False
last_reported_presence = None
last_reported_at = 0.0
last_detected_person_count = 0
last_detected_max_confidence = None

fps = 0
fps_timer = time.time()

print(f"Monitoring room: {ROOM_ID}")
print(f"Sending occupancy to: {OCCUPANCY_API_URL}")
print("Start detection...\n")

# ==========================================================
# LOOP
# ==========================================================

try:
    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame_count += 1

        detected_person_count = 0
        detected_max_confidence = None

        # ------------------------------------------------------
        # Chỉ detect mỗi N frame
        # ------------------------------------------------------

        if frame_count % SKIP_FRAMES == 0:

            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame, (300, 300)),
                scalefactor=0.007843,
                size=(300, 300),
                mean=127.5
            )

            net.setInput(blob)

            detections = net.forward()

            h, w = frame.shape[:2]

            for i in range(detections.shape[2]):

                confidence = float(detections[0, 0, i, 2])

                if confidence < CONFIDENCE_THRESHOLD:
                    continue

                idx = int(detections[0, 0, i, 1])

                if idx < 0 or idx >= len(CLASSES) or CLASSES[idx] != "person":
                    continue

                detected_person_count += 1
                detected_max_confidence = max(
                    detected_max_confidence or 0.0,
                    confidence,
                )

                if SHOW_WINDOW:

                    box = detections[0, 0, i, 3:7] * np.array(
                        [w, h, w, h]
                    )

                    startX, startY, endX, endY = box.astype("int")

                    cv2.rectangle(
                        frame,
                        (startX, startY),
                        (endX, endY),
                        (0, 255, 0),
                        2
                    )

                    cv2.putText(
                        frame,
                        f"Person {confidence:.2f}",
                        (startX, max(20, startY - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2
                    )

            last_detected_person_count = detected_person_count
            last_detected_max_confidence = detected_max_confidence
            history.append(detected_person_count > 0)

        # ------------------------------------------------------
        # FILTER
        # ------------------------------------------------------

        presence = sum(history) >= MIN_POSITIVE

        # ------------------------------------------------------
        # Gửi API khi trạng thái thay đổi hoặc heartbeat đến hạn.
        # Chỉ thay đổi dữ liệu server khi detection đã ổn định.
        # ------------------------------------------------------

        now = time.time()

        if presence != last_presence:
            last_presence = presence
            print("1" if presence else "0")

        heartbeat_due = (
            last_reported_presence is None
            or presence != last_reported_presence
            or now - last_reported_at >= HEARTBEAT_SECONDS
        )

        if heartbeat_due:
            if send_occupancy(
                occupied=presence,
                person_count=last_detected_person_count if presence else 0,
                confidence=last_detected_max_confidence,
            ):
                last_reported_presence = presence
                last_reported_at = now

        # ------------------------------------------------------
        # FPS
        # ------------------------------------------------------

        elapsed = now - fps_timer
        if elapsed > 0:
            fps = 1.0 / elapsed

        fps_timer = now

        # ------------------------------------------------------
        # DISPLAY
        # ------------------------------------------------------

        if SHOW_WINDOW:

            color = (0, 255, 0) if presence else (0, 0, 255)

            text = "PERSON DETECTED" if presence else "NO PERSON"

            cv2.putText(
                frame,
                text,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                color,
                2
            )

            cv2.putText(
                frame,
                f"Room: {ROOM_ID}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"FPS: {fps:.1f}",
                (20, 115),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 0),
                2
            )

            cv2.imshow("Person Detection", frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

finally:
    cap.release()
    cv2.destroyAllWindows()

print("Exit.")
