"""Command-line interface: argument parsing and the PDF queue."""
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from . import epub, extraction, sections, workspace
from .metadata import BookDescription, metadata_from_pdf_info

log = logging.getLogger("pdf2epub")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PDF files to EPUB format via Markdown")
    parser.add_argument("input_path", nargs="?", type=Path,
                        help="Path to input PDF file or directory (default: ./input/*.pdf)")
    parser.add_argument("output_path", nargs="?", type=Path,
                        help="Path to output directory (default: directory named after PDF)")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to process")
    parser.add_argument("--start-page", type=int, default=None, help="Page number to start from")
    parser.add_argument("--skip-epub", action="store_true", help="Skip EPUB generation, only create markdown")
    parser.add_argument("--skip-md", action="store_true",
                        help="Skip markdown generation, use existing markdown files")
    parser.add_argument("--split-level", choices=sections.SPLIT_LEVELS, default="auto",
                        help="Split EPUB at detected headings, at the given heading rank and shallower, "
                             "or not at all (default: auto)")
    return parser.parse_args(argv)


def default_input_dir() -> Path:
    """./input relative to the working directory, created if missing."""
    input_dir = Path.cwd() / "input"
    input_dir.mkdir(exist_ok=True)
    return input_dir


def work_dir_for(pdf_path: Path, output_path: Optional[Path]) -> Path:
    return output_path / pdf_path.stem if output_path else workspace.default_output_dir(pdf_path)


def convert_to_markdown(pdf_path: Path, work_dir: Path, models: dict, args: argparse.Namespace) -> None:
    pages = extraction.page_range(args.start_page, args.max_pages)
    if args.start_page is not None and pages is None:
        log.warning("--start-page requires --max-pages in marker-pdf 1.x "
                    "(no open-ended page range is supported). Processing all pages.")
    print("Converting PDF to Markdown...")
    result = extraction.extract_pdf(pdf_path, models, pages)
    md_path = workspace.save_extraction(result, work_dir, pdf_path.stem)
    workspace.close_images(result.images)
    print(f"Markdown saved to: {md_path}")


def convert_to_epub(pdf_path: Path, work_dir: Path, split_level: str = "auto") -> Path:
    """Build the EPUB; metadata comes from description.json, then the PDF itself."""
    if not workspace.markdown_files(work_dir):
        raise ValueError(f"No markdown files found in: {work_dir}")
    description = BookDescription.for_workspace(
        work_dir,
        pdf_metadata=metadata_from_pdf_info(extraction.read_pdf_info(pdf_path)),
        fallback_title=pdf_path.stem,
    )
    description.save(work_dir)
    print(f"Converting Markdown to EPUB: {description.title} ({description.authors})")
    output = epub.build_epub(work_dir, epub.default_epub_path(work_dir), description,
                             split_level=split_level)
    print(f"EPUB creation complete: {output}")
    print(f"To change metadata, edit {work_dir / 'description.json'} and rerun with --skip-md.")
    return output


def process_pdf(pdf_path: Path, args: argparse.Namespace, models: Optional[dict]) -> None:
    work_dir = work_dir_for(pdf_path, args.output_path)
    if args.skip_md:
        if not work_dir.exists():
            raise FileNotFoundError(f"Markdown directory not found: {work_dir}")
        print(f"Using existing markdown files from: {work_dir}")
    else:
        convert_to_markdown(pdf_path, work_dir, models, args)
    if not args.skip_epub:
        convert_to_epub(pdf_path, work_dir, args.split_level)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)

    try:
        queue = workspace.find_pdfs(args.input_path or default_input_dir())
    except workspace.InputError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Found {len(queue)} PDF files to process")

    models = None
    if not args.skip_md:
        print(f"Using {extraction.describe_device()} for processing.")
        print("Loading marker models...")
        models = extraction.load_models()

    failed = []
    for pdf_path in queue:
        print(f"\nProcessing: {pdf_path.name}")
        try:
            process_pdf(pdf_path, args, models)
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}", file=sys.stderr)
            failed.append(pdf_path.name)

    if failed:
        print(f"\nFailed to process {len(failed)} of {len(queue)} PDF file(s):", file=sys.stderr)
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        return 1
    return 0
