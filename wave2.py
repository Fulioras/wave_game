import pyglet
from pyglet import shapes
from pyglet.window import key
import math
import time
import collections
import os
import subprocess
import glob

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False
    print("[WARNING] pyserial not installed - Arduino signalling disabled. "
          "Run: pip install pyserial")

# ---------------------------------------------------------------------------
# ARDUINO CONFIGURATION
# ---------------------------------------------------------------------------
# Set ARDUINO_PORT to a specific port string (e.g. "/dev/ttyUSB0", "COM3")
# or leave as None to auto-detect the first Arduino-like device.
ARDUINO_PORT     = None
ARDUINO_BAUDRATE = 9600

# Bytes sent to the Arduino on win / loss
ARDUINO_WIN_MSG  = b'W'
ARDUINO_LOSE_MSG = b'L'


def _find_arduino_port():
    """Return the first likely Arduino serial port, or None."""
    candidates = (
        glob.glob("/dev/ttyUSB*") +
        glob.glob("/dev/ttyACM*") +
        glob.glob("/dev/cu.usbmodem*") +
        glob.glob("/dev/cu.usbserial*") +
        glob.glob("COM[0-9]*")
    )
    return candidates[0] if candidates else None


def _open_arduino():
    """Open and return a serial.Serial connected to the Arduino, or None."""
    if not _SERIAL_AVAILABLE:
        return None
    port = ARDUINO_PORT or _find_arduino_port()
    if port is None:
        print("[WARNING] No Arduino port found - serial signalling disabled.")
        return None
    try:
        conn = serial.Serial(port, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)          # wait for Arduino reset after DTR toggle
        print(f"[INFO] Arduino connected on {port} at {ARDUINO_BAUDRATE} baud.")
        return conn
    except Exception as e:
        print(f"[WARNING] Could not open Arduino on {port}: {e}")
        return None


def _send_arduino(conn, msg):
    """Send msg (bytes) to Arduino; silently ignore errors."""
    if conn is None:
        return
    try:
        conn.write(msg)
        conn.flush()
    except Exception as e:
        print(f"[WARNING] Arduino write failed: {e}")


# ---------------------------------------------------------------------------
# MEDIA FILES  -  place these files next to game.py (or set full paths)
# ---------------------------------------------------------------------------
SPLASH_IMAGE   = "start.png"          # shown on startup
INTRO_VIDEO    = "intro.mp4"           # plays before the game
WIN_VIDEO      = "win.mp4"             # plays when players win
LOSE_VIDEO     = "lose.mp4"            # plays when players lose

# Video player command – ffplay plays fullscreen with no controls/border.
# Swap 'ffplay' for 'mpv --fullscreen' or 'vlc --fullscreen' if preferred.
VIDEO_PLAYER_CMD = [
    "ffplay",
    "-fs",           # fullscreen
    "-autoexit",     # exit when video ends
    "-noborder",
    "-loglevel", "quiet",
]

# ---------------------------------------------------------------------------
# GAME CONFIGURATION
# ---------------------------------------------------------------------------
SYNC_DURATION = 5.0
INPUT_DELAY   = 2
WAVE_RESOLUTION = 250

IDLE_RESET_TIME   = 4.0
IDLE_RETURN_SPEED = 4.0
IDLE_WAVE_SETTLE  = 1.2

PULSE_SPEED        = 1.5
NEON_GLOW_STRENGTH = 0.6

SYNC_FREQ_TOLERANCE  = 0.10
SYNC_PHASE_TOLERANCE = 0.5

FLAG_WIN_THRESHOLD = 0.50   # sync fraction needed to win

# --- THICKNESS & SIZING RATIOS ---
WAVE_GLOW_THICK_RATIO   = 0.020
WAVE_CORE_THICK_RATIO   = 0.014
WAVE_CENTER_THICK_RATIO = 0.004
PHASOR_LINE_THICK_RATIO = 0.003
AXIS_LINE_THICK_RATIO   = 0.002
ARROW_HEAD_SIZE_RATIO   = 0.018
WAVE_END_DOT_RATIO      = 0.007
WAVE_END_DOT_CORE_RATIO = 0.0035

# --- GRID ---
GRID_CELL_W = 120
GRID_CELL_H = 240
GRID_STYLE  = "endless"
GRID_COLOR  = (255, 255, 255, 75)

PULSE_MAX_RADIUS_RATIO = 0.25
PULSE_INTERVAL         = 0.9

WAVE_WIDTH_PERCENT = 0.65
AXIS_LABEL_X = "Laikas (t)"
AXIS_LABEL_Y = "Itampa (I)"

P1_COLOR = (120, 200, 120)
P2_COLOR = (0, 150, 200)
WHITE    = (255, 255, 255)

