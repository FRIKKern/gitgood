"""Join genuine browser screenshots into a small README slideshow."""
import sys
from pathlib import Path
from PIL import Image

output = Path(sys.argv[1])
frames = []
for name in sys.argv[2:]:
    with Image.open(name) as screenshot:
        frame = screenshot.convert("RGB")
        frame.thumbnail((960, 675), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=128))
if len(frames) != 5:
    raise SystemExit("Expected all five captured screens")
frames[0].save(output, save_all=True, append_images=frames[1:],
               duration=2400, loop=0, optimize=True, disposal=2)
