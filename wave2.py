import pyglet
from pyglet import shapes
from pyglet.window import key
import math
import time
import collections

SYNC_DURATION = 5.0
INPUT_DELAY = 2
WAVE_RESOLUTION = 250

IDLE_RESET_TIME   = 4.0
IDLE_RETURN_SPEED = 4.0
IDLE_WAVE_SETTLE  = 1.2

PULSE_SPEED = 1.5
NEON_GLOW_STRENGTH = 0.6

SYNC_FREQ_TOLERANCE  = 0.10
SYNC_PHASE_TOLERANCE = 0.20

WAVE_GLOW_THICK_RATIO   = 0.011
WAVE_CORE_THICK_RATIO   = 0.007
WAVE_CENTER_THICK_RATIO = 0.004
PHASOR_LINE_THICK_RATIO = 0.003
AXIS_LINE_THICK_RATIO   = 0.001
ARROW_HEAD_SIZE_RATIO   = 0.018
WAVE_END_DOT_RATIO      = 0.007

PULSE_MAX_RADIUS_RATIO = 0.25
PULSE_INTERVAL         = 0.9

WAVE_WIDTH_PERCENT = 0.65
AXIS_LABEL_X = "TIME (t)"
AXIS_LABEL_Y = "PHASE (Ph)"

P1_COLOR = (0, 255, 255)
P2_COLOR = (255, 0, 255)
WHITE    = (255, 255, 255)


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
        frac                = self.radius / self.max_radius
        fade_start          = 0.25
        fade                = max(0.0, 1.0 - max(0.0, frac - fade_start) / (1.0 - fade_start))
        self.circle.opacity = int(160 * fade)
        self.circle.visible = True


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

        self.current_y_norm   = 0.0
        self.current_direction = 1
        self.last_peak_time   = None
        
        self.ever_had_input = False
        self.first_input_time = None

        self.frequency     = 0.0
        self.phase         = 0.0

        self.arrow_angle       = 0.0
        self.display_angle     = 0.0

        self._idle_returning   = False
        self._idle_wave_from   = 0.0
        self._idle_wave_t      = 0.0

    def queue_signal(self, signal, current_time):
        if signal == self.last_signal:
            return
        self.last_signal     = signal
        self.last_input_time = current_time
        direction = 1 if signal == 'u' else -1
        
        if not self.ever_had_input:
            self.first_input_time = current_time
            self.ever_had_input = True
        
        self.signal_queue.append((current_time + INPUT_DELAY, direction))

    def _calculate_wave_position(self, current_time):
        if not self.signal_queue:
            if self.last_peak_time is None:
                return 0.0, 0.0, self.arrow_angle
            else:
                predicted_peak_time = current_time + INPUT_DELAY
                half_period = predicted_peak_time - self.last_peak_time
                time_since_peak = current_time - self.last_peak_time
                
                if half_period > 0.001:
                    progress = min(time_since_peak / half_period, 1.0)
                    y_norm = self.current_direction * math.cos(progress * math.pi)
                    frequency = 1.0 / (half_period * 2)
                    
                    if self.current_direction == 1:
                        target_angle = (math.pi / 2) + progress * math.pi
                    else:
                        target_angle = (3 * math.pi / 2) + progress * math.pi
                else:
                    y_norm = 0.0
                    frequency = 0.0
                    target_angle = self.arrow_angle
                    
        else:
            next_peak_time, next_direction = self.signal_queue[0]
            
            if self.last_peak_time is None:
                time_until_peak = next_peak_time - current_time
                time_since_queue = current_time - self.first_input_time
                total_rise_time = INPUT_DELAY
                
                if total_rise_time > 0.001:
                    progress = min(time_since_queue / total_rise_time, 1.0)
                    y_norm = next_direction * math.sin(progress * math.pi / 2.0)
                    frequency = 1.0 / (total_rise_time * 2)
                    
                    if next_direction == 1:
                        target_angle = progress * (math.pi / 2)
                    else:
                        target_angle = 2 * math.pi - progress * (math.pi / 2)
                else:
                    y_norm = 0.0
                    frequency = 0.0
                    target_angle = 0.0
                    
            else:
                half_period = next_peak_time - self.last_peak_time
                time_in_cycle = current_time - self.last_peak_time
                
                if half_period > 0.001:
                    progress = min(time_in_cycle / half_period, 1.0)
                    if progress > 1.0:
                        y_norm = next_direction
                    else:
                        y_norm = self.current_direction * math.cos(progress * math.pi)
                    
                    frequency = 1.0 / (half_period * 2)
                    
                    if self.current_direction == 1:
                        target_angle = (math.pi / 2) + progress * math.pi
                    else:
                        target_angle = (3 * math.pi / 2) + progress * math.pi
                else:
                    y_norm = self.current_y_norm
                    frequency = 0.0
                    target_angle = self.arrow_angle
        
        return y_norm, frequency, target_angle

    def update(self, dt, current_time, amplitude):
        idle = (current_time - self.last_input_time) > IDLE_RESET_TIME

        while self.signal_queue and current_time >= self.signal_queue[0][0]:
            fire_time, direction = self.signal_queue.popleft()
            self.last_peak_time = fire_time
            self.current_direction = direction
            self._idle_returning = False

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
            diff         = target_angle - self.arrow_angle
            step         = IDLE_RETURN_SPEED * dt
            if abs(diff) <= step:
                self.arrow_angle = target_angle
                arrow_done       = True
            else:
                self.arrow_angle += math.copysign(step, diff)
                arrow_done        = False

            if wave_frac >= 1.0 and arrow_done:
                self._idle_returning  = False
                self.ever_had_input   = False
                self.arrow_angle      = 0.0
                y_norm                = 0.0

            self.current_y_norm = y_norm
            self.frequency = 0.0
            
        else:
            y_norm, frequency, target_angle = self._calculate_wave_position(current_time)
            self.current_y_norm = y_norm
            self.frequency = frequency
            self.arrow_angle = target_angle

        self.display_angle = self.arrow_angle % (2 * math.pi)
        self.phase = self.display_angle

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


