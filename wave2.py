import pyglet
from pyglet import shapes
from pyglet.window import key
import math
import time
import collections
import os

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False
    print("[WARNING] pyserial not installed - Arduino signalling disabled. "
          "Run: pip install pyserial")


# ===========================================================================
# ARDUINO CONFIGURATION
# ===========================================================================
ARDUINO_PORT     = None
ARDUINO_BAUDRATE = 9600
ARDUINO_WIN_MSG  = b'1'
ARDUINO_LOSE_MSG = b'0'


def _find_arduino_port():
    import glob
    candidates = (
        glob.glob("/dev/ttyUSB*") +
        glob.glob("/dev/ttyACM*") +
        glob.glob("/dev/cu.usbmodem*") +
        glob.glob("/dev/cu.usbserial*") +
        glob.glob("COM[0-9]*")
    )
    return candidates[0] if candidates else None


def _open_arduino():
    if not _SERIAL_AVAILABLE:
        return None
    port = ARDUINO_PORT or _find_arduino_port()
    if port is None:
        print("[WARNING] No Arduino port found - serial signalling disabled.")
        return None
    try:
        conn = serial.Serial(port, ARDUINO_BAUDRATE, timeout=1)
        time.sleep(2)
        print(f"[INFO] Arduino connected on {port} at {ARDUINO_BAUDRATE} baud.")
        return conn
    except Exception as e:
        print(f"[WARNING] Could not open Arduino on {port}: {e}")
        return None


def _send_arduino(conn, msg):
    if conn is None:
        return
    try:
        conn.write(msg)
        conn.flush()
    except Exception as e:
        print(f"[WARNING] Arduino write failed: {e}")


# ===========================================================================
# MEDIA FILE CONFIGURATION
# ===========================================================================
SPLASH_IMAGE = "start.png"
INTRO_VIDEO  = "win1.mp4"
WIN_VIDEO    = "win1.mp4"
LOSE_VIDEO   = "lose1.mp4"


# ===========================================================================
# GAME LOGIC CONFIGURATION
# ===========================================================================
SYNC_DURATION = 5.0        
INPUT_DELAY   = 2          
WAVE_RESOLUTION = 250      

IDLE_RESET_TIME   = 4.0    
IDLE_RETURN_SPEED = 4.0    
IDLE_WAVE_SETTLE  = 1.2    

SYNC_FREQ_TOLERANCE  = 0.10
SYNC_PHASE_TOLERANCE = 0.5 
FLAG_WIN_THRESHOLD   = 0.50

# Game states
STATE_SPLASH       = "splash"
STATE_INTRO_VIDEO  = "intro_video"
STATE_PLAYING      = "playing"
STATE_RESULT_VIDEO = "result_video"


# ===========================================================================
# VISUAL / STYLE CONFIGURATION
# ===========================================================================

# --- Colours ---
P1_COLOR = (120, 200, 120)
P2_COLOR = (0, 150, 200)
WHITE    = (255, 255, 255)

GRID_COLOR = (255, 255, 255, 75)

# --- Neon glow ---
NEON_GLOW_STRENGTH = 0.6   

# --- Axis labels ---
AXIS_LABEL_X = "Laikas (t)"
AXIS_LABEL_Y = "Itampa (I)"

PLAYER1_LABEL = "CESA"
PLAYER2_LABEL = "Baltic"

PLAYER1_FLAG_KEY_HINT = ""
PLAYER2_FLAG_KEY_HINT = ""

WAVE_WIDTH_PERCENT = 0.65 

# All thickness
# Based on screen diagonal so the layout scales identically on any resolution.
WAVE_GLOW_THICK_RATIO   = 0.020
WAVE_CORE_THICK_RATIO   = 0.014
WAVE_CENTER_THICK_RATIO = 0.004
PHASOR_LINE_THICK_RATIO = 0.003
AXIS_LINE_THICK_RATIO   = 0.002
WAVE_END_DOT_RATIO      = 0.007   
WAVE_END_DOT_CORE_RATIO = 0.0035  

ARROW_HEAD_SIZE_RATIO   = 0.018


AXIS_FONT_RATIO         = 0.007
SYNC_LABEL_FONT_RATIO   = 0.015


DEGREE_LABEL_FONT_RATIO = 0.006

INDICATOR_LABEL_FONT_RATIO = 0.010

