# user_callback.py

from hailo_apps_infra.hailo_rpi_common import app_callback_class

class user_app_callback_class(app_callback_class):
    """
    A custom callback class that inherits from hailo_apps_infra.app_callback_class.
    It holds a reference to our ROI queue, so the pipeline callback can push
    bounding-box images for decoding.
    """
    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        self.use_frame = True  # This can be toggled
        print("[DEBUG] user_app_callback_class initialized.")

