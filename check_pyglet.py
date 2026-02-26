#!/usr/bin/env python3
"""
Pyglet Installation Diagnostic Tool
Checks if Pyglet is installed correctly and reports version/capabilities
"""

import sys

print("=" * 60)
print("PYGLET INSTALLATION DIAGNOSTIC")
print("=" * 60)

# Check Python version
print(f"\n1. Python Version: {sys.version}")
print(f"   Python Executable: {sys.executable}")

# Try to import pyglet
print("\n2. Attempting to import pyglet...")
try:
    import pyglet
    print("   ✓ Pyglet imported successfully!")
    print(f"   Version: {pyglet.version}")
except ImportError as e:
    print("   ✗ FAILED to import pyglet!")
    print(f"   Error: {e}")
    print("\n   TO FIX: Run one of these commands:")
    print("   - pip3 install pyglet --break-system-packages")
    print("   - pip install pyglet --user")
    print("   - python3 -m pip install pyglet")
    sys.exit(1)

# Check pyglet.gl module
print("\n3. Checking pyglet.gl module...")
try:
    from pyglet import gl
    print("   ✓ pyglet.gl module loaded")
except ImportError as e:
    print(f"   ✗ FAILED to import pyglet.gl: {e}")

# Check graphics capabilities
print("\n4. Checking graphics modules...")
try:
    from pyglet import graphics
    print("   ✓ pyglet.graphics module loaded")
    print(f"   Available in graphics: {[x for x in dir(graphics) if not x.startswith('_')][:10]}...")
except ImportError as e:
    print(f"   ✗ FAILED to import pyglet.graphics: {e}")

# Check window capabilities
print("\n5. Checking window module...")
try:
    from pyglet import window
    print("   ✓ pyglet.window module loaded")
except ImportError as e:
    print(f"   ✗ FAILED to import pyglet.window: {e}")

# Try creating a simple window (without showing it)
print("\n6. Testing window creation...")
try:
    test_window = pyglet.window.Window(width=400, height=300, visible=False)
    print("   ✓ Window created successfully!")
    test_window.close()
except Exception as e:
    print(f"   ✗ FAILED to create window: {e}")
    print("\n   This might indicate:")
    print("   - Missing OpenGL libraries")
    print("   - No display server (if running headless)")
    print("   - Graphics driver issues")

# Check OpenGL availability
print("\n7. Checking OpenGL...")
try:
    from pyglet.gl import gl_info
    print("   ✓ OpenGL information available")
    
    # Create a hidden window to get GL context
    try:
        hidden_window = pyglet.window.Window(width=1, height=1, visible=False)
        print(f"   OpenGL Version: {gl_info.get_version()}")
        print(f"   OpenGL Vendor: {gl_info.get_vendor()}")
        print(f"   OpenGL Renderer: {gl_info.get_renderer()}")
        hidden_window.close()
    except Exception as e:
        print(f"   ⚠ Could not get detailed GL info: {e}")
        
except ImportError as e:
    print(f"   ✗ FAILED to check OpenGL: {e}")

# Test basic drawing
print("\n8. Testing basic OpenGL drawing...")
try:
    test_window = pyglet.window.Window(width=200, height=200, visible=False)
    
    @test_window.event
    def on_draw():
        test_window.clear()
        pyglet.gl.glColor3ub(255, 0, 0)
        pyglet.gl.glBegin(pyglet.gl.GL_LINES)
        pyglet.gl.glVertex2f(10, 10)
        pyglet.gl.glVertex2f(100, 100)
        pyglet.gl.glEnd()
    
    on_draw()
    test_window.close()
    print("   ✓ Basic OpenGL drawing works!")
except Exception as e:
    print(f"   ✗ FAILED drawing test: {e}")

# Summary
print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)

try:
    import pyglet
    print(f"\n✓ Pyglet {pyglet.version} is installed and working!")
    print("\nYou should be able to run the wave game.")
    print("If you still have issues, try:")
    print("1. python3 wave_game.py")
    print("2. Check for any error messages above")
except:
    print("\n✗ Pyglet is NOT properly installed")
    print("\nInstall with:")
    print("pip3 install pyglet --break-system-packages")
