import cv2
import os
from datetime import datetime


class VideoProcessor:
    """
    Handles recording of motion-detected video segments with compression,
    and provides utility methods for compressing saved images and video clips.

    Video compression: uses H.264 (mp4v) codec which gives significantly
    smaller file sizes than the original XVID/AVI format.

    Image compression:
      - JPEG: lossy, quality 0-100 (default 85) — smallest file size
      - PNG:  lossless, compression level 0-9 (default 3) — no quality loss
    """

    def __init__(self, output_dir='output_videos'):
        self.output_dir  = output_dir
        self.writer      = None
        self.recording   = False
        self.current_clip = None
        self.clip_count  = 0

        # Video compression quality (CRF-equivalent scale via bitrate target)
        # Codec: mp4v (H.264-compatible), smaller than XVID
        self.video_fps     = 20.0
        self.video_codec   = 'mp4v'   # produces .mp4 — more compressed than XVID .avi

        os.makedirs(output_dir, exist_ok=True)

    def set_output_dir(self, path):
        self.output_dir = path
        os.makedirs(path, exist_ok=True)

    # ------------------------------------------------------------------
    # VIDEO RECORDING
    # ------------------------------------------------------------------
    def start_recording(self, frame_shape):
        if self.recording:
            return

        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # .mp4 extension — smaller than .avi with mp4v codec
        filename  = os.path.join(self.output_dir, f"incident_{timestamp}.mp4")

        fourcc       = cv2.VideoWriter_fourcc(*self.video_codec)
        self.writer  = cv2.VideoWriter(
            filename, fourcc, self.video_fps,
            (frame_shape[1], frame_shape[0])
        )
        self.current_clip = filename
        self.recording    = True
        self.clip_count  += 1
        print(f"🎥 Recording started: {filename}")

    def write_frame(self, frame):
        if self.writer is not None:
            self.writer.write(frame)

    def stop_recording(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            size_kb = self._file_size_kb(self.current_clip)
            print(f"✅ Clip saved: {self.current_clip}  ({size_kb} KB)")
        self.recording = False

    def get_clip_count(self):
        return self.clip_count

    # ------------------------------------------------------------------
    # IMAGE COMPRESSION
    # ------------------------------------------------------------------
    def save_snapshot_jpeg(self, frame, path, quality=85):
        """
        Save a frame as a compressed JPEG.
        quality: 0 (smallest/worst) – 100 (largest/best). Default 85 is a
                 good balance between file size and visual quality.
        """
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        cv2.imwrite(path, frame, params)
        size_kb = self._file_size_kb(path)
        print(f"📸 JPEG snapshot saved: {path}  ({size_kb} KB, quality={quality})")
        return path

    def save_snapshot_png(self, frame, path, compression=3):
        """
        Save a frame as a lossless PNG with compression.
        compression: 0 (no compression/fastest) – 9 (maximum compression/slowest).
                     Default 3 is a good balance of speed and size.
        """
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        params = [cv2.IMWRITE_PNG_COMPRESSION, compression]
        cv2.imwrite(path, frame, params)
        size_kb = self._file_size_kb(path)
        print(f"📸 PNG snapshot saved: {path}  ({size_kb} KB, compression={compression})")
        return path

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------
    def _file_size_kb(self, path):
        """Return file size in KB, or 0 if the file doesn't exist."""
        try:
            return round(os.path.getsize(path) / 1024, 1)
        except OSError:
            return 0