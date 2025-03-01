# decode_thread.py

import time
import cv2
from queue import Empty
from threading import Thread
from pylibdmtx.pylibdmtx import decode as dmtx_decode


# Global shared variable for the last decoded string (optional).
# If you prefer, pass a reference to the decode thread's constructor
# or maintain state in some other structure.
last_decoded = ""


class DMCDecoderThread(Thread):
    """Background thread that dequeues ROI images and decodes DMC codes asynchronously."""

    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        self._stop_flag = False
        print("[DEBUG] DMCDecoderThread initialized with queue maxsize =", roi_queue.maxsize)

    def run(self):
        global last_decoded
        print("[DEBUG] DMCDecoderThread started (run method).")

        while not self._stop_flag:
            try:
                frame_idx, roi_img = self.roi_queue.get(timeout=0.5)
            except Empty:
                # no item => loop again
                continue

            # Perform decode
            print(f"[DEBUG] Decoding ROI from frame {frame_idx}.")
            results = dmtx_decode(roi_img)
            if results:
                decoded_str = results[0].data.decode("utf-8", errors="ignore")
                print(f"[DECODE] Frame {frame_idx}: DMC => '{decoded_str}'")
                last_decoded = decoded_str
            else:
                print(f"[DECODE] Frame {frame_idx}: no DMC code found")

            self.roi_queue.task_done()

        print("[DEBUG] DMCDecoderThread stopping (run loop ended).")

    def stop(self):
        self._stop_flag = True
        print("[DEBUG] DMCDecoderThread stop_flag set.")