# ---------------------------------------------------------------------------
# GAME STATES
# ---------------------------------------------------------------------------
STATE_SPLASH       = "splash"
STATE_INTRO_VIDEO  = "intro_video"
STATE_PLAYING      = "playing"
STATE_RESULT_VIDEO = "result_video"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _load_image(path):
    if not os.path.exists(path):
        print(f"[WARNING] Image file not found: {path}")
        return None
    try:
        return pyglet.image.load(path)
    except Exception as e:
        print(f"[WARNING] Could not load image {path}: {e}")
        return None


def _launch_video(path):
    """Launch video fullscreen via ffplay subprocess. Returns Popen or None."""
    if not os.path.exists(path):
        print(f"[WARNING] Video file not found: {path}")
        return None
    try:
        return subprocess.Popen(VIDEO_PLAYER_CMD + [path])
    except Exception as e:
        print(f"[WARNING] Could not launch video {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# PULSE RING
# ---------------------------------------------------------------------------

class PulseRing:
    __slots__ = ['color', 'circle', 'active', 'radius', 'max_radius']

    def __init__(self, color, batch):
        self.color  = color
        self.circle = shapes.Circle(0, 0, 1, color=(*color, 0), batch=batch)
        self.active = False
        self.radius = 0.0
        self.max_radius = 1.0

    def fire(self, x, y, max_radius):
        self.circle.x   = x
        self.circle.y   = y
        self.max_radius = max_radius
        self.radius     = 0.0
        self.active     = True

    def update(self, dt, expand_speed):
        if not self.active:
            self.circle.visible = False
            return
        self.radius += expand_speed * dt
        if self.radius >= self.max_radius:
            self.active = False
            self.circle.visible = False
            return
        self.circle.radius  = self.radius
        frac       = self.radius / self.max_radius
        fade_start = 0.25
        fade       = max(0.0, 1.0 - max(0.0, frac - fade_start) / (1.0 - fade_start))
        self.circle.opacity = int(160 * fade)
        self.circle.visible = True


# ---------------------------------------------------------------------------
# PLAYER STATE
# ---------------------------------------------------------------------------

class PlayerState:
    SETTLE_DURATION = 0.55

    def __init__(self, color, window_h, wave_w, wave_speed):
        self.color      = color
        self.window_h   = window_h
        self.wave_w     = wave_w
        self.wave_speed = wave_speed

        self.last_signal      = None
        self.last_input_time  = time.time()
        self.signal_queue     = collections.deque()
        self.points           = collections.deque()
        self.total_scroll     = 0.0

        self.current_y_norm    = 0.0
        self.current_direction = 1
        self.last_peak_time    = None

        self.ever_had_input   = False
        self.first_input_time = None

        self.frequency = 0.0
        self.phase     = 0.0

        self.arrow_angle   = 0.0
        self.display_angle = 0.0

        self._idle_returning = False
        self._idle_wave_from = 0.0
        self._idle_wave_t    = 0.0

        self.flag_raised = False

    def reset(self):
        self.last_signal      = None
        self.last_input_time  = time.time()
        self.signal_queue.clear()
        self.points.clear()
        self.total_scroll     = 0.0
        self.current_y_norm   = 0.0
        self.current_direction = 1
        self.last_peak_time   = None
        self.ever_had_input   = False
        self.first_input_time = None
        self.frequency        = 0.0
        self.phase            = 0.0
        self.arrow_angle      = 0.0
        self.display_angle    = 0.0
        self._idle_returning  = False
        self._idle_wave_from  = 0.0
        self._idle_wave_t     = 0.0
        self.flag_raised      = False

    def queue_signal(self, signal, current_time):
        if signal == self.last_signal:
            return
        self.last_signal     = signal
        self.last_input_time = current_time
        direction = 1 if signal == 'u' else -1

        if not self.ever_had_input:
            self.first_input_time = current_time
            self.ever_had_input   = True

        self.signal_queue.append((current_time + INPUT_DELAY, direction))

    def _calculate_wave_position(self, current_time):
        if not self.signal_queue:
            if self.last_peak_time is None:
                return 0.0, 0.0, self.arrow_angle
            else:
                predicted_peak_time = current_time + INPUT_DELAY
                half_period         = predicted_peak_time - self.last_peak_time
                time_since_peak     = current_time - self.last_peak_time

                if half_period > 0.001:
                    progress  = min(time_since_peak / half_period, 1.0)
                    y_norm    = self.current_direction * math.cos(progress * math.pi)
                    frequency = 1.0 / (half_period * 2)
                    if self.current_direction == 1:
                        target_angle = (math.pi / 2) + progress * math.pi
                    else:
                        target_angle = (3 * math.pi / 2) + progress * math.pi
                else:
                    y_norm = 0.0; frequency = 0.0; target_angle = self.arrow_angle
        else:
            next_peak_time, next_direction = self.signal_queue[0]

            if self.last_peak_time is None:
                time_since_queue = current_time - (self.first_input_time or current_time)
                total_rise_time  = INPUT_DELAY

                if total_rise_time > 0.001:
                    progress  = min(time_since_queue / total_rise_time, 1.0)
                    y_norm    = next_direction * math.sin(progress * math.pi / 2.0)
                    frequency = 1.0 / (total_rise_time * 2)
                    if next_direction == 1:
                        target_angle = progress * (math.pi / 2)
                    else:
                        target_angle = 2 * math.pi - progress * (math.pi / 2)
                else:
                    y_norm = 0.0; frequency = 0.0; target_angle = 0.0
            else:
                half_period   = next_peak_time - self.last_peak_time
                time_in_cycle = current_time - self.last_peak_time

                if half_period > 0.001:
                    progress  = min(time_in_cycle / half_period, 1.0)
                    y_norm    = self.current_direction * math.cos(progress * math.pi) if progress <= 1.0 else next_direction
                    frequency = 1.0 / (half_period * 2)
                    if self.current_direction == 1:
                        target_angle = (math.pi / 2) + progress * math.pi
                    else:
                        target_angle = (3 * math.pi / 2) + progress * math.pi
                else:
                    y_norm = self.current_y_norm; frequency = 0.0; target_angle = self.arrow_angle

        return y_norm, frequency, target_angle

    def update(self, dt, current_time, amplitude):
        idle = (current_time - self.last_input_time) > IDLE_RESET_TIME

        while self.signal_queue and current_time >= self.signal_queue[0][0]:
            fire_time, direction = self.signal_queue.popleft()
            self.last_peak_time    = fire_time
            self.current_direction = direction
            self._idle_returning   = False

        if idle and self.ever_had_input and not self._idle_returning:
            self._idle_returning  = True
            self._idle_wave_from  = self.current_y_norm
            self._idle_wave_t     = 0.0
            self.frequency        = 0.0
            self.last_signal      = None
            self.last_peak_time   = None
            self.first_input_time = None

        if self._idle_returning:
            self._idle_wave_t += dt
            wave_frac = min(self._idle_wave_t / IDLE_WAVE_SETTLE, 1.0)
            wave_ease = 1.0 - (1.0 - wave_frac) ** 3
            y_norm    = self._idle_wave_from * (1.0 - wave_ease)

            target_angle = round(self.arrow_angle / (2 * math.pi)) * 2 * math.pi
            diff  = target_angle - self.arrow_angle
            step  = IDLE_RETURN_SPEED * dt
            if abs(diff) <= step:
                self.arrow_angle = target_angle; arrow_done = True
            else:
                self.arrow_angle += math.copysign(step, diff); arrow_done = False

            if wave_frac >= 1.0 and arrow_done:
                self._idle_returning = False
                self.ever_had_input  = False
                self.arrow_angle     = 0.0
                y_norm               = 0.0

            self.current_y_norm = y_norm
            self.frequency      = 0.0
        else:
            y_norm, frequency, target_angle = self._calculate_wave_position(current_time)
            self.current_y_norm = y_norm
            self.frequency      = frequency
            self.arrow_angle    = target_angle

        self.display_angle = self.arrow_angle % (2 * math.pi)
        self.phase         = self.display_angle

        self.total_scroll += self.wave_speed * dt

        if self.total_scroll > 10000.0:
            for i in range(len(self.points)):
                x, y = self.points[i]
                self.points[i] = (x - self.total_scroll, y)
            self.total_scroll = 0.0

        new_y = (self.window_h / 2) + amplitude * self.current_y_norm
        self.points.append((self.wave_w + self.total_scroll, new_y))

        while self.points and (self.points[0][0] - self.total_scroll) < 0:
            self.points.popleft()


# ---------------------------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------------------------

class MuseumSyncGame(pyglet.window.Window):
    def __init__(self):
        super().__init__(fullscreen=True, caption="CESA-Baltic frequency convergence")

        diag = math.hypot(self.width, self.height)

        self.WAVE_GLOW_THICK     = max(2, int(diag * WAVE_GLOW_THICK_RATIO))
        self.WAVE_CORE_THICK     = max(1, int(diag * WAVE_CORE_THICK_RATIO))
        self.WAVE_CENTER_THICK   = max(1, int(diag * WAVE_CENTER_THICK_RATIO))
        self.PHASOR_LINE_THICK   = max(1, int(diag * PHASOR_LINE_THICK_RATIO))
        self.AXIS_LINE_THICK     = max(1, int(diag * AXIS_LINE_THICK_RATIO))
        self.ARROW_HEAD_SIZE     = max(8, int(diag * ARROW_HEAD_SIZE_RATIO))
        self.WAVE_END_DOT_R      = max(4, int(diag * WAVE_END_DOT_RATIO))
        self.WAVE_END_DOT_CORE_R = max(2, int(diag * WAVE_END_DOT_CORE_RATIO))

        self.PULSE_MAX_RADIUS = self.height * PULSE_MAX_RADIUS_RATIO
        self.PULSE_EXPAND_SPD = self.PULSE_MAX_RADIUS * PULSE_SPEED

        self.WAVE_AREA_W = self.width  * WAVE_WIDTH_PERCENT
        self.AMPLITUDE   = self.height * 0.18
        self.WAVE_SPEED  = self.width  * 0.22
        self.PH_CX       = self.WAVE_AREA_W + (self.width - self.WAVE_AREA_W) / 2
        self.PH_CY       = self.height / 2
        self.PH_RADIUS   = min(self.width - self.WAVE_AREA_W, self.height) * 0.35

        self.batch     = pyglet.graphics.Batch()
        self.fg_batch  = pyglet.graphics.Batch()
        self.top_batch = pyglet.graphics.Batch()

        self.p1 = PlayerState(P1_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)
        self.p2 = PlayerState(P2_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)

        self._build_game_ui(diag)

        # Media assets
        self._splash_image = _load_image(SPLASH_IMAGE)
        self._splash_sprite = None
        # Subprocess-based video playback (avoids pyglet media/wave bug)
        self._video_proc       = None   # Popen object for running video
        self._video_next_state = STATE_PLAYING

        # Arduino serial connection (opened once, kept for the lifetime of the app)
        self._arduino = _open_arduino()

        self.state = None
        self._set_state(STATE_SPLASH)

        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    # -----------------------------------------------------------------------
    # STATE MACHINE
    # -----------------------------------------------------------------------

    def _set_state(self, new_state, video_path=None):
        # Teardown
        if self.state == STATE_SPLASH:
            if self._splash_sprite:
                self._splash_sprite.delete()
                self._splash_sprite = None

        if self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            self._stop_video()

        self.state = new_state

        if new_state == STATE_SPLASH:
            self._show_splash()
        elif new_state == STATE_INTRO_VIDEO:
            self._play_video(INTRO_VIDEO, next_state=STATE_PLAYING)
        elif new_state == STATE_PLAYING:
            self._reset_game()
        elif new_state == STATE_RESULT_VIDEO:
            path = video_path or LOSE_VIDEO
            self._play_video(path, next_state=STATE_SPLASH)

    def _show_splash(self):
        if self._splash_image:
            iw, ih = self._splash_image.width, self._splash_image.height
            scale   = min(self.width / iw, self.height / ih)
            self._splash_sprite = pyglet.sprite.Sprite(self._splash_image)
            self._splash_sprite.scale = scale
            self._splash_sprite.x = (self.width  - iw * scale) / 2
            self._splash_sprite.y = (self.height - ih * scale) / 2

    def _play_video(self, path, next_state):
        self._video_next_state = next_state
        self._video_proc = _launch_video(path)
        if self._video_proc is None:
            # File missing or player unavailable — skip immediately
            pyglet.clock.schedule_once(lambda dt: self._set_state(next_state), 0)

    def _stop_video(self):
        if self._video_proc:
            try:
                self._video_proc.terminate()
                self._video_proc.wait(timeout=1)
            except Exception:
                pass
            self._video_proc = None

    def _reset_game(self):
        self.p1.reset()
        self.p2.reset()
        self.sync_timer      = 0.0
        self.last_sync_prog  = -1
        self.sync_label.text  = "READY"
        self.sync_label.color = (255, 255, 255, 255)
        self.p1_pulse_tmr = 0.0
        self.p2_pulse_tmr = 0.0
        for p in self.p1_pulses + self.p2_pulses:
            p.active = False
        self._update_flag_ui()

    # -----------------------------------------------------------------------
    # FLAG LOGIC
    # -----------------------------------------------------------------------

    def _update_flag_ui(self):
        p1_alpha = 220 if self.p1.flag_raised else 55
        p2_alpha = 220 if self.p2.flag_raised else 55
        self.p1_flag_box.color = (*P1_COLOR, p1_alpha)
        self.p2_flag_box.color = (*P2_COLOR, p2_alpha)

    def _check_flags(self):
        if not (self.p1.flag_raised and self.p2.flag_raised):
            return
        sync_frac = self.sync_timer / SYNC_DURATION
        won       = sync_frac >= FLAG_WIN_THRESHOLD
        # Signal the Arduino before starting the result video
        _send_arduino(self._arduino, ARDUINO_WIN_MSG if won else ARDUINO_LOSE_MSG)
        video = WIN_VIDEO if won else LOSE_VIDEO
        self._set_state(STATE_RESULT_VIDEO, video_path=video)

    # -----------------------------------------------------------------------
    # BUILD GAME UI
    # -----------------------------------------------------------------------

    def _build_game_ui(self, diag):
        self._create_background_grid()

        self.axis_h = shapes.Line(
            50, self.height / 2, self.WAVE_AREA_W + 20, self.height / 2,
            thickness=self.AXIS_LINE_THICK, color=(*WHITE, 255), batch=self.batch)
        self.axis_v = shapes.Line(
            50, self.height / 2 - self.AMPLITUDE - 20,
            50, self.height / 2 + self.AMPLITUDE + 20,
            thickness=self.AXIS_LINE_THICK, color=(*WHITE, 255), batch=self.batch)

        font_size = max(10, int(diag * 0.007))
        self.lbl_x = pyglet.text.Label(AXIS_LABEL_X, font_size=font_size,
                                        x=self.WAVE_AREA_W - 80, y=self.height / 2 - 30,
                                        batch=self.batch)
        self.lbl_y = pyglet.text.Label(AXIS_LABEL_Y, font_size=font_size,
                                        x=60, y=self.height / 2 + self.AMPLITUDE + 25,
                                        batch=self.batch)

        self.p1_layers = self._create_neon_wave(P1_COLOR)
        self.p2_layers = self._create_neon_wave(P2_COLOR)

        self.p1_dot_glow = shapes.Circle(0, 0, self.WAVE_END_DOT_R * 2,
                                          color=(*P1_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.fg_batch)
        self.p1_dot      = shapes.Circle(0, 0, self.WAVE_END_DOT_R,
                                          color=(*P1_COLOR, 255), batch=self.fg_batch)
        self.p1_dot_core = shapes.Circle(0, 0, self.WAVE_END_DOT_CORE_R,
                                          color=(*WHITE, 255), batch=self.top_batch)

        self.p2_dot_glow = shapes.Circle(0, 0, self.WAVE_END_DOT_R * 2,
                                          color=(*P2_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.fg_batch)
        self.p2_dot      = shapes.Circle(0, 0, self.WAVE_END_DOT_R,
                                          color=(*P2_COLOR, 255), batch=self.fg_batch)
        self.p2_dot_core = shapes.Circle(0, 0, self.WAVE_END_DOT_CORE_R,
                                          color=(*WHITE, 255), batch=self.top_batch)

        self.pizza_slice = shapes.Sector(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(255, 255, 255, 40), batch=self.batch)
        self.phasor_bg   = shapes.Circle(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(15, 15, 15), batch=self.batch)

        web_color   = (255, 255, 255, 75)
        ring_color  = (255, 255, 255, 100)
        spoke_thick = max(1, int(diag * 0.001))

        N_RIM = 120
        self.rim_lines = []
        for i in range(N_RIM):
            a0 = 2 * math.pi * i / N_RIM
            a1 = 2 * math.pi * (i + 1) / N_RIM
            self.rim_lines.append(shapes.Line(
                self.PH_CX + self.PH_RADIUS * math.cos(a0),
                self.PH_CY + self.PH_RADIUS * math.sin(a0),
                self.PH_CX + self.PH_RADIUS * math.cos(a1),
                self.PH_CY + self.PH_RADIUS * math.sin(a1),
                thickness=spoke_thick * 2, color=web_color, batch=self.batch))

        self.web_rings = []
        for frac in (0.25, 0.50, 0.75):
            r = self.PH_RADIUS * frac
            N = max(40, int(N_RIM * frac))
            for i in range(N):
                a0 = 2 * math.pi * i / N
                a1 = 2 * math.pi * (i + 1) / N
                self.web_rings.append(shapes.Line(
                    self.PH_CX + r * math.cos(a0), self.PH_CY + r * math.sin(a0),
                    self.PH_CX + r * math.cos(a1), self.PH_CY + r * math.sin(a1),
                    thickness=spoke_thick, color=ring_color, batch=self.batch))

        self.web_spokes = []
        for deg in range(0, 360, 45):
            a = math.radians(deg)
            self.web_spokes.append(shapes.Line(
                self.PH_CX, self.PH_CY,
                self.PH_CX + self.PH_RADIUS * math.cos(a),
                self.PH_CY + self.PH_RADIUS * math.sin(a),
                thickness=spoke_thick, color=web_color, batch=self.batch))

        lbl_font = max(9, int(diag * 0.006))
        lbl_off  = self.PH_RADIUS * 1.12
        self.degree_labels = []
        for deg, text in ((0, "0"), (90, "90"), (180, "180"), (270, "270")):
            a  = math.radians(deg)
            lx = self.PH_CX + lbl_off * math.cos(a)
            ly = self.PH_CY + lbl_off * math.sin(a)
            ax = 'left' if deg == 0 else ('right' if deg == 180 else 'center')
            ay = 'center' if deg in (0, 180) else ('bottom' if deg == 90 else 'top')
            self.degree_labels.append(pyglet.text.Label(
                text, font_size=lbl_font, x=lx, y=ly,
                anchor_x=ax, anchor_y=ay,
                color=(200, 200, 200, 180), batch=self.batch))

        # Player indicator circles
        indicator_radius = max(20, diag * 0.004)
        indicator_y = self.PH_CY - self.PH_RADIUS - self.height * 0.12
        self.p1_indicator_glow = shapes.Circle(
            self.PH_CX - 80, indicator_y, indicator_radius * 1.5,
            color=(*P1_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
        self.p1_indicator = shapes.Circle(
            self.PH_CX - 80, indicator_y, indicator_radius,
            color=(*P1_COLOR, 255), batch=self.batch)
        self.p1_indicator_label = pyglet.text.Label(
            "CESA", font_size=16,
            x=self.PH_CX - 80, y=indicator_y - 35,
            anchor_x='center', anchor_y='top', batch=self.batch)

        self.p2_indicator_glow = shapes.Circle(
            self.PH_CX + 80, indicator_y, indicator_radius * 1.5,
            color=(*P2_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
        self.p2_indicator = shapes.Circle(
            self.PH_CX + 80, indicator_y, indicator_radius,
            color=(*P2_COLOR, 255), batch=self.batch)
        self.p2_indicator_label = pyglet.text.Label(
            "Baltic", font_size=16,
            x=self.PH_CX + 80, y=indicator_y - 35,
            anchor_x='center', anchor_y='top', batch=self.batch)

        # Sync progress circle
        self.sync_circle = shapes.Circle(
            self.PH_CX, self.PH_CY, 0,
            color=(0, 255, 100, 100), batch=self.batch)

        self.p1_arrow = self._create_arrow(P1_COLOR)
        self.p2_arrow = self._create_arrow(P2_COLOR)

        label_font = max(16, int(diag * 0.015))
        self.sync_label = pyglet.text.Label(
            "READY", font_size=label_font,
            x=diag * 0.72, y=self.height - self.height * 0.1,
            anchor_x='center', anchor_y='top', batch=self.batch)
        self.last_sync_prog = -1

        # ---- FLAG UI ----
        flag_y    = indicator_y - self.height * 0.09
        flag_size = max(22, int(diag * 0.014))
        half      = flag_size // 2

        self.p1_flag_box = shapes.Rectangle(
            self.PH_CX - 80 - half, flag_y - half,
            flag_size, flag_size,
            color=(*P1_COLOR, 55), batch=self.batch)
        self.p1_flag_border = shapes.Box(
            self.PH_CX - 80 - half, flag_y - half,
            flag_size, flag_size,
            thickness=2, color=(*P1_COLOR, 180), batch=self.batch)
        self.p1_flag_label = pyglet.text.Label(
            "FLAG", font_size=max(8, flag_size // 3),
            x=self.PH_CX - 80, y=flag_y,
            anchor_x='center', anchor_y='center',
            color=(*P1_COLOR, 230), batch=self.batch)

        self.p2_flag_box = shapes.Rectangle(
            self.PH_CX + 80 - half, flag_y - half,
            flag_size, flag_size,
            color=(*P2_COLOR, 55), batch=self.batch)
        self.p2_flag_border = shapes.Box(
            self.PH_CX + 80 - half, flag_y - half,
            flag_size, flag_size,
            thickness=2, color=(*P2_COLOR, 180), batch=self.batch)
        self.p2_flag_label = pyglet.text.Label(
            "FLAG", font_size=max(8, flag_size // 3),
            x=self.PH_CX + 80, y=flag_y,
            anchor_x='center', anchor_y='center',
            color=(*P2_COLOR, 230), batch=self.batch)

        hint_font = max(9, int(diag * 0.005))
        self.p1_flag_hint = pyglet.text.Label(
            "[D]", font_size=hint_font,
            x=self.PH_CX - 80, y=flag_y - half - 4,
            anchor_x='center', anchor_y='top',
            color=(200, 200, 200, 130), batch=self.batch)
        self.p2_flag_hint = pyglet.text.Label(
            "[/]", font_size=hint_font,
            x=self.PH_CX + 80, y=flag_y - half - 4,
            anchor_x='center', anchor_y='top',
            color=(200, 200, 200, 130), batch=self.batch)

        # Pulses
        self.p1_pulses    = [PulseRing(P1_COLOR, self.fg_batch) for _ in range(3)]
        self.p2_pulses    = [PulseRing(P2_COLOR, self.fg_batch) for _ in range(3)]
        self.p1_pulse_idx = 0
        self.p2_pulse_idx = 0
        self.p1_pulse_tmr = 0.0
        self.p2_pulse_tmr = 0.0

        self.sync_timer = 0.0

    # -----------------------------------------------------------------------
    # GRID / WAVE / ARROW
    # -----------------------------------------------------------------------

    def _create_background_grid(self):
        self.bg_grid_lines = []
        if GRID_STYLE == "closed":
            min_y = int(self.height / 2 - self.AMPLITUDE - 20)
            max_y = int(self.height / 2 + self.AMPLITUDE + 20)
            min_x = 50; max_x = int(self.WAVE_AREA_W)
        else:
            min_y = 0; max_y = self.height
            min_x = 0; max_x = int(self.WAVE_AREA_W)

        cy = self.height / 2
        y_offsets = [0]
        i = 1
        while cy + i * GRID_CELL_H <= max_y: y_offsets.append(i * GRID_CELL_H); i += 1
        i = 1
        while cy - i * GRID_CELL_H >= min_y: y_offsets.append(-i * GRID_CELL_H); i += 1
        for offset in y_offsets:
            self.bg_grid_lines.append(shapes.Line(min_x, cy + offset, max_x, cy + offset,
                                                   color=GRID_COLOR, batch=self.batch))
        cx = max_x
        x_offsets = [0]
        i = 1
        while cx - i * GRID_CELL_W >= min_x: x_offsets.append(-i * GRID_CELL_W); i += 1
        for offset in x_offsets:
            self.bg_grid_lines.append(shapes.Line(cx + offset, min_y, cx + offset, max_y,
                                                   thickness=4, color=GRID_COLOR, batch=self.batch))
        if GRID_STYLE == "closed":
            for coords in [(min_x,min_y,max_x,min_y),(min_x,max_y,max_x,max_y),
                           (min_x,min_y,min_x,max_y),(max_x,min_y,max_x,max_y)]:
                self.bg_grid_lines.append(shapes.Line(*coords, thickness=2,
                                                       color=GRID_COLOR, batch=self.batch))

    def _create_neon_wave(self, color):
        return (
            [shapes.Line(0,0,0,0, thickness=self.WAVE_GLOW_THICK,
                         color=(*color, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
             for _ in range(WAVE_RESOLUTION)],
            [shapes.Line(0,0,0,0, thickness=self.WAVE_CORE_THICK,
                         color=(*color, 255), batch=self.batch)
             for _ in range(WAVE_RESOLUTION)],
            [shapes.Line(0,0,0,0, thickness=self.WAVE_CENTER_THICK,
                         color=(*WHITE, 255), batch=self.top_batch)
             for _ in range(WAVE_RESOLUTION)],
        )

    def _create_arrow(self, color):
        stem = shapes.Line(self.PH_CX, self.PH_CY, self.PH_CX, self.PH_CY + 1,
                           thickness=self.PHASOR_LINE_THICK, color=(*color, 255),
                           batch=self.batch)
        head = shapes.Triangle(self.PH_CX, self.PH_CY, self.PH_CX, self.PH_CY,
                                self.PH_CX, self.PH_CY, color=(*color, 255),
                                batch=self.batch)
        return {'stem': stem, 'head': head}

    def _update_arrow(self, arrow, angle):
        cos_a = math.cos(angle); sin_a = math.sin(angle)
        r       = self.PH_RADIUS * 0.85
        tip_x   = self.PH_CX + r * cos_a
        tip_y   = self.PH_CY + r * sin_a
        shaft_r = r - self.ARROW_HEAD_SIZE * 1.2
        shaft_x = self.PH_CX + shaft_r * cos_a
        shaft_y = self.PH_CY + shaft_r * sin_a
        arrow['stem'].x,  arrow['stem'].y  = self.PH_CX, self.PH_CY
        arrow['stem'].x2, arrow['stem'].y2 = shaft_x, shaft_y
        s = self.ARROW_HEAD_SIZE
        arrow['head'].x,  arrow['head'].y  = tip_x, tip_y
        arrow['head'].x2, arrow['head'].y2 = tip_x - s*math.cos(angle-0.45), tip_y - s*math.sin(angle-0.45)
        arrow['head'].x3, arrow['head'].y3 = tip_x - s*math.cos(angle+0.45), tip_y - s*math.sin(angle+0.45)

    def _tip_pos(self, player):
        return self.WAVE_AREA_W, (self.height / 2) + self.AMPLITUDE * player.current_y_norm

    def _fire_pulse(self, pulses, idx_attr, player):
        tx, ty = self._tip_pos(player)
        idx = getattr(self, idx_attr)
        pulses[idx].fire(tx, ty, self.PULSE_MAX_RADIUS)
        setattr(self, idx_attr, (idx + 1) % len(pulses))

    # -----------------------------------------------------------------------
    # INPUT
    # -----------------------------------------------------------------------

    def on_key_press(self, symbol, modifiers):
        t = time.time()

        if symbol == key.ESCAPE:
            self.close()

        # Splash: any key → intro video
        if self.state == STATE_SPLASH:
            if symbol != key.ESCAPE:
                self._set_state(STATE_INTRO_VIDEO)
            return

        # Videos are unskippable — consume all input except ESC
        if self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            return

        # Playing
        if self.state == STATE_PLAYING:
            if symbol == key.W:     self.p1.queue_signal('u', t)
            if symbol == key.S:     self.p1.queue_signal('d', t)
            if symbol == key.UP:    self.p2.queue_signal('u', t)
            if symbol == key.DOWN:  self.p2.queue_signal('d', t)

            # Flag buttons
            if symbol == key.D and not self.p1.flag_raised:
                self.p1.flag_raised = True
                self._update_flag_ui()
                self._check_flags()

            if symbol == key.SLASH and not self.p2.flag_raised:
                self.p2.flag_raised = True
                self._update_flag_ui()
                self._check_flags()

    # -----------------------------------------------------------------------
    # UPDATE LOOP
    # -----------------------------------------------------------------------

    def update(self, dt):
        # Poll video subprocess — transition when it exits
        if self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            if self._video_proc is not None and self._video_proc.poll() is not None:
                # Process has ended naturally
                self._video_proc = None
                next_st = getattr(self, '_video_next_state', STATE_SPLASH)
                self._set_state(next_st)
            return

        if self.state != STATE_PLAYING:
            return

        now = time.time()
        self.p1.update(dt, now, self.AMPLITUDE)
        self.p2.update(dt, now, self.AMPLITUDE)

        p1_idle = not self.p1.ever_had_input or (now - self.p1.last_input_time > IDLE_RESET_TIME)
        p2_idle = not self.p2.ever_had_input or (now - self.p2.last_input_time > IDLE_RESET_TIME)

        if p1_idle:
            self.p1_pulse_tmr += dt
            if self.p1_pulse_tmr >= PULSE_INTERVAL:
                self.p1_pulse_tmr = 0.0
                self._fire_pulse(self.p1_pulses, 'p1_pulse_idx', self.p1)
        else:
            self.p1_pulse_tmr = 0.0

        if p2_idle:
            self.p2_pulse_tmr += dt
            if self.p2_pulse_tmr >= PULSE_INTERVAL:
                self.p2_pulse_tmr = 0.0
                self._fire_pulse(self.p2_pulses, 'p2_pulse_idx', self.p2)
        else:
            self.p2_pulse_tmr = 0.0

        for p in self.p1_pulses + self.p2_pulses:
            p.update(dt, self.PULSE_EXPAND_SPD)

        p1_ang = self.p1.display_angle
        p2_ang = self.p2.display_angle
        diff   = (p1_ang - p2_ang + math.pi) % (2 * math.pi) - math.pi
        self.pizza_slice.start_angle = p2_ang
        self.pizza_slice.angle       = diff

        f_diff      = abs(self.p1.frequency - self.p2.frequency)
        p_diff      = abs((self.p1.phase - self.p2.phase + math.pi) % (2 * math.pi) - math.pi)
        both_active = self.p1.frequency > 0.05 and self.p2.frequency > 0.05

        if f_diff < SYNC_FREQ_TOLERANCE and p_diff < SYNC_PHASE_TOLERANCE and both_active:
            self.sync_timer = min(SYNC_DURATION, self.sync_timer + dt)
        else:
            self.sync_timer = max(0.0, self.sync_timer - dt * 2)

        sync_frac = self.sync_timer / SYNC_DURATION
        self.sync_circle.radius = sync_frac * self.PH_RADIUS

        self._render_neon_wave(self.p1, self.p1_layers)
        self._render_neon_wave(self.p2, self.p2_layers)
        self._update_end_dots()
        self._update_arrow(self.p1_arrow, self.p1.display_angle)
        self._update_arrow(self.p2_arrow, self.p2.display_angle)

        prog = int(sync_frac * 100)
        if prog != self.last_sync_prog:
            self.last_sync_prog   = prog
            self.sync_label.text  = "Sinchronizacija pasiekta" if prog >= 100 else f"{prog}%"
            self.sync_label.color = (0, 255, 100, 255) if prog >= 100 else (255, 255, 255, 255)

    # -----------------------------------------------------------------------
    # RENDER
    # -----------------------------------------------------------------------

    def _update_end_dots(self):
        for player, glow, dot, core in (
            (self.p1, self.p1_dot_glow, self.p1_dot, self.p1_dot_core),
            (self.p2, self.p2_dot_glow, self.p2_dot, self.p2_dot_core),
        ):
            tx, ty = self._tip_pos(player)
            glow.x, glow.y = tx, ty
            dot.x,  dot.y  = tx, ty
            core.x, core.y = tx, ty

    def _render_neon_wave(self, player, layers):
        pts     = player.points
        pts_len = len(pts)
        scroll  = player.total_scroll
        l0, l1, l2 = layers

        tail_start = max(0, pts_len - WAVE_RESOLUTION - 1)

        for i in range(WAVE_RESOLUTION):
            tail_i = tail_start + i
            if tail_i < pts_len - 1:
                p1, p2 = pts[tail_i], pts[tail_i + 1]
                x1, y1 = p1[0] - scroll, p1[1]
                x2, y2 = p2[0] - scroll, p2[1]
                for layer in (l0, l1, l2):
                    layer[i].x,  layer[i].y  = x1, y1
                    layer[i].x2, layer[i].y2 = x2, y2
                    layer[i].visible = True
            else:
                for layer in (l0, l1, l2):
                    layer[i].visible = False

    def on_draw(self):
        self.clear()

        if self.state == STATE_SPLASH:
            if self._splash_sprite:
                self._splash_sprite.draw()
            else:
                pyglet.text.Label(
                    "Press any key to start",
                    font_size=36,
                    x=self.width // 2, y=self.height // 2,
                    anchor_x='center', anchor_y='center',
                ).draw()

        elif self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            pass  # ffplay renders in its own fullscreen window

        elif self.state == STATE_PLAYING:
            self.batch.draw()
            self.fg_batch.draw()
            self.top_batch.draw()


if __name__ == "__main__":
    game = MuseumSyncGame()
    try:
        pyglet.app.run()
    finally:
        if game._arduino:
            game._arduino.close()