# user_callback.py

from hailo_apps_infra.hailo_rpi_common import app_callback_class

class user_app_callback_class(app_callback_class):
    """Custom callback class referencing an ROI queue for decode."""

    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        print("[DEBUG] user_app_callback_class initialized.")

    # We could override or add custom methods if needed,
    # but typically you store your extra data here (like the queue).
