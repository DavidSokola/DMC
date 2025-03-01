# pipeline_code.py

import cv2
import hailo
from gi.repository import Gst
from hailo_apps_infra.hailo_rpi_common import get_caps_from_pad, get_numpy_from_buffer
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# Some config constants can be here or in a shared config
FRAMES_PER_DECODE = 30
DMC_CONF_THRESH   = 0.4


def app_callback(pad, info, user_data):
    """GStreamer callback: parse detection metadata, optionally decode a frame every N frames."""
    buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    frame_idx = user_data.get_count()

    do_decode = (frame_idx % FRAMES_PER_DECODE == 0)

    # Retrieve detection metadata from Hailo buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    print(f"[DEBUG] Frame {frame_idx} => {len(detections)} detections (decode={do_decode}).")

    if not do_decode:
        return Gst.PadProbeReturn.OK

    # We only read the raw frame if we plan to decode this frame
    gst_format, width, height = get_caps_from_pad(pad)
    if not (user_data.use_frame and gst_format and width and height):
        return Gst.PadProbeReturn.OK

    frame_rgb = get_numpy_from_buffer(buffer, gst_format, width, height)
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    for det in detections:
        label = det.get_label()
        conf  = det.get_confidence()
        bbox  = det.get_bbox()

        if label == "DMC" and conf >= DMC_CONF_THRESH:
            x0 = int(bbox.xmin() * width)
            y0 = int(bbox.ymin() * height)
            x1 = int(bbox.xmax() * width)
            y1 = int(bbox.ymax() * height)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)

            roi_img = frame_bgr[y0:y1, x0:x1].copy()
            try:
                user_data.roi_queue.put_nowait((frame_idx, roi_img))
                print(f"[DEBUG] Enqueued ROI from frame {frame_idx} for decode.")
            except:
                print(f"[DEBUG] ROI queue full; skipping decode for frame {frame_idx}.")

    return Gst.PadProbeReturn.OK


class MyDetectionApp(GStreamerDetectionApp):
    """Custom detection app if you want to override pipeline creation or debug logs."""
    def __init__(self, callback, user_data):
        super().__init__(callback, user_data)
        print("[DEBUG] MyDetectionApp initialized.")

    # Optionally override get_pipeline_string if you need custom pipeline debug
    # def get_pipeline_string(self):
    #     pipeline_str = super().get_pipeline_string()
    #     print("[DEBUG] Using pipeline string:", pipeline_str)
    #     return pipeline_str
