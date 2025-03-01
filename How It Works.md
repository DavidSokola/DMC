How It Works

main.py calls Gst.init(), creates a Queue (roi_queue), and spawns the DMCDecoderThread.
The pipeline code (MyDetectionApp) starts capturing from the camera and runs app_callback on each frame. If it finds a DMC bounding box, that ROI is appended to roi_queue.

The decoder thread (DMCDecoderThread) consumes those ROIs, uses pylibdmtx to decode, saves each ROI to disk, writes the decoded string to a .txt file, and updates the global last_decoded variable.

Meanwhile, the GUI (DecodedGUI) keeps refreshing every 500ms, reading last_decoded from decode_thread.py, and shows it on the screen.
Result: You see the latest decoded code in the GUI window. Meanwhile, each bounding box is also saved to output_images/ as DMC_<timestamp>.jpg plus a matching DMC_<timestamp>.txt.

Final Tips
If the pipeline fails to detect anything, confirm you are:

Providing a valid camera source for your environment (e.g., replace libcamerasrc with v4l2src if needed).
Using the correct Hailo detection network that recognizes "DMC" label. (Or if you have a custom label, adjust the label check in pipeline_code.py accordingly.)
If you need a higher resolution or different camera config, modify get_pipeline_string() in pipeline_code.py to match your device.

That’s it! Now you have a clean code base for reading Data Matrix from live camera frames, saving each detection, logging the text, and displaying the last code in a GUI.