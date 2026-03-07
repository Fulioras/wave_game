Only tested on a Ubuntu 24 lts PC so working on other configurations is not known.

MEDIA NAMING:
start.png
intro.mp4
win.mp4
lose.mp4

- paste the files inside the game folder "wave_game" or other
(you can change the naming in config.py)


MAKING VISUAL CHANGES:
open the config.py change the wanted values


MAIN FILES:
wave2.py - MAIN GAME FILE, works with config.py
config.py - file for configuring the game
wave.py - alternate version, works without config.py

GAME LOOP:
start.png -> intro.mp4 -> game -> win.mp4 OR lose.mp4 -> repeat

ONLY FOR FIRST START:
pip install -r requirements.txt

Should work now, just run:
python3 wave2.py
