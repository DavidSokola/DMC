#!/usr/bin/env python3

import os
import time
import cv2
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import hailo
from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# For decoding DataMatrix
from pylibdmtx.pylibdmtx import decode as dmtx_decode

# Python's standard library
from queue import Queue, Empty
from threading import Thread

# This background thread will read ROIs from a queue and decode them
class DMCDecoderThread(Thread):
    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        self._stop_flag = False

    def run(self):
        while not self._stop_flag:
            try:
                # Wait for up to 0.5s for an ROI
                frame_idx, roi_img = self.roi_queue.get(timeout=0.5)
            except Empty:
                # No item available, loop around and check stop_flag
                continue

            # Perform DMC decode
            results = dmtx_decode(roi_img)
            if results:
                # For simplicity, just use first result
                dmc_str = results[0].data.decode("utf-8", errors="ignore")
                print(f"[DECODE THREAD] Frame {frame_idx}: Decoded DMC => '{dmc_str}'")
            else:
                print(f"[DECODE THREAD] Frame {frame_idx}: No DMC code found")

            self.roi_queue.task_done()

    def stop(self):
        self._stop_flag = True

# Custom callback class
class user_app_callback_class(app_callback_class):
    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        # For saving frames if needed
        timestamp_str = time.strftime("%y%m%d_%H%M%S")
        self.debug_dir = f"{timestamp_str}-detect"
        os.makedirs(self.debug_dir, exist_ok=True)

def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    frame_idx = user_data.get_count()

    # Extract the frame if user_data.use_frame
    gst_format, width, height = get_caps_from_pad(pad)
    frame_rgb = None
    if user_data.use_frame and gst_format and width and height:
        frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)
        # Convert for annotation if you want to draw bounding boxes
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = None

    # Retrieve detections
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[CALLBACK] Frame {frame_idx} - Found {len(detections)} detections.")

    # Quick bounding box logic
    for det in detections:
        label = det.get_label()
        conf = det.get_confidence()
        bbox = det.get_bbox()

        if label == "DMC" and conf >= 0.4 and frame_bgr is not None:
            # Convert normalized coords
            x0 = int(bbox.xmin() * width)
            y0 = int(bbox.ymin() * height)
            x1 = int(bbox.xmax() * width)
            y1 = int(bbox.ymax() * height)

            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)

            # Draw bounding box if you want
            cv2.rectangle(frame_bgr, (x0, y0), (x1, y1), (0, 255, 0), 2)

            # Copy ROI for decode
            roi_img = frame_bgr[y0:y1, x0:x1].copy()

            # **Push** into queue for background decoding
            user_data.roi_queue.put((frame_idx, roi_img))

    # If you want to display the annotated frame
    if frame_bgr is not None and user_data.use_frame:
        final_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        user_data.set_frame(final_rgb)

    return Gst.PadProbeReturn.OK

# Our custom pipeline app
class MyDetectionApp(GStreamerDetectionApp):
    # You can override pipeline creation if needed
    pass

if __name__ == "__main__":
    Gst.init(None)

    # 1) Create a queue and start the background decode thread
    roi_queue = Queue(maxsize=50)  # limit size so we don't run out of memory
    decoder_thread = DMCDecoderThread(roi_queue)
    decoder_thread.start()

    # 2) Create user data with reference to queue
    user_data = user_app_callback_class(roi_queue)

    # 3) Create and run the pipeline
    app = MyDetectionApp(app_callback, user_data)
    try:
        app.run()
    finally:
        # 4) Stop the decode thread
        decoder_thread.stop()
        decoder_thread.join()
        print("[MAIN] Exiting, decode thread stopped.")

