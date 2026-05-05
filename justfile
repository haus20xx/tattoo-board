# Tattoo Lookbook — task runner.
# Run `just` to list recipes.

set positional-arguments

# Default: show recipes.
default:
    @just --list

# Full build: fetch any new images and re-render index.html.
build:
    uv run --with pyyaml python build_board.py --category ""

# Re-render index.html from existing cache (no network).
rebuild:
    uv run --with pyyaml python build_board.py --category "" --no-fetch

# Add new items (paste URLs interactively, or `just add urls.txt`).
add *args:
    uv run --with pyyaml python add_item.py "$@"

# Open index.html in your default browser.
serve:
    open index.html
