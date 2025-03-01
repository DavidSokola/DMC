# pipeline_code.py

import cv2
import time
from datetime import datetime

from gi.repository import Gst
import hailo
from hailo_apps_infra.hailo_rpi_common import get_caps_from_pad, get_numpy_from_buffer
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# Confidence threshold
DMC_CONF_THRESH = 0.8

def get_pipeline_string():
    """
    Return a GStreamer pipeline string that captures from the RPi camera (or HQ camera),
    at 640x480, 60 FPS, and passes raw frames to an appsink for further processing.
    Adjust as needed for your hardware setup (libcamerasrc vs v4l2src, etc.).
    """
    pipeline = (
        "libcamerasrc sensor-id=0 exposure-time=3000 ! "
        # 640 x 480 to 480 to 480
        "video/x-raw,width=480,height=480,framerate=60/1 ! "
        # Ensure we only produce 1 frame per second from the pipeline
        "videorate ! video/x-raw,framerate=1/1 ! "
        "queue max-size-buffers=1 leaky=downstream ! "
        "videoconvert ! "
        "appsink"
    )
    print(f"[DEBUG] GStreamer pipeline: {pipeline}")
    return pipeline

def app_callback(pad, info, user_data):
    """
    This is the GStreamer pad probe callback:
      - Takes the GStreamer buffer
      - Extracts Hailo detections for label 'DMC'
      - For each detection, cut out the bounding box from the frame
      - Push the ROI image onto the decode queue
    """
    buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK

    user_data.increment()  # track how many frames we've processed
    frame_idx = user_data.get_count()

    # Grab all the HAILO_DETECTION objects from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Check if we have a valid frame
    gst_format, width, height = get_caps_from_pad(pad)
    if not (user_data.use_frame and gst_format and width and height):
        return Gst.PadProbeReturn.OK

    # Convert GStreamer buffer to an RGB NumPy array, then BGR for OpenCV
    frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    # Loop over all detections
    for det in detections:
        label = det.get_label()
        conf = det.get_confidence()
        bbox = det.get_bbox()

        if label == "DMC" and conf >= DMC_CONF_THRESH:
            # Add some padding
            x0 = int(bbox.xmin() * width) - 10
            y0 = int(bbox.ymin() * height) - 10
            x1 = int(bbox.xmax() * width) + 10
            y1 = int(bbox.ymax() * height) + 10

            # Ensure ROI remains valid
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(width, x1)
            y1 = min(height, y1)

            # If bounding box is invalid (e.g., out of frame), skip
            if x1 <= x0 or y1 <= y0:
                continue

            # 1) Extract the ROI from the frame
            roi_img = frame_bgr[y0:y1, x0:x1].copy()

            # 2) Flip horizontally (if you truly need mirror flip)
            roi_img = cv2.flip(roi_img, 1)

            # 3) debug print
            print(f"[PIPELINE] Enqueuing ROI for frame={frame_idx}")
           
            # 4) Enqueue for decoding
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            user_data.roi_queue.put((frame_idx, roi_img, timestamp))

    return Gst.PadProbeReturn.OK

class MyDetectionApp(GStreamerDetectionApp):
    """
    A minimal class for running the GStreamer pipeline with a custom callback.
    This inherits from hailo_apps_infra.detection_pipeline.GStreamerDetectionApp,
    which sets up the GStreamer loop, bus, etc.
    """
    def __init__(self, callback, user_data):
        super().__init__(callback, user_data)
        print("[DEBUG] MyDetectionApp initialized.")
