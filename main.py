# main.py

import sys
import signal
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from queue import Queue

from decode_thread import DMCDecoderThread
from user_callback import user_app_callback_class
from pipeline_code import MyDetectionApp, app_callback
from gui_display import DecodedGUI

QUEUE_MAXSIZE = 50

decoder_thread = None
app = None

def signal_handler(sig, frame):
    print(f"[MAIN] Caught signal {sig}, shutting down...")
    if decoder_thread:
        decoder_thread.stop()
    if app:
        app.stop()
    sys.exit(0)

def main():
    # Handle Ctrl+C, kill signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize GStreamer
    print("[MAIN] Initializing GStreamer...")
    Gst.init(None)

    # Create a queue for bounding box images
    roi_queue = Queue(maxsize=QUEUE_MAXSIZE)

    # Start the decode thread
    global decoder_thread
    decoder_thread = DMCDecoderThread(roi_queue)
    decoder_thread.start()

    # Create user callback object with reference to roi_queue
    user_data = user_app_callback_class(roi_queue)
    user_data.use_frame = True

    # Build the pipeline app
    global app
    app = MyDetectionApp(app_callback, user_data)

    # Start the GUI in a separate thread so GStreamer doesn't block it
    # Alternatively, we can just call app.run() and not show GUI, but let's show both
    gui = DecodedGUI()

    # We'll run the pipeline in its own thread so the GUI can remain responsive
    import threading
    def run_pipeline():
        print("[MAIN] Starting pipeline...")
        app.run()  # blocks until pipeline stops
        print("[MAIN] Pipeline ended.")

    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()

    # Now run the GUI main loop in the main thread
    print("[MAIN] Running GUI. Press Ctrl+C to exit.")
    gui.run()

    # If GUI closes, we stop everything
    decoder_thread.stop()
    pipeline_thread.join()
    print("[MAIN] Done.")

if __name__ == "__main__":
    main()
