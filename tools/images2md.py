#!/usr/bin/env python3
"""Convert slide images in a folder to MD//WORKS-compatible Markdown."""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

VERSION = "0.1.0"
DEFAULT_OUTPUT = "presentation.md"
DEFAULT_MAX_KB = 300
DEFAULT_HEADING_LEVEL = 2
TOTAL_SIZE_WARNING_BYTES = 10 * 1024 * 1024
SUPPORTED_TYPES = {
    ".png": ("png", "image/png"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".webp": ("webp", "image/webp"),
}
UNSUPPORTED_IMAGE_EXTENSIONS = {".svg", ".gif", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class ImageFile:
    path: Path
    image_type: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True)
class SkipItem:
    name: str
    reason: str
    size_bytes: int | None = None


@dataclass
class Result:
    input_dir: Path
    output_path: Path
    mode: str
    max_kb: int
    processed: list[ImageFile]
    skipped: list[SkipItem]
    markdown_size: int
    dry_run: bool = False
    warning: str | None = None


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def heading_level(value: str) -> int:
    number = positive_int(value)
    if number < 1 or number > 6:
        raise argparse.ArgumentTypeError("must be between 1 and 6")
    return number


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="images2md.py",
        description="Convert PNG, JPEG, and WebP files in a folder to Markdown.",
    )
    parser.add_argument("input_dir", nargs="?", type=Path, help="Folder containing image files")
    parser.add_argument("-o", "--output", type=Path, default=Path(DEFAULT_OUTPUT), help="Output Markdown file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--embed", action="store_true", help="Embed images as Base64 data URIs (default)")
    mode.add_argument("--link", action="store_true", help="Write relative links instead of Base64 data URIs")
    parser.add_argument("--max-kb", type=positive_int, default=DEFAULT_MAX_KB, help="Maximum source image size in KiB")
    parser.add_argument("--heading-level", type=heading_level, default=DEFAULT_HEADING_LEVEL, help="Heading level for each image, 1-6")
    parser.add_argument("--title", help="Optional document title")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing Markdown")
    parser.add_argument("--version", action="version", version=f"images2md.py {VERSION}")
    args = parser.parse_args(argv)
    if args.input_dir is None:
        parser.error("INPUT_DIR is required")
    return args


def natural_sort_key(name: str) -> list[tuple[int, int | str]]:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    key: list[tuple[int, int | str]] = []
    for part in re.split(r"(\d+)", normalized):
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return key


def detect_image_type(path: Path) -> tuple[str, str] | None:
    return SUPPORTED_TYPES.get(path.suffix.lower())


def validate_image_signature(path: Path, image_type: str) -> tuple[bool, str | None]:
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError as exc:
        return False, f"read error: {exc}"
    if image_type == "png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "invalid PNG signature"
    if image_type == "jpeg" and not header.startswith(b"\xff\xd8\xff"):
        return False, "invalid JPEG signature"
    if image_type == "webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
        return False, "invalid WebP signature"
    return True, None


def collect_image_files(input_dir: Path, output_path: Path, max_bytes: int) -> tuple[list[ImageFile], list[SkipItem]]:
    images: list[ImageFile] = []
    skipped: list[SkipItem] = []
    resolved_output = output_path.resolve(strict=False)
    try:
        entries = sorted(input_dir.iterdir(), key=lambda p: natural_sort_key(p.name))
    except OSError as exc:
        raise RuntimeError(f"Cannot read input folder: {exc}") from exc

    for entry in entries:
        name = entry.name
        try:
            if entry.resolve(strict=False) == resolved_output:
                skipped.append(SkipItem(name, "output file"))
                continue
            if entry.is_symlink():
                skipped.append(SkipItem(name, "symlink skipped"))
                continue
            if not entry.is_file():
                skipped.append(SkipItem(name, "not a regular file"))
                continue
            detected = detect_image_type(entry)
            if detected is None:
                reason = "unsupported format" if entry.suffix.lower() in UNSUPPORTED_IMAGE_EXTENSIONS or entry.suffix else "unsupported format"
                skipped.append(SkipItem(name, reason))
                continue
            size = entry.stat().st_size
            if size > max_bytes:
                skipped.append(SkipItem(name, "size limit exceeded", size))
                continue
            image_type, mime_type = detected
            valid, reason = validate_image_signature(entry, image_type)
            if not valid:
                skipped.append(SkipItem(name, reason or "invalid image signature", size))
                continue
            images.append(ImageFile(entry, image_type, mime_type, size))
        except OSError as exc:
            skipped.append(SkipItem(name, f"file error: {exc}"))
    return images, skipped


