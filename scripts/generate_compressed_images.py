#!/usr/bin/env python3
"""boar / deer 画像をカラー・モノクロの4:3 JPEGへ変換し、変換情報をCSVへ記録する。"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from datetime import date
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
    color_mode: str = "rgb"


CONDITIONS = (
    CompressionCondition("qvga_q75", 320, 240, 75),
    CompressionCondition("qvga_q50", 320, 240, 50),
    CompressionCondition("qvga_q30", 320, 240, 30),
    CompressionCondition("qvga_q15", 320, 240, 15),
    CompressionCondition("qvga_q5", 320, 240, 5),
    CompressionCondition("qvga_gray_q50", 320, 240, 50, "grayscale"),
    CompressionCondition("qvga_gray_q30", 320, 240, 30, "grayscale"),
    CompressionCondition("qqvga_gray_q50", 160, 120, 50, "grayscale"),
    CompressionCondition("qqvga_gray_q30", 160, 120, 30, "grayscale"),
)


def parse_run_id(value: str) -> str:
    if re.fullmatch(r"\d{8}_v\d{2,}", value) is None:
        raise argparse.ArgumentTypeError("実験IDは YYYYMMDD_vNN 形式で指定してください。")
    return value


def next_run_id(results_dir: Path, output_dir: Path) -> str:
    date_prefix = date.today().strftime("%Y%m%d")
    existing_ids = {
        path.stem.removeprefix("compression_manifest_")
        for path in results_dir.glob(f"compression_manifest_{date_prefix}_v*.csv")
    }
    existing_ids.update(
        path.name for path in output_dir.glob(f"{date_prefix}_v*") if path.is_dir()
    )
    version = 1
    while f"{date_prefix}_v{version:02d}" in existing_ids:
        version += 1
    return f"{date_prefix}_v{version:02d}"


def parse_args() -> argparse.Namespace:
    work_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=work_dir / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=work_dir / "data" / "processed")
    parser.add_argument("--manifest", type=Path, help="manifestの保存先（省略時は実験ID付きで保存）。")
    parser.add_argument("--run-id", type=parse_run_id, help="実験ID（例: 20261019_v01）。省略時は自動採番。")
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


def fit_with_padding(
    image: Image.Image,
    target_size: tuple[int, int],
    background: int | tuple[int, int, int],
) -> tuple[Image.Image, dict[str, int | float]]:
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
    results_dir = Path(__file__).resolve().parents[1] / "results"
    run_id = args.run_id or next_run_id(results_dir, output_dir)
    manifest_path = args.manifest or results_dir / f"compression_manifest_{run_id}.csv"
    versioned_output_dir = output_dir / run_id
    if manifest_path.exists() or versioned_output_dir.exists():
        raise SystemExit(f"実験ID {run_id} の出力が既に存在します。別の --run-id を指定してください。")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()

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
                if condition.color_mode == "grayscale":
                    working_image = image.convert("L")
                    # RGBの余白色と同じ知覚輝度になる値を使う。
                    working_background: int | tuple[int, int, int] = round(
                        0.299 * background[0] + 0.587 * background[1] + 0.114 * background[2]
                    )
                    output_color_mode = "grayscale"
                else:
                    working_image = image
                    working_background = background
                    output_color_mode = "rgb"
                transformed, geometry = fit_with_padding(
                    working_image, (condition.width, condition.height), working_background
                )
                destination_path = versioned_output_dir / condition.label / class_name / f"{source_path.stem}.jpg"
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                # optimize を無効にして、実機との比較で再現性を優先する。
                save_options: dict[str, object] = {
                    "format": "JPEG",
                    "quality": condition.quality,
                    "optimize": True,
                    "progressive": False,
                }
                if condition.color_mode == "rgb":
                    save_options["subsampling"] = 2  # 4:2:0
                transformed.save(destination_path, **save_options)
                output_size = destination_path.stat().st_size
                rows.append({
                    "class_name": class_name,
                    "source_path": source_path.relative_to(input_dir).as_posix(),
                    "output_path": destination_path.relative_to(output_dir.parent.parent).as_posix(),
                    "condition": condition.label,
                    "target_width": condition.width,
                    "target_height": condition.height,
                    "jpeg_quality": condition.quality,
                    "color_mode": output_color_mode,
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
        "run_id", "class_name", "source_path", "output_path", "condition", "target_width", "target_height",
        "jpeg_quality", "color_mode", "padding_method", "background_rgb", "source_width", "source_height",
        "resized_width", "resized_height", "scale", "padding_left", "padding_top", "padding_right",
        "padding_bottom", "source_size_bytes", "output_size_bytes", "compression_ratio", "status", "error",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({"run_id": run_id, **row} for row in rows)

    success_count = sum(row.get("status") == "ok" for row in rows)
    print(f"変換済み画像: {success_count} 枚")
    print(f"実験ID: {run_id}")
    print(f"画像出力先: {versioned_output_dir}")
    print(f"変換記録: {manifest_path}")

    end = time.perf_counter()
    print(f"実行時間: {end - start}msec")


if __name__ == "__main__":
    main()
