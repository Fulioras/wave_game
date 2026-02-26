"""
Two-Player Wave Game for Museum Installation
Interactive wave visualization with trailing ribbon effect
Compatible with Pyglet 2.1+ using modern rendering
"""

import pyglet
from pyglet.window import key
from pyglet import shapes
from pyglet.graphics import Batch
import math
import os
import sys


# ============================================================================
# CONFIGURATION - Easy to modify settings
# ============================================================================

class GameConfig:
    """Centralized configuration for easy modifications"""
    
    # Window settings
    WINDOW_WIDTH = 1920  # Will be overridden by screen resolution in fullscreen
    WINDOW_HEIGHT = 1080
    WINDOW_TITLE = "Wave Oscillation Game"
    BACKGROUND_COLOR = (0, 0, 0)  # Pure black for maximum neon contrast
    FULLSCREEN = True  # Start in borderless fullscreen
    VSYNC = True  # Enable vsync for smooth rendering
    
    # Player 1 settings (Top wave)
    PLAYER1_COLOR = (255, 0, 150)  # Hot Pink/Magenta
    PLAYER1_UP_KEY = key.W  # Push wave up (above axis)
    PLAYER1_DOWN_KEY = key.S  # Push wave down (below axis)
    PLAYER1_POSITION = WINDOW_HEIGHT * 0.5  # 35% from bottom
    
    # Player 2 settings (Bottom wave)
    PLAYER2_COLOR = (0, 255, 255)  # Cyan
    PLAYER2_UP_KEY = key.UP  # Push wave up (above axis)
    PLAYER2_DOWN_KEY = key.DOWN  # Push wave down (below axis)
    PLAYER2_POSITION = WINDOW_HEIGHT * 0.5  # 65% from bottom
    
    # Wave physics - DIRECTIONAL CONTROL
    PUSH_IMPULSE = 80.0  # Not used (kept for compatibility)
    WAVE_DECAY = 0.98  # Not used - amplitude stays constant
    MAX_OFFSET_PERCENT = 0.15  # Wave amplitude as % of screen height (15%)
    
    # Wave visual properties (all relative to screen size)
    WAVE_THICKNESS_PERCENT = 0.015  # Thickness as % of screen height (1.5%)
    WAVE_POINTS = 100  # Number of trailing points
    WAVE_MARGIN_LEFT_PERCENT = 0.0  # Left margin as % of screen width
    WAVE_MARGIN_RIGHT_PERCENT = 0.04  # Right margin as % of screen width (4%)
    
    # Wave smoothing
    INPUT_SMOOTHING = 0.15  # How fast head responds to input (0.1 = smooth, 0.3 = responsive)
    
    # Neon glow effect
    NEON_GLOW = True
    GLOW_LAYERS = 2  # Number of glow layers
    CIRCLE_DENSITY = 1  # Draw circle every N points
    
    # UI settings (relative to screen)
    SHOW_INSTRUCTIONS = True
    SHOW_FREQUENCY_DISPLAY = True
    FONT_NAME = 'Arial'
    FONT_SIZE_PERCENT = 0.02  # Font size as % of screen height (2%)
    LARGE_FONT_SIZE_PERCENT = 0.04  # Large numbers as % of screen height (4%)
    
    def calculate_absolute_values(self):
        """Calculate absolute pixel values from percentages based on screen size"""
        # Wave properties
        self.MAX_OFFSET = int(self.WINDOW_HEIGHT * self.MAX_OFFSET_PERCENT)
        self.WAVE_THICKNESS = int(self.WINDOW_HEIGHT * self.WAVE_THICKNESS_PERCENT)
        self.WAVE_MARGIN_LEFT = int(self.WINDOW_WIDTH * self.WAVE_MARGIN_LEFT_PERCENT)
        self.WAVE_MARGIN_RIGHT = int(self.WINDOW_WIDTH * self.WAVE_MARGIN_RIGHT_PERCENT)
        
        # UI properties
        self.FONT_SIZE = int(self.WINDOW_HEIGHT * self.FONT_SIZE_PERCENT)
        self.LARGE_FONT_SIZE = int(self.WINDOW_HEIGHT * self.LARGE_FONT_SIZE_PERCENT)
        
        # Update player positions (recalculate with actual height)
        self.PLAYER1_POSITION = int(self.WINDOW_HEIGHT * 0.35)
        self.PLAYER2_POSITION = int(self.WINDOW_HEIGHT * 0.65)


