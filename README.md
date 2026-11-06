# Health & Mana Monitor for Windows

A small Python desktop app that reads two visible horizontal screen bars with Pillow and shows estimated percentages. Select health and mana regions, choose their fill colors, and set separate low-resource sound thresholds. It reads screenshots only; it does not read game memory or send game inputs.

## Download and run on Windows (first time)

1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/windows/>. In the installer, keep **pip**, **Tcl/Tk**, and the **Python launcher** enabled. If offered, select **Add Python to PATH**.
2. Download [the Windows app ZIP](https://github.com/jasonnhermanson/TibiaBot/archive/refs/heads/health-mana-monitor.zip) and save it in Downloads. Sign in to GitHub if needed. Right-click it → **Extract All…** → **Extract**. Open the extracted folder containing `launch_windows.bat`.
   - You can also visit <https://github.com/jasonnhermanson/TibiaBot>, select the `health-mana-monitor` branch, and click **Code → Download ZIP**, then extract it.
3. Double-click **launch_windows.bat** (it may appear as `launch_windows` if extensions are hidden). Do not run it from inside the ZIP. The first launch creates a local `.venv` and downloads Pillow, so it needs internet access. Later launches reuse it.
4. Keep the console open while using the app. If setup fails, the console stays open so you can read the error. You do not need administrator access.

This is source code with a launcher, not a standalone `.exe`.

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
