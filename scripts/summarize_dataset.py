#!/usr/bin/env python3
"""boar / deer 画像データセットの基本情報を集計する。"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError


CLASSES = ("boar", "deer")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    work_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=work_dir / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=work_dir / "results")
    return parser.parse_args()


def safe_stat(values: list[int | float], operation: str) -> int | float | str:
    if not values:
        return ""
    if operation == "mean":
        return round(statistics.mean(values), 2)
    if operation == "median":
        return round(statistics.median(values), 2)
    if operation == "min":
        return min(values)
    if operation == "max":
        return max(values)
    raise ValueError(f"Unsupported operation: {operation}")


def main() -> None:
    args = parse_args()
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image_rows: list[dict[str, object]] = []
    by_class: dict[str, list[dict[str, object]]] = defaultdict(list)

    for class_name in CLASSES:
        class_dir = input_dir / class_name
        if not class_dir.is_dir():
            print(f"警告: クラスフォルダが見つかりません: {class_dir}")
            continue

        for path in sorted(class_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            row: dict[str, object] = {
                "class_name": class_name,
                "file_name": path.name,
                "relative_path": path.relative_to(input_dir).as_posix(),
                "extension": path.suffix.lower(),
                "file_size_bytes": path.stat().st_size,
                "file_size_kb": round(path.stat().st_size / 1024, 2),
                "format": "",
                "width": "",
                "height": "",
                "color_mode": "",
                "readable": False,
                "error": "",
            }
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    row.update(
                        format=image.format or "",
                        width=image.width,
                        height=image.height,
                        color_mode=image.mode,
                        readable=True,
                    )
            except (UnidentifiedImageError, OSError, ValueError) as error:
                row["error"] = str(error)

            image_rows.append(row)
            by_class[class_name].append(row)

    detail_path = output_dir / "dataset_summary.csv"
    detail_fields = [
        "class_name", "file_name", "relative_path", "extension", "file_size_bytes",
        "file_size_kb", "format", "width", "height", "color_mode", "readable", "error",
    ]
    with detail_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=detail_fields)
        writer.writeheader()
        writer.writerows(image_rows)

    class_summary_rows: list[dict[str, object]] = []
    for class_name in CLASSES:
        rows = by_class[class_name]
        valid_rows = [row for row in rows if row["readable"]]
        file_sizes = [float(row["file_size_bytes"]) for row in rows]
        widths = [int(row["width"]) for row in valid_rows]
        heights = [int(row["height"]) for row in valid_rows]
        formats = Counter(str(row["format"]) for row in valid_rows)
        color_modes = Counter(str(row["color_mode"]) for row in valid_rows)
        class_summary_rows.append(
            {
                "class_name": class_name,
                "image_count": len(rows),
                "readable_count": len(valid_rows),
                "unreadable_count": len(rows) - len(valid_rows),
                "file_size_mean_kb": safe_stat([value / 1024 for value in file_sizes], "mean"),
                "file_size_median_kb": safe_stat([value / 1024 for value in file_sizes], "median"),
                "file_size_min_kb": safe_stat([value / 1024 for value in file_sizes], "min"),
                "file_size_max_kb": safe_stat([value / 1024 for value in file_sizes], "max"),
                "width_median_px": safe_stat(widths, "median"),
                "height_median_px": safe_stat(heights, "median"),
                "formats": "; ".join(f"{name}:{count}" for name, count in sorted(formats.items())),
                "color_modes": "; ".join(f"{name}:{count}" for name, count in sorted(color_modes.items())),
            }
        )

    class_path = output_dir / "dataset_class_summary.csv"
    with class_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(class_summary_rows[0]) if class_summary_rows else ["class_name"])
        writer.writeheader()
        writer.writerows(class_summary_rows)

    print(f"詳細一覧: {detail_path}")
    print(f"クラス別集計: {class_path}")
    print(f"対象画像: {len(image_rows)} 枚")


if __name__ == "__main__":
    main()
