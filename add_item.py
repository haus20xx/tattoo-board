#!/usr/bin/env python3
"""
Interactive helper to add new items to tattoo_idea_board_v2.md and the cache.

Workflow:
  prompt URL -> fetch image -> prompt title/category/kind -> update markdown ->
  repeat or finish (rebuilds index.html at the end).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Reuse the existing pipeline's fetchers / parser.
sys.path.insert(0, str(Path(__file__).parent))
from build_board import (  # type: ignore
    MD_PATH,
    IMAGES,
    ROOT,
    parse_markdown,
    fetch_item,
    item_id,
    find_existing,
    build,
    render_html,
)

VALID_KINDS = ("tattoo", "art", "lookbook")


# ---------- prompt helpers ----------


def prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        s = input(f"{label}{suffix}: ").strip()
        if s:
            return s
        if default is not None:
            return default


def yesno(label: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        s = input(f"{label} [{d}]: ").strip().lower()
        if not s:
            return default
        if s in ("y", "yes"):
            return True
        if s in ("n", "no"):
            return False


def pick_category(existing: list[str]) -> str:
    print("\nExisting categories:")
    for i, c in enumerate(existing, 1):
        print(f"  {i:2d}. {c}")
    print("  (or type a new category name to create one)")
    while True:
        s = input("Category: ").strip()
        if not s:
            continue
        # numeric selection?
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(existing):
                return existing[idx - 1]
            print(f"  out of range (1..{len(existing)})")
            continue
        # exact-name match?
        if s in existing:
            return s
        # case-insensitive match?
        matches = [c for c in existing if c.lower() == s.lower()]
        if len(matches) == 1:
            return matches[0]
        # otherwise propose new
        if yesno(f"Create new category {s!r}?", default=False):
            return s


def pick_kind() -> str:
    while True:
        s = prompt(f"Kind ({'/'.join(VALID_KINDS)})", default="tattoo").lower()
        if s in VALID_KINDS:
            return s
        print(f"  must be one of {VALID_KINDS}")


# ---------- markdown surgery ----------


def yaml_escape(s: str) -> str:
    """Quote a string for YAML if needed."""
    if not s:
        return '""'
    # things that force quoting: leading/trailing whitespace, special yaml chars,
    # numeric-looking, boolean-looking
    needs_quote = (
        s != s.strip()
        or s.lower() in ("true", "false", "null", "yes", "no", "on", "off")
        or any(c in s for c in ":#&*!|>'\"%@`{}[],")
        or s.startswith(("- ", "? ", ": "))
    )
    if not needs_quote:
        return s
    # use double quotes; escape backslashes and quotes
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_item_block(url: str, note: str, kind: str) -> str:
    lines = [f"- url: {url}"]
    if note:
        lines.append(f"  note: {yaml_escape(note)}")
    lines.append(f"  kind: {kind}")
    return "\n".join(lines)


CATEGORY_BLOCK_RE = re.compile(
    r"(^##\s+(?P<cat>.+?)\s*$.*?```yaml\s*\n)(?P<body>.*?)(\n```)",
    re.DOTALL | re.MULTILINE,
)


def append_to_existing_category(
    text: str, category: str, item_block: str
) -> str | None:
    """Insert item_block at the end of the named category's yaml block.
    Returns updated text, or None if the category wasn't found.
    """

    def sub(m: re.Match[str]) -> str:
        if m.group("cat").strip() != category:
            return m.group(0)
        body = m.group("body").rstrip()
        new_body = f"{body}\n{item_block}" if body else item_block
        return f"{m.group(1)}{new_body}{m.group(4)}"

    new_text, _ = CATEGORY_BLOCK_RE.subn(sub, text, count=0)
    # detect whether any block was actually changed (subn count is matches, not replacements)
    if category in {m.group("cat").strip() for m in CATEGORY_BLOCK_RE.finditer(text)}:
        return new_text
    return None


def append_new_category(text: str, category: str, item_block: str) -> str:
    section = f"\n## {category}\n\n```yaml\n{item_block}\n```\n"
    if not text.endswith("\n"):
        text += "\n"
    return text + section


def existing_urls(items: list[dict[str, Any]]) -> set[str]:
    return {it["url"] for it in items}


# ---------- main loop ----------


def fetch_with_status(url: str) -> tuple[str, str | None, str | None]:
    """Try to fetch an image for url. Returns (status, image_rel_path, error)."""
    iid = item_id(url)
    existing = find_existing(iid, IMAGES)
    if existing:
        return ("ok", str(existing.relative_to(ROOT)), None)
    try:
        IMAGES.mkdir(parents=True, exist_ok=True)
        path = fetch_item(url, IMAGES / iid)
        return ("ok", str(path.relative_to(ROOT)), None)
    except Exception as e:
        return ("failed", None, str(e))


URL_LINE_RE = re.compile(r"https?://\S+")


def extract_urls(text: str) -> list[str]:
    """Extract URLs from a chunk of pasted text. One URL per line preferred,
    but we tolerate surrounding noise (markdown brackets, trailing punctuation).
    """
    urls: list[str] = []
    for line in text.splitlines():
        for match in URL_LINE_RE.findall(line):
            # strip common trailing punctuation that's almost never part of a URL
            cleaned = match.rstrip(").,;:>]")
            # strip surrounding angle brackets if present
            cleaned = cleaned.strip("<>")
            urls.append(cleaned)
    # de-duplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def read_batch_paste() -> list[str]:
    """Read multi-line URL paste from stdin, terminated by blank line or EOF."""
    print("Paste URLs (one per line). Empty line or Ctrl-D to finish:")
    lines: list[str] = []
    try:
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
    except EOFError:
        pass
    return extract_urls("\n".join(lines))


def add_one(
    url: str,
    items: list[dict[str, Any]],
    categories: list[str],
    progress: str = "",
) -> str:
    """Run a single add cycle for a known URL.
    Returns 'added', 'skipped', or 'duplicate'.
    """
    print("\n" + "=" * 60)
    print(f"{progress}{url}")

    if url in existing_urls(items) and not yesno(
        "URL already in board. Add again anyway?", default=False
    ):
        return "duplicate"

    print("  Fetching image...")
    status, image, err = fetch_with_status(url)
    if status == "ok":
        print(f"  ✓ cached → {image}")
    else:
        print(f"  ✗ {err}")
        if not yesno("Add to board anyway (will render as failed tile)?", default=True):
            return "skipped"

    note = prompt("Title / note (short description)", default="")
    category = pick_category(categories)
    kind = pick_kind()

    block = render_item_block(url, note, kind)
    print(f"\n  Will add to '{category}':")
    for line in block.splitlines():
        print(f"    {line}")
    if not yesno("Confirm?", default=True):
        return "skipped"

    text = MD_PATH.read_text()
    updated = append_to_existing_category(text, category, block)
    if updated is None:
        updated = append_new_category(text, category, block)
        print(f"  + new category '{category}' appended to file")
    MD_PATH.write_text(updated)
    print(f"  ✓ wrote {MD_PATH.name}")

    items.append({"url": url, "note": note, "kind": kind, "category": category})
    if category not in categories:
        categories.append(category)
    return "added"


def run_batch(
    urls: list[str],
    items: list[dict[str, Any]],
    categories: list[str],
) -> int:
    """Iterate through a list of URLs. Returns count of added items."""
    added = 0
    total = len(urls)
    for i, url in enumerate(urls, 1):
        progress = f"[{i}/{total}] "
        try:
            result = add_one(url, items, categories, progress=progress)
            if result == "added":
                added += 1
        except (KeyboardInterrupt, EOFError):
            print("\n(item aborted)")
            if not yesno("Continue with remaining URLs?", default=True):
                break
    return added


def main() -> None:
    description = (__doc__ or "").strip().splitlines()[0] if __doc__ else None
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "urls_file",
        nargs="?",
        help="Optional file containing URLs to add (one per line). "
        "If omitted, prompts for a batch paste, then offers "
        "interactive single-URL mode.",
    )
    args = ap.parse_args()

    if not MD_PATH.exists():
        print(f"error: {MD_PATH} not found", file=sys.stderr)
        sys.exit(1)

    items = parse_markdown(MD_PATH)
    seen: set[str] = set()
    categories = [
        c for c in (it["category"] for it in items) if not (c in seen or seen.add(c))
    ]

    print(f"Tattoo board: {len(items)} items across {len(categories)} categories")

    added = 0

    # Phase 1: batch input (file or paste)
    if args.urls_file:
        text = Path(args.urls_file).read_text()
        batch = extract_urls(text)
        print(f"Loaded {len(batch)} URL(s) from {args.urls_file}")
    else:
        batch = read_batch_paste()
        if batch:
            print(f"Detected {len(batch)} URL(s).")

    if batch:
        added += run_batch(batch, items, categories)

    # Phase 2: optional interactive single-URL adds
    if not batch or yesno("\nAdd more URLs interactively?", default=False):
        while True:
            try:
                url = prompt("URL (blank to finish)", default="")
            except (KeyboardInterrupt, EOFError):
                print()
                break
            if not url:
                break
            try:
                result = add_one(url, items, categories)
                if result == "added":
                    added += 1
            except (KeyboardInterrupt, EOFError):
                print("\n(item aborted)")

    if added == 0:
        print("\nNothing added.")
        return

    print(f"\n{added} item(s) added. Rebuilding index.html...")
    records = build(category_filter=None, force=False)
    Path(ROOT / "index.html").write_text(render_html(records))
    print("✓ wrote index.html")
    print("\nTo publish:")
    print("  cd ~/Documents/tattoo_board")
    print("  git add -A && git commit -m 'add: <items>' && git push")


if __name__ == "__main__":
    main()
