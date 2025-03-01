# gui_display.py

import tkinter as tk
from decode_thread import last_decoded

REFRESH_MS = 500  # GUI refresh interval (milliseconds)

class DecodedGUI:
    """
    A simple Tkinter-based GUI to display the last decoded Data Matrix code.
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DMC Decoder Display")
        self.root.geometry("600x300+50+50")
        self.root.configure(bg="black")

        self.label = tk.Label(
            self.root,
            text="Waiting for codes...",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="black",
            wraplength=550
        )
        self.label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        # Repeatedly update label from decode_thread.last_decoded
        self.update_label()

    def update_label(self):
        global last_decoded
        if last_decoded:
            self.label.config(text=f"Latest Code:\n{last_decoded}")
        else:
            self.label.config(text="Waiting for codes...")
        self.root.after(REFRESH_MS, self.update_label)

    def run(self):
        self.root.mainloop()
