"""Beginner-facing setup and saved coordinate routes, backed by Origins' Lua APIs."""
import copy
import os
from pathlib import Path
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from . import coordinate as model
from .alerts import AlertGate
from .windows import WindowsInput


class CoordinateWindow:
    def __init__(self,app):
        self.app=app
        self.window=tk.Toplevel(app.root)
        self.window.title('Origins — Coordinate Routes')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.closed=False
        self.recording=None
        self.hunter=None
        self.bridge=None
        self.state=None
        self.token=0
        self.busy=False
        self.alerts=AlertGate()
        try:
            self.controls=WindowsInput()
        except RuntimeError:
            self.controls=None
        try:
            self.data=model.load_library()
        except Exception as error:
            self.data=model.library_defaults()
            messagebox.showwarning('Coordinate routes',f'Could not load saved coordinate settings: {error}',parent=self.window)
        outer=ttk.Frame(self.window)
        outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,highlightthickness=0,width=740,
                         height=min(780,max(400,self.window.winfo_screenheight()-140)))
        scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        shell=ttk.Frame(canvas,padding=12)
        content=canvas.create_window(0,0,window=shell,anchor='nw')
        shell.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(content,width=event.width))
        self.window.bind('<MouseWheel>',lambda event:canvas.yview_scroll(-int(event.delta/120),'units'))
        ttk.Label(shell,text='Origins Coordinate Routes',font=('Segoe UI',17,'bold')).pack(anchor='w')
        ttk.Label(shell,text='F8 adds a checkpoint • F10 stops • Use short routes on one floor first').pack(anchor='w',pady=5)
        setup=ttk.LabelFrame(shell,text='1. Connect the Lua bridge',padding=8)
        setup.pack(fill='x',pady=6)
        ttk.Button(setup,text='Install bridge in game folder…',command=self.install).grid(row=0,column=0,sticky='w')
        ttk.Button(setup,text='Copy terminal load command',command=self.copy_command).grid(row=0,column=1,padx=5)
        self.folder=tk.StringVar(value=self.data['bridge_folder'])
        ttk.Label(setup,text='Bridge folder (shown by the terminal command):').grid(row=1,column=0,columnspan=2,sticky='w',pady=5)
        ttk.Entry(setup,textvariable=self.folder,width=65).grid(row=2,column=0,columnspan=2,sticky='ew')
        ttk.Button(setup,text='Browse…',command=self.browse).grid(row=2,column=2)
        ttk.Button(setup,text='Connect',command=self.connect).grid(row=3,column=0,sticky='w',pady=5)
        self.readout=tk.StringVar(value='Not connected')
        ttk.Label(setup,textvariable=self.readout,wraplength=650).grid(row=4,column=0,columnspan=3,sticky='w')
        route=ttk.LabelFrame(shell,text='2. Record and choose routes',padding=8)
        route.pack(fill='x',pady=6)
        self.name=tk.StringVar(value=self.data['selected'] or next(iter(self.data['routes']),'My first route'))
        self.picker=ttk.Combobox(route,textvariable=self.name,values=list(self.data['routes']),width=30)
        self.picker.grid(row=0,column=0,columnspan=2,sticky='ew')
        self.picker.bind('<<ComboboxSelected>>',lambda event:self.refresh())
        ttk.Button(route,text='Create route',command=self.create).grid(row=0,column=2)
        ttk.Button(route,text='Delete route',command=self.delete_route).grid(row=0,column=3)
        self.points=tk.Listbox(route,height=5,exportselection=False,width=65)
        self.points.grid(row=1,column=0,columnspan=4,sticky='ew',pady=5)
        for column,(label,callback) in enumerate([('Record / append',self.record),('Add current position',self.add),('Add 3-second wait',self.wait),('Delete checkpoint',self.delete_point)]):
            ttk.Button(route,text=label,command=callback).grid(row=2,column=column)
        opts=ttk.LabelFrame(shell,text='3. Hunt settings',padding=8)
        opts.pack(fill='x',pady=6)
        self.fields={}
        o=self.data['options']
        for column,(key,label) in enumerate([('loop','Loop route'),('walk_only','Walk only (no targeting)')]):
            self.fields[key]=tk.BooleanVar(value=o[key])
            ttk.Checkbutton(opts,text=label,variable=self.fields[key]).grid(row=0,column=column,columnspan=1,sticky='w')
        for row,kind in enumerate(('heal','mana'),1):
            self.fields[kind+'_enabled']=tk.BooleanVar(value=o[kind+'_enabled'])
            ttk.Checkbutton(opts,text=kind.title()+' enabled',variable=self.fields[kind+'_enabled']).grid(row=row,column=0,sticky='w')
            for column,key in enumerate((kind+'_key',kind+'_at'),1):
                self.fields[key]=tk.StringVar(value=str(o[key]))
                ttk.Entry(opts,textvariable=self.fields[key],width=8).grid(row=row,column=column)
            ttk.Label(opts,text='key / at or below %').grid(row=row,column=3,sticky='w')
        for row,key,label in [(3,'critical_at','Critical health stop (%)'),(4,'cooldown','Resource-key cooldown (seconds)'),(5,'timeout','Walking / combat timeout (seconds)')]:
            ttk.Label(opts,text=label).grid(row=row,column=0,columnspan=2,sticky='w')
            self.fields[key]=tk.StringVar(value=str(o[key]))
            ttk.Entry(opts,textvariable=self.fields[key],width=8).grid(row=row,column=2)
        buttons=ttk.Frame(shell)
        buttons.pack(fill='x',pady=8)
        for label,callback in [('Save settings',self.save_options),('Start route (3s)',self.start),('STOP / F10',lambda:self.stop('Stopped')),('Back',self.close)]:
            ttk.Button(buttons,text=label,command=callback).pack(side='left',padx=3)
        self.status=tk.StringVar(value='Install the bridge, load it in the game terminal, then connect to its folder.')
        ttk.Label(shell,textvariable=self.status,wraplength=680).pack(anchor='w')
        self.refresh()
        app.root.withdraw()
        self.window.after(200,self.poll)

    def error(self,error):
        messagebox.showerror('Coordinate routes',str(error),parent=self.window)

    def idle(self):
        if self.recording or self.busy or (self.hunter and self.hunter.active):
            raise model.BridgeError('Stop recording/playback before editing settings or routes')

    def save(self):
        self.data['bridge_folder']=self.folder.get().strip()
        self.data['selected']=self.name.get()
        model.save_library(self.data)
        self.refresh()

    def refresh(self):
        self.picker['values']=list(self.data['routes'])
        self.points.delete(0,'end')
        for index,point in enumerate(self.data['routes'].get(self.name.get(),[]),1):
            if point['action']=='walk':
                p=point['position']
                label=f"{index}. Walk to {p['x']}, {p['y']}, floor {p['z']}"
            else:
                label=f"{index}. Wait {point['seconds']} seconds"
            self.points.insert('end',label)

    def install(self):
        try:
            self.idle()
            initial=Path(os.environ.get('LOCALAPPDATA',''))/'TibiaOrigins'
            selected=filedialog.askdirectory(title='Select TibiaOrigins folder containing the game EXE and modules',initialdir=str(initial) if initial.exists() else None,parent=self.window)
            if not selected:
                return
            root=Path(selected)
            if not (root/'modules').is_dir() or not (root/'mods').is_dir():
                raise model.BridgeError('Select the game folder that contains both modules and mods')
            source=Path(__file__).resolve().parent.parent/'client_bridge'/'origins_bridge.lua'
            dest=root/'mods'/'origins_bridge.lua'
            if dest.exists() and dest.read_bytes()!=source.read_bytes():
                shutil.copy2(dest,dest.with_suffix('.lua.bak'))
            shutil.copy2(source,dest)
            self.copy_command()
            messagebox.showinfo('Bridge installed','Bridge copied into mods. The load command is on your clipboard.\nOpen the game terminal with Ctrl+T, paste it, and press Enter.\nCopy the folder it returns into Bridge folder here.',parent=self.window)
        except Exception as error:
            self.error(error)

    def copy_command(self):
        self.window.clipboard_clear()
        self.window.clipboard_append("dofile('/mods/origins_bridge.lua'); return OriginsBridge.folder")
        self.status.set('Load command copied. Paste in the GAME terminal; it returns the bridge folder.')

    def browse(self):
        selected=filedialog.askdirectory(title='Select folder returned by OriginsBridge.folder',parent=self.window)
        if selected:
            self.folder.set(selected)

    def connect(self):
        try:
            self.idle()
            self.bridge=model.Bridge(self.folder.get().strip())
            self.state=self.bridge.read()
            self.save()
            self.status.set('Connected. Bridge is observing only; movement starts only with Start route.')
        except Exception as error:
            self.bridge=None
            self.error(error)

    def current(self):
        if not self.bridge:
            raise model.BridgeError('Connect the bridge folder first')
        self.state=self.bridge.read()
        if not self.state['online']:
            raise model.BridgeError('Log into a character first. '+self.state.get('error',''))
        return self.state

    def create(self):
        try:
            self.idle()
            name=self.name.get().strip()
            if not 1<=len(name)<=80 or name in self.data['routes']:
                raise model.BridgeError('Enter a new route name (1–80 characters)')
            self.name.set(name)
            self.data['routes'][name]=[]
            self.save()
        except Exception as error:
            self.error(error)

    def delete_route(self):
        try:
            self.idle()
            name=self.name.get()
            if name in self.data['routes'] and messagebox.askyesno('Delete route',f'Delete {name!r}?',parent=self.window):
                del self.data['routes'][name]
                self.name.set(next(iter(self.data['routes']),'My first route'))
                self.save()
        except Exception as error:
            self.error(error)

    def route_points(self):
        if self.name.get() not in self.data['routes']:
            raise model.BridgeError('Create or select a saved route first')
        return self.data['routes'][self.name.get()]

    def record(self):
        try:
            self.idle()
            self.recording=model.Recorder(self.current(),self.route_points())
            self.save()
            self.status.set('Recording automatically every 3 tiles and at observed turns. Walk manually; F8 adds a point, F10 finishes.')
            self.window.iconify()
        except Exception as error:
            self.recording=None
            self.error(error)

    def add(self):
        try:
            if self.hunter and self.hunter.active:
                raise model.BridgeError('Stop playback before adding checkpoints')
            state=self.current()
            if self.recording:
                self.recording.sample(state,force=True)
            else:
                model.Recorder(state,self.route_points())
            self.save()
        except Exception as error:
            self.error(error)

    def wait(self):
        try:
            self.idle()
            self.route_points().append({'action':'wait','seconds':3})
            self.save()
        except Exception as error:
            self.error(error)

    def delete_point(self):
        try:
            self.idle()
            chosen=self.points.curselection()
            if chosen:
                del self.route_points()[chosen[0]]
                self.save()
        except Exception as error:
            self.error(error)

    def save_options(self):
        try:
            self.idle()
            candidate=copy.deepcopy(self.data)
            for key,value in self.fields.items():
                if key in ('loop','walk_only','heal_enabled','mana_enabled'):
                    candidate['options'][key]=value.get()
                elif key.endswith('_key'):
                    candidate['options'][key]=value.get().strip().upper()
                else:
                    candidate['options'][key]=float(value.get())
            model.validate_library(candidate)
            self.data=candidate
            self.save()
            return True
        except Exception as error:
            self.error(error)
            return False

    def start(self):
        try:
            if not self.save_options():
                return
            if not self.controls:
                raise model.BridgeError('Playback requires Windows')
            self.current()
            points=copy.deepcopy(self.route_points())
            self.token+=1
            token=self.token
            self.busy=True
            self.status.set('Switch to the actual GAME within 3 seconds. F10 cancels.')
            self.window.iconify()
            def begin():
                if self.closed or token!=self.token:
                    return
                self.busy=False
                try:
                    title=self.controls.bind_foreground()
                    if 'tibiaorigins' not in title.lower().replace(' ',''):
                        raise model.BridgeError('Switch to the TibiaOrigins game window during the countdown')
                    self.hunter=model.CoordinateHunter(self.bridge,self.controls,self.current(),points,self.data['options'])
                    self.alerts=AlertGate()
                except Exception as error:
                    self.error(error)
                    self.window.deiconify()
            self.window.after(3000,begin)
        except Exception as error:
            self.error(error)

    def stop(self,reason):
        self.token+=1
        self.busy=False
        if self.hunter:
            self.hunter.stop(reason,self.state)
        if self.recording:
            try:
                self.recording.sample(self.current(),force=True)
            except Exception:
                pass
            self.recording=None
            self.save()
        self.status.set(reason)

    def poll(self):
        if self.closed:
            return
        try:
            if self.controls and self.controls.pressed('F10'):
                self.stop('Stopped by F10')
            add=self.controls and self.controls.pressed('F8')
            if self.bridge:
                try:
                    self.state=self.bridge.read()
                except (OSError,ValueError,KeyError,TypeError) as error:
                    # A client write may be in progress; never send another action from an old snapshot.
                    if self.recording or (self.hunter and self.hunter.active):
                        self.stop('Stopped: '+str(error))
                    self.readout.set('No live data: '+str(error))
                    self.window.after(200,self.poll)
                    return
                state=self.state
                if state['online']:
                    p=state['position']
                    target=state.get('target',{}).get('name','none')
                    self.readout.set(f"Position {p['x']}, {p['y']}, {p['z']} | HP {state['health']}/{state['max_health']} | Mana {state['mana']}/{state['max_mana']} | Target {target}")
                else:
                    self.readout.set('Offline. '+state.get('error',''))
                if self.recording:
                    if self.recording.sample(state,force=bool(add)):
                        self.save()
                if self.hunter and self.hunter.active:
                    self.hunter.step(state)
                    self.status.set(self.hunter.status)
                    if state['online']:
                        for name,current,total in [('health',state['health'],state['max_health']),('mana',state['mana'],state['max_mana'])]:
                            bar=self.app.data[name]
                            pct=100*current/total if total else 100
                            if self.alerts.due(name,pct,bar['threshold'],bar['enabled'],time.monotonic()):
                                self.app.play(name)
        except Exception as error:
            self.stop('Stopped: '+str(error))
            self.error(error)
        self.window.after(200,self.poll)

    def close(self):
        self.stop('Stopped')
        self.closed=True
        self.window.destroy()
        self.app.coordinate_window=None
        self.app.root.deiconify()
