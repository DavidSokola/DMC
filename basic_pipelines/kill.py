try:
    app.run()  # your GStreamer pipeline
finally:
    # Once the pipeline is done, we destroy any OpenCV windows:
    cv2.destroyAllWindows()
    print("[MAIN] Closed OpenCV windows, exiting.")
