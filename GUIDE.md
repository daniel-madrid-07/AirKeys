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

Types letters on an empty desk. **No training needed** (default geometric decoder):

1. Camera elevated at ~45-60° in front-above (see section 1).
2. Start **Keyboard** mode.
3. **Calibrate**: rest both hands on the desk in home position (ASDF / JKL;) and
   hold still for ~1 second. The status hint switches to "calibrated".
4. Type **slowly and deliberately**: lift the finger and strike down on the
   imaginary key. Thumbs = space. Each finger only types its own touch-typing
   columns (index right = Y U H J N M, etc.).
5. Resting both hands again recalibrates at any time (do it whenever you move
   your hands or the camera).

How it works: press depth is invisible to a single camera, so AirKeys never
measures it. Resting hands = touching the desk, which anchors the surface
appearance per finger; a keystroke is its temporal signature (fast drop, hard
stop, lift); the key comes from where the fingertip landed on a QWERTY grid
anchored to your calibrated home position and scaled by your own finger spacing.

Tuning (settings.json): `KB_VEL_ENTER` (strike sensitivity: lower = easier to
trigger), `KB_MIN_DROP` (minimum finger travel), `KB_ROW_SCALE` (vertical
distance between rows as seen by your camera), `KB_MAX_KEY_DIST` (how far from
a key center still counts).

**Optional trained model** (the previous pipeline, for tinkerers): record with
the metronome (`Record keyboard`), `Calibrate tap`, `Train keyboard`, and set
`"KB_DECODER": "model"` in settings.json.

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
- **Keyboard types nothing**: check the hint says "calibrated" (rest both hands
  still on the desk first), strike faster/more vertically, or lower `KB_VEL_ENTER`.
- **Keyboard types too much / wrong keys**: raise `KB_VEL_ENTER` or `KB_MIN_DROP`;
  type slower; adjust `KB_ROW_SCALE` if top/bottom rows get confused.
- **Left/right hands swapped**: set `"SWAP_HANDS": true`.
- **Camera paused ("click to resume")**: an external tool took the camera; close
  it and click the video area.
