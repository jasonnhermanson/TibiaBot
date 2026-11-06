import ctypes
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import ImageGrab, ImageTk
from . import settings
from .alerts import AlertGate
from .imaging import fill_percentage


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


class App:
    def __init__(self, root):
        self.root = root
        root.title("Health & Mana Monitor")
        root.resizable(False, False)
        self.running = False
        self.hunting_window = None
        self.gate = AlertGate()
        self.sounds = queue.Queue(maxsize=2)
        threading.Thread(target=self.sound_worker, daemon=True).start()
        try:
            self.data = settings.load()
        except (OSError, ValueError, KeyError, TypeError):
            self.data = settings.defaults()
            messagebox.showwarning("Settings", "Saved settings could not be read. Defaults loaded; select your regions again.")
        self.values, self.thresholds, self.enabled = {}, {}, {}
        frame = ttk.Frame(root, padding=16)
        frame.grid()
        ttk.Label(frame, text="Health & Mana", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(frame, text="Keep bars visible on your primary monitor. Select only their full interior.").grid(row=1, column=0, columnspan=4, pady=10)
        for row, name in enumerate(("health", "mana"), 2):
            box = ttk.LabelFrame(frame, text=name.title(), padding=10)
            box.grid(row=row, column=0, columnspan=4, sticky="ew", pady=5)
            self.values[name] = tk.StringVar(value="— %")
            ttk.Label(box, textvariable=self.values[name], font=("Segoe UI", 22)).grid(row=0, column=0, padx=10)
            ttk.Button(box, text="Select region", command=lambda n=name: self.select(n)).grid(row=0, column=1)
            ttk.Button(box, text="Bar color…", command=lambda n=name: self.color(n)).grid(row=0, column=2, padx=6)
            self.enabled[name] = tk.BooleanVar(value=self.data[name]["enabled"])
            ttk.Checkbutton(box, text="Sound at or below", variable=self.enabled[name]).grid(row=1, column=0, columnspan=2)
            self.thresholds[name] = tk.StringVar(value=str(self.data[name]["threshold"]))
            ttk.Spinbox(box, from_=0, to=100, width=6, textvariable=self.thresholds[name]).grid(row=1, column=2)
            ttk.Label(box, text="%").grid(row=1, column=3)
            ttk.Button(box, text="Test sound", command=lambda n=name: self.play(n)).grid(row=0, column=3)
        ttk.Button(frame, text="Start / Apply", command=self.start).grid(row=4, column=0, pady=12)
        ttk.Button(frame, text="Stop", command=self.stop).grid(row=4, column=1)
        ttk.Button(frame, text="Save settings", command=self.persist).grid(row=4, column=2)
        ttk.Button(frame, text="Route hunting…", command=self.open_hunting).grid(row=6, column=0, columnspan=4, pady=8)
        self.status = tk.StringVar(value="Select both regions, then Start. Alerts repeat every 5 seconds while low.")
        ttk.Label(frame, textvariable=self.status, wraplength=550).grid(row=5, column=0, columnspan=4)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(250, self.tick)

    def open_hunting(self):
        self.stop()
        if not self.persist():
            return
        from .hunting_ui import HuntingWindow
        self.hunting_window = HuntingWindow(self)

    def sound_worker(self):
        while True:
            name = self.sounds.get()
            try:
                if sys.platform == "win32":
                    import winsound
                    winsound.Beep(880 if name == "health" else 440, 250)
                    time.sleep(0.1)
                    winsound.Beep(880 if name == "health" else 440, 250)
            except RuntimeError:
                pass
            finally:
                self.sounds.task_done()

    def play(self, name):
        try:
            self.sounds.put_nowait(name)
        except queue.Full:
            pass

    def collect(self):
        candidate = {n: dict(v) for n, v in self.data.items()}
        for name in candidate:
            candidate[name]["threshold"] = float(self.thresholds[name].get())
            candidate[name]["enabled"] = self.enabled[name].get()
        settings.validate(candidate)
        self.data = candidate

    def persist(self):
        try:
            self.collect()
            settings.save(self.data)
            self.status.set("Settings saved.")
            return True
        except (ValueError, OSError) as error:
            messagebox.showerror("Cannot save", str(error))
            return False

    def start(self):
        if not self.persist():
            return
        if any(self.data[n]["region"] is None for n in self.data):
            messagebox.showinfo("Select bars", "Select both health and mana regions first.")
            return
        self.gate = AlertGate()
        self.running = True
        self.status.set("Monitoring. Keep the game visible; move this window away from the bars.")

    def stop(self):
        if self.hunting_window:
            self.hunting_window.stop("Stopped from monitor")
        self.running = False
        self.status.set("Stopped.")

    def color(self, name):
        self.stop()
        rgb, _ = colorchooser.askcolor(color="#%02x%02x%02x" % tuple(self.data[name]["color"]), parent=self.root)
        if rgb:
            chosen = [int(c) for c in rgb]
            try:
                from PIL import Image
                fill_percentage(Image.new("RGB", (2, 2)), tuple(chosen))
            except ValueError as error:
                messagebox.showerror("Bar color", str(error))
                return
            self.data[name]["color"] = chosen
            self.persist()

    def select(self, name):
        self.stop()
        self.root.withdraw()
        self.root.after(350, lambda: self.selection_snapshot(name))

    def selection_snapshot(self, name):
        try:
            shot = ImageGrab.grab()  # Primary monitor, physical pixels with DPI awareness.
            window = tk.Toplevel(self.root)
            window.overrideredirect(True)
            window.geometry(f"{shot.width}x{shot.height}+0+0")
            window.attributes("-topmost", True)
            canvas = tk.Canvas(window, width=shot.width, height=shot.height, highlightthickness=0, cursor="crosshair")
            canvas.pack()
            photo = ImageTk.PhotoImage(shot)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            canvas.create_text(20, 20, anchor="nw", fill="yellow", font=("Segoe UI", 16, "bold"), text=f"Drag around the FULL {name} bar interior (including empty area). Esc cancels.")
            origin = []
            rectangle = [None]
            def finish():
                window.destroy()
                self.root.deiconify()
            def press(event):
                origin[:] = [event.x, event.y]
                if rectangle[0]:
                    canvas.delete(rectangle[0])
                rectangle[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="yellow", width=2)
            def drag(event):
                if origin:
                    canvas.coords(rectangle[0], *origin, event.x, event.y)
            def release(event):
                if not origin:
                    return
                x1, x2 = sorted((max(0, min(shot.width, origin[0])), max(0, min(shot.width, event.x))))
                y1, y2 = sorted((max(0, min(shot.height, origin[1])), max(0, min(shot.height, event.y))))
                if x2 - x1 < 2 or y2 - y1 < 2:
                    return
                self.data[name]["region"] = [x1, y1, x2, y2]
                finish()
                self.persist()
            canvas.bind("<ButtonPress-1>", press)
            canvas.bind("<B1-Motion>", drag)
            canvas.bind("<ButtonRelease-1>", release)
            window.bind("<Escape>", lambda event: finish())
            window.focus_force()
        except Exception as error:
            self.root.deiconify()
            messagebox.showerror("Screen capture failed", str(error))

    def tick(self):
        if self.running:
            try:
                shot = ImageGrab.grab()
                for name, item in self.data.items():
                    region = item["region"]
                    if region[2] > shot.width or region[3] > shot.height:
                        raise ValueError("Saved region is outside the primary monitor. Select both regions again.")
                    percentage = fill_percentage(shot.crop(region), tuple(item["color"]))
                    self.values[name].set(f"{percentage:.0f} %")
                    if self.gate.due(name, percentage, item["threshold"], item["enabled"], time.monotonic()):
                        self.play(name)
            except Exception as error:
                self.stop()
                for value in self.values.values():
                    value.set("— %")
                self.status.set(f"Capture stopped: {error}")
        self.root.after(250, self.tick)

    def close(self):
        if self.hunting_window:
            self.hunting_window.close()
        if self.persist():
            self.running = False
            self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