class MuseumSyncGame(pyglet.window.Window):
    def __init__(self):
        super().__init__(fullscreen=True, caption="Grid Sync")

        diag = math.hypot(self.width, self.height)

        self.WAVE_GLOW_THICK   = max(2, int(diag * WAVE_GLOW_THICK_RATIO))
        self.WAVE_CORE_THICK   = max(1, int(diag * WAVE_CORE_THICK_RATIO))
        self.WAVE_CENTER_THICK = max(1, int(diag * WAVE_CENTER_THICK_RATIO))
        self.PHASOR_LINE_THICK = max(1, int(diag * PHASOR_LINE_THICK_RATIO))
        self.AXIS_LINE_THICK   = max(1, int(diag * AXIS_LINE_THICK_RATIO))
        self.ARROW_HEAD_SIZE   = max(8, int(diag * ARROW_HEAD_SIZE_RATIO))
        self.WAVE_END_DOT_R    = max(4, int(diag * WAVE_END_DOT_RATIO))
        self.PULSE_MAX_RADIUS  = self.height * PULSE_MAX_RADIUS_RATIO
        self.PULSE_EXPAND_SPD  = self.PULSE_MAX_RADIUS * PULSE_SPEED

        self.WAVE_AREA_W = self.width * WAVE_WIDTH_PERCENT
        self.AMPLITUDE   = self.height * 0.18
        self.WAVE_SPEED  = self.width * 0.22
        self.PH_CX       = self.WAVE_AREA_W + (self.width - self.WAVE_AREA_W) / 2
        self.PH_CY       = self.height / 2
        self.PH_RADIUS   = min(self.width - self.WAVE_AREA_W, self.height) * 0.35

        self.batch     = pyglet.graphics.Batch()
        self.fg_batch  = pyglet.graphics.Batch()
        self.top_batch = pyglet.graphics.Batch()

        self.p1 = PlayerState(P1_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)
        self.p2 = PlayerState(P2_COLOR, self.height, self.WAVE_AREA_W, self.WAVE_SPEED)

        self.axis_h = shapes.Line(
            50, self.height / 2, self.WAVE_AREA_W, self.height / 2,
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
                                          color=(*P1_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)),
                                          batch=self.fg_batch)
        self.p1_dot      = shapes.Circle(0, 0, self.WAVE_END_DOT_R,
                                          color=(*P1_COLOR, 255), batch=self.fg_batch)
        self.p2_dot_glow = shapes.Circle(0, 0, self.WAVE_END_DOT_R * 2,
                                          color=(*P2_COLOR, int(255 * NEON_GLOW_STRENGTH / 2)),
                                          batch=self.fg_batch)
        self.p2_dot      = shapes.Circle(0, 0, self.WAVE_END_DOT_R,
                                          color=(*P2_COLOR, 255), batch=self.fg_batch)

        self.pizza_slice = shapes.Sector(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(255, 255, 255, 40), batch=self.batch)
        self.phasor_bg   = shapes.Circle(self.PH_CX, self.PH_CY, self.PH_RADIUS,
                                          color=(15, 15, 15), batch=self.batch)

        web_color   = (255, 255, 255, 40)
        ring_color  = (255, 255, 255, 30)
        spoke_thick = max(1, int(diag * 0.0005))

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
        for deg, text in ((0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")):
            a  = math.radians(deg)
            lx = self.PH_CX + lbl_off * math.cos(a)
            ly = self.PH_CY + lbl_off * math.sin(a)
            ax = 'left' if deg == 0 else ('right' if deg == 180 else 'center')
            ay = 'center' if deg in (0, 180) else ('bottom' if deg == 90 else 'top')
            self.degree_labels.append(pyglet.text.Label(
                text, font_size=lbl_font, x=lx, y=ly,
                anchor_x=ax, anchor_y=ay,
                color=(200, 200, 200, 180), batch=self.batch))

        self.p1_arrow = self._create_arrow(P1_COLOR)
        self.p2_arrow = self._create_arrow(P2_COLOR)

        label_font = max(16, int(diag * 0.014))
        self.sync_label = pyglet.text.Label(
            "READY", font_size=label_font,
            x=self.width / 2, y=self.height * 0.9,
            anchor_x='center', batch=self.batch)
        self.last_sync_prog = -1

        self.p1_pulses    = [PulseRing(P1_COLOR, self.fg_batch) for _ in range(3)]
        self.p2_pulses    = [PulseRing(P2_COLOR, self.fg_batch) for _ in range(3)]
        self.p1_pulse_idx = 0
        self.p2_pulse_idx = 0
        self.p1_pulse_tmr = 0.0
        self.p2_pulse_tmr = 0.0

        self.sync_timer = 0.0
        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    def _create_neon_wave(self, color):
        return (
            [shapes.Line(0, 0, 0, 0, thickness=self.WAVE_GLOW_THICK,
                         color=(*color, int(255 * NEON_GLOW_STRENGTH / 2)), batch=self.batch)
             for _ in range(WAVE_RESOLUTION)],
            [shapes.Line(0, 0, 0, 0, thickness=self.WAVE_CORE_THICK,
                         color=(*color, 255), batch=self.batch)
             for _ in range(WAVE_RESOLUTION)],
            [shapes.Line(0, 0, 0, 0, thickness=self.WAVE_CENTER_THICK,
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
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        r       = self.PH_RADIUS * 0.85
        tip_x   = self.PH_CX + r * cos_a
        tip_y   = self.PH_CY + r * sin_a
        
        shaft_r = r - self.ARROW_HEAD_SIZE * 1.2
        shaft_x = self.PH_CX + shaft_r * cos_a
        shaft_y = self.PH_CY + shaft_r * sin_a
        
        arrow['stem'].x,  arrow['stem'].y  = self.PH_CX, self.PH_CY
        arrow['stem'].x2, arrow['stem'].y2 = shaft_x, shaft_y
        
        s = self.ARROW_HEAD_SIZE
        cos_minus = math.cos(angle - 0.45)
        sin_minus = math.sin(angle - 0.45)
        cos_plus  = math.cos(angle + 0.45)
        sin_plus  = math.sin(angle + 0.45)
        
        arrow['head'].x,  arrow['head'].y  = tip_x, tip_y
        arrow['head'].x2, arrow['head'].y2 = tip_x - s * cos_minus, tip_y - s * sin_minus
        arrow['head'].x3, arrow['head'].y3 = tip_x - s * cos_plus, tip_y - s * sin_plus

    def _tip_pos(self, player):
        return self.WAVE_AREA_W, (self.height / 2) + self.AMPLITUDE * player.current_y_norm

    def _fire_pulse(self, pulses, idx_attr, player):
        tx, ty = self._tip_pos(player)
        idx = getattr(self, idx_attr)
        pulses[idx].fire(tx, ty, self.PULSE_MAX_RADIUS)
        setattr(self, idx_attr, (idx + 1) % len(pulses))

    def on_key_press(self, symbol, modifiers):
        t = time.time()
        if symbol == key.ESCAPE: self.close()
        if symbol == key.W:    self.p1.queue_signal('u', t)
        if symbol == key.S:    self.p1.queue_signal('d', t)
        if symbol == key.UP:   self.p2.queue_signal('u', t)
        if symbol == key.DOWN: self.p2.queue_signal('d', t)

    def update(self, dt):
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

        self._render_neon_wave(self.p1, self.p1_layers)
        self._render_neon_wave(self.p2, self.p2_layers)
        self._update_end_dots()
        self._update_arrow(self.p1_arrow, self.p1.display_angle)
        self._update_arrow(self.p2_arrow, self.p2.display_angle)

        prog = int((self.sync_timer / SYNC_DURATION) * 100)
        if prog != self.last_sync_prog:
            self.last_sync_prog = prog
            self.sync_label.text  = "STABLE CONNECTION" if prog >= 100 else f"SYNC: {prog}%"
            self.sync_label.color = (0, 255, 100, 255) if prog >= 100 else (255, 255, 255, 255)

    def _update_end_dots(self):
        for player, glow, dot in ((self.p1, self.p1_dot_glow, self.p1_dot),
                                   (self.p2, self.p2_dot_glow, self.p2_dot)):
            tx, ty = self._tip_pos(player)
            glow.x, glow.y = tx, ty
            dot.x,  dot.y  = tx, ty

    def _render_neon_wave(self, player, layers):
        pts = player.points
        pts_len = len(pts)
        scroll = player.total_scroll
        l0, l1, l2 = layers
        
        for i in range(WAVE_RESOLUTION):
            if i < pts_len - 1:
                p1, p2 = pts[i], pts[i + 1]
                x1, y1 = p1[0] - scroll, p1[1]
                x2, y2 = p2[0] - scroll, p2[1]
                
                l0[i].x, l0[i].y, l0[i].x2, l0[i].y2 = x1, y1, x2, y2
                l0[i].visible = True
                
                l1[i].x, l1[i].y, l1[i].x2, l1[i].y2 = x1, y1, x2, y2
                l1[i].visible = True
                
                l2[i].x, l2[i].y, l2[i].x2, l2[i].y2 = x1, y1, x2, y2
                l2[i].visible = True
            else:
                l0[i].visible = l1[i].visible = l2[i].visible = False

    def on_draw(self):
        self.clear()
        self.batch.draw()
        self.fg_batch.draw()
        self.top_batch.draw()


if __name__ == "__main__":
    MuseumSyncGame()
    pyglet.app.run()