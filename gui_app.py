import cv2
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
import threading
import time
import os
from PIL import Image, ImageTk
from motion_detector import MotionDetector
from video_processor import VideoProcessor


# Colour map per object category (BGR for OpenCV, hex for Tkinter)
LABEL_COLOURS_CV = {
    "PERSON": (0, 255, 0),
}
LABEL_COLOURS_HEX = {
    "PERSON": "#00ff00",
}

OUTPUT_DIR   = 'output_videos'
SCREENSHOT_DIR = r'E:\smart_security_cams\screenshots'
THUMB_W, THUMB_H = 140, 85   # thumbnail size in pixels


class DashboardGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Smart Security Camera - Control Center")
        self.root.geometry("1100x700")
        self.root.configure(bg="#0f172a")

        self.detector  = MotionDetector()
        self.processor = VideoProcessor(output_dir=OUTPUT_DIR)

        self.cap             = None
        self.running         = False
        self.paused          = False
        self.video_path      = None

        # Replay state — when replaying a saved clip
        self._replaying      = False
        self._replay_path    = None

        # Current display frame held for snapshot
        self._current_frame  = None

        # FPS tracking
        self._fps_frame_count = 0
        self._fps_start_time  = None

        # Session elapsed time
        self._session_start   = None

        # Recording duration
        self._rec_start       = None

        # Saved clip paths list (for thumbnail gallery)
        self._clip_paths      = []

        # Keep refs to thumbnail PhotoImages so GC doesn't kill them
        self._thumb_images    = []

        os.makedirs(OUTPUT_DIR,      exist_ok=True)
        os.makedirs(SCREENSHOT_DIR,  exist_ok=True)

        self.setup_dashboard()

    # ------------------------------------------------------------------
    # UI BUILD
    # ------------------------------------------------------------------
    def setup_dashboard(self):
        # ── Top Bar ───────────────────────────────────────────────────
        top_bar = tk.Frame(self.root, bg="#1e2937", height=60)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        tk.Label(top_bar, text="🛡️ SMART SECURITY CAMERA",
                 font=("Arial", 18, "bold"),
                 bg="#1e2937", fg="#60a5fa").pack(side="left", padx=20, pady=15)

        self.status_var = tk.StringVar(value="● SYSTEM READY")
        tk.Label(top_bar, textvariable=self.status_var,
                 font=("Arial", 11, "bold"),
                 bg="#1e2937", fg="#4ade80").pack(side="right", padx=20)

        # ── Main Area ─────────────────────────────────────────────────
        main_frame = tk.Frame(self.root, bg="#0f172a")
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)

        # ── Left Control Panel ────────────────────────────────────────
        left_panel = tk.LabelFrame(
            main_frame, text=" CONTROL PANEL ",
            font=("Arial", 12, "bold"),
            bg="#1e2937", fg="#bae6fd", padx=15, pady=15
        )
        left_panel.pack(side="left", fill="y", padx=(0, 15))

        tk.Button(left_panel, text="📂 Load Video",
                  command=self.load_video,
                  bg="#3b82f6", fg="white",
                  font=("Arial", 10, "bold"), width=20, height=2).pack(pady=8)

        self.play_btn = tk.Button(
            left_panel, text="▶️ Start Detection",
            command=self.toggle_play,
            bg="#22c55e", fg="black",
            font=("Arial", 10, "bold"), width=20, height=2
        )
        self.play_btn.pack(pady=8)

        tk.Button(left_panel, text="⏹️ Stop All",
                  command=self.stop_detection,
                  bg="#ef4444", fg="white",
                  font=("Arial", 10, "bold"), width=20, height=2).pack(pady=8)

        # ── Snapshot button ───────────────────────────────────────────
        tk.Button(left_panel, text="📸 Save Snapshot",
                  command=self.save_snapshot,
                  bg="#a855f7", fg="white",
                  font=("Arial", 10, "bold"), width=20, height=2).pack(pady=8)

        self.snapshot_label = tk.Label(
            left_panel, text="", bg="#1e2937", fg="#c4b5fd",
            font=("Arial", 8), wraplength=200, justify="left"
        )
        self.snapshot_label.pack(anchor="w", pady=(0, 6))

        # ── Live Stats ────────────────────────────────────────────────
        tk.Label(left_panel, text="Live Stats",
                 bg="#1e2937", fg="#bae6fd",
                 font=("Arial", 11, "bold")).pack(pady=(16, 6), anchor="w")

        self.fps_var = tk.StringVar(value="FPS         --")
        tk.Label(left_panel, textvariable=self.fps_var,
                 bg="#1e2937", fg="#e0f2fe",
                 font=("Courier", 10)).pack(anchor="w", pady=2)

        self.elapsed_var = tk.StringVar(value="Elapsed     --")
        tk.Label(left_panel, textvariable=self.elapsed_var,
                 bg="#1e2937", fg="#e0f2fe",
                 font=("Courier", 10)).pack(anchor="w", pady=2)

        self.rec_dur_var = tk.StringVar(value="Rec time    --")
        tk.Label(left_panel, textvariable=self.rec_dur_var,
                 bg="#1e2937", fg="#f87171",
                 font=("Courier", 10)).pack(anchor="w", pady=2)

        # ── Detection Legend ──────────────────────────────────────────
        tk.Label(left_panel, text="Detection Legend",
                 bg="#1e2937", fg="#bae6fd",
                 font=("Arial", 10, "bold")).pack(pady=(20, 4), anchor="w")
        for lbl, hexcol in LABEL_COLOURS_HEX.items():
            tk.Label(left_panel, text=f"■  {lbl}",
                     bg="#1e2937", fg=hexcol,
                     font=("Arial", 9, "bold")).pack(anchor="w")

        # ── Right area ────────────────────────────────────────────────
        right_panel = tk.Frame(main_frame, bg="#0f172a")
        right_panel.pack(side="right", fill="both", expand=True)

        # Fixed-height video feed — does NOT expand
        self.video_label = tk.Label(right_panel, bg="#1e2937",
                                    relief="solid", bd=3,
                                    width=760, height=400)
        self.video_label.pack(fill="x", padx=10, pady=(10, 5))

        # ── Clip Gallery ──────────────────────────────────────────────
        gallery_frame = tk.LabelFrame(
            right_panel, text=" 🎬 INCIDENT CLIPS  (click thumbnail to replay) ",
            font=("Arial", 10, "bold"),
            bg="#1e2937", fg="#fbbf24", padx=6, pady=6
        )
        gallery_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Horizontal scrollable canvas for thumbnails
        self._gallery_canvas = tk.Canvas(
            gallery_frame, height=THUMB_H + 55,
            bg="#0f172a", highlightthickness=0
        )
        h_scroll = tk.Scrollbar(gallery_frame, orient=tk.HORIZONTAL,
                                 command=self._gallery_canvas.xview)
        self._gallery_canvas.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side="bottom", fill="x")
        self._gallery_canvas.pack(side="left", fill="both", expand=True)

        # Inner frame that holds the thumbnail widgets
        self._thumb_frame = tk.Frame(self._gallery_canvas, bg="#0f172a")
        self._gallery_canvas.create_window((0, 0), window=self._thumb_frame,
                                           anchor="nw")
        self._thumb_frame.bind(
            "<Configure>",
            lambda e: self._gallery_canvas.configure(
                scrollregion=self._gallery_canvas.bbox("all")
            )
        )

        self.clip_count_var = tk.StringVar(value="Clips saved: 0")
        tk.Label(gallery_frame, textvariable=self.clip_count_var,
                 bg="#1e2937", fg="#94a3b8",
                 font=("Arial", 8)).pack(side="right", anchor="se", pady=2)

        # Footer
        tk.Label(
            self.root,
            text="Green = Person  |  Click thumbnail to replay  |  ✕ to delete clip",
            bg="#0f172a", fg="#94a3b8", font=("Arial", 9)
        ).pack(pady=6)

    # ------------------------------------------------------------------
    # THUMBNAIL GALLERY
    # ------------------------------------------------------------------
    def _extract_thumbnail(self, clip_path):
        """Read the first frame of a clip and return a resized PIL Image."""
        cap = cv2.VideoCapture(clip_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            # Return a blank placeholder if the frame can't be read
            return Image.new("RGB", (THUMB_W, THUMB_H), color=(30, 41, 59))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb).resize((THUMB_W, THUMB_H))

    def _add_thumbnail(self, clip_path):
        """Add a thumbnail card to the gallery for the given clip path."""
        def _build():
            idx       = len(self._clip_paths) - 1
            thumb_img = self._extract_thumbnail(clip_path)
            tk_thumb  = ImageTk.PhotoImage(thumb_img)
            self._thumb_images.append(tk_thumb)   # prevent GC

            card = tk.Frame(self._thumb_frame, bg="#1e2937",
                            relief="solid", bd=1)
            card.pack(side="left", padx=6, pady=4)

            # Top row: delete button aligned right
            top_row = tk.Frame(card, bg="#1e2937")
            top_row.pack(fill="x")
            tk.Button(
                top_row, text="✕", command=lambda c=card, p=clip_path: self.delete_clip(c, p),
                bg="#ef4444", fg="white", font=("Arial", 7, "bold"),
                width=2, height=1, relief="flat", cursor="hand2"
            ).pack(side="right", padx=2, pady=1)

            # Thumbnail image — click to replay
            btn = tk.Label(card, image=tk_thumb, bg="#1e2937", cursor="hand2")
            btn.pack()
            btn.bind("<Button-1>", lambda e, p=clip_path: self.replay_clip(p))

            # Clip label underneath thumbnail
            name = os.path.basename(clip_path)
            try:
                parts    = name.replace(".avi", "").split("_")
                time_str = f"{parts[2][:2]}:{parts[2][2:4]}:{parts[2][4:]}"
                short    = f"#{idx+1}  {time_str}"
            except Exception:
                short = f"#{idx+1}"

            tk.Label(card, text=short, bg="#1e2937", fg="#94a3b8",
                     font=("Arial", 7)).pack(pady=(2, 4))

            # Scroll to show the latest thumbnail
            self._gallery_canvas.update_idletasks()
            self._gallery_canvas.xview_moveto(1.0)

            self.clip_count_var.set(f"Clips saved: {len(self._clip_paths)}")

        self.root.after(0, _build)

    def delete_clip(self, card_widget, clip_path):
        """Remove a clip from the gallery and delete the file from disk."""
        if self._replay_path == clip_path and self._replaying:
            self._replaying = False
            time.sleep(0.1)
            self.status_var.set("● SYSTEM READY")

        # Remove from disk
        try:
            if os.path.exists(clip_path):
                os.remove(clip_path)
                print(f"🗑️ Deleted: {clip_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not delete file:\n{e}")
            return

        # Remove from internal list
        if clip_path in self._clip_paths:
            self._clip_paths.remove(clip_path)

        # Destroy the card widget from the gallery
        card_widget.destroy()

        # Update scrollregion and counter
        self._gallery_canvas.update_idletasks()
        self._gallery_canvas.configure(
            scrollregion=self._gallery_canvas.bbox("all")
        )
        self.clip_count_var.set(f"Clips saved: {len(self._clip_paths)}")

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def load_video(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video Files", "*.mp4 *.avi *.mov")]
        )
        if not path:
            return
        self.video_path = path
        self.status_var.set("● VIDEO LOADED")

        # Show first frame as preview in the video label
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
        cap.release()
        if ret:
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img    = Image.fromarray(rgb).resize((760, 400))
            tk_img = ImageTk.PhotoImage(img)
            self.video_label.config(image=tk_img)
            self.video_label.image = tk_img

    def toggle_play(self):
        if not self.video_path:
            messagebox.showwarning("Warning", "Please load a video first!")
            return

        # If currently replaying, stop replay first
        if self._replaying:
            self._replaying = False
            time.sleep(0.1)

        if not self.running:
            self.running          = True
            self.paused           = False
            self._fps_frame_count = 0
            self._fps_start_time  = time.time()
            self._session_start   = time.time()
            self.play_btn.config(text="⏸️ Pause", bg="#eab308")
            self.status_var.set("● DETECTING")
            threading.Thread(target=self.process_video, daemon=True).start()
        else:
            self.paused = not self.paused
            if self.paused:
                self.play_btn.config(text="▶️ Resume", bg="#22c55e")
                self.status_var.set("● PAUSED")
            else:
                self.play_btn.config(text="⏸️ Pause", bg="#eab308")
                self.status_var.set("● DETECTING")

    def save_snapshot(self):
        """Save the current annotated display frame as a compressed JPEG screenshot."""
        if self._current_frame is None:
            messagebox.showwarning("Warning", "No frame available. Start detection first.")
            return
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = os.path.join(SCREENSHOT_DIR, f"screenshot_{ts}.jpg")
        self.processor.save_snapshot_jpeg(self._current_frame, filename, quality=85)
        full_path = os.path.abspath(filename)
        size_kb   = round(os.path.getsize(full_path) / 1024, 1)
        self.snapshot_label.config(
            text=f"✅ {os.path.basename(filename)}  ({size_kb} KB)\n{full_path}"
        )
        print(f"📸 Screenshot saved: {full_path}")

    def replay_clip(self, clip_path):
        """Play a saved incident clip inside the main video panel."""
        if self.running:
            messagebox.showinfo(
                "Info",
                "Stop detection first before replaying a clip."
            )
            return
        if self._replaying:
            self._replaying = False
            time.sleep(0.15)
        self._replay_path = clip_path
        self._replaying   = True
        self.status_var.set(f"▶ REPLAYING  {os.path.basename(clip_path)}")
        threading.Thread(target=self._replay_worker, daemon=True).start()

    def _replay_worker(self):
        """Background thread: stream a saved clip into the video label."""
        cap = cv2.VideoCapture(self._replay_path)
        while self._replaying and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                # Loop back to start
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img    = Image.fromarray(rgb).resize((760, 400))
            tk_img = ImageTk.PhotoImage(img)
            self.video_label.config(image=tk_img)
            self.video_label.image = tk_img
            time.sleep(0.04)   # ~25 fps
        cap.release()
        self._replaying = False
        self.root.after(0, self.status_var.set, "● SYSTEM READY")

    def _update_stats(self):
        """Recalculate FPS, elapsed time, recording duration and push to labels."""
        now = time.time()

        elapsed_fps = now - self._fps_start_time
        if elapsed_fps >= 1.0:
            fps = self._fps_frame_count / elapsed_fps
            self._fps_frame_count = 0
            self._fps_start_time  = now
            self.root.after(0, self.fps_var.set, f"FPS         {fps:.1f}")

        if self._session_start:
            total = int(now - self._session_start)
            m, s  = divmod(total, 60)
            self.root.after(0, self.elapsed_var.set, f"Elapsed     {m:02d}:{s:02d}")

        if self.processor.recording and self._rec_start:
            rdur   = int(now - self._rec_start)
            rm, rs = divmod(rdur, 60)
            self.root.after(0, self.rec_dur_var.set, f"Rec time  ⏺ {rm:02d}:{rs:02d}")
        else:
            self.root.after(0, self.rec_dur_var.set, "Rec time    --")

    # ------------------------------------------------------------------
    # MAIN PROCESSING LOOP
    # ------------------------------------------------------------------
    def process_video(self):
        self.cap        = cv2.VideoCapture(self.video_path)
        last_clip_count = 0

        while self.running and self.cap.isOpened():
            if self.paused:
                time.sleep(0.05)
                continue

            ret, frame = self.cap.read()
            if not ret:
                break

            motion_detected, detected_boxes = self.detector.detect(frame)
            display_frame = frame.copy()

            for (x, y, w, h, label) in detected_boxes:
                if label != "PERSON":
                    continue
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 4)
                cv2.putText(display_frame, "PERSON", (x, max(y - 15, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)

            person_count = sum(1 for b in detected_boxes if b[4] == "PERSON")
            motion_text  = "MOTION DETECTED" if person_count > 0 else ""
            cv2.putText(display_frame,
                        f"PEOPLE: {person_count}",
                        (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
            if motion_text:
                cv2.putText(display_frame, motion_text,
                            (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 3)

            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(display_frame, ts,
                        (10, display_frame.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            self._current_frame = display_frame.copy()

            # Recording logic
            if motion_detected:
                if not self.processor.recording:
                    self.processor.start_recording(frame.shape)
                    self._rec_start = time.time()
                self.processor.write_frame(display_frame)
            elif self.processor.recording:
                self.processor.stop_recording()
                self._rec_start = None
                if self.processor.get_clip_count() > last_clip_count:
                    last_clip_count = self.processor.get_clip_count()
                    # Add to gallery
                    self._clip_paths.append(self.processor.current_clip)
                    self._add_thumbnail(self.processor.current_clip)

            self._fps_frame_count += 1
            self._update_stats()

            rgb    = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            img    = Image.fromarray(rgb).resize((760, 400))
            tk_img = ImageTk.PhotoImage(img)
            self.video_label.config(image=tk_img)
            self.video_label.image = tk_img

            if cv2.waitKey(25) & 0xFF == ord('q'):
                break

        self.stop_detection()

    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------
    def stop_detection(self):
        self.running    = False
        self.paused     = False
        self._replaying = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        if self.processor.recording:
            self.processor.stop_recording()
            if self.processor.current_clip not in self._clip_paths:
                self._clip_paths.append(self.processor.current_clip)
                self._add_thumbnail(self.processor.current_clip)
        self._rec_start = None
        if getattr(self, '_closing', False):
            return
        self.root.after(0, self.fps_var.set,     "FPS         --")
        self.root.after(0, self.elapsed_var.set, "Elapsed     --")
        self.root.after(0, self.rec_dur_var.set, "Rec time    --")
        self.play_btn.config(text="▶️ Start Detection", bg="#22c55e")
        self.status_var.set("● SYSTEM STOPPED")

    def _on_close(self):
        self.running    = False
        self.paused     = False
        self._replaying = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        if self.processor.recording:
            self.processor.stop_recording()
        self._closing = True
        self.root.after(100, self.root.destroy)

    def run(self):
        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()


if __name__ == "__main__":
    app = DashboardGUI()
    app.run()