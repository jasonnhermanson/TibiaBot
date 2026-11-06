# Tibia Origins Route Hunter & Health/Mana Monitor for Windows

A Python desktop app with a health/mana monitor and an experimental screen-driven route hunter for Tibia Origins OT. The monitor reads two visible horizontal screen bars with Pillow and shows estimated percentages. Select health and mana regions, choose their fill colors, and set separate low-resource sound thresholds. It reads screenshots only and does not read game memory. Monitor mode sends no game input; Route hunting mode sends configured keys and minimap clicks to the bound foreground game window.

## Download and run on Windows (first time)

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/windows/>. In the installer, keep **pip**, **Tcl/Tk**, and the **Python launcher** enabled. If offered, select **Add Python to PATH**.
2. Download [the Windows app ZIP](https://github.com/jasonnhermanson/TibiaBot/archive/refs/heads/health-mana-monitor.zip) and save it in Downloads. Sign in to GitHub if needed. Right-click it → **Extract All…** → **Extract**. Open the extracted folder containing `launch_windows.bat`.
   - You can also visit <https://github.com/jasonnhermanson/TibiaBot>, select the `health-mana-monitor` branch, and click **Code → Download ZIP**, then extract it.
3. Double-click **launch_windows.bat** (it may appear as `launch_windows` if extensions are hidden). Do not run it from inside the ZIP. The first launch creates a local `.venv` and downloads Pillow, so it needs internet access. Later launches reuse it.
4. Keep the console open while using the app. If setup fails, the console stays open so you can read the error. You do not need administrator access.

This is source code with a launcher, not a standalone `.exe`.

## Upgrade from the monitor-only version

Download the ZIP again using the link above and extract it into a **new folder**. Run that folder's `launch_windows.bat`. Your health/mana settings remain in your Windows user profile. A new **Route hunting…** button opens the hunting controls. The launcher also now explains when it has accidentally been run from inside a ZIP.

## Select bars and configure alerts

1. Run your game in **windowed or borderless mode on your primary monitor**. Keep both bars visible. Keep the monitor app away from them.
2. Click **Select region** under Health. The app hides itself and freezes a screenshot. Drag from one corner of the **entire bar interior** to the opposite corner, including its empty part. Exclude the border, icons, and labels outside the bar. Release to save; **Esc** cancels. Tiny selections are ignored.
3. Repeat for Mana. Regions use fixed screen coordinates: reselect if you move the game, change resolution, or change display scaling.
4. Defaults assume red health and blue mana. Use **Bar color…** to choose a color close to the actual filled portion if needed. Use a saturated color, not white, gray, or black.
5. Enter each alert percentage from **0 to 100** and enable its sound checkbox. Click **Test sound** to check volume: health uses a higher tone; mana uses a lower tone.
6. Click **Start / Apply**. Percentages refresh about four times per second. Alerts sound immediately at or below the chosen threshold, then at most every five seconds per resource while low. **Stop** pauses measurement and new alerts; a tone already playing may finish. Apply changes with **Start / Apply**, or save them with **Save settings**.

Regions and colors save after selection; thresholds and checkboxes save with Save settings, Start / Apply, or closing the app. Settings live at `%APPDATA%\HealthManaMonitor\settings.json`. Monitoring always starts stopped. To reset, close the app and delete that file. If settings are damaged, the app warns and loads defaults.

## Accuracy and troubleshooting

- This estimates the fraction of columns containing the selected color. It supports horizontal colored bars with a dark or neutral empty background. It is not OCR and does not infer maximum hit points or mana.
- Shading and modest text overlays are tolerated. Animated colors, heavy labels, similar-colored backgrounds, non-horizontal bars, or a badly selected region can produce incorrect readings. A fully empty bar reads 0%.
- If another window covers a bar, the game is minimized, or the capture is black, readings can be wrong and low alerts can fire. Keep bars visible and stop monitoring before switching away. Exclusive fullscreen capture may fail; use borderless mode.
- Primary monitor only. Windows DPI awareness is enabled before the UI starts. Reselect after display changes. Secondary monitors and unusual mixed-DPI arrangements are not supported in this first version.
- No sound: check Windows volume/output device and the alert checkbox, then use Test sound. Sounds use Windows `winsound.Beep`; no audio files are required.
- Python not found: rerun the Python installer and enable the launcher. `py -3 --version` in Command Prompt should work.
- Pillow installation fails: check internet access; rerun the launcher. If the virtual environment is broken, close the app, delete only this app's `.venv` folder, then launch again.

## Run manually / test

In Command Prompt opened in the extracted app folder:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m monitor.app
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Only Pillow is an external dependency; the GUI uses Python's bundled Tkinter. Tests use generated Pillow images and do not capture your screen. They cover empty/full/partial fills, mana colors, hue wraparound, gradients, text occlusion, sparse noise, invalid regions, settings validation/round-trip, and alert cooldown/recovery.

Windows manual acceptance: select both bars, cancel a selection, test both tones, observe full/partial/empty values, trigger both thresholds, stop/restart, then close/reopen to confirm saved settings. Test at your usual Windows display scale. Automated tests in the development Linux environment cannot verify Windows capture, DPI behavior, launcher execution, or audible output.


## Route hunting for Tibia Origins (experimental)

This first hunting version supports **multiple named routes that you record manually**, minimap walking, repeated target-next actions, and optional healing/mana hotkeys. Tibia Origins handles looting automatically, so the app sends no loot key. You can walk with WASD while recording; movement playback uses minimap clicks rather than timed WASD presses.

The hunting controls open in a separate window with a scrollbar on shorter displays. The monitor window hides while these controls are open. The hunter independently reads your saved bar regions; you do not need to start the monitor first. Your saved monitor sound-alert settings also apply during hunting, alongside the separate resource-action thresholds and critical-health stop described below.

### Set up the game and regions

1. Keep the game in windowed/borderless mode, on the primary monitor. Keep its position, size, minimap zoom, map theme, and display scaling fixed. Configure **F** as your target-next-creature action. Keep chat input closed while hunting so hotkeys act on the game.
2. Select the health/mana regions and colors in the monitor as before. Verify their readings. Click **Route hunting…**.
3. Click **1. Select minimap**. Drag around the minimap interior only, excluding buttons and borders. Maximum size is 240×240 pixels. Hide other windows that cover the game. Changing this calibration clears recorded checkpoints, player-center calibration, and the battle-list calibration.
4. Click **2. Mark player center** and click the center of your player marker on the minimap. The player marker must stay centered as the map scrolls. If your client allows manually panning the minimap, recenter it first. The center must be at least 13 pixels from each edge.
5. Go somewhere with **no creatures in the battle list**. Click **3. Select EMPTY battle list** and select its content area (at least 25×25 pixels), excluding headings, clocks, and animated borders. This snapshot is the empty reference. It must include the area where the first creature row will appear.

The app treats changes from this reference as a nonempty battle list. It cannot distinguish creatures from players, decorations, filters, or other changed UI elements. Configure your battle list to show the creatures you want to hunt. Test it before using a route.

### Record several routes

1. Type a name such as `Rats south loop` and click **Save new route**.
2. Stand at the desired first checkpoint. Click **Record / append (3s)** and immediately switch to the game window. After three seconds, that exact foreground window is bound for recording.
3. While standing still, press **F8** once to save the first checkpoint. Walk manually to the next location, stop, and press F8 again. Continue along your route. The app saves every checkpoint immediately.
4. Use **short, nearby checkpoints**: each destination and its surrounding map patch must be visible in the minimap from the preceding checkpoint. Record near corners to avoid blocked direct paths. Choose locations with distinctive terrain; featureless areas or repeated patterns are rejected or may fail to match later.
5. For a loop, finish near the start so the first checkpoint is visible from the final checkpoint. Do not record an identical first/last checkpoint unnecessarily. All checkpoints must be on the **same floor**.
6. Press **F10** to end recording. Restore the hunting window from the taskbar to see your saved checkpoint list.
7. Create another name with **Save new route** to record a different route. Use the dropdown to switch routes. **Record / append** adds to the chosen route. Select a checkpoint and click **Delete checkpoint** to remove a mistake.

Reserve **F8 and F10** in the game; unbind them from other game actions. They are polled while the hunting window is open and may still be seen by the game. Recording stops if the game loses focus or moves. Binding lasts only for the current session; window handles are not persisted. The recorded game-window geometry is saved and checked again when you start or append.

### Configure healing and mana

- Suggested mapping: **F1 = your heal spell or health item**, **F2 = your mana item/spell**. Assign those actions inside your game client first. You may choose other single keys in the app. Supported: A–Z, 0–9, F1–F12, ESC, SPACE. F8, F10, and ESC are reserved; target/heal/mana keys must be different. Key combinations and clicking inventory items are not supported.
- Healing and mana actions default **off**. Use **Test key (3s)** beside each action, switch to the game, and verify it performs the intended action. Enable resource actions only after testing. No spell or item is assigned automatically by the app.
- Defaults: heal at/below **45%**, mana at/below **30%**, two seconds between repeats **per action**. Healing takes priority if both are due. Set cooldowns for your server's actual spell/item timing.
- At/below **15% health**, the hunter tries a due, enabled heal, then stops hunting and cancels walking. This is a stop for manual intervention, not a logout or escape route. Adjust the critical threshold for your character.

### Run a recorded hunt

1. Select your route and stand at its first checkpoint, or close enough that its landmark is visible on the minimap. The route always starts at checkpoint 1; it does not resume from an arbitrary point.
2. Enable **Loop route** for repeated circuits, or disable it to finish once. Save settings.
3. Click **Start hunt (3s)** and switch to the game within three seconds. The app binds to that exact window and begins. Start with a short, supervised route to verify the setup.
4. The hunter matches the next minimap landmark and clicks its current screen position. It confirms arrival visually before advancing. It retries walking clicks every two seconds until arrival or timeout.
5. When the battle list differs from its empty reference, it sends **ESC** to cancel walking, then **F** to target. It repeats the target key every five seconds by default. This can cycle targets; adjust **Target next interval** to match your client's targeting behavior. It waits for the battle list to remain empty for one second, then resumes the route. It does not read individual monster HP or confirm kills directly.
6. **F10 stops recording/hunting**, including during image matching. Switching away from the bound game or moving/resizing it also stops hunting. Stopping sends ESC only when the bound game is still foreground, to cancel an outstanding walk. Verify ESC cancels click-to-walk in your client. The app never forces the game back into focus. Already-issued game movement or attacks may continue according to the client's behavior.

### Route limitations and troubleshooting

- **This is a beta, not a verified unattended hunter.** It has automated image/state-machine tests, but Windows input, minimap rendering, and actual Tibia Origins combat must be checked on your PC. No live-client compatibility has been verified here.
- **Missing/ambiguous checkpoint:** hunting stops rather than clicking a guessed location. Restore the recorded minimap zoom/theme/floor, move closer to the next checkpoint, or record denser checkpoints in more distinctive terrain. Markers and map overlays can obscure landmarks.
- **Walking timeout:** hunting stops after 45 seconds of travel toward one checkpoint (combat time is excluded). An obstruction, unreachable tile, or mismatched location may be responsible. There is no automatic unsticking or path search around doors.
- **Always fighting:** capture the empty battle-list reference again with no creatures, remove animated UI elements from the region, and check battle-list filters. The changed-fraction threshold defaults to 0.02 (2%). Raising it can ignore noise but may miss creatures.
- **Never fighting:** check that the region includes creature rows and lower the changed-fraction threshold if needed. No target-highlight or corpse recognition is implemented.
- **Game window/layout changed:** restore the recorded layout. If you cannot, reselect your health/mana regions and minimap, mark the player center, select the empty battle list, and re-record routes. Routes share one minimap/battle layout; there are no separate layouts per route.
- Supported routes stay on **one floor**. Stairs, ladders, teleports, doors, bank/depot trips, restocking, weight/supply checks, death recovery, and automatic map zoom changes are not implemented.
- Any screen-based readings can be wrong if the game is covered, minimized, or rendered differently. Focus checks prevent sending input to another foreground window, but cannot detect every in-game menu, chat box, overlay, or incorrect region selection. Keep chat and game menus closed.
- You must click the actual game during each three-second countdown, not a terminal or other app. The selected window's title appears in status when you restore the hunting window. Windows may block input to an elevated game; run both normally, at the same privilege level.

Routes, embedded landmark images, empty battle-list reference, and hunting settings are saved at `%APPDATA%\HealthManaMonitor\routes.json`. Close the app before backing up or replacing this file. Your health/mana settings remain in the separate `settings.json`. No network connection is used by hunting; the first-time Pillow install requires one.

### Additional validation

The route tests cover a scrolling synthetic minimap driving an actual two-checkpoint route, recorded-marker occlusion, repeated/absent landmarks, empty-battle image differences, multiple saved routes, invalid settings, combat interruption, health/mana priorities and cooldowns, loop completion, missing checkpoints, stuck timeout, and stop/focus changes during matching. Run all tests with the command in the earlier test section.

Windows manual check before a hunt: verify F8 records and F10 stops; confirm each tested action key; record and replay a short two-checkpoint route without creatures; verify battle-list detection when a creature appears; verify resuming after the list empties; confirm switching away and moving the game stops input; reopen the app to confirm routes/settings persist. Do not treat passing synthetic tests as proof of live-client behavior.