# ============================================================================
# WAVE ENTITY - Trailing ribbon effect
# ============================================================================

class Wave:
    """Wave where the rightmost point is controlled and leaves a trail behind it"""
    
    def __init__(self, y_position, color, config):
        self.y_position = y_position  # Center axis
        self.color = color
        self.config = config
        
        # The active point (rightmost) - this is what player controls
        self.head_offset = 0.0  # Current offset of the head point
        self.head_target = 0.0  # Target offset from button presses
        
        # Trail - stores historical Y positions that the head has visited
        # Oldest on left, newest (head) on right
        self.trail_y_positions = [y_position] * config.WAVE_POINTS
        self.last_trail_y = y_position
        
        # Frequency tracking
        self.frequency_history = []
        self.last_position = 0.0
        self.zero_crossings = 0
        self.time_elapsed = 0.0
        
        # Glow layers
        self.glow_layers = []
        self.update_glow_layers()
    
    def push_up(self):
        """Push the head point up"""
        self.head_target = self.config.MAX_OFFSET
    
    def push_down(self):
        """Push the head point down"""
        self.head_target = -self.config.MAX_OFFSET
    
    def update(self, dt):
        """Update wave - head moves smoothly, trail follows"""
        # Smoothly move head toward target
        offset_diff = self.head_target - self.head_offset
        self.head_offset += offset_diff * self.config.INPUT_SMOOTHING
        
        # Track zero crossings for frequency (using head position)
        if self.last_position > 0 and self.head_offset <= 0:
            self.zero_crossings += 1
        elif self.last_position < 0 and self.head_offset >= 0:
            self.zero_crossings += 1
        
        self.last_position = self.head_offset
        self.time_elapsed += dt
        
        # Calculate frequency every second
        if self.time_elapsed >= 1.0:
            freq = self.zero_crossings / 2.0 / self.time_elapsed
            self.frequency_history.append((freq, self.time_elapsed))
            
            self.zero_crossings = 0
            self.time_elapsed = 0.0
            
            if len(self.frequency_history) > 5:
                self.frequency_history.pop(0)
        
        # Update trail - add new head position
        new_head_y = self.y_position + self.head_offset
        
        # Only update if changed significantly (optimization)
        if abs(new_head_y - self.last_trail_y) > 1.0:
            # Shift all positions left (oldest falls off)
            self.trail_y_positions.pop(0)
            # Add new head position at right
            self.trail_y_positions.append(new_head_y)
            
            self.update_glow_layers()
            self.last_trail_y = new_head_y
        else:
            # Still update trail position
            self.trail_y_positions.pop(0)
            self.trail_y_positions.append(new_head_y)
    
    def get_trail_points(self):
        """Get (x, y) coordinates for trail"""
        start_x = self.config.WAVE_MARGIN_LEFT
        end_x = self.config.WINDOW_WIDTH - self.config.WAVE_MARGIN_RIGHT
        width = end_x - start_x
        
        points = []
        for i, y in enumerate(self.trail_y_positions):
            x = start_x + (i * width / (len(self.trail_y_positions) - 1))
            points.append((x, y))
        return points
    
    def update_glow_layers(self):
        """Update glow circles - optimized for performance"""
        self.glow_layers = []
        
        if not self.config.NEON_GLOW:
            return
        
        trail_points = self.get_trail_points()
        
        # Use fixed step based on density setting instead of calculating
        step = self.config.CIRCLE_DENSITY
        
        # Colored glow layers
        for layer_idx in range(self.config.GLOW_LAYERS, 0, -1):
            brightness = 0.4 + (0.6 * (self.config.GLOW_LAYERS - layer_idx) / self.config.GLOW_LAYERS)
            alpha = int(80 + (175 * (self.config.GLOW_LAYERS - layer_idx) / self.config.GLOW_LAYERS))
            
            r = int(self.color[0] * brightness)
            g = int(self.color[1] * brightness)
            b = int(self.color[2] * brightness)
            color = (r, g, b)
            
            radius = self.config.WAVE_THICKNESS * (0.5 + layer_idx * 0.4)
            
            layer_circles = []
            
            for i in range(0, len(trail_points), step):
                x, y = trail_points[i]
                circle = shapes.Circle(x, y, radius, color=color + (alpha,))
                layer_circles.append(circle)
            
            self.glow_layers.append(layer_circles)
        
        # White core
        white_radius = self.config.WAVE_THICKNESS * 0.5
        white_circles = []
        
        for i in range(0, len(trail_points), step):
            x, y = trail_points[i]
            circle = shapes.Circle(x, y, white_radius, color=(255, 255, 255, 255))
            white_circles.append(circle)
        
        self.glow_layers.append(white_circles)
    
    def draw(self):
        """Draw the trailing wave"""
        for layer in self.glow_layers:
            for circle in layer:
                circle.draw()
    
    def get_smoothed_frequency(self):
        """Get smoothed frequency for display"""
        if not self.frequency_history:
            return 0.0
        
        total = sum(f for f, _ in self.frequency_history)
        return total / len(self.frequency_history) if self.frequency_history else 0.0


