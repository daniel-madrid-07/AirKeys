# AirKeys Guide

Invisible mouse and keyboard with one webcam. Three modes: **Mouse**, **Gaming**, **Keyboard**.

---

## 1. Place the camera

Camera placement is what affects accuracy the most.

| Mode | Best camera position |
|------|----------------------|
| **Mouse only** | Sideways / low, looking at your hand across the desk. Very comfortable. |
| **Keyboard** | **Elevated at ~45–60°**, in front and above, looking down at your hands. It sees the vertical finger strike *and* where each key is. |
| **Gaming** (mouse+keys) | The same ~45° front-above spot works for both hands. |

> General recommendation: a webcam on an arm/tripod **elevated, angled ~45–60° down** over the desk, in front-above your hands, covers all three modes. Perfectly vertical (90°) is NOT ideal: it loses the vertical strike.

**Orientation.** An overhead-mounted camera usually comes out rotated. Fix it live in **Settings → Camera**:
- **Rotate image**: 0 / 90 / 180 / 270 — until your hands look natural (fingers pointing up, left on the left).
- **Mirror horizontally**: if left/right are swapped.
- **Camera**: pick the right webcam if you have several (DroidCam, OBS, etc.).

**Important:** keep rotation/mirror fixed and **recalibrate** (mouse and tap) in that position. They must match between calibrating, recording and using.

Good light and a matte desk surface help.

---

## 2. Start

- **Installed (.exe)**: open **AirKeys** from the Start menu or desktop.
- **From source**: double-click `run.bat`, or `python airkeys.py`.

The window opens with the camera already live. Pick a mode and press **Start**.
Every mode starts in **test mode** (it does not control your real mouse/keyboard).
Turn on **Real control** when you trust it.

---

## 3. MOUSE mode

1. Settings → tools → **Calibrate mouse**: two gestures when prompted (hand to the
   **right**, then hand **forward**). ~8 seconds. Once per camera position.
2. Start **Mouse** mode. Neutral pose = **fist**. Gestures:
   - **Fist** + move hand → moves the cursor (relative, like a real mouse).
   - **Open the thumb** away from the hand → **left click** (held while open).
   - **Extend the index** finger → **right click** (held while extended).
   - **Flat hand** (all fingers straight) → freezes the cursor (reposition freely).

The telemetry panel shows the live thumb/index meters and the threshold markers —
watch them to tune the click thresholds in Settings (they apply live).

Feel: `MOUSE_GAIN` (sensitivity), `MOUSE_SMOOTH` (smoothing), `MOUSE_DEADZONE`
(idle jitter), `MOUSE_ACCEL` (pointer acceleration).

---

## 4. GAMING mode (mouse + keys, no training)

- **Right hand** = mouse (same as above).
- **Left hand** = held keys. Each finger is one key; **finger down** presses and
  holds it (like holding W to run).
- Default mapping (`GAMING_KEYS` in settings.json):
  pinky=Shift, ring=A, middle=W, index=D, thumb=Space.

No training needed.

---

## 5. Full KEYBOARD mode (typing letters)

The hard one. Types letters on an empty desk. **Needs training** with your own
data (everyone types differently).

1. Camera at ~45° (see above).
2. **Record keyboard** (Settings → tools): follow the metronome, tap each shown
   letter in the air. Do several sessions (more data = better).
3. **Calibrate tap**: copy the suggested thresholds into `settings.json`.
4. **Train keyboard**.
5. Start **Keyboard** mode: test first, then real control.

> Realistic expectations: keyboard mode is research-grade. Accuracy depends on
> camera placement and how much data you record. Mouse and Gaming work untrained.

---

## 6. Settings (`settings.json`)

Copy `settings.example.json` to `settings.json` (next to the app) and change
anything. Any value in `config.py` can be overridden. Examples:

```json
{ "MOUSE_HAND": "Left", "MOUSE_GAIN": 1.4, "CAM_NAME": "Logitech" }
```

The UI edits the common ones live.

---

## 7. Troubleshooting

- **Wrong camera / camera not found (DroidCam, OBS)**: pick it in Settings →
  Camera, or set `CAM_NAME` with part of your webcam's name. `python -m
  tools.probe_cam` lists working backends/indices.
- **Cursor jitters at rest**: raise `MOUSE_DEADZONE`.
- **Jerky movement**: lower `MOUSE_SMOOTH`.
- **Left click misfires / won't fire**: watch the *thumb* meter while opening your
  thumb and set the left-click threshold just below its peak. Right click: same
  with the *index* meter.
- **Keyboard types nothing**: almost always the camera (can't see the vertical
  strike) or too little data. Camera at ~45° and record more.
- **Left/right hands swapped**: set `"SWAP_HANDS": true`.
- **Camera paused ("click to resume")**: an external tool took the camera; close
  it and click the video area.
