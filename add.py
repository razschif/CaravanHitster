import os
import re
import shutil
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

SONGS_JS_PATH = "songs.js"
DEST_FOLDER = Path(r"C:\Raz\CaravanHitster\songs")

# ─────────────────────────────────────────────────────────────────────────────
# ANSI Colors for Terminal Output
# ─────────────────────────────────────────────────────────────────────────────

class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Song:
    id: int
    original_file: Path
    clean_name: str
    title: str
    year: str


@dataclass
class ProcessingResult:
    songs_added: list[Song]
    songs_skipped: list[tuple[Path, str]]  # (file, reason)
    folders_skipped: list[tuple[Path, str]]  # (folder, reason)
    errors: list[tuple[Path, str]]  # (path, error message)


# ─────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────────

def get_max_id(js_text: str) -> int:
    """Extract the highest song ID from the JS file."""
    ids = re.findall(r"id:\s*(\d+)", js_text)
    return max(map(int, ids)) if ids else 0


def clean_title(filename: str) -> str:
    """Convert filename to a readable song title."""
    name = Path(filename).stem
    # Remove common prefixes like track numbers
    name = re.sub(r"^\d+[\s._-]*", "", name)
    # Remove remaining numbers that look like IDs
    name = re.sub(r"\b\d{5,}\b", "", name)
    # Clean up separators
    name = name.replace("_", " ").replace("-", " ")
    # Normalize whitespace and title case
    return " ".join(name.split()).title()


def clean_file_name(filename: str) -> str:
    """Convert filename to a URL-safe format."""
    name = Path(filename).stem
    # Replace spaces and underscores with hyphens
    name = re.sub(r"[\s_]+", "-", name)
    # Remove any non-alphanumeric characters except hyphens
    name = re.sub(r"[^\w-]", "", name)
    # Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)
    return name.lower().strip("-")


def extract_year(folder_name: str) -> str | None:
    """Extract a 4-digit year from folder name."""
    match = re.search(r"\b(19|20)\d{2}\b", folder_name)
    return match.group() if match else None


# ─────────────────────────────────────────────────────────────────────────────
# JS File Manipulation
# ─────────────────────────────────────────────────────────────────────────────

def find_year_block(js_text: str, year: str) -> tuple[int, int] | None:
    """Find the start and end positions of a year's song array."""
    pattern = rf"{{\s*year:\s*{year},\s*songs:\s*\["
    match = re.search(pattern, js_text)
    if not match:
        return None

    start = match.start()
    bracket_count = 0

    for i in range(start, len(js_text)):
        if js_text[i] == "[":
            bracket_count += 1
        elif js_text[i] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                return start, i
    return None


def format_song_entry(song: Song) -> str:
    """Format a song as a JS object entry."""
    return f'      {{ id: {song.id}, file: "{song.clean_name}", title: "{song.title}" }}'


def insert_into_js(js_text: str, year: str, songs: list[Song]) -> str:
    """Insert songs into the JS file, creating year block if needed."""
    entries = ",\n".join(format_song_entry(s) for s in songs)
    block = find_year_block(js_text, year)

    if block:
        start, end = block
        # Find the last entry in the array
        insert_pos = js_text.rfind("]", start, end)
        # Check if array is empty
        array_content = js_text[start:insert_pos].strip()
        if array_content.endswith("["):
            # Empty array - no comma needed before
            return js_text[:insert_pos] + "\n" + entries + "\n    " + js_text[insert_pos:]
        else:
            return js_text[:insert_pos] + ",\n" + entries + "\n    " + js_text[insert_pos:]
    else:
        # Create new year block
        new_block = f"""
  {{
    year: {year},
    songs: [
{entries}
    ]
  }},"""
        # Find the end of the array and insert before closing
        return js_text.rstrip().rstrip("];") + new_block + "\n];"


# ─────────────────────────────────────────────────────────────────────────────
# Visualization
# ─────────────────────────────────────────────────────────────────────────────

def print_header():
    """Print the application header."""
    print()
    print(colored("╔════════════════════════════════════════════════════════════╗", Colors.CYAN))
    print(colored("║           🎵  SONG LIBRARY PROCESSOR  🎵                   ║", Colors.CYAN))
    print(colored("╚════════════════════════════════════════════════════════════╝", Colors.CYAN))
    print()


def print_section(title: str):
    """Print a section header."""
    print()
    print(colored(f"{'─' * 60}", Colors.DIM))
    print(colored(f"  {title}", Colors.BOLD + Colors.BLUE))
    print(colored(f"{'─' * 60}", Colors.DIM))


def print_progress(current: int, total: int, message: str):
    """Print a progress indicator."""
    bar_width = 30
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    percent = (current / total * 100) if total > 0 else 0
    print(f"\r  [{colored(bar, Colors.GREEN)}] {percent:5.1f}% {message[:30]:<30}", end="", flush=True)


def print_tree(result: ProcessingResult):
    """Print the processing results as a tree structure."""
    # Group songs by year
    by_year = defaultdict(list)
    for song in result.songs_added:
        by_year[song.year].append(song)

    if by_year:
        print_section("📁 Songs Added")
        years = sorted(by_year.keys(), reverse=True)

        for i, year in enumerate(years):
            is_last_year = i == len(years) - 1
            branch = "└──" if is_last_year else "├──"
            print(f"  {branch} 📅 {colored(year, Colors.YELLOW)} ({len(by_year[year])} songs)")

            songs = by_year[year]
            for j, song in enumerate(songs):
                is_last_song = j == len(songs) - 1
                prefix = "    " if is_last_year else "│   "
                song_branch = "└──" if is_last_song else "├──"
                print(f"  {prefix}{song_branch} 🎵 {colored(song.title, Colors.GREEN)}")
                print(f"  {prefix}{'    ' if is_last_song else '│   '}{colored(f'ID: {song.id} | File: {song.clean_name}', Colors.DIM)}")


