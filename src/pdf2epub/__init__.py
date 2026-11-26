"""
pdf2epub: convert PDF files to EPUB via Markdown.

The package is a library first; `pdf2epub.cli` is a thin command-line layer on
top of it. A typical programmatic conversion:

    from pdf2epub import extraction, workspace, epub
    from pdf2epub.metadata import BookDescription

    models = extraction.load_models()          # once per process
    result = extraction.extract_pdf(pdf_path, models)
    workspace.save_extraction(result, work_dir, pdf_path.stem)

    description = BookDescription.for_workspace(work_dir)
    epub.build_epub(work_dir, work_dir / "book.epub", description)
"""

__all__ = ["epub", "extraction", "html", "images", "metadata", "workspace"]
