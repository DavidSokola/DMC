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

# pylibdmtx for decoding DataMatrix (DMC)
from pylibdmtx.pylibdmtx import decode as dmtx_decode

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        # Make a timestamp-based debug folder
        timestamp_str = time.strftime("%y%m%d_%H%M%S")
        self.debug_dir = f"{timestamp_str}-detect"
        os.makedirs(self.debug_dir, exist_ok=True)

        self.save_whole_frame = True   # If True, we annotate & save entire frame
        self.save_counter = 0

def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    frame_idx = user_data.get_count()

    gst_format, width, height = get_caps_from_pad(pad)

    # If we want frames, retrieve them
    frame_rgb = None
    if user_data.use_frame and gst_format and width and height:
        frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[DEBUG] Frame {frame_idx} - Found {len(detections)} detections.")

    if frame_rgb is not None:
        # Convert once to BGR so we can do our processing / drawing
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = None

    for det in detections:
        label = det.get_label()
        confidence = det.get_confidence()
        bbox = det.get_bbox()

        # Example: focus on label "DMC"
        if label == "DMC" and confidence >= 0.4:
            print(f"[DEBUG] Frame {frame_idx} - label:{label}, conf:{confidence:.2f}")
            if frame_bgr is not None:
                x0 = int(bbox.xmin() * width)
                y0 = int(bbox.ymin() * height)
                x1 = int(bbox.xmax() * width)
                y1 = int(bbox.ymax() * height)

                # Ensure valid ROI
                x0, y0 = max(0, x0), max(0, y0)
                x1, y1 = min(width, x1), min(height, y1)

                # Extract the bounding-box region to decode
                roi_img = frame_bgr[y0:y1, x0:x1]

                # Decode the DMC
                results = dmtx_decode(roi_img)
                decoded_str = ""
                if results:
                    # pylibdmtx may return multiple codes if found
                    # We'll just take the first or join them
                    decoded_str = results[0].data.decode("utf-8", errors="ignore")
                    print(f"[DEBUG] Decoded DMC => '{decoded_str}'")
                else:
                    print("[DEBUG] Could not decode DMC from bounding-box ROI.")

                # Draw a rectangle around the bounding box
                color = (0, 255, 0)  # Green
                cv2.rectangle(frame_bgr, (x0, y0), (x1, y1), color, 2)

                # Overlay the decoded text near the bounding box if we have it
                if decoded_str:
                    text_x, text_y = x0, max(y0 - 10, 0)
                    cv2.putText(frame_bgr, decoded_str, (text_x, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

                # Decide which image to save: bounding-box only or entire annotated frame
                if user_data.save_whole_frame:
                    # We'll save the entire annotated frame
                    out_img = frame_bgr
                else:
                    # Or if you prefer to only save the ROI, you can also
                    # put the text on roi_img before saving
                    out_img = roi_img
                    if decoded_str:
                        # Optionally overlay text on ROI itself
                        cv2.putText(out_img, decoded_str, (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

                # Construct a unique filename
                user_data.save_counter += 1
                timestamp = int(time.time())
                filename = f"frame_{frame_idx}_{label}_{user_data.save_counter}_{timestamp}.jpg"
                save_path = os.path.join(user_data.debug_dir, filename)

                # Save it
                cv2.imwrite(save_path, out_img)
                print(f"[DEBUG] Wrote detection image to: {save_path}")

    # If you want the pipeline to be able to display the annotated frame in a window:
    if frame_bgr is not None and user_data.use_frame:
        # Convert back to RGB for the pipeline (if needed)
        final_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        user_data.set_frame(final_rgb)

    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    Gst.init(None)
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
