"""
Two-Player Wave Game for Museum Installation
Interactive wave visualization that responds to player clicks
Compatible with Pyglet 2.1+ using modern rendering
"""

import pyglet
from pyglet.window import key
from pyglet import shapes
from pyglet.graphics import Batch
import math


# ============================================================================
# CONFIGURATION - Easy to modify settings
# ============================================================================

class GameConfig:
    """Centralized configuration for easy modifications"""
    
    # Window settings
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    WINDOW_TITLE = "Wave Oscillation Game"
    BACKGROUND_COLOR = (0, 0, 0)  # Pure black for maximum neon contrast
    
    # Player 1 settings (Top wave)
    PLAYER1_COLOR = (255, 0, 150)  # Hot Pink/Magenta
    PLAYER1_CLICK_KEY = key.A
    PLAYER1_POSITION = WINDOW_HEIGHT * 0.50  # 35% from bottom
    
    # Player 2 settings (Bottom wave)
    PLAYER2_COLOR = (0, 255, 255)  # Cyan
    PLAYER2_CLICK_KEY = key.L
    PLAYER2_POSITION = WINDOW_HEIGHT * 0.50  # 65% from bottom
    
    # Wave physics - MOMENTUM BASED
    SWING_IMPULSE = 3.0  # How much velocity each click adds
    SWING_DECAY = 0.92  # How fast the swing slows down (lower = slower, heavier feel)
    MAX_VELOCITY = 8.0  # Maximum swing velocity
    MOMENTUM_APPLICATION_RATE = 0.3  # How fast velocity catches up to target (0.1 = slow, 0.3 = fast)
    
    # Amplitude dynamics - swing behavior
    BASE_AMPLITUDE = 40  # Minimum amplitude
    MAX_AMPLITUDE = 300  # Maximum amplitude (at slowest swing)
    AMPLITUDE_VELOCITY_THRESHOLD = 2.0  # Velocity below this = large amplitude
    
    # Wave visual properties
    WAVE_THICKNESS = 15  # Base thickness of wave lines
    WAVE_POINTS = 100  # Number of points in wave (higher = smoother)
    WAVE_MARGIN_LEFT = 0  # No margin on left - waves start at edge
    WAVE_MARGIN_RIGHT = 400  # Margin on right side
    
    # Neon glow effect - ENHANCED
    NEON_GLOW = True
    GLOW_LAYERS = 3  # Number of glow layers (more = better glow)
    
    # UI settings
    SHOW_INSTRUCTIONS = False
    SHOW_FREQUENCY_DISPLAY = False  # Show velocity numbers instead of bars
    FONT_NAME = 'Arial'
    FONT_SIZE = 16


# ============================================================================
# WAVE ENTITY - Handles individual wave behavior
# ============================================================================

