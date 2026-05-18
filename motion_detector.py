import cv2
import numpy as np


class MotionDetector:
    def __init__(self):
        self.prev_gray = None
        self.min_area = 1300          # Default value (updated from GUI)
        self.threshold = 20           # FIX: now configurable (was hardcoded)
        self.consecutive_motion = 0
        self.frame_count = 0

    def classify_object(self, box_w, box_h, area):
        """
        Classify detected motion contours as PERSON, VEHICLE, or OBJECT.

        Frame-differencing produces partial contours (torso, legs, etc.) so
        thresholds are intentionally relaxed for PERSON detection:
          - Vehicles: very wide (aspect > 2.0) AND large area (> 12000px)
          - Persons:  upright or roughly square (aspect < 1.6) with any
                      reasonable height (> 50px) — catches full-body,
                      torso-only, and side-on walking people
          - Object:   everything else
        """
        aspect_ratio = float(box_w) / box_h

        # VEHICLE: clearly wide and large
        if aspect_ratio > 2.0 and area > 12000:
            return "VEHICLE"

        # PERSON: upright or roughly square shape of any reasonable height
        if aspect_ratio < 1.6 and box_h > 50:
            return "PERSON"

        # OBJECT: leftover blobs
        return "OBJECT"

    def detect_people(self, frame):
        self.frame_count += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            return []

        # Frame Differencing
        frame_delta = cv2.absdiff(self.prev_gray, gray)

        # FIX: Use self.threshold instead of hardcoded 20
        thresh = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]

        # Morphological cleaning for better precision
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=2)
        thresh = cv2.erode(thresh, kernel, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detected_boxes = []
        h, w = frame.shape[:2]

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue

            epsilon = 0.018 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            x, y, box_w, box_h = cv2.boundingRect(approx)

            aspect_ratio = float(box_w) / box_h

            # Filters
            if box_h < 75:
                continue
            if not (0.35 < aspect_ratio < 2.3):
                continue
            if x > w - 200:
                continue
            if y > h - 90:
                continue
            if self.frame_count < 45 and y < 100:
                continue

            # FIX: Attach classification label to each detected box
            label = self.classify_object(box_w, box_h, area)
            detected_boxes.append((x, y, box_w, box_h, label))

        # Limit to maximum 3 detections, sorted by area (largest first)
        if len(detected_boxes) > 3:
            detected_boxes = sorted(
                detected_boxes, key=lambda b: b[2] * b[3], reverse=True
            )[:3]

        self.prev_gray = gray.copy()
        return detected_boxes

    def detect(self, frame):
        detected_boxes = self.detect_people(frame)

        current_count = len(detected_boxes)
        if current_count > 0:
            self.consecutive_motion += 1
        else:
            self.consecutive_motion = max(0, self.consecutive_motion - 2)

        motion_detected = self.consecutive_motion >= 3
        return motion_detected, detected_boxes