# ============================================================================
# GAME MANAGER
# ============================================================================

class WaveGame:
    """Main game controller"""
    
    def __init__(self, config):
        self.config = config
        self.ui_batch = Batch()
        
        # Create waves
        self.player1_wave = Wave(config.PLAYER1_POSITION, config.PLAYER1_COLOR, config)
        self.player2_wave = Wave(config.PLAYER2_POSITION, config.PLAYER2_COLOR, config)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create UI labels"""
        self.labels = []
        
        if self.config.SHOW_INSTRUCTIONS:
            instruction_text = (f"Player 1: {chr(self.config.PLAYER1_UP_KEY)}↑ {chr(self.config.PLAYER1_DOWN_KEY)}↓ | "
                              f"Player 2: {chr(self.config.PLAYER2_UP_KEY)}↑ {chr(self.config.PLAYER2_DOWN_KEY)}↓")
            instruction_label = pyglet.text.Label(
                instruction_text,
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH // 2,
                y=self.config.WINDOW_HEIGHT - int(self.config.WINDOW_HEIGHT * 0.04),  # 4% from top
                anchor_x='center',
                color=(255, 255, 255, 255),
                batch=self.ui_batch
            )
            self.labels.append(instruction_label)
        
        if self.config.SHOW_FREQUENCY_DISPLAY:
            label_offset_x = int(self.config.WINDOW_WIDTH * 0.1)  # 10% from right edge
            
            # Player 1
            self.player1_label = pyglet.text.Label(
                'Player 1 - Hz',
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH - label_offset_x,
                y=self.config.PLAYER1_POSITION + int(self.config.WINDOW_HEIGHT * 0.01),
                anchor_x='left',
                color=self.config.PLAYER1_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.player1_label)
            
            self.p1_freq_label = pyglet.text.Label(
                '0',
                font_name=self.config.FONT_NAME,
                font_size=self.config.LARGE_FONT_SIZE,
                x=self.config.WINDOW_WIDTH - label_offset_x,
                y=self.config.PLAYER1_POSITION - int(self.config.WINDOW_HEIGHT * 0.03),
                anchor_x='left',
                color=self.config.PLAYER1_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.p1_freq_label)
            
            # Player 2
            self.player2_label = pyglet.text.Label(
                'Player 2 - Hz',
                font_name=self.config.FONT_NAME,
                font_size=self.config.FONT_SIZE,
                x=self.config.WINDOW_WIDTH - label_offset_x,
                y=self.config.PLAYER2_POSITION + int(self.config.WINDOW_HEIGHT * 0.01),
                anchor_x='left',
                color=self.config.PLAYER2_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.player2_label)
            
            self.p2_freq_label = pyglet.text.Label(
                '0',
                font_name=self.config.FONT_NAME,
                font_size=self.config.LARGE_FONT_SIZE,
                x=self.config.WINDOW_WIDTH - label_offset_x,
                y=self.config.PLAYER2_POSITION - int(self.config.WINDOW_HEIGHT * 0.03),
                anchor_x='left',
                color=self.config.PLAYER2_COLOR + (255,),
                batch=self.ui_batch
            )
            self.labels.append(self.p2_freq_label)
    
    def handle_key_press(self, symbol):
        """Handle keyboard input"""
        # Player 1 controls
        if symbol == self.config.PLAYER1_UP_KEY:
            self.player1_wave.push_up()
        elif symbol == self.config.PLAYER1_DOWN_KEY:
            self.player1_wave.push_down()
        
        # Player 2 controls
        elif symbol == self.config.PLAYER2_UP_KEY:
            self.player2_wave.push_up()
        elif symbol == self.config.PLAYER2_DOWN_KEY:
            self.player2_wave.push_down()
    
    def update(self, dt):
        """Update game state"""
        self.player1_wave.update(dt)
        self.player2_wave.update(dt)
        
        # Update frequency displays
        if self.config.SHOW_FREQUENCY_DISPLAY:
            p1_freq = int(round(self.player1_wave.get_smoothed_frequency()))
            p2_freq = int(round(self.player2_wave.get_smoothed_frequency()))
            
            self.p1_freq_label.text = str(p1_freq)
            self.p2_freq_label.text = str(p2_freq)
    
    def draw(self):
        """Render everything"""
        self.player1_wave.draw()
        self.player2_wave.draw()
        self.ui_batch.draw()


# ============================================================================
# WINDOW
# ============================================================================

class GameWindow(pyglet.window.Window):
    """Main window"""
    
    def __init__(self, game_config):
        if game_config.FULLSCREEN:
            super().__init__(
                fullscreen=True,
                caption=game_config.WINDOW_TITLE,
                vsync=game_config.VSYNC
            )
            game_config.WINDOW_WIDTH = self.width
            game_config.WINDOW_HEIGHT = self.height
        else:
            super().__init__(
                width=game_config.WINDOW_WIDTH,
                height=game_config.WINDOW_HEIGHT,
                caption=game_config.WINDOW_TITLE,
                vsync=game_config.VSYNC
            )
        
        # Calculate absolute values from percentages now that we know screen size
        game_config.calculate_absolute_values()
        
        self.game_config = game_config
        self.game = WaveGame(game_config)
        
        r, g, b = game_config.BACKGROUND_COLOR
        pyglet.gl.glClearColor(r/255, g/255, b/255, 1)
        
        if game_config.FULLSCREEN:
            self.set_mouse_visible(False)
        
        pyglet.clock.schedule_interval(self.update, 1/60)
    
    def on_draw(self):
        self.clear()
        self.game.draw()
    
    def on_key_press(self, symbol, modifiers):
        self.game.handle_key_press(symbol)
        if symbol == key.ESCAPE:
            self.close()
    
    def update(self, dt):
        self.game.update(dt)


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run the game"""
    # Try to set high priority
    try:
        if sys.platform != 'win32':
            try:
                os.nice(-10)
                print("Process priority set to HIGH")
            except PermissionError:
                print("Warning: Cannot set high priority (run with sudo for priority boost)")
                print("Game will run with normal priority")
    except Exception as e:
        print(f"Could not set process priority: {e}")
    
    config = GameConfig()
    window = GameWindow(config)
    
    print(f"\nWave Game Started")
    print(f"Resolution: {config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
    print(f"Fullscreen: {config.FULLSCREEN}")
    print(f"Press ESC to exit\n")
    
    pyglet.app.run()


if __name__ == '__main__':
    main()