def print_summary(result: ProcessingResult):
    """Print a summary of the processing results."""
    print_section("📊 Summary")

    # Stats
    stats = [
        ("Songs Added", len(result.songs_added), Colors.GREEN),
        ("Songs Skipped", len(result.songs_skipped), Colors.YELLOW),
        ("Folders Skipped", len(result.folders_skipped), Colors.YELLOW),
        ("Errors", len(result.errors), Colors.RED),
    ]

    for label, count, color in stats:
        indicator = "●" if count > 0 else "○"
        print(f"  {colored(indicator, color)} {label}: {colored(str(count), color + Colors.BOLD)}")

    # Show skipped items if any
    if result.songs_skipped:
        print()
        print(colored("  Skipped Songs:", Colors.YELLOW))
        for file, reason in result.songs_skipped[:5]:
            print(f"    • {file.name}: {reason}")
        if len(result.songs_skipped) > 5:
            print(f"    ... and {len(result.songs_skipped) - 5} more")

    if result.folders_skipped:
        print()
        print(colored("  Skipped Folders:", Colors.YELLOW))
        for folder, reason in result.folders_skipped:
            print(f"    • {folder.name}: {reason}")

    if result.errors:
        print()
        print(colored("  Errors:", Colors.RED))
        for path, error in result.errors:
            print(f"    ✗ {path.name}: {error}")


# ─────────────────────────────────────────────────────────────────────────────
# Core Processing
# ─────────────────────────────────────────────────────────────────────────────

def process_folder(folder: Path, year: str, next_id: int, result: ProcessingResult) -> int:
    """Process all MP3 files in a folder."""
    mp3_files = list(folder.glob("*.mp3"))

    for file in mp3_files:
        try:
            # Check if file already exists in destination
            dest_path = DEST_FOLDER / file.name
            if dest_path.exists():
                result.songs_skipped.append((file, "Already exists in destination"))
                continue

            title = clean_title(file.name)
            clean_name = clean_file_name(file.name)

            # Copy file
            shutil.copy2(file, dest_path)

            # Create song record
            song = Song(
                id=next_id,
                original_file=file,
                clean_name=clean_name,
                title=title,
                year=year
            )
            result.songs_added.append(song)
            next_id += 1

        except PermissionError:
            result.errors.append((file, "Permission denied"))
        except Exception as e:
            result.errors.append((file, str(e)))

    return next_id


def main(parent_folder: str):
    print_header()

    parent = Path(parent_folder)

    # Validate input
    if not parent.exists():
        print(colored(f"  ✗ Error: Folder not found: {parent}", Colors.RED))
        return

    if not parent.is_dir():
        print(colored(f"  ✗ Error: Not a directory: {parent}", Colors.RED))
        return

    # Load JS file
    print_section("🔧 Initialization")

    js_path = Path(SONGS_JS_PATH)
    if not js_path.exists():
        print(colored(f"  ✗ Error: JS file not found: {js_path}", Colors.RED))
        return

    with open(js_path, "r", encoding="utf-8") as f:
        js_text = f.read()

    print(f"  ✓ Loaded {colored(SONGS_JS_PATH, Colors.CYAN)}")

    # Create destination folder
    DEST_FOLDER.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Destination: {colored(str(DEST_FOLDER), Colors.CYAN)}")

    # Get starting ID
    next_id = get_max_id(js_text) + 1
    print(f"  ✓ Next ID: {colored(str(next_id), Colors.CYAN)}")

    # Find folders to process
    folders = [f for f in parent.iterdir() if f.is_dir()]
    print(f"  ✓ Found {colored(str(len(folders)), Colors.CYAN)} subfolders")

    # Process folders
    print_section("⚙️  Processing")

    result = ProcessingResult(
        songs_added=[],
        songs_skipped=[],
        folders_skipped=[],
        errors=[]
    )

    songs_by_year: dict[str, list[Song]] = defaultdict(list)

    for i, folder in enumerate(folders):
        print_progress(i + 1, len(folders), folder.name)

        year = extract_year(folder.name)
        if not year:
            result.folders_skipped.append((folder, "No year found in folder name"))
            continue

        start_count = len(result.songs_added)
        next_id = process_folder(folder, year, next_id, result)

        # Group newly added songs by year
        for song in result.songs_added[start_count:]:
            songs_by_year[song.year].append(song)

    print()  # New line after progress bar

    # Update JS file
    if result.songs_added:
        print_section("💾 Updating JS File")

        for year in sorted(songs_by_year.keys()):
            js_text = insert_into_js(js_text, year, songs_by_year[year])
            print(f"  ✓ Added {len(songs_by_year[year])} songs to year {colored(year, Colors.YELLOW)}")

        # Backup original
        backup_path = js_path.with_suffix(".js.backup")
        shutil.copy2(js_path, backup_path)
        print(f"  ✓ Backup saved to {colored(str(backup_path), Colors.DIM)}")

        # Write updated file
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(js_text)
        print(f"  ✓ Saved {colored(SONGS_JS_PATH, Colors.CYAN)}")

    # Show results
    print_tree(result)
    print_summary(result)

    print()
    print(colored("  ✨ Processing complete!", Colors.GREEN + Colors.BOLD))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        path = input(f"\n  {colored('Enter parent folder path:', Colors.CYAN)} ").strip()
        if path:
            main(path)
        else:
            print(colored("  ✗ No path provided", Colors.RED))
    except KeyboardInterrupt:
        print(colored("\n\n  Cancelled by user.", Colors.YELLOW))
