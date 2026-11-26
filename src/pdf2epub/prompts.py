"""Interactive terminal prompts used by the CLI (kept out of the library core)."""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .metadata import BookDescription, metadata_fields

InputFn = Callable[[str], str]


def ask(prompt: str, default: str = "", input_fn: InputFn = input) -> str:
    answer = input_fn(f"{prompt} [{default}]: ").strip()
    return answer or default


def ask_yes_no(prompt: str, input_fn: InputFn = input) -> bool:
    while True:
        answer = input_fn(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'")


def ask_metadata(description: BookDescription, input_fn: InputFn = input,
                 now: Optional[datetime] = None) -> BookDescription:
    """Prompt for each metadata field, defaulting to the saved value."""
    print("\nPlease provide the following metadata for your EPUB (press Enter to use default value):")
    fields = metadata_fields(description.metadata, now or datetime.now())
    metadata = {f.key: ask(f.label, f.default, input_fn) for f in fields}
    return BookDescription(metadata, description.default_css, description.chapters, description.cover_image)


def open_in_editor(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    elif os.name == "posix":
        subprocess.run(["xdg-open", str(path)], check=True)
    else:
        os.startfile(str(path))


def review_markdown(path: Path, input_fn: InputFn = input) -> Optional[str]:
    """
    Offer to open the markdown in an editor before conversion.
    Returns the (possibly edited) content, or None if the user aborts.
    """
    content = path.read_text(encoding="utf-8")
    if not ask_yes_no("\nWould you like to review the markdown file before conversion? (y/n): ", input_fn):
        return content
    try:
        open_in_editor(path)
    except Exception as e:
        print(f"\nError opening markdown file: {e}")
        print("Proceeding with conversion...")
        return content
    while True:
        answer = input_fn("\nPress Enter when you're done editing (or 'q' to abort): ").lower()
        if answer == "q":
            return None
        if answer == "":
            return path.read_text(encoding="utf-8")
