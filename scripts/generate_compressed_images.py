#!/usr/bin/env python3
"""boar / deer 画像を4:3のJPEGへ変換し、変換情報をCSVへ記録する。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


CLASSES = ("boar", "deer")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class CompressionCondition:
    label: str
    width: int
    height: int
    quality: int


CONDITIONS = (
    CompressionCondition("vga_q95", 640, 480, 95),
    CompressionCondition("qvga_q75", 320, 240, 75),
    CompressionCondition("qvga_q50", 320, 240, 50),
    CompressionCondition("qqvga_q75", 160, 120, 75),
    CompressionCondition("qqvga_q50", 160, 120, 50),
)


def parse_args() -> argparse.Namespace:
    work_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=work_dir / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=work_dir / "data" / "processed")
    parser.add_argument("--manifest", type=Path, default=work_dir / "results" / "compression_manifest.csv")
    parser.add_argument(
        "--background",
        default="0,0,0",
        help="余白のRGB値。既定値は黒（例: 128,128,128）。",
    )
    return parser.parse_args()


def parse_color(value: str) -> tuple[int, int, int]:
    try:
        rgb = tuple(int(component) for component in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("背景色は R,G,B 形式で指定してください。") from error
    if len(rgb) != 3 or any(component < 0 or component > 255 for component in rgb):
        raise argparse.ArgumentTypeError("背景色は0〜255のRGB値で指定してください。")
    return rgb


def fit_with_padding(image: Image.Image, target_size: tuple[int, int], background: tuple[int, int, int]) -> tuple[Image.Image, dict[str, int | float]]:
    target_width, target_height = target_size
    source_width, source_height = image.size
    scale = min(target_width / source_width, target_height / source_height)
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", target_size, background)
    offset_x = (target_width - resized_width) // 2
    offset_y = (target_height - resized_height) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas, {
        "scale": round(scale, 8),
        "resized_width": resized_width,
        "resized_height": resized_height,
        "padding_left": offset_x,
        "padding_top": offset_y,
        "padding_right": target_width - resized_width - offset_x,
        "padding_bottom": target_height - resized_height - offset_y,
    }


def main() -> None:
    args = parse_args()
    background = parse_color(args.background)
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    manifest_path: Path = args.manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for class_name in CLASSES:
        class_dir = input_dir / class_name
        if not class_dir.is_dir():
            print(f"警告: クラスフォルダが見つかりません: {class_dir}")
            continue

        for source_path in sorted(class_dir.rglob("*")):
            if not source_path.is_file() or source_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            source_size = source_path.stat().st_size
            try:
                with Image.open(source_path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    source_width, source_height = image.size
            except (UnidentifiedImageError, OSError, ValueError) as error:
                rows.append({
                    "class_name": class_name,
                    "source_path": source_path.relative_to(input_dir).as_posix(),
                    "status": "error",
                    "error": str(error),
                })
                continue

            for condition in CONDITIONS:
                transformed, geometry = fit_with_padding(
                    image, (condition.width, condition.height), background
                )
                destination_path = output_dir / condition.label / class_name / f"{source_path.stem}.jpg"
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                # optimize を無効にして、実機との比較で再現性を優先する。
                transformed.save(
                    destination_path,
                    format="JPEG",
                    quality=condition.quality,
                    subsampling=2,  # 4:2:0
                    optimize=False,
                    progressive=False,
                )
                output_size = destination_path.stat().st_size
                rows.append({
                    "class_name": class_name,
                    "source_path": source_path.relative_to(input_dir).as_posix(),
                    "output_path": destination_path.relative_to(output_dir.parent.parent).as_posix(),
                    "condition": condition.label,
                    "target_width": condition.width,
                    "target_height": condition.height,
                    "jpeg_quality": condition.quality,
                    "padding_method": "fit_with_black_bars",
                    "background_rgb": ",".join(str(value) for value in background),
                    "source_width": source_width,
                    "source_height": source_height,
                    "source_size_bytes": source_size,
                    "output_size_bytes": output_size,
                    "compression_ratio": round(output_size / source_size, 6),
                    "status": "ok",
                    "error": "",
                    **geometry,
                })

    fieldnames = [
        "class_name", "source_path", "output_path", "condition", "target_width", "target_height",
        "jpeg_quality", "padding_method", "background_rgb", "source_width", "source_height",
        "resized_width", "resized_height", "scale", "padding_left", "padding_top", "padding_right",
        "padding_bottom", "source_size_bytes", "output_size_bytes", "compression_ratio", "status", "error",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    success_count = sum(row.get("status") == "ok" for row in rows)
    print(f"変換済み画像: {success_count} 枚")
    print(f"変換記録: {manifest_path}")


if __name__ == "__main__":
    main()
