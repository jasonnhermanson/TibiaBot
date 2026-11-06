import copy
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import ImageGrab
from . import routes
from .hunting import Hunter
from .selection import select_region
from .vision import landmark
from .windows import WindowsInput, key_code


class HuntingWindow:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title('Tibia Origins — Route Hunting (beta)')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.hunter = None
        self.worker = None
        self.recording = False
        self.busy = False
        self.closed = False
        self.token = 0
        self.controls = None
        try:
            self.controls = WindowsInput()
        except RuntimeError:
            pass
        try:
            self.data = routes.load()
        except Exception as error:
            self.data = routes.defaults()
            messagebox.showwarning('Routes', f'Could not load route library; defaults loaded.\n{error}', parent=self.window)
        shell = ttk.Frame(self.window)
        shell.pack(fill='both', expand=True)
        canvas = tk.Canvas(shell, highlightthickness=0, width=730,
                           height=min(780, max(400, self.window.winfo_screenheight()-140)))
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(canvas, padding=12)
        content = canvas.create_window(0, 0, window=frame, anchor='nw')
        frame.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content, width=event.width))
        self.window.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta/120), 'units'))
        ttk.Label(frame, text='Recorded routes', font=('Segoe UI', 17, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w')
        ttk.Label(frame, text='Primary monitor • same floor and map zoom • F8 adds checkpoints • F10 stops').grid(row=1, column=0, columnspan=4, pady=6)
        ttk.Button(frame, text='1. Select minimap', command=self.select_map).grid(row=2, column=0)
        ttk.Button(frame, text='2. Mark player center', command=self.select_center).grid(row=2, column=1)
        ttk.Button(frame, text='3. Select EMPTY battle list', command=self.select_battle).grid(row=2, column=2, columnspan=2)
        self.setup = tk.StringVar()
        ttk.Label(frame, textvariable=self.setup).grid(row=3, column=0, columnspan=4, pady=6)
        ttk.Label(frame, text='Route name:').grid(row=4, column=0)
        self.route = tk.StringVar(value=next(iter(self.data['routes']), 'My first hunt'))
        self.picker = ttk.Combobox(frame, textvariable=self.route, width=28, values=list(self.data['routes']))
        self.picker.grid(row=4, column=1, columnspan=2, sticky='ew')
        self.picker.bind('<<ComboboxSelected>>', lambda event: self.refresh())
        ttk.Button(frame, text='Save new route', command=self.new_route).grid(row=4, column=3)
        self.points = tk.Listbox(frame, height=5, exportselection=False)
        self.points.grid(row=5, column=0, columnspan=4, sticky='ew', pady=6)
        ttk.Button(frame, text='Record / append (3s)', command=self.record).grid(row=6, column=0)
        ttk.Button(frame, text='Delete checkpoint', command=self.delete_point).grid(row=6, column=1)
        ttk.Button(frame, text='Delete route', command=self.delete_route).grid(row=6, column=2)
        ttk.Button(frame, text='Stop / F10', command=lambda: self.stop('Stopped')).grid(row=6, column=3)
        config = ttk.LabelFrame(frame, text='Game hotkeys — assign these in Tibia first', padding=8)
        config.grid(row=7, column=0, columnspan=4, sticky='ew', pady=8)
        self.fields = {}
        options = self.data['options']
        for row, (label, key, threshold) in enumerate([('Target next', 'target_key', None), ('Heal', 'heal_key', 'heal_at'), ('Mana', 'mana_key', 'mana_at')]):
            ttk.Label(config, text=label).grid(row=row, column=0, sticky='w')
            self.fields[key] = tk.StringVar(value=options[key])
            ttk.Entry(config, width=7, textvariable=self.fields[key]).grid(row=row, column=1)
            if threshold:
                enabled = 'heal_enabled' if key == 'heal_key' else 'mana_enabled'
                self.fields[enabled] = tk.BooleanVar(value=options[enabled])
                ttk.Checkbutton(config, text='Enable at/below', variable=self.fields[enabled]).grid(row=row, column=2)
                self.fields[threshold] = tk.StringVar(value=str(options[threshold]))
                ttk.Entry(config, width=5, textvariable=self.fields[threshold]).grid(row=row, column=3)
                ttk.Label(config, text='%').grid(row=row, column=4)
            ttk.Button(config, text='Test key (3s)', command=lambda k=key: self.test_key(k)).grid(row=row, column=5, padx=5)
        advanced = ttk.LabelFrame(frame, text='Timing and detection', padding=8)
        advanced.grid(row=8, column=0, columnspan=4, sticky='ew')
        for row, (label, key) in enumerate([('Critical health stop (%)', 'critical_at'), ('Heal / mana cooldown (seconds)', 'key_cooldown'), ('Target next interval (seconds)', 'target_interval'), ('Battle-list changed fraction (0.02 = 2%)', 'battle_change'), ('Checkpoint timeout (seconds)', 'waypoint_timeout')]):
            ttk.Label(advanced, text=label).grid(row=row, column=0, sticky='w')
            self.fields[key] = tk.StringVar(value=str(options[key]))
            ttk.Entry(advanced, width=8, textvariable=self.fields[key]).grid(row=row, column=1)
        self.fields['loop'] = tk.BooleanVar(value=options['loop'])
        ttk.Checkbutton(advanced, text='Loop route', variable=self.fields['loop']).grid(row=5, column=0, sticky='w')
        ttk.Button(frame, text='Save settings', command=self.save_options).grid(row=9, column=0, pady=10)
        ttk.Button(frame, text='Start hunt (3s)', command=self.start).grid(row=9, column=1)
        ttk.Button(frame, text='Back to monitor', command=self.close).grid(row=9, column=3)
        self.status = tk.StringVar(value='Set up minimap and empty battle list, then create a route.')
        ttk.Label(frame, textvariable=self.status, wraplength=650).grid(row=10, column=0, columnspan=4)
        self.refresh()
        app.root.withdraw()
        self.window.after(100, self.poll)

    def error(self, error):
        self.busy = False
        self.window.deiconify()
        messagebox.showerror('Route hunting', str(error), parent=self.window)

    def idle(self):
        if self.recording or self.busy or (self.hunter and self.hunter.active):
            raise ValueError('Stop recording/hunting before changing setup or routes.')

    def save(self):
        routes.save(self.data)
        self.refresh()

    def refresh(self):
        self.picker['values'] = list(self.data['routes'])
        self.points.delete(0, 'end')
        for index, _ in enumerate(self.data['routes'].get(self.route.get(), []), 1):
            self.points.insert('end', f'Checkpoint {index}')
        self.setup.set('Minimap: '+('set' if self.data['minimap'] else 'missing')+'   Player center: '+('set' if self.data['center'] else 'missing')+'   Empty battle list: '+('set' if self.data['empty_battle'] else 'missing'))

    def select_map(self):
        try:
            self.idle()
            if any(self.data['routes'].values()):
                if not messagebox.askyesno('Map calibration', 'Changing the minimap invalidates recorded routes. Clear all recorded checkpoints?', parent=self.window):
                    return
            def done(region, shot):
                if region[2]-region[0] > 240 or region[3]-region[1] > 240:
                    raise ValueError('Select only the minimap interior, at most 240×240 pixels.')
                self.data['minimap'] = region
                self.data['center'] = None
                self.data['game_rect'] = None
                self.data['battle'] = None
                self.data['empty_battle'] = None
                self.data['routes'] = {name: [] for name in self.data['routes']}
                self.save()
            select_region(self.window, 'Drag around minimap INTERIOR; exclude zoom buttons/borders', done, self.error)
        except Exception as error:
            self.error(error)

    def select_center(self):
        try:
            self.idle()
            if not self.data['minimap']:
                raise ValueError('Select the minimap first.')
            if any(self.data['routes'].values()):
                raise ValueError('Delete recorded checkpoints/routes before changing the player center.')
            def done(point, shot):
                region = self.data['minimap']
                candidate = [point[0]-region[0], point[1]-region[1]]
                test = copy.deepcopy(self.data)
                test['center'] = candidate
                routes.validate(test)
                self.data = test
                self.save()
            select_region(self.window, 'Click the CENTER of your player marker on the minimap', done, self.error, point=True)
        except Exception as error:
            self.error(error)

    def select_battle(self):
        try:
            self.idle()
            def done(region, shot):
                self.data['battle'] = region
                self.data['empty_battle'] = routes.encode_image(shot.crop(region))
                self.save()
            select_region(self.window, 'With NO creatures present, drag around battle-list CONTENT only', done, self.error)
        except Exception as error:
            self.error(error)

    def new_route(self):
        try:
            self.idle()
            name = self.route.get().strip()
            if not name or len(name) > 80:
                raise ValueError('Enter a route name of 1–80 characters.')
            if name in self.data['routes']:
                raise ValueError('That route already exists. Record / append adds more checkpoints.')
            self.data['routes'][name] = []
            self.route.set(name)
            self.save()
        except Exception as error:
            self.error(error)

    def delete_point(self):
        try:
            self.idle()
            selected = self.points.curselection()
            if selected:
                del self.data['routes'][self.route.get()][selected[0]]
                self.save()
        except Exception as error:
            self.error(error)

    def delete_route(self):
        try:
            self.idle()
            name = self.route.get()
            if name in self.data['routes'] and messagebox.askyesno('Delete route', f'Delete {name!r}?', parent=self.window):
                del self.data['routes'][name]
                self.route.set(next(iter(self.data['routes']), 'My first hunt'))
                self.save()
        except Exception as error:
            self.error(error)

    def save_options(self):
        try:
            self.idle()
            candidate = copy.deepcopy(self.data)
            for key, field in self.fields.items():
                if key.endswith('_key'):
                    candidate['options'][key] = field.get().strip().upper()
                elif key in ('heal_enabled', 'mana_enabled', 'loop'):
                    candidate['options'][key] = field.get()
                else:
                    candidate['options'][key] = float(field.get())
            routes.validate(candidate)
            self.data = candidate
            self.save()
            return True
        except Exception as error:
            self.error(error)
            return False

    def countdown(self, callback):
        self.idle()
        if not self.controls:
            raise ValueError('Hunting requires Windows.')
        if self.worker and self.worker.is_alive():
            raise ValueError('The previous hunt is finishing. Try again in a moment.')
        self.busy = True
        self.token += 1
        token = self.token
        self.status.set('Switch to the GAME window now. Binding in 3 seconds. F10 cancels.')
        self.window.iconify()
        def finish():
            if self.closed or token != self.token:
                return
            try:
                self.busy = False
                title = self.controls.bind_foreground()
                callback()
                self.status.set(f'Bound to {title}. '+self.status.get())
            except Exception as error:
                self.error(error)
        self.window.after(3000, finish)

    def check_layout(self):
        rect = list(self.controls.rect)
        saved = self.data.get('game_rect')
        if saved is not None and rect != saved:
            raise ValueError('Game window position/size differs from the recording. Restore its original layout, or reselect regions and record routes again.')
        for name in ('minimap', 'battle'):
            region = self.data[name]
            if region and not (rect[0] <= region[0] < region[2] <= rect[2]
                               and rect[1] <= region[1] < region[3] <= rect[3]):
                raise ValueError(f'The {name} region is outside the selected game window.')
        self.data['game_rect'] = rect
        self.save()

    def record(self):
        try:
            if not self.data['minimap'] or not self.data['center']:
                raise ValueError('Select the minimap and player center first.')
            if self.route.get() not in self.data['routes']:
                raise ValueError('Save a new route first, or select an existing one.')
            def begin():
                self.check_layout()
                self.recording = True
                self.record_name = self.route.get()
                self.status.set('Recording: walk manually, stop at each checkpoint, press F8. F10 ends recording.')
            self.countdown(begin)
        except Exception as error:
            self.error(error)

    def test_key(self, key):
        try:
            code = self.fields[key].get().strip().upper()
            key_code(code)
            if not self.save_options():
                return
            def send():
                self.controls.tap(code)
                self.status.set(f'Sent {code} once. Verify the action in game.')
            self.countdown(send)
        except Exception as error:
            self.error(error)

    def start(self):
        try:
            if not self.save_options():
                return
            self.app.collect()
            if any(item['region'] is None for item in self.app.data.values()):
                raise ValueError('Select health and mana bar regions in the monitor first.')
            if not all(self.data[key] for key in ('minimap', 'center', 'battle', 'empty_battle')):
                raise ValueError('Finish all three region setup steps first.')
            points = self.data['routes'].get(self.route.get(), [])
            if not points:
                raise ValueError('Select a route with recorded checkpoints.')
            bars = copy.deepcopy(self.app.data)
            def begin():
                self.check_layout()
                for bar in bars.values():
                    region, rect = bar['region'], self.controls.rect
                    if not (rect[0] <= region[0] < region[2] <= rect[2] and rect[1] <= region[1] < region[3] <= rect[3]):
                        raise ValueError('Health/mana regions are outside the game window. Select them again.')
                data = self.data
                self.hunter = Hunter(self.controls, data['options'], bars, data['minimap'], data['center'], data['battle'], routes.decode_image(data['empty_battle']), points, alert=self.app.play)
                hunter = self.hunter
                def work():
                    while hunter.active:
                        try:
                            hunter.step(ImageGrab.grab())
                        except Exception as error:
                            hunter.stop(f'Stopped: {error}')
                        time.sleep(0.2)
                self.worker = threading.Thread(target=work, daemon=True)
                self.worker.start()
            self.countdown(begin)
        except Exception as error:
            self.error(error)

    def stop(self, reason):
        self.token += 1
        self.busy = False
        self.recording = False
        if self.hunter:
            self.hunter.stop(reason)
        self.status.set(reason)

    def poll(self):
        if self.closed:
            return
        try:
            if self.controls:
                stop = self.controls.pressed('F10')
                record = self.controls.pressed('F8')
                if stop:
                    self.stop('Stopped by F10. Recorded checkpoints are saved.')
                elif self.recording:
                    if not self.controls.ready():
                        self.stop('Recording stopped: game lost focus or moved.')
                    elif record:
                        region = self.data['minimap']
                        shot = ImageGrab.grab()
                        if region[2] > shot.width or region[3] > shot.height:
                            raise ValueError('Minimap is outside the primary monitor.')
                        patch = landmark(shot.crop(region), self.data['center'])
                        points = self.data['routes'][self.record_name]
                        if len(points) >= 500:
                            raise ValueError('Route has reached 500 checkpoints.')
                        points.append({'image': routes.encode_image(patch)})
                        self.save()
                        self.status.set(f'{self.record_name}: saved checkpoint {len(points)}. F8 adds; F10 ends.')
                elif self.hunter and not self.busy:
                    self.status.set(self.hunter.status)
        except Exception as error:
            self.stop(f'Stopped: {error}')
            self.error(error)
        self.window.after(100, self.poll)

    def close(self):
        self.stop('Stopped')
        self.closed = True
        self.window.destroy()
        self.app.root.deiconify()
        self.app.hunting_window = None
