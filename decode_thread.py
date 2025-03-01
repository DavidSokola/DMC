# decode_thread.py

import os
import time
import cv2
from queue import Empty
from threading import Thread
from pylibdmtx.pylibdmtx import decode as dmtx_decode
from PIL import Image

# This global variable is read by gui_display.py to show the latest code
last_decoded = ""

class DMCDecoderThread(Thread):
    """
    A background thread that receives (frame_idx, roi_img, timestamp)
    from a queue, decodes it using pylibdmtx, and:
      - Saves each ROI to 'DMC_<timestamp>.jpg'
      - Writes the decoded text (if found) to 'DMC_<timestamp>.txt'
      - Updates last_decoded so the GUI can display it.
    """

    def __init__(self, roi_queue):
        super().__init__()
        self.roi_queue = roi_queue
        self._stop_flag = False

        # Make sure output directory exists
        self.output_dir = "output_images"
        os.makedirs(self.output_dir, exist_ok=True)

        print("[DEBUG] DMCDecoderThread initialized")

    def run(self):
        global last_decoded
        print("[DEBUG] DMCDecoderThread started")

        while not self._stop_flag:
            try:
                # The pipeline callback puts (frame_idx, roi_img, timestamp)
                frame_idx, roi_img, stamp = self.roi_queue.get(timeout=0.5)
                print(f"[DECODE_THREAD] Got ROI frame={frame_idx}, running decode...")
            except Empty:
                continue

            # Convert the ROI (a NumPy BGR array) to a PIL Image in RGB for dmtx_decode
            pil_img = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(pil_img)

            # Attempt to decode the DMC
            results = dmtx_decode(pil_img)
            if results:
                decoded_str = results[0].data.decode("utf-8", errors="ignore")
                print(f"[DECODE] Frame {frame_idx} => '{decoded_str}'")
                last_decoded = decoded_str
            else:
                last_decoded = ""
                print(f"[DECODE] Frame {frame_idx}: no DMC found")

            # Save ROI image
            jpg_path = os.path.join(self.output_dir, f"DMC_{stamp}.jpg")
            cv2.imwrite(jpg_path, roi_img)
            print(f"[SAVE] ROI image => {jpg_path}")

            # Write decoded text (if any) to .txt
            txt_path = os.path.join(self.output_dir, f"DMC_{stamp}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                if last_decoded:
                    f.write(last_decoded + "\n")
                else:
                    f.write("NO CODE FOUND\n")
            print(f"[SAVE] Wrote text => {txt_path}")

            self.roi_queue.task_done()

        print("[DEBUG] DMCDecoderThread stopping")

    def stop(self):
        """Tell the thread to exit its loop."""
        self._stop_flag = True