class Wave:
    """Represents a single player's wave with momentum-based swing physics"""
    
    def __init__(self, y_position, color, config):
        self.y_position = y_position
        self.color = color
        self.config = config
        
        # Physics properties - MOMENTUM BASED
        self.velocity = 0.0  # Current swing velocity
        self.target_velocity = 0.0  # Target velocity after click
        self.phase = 0.0  # Wave phase (advances over time)
        self.current_amplitude = config.BASE_AMPLITUDE  # Dynamic amplitude
        
        # Velocity history for smoothed display
        self.velocity_history = []
        self.history_duration = 2.0  # Keep last 2 seconds of history
        
        # Visual properties
        self.vertices = []
        self.update_vertices()
        
        # Create shape layers for neon glow effect
        self.glow_layers = []
        self.create_glow_layers()
    
    def click(self):
        """Called when player clicks - adds impulse to the wave gradually"""
        # Add to target velocity instead of instant velocity
        self.target_velocity = min(
            self.target_velocity + self.config.SWING_IMPULSE,
            self.config.MAX_VELOCITY
        )
    
    def update(self, dt):
        """Update wave state with momentum physics"""
        # Store previous phase for frequency calculation
        previous_phase = self.phase
        
        # Gradually apply momentum - velocity smoothly moves toward target_velocity
        # This creates a "wind-up" effect where clicks build momentum over time
        velocity_diff = self.target_velocity - self.velocity
        self.velocity += velocity_diff * self.config.MOMENTUM_APPLICATION_RATE
        
        # Apply velocity to phase (like a pendulum swinging)
        self.phase += self.velocity * dt
        
        # Apply decay to both velocity and target velocity (friction/air resistance)
        self.velocity *= self.config.SWING_DECAY
        self.target_velocity *= self.config.SWING_DECAY
        
        # Stop very small velocities
        if abs(self.velocity) < 0.01:
            self.velocity = 0.0
        if abs(self.target_velocity) < 0.01:
            self.target_velocity = 0.0
        
        # Calculate actual wave frequency (cycles per second)
        # Phase change per frame / (2π) = cycles per frame
        # Multiply by FPS (1/dt) to get cycles per second
        phase_change = abs(self.phase - previous_phase)
        if dt > 0:
            cycles_per_second = (phase_change / (2 * math.pi)) * (1 / dt)
        else:
            cycles_per_second = 0
        
        # Track frequency history for smoothed display
        self.velocity_history.append((cycles_per_second, dt))
        
        # Remove old history entries (older than history_duration)
        total_time = 0
        for i in range(len(self.velocity_history) - 1, -1, -1):
            total_time += self.velocity_history[i][1]
            if total_time > self.history_duration:
                self.velocity_history = self.velocity_history[i+1:]
                break
        
        # Calculate dynamic amplitude based on velocity
        # Lower velocity = larger amplitude (slow, wide swings)
        # Higher velocity = smaller amplitude (fast, tight swings)
        velocity_factor = abs(self.velocity) / self.config.MAX_VELOCITY
        
        # Inverse relationship: as velocity increases, amplitude decreases
        # When velocity is low (slow swing), amplitude approaches MAX_AMPLITUDE
        # When velocity is high (fast swing), amplitude approaches BASE_AMPLITUDE
        self.current_amplitude = self.config.MAX_AMPLITUDE - (
            (self.config.MAX_AMPLITUDE - self.config.BASE_AMPLITUDE) * velocity_factor
        )
        
        self.update_vertices()
        self.update_glow_layers()
    
    def get_smoothed_velocity(self):
        """Get average wave frequency over the last few seconds for display"""
        if not self.velocity_history:
            return 0.0
        
        # Calculate weighted average of wave frequency (cycles per second)
        total_weight = 0
        weighted_sum = 0
        
        for freq, dt in self.velocity_history:
            weight = dt
            weighted_sum += freq * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        return weighted_sum / total_weight
    
    def update_vertices(self):
        """Calculate wave shape based on momentum and phase"""
        self.vertices = []
        
        start_x = self.config.WAVE_MARGIN_LEFT
        end_x = self.config.WINDOW_WIDTH - self.config.WAVE_MARGIN_RIGHT
        usable_width = end_x - start_x
        
        for i in range(self.config.WAVE_POINTS):
            x = start_x + (i * (usable_width / (self.config.WAVE_POINTS - 1)))
            norm_x = (x - start_x) / usable_width
            
            # Reverse the wave direction: right side (end) is the head
            # Instead of (0 to 2π), we go from (2π to 0) so the wave travels right-to-left visually
            wave_position = (1 - norm_x) * math.pi * 2
            # Use dynamic current_amplitude instead of static value
            offset = math.sin(wave_position - self.phase) * self.current_amplitude
            
            y = self.y_position + offset
            self.vertices.append((x, y))
    
    def create_glow_layers(self):
        """Create multiple circle layers for each vertex to simulate thick glowing lines"""
        # We'll create circles at each vertex point to simulate thick lines with glow
        pass  # Layers created on first update
    
    def update_glow_layers(self):
        """Update circle positions for glow effect"""
        # Clear old layers
        self.glow_layers = []
        
        if not self.config.NEON_GLOW:
            return
        
        # Create glow effect using overlapping circles
        # Start with colored glow layers (outermost to inner)
        for layer_idx in range(self.config.GLOW_LAYERS, 0, -1):
            # Colored glow layers - progressively brighter toward center
            brightness = 0.4 + (0.6 * (self.config.GLOW_LAYERS - layer_idx) / self.config.GLOW_LAYERS)
            alpha = int(80 + (175 * (self.config.GLOW_LAYERS - layer_idx) / self.config.GLOW_LAYERS))
            
            r = int(self.color[0] * brightness)
            g = int(self.color[1] * brightness)
            b = int(self.color[2] * brightness)
            color = (r, g, b)
            
            radius = self.config.WAVE_THICKNESS * (0.5 + layer_idx * 0.4)
            
            # Create circles at intervals for smooth appearance
            step = max(1, self.config.WAVE_POINTS // 150)
            layer_circles = []
            
            for i in range(0, len(self.vertices), step):
                x, y = self.vertices[i]
                circle = shapes.Circle(
                    x, y, radius,
                    color=color + (alpha,)
                )
                layer_circles.append(circle)
            
            self.glow_layers.append(layer_circles)
        
        # Pure white core layer - drawn last so it's on top
        # Same size as the base wave thickness for full coverage
        white_radius = self.config.WAVE_THICKNESS * 0.5
        white_circles = []
        
        # Use same density as other layers for consistency
        step = max(1, self.config.WAVE_POINTS // 150)
        
        for i in range(0, len(self.vertices), step):
            x, y = self.vertices[i]
            circle = shapes.Circle(
                x, y, white_radius,
                color=(255, 255, 255, 255)  # Pure white, fully opaque
            )
            white_circles.append(circle)
        
        self.glow_layers.append(white_circles)
    
    def draw(self):
        """Draw the wave with glow effect"""
        for layer in self.glow_layers:
            for circle in layer:
                circle.draw()
    
    def get_velocity_normalized(self):
        """Get velocity as a 0-1 value for UI display"""
        return min(abs(self.velocity) / self.config.MAX_VELOCITY, 1.0)


# ============================================================================
# GAME MANAGER - Orchestrates game logic
# ============================================================================

class WaveGame:
    """Main game controller"""
    
    def __init__(self, config):
        self.config = config
        
        # Create batch for UI
        self.ui_batch = Batch()
        
        # Create waves for both players
        self.player1_wave = Wave(
            config.PLAYER1_POSITION,
            config.PLAYER1_COLOR,
            config
        )
        
        self.player2_wave = Wave(
            config.PLAYER2_POSITION,
            config.PLAYER2_COLOR,
            config
        )
        
        # Click counters
        self.player1_clicks = 0
        self.player2_clicks = 0
        
        # UI elements
        self.setup_ui()
    
    def setup_ui(self):
        """Create UI labels with velocity numbers"""
        self.labels = []
        
        if self.config.SHOW_INSTRUCTIONS:
            instruction_text = f"Player 1 (Top): Press '{chr(self.config.PLAYER1_CLICK_KEY)}' | Player 2 (Bottom): Press '{chr(self.config.PLAYER2_CLICK_KEY)}'"
            instruction_label = pyglet.text.Label(
                instruction_text,
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH // 2,
                y=self.config.WINDOW_HEIGHT - 30,
                anchor_x='center',
                anchor_y='center',
                color=(255, 255, 255, 255),
                batch=self.ui_batch
            )
            self.labels.append(instruction_label)
        
        if self.config.SHOW_FREQUENCY_DISPLAY:
            # Player 1 frequency display
            self.player1_freq_label = pyglet.text.Label(
                'Player 1 - Hz',
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH - 120,
                y=self.config.PLAYER1_POSITION + 10,
                anchor_x='left',
                color=self.config.PLAYER1_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.player1_freq_label)
            
            # Player 1 frequency number (large display)
            self.p1_velocity_label = pyglet.text.Label(
                '0',
                font_name=self.config.FONT_NAME,
                font_size=32,
                x=self.config.WINDOW_WIDTH - 120,
                y=self.config.PLAYER1_POSITION - 25,
                anchor_x='left',
                color=self.config.PLAYER1_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.p1_velocity_label)
            
            # Player 2 frequency display
            self.player2_freq_label = pyglet.text.Label(
                'Player 2 - Hz',
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH - 120,
                y=self.config.PLAYER2_POSITION + 10,
                anchor_x='left',
                color=self.config.PLAYER2_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.player2_freq_label)
            
            # Player 2 frequency number (large display)
            self.p2_velocity_label = pyglet.text.Label(
                '0',
                font_name=self.config.FONT_NAME,
                font_size=32,
                x=self.config.WINDOW_WIDTH - 120,
                y=self.config.PLAYER2_POSITION - 25,
                anchor_x='left',
                color=self.config.PLAYER2_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.p2_velocity_label)
    
    def handle_key_press(self, symbol):
        """Process keyboard input"""
        if symbol == self.config.PLAYER1_CLICK_KEY:
            self.player1_wave.click()
            self.player1_clicks += 1
        
        elif symbol == self.config.PLAYER2_CLICK_KEY:
            self.player2_wave.click()
            self.player2_clicks += 1
    
    def update(self, dt):
        """Update game state"""
        self.player1_wave.update(dt)
        self.player2_wave.update(dt)
        
        # Update frequency number displays (wave oscillation frequency in Hz)
        if self.config.SHOW_FREQUENCY_DISPLAY:
            # Show smoothed wave frequency as integer (cycles per second)
            p1_freq = int(round(self.player1_wave.get_smoothed_velocity()))
            p2_freq = int(round(self.player2_wave.get_smoothed_velocity()))
            
            self.p1_velocity_label.text = str(p1_freq)
            self.p2_velocity_label.text = str(p2_freq)
    
    def draw(self):
        """Render everything"""
        # Draw waves
        self.player1_wave.draw()
        self.player2_wave.draw()
        
        # Draw UI
        self.ui_batch.draw()


# ============================================================================
# WINDOW - Pyglet window setup
# ============================================================================

class GameWindow(pyglet.window.Window):
    """Main window for the game"""
    
    def __init__(self, game_config):
        super().__init__(
            width=game_config.WINDOW_WIDTH,
            height=game_config.WINDOW_HEIGHT,
            caption=game_config.WINDOW_TITLE
        )
        
        self.game_config = game_config
        self.game = WaveGame(game_config)
        
        # Set background color
        r, g, b = game_config.BACKGROUND_COLOR
        pyglet.gl.glClearColor(r/255, g/255, b/255, 1)
        
        # Schedule updates
        pyglet.clock.schedule_interval(self.update, 1/60)
    
    def on_draw(self):
        """Render frame"""
        self.clear()
        self.game.draw()
    
    def on_key_press(self, symbol, modifiers):
        """Handle keyboard input"""
        self.game.handle_key_press(symbol)
        
        if symbol == key.ESCAPE:
            self.close()
    
    def update(self, dt):
        """Update game state"""
        self.game.update(dt)


# ============================================================================
# MAIN - Entry point
# ============================================================================

def main():
    """Run the game"""
    config = GameConfig()
    window = GameWindow(config)
    pyglet.app.run()


if __name__ == '__main__':
    main()