import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo

from picamera2 import Picamera2
from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# -----------------------------------------------------------------------------------------------
# Set Raspberry Pi Camera to Closest Focus & 640x640 Resolution
# -----------------------------------------------------------------------------------------------
def set_camera_focus(closest_focus=10.0, resolution=(640, 640)):
    """Sets the Raspberry Pi Camera (v3) to the closest focus with a fixed resolution."""
    picam2 = Picamera2()
    config = picam2.create_still_configuration(
        main={"size": resolution, "format": "RGB888"}  # Ensures 640x640 format
    )
    picam2.configure(config)
    picam2.set_controls({"AfMode": 1, "LensPosition": closest_focus})
    picam2.start()
    return picam2

# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.new_variable = 42  # New variable example

    def new_function(self):  # New function example
        return "The meaning of life is: "

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------

# This is the callback function that will be called when data is available from the pipeline
def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Using the user_data to count the number of frames
    user_data.increment()
    string_to_print = f"Frame count: {user_data.get_count()}\n"

    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)

    # If the user_data.use_frame is set to True, we can get the video frame from the buffer
    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        # Get video frame
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Parse the detections
    detection_count = 0
    string_to_print = ""

    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        track_id = 0
        track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
        if len(track) == 1:
            track_id = track[0].get_id()
        
        print(f"Detection: ID: {track_id} Label: {label} Confidence: {confidence:.2f}")

        if label in ["DMC", "text"]:  # Use a list for multiple labels
            string_to_print += (f"Detection: ID: {track_id} Label: {label} Confidence: {confidence:.2f}\n")
            detection_count += 1
    
    print("Final Output:\n", string_to_print)

    if user_data.use_frame:
        # Convert the frame to BGR before adding text
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Draw detection count on the frame
        cv2.putText(frame, f"Detections: {detection_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Print the new_variable and the result of new_function to the frame
        cv2.putText(frame, f"{user_data.new_function()} {user_data.new_variable}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        user_data.set_frame(frame)

    return Gst.PadProbeReturn.OK  # Ensure this is at the correct indentation level

# -----------------------------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()