FLAG_LABEL_FONT_RATIO = 0.008
FLAG_KEY_HINT_FONT_RATIO = 0.005

INDICATOR_RADIUS_RATIO = 0.004

FLAG_SIZE_RATIO = 0.014 


PHASOR_RADIUS_RATIO = 0.35   

# Spoke / web line thickness
SPOKE_THICK_RATIO = 0.001

# --- Grid ---
GRID_CELL_W = 120           
GRID_CELL_H = 240           
GRID_STYLE  = "endless"     # "endless" or "closed"

# --- Pulse rings (emitted from wave tip when idle) ---
PULSE_MAX_RADIUS_RATIO = 0.25   # fraction of window height
PULSE_SPEED            = 1.5    
PULSE_INTERVAL         = 0.9    # seconds between pulse emissions

# --- Wave amplitude and scroll speed ---
AMPLITUDE_RATIO    = 0.18   # of window height
WAVE_SPEED_RATIO   = 0.22   # of window width per second


# ===========================================================================
# HELPERS
# ===========================================================================

def _load_image(path):
    if not os.path.exists(path):
        print(f"[WARNING] Image file not found: {path}")
        return None
    try:
        return pyglet.image.load(path)
    except Exception as e:
        print(f"[WARNING] Could not load image {path}: {e}")
        return None


def _fix_wave():
    """
    Pyglet bundles its own wave.py that lacks stdlib attributes like 'open'.
    Before every media.load call we swap sys.modules['wave'] for the real
    stdlib copy, which lives alongside other stdlib modules like struct.py.
    """
    import sys, importlib.util, importlib.machinery
    w = sys.modules.get('wave')
    if w is not None and hasattr(w, 'open'):
        return
    struct_origin = importlib.util.find_spec('struct').origin
    stdlib_dir = os.path.dirname(struct_origin)
    wave_path  = os.path.join(stdlib_dir, 'wave.py')
    if not os.path.isfile(wave_path):
        for p in sys.path:
            candidate = os.path.join(p, 'wave.py')
            if os.path.isfile(candidate) and 'pyglet' not in candidate:
                wave_path = candidate
                break
    loader = importlib.machinery.SourceFileLoader('wave', wave_path)
    real_wave = loader.load_module('wave')
    if not hasattr(real_wave, 'Error'):
        real_wave.Error = EOFError
    sys.modules['wave'] = real_wave


def _load_video(path):
    """Load a video as a pyglet media Source, or return None on failure."""
    if not os.path.exists(path):
        print(f"[WARNING] Video file not found: {path}")
        return None
    try:
        _fix_wave()
        return pyglet.media.load(path)
    except Exception as e:
        print(f"[WARNING] Could not load video {path}: {e}")
        return None


# ===========================================================================
# PULSE RING
# ===========================================================================
# Configuration for pulse ring visual behaviour is in VISUAL / STYLE section
# above (PULSE_MAX_RADIUS_RATIO, PULSE_SPEED, PULSE_INTERVAL).

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


# ===========================================================================
# PLAYER STATE
# ===========================================================================
# Configuration used here: INPUT_DELAY, IDLE_RESET_TIME, IDLE_RETURN_SPEED,
# IDLE_WAVE_SETTLE (all in GAME LOGIC section above).

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


# ===========================================================================
# MAIN WINDOW
# ===========================================================================

