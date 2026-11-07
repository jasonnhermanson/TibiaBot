# Origins coordinate routes — first setup

This optional mode uses the Lua interfaces you verified in the Tibia Origins terminal to read exact coordinates, HP, mana, and the current target. The Python app records and runs named routes. A small Lua companion passes observations and a limited set of commands through local JSON files.

This is a new beta. The automated suite exercises the actual Lua companion in Lua 5.1 with a mock client, including a Python/Lua protocol round trip. The complete setup, resource-file behavior, Windows input, and live movement still need checking in your Origins client. Start with a short route in an empty area using **Walk only**.

## 1. Download and launch the update

1. Close the previous monitor app.
2. Download the [current app ZIP](https://github.com/jasonnhermanson/TibiaBot/archive/refs/heads/health-mana-monitor.zip).
3. Right-click it in Downloads → **Extract All**. Open the extracted folder containing `launch_windows.bat`, then double-click that launcher. Run it from the extracted folder, not inside the ZIP.
4. Click **Coordinate routes (Origins)…** in the monitor. This opens the new coordinate controls. The earlier **Route hunting…** button is the separate screen/minimap-based beta.

The runtime dependencies remain Python 3.11+, Tkinter, and Pillow. The Lua script runs in the game; you do not need to install Lua separately. Your previous bar settings and pixel-route profiles remain in their existing files.

## 2. Install and load the companion script

1. Click **Install bridge in game folder…**.
2. Select your actual game folder. From your screenshot, it is `%LOCALAPPDATA%\TibiaOrigins` (normally `C:\Users\Owner\AppData\Local\TibiaOrigins`). It must contain the `modules` and `mods` folders and the game EXE.
3. The installer copies only `client_bridge/origins_bridge.lua` from this app into the game's `mods` folder as `origins_bridge.lua`. If updating a different existing bridge file, it first creates `origins_bridge.lua.bak`. It does not change `init.lua`, existing modules, or the game executable.
4. The installer puts this command on your clipboard. Open the game's terminal with **Ctrl+T**, paste, and press Enter:

```lua
dofile('/mods/origins_bridge.lua'); return OriginsBridge.folder
```

5. The terminal should return a folder path. It is the **client's writable resource folder**, which may differ from the game installation folder. Copy that path into **Bridge folder** in the Python window (or use Browse to select it), then click **Connect**.
6. Verify that the app displays the same position, HP, mana, and target as the game. Loading or connecting the bridge does not arm movement or attack. When offline, the app displays Offline until you log in.

Load the script once after every game-client restart. Reloading it replaces its previous timer and disarms any running hunt. To display the folder again:

```lua
return OriginsBridge.folder
```

If the command reports a missing file, verify the installed file is `TibiaOrigins\mods\origins_bridge.lua`, not `origins_bridge.lua.txt`. If it reports an unreadable script, Lua error, or unavailable function, copy the exact error for diagnosis. A visible function name alone does not guarantee that this particular client accepts every operation. This version uses the normal client resource loader; it does not alter the client's protected scripts.

## 3. Record multiple routes

1. Type a new name, such as `Rats north`, then click **Create route**.
2. Stand at its first location and click **Record / append**. The window minimizes so you can walk manually in the game.
3. The app immediately records your starting coordinate, then adds checkpoints about every **three tiles** and at turns it observes. Sampling runs about five times per second. Press **F8** to force a checkpoint at a precise corner or stopping point. This recording step sends no movement or attack commands.
4. Stay on one floor. Press **F10** when finished. The final observed location is added and checkpoints are saved.
5. Restore the Python window from the taskbar. The list shows each checkpoint as `Walk to x, y, floor z`. You can delete a selected checkpoint, add your current position, or append a three-second wait.
6. For a loop, make the last checkpoint near the start, with a reachable return path. Create additional route names for other hunts. Select routes from the dropdown.

Recording appends to the selected route; it does not silently replace it. Start recording near the end when extending a route. The recorder stops at a floor change, character/session change, or a large position jump that could indicate a teleport or missed movement. A few tiles can pass between observations on fast characters, so add points manually at important corners. Save files contain up to 100 named routes, 1000 actions per route.

## 4. Check a route without targeting

1. Leave **Walk only (no targeting)** checked and healing/mana actions disabled for the first test.
2. Select a short two-checkpoint route. Stand at the start, on the recorded floor.
3. Disable **Loop route** for this test. Click **Save settings**.
4. Click **Start route (3s)** and switch to the actual **TibiaOrigins game window** within three seconds. Keep game chat, menus, and the terminal closed during playback.
5. The controller arms the bridge, asks the client's local player to walk to each destination, and checks actual coordinates before advancing. It uses `LocalPlayer:autoWalk(destination)`; the similarly named `g_game.autoWalk` accepts a list of directions and is not used as a coordinate function.
6. **F10 stops**. So do switching away, moving/resizing the bound game window, disconnecting, a floor/character change, a command rejection, or a failed/stale bridge connection.

The route always starts at action 1. Destinations must be within 80 tiles of the current position. An unchanged position for eight seconds, or exceeding the configured walking timeout (default 45 seconds), stops playback. Wait actions continue checking resources and stop conditions. There is no nearest-waypoint resume or automatic recovery around doors.

## 5. Enable hunting and resource actions

After the short walking test succeeds:

- Uncheck **Walk only** to enable targeting. The bridge must expose creature enumeration and attack functions, as well as destination walking. Missing capabilities produce an explicit error before playback.
- The app chooses a nearby visible monster when it has no valid target, then **retains the current valid monster target** while it remains alive. It does not periodically press F or cycle healthy targets. Travel resumes when no eligible target/monster remains.
- Monsters named with `Training Machine` or `Training Dummy` are excluded, case-insensitively, by both Python and the Lua bridge. NPCs and players are excluded using the client's monster classification. Other monsters are eligible; a configurable per-species allowlist is not implemented yet.
- Attack selection cancels route walking before asking the client to attack that specific creature ID. Use the client's appropriate chase/follow-attack mode for melee. This version does not implement kiting or spell attack combinations. If target HP stops changing for the configured timeout, the hunt stops for manual intervention.
- Assign your actual healing and mana actions inside the game. Suggested keys are **F1** and **F2**, but the app does not bind spells or items for you. Use the existing pixel-hunting window's Test key controls, or test your keys manually in game, before enabling them here.
- Healing/mana actions default off. Their thresholds use **exact client HP/mana totals**. Defaults are heal at/below 45%, mana at/below 30%, two seconds between repeats per action. Health has priority when both actions are due. Resource checks continue while waiting for a navigation-command acknowledgement.
- A critical-health threshold of 15% stops the hunt after a due, enabled heal attempt. It is not an escape or logout action. Set thresholds and cooldowns for your character and server.
- Resource actions send the configured single key through Windows to the bound foreground game window. Supported keys are A–Z, 0–9, F1–F12, ESC, SPACE; F8, F10, and ESC are reserved and heal/mana keys must differ. Keep chat and menus closed.
- The monitor's saved low-resource sound settings also apply during coordinate playback, using exact percentages. Auto-looting is supplied by your server, so no loot key is sent.

## Stop behavior and saved files

- F10 works through both the Python window's key polling and the companion's game key binding. Reserve F8/F10 in your client so they do not trigger other actions. F10 stops recording or playback; it does not unload the bridge's observation timer.
- Stopping asks the client to cancel automatic walking and attack/follow. The companion requires continuing, fresh controller heartbeats; if Python closes or freezes, it disarms and cancels actions in roughly two seconds. Delayed game/network responses remain possible. An internal client error or a suspended client can only be handled when the client resumes executing its timer.
- Commands carry a bridge-session ID, controller ID, acknowledgement ID, and observed sequence number. Old-session, duplicate, and expired commands are not replayed. A command rejected by the client stops the hunt rather than advancing the route.
- The coordinate library and settings are saved at `%APPDATA%\HealthManaMonitor\coordinate_routes.json`.
- The bridge uses three JSON files in the resource folder it returns: `origins_hunt_state.json`, `origins_hunt_heartbeat.json`, and `origins_hunt_command.json`. State contains coordinates, HP/mana, a numeric character ID, and visible monster/target data. It does not read login credentials or send data over the network.
- Support is for **one running Origins client and one controller** per bridge folder. Two clients writing the same files will invalidate the session checks.
- To disarm from the game's terminal:

```lua
OriginsBridge.stop('Stopped manually')
```

- To stop the timer and unload its bindings:

```lua
OriginsBridge.shutdown()
```

After shutting down the companion, close the Python app and optionally remove `mods\origins_bridge.lua` and the three bridge JSON files. Client updates may remove the added bridge file; reinstall and load it again if needed.

## Known scope and validation

This mode supports saved coordinate walk/wait routes on a single floor, exact resource readings, target retention, basic nearest-monster selection, cooldowns, command acknowledgements, and stopping on stale data or failed progress. It does not yet handle stairs/teleports, restocking, depot runs, supplies, death recovery, per-monster attack settings, or multiple concurrent clients. Screen-based routes are separate profiles and are not automatically converted into coordinates.

Run the full development suite (including actual Lua 5.1 execution) from the extracted app folder:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Lupa is needed only for Lua tests, not for running the app. Without it, the Lua integration tests are explicitly skipped; the other tests still run. The suite includes original Pillow image tests, route storage/recording tests, exact-resource control, target retention/training exclusion, the Python-to-Lua file protocol, duplicate/expired commands, lease expiry, F10, rejected destinations, disconnects, and client reloads.

Manual Origins acceptance: load the script and verify live values; record/reopen two named routes; run a two-checkpoint route in Walk only mode; stop with F10 and by switching windows; then test one monster, retention until death, resuming movement, and resource actions. Confirm the returned resource folder is writable and the live client accepts the destination API before relying on longer routes.
