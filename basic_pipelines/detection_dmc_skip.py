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

# pylibdmtx for decoding DMC
from pylibdmtx.pylibdmtx import decode as dmtx_decode

# We’ll decode once every 30 frames => ~1 decode/second if input is ~30 FPS
FRAMES_PER_DECODE = 3

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        # Create a timestamp-based output folder
        timestamp_str = time.strftime("%y%m%d_%H%M%S")
        self.debug_dir = f"{timestamp_str}-detect"
        os.makedirs(self.debug_dir, exist_ok=True)

        # Toggle whether to save the entire frame or just ROI
        self.save_whole_frame = True
        self.save_counter = 0

def app_callback(pad, info, user_data):
    """GStreamer callback: draws bounding boxes for each detection every frame,
    but only decodes the DMC content for every Nth frame."""
    buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    frame_idx = user_data.get_count()

    # Retrieve caps and resolution
    gst_format, width, height = get_caps_from_pad(pad)

    # Attempt to get a raw frame if use_frame is True
    # so we can display and/or annotate it
    frame_rgb = None
    if user_data.use_frame and gst_format and width and height:
        frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)  # Typically RGB
        # Convert once to BGR for annotation
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = None

    # Extract detection metadata
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[DEBUG] Frame {frame_idx} - Found {len(detections)} detections.")

    # We'll annotate bounding boxes for all frames (optional)
    # But decode DMC content only on certain frames
    do_decode_this_frame = (frame_idx % FRAMES_PER_DECODE == 0)

    # We’ll store decoded results or skip
    for det in detections:
        label = det.get_label()
        confidence = det.get_confidence()
        bbox = det.get_bbox()

        # If you like, skip low confidence
        if confidence < 0.4:
            continue

        if frame_bgr is not None:
            # Convert normalized coords [0..1] to pixel coords
            x0 = int(bbox.xmin() * width)
            y0 = int(bbox.ymin() * height)
            x1 = int(bbox.xmax() * width)
            y1 = int(bbox.ymax() * height)

            # Clip
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)

            # Draw bounding box every frame
            color = (0, 255, 0)  # green
            cv2.rectangle(frame_bgr, (x0, y0), (x1, y1), color, 2)

            # If label == "DMC" and it's time to decode
            if label == "DMC" and do_decode_this_frame:
                # Extract the bounding-box ROI for decoding
                roi_img = frame_bgr[y0:y1, x0:x1]
                results = dmtx_decode(roi_img)
                if results:
                    # For simplicity, use the first decode result
                    decoded_str = results[0].data.decode("utf-8", errors="ignore")
                    print(f"[DEBUG] Frame {frame_idx} DECODING: '{decoded_str}'")
                    # Optionally overlay text near bounding box
                    cv2.putText(frame_bgr, decoded_str, (x0, max(y0 - 5, 0)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    print(f"[DEBUG] Frame {frame_idx} - Could NOT decode DMC.")
    
    # If it’s a decode frame, let’s optionally save an image
    if do_decode_this_frame and frame_bgr is not None:
        user_data.save_counter += 1
        timestamp = int(time.time())
        filename = f"frame_{frame_idx}_decode_{user_data.save_counter}_{timestamp}.jpg"
        save_path = os.path.join(user_data.debug_dir, filename)

        # If you only want to save bounding-box ROI, you can do that here
        # but in this example we save the entire annotated frame:
        cv2.imwrite(save_path, frame_bgr)
        print(f"[DEBUG] Wrote debug image: {save_path}")

    # If you want to display frames at full FPS in a window or GStreamer overlay,
    # convert back to RGB and set in user_data for pipeline to display
    if frame_bgr is not None and user_data.use_frame:
        final_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        user_data.set_frame(final_rgb)

    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    Gst.init(None)
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
