from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from compare_png_pixels import compare_pixels


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="compare-png-pixels-") as temp:
        root = Path(temp)
        red_a = root / "red-a.png"
        red_b = root / "red-b.png"
        blue = root / "blue.png"
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(red_a)
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(red_b)
        Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(blue)

        if not compare_pixels(red_a, red_b)["pixels_equal"]:
            raise AssertionError("identical pixels were reported as different")
        if compare_pixels(red_a, blue)["pixels_equal"]:
            raise AssertionError("different RGB pixels were reported as equal")

    print("PNG pixel comparison tests passed")


if __name__ == "__main__":
    main()