class MuseumSyncGame(pyglet.window.Window):
    def __init__(self):
        super().__init__(fullscreen=True, caption="CESA-Baltic frequency convergence")

        # ------------------------------------------------------------------
        # Derive all pixel sizes from the screen diagonal so every element
        # scales proportionally on any resolution (720p, 1080p, 4K, …).
        # ------------------------------------------------------------------
        diag = math.hypot(self.width, self.height)

        # Wave line thicknesses
        self.WAVE_GLOW_THICK     = max(2, int(diag * WAVE_GLOW_THICK_RATIO))
        self.WAVE_CORE_THICK     = max(1, int(diag * WAVE_CORE_THICK_RATIO))
        self.WAVE_CENTER_THICK   = max(1, int(diag * WAVE_CENTER_THICK_RATIO))
        self.PHASOR_LINE_THICK   = max(1, int(diag * PHASOR_LINE_THICK_RATIO))
        self.AXIS_LINE_THICK     = max(1, int(diag * AXIS_LINE_THICK_RATIO))

        # Arrow head
        self.ARROW_HEAD_SIZE     = max(8, int(diag * ARROW_HEAD_SIZE_RATIO))

        # Wave-tip dots
        self.WAVE_END_DOT_R      = max(4, int(diag * WAVE_END_DOT_RATIO))
        self.WAVE_END_DOT_CORE_R = max(2, int(diag * WAVE_END_DOT_CORE_RATIO))

        # Font sizes
        self.AXIS_FONT_SIZE      = max(10, int(diag * AXIS_FONT_RATIO))
        self.SYNC_LABEL_FONT     = max(16, int(diag * SYNC_LABEL_FONT_RATIO))
        self.DEGREE_LABEL_FONT   = max(9,  int(diag * DEGREE_LABEL_FONT_RATIO))
        self.INDICATOR_LABEL_FONT = max(12, int(diag * INDICATOR_LABEL_FONT_RATIO))
        self.FLAG_LABEL_FONT     = max(8,  int(diag * FLAG_LABEL_FONT_RATIO))
        self.FLAG_HINT_FONT      = max(9,  int(diag * FLAG_KEY_HINT_FONT_RATIO))

        # Indicator dots and flag boxes
        self.INDICATOR_RADIUS    = max(20, diag * INDICATOR_RADIUS_RATIO)
        self.FLAG_SIZE           = max(22, int(diag * FLAG_SIZE_RATIO))

        # Spoke / web grid lines
        self.SPOKE_THICK         = max(1, int(diag * SPOKE_THICK_RATIO))

        # Pulse rings
        self.PULSE_MAX_RADIUS = self.height * PULSE_MAX_RADIUS_RATIO
        self.PULSE_EXPAND_SPD = self.PULSE_MAX_RADIUS * PULSE_SPEED

        # Wave panel and physics
        self.WAVE_AREA_W = self.width  * WAVE_WIDTH_PERCENT
        self.AMPLITUDE   = self.height * AMPLITUDE_RATIO
        self.WAVE_SPEED  = self.width  * WAVE_SPEED_RATIO

        # Phasor panel geometry
        panel_w   = self.width - self.WAVE_AREA_W
        self.PH_CX     = self.WAVE_AREA_W + panel_w / 2
        self.PH_CY     = self.height / 2
        self.PH_RADIUS = min(panel_w, self.height) * PHASOR_RADIUS_RATIO

        self.batch     = pyglet.graphics.Batch()
        self.fg_batch  = pyglet.graphics.Batch()
        self.top_batch = pyglet.graphics.Batch()

        self.p1 = PlayerState(P1_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)
        self.p2 = PlayerState(P2_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)

        self._build_game_ui()

        # Media assets
        self._splash_image  = _load_image(SPLASH_IMAGE)
        self._splash_sprite = None

        self._media_player     = None
        self._video_sprite     = None
        self._video_next_state = STATE_PLAYING

        # Arduino
        self._arduino = _open_arduino()

        self.state = None
        self._set_state(STATE_SPLASH)

        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    # -----------------------------------------------------------------------
    # STATE MACHINE
    # -----------------------------------------------------------------------

    def _set_state(self, new_state, video_path=None):
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
        source = _load_video(path)
        if source is None:
            pyglet.clock.schedule_once(lambda dt: self._set_state(next_state), 0)
            return

        self._stop_video()

        player = pyglet.media.Player()
        player.queue(source)

        @player.event
        def on_player_eos():
            self._video_sprite = None
            self._set_state(self._video_next_state)

        player.play()
        self._media_player = player
        self._video_sprite = None

    def _stop_video(self):
        if self._media_player:
            try:
                self._media_player.pause()
                self._media_player.delete()
            except Exception:
                pass
            self._media_player = None
        self._video_sprite = None

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
        _send_arduino(self._arduino, ARDUINO_WIN_MSG if won else ARDUINO_LOSE_MSG)
        video = WIN_VIDEO if won else LOSE_VIDEO
        self._set_state(STATE_RESULT_VIDEO, video_path=video)

    # -----------------------------------------------------------------------
    # BUILD GAME UI
    # -----------------------------------------------------------------------

    def _build_game_ui(self):
        # --- Background grid ---
        # Configuration: GRID_CELL_W, GRID_CELL_H, GRID_STYLE, GRID_COLOR
        self._create_background_grid()

        # --- Axis lines and labels ---
        # Configuration: AXIS_LINE_THICK, AXIS_FONT_SIZE, AXIS_LABEL_X/Y
        self.axis_h = shapes.Line(
            50, self.height / 2, self.WAVE_AREA_W + 20, self.height / 2,
            thickness=self.AXIS_LINE_THICK, color=(*WHITE, 255), batch=self.batch)
        self.axis_v = shapes.Line(
            50, self.height / 2 - self.AMPLITUDE - 20,
            50, self.height / 2 + self.AMPLITUDE + 20,
            thickness=self.AXIS_LINE_THICK, color=(*WHITE, 255), batch=self.batch)

        self.lbl_x = pyglet.text.Label(
            AXIS_LABEL_X, font_size=self.AXIS_FONT_SIZE,
            x=self.WAVE_AREA_W - 80, y=self.height / 2 - 30,
            batch=self.batch)
        self.lbl_y = pyglet.text.Label(
            AXIS_LABEL_Y, font_size=self.AXIS_FONT_SIZE,
            x=60, y=self.height / 2 + self.AMPLITUDE + 25,
            batch=self.batch)

        # --- Neon wave line layers ---
        # Configuration: WAVE_GLOW_THICK, WAVE_CORE_THICK, WAVE_CENTER_THICK,
        #                NEON_GLOW_STRENGTH, WAVE_RESOLUTION, P1_COLOR, P2_COLOR
        self.p1_layers = self._create_neon_wave(P1_COLOR)
        self.p2_layers = self._create_neon_wave(P2_COLOR)

        # --- Wave-tip dots (glow + solid + white core) ---
        # Configuration: WAVE_END_DOT_R, WAVE_END_DOT_CORE_R, NEON_GLOW_STRENGTH
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

        # --- Phasor panel background ---
        # Configuration: PH_CX, PH_CY, PH_RADIUS (derived from PHASOR_RADIUS_RATIO)
        self.pizza_slice = shapes.Sector(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(255, 255, 255, 40), batch=self.batch)
        self.phasor_bg   = shapes.Circle(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(15, 15, 15), batch=self.batch)

        # --- Phasor web: rim, rings, spokes ---
        # Configuration: SPOKE_THICK_RATIO -> self.SPOKE_THICK
        web_color   = (255, 255, 255, 75)
        ring_color  = (255, 255, 255, 100)

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
                thickness=self.SPOKE_THICK * 2, color=web_color, batch=self.batch))

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
                    thickness=self.SPOKE_THICK, color=ring_color, batch=self.batch))

        self.web_spokes = []
        for deg in range(0, 360, 45):
            a = math.radians(deg)
            self.web_spokes.append(shapes.Line(
                self.PH_CX, self.PH_CY,
                self.PH_CX + self.PH_RADIUS * math.cos(a),
                self.PH_CY + self.PH_RADIUS * math.sin(a),
                thickness=self.SPOKE_THICK, color=web_color, batch=self.batch))

        # --- Phasor degree labels (0 / 90 / 180 / 270) ---
        # Configuration: DEGREE_LABEL_FONT
        lbl_off = self.PH_RADIUS * 1.12
        self.degree_labels = []
        for deg, text in ((0, "0"), (90, "90"), (180, "180"), (270, "270")):
            a  = math.radians(deg)
            lx = self.PH_CX + lbl_off * math.cos(a)
            ly = self.PH_CY + lbl_off * math.sin(a)
            ax = 'left' if deg == 0 else ('right' if deg == 180 else 'center')
            ay = 'center' if deg in (0, 180) else ('bottom' if deg == 90 else 'top')
            self.degree_labels.append(pyglet.text.Label(
                text, font_size=self.DEGREE_LABEL_FONT, x=lx, y=ly,
                anchor_x=ax, anchor_y=ay,
                color=(200, 200, 200, 180), batch=self.batch))

        # --- Player indicator dots and labels (CESA / Baltic) ---
        # Configuration: INDICATOR_RADIUS, INDICATOR_LABEL_FONT,
        #                NEON_GLOW_STRENGTH, P1_COLOR, P2_COLOR
        indicator_y = self.PH_CY - self.PH_RADIUS - self.height * 0.12

        self.p1_indicator_glow = shapes.Circle(
            self.PH_CX - 80, indicator_y, self.INDICATOR_RADIUS * 1.5,
            color=(*P1_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
        self.p1_indicator = shapes.Circle(
            self.PH_CX - 80, indicator_y, self.INDICATOR_RADIUS,
            color=(*P1_COLOR, 255), batch=self.batch)
        self.p1_indicator_label = pyglet.text.Label(
            PLAYER1_LABEL, font_size=self.INDICATOR_LABEL_FONT,
            x=self.PH_CX - 80, y=indicator_y - self.INDICATOR_RADIUS * 1.8,
            anchor_x='center', anchor_y='top', batch=self.batch)

        self.p2_indicator_glow = shapes.Circle(
            self.PH_CX + 80, indicator_y, self.INDICATOR_RADIUS * 1.5,
            color=(*P2_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
        self.p2_indicator = shapes.Circle(
            self.PH_CX + 80, indicator_y, self.INDICATOR_RADIUS,
            color=(*P2_COLOR, 255), batch=self.batch)
        self.p2_indicator_label = pyglet.text.Label(
            PLAYER2_LABEL, font_size=self.INDICATOR_LABEL_FONT,
            x=self.PH_CX + 80, y=indicator_y - self.INDICATOR_RADIUS * 1.8,
            anchor_x='center', anchor_y='top', batch=self.batch)

        # --- Sync fill circle ---
        self.sync_circle = shapes.Circle(
            self.PH_CX, self.PH_CY, 0,
            color=(0, 255, 100, 100), batch=self.batch)

        # --- Phasor arrows ---
        # Configuration: PHASOR_LINE_THICK, ARROW_HEAD_SIZE, P1_COLOR, P2_COLOR
        self.p1_arrow = self._create_arrow(P1_COLOR)
        self.p2_arrow = self._create_arrow(P2_COLOR)

        # --- Sync percentage readout ---
        # Configuration: SYNC_LABEL_FONT
        self.sync_label = pyglet.text.Label(
            "READY", font_size=self.SYNC_LABEL_FONT,
            x=self.PH_CX, y=self.height - self.height * 0.06,
            anchor_x='center', anchor_y='top', batch=self.batch)
        self.last_sync_prog = -1

        # --- Flag widgets ---
        # Configuration: FLAG_SIZE, FLAG_LABEL_FONT, FLAG_HINT_FONT,
        #                PLAYER1/2_FLAG_KEY_HINT, P1_COLOR, P2_COLOR
        flag_y   = indicator_y - self.height * 0.09
        half     = self.FLAG_SIZE // 2

        self.p1_flag_box = shapes.Rectangle(
            self.PH_CX - 80 - half, flag_y - half,
            self.FLAG_SIZE, self.FLAG_SIZE,
            color=(*P1_COLOR, 55), batch=self.batch)
        self.p1_flag_border = shapes.Box(
            self.PH_CX - 80 - half, flag_y - half,
            self.FLAG_SIZE, self.FLAG_SIZE,
            thickness=max(1, int(self.FLAG_SIZE * 0.07)),
            color=(*P1_COLOR, 180), batch=self.batch)
        self.p1_flag_label = pyglet.text.Label(
            "", font_size=self.FLAG_LABEL_FONT,
            x=self.PH_CX - 80, y=flag_y,
            anchor_x='center', anchor_y='center',
            color=(*P1_COLOR, 230), batch=self.batch)

        self.p2_flag_box = shapes.Rectangle(
            self.PH_CX + 80 - half, flag_y - half,
            self.FLAG_SIZE, self.FLAG_SIZE,
            color=(*P2_COLOR, 55), batch=self.batch)
        self.p2_flag_border = shapes.Box(
            self.PH_CX + 80 - half, flag_y - half,
            self.FLAG_SIZE, self.FLAG_SIZE,
            thickness=max(1, int(self.FLAG_SIZE * 0.07)),
            color=(*P2_COLOR, 180), batch=self.batch)
        self.p2_flag_label = pyglet.text.Label(
            "", font_size=self.FLAG_LABEL_FONT,
            x=self.PH_CX + 80, y=flag_y,
            anchor_x='center', anchor_y='center',
            color=(*P2_COLOR, 230), batch=self.batch)

        self.p1_flag_hint = pyglet.text.Label(
            PLAYER1_FLAG_KEY_HINT, font_size=self.FLAG_HINT_FONT,
            x=self.PH_CX - 80, y=flag_y - half - 4,
            anchor_x='center', anchor_y='top',
            color=(200, 200, 200, 130), batch=self.batch)
        self.p2_flag_hint = pyglet.text.Label(
            PLAYER2_FLAG_KEY_HINT, font_size=self.FLAG_HINT_FONT,
            x=self.PH_CX + 80, y=flag_y - half - 4,
            anchor_x='center', anchor_y='top',
            color=(200, 200, 200, 130), batch=self.batch)

        # --- Pulse rings ---
        # Configuration: PULSE_MAX_RADIUS_RATIO, PULSE_SPEED, PULSE_INTERVAL
        self.p1_pulses    = [PulseRing(P1_COLOR, self.fg_batch) for _ in range(3)]
        self.p2_pulses    = [PulseRing(P2_COLOR, self.fg_batch) for _ in range(3)]
        self.p1_pulse_idx = 0
        self.p2_pulse_idx = 0
        self.p1_pulse_tmr = 0.0
        self.p2_pulse_tmr = 0.0

        self.sync_timer = 0.0

    # -----------------------------------------------------------------------
    # GRID / WAVE / ARROW helpers
    # -----------------------------------------------------------------------

    def _create_background_grid(self):
        # Configuration: GRID_CELL_W, GRID_CELL_H, GRID_STYLE, GRID_COLOR,
        #                WAVE_WIDTH_PERCENT (via self.WAVE_AREA_W)
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
        while cy + i * GRID_CELL_H <= max_y: y_offsets.append( i * GRID_CELL_H); i += 1
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
        # Configuration: WAVE_GLOW_THICK, WAVE_CORE_THICK, WAVE_CENTER_THICK,
        #                NEON_GLOW_STRENGTH, WAVE_RESOLUTION
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
        # Configuration: PHASOR_LINE_THICK (-> self.PHASOR_LINE_THICK)
        stem = shapes.Line(self.PH_CX, self.PH_CY, self.PH_CX, self.PH_CY + 1,
                           thickness=self.PHASOR_LINE_THICK, color=(*color, 255),
                           batch=self.batch)
        head = shapes.Triangle(self.PH_CX, self.PH_CY, self.PH_CX, self.PH_CY,
                                self.PH_CX, self.PH_CY, color=(*color, 255),
                                batch=self.batch)
        return {'stem': stem, 'head': head}

    def _update_arrow(self, arrow, angle):
        # Configuration: ARROW_HEAD_SIZE (-> self.ARROW_HEAD_SIZE)
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

        if self.state == STATE_SPLASH:
            if symbol != key.ESCAPE:
                self._set_state(STATE_INTRO_VIDEO)
            return

        if self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            return

        if self.state == STATE_PLAYING:
            if symbol == key.W:     self.p1.queue_signal('u', t)
            if symbol == key.S:     self.p1.queue_signal('d', t)
            if symbol == key.UP:    self.p2.queue_signal('u', t)
            if symbol == key.DOWN:  self.p2.queue_signal('d', t)

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
        if self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            return

        if self.state != STATE_PLAYING:
            return

        now = time.time()
        self.p1.update(dt, now, self.AMPLITUDE)
        self.p2.update(dt, now, self.AMPLITUDE)

        # Pulse rings from wave tips when idle
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

        # Phasor phase-difference sector
        p1_ang = self.p1.display_angle
        p2_ang = self.p2.display_angle
        diff   = (p1_ang - p2_ang + math.pi) % (2 * math.pi) - math.pi
        self.pizza_slice.start_angle = p2_ang
        self.pizza_slice.angle       = diff

        # Sync detection
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

    def _draw_video_frame(self):
        """Draw the current video frame scaled to fill the window."""
        if self._media_player is None:
            return
        texture = self._media_player.texture
        if texture is None:
            return
        vw, vh = texture.width, texture.height
        if vw == 0 or vh == 0:
            return
        scale = max(self.width / vw, self.height / vh)
        dw, dh = vw * scale, vh * scale
        x = (self.width  - dw) / 2
        y = (self.height - dh) / 2
        texture.blit(x, y, width=dw, height=dh)

    def on_draw(self):
        self.clear()

        if self.state == STATE_SPLASH:
            if self._splash_sprite:
                self._splash_sprite.draw()
            else:
                pyglet.text.Label(
                    "Press any key to start",
                    font_size=self.SYNC_LABEL_FONT,
                    x=self.width // 2, y=self.height // 2,
                    anchor_x='center', anchor_y='center',
                ).draw()

        elif self.state in (STATE_INTRO_VIDEO, STATE_RESULT_VIDEO):
            self._draw_video_frame()

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