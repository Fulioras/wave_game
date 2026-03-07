# ===========================================================================
# config.py  –  all tuneable settings for the CESA-Baltic sync game
# ===========================================================================

# ---------------------------------------------------------------------------
# ARDUINO
# ---------------------------------------------------------------------------
ARDUINO_PORT     = None          # e.g. "/dev/ttyUSB0" or "COM3"; None = auto-detect
ARDUINO_BAUDRATE = 9600
ARDUINO_WIN_MSG  = b'1'
ARDUINO_LOSE_MSG = b'0'

# ---------------------------------------------------------------------------
# MEDIA FILES
# ---------------------------------------------------------------------------
SPLASH_IMAGE = "start.png"
INTRO_VIDEO  = "intro.mp4"
WIN_VIDEO    = "win.mp4"
LOSE_VIDEO   = "lose.mp4"

# ---------------------------------------------------------------------------
# GAME LOGIC
# ---------------------------------------------------------------------------
SYNC_DURATION    = 5.0   # seconds of sustained sync required to win
INPUT_DELAY      = 2     # seconds between key press and wave peak
WAVE_RESOLUTION  = 250   # number of line segments used to draw each wave

IDLE_RESET_TIME   = 4.0  # seconds of inactivity before wave resets
IDLE_RETURN_SPEED = 4.0  # radians/sec for phasor arrow return to 0
IDLE_WAVE_SETTLE  = 1.2  # seconds for idle wave-settle animation

SYNC_FREQ_TOLERANCE  = 0.10  # max frequency difference counted as "in sync"
SYNC_PHASE_TOLERANCE = 0.5   # max phase difference (radians) counted as "in sync"
FLAG_WIN_THRESHOLD   = 0.50  # sync progress fraction required to win on flag

# ---------------------------------------------------------------------------
# PLAYER / TEAM LABELS
# ---------------------------------------------------------------------------
PLAYER1_LABEL        = "CESA"
PLAYER2_LABEL        = "Baltic"
PLAYER1_FLAG_KEY_HINT = ""
PLAYER2_FLAG_KEY_HINT = ""

# ---------------------------------------------------------------------------
# COLOURS  (R, G, B)
# ---------------------------------------------------------------------------
P1_COLOR = (120, 200, 120)
P2_COLOR = (0, 150, 200)
WHITE    = (255, 255, 255)

GRID_COLOR = (255, 255, 255, 75)   # RGBA

# ---------------------------------------------------------------------------
# NEON GLOW
# ---------------------------------------------------------------------------
NEON_GLOW_STRENGTH = 0.6   # 0.0 – 1.0; higher = brighter glow

# ---------------------------------------------------------------------------
# AXIS LABELS
# ---------------------------------------------------------------------------
AXIS_LABEL_X = "Laikas (t)"
AXIS_LABEL_Y = "Itampa (I)"

# ---------------------------------------------------------------------------
# LAYOUT
# ---------------------------------------------------------------------------
WAVE_WIDTH_PERCENT = 0.65   # fraction of window width used by the wave panel

# ---------------------------------------------------------------------------
# LINE / DOT THICKNESSES  (fraction of screen diagonal)
# ---------------------------------------------------------------------------
WAVE_GLOW_THICK_RATIO   = 0.020
WAVE_CORE_THICK_RATIO   = 0.014
WAVE_CENTER_THICK_RATIO = 0.004
PHASOR_LINE_THICK_RATIO = 0.003
AXIS_LINE_THICK_RATIO   = 0.002
WAVE_END_DOT_RATIO      = 0.007
WAVE_END_DOT_CORE_RATIO = 0.0035
SPOKE_THICK_RATIO       = 0.001

ARROW_HEAD_SIZE_RATIO   = 0.018

# ---------------------------------------------------------------------------
# FONT SIZES  (fraction of screen diagonal)
# ---------------------------------------------------------------------------
AXIS_FONT_RATIO            = 0.007
SYNC_LABEL_FONT_RATIO      = 0.015
DEGREE_LABEL_FONT_RATIO    = 0.006
INDICATOR_LABEL_FONT_RATIO = 0.010
FLAG_LABEL_FONT_RATIO      = 0.008
FLAG_KEY_HINT_FONT_RATIO   = 0.005

# ---------------------------------------------------------------------------
# INDICATOR DOTS & FLAG BOXES  (fraction of screen diagonal)
# ---------------------------------------------------------------------------
INDICATOR_RADIUS_RATIO = 0.004
FLAG_SIZE_RATIO        = 0.014

# ---------------------------------------------------------------------------
# PHASOR PANEL
# ---------------------------------------------------------------------------
PHASOR_RADIUS_RATIO = 0.35   # fraction of min(panel_width, window_height)

# ---------------------------------------------------------------------------
# GRID
# ---------------------------------------------------------------------------
GRID_CELL_W = 120           # pixels between vertical grid lines
GRID_CELL_H = 240           # pixels between horizontal grid lines
GRID_STYLE  = "endless"     # "endless"  or  "closed"

# ---------------------------------------------------------------------------
# PULSE RINGS  (emitted from wave tip while idle)
# ---------------------------------------------------------------------------
PULSE_MAX_RADIUS_RATIO = 0.25   # fraction of window height
PULSE_SPEED            = 1.5    # max_radius / second
PULSE_INTERVAL         = 0.9    # seconds between pulse emissions

# ---------------------------------------------------------------------------
# WAVE PHYSICS
# ---------------------------------------------------------------------------
AMPLITUDE_RATIO   = 0.18   # wave amplitude as fraction of window height
WAVE_SPEED_RATIO  = 0.22   # wave scroll speed as fraction of window width/sec