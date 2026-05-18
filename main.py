import cv2
from datetime import datetime
from motion_detector import MotionDetector
from video_processor import VideoProcessor
from config import *

# Colour map per object category (BGR for OpenCV)
LABEL_COLOURS = {
    "PERSON":  (0, 255, 0),    # Green
    "VEHICLE": (0, 165, 255),  # Orange
    "OBJECT":  (0, 255, 255),  # Yellow
}


def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("❌ Error: Could not open video file!")
        print(f"Make sure the file exists at: {VIDEO_PATH}")
        return

    detector = MotionDetector()
    detector.min_area = MIN_CONTOUR_AREA
    detector.threshold = THRESHOLD          # FIX: now properly passed in

    processor = VideoProcessor(output_dir=OUTPUT_DIR)

    motion_cooldown = 0
    print("🚀 Smart Security Camera Started")
    print("Press 'q' to quit")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        motion_detected, detected_boxes = detector.detect(frame)

        display_frame = frame.copy()

        # FIX: Draw colour-coded bounding boxes with classification labels
        for (x, y, w, h, label) in detected_boxes:
            colour = LABEL_COLOURS.get(label, (255, 255, 255))
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), colour, 3)
            cv2.putText(display_frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)

        # Count by category
        person_count  = sum(1 for b in detected_boxes if b[4] == "PERSON")
        vehicle_count = sum(1 for b in detected_boxes if b[4] == "VEHICLE")
        object_count  = sum(1 for b in detected_boxes if b[4] == "OBJECT")

        # Status overlay
        status_colour = (0, 0, 255) if motion_detected else (0, 255, 0)
        cv2.putText(display_frame,
                    f"People: {person_count}  Vehicles: {vehicle_count}  Objects: {object_count}",
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, status_colour, 3)

        cv2.putText(display_frame,
                    f"Motion: {'YES' if motion_detected else 'NO'}",
                    (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_colour, 2)

        # FIX: Timestamp on every frame (and therefore on saved clips)
        cv2.putText(display_frame,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    (10, display_frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Recording logic with cooldown
        if motion_detected:
            motion_cooldown = COOLDOWN_FRAMES
            if not processor.recording:
                processor.start_recording(frame.shape)

        if motion_cooldown > 0:
            processor.write_frame(display_frame)
            motion_cooldown -= 1
        elif processor.recording:
            processor.stop_recording()

        cv2.imshow('Smart Security Camera - People Detection', display_frame)

        if cv2.waitKey(25) & 0xFF == ord('q'):
            break

    # Cleanup
    if processor.recording:
        processor.stop_recording()
    cap.release()
    cv2.destroyAllWindows()
    print(f"✅ Done. {processor.get_clip_count()} clip(s) saved to '{OUTPUT_DIR}'.")


if __name__ == "__main__":
    main()