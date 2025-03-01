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

# ------------------------------------------------------------------------------
# 1) Define a custom user callback class
# ------------------------------------------------------------------------------
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()

        # Create a unique debug directory based on the current time (yymmdd_hhmmss)
        timestamp_str = time.strftime("%y%m%d_%H%M%S")
        self.debug_dir = f"{timestamp_str}-detect"
        os.makedirs(self.debug_dir, exist_ok=True)

        self.save_whole_frame = True   # Toggle: True => save entire frame; False => only ROI
        self.save_counter = 0


# ------------------------------------------------------------------------------
# 2) The callback function that GStreamer calls for each buffer
# ------------------------------------------------------------------------------
def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Increment the user_data frame counter
    user_data.increment()
    frame_idx = user_data.get_count()

    # Retrieve caps/format from the pad
    gst_format, width, height = get_caps_from_pad(pad)

    # Grab the raw frame if requested (i.e., --use-frame)
    frame_rgb = None
    if user_data.use_frame and gst_format and width and height:
        frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)  # Likely RGB format

    # Extract detection metadata from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[DEBUG] Frame {frame_idx} - Found {len(detections)} detections.")

    # Loop over all detections
    for det in detections:
        label = det.get_label()
        confidence = det.get_confidence()
        bbox = det.get_bbox()

        # Only process “DMC” label with confidence >= 0.4 (example)
        if label == "DMC" and confidence >= 0.4:
            print(f"[DEBUG] Frame {frame_idx} - label:{label}, conf:{confidence:.2f}")

            if frame_rgb is not None:
                # IMPORTANT: use bbox.xmin() instead of bbox.xmin
                x0 = int(bbox.xmin() * width)
                y0 = int(bbox.ymin() * height)
                x1 = int(bbox.xmax() * width)
                y1 = int(bbox.ymax() * height)

                # Clip coords to valid frame region
                x0, y0 = max(0, x0), max(0, y0)
                x1, y1 = min(width, x1), min(height, y1)

                # Convert from RGB -> BGR for saving with OpenCV
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

                # Decide if we save the entire frame or just the bounding-box region
                if user_data.save_whole_frame:
                    out_img = frame_bgr
                else:
                    out_img = frame_bgr[y0:y1, x0:x1]

                # Construct a unique filename
                user_data.save_counter += 1
                timestamp = int(time.time())
                filename = f"frame_{frame_idx}_{label}_{user_data.save_counter}_{timestamp}.jpg"
                save_path = os.path.join(user_data.debug_dir, filename)

                # Save the image
                cv2.imwrite(save_path, out_img)
                print(f"[DEBUG] Wrote detection image to: {save_path}")

    return Gst.PadProbeReturn.OK


# ------------------------------------------------------------------------------
# 3) Main code that sets up and runs the pipeline
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize GStreamer
    Gst.init(None)

    # Instantiate the user callback class
    user_data = user_app_callback_class()

    # Create the detection pipeline application
    app = GStreamerDetectionApp(app_callback, user_data)

    # Run the pipeline (it will call our app_callback function on each buffer)
    app.run()