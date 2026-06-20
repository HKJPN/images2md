# images2md.py![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

 [🇯🇵 日本語](readme-ja.md) or [🇺🇸 English](README.md) 

`images2md.py` is an independent Python CLI tool that converts PNG, JPEG, and WebP files directly under an input folder into a standard Markdown file. It uses only Python standard-library modules, does not contact external services, and never modifies source images.
<div align="center">
  <img width="480" height="270" alt="プレゼンテーション1" src="https://github.com/user-attachments/assets/f4e62bd1-d78e-4a69-8559-108d1a587043" />
</div>
## Requirements

- Python 3.10 or later
- No third-party packages

## Basic usage

```bash
python tools/images2md.py ./slides -o presentation.md
```

By default, each image is embedded as a one-line Base64 data URI.

```md
## Slide1

![Slide1.png](data:image/png;base64,...)
```

## Options

```text
python tools/images2md.py INPUT_DIR [options]
```

| Option | Description | Default |
| --- | --- | --- |
| `-o, --output FILE` | Markdown output path. | `presentation.md` |
| `--embed` | Embed images as Base64 data URIs. | enabled |
| `--link` | Output relative Markdown links instead of Base64 data URIs. | disabled |
| `--max-kb NUMBER` | Maximum source image size in KiB. | `300` |
| `--heading-level NUMBER` | Heading level for each image, from 1 to 6. | `2` |
| `--title TEXT` | Add a document title at the top. | none |
| `--overwrite` | Replace an existing Markdown file. | disabled |
| `--dry-run` | Print planned processing and skips without writing Markdown. | disabled |
| `--version` | Print the tool version. | - |
| `-h, --help` | Show help. | - |

`--embed` and `--link` cannot be used together.

## Supported files

The tool scans only files directly inside `INPUT_DIR`; it does not search subfolders.

Supported extensions are case-insensitive:

- `.png` (`image/png`)
- `.jpg` (`image/jpeg`)
- `.jpeg` (`image/jpeg`)
- `.webp` (`image/webp`)

SVG, GIF, BMP, TIFF, PDF, video files, folders, symlinks, and extensionless files are skipped. The tool also checks basic file signatures before processing an image.

## Ordering and headings

Files are sorted in natural order, so names such as these are processed as expected:

```text
Slide1.png
Slide2.png
Slide10.png
```

Each image becomes a Markdown section whose heading is generated from the filename without the extension:

```md
## Slide1

![Slide1.png](data:image/png;base64,...)
```

Use `--heading-level` to choose another level:

```bash
python tools/images2md.py ./slides -o presentation.md --heading-level 3
```

## Relative link mode

```bash
python tools/images2md.py ./slides -o presentation.md --link
```

Relative link mode writes links from the Markdown file to the source images, using `/` path separators and angle brackets for paths with spaces or parentheses:

```md
## Slide1

![Slide1.png](<slides/Slide1.png>)
```

The same per-image size limit is applied in link mode for MD//WORKS compatibility.

## Size limits and skips

The default limit is 300 KiB per source image:

```text
300 × 1024 = 307,200 bytes
```

Files over the limit and unsupported files are skipped individually. Processing continues as long as at least one image can be converted.

## Existing output files

If the output file already exists, the command stops unless `--overwrite` is specified:

```bash
python tools/images2md.py ./slides -o presentation.md --overwrite
```

Markdown is written via a temporary file in the output directory and replaced atomically to avoid leaving incomplete output after a write failure.

## Dry run

```bash
python tools/images2md.py ./slides -o presentation.md --dry-run
```

Dry run mode prints the files that would be processed and skipped without writing Markdown.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Markdown was created successfully with at least one processed image and no skipped files. |
| `1` | Fatal input, output, or argument error. |
| `2` | Markdown was created, but one or more files were skipped. |

## Not implemented in this MVP

- Image resizing or recompression
- JPEG quality changes
- PNG/WebP conversion
- EXIF removal or modification
- OCR
- PowerPoint/PDF direct import
- Recursive folder scanning
- ZIP creation
- Viewer HTML generation
- GUI or drag-and-drop UI
- External communication or auto-update
