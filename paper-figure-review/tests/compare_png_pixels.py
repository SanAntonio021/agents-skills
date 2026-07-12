from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image


def compare_pixels(first_path: Path, second_path: Path) -> dict[str, object]:
    with Image.open(first_path) as first_image, Image.open(second_path) as second_image:
        first = first_image.convert("RGBA")
        second = second_image.convert("RGBA")
        same_size = first.size == second.size
        pixels_equal = same_size and first.tobytes() == second.tobytes()

    return {
        "first": str(first_path),
        "second": str(second_path),
        "same_size": same_size,
        "pixels_equal": pixels_equal,
    }


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: compare_png_pixels.py <first.png> <second.png>")

    first_path = Path(sys.argv[1])
    second_path = Path(sys.argv[2])
    result = compare_pixels(first_path, second_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["pixels_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
