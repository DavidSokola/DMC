#!/usr/bin/env python3

import os
import time
import signal
import sys
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import hailo
from queue import Queue, Empty
from threading import Thread

from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# For decoding DataMatrix
from pylibdmtx.pylibdmtx import decode as dmtx_decode

# For GUI
import tkinter as tk

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
FRAMES_PER_DECODE = 30  # decode once every 30 frames => ~1 decode/sec at 30 FPS
QUEUE_MAXSIZE     = 50  # max ROI queue size to prevent memory balloon
DMC_CONF_THRESH   = 0.4 # only decode DMC bboxes above this confidence
# ------------------------------------------------------------------------------
# END CONFIG
# ------------------------------------------------------------------------------

# We'll store the latest decoded text in a global or shared object
last_decoded = ""  # the most recent DMC content

# ------------------------------------------------------------------------------
# 1) BACKGROUND DECODE THREAD
#    This thread pulls ROI images from a queue and runs pylibdmtx decode.
#    Instead of showing via OpenCV, we just update `last_decoded`.
# ------------------------------------------------------------------------------
class DMCDecoderThread(Thread):
    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        self._stop_flag = False

    def run(self):
        global last_decoded
        while not self._stop_flag:
            try:
                frame_idx, roi_img = self.roi_queue.get(timeout=0.5)
            except Empty:
                continue  # no item, loop again and check _stop_flag

            # Perform decode
            results = dmtx_decode(roi_img)
            if results:
                decoded_str = results[0].data.decode("utf-8", errors="ignore")
                print(f"[DECODE] Frame {frame_idx}: DMC => '{decoded_str}'")
                last_decoded = decoded_str
            else:
                print(f"[DECODE] Frame {frame_idx}: no DMC code found")

            self.roi_queue.task_done()

    def stop(self):
        self._stop_flag = True


# ------------------------------------------------------------------------------
# 2) CUSTOM USER APP CALLBACK CLASS
#    We'll store a reference to the ROI queue for async decoding.
# ------------------------------------------------------------------------------
class user_app_callback_class(app_callback_class):
    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue


# ------------------------------------------------------------------------------
# 3) GSTREAMER APP CALLBACK
#    - We parse detection metadata
#    - Every FRAMES_PER_DECODE frames, we retrieve raw frame, enqueue ROIs
# ------------------------------------------------------------------------------
def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    frame_idx = user_data.get_count()

    do_decode = (frame_idx % FRAMES_PER_DECODE == 0)

    # Retrieve detection metadata
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[CALLBACK] Frame {frame_idx} => {len(detections)} detections (decode={do_decode}).")

    if not do_decode:
        return Gst.PadProbeReturn.OK

    # If we do want to decode, we need the raw frame
    gst_format, width, height = get_caps_from_pad(pad)
    if not (user_data.use_frame and gst_format and width and height):
        return Gst.PadProbeReturn.OK

    frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)
    # BGR for decode
    # (Technically, pylibdmtx can decode in either color, but we do BGR for consistency)
    import cv2
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    for det in detections:
        label = det.get_label()
        conf  = det.get_confidence()

        if label == "DMC" and conf >= DMC_CONF_THRESH:
            bbox = det.get_bbox()
            x0 = int(bbox.xmin() * width)
            y0 = int(bbox.ymin() * height)
            x1 = int(bbox.xmax() * width)
            y1 = int(bbox.ymax() * height)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)

            roi_img = frame_bgr[y0:y1, x0:x1].copy()

            # Enqueue ROI for decode in background
            try:
                user_data.roi_queue.put_nowait((frame_idx, roi_img))
            except:
                print(f"[CALLBACK] ROI queue is full, skipping decode for Frame {frame_idx}.")

    return Gst.PadProbeReturn.OK


# ------------------------------------------------------------------------------
# 4) GSTREAMER DETECTION APP
# ------------------------------------------------------------------------------
class MyDetectionApp(GStreamerDetectionApp):
    pass

# ------------------------------------------------------------------------------
# 5) Pipeline-Thread Function
#    We'll run the GStreamer pipeline in a separate thread so we can keep
#    the Tkinter mainloop in the main thread.
# ------------------------------------------------------------------------------
def pipeline_thread_func(app):
    try:
        app.run()
    finally:
        print("[PIPELINE] Pipeline ended (thread).")


# ------------------------------------------------------------------------------
# 6) MAIN: Tkinter + Pipeline Thread + Decode Thread
# ------------------------------------------------------------------------------
decoder_thread = None
app = None
pipeline_thread = None

def main():
    global decoder_thread, app, pipeline_thread

    # 6a) Prepare GStreamer
    Gst.init(None)
    roi_queue = Queue(maxsize=QUEUE_MAXSIZE)
    decoder_thread = DMCDecoderThread(roi_queue)
    decoder_thread.start()

    user_data = user_app_callback_class(roi_queue)
    app = MyDetectionApp(app_callback, user_data)

    # 6b) Start pipeline in background
    pipeline_thread = threading.Thread(target=pipeline_thread_func, args=(app,))
    pipeline_thread.start()

    # 6c) Create a simple Tkinter UI to show last decoded code
    root = tk.Tk()
    root.title("Latest DMC Code")

    label = tk.Label(root, text="(No code yet)", font=("Helvetica", 16))
    label.pack(padx=20, pady=20)

    def update_label():
        """Poll the global 'last_decoded' every 200ms and update the label."""
        label.config(text=last_decoded if last_decoded else "(No code yet)")
        root.after(200, update_label)

    # Start the poll loop
    root.after(200, update_label)

    # 6d) Handle close event to stop everything gracefully
    def on_close():
        print("[TK] Window closed, stopping pipeline & decode thread.")
        if decoder_thread:
            decoder_thread.stop()
        if app:
            app.stop()  # attempts to kill pipeline
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_close)

    # 6e) Run the Tkinter main loop (blocking)
    root.mainloop()

    # If we ever exit that mainloop, we'll do cleanup
    print("[MAIN] Tkinter loop ended, cleaning up.")
    decoder_thread.stop()
    decoder_thread.join()

    pipeline_thread.join()
    print("[MAIN] Done.")


if __name__ == "__main__":
    main()
