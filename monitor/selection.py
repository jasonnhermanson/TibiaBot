"""Frozen screenshot selection shared by route setup tools."""
import tkinter as tk
from PIL import ImageGrab, ImageTk


def select_region(root, prompt, callback, failed, point=False):
    root.withdraw()
    def capture():
        try:
            shot = ImageGrab.grab()
            window = tk.Toplevel(root)
            window.overrideredirect(True)
            window.attributes('-topmost', True)
            window.geometry(f'{shot.width}x{shot.height}+0+0')
            canvas = tk.Canvas(window, highlightthickness=0, cursor='crosshair')
            canvas.pack(fill='both', expand=True)
            photo = ImageTk.PhotoImage(shot)
            canvas.create_image(0, 0, image=photo, anchor='nw')
            canvas.image = photo
            canvas.create_text(15, 15, anchor='nw', text=prompt+' (Esc cancels)', fill='yellow', font=('Segoe UI', 14, 'bold'))
            origin, rectangle = [], [None]
            def close():
                window.destroy()
                root.deiconify()
            def press(event):
                origin[:] = [event.x, event.y]
                if not point:
                    if rectangle[0]:
                        canvas.delete(rectangle[0])
                    rectangle[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='yellow', width=2)
            def drag(event):
                if origin and rectangle[0]:
                    canvas.coords(rectangle[0], *origin, event.x, event.y)
            def release(event):
                if not origin:
                    return
                if point:
                    result = [event.x, event.y]
                else:
                    x1, x2 = sorted((max(0, min(shot.width, origin[0])), max(0, min(shot.width, event.x))))
                    y1, y2 = sorted((max(0, min(shot.height, origin[1])), max(0, min(shot.height, event.y))))
                    if x2-x1 < 25 or y2-y1 < 25:
                        return
                    result = [x1, y1, x2, y2]
                close()
                try:
                    callback(result, shot)
                except Exception as error:
                    failed(error)
            canvas.bind('<ButtonPress-1>', press)
            canvas.bind('<B1-Motion>', drag)
            canvas.bind('<ButtonRelease-1>', release)
            window.bind('<Escape>', lambda event: close())
            window.focus_force()
        except Exception as error:
            root.deiconify()
            failed(error)
    root.after(400, capture)