def format_heading(filename: str, level: int, fallback_number: int | None = None) -> str:
    stem = Path(filename).stem.strip()
    if not stem:
        stem = f"Slide {fallback_number or 1}"
    return f"{'#' * level} {stem}"


def encode_image_as_data_uri(path: Path, mime_type: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def create_relative_markdown_path(image_path: Path, output_path: Path) -> str:
    output_dir = output_path.parent if output_path.parent != Path("") else Path(".")
    relative = os.path.relpath(image_path, output_dir)
    return Path(relative).as_posix()


def markdown_alt_text(path: Path) -> str:
    return path.name.replace("]", r"\]")


def build_markdown_entry(image: ImageFile, output_path: Path, mode: str, heading_level_value: int, index: int) -> str:
    heading = format_heading(image.path.name, heading_level_value, index)
    alt = markdown_alt_text(image.path)
    if mode == "link":
        target = f"<{create_relative_markdown_path(image.path, output_path)}>"
    else:
        target = encode_image_as_data_uri(image.path, image.mime_type)
    return f"{heading}\n\n![{alt}]({target})"


def build_markdown(images: Sequence[ImageFile], output_path: Path, mode: str, level: int, title: str | None) -> str:
    sections: list[str] = []
    if title:
        sections.append(f"# {title}")
    for index, image in enumerate(images, start=1):
        sections.append(build_markdown_entry(image, output_path, mode, level, index))
    return "\n\n".join(sections) + "\n"


def write_markdown_atomically(output_path: Path, content: str, overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError("Output file already exists. Use --overwrite to replace it.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def print_summary(result: Result) -> None:
    total_size = sum(image.size_bytes for image in result.processed)
    print("images2md.py")
    print()
    print(f"Input folder : {result.input_dir}")
    print(f"Output file  : {result.output_path}")
    print(f"Mode         : {result.mode}")
    print(f"Max size     : {result.max_kb} KB")
    if result.dry_run:
        print("Dry run      : yes")
    print()
    if result.warning:
        print("Warning:")
        print(result.warning)
        print()
    print("Processed:")
    print(f"  {len(result.processed)} files")
    print(f"  Original image size: {format_size(total_size)}")
    print(f"  Markdown file size : {format_size(result.markdown_size)}")
    print()
    print("Skipped:")
    print(f"  {len(result.skipped)} files")
    for item in result.skipped:
        size = f" — {format_size(item.size_bytes)}" if item.size_bytes is not None else ""
        print(f"  - {item.name}{size} — {item.reason}")
    print()
    print("Completed successfully." if not result.dry_run else "Dry run completed.")


def run(args: argparse.Namespace) -> int:
    input_dir = args.input_dir.resolve(strict=False)
    output_path = args.output.resolve(strict=False)
    if not input_dir.exists():
        raise RuntimeError("Input folder does not exist.")
    if not input_dir.is_dir():
        raise RuntimeError("Input path is not a folder.")
    if output_path.exists() and not args.overwrite and not args.dry_run:
        raise FileExistsError("Output file already exists. Use --overwrite to replace it.")

    mode = "link" if args.link else "embed"
    images, skipped = collect_image_files(input_dir, output_path, args.max_kb * 1024)
    if not images:
        raise RuntimeError("No processable images found.")
    content = build_markdown(images, output_path, mode, args.heading_level, args.title)
    markdown_size = len(content.encode("utf-8"))
    total_size = sum(image.size_bytes for image in images)
    warning = None
    if mode == "embed" and total_size > TOTAL_SIZE_WARNING_BYTES:
        warning = f"The total image size is {format_size(total_size)}.\nThe embedded Markdown may exceed approximately {format_size(int(total_size * 4 / 3))}."
    if not args.dry_run:
        write_markdown_atomically(output_path, content, args.overwrite)
        markdown_size = output_path.stat().st_size
    result = Result(input_dir, output_path, mode, args.max_kb, images, skipped, markdown_size, args.dry_run, warning)
    print_summary(result)
    return 2 if skipped else 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_arguments(argv)
        return run(args)
    except (FileExistsError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
