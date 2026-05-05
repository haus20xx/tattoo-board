#!/usr/bin/env python3
"""
Build a local HTML board from tattoo_idea_board_v2.md.

Pipeline:
  parse markdown → fetch images into cache/ → render board.html

Idempotent: re-runs skip already-cached items. Manual overrides at
cache/manual/<id>.* take precedence over fetched images.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).parent
MD_PATH = ROOT / "tattoo_idea_board_v2.md"
CACHE = ROOT / "cache"
IMAGES = CACHE / "images"
MANUAL = CACHE / "manual"
INDEX_PATH = CACHE / "index.json"
HTML_PATH = ROOT / "index.html"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DIRECT_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
IMAGE_EXTS_PREFERENCE = [".jpg", ".jpeg", ".png", ".webp", ".gif"]


# ---------- parsing ----------

# Headings to skip even if they contain yaml fences (e.g. schema docs).
SKIP_CATEGORIES = {"Format"}


def parse_markdown(path: Path) -> list[dict]:
    """Return list of items, each with 'category' added."""
    text = path.read_text()
    items: list[dict] = []
    # match: ## Category\n ... ```yaml ... ```
    pattern = re.compile(
        r"^##\s+(?P<cat>.+?)\s*$.*?```yaml\s*\n(?P<body>.*?)\n```",
        re.DOTALL | re.MULTILINE,
    )
    for m in pattern.finditer(text):
        cat = m.group("cat").strip()
        if cat in SKIP_CATEGORIES:
            continue
        body = m.group("body")
        parsed = yaml.safe_load(body) or []
        # ensure each entry is a dict (skip schema-doc YAML that has plain values)
        if not all(isinstance(it, dict) and "url" in it for it in parsed):
            continue
        for it in parsed:
            it["category"] = cat
            items.append(it)
    return items


# ---------- fetchers ----------

def item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def find_existing(item_id_: str, root: Path) -> Optional[Path]:
    """Return existing cached file (any extension) for this id, or None."""
    for ext in IMAGE_EXTS_PREFERENCE:
        p = root / f"{item_id_}{ext}"
        if p.exists():
            return p
    # generic fallback
    for p in root.glob(f"{item_id_}.*"):
        return p
    return None


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_get_text(url: str, timeout: int = 30) -> str:
    return http_get(url, timeout).decode("utf-8", errors="replace")


def ext_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    # walk path segments to find the first one ending in a known image ext
    # (handles wikia /File.png/revision/latest)
    for seg in reversed(path.split("/")):
        ext = Path(seg).suffix.lower()
        if ext in DIRECT_IMAGE_EXTS:
            return ext
    # fall back to query string format=jpg etc.
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    fmt = qs.get("format", [""])[0].lower()
    if fmt and ("." + fmt) in DIRECT_IMAGE_EXTS:
        return "." + fmt
    return ".jpg"


def fetch_direct(url: str, dest_stem: Path) -> Path:
    data = http_get(url)
    ext = ext_from_url(url)
    dest = dest_stem.with_suffix(ext)
    dest.write_bytes(data)
    return dest


def fetch_og_image(page_url: str, dest_stem: Path) -> Path:
    html_text = http_get_text(page_url)
    # try og:image first, then twitter:image
    for prop in ("og:image", "twitter:image"):
        m = re.search(
            rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
            html_text,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+name=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
                html_text,
                re.IGNORECASE,
            )
        if m:
            img_url = html.unescape(m.group(1))
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            return fetch_direct(img_url, dest_stem)
    raise RuntimeError(f"no og:image found on {page_url}")


def fetch_reddit(post_url: str, dest_stem: Path) -> Path:
    # Reddit JSON API: append .json
    api = post_url.rstrip("/") + ".json"
    req = urllib.request.Request(api, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    post = data[0]["data"]["children"][0]["data"]
    img = (
        post.get("url_overridden_by_dest")
        or post.get("url")
        or (post.get("preview", {}).get("images", [{}])[0].get("source", {}).get("url"))
    )
    if not img:
        raise RuntimeError(f"could not find image in reddit post {post_url}")
    img = html.unescape(img)
    return fetch_direct(img, dest_stem)


def fetch_instagram(url: str, dest_stem: Path, browser: str = "firefox") -> Path:
    """Use gallery-dl with browser cookies."""
    tmp = CACHE / "_tmp_ig"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        result = subprocess.run(
            [
                "gallery-dl",
                "--cookies-from-browser", browser,
                "-D", str(tmp),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gallery-dl failed (code {result.returncode}): {result.stderr.strip()}"
            )
        # pick best file: prefer images, prefer first by name (carousel order)
        files = sorted(tmp.iterdir())
        images = [
            f for f in files
            if f.suffix.lower() in DIRECT_IMAGE_EXTS
        ]
        if not images:
            video_only = any(
                f.suffix.lower() in (".mp4", ".m4a", ".webm")
                for f in files
            )
            if video_only:
                raise RuntimeError(
                    "video-only post (no poster image); drop a screenshot at "
                    f"cache/manual/<id>.jpg to override"
                )
            raise RuntimeError(f"gallery-dl produced no image files for {url}")
        chosen = images[0]
        dest = dest_stem.with_suffix(chosen.suffix.lower())
        shutil.copy2(chosen, dest)
        return dest
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


DIRECT_IMAGE_HOSTS = (
    "pbs.twimg.com",          # /media/<id>?format=jpg
    "wikia.nocookie.net",     # /.../File.png/revision/latest?cb=...
    "redd.it",
    "pinimg.com",
    "redbubble.net",
    "zcache.com",
    "cargocollective.com",
)


def fetch_item(url: str, dest_stem: Path) -> Path:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    # direct image URL by extension on path
    if any(path.endswith(ext) for ext in DIRECT_IMAGE_EXTS):
        return fetch_direct(url, dest_stem)

    # direct image URL by known image-CDN host (path may have no extension
    # or have suffixes like /revision/latest after the real filename)
    if any(host.endswith(h) or h in host for h in DIRECT_IMAGE_HOSTS):
        return fetch_direct(url, dest_stem)

    if "instagram.com" in host:
        return fetch_instagram(url, dest_stem)

    if "reddit.com" in host:
        return fetch_reddit(url, dest_stem)

    # general HTML page → og:image
    return fetch_og_image(url, dest_stem)


# ---------- main ----------

def build(category_filter: Optional[str], force: bool) -> dict:
    IMAGES.mkdir(parents=True, exist_ok=True)
    MANUAL.mkdir(parents=True, exist_ok=True)

    items = parse_markdown(MD_PATH)
    if category_filter:
        items = [it for it in items if it["category"] == category_filter]

    existing_index = {}
    if INDEX_PATH.exists():
        existing_index = {e["url"]: e for e in json.loads(INDEX_PATH.read_text())}

    out: list[dict] = []
    for it in items:
        url = it["url"]
        iid = item_id(url)
        record = {
            "id": iid,
            "url": url,
            "category": it["category"],
            "note": it.get("note", ""),
            "kind": it.get("kind", ""),
            "starred": bool(it.get("starred", False)),
            "owned": bool(it.get("owned", False)),
            "todo": it.get("todo", ""),
        }

        # 1. manual override wins
        manual_file = find_existing(iid, MANUAL)
        if manual_file:
            record["status"] = "manual"
            record["image"] = str(manual_file.relative_to(ROOT))
            out.append(record)
            print(f"[manual] {iid} {url}")
            continue

        # 2. existing cached file (skip unless --force)
        cached = find_existing(iid, IMAGES)
        if cached and not force:
            record["status"] = "ok"
            record["image"] = str(cached.relative_to(ROOT))
            out.append(record)
            print(f"[cached] {iid} {url}")
            continue

        # 3. fetch
        try:
            dest_stem = IMAGES / iid
            path = fetch_item(url, dest_stem)
            record["status"] = "ok"
            record["image"] = str(path.relative_to(ROOT))
            print(f"[ok]     {iid} {url} → {path.name}")
        except Exception as e:
            record["status"] = "failed"
            record["error"] = str(e)
            record["image"] = None
            print(f"[FAIL]   {iid} {url}: {e}", file=sys.stderr)
        out.append(record)

    INDEX_PATH.write_text(json.dumps(out, indent=2))
    return out


# ---------- rendering ----------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tattoo Lookbook</title>
<style>
  :root { --bg:#1a1a1a; --panel:#262626; --panel2:#1f1f1f; --text:#eee; --muted:#888; --accent:#6ab0ff; --gold:#f5c542; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; }

  /* ---------- header / TOC ---------- */
  header.lean {
    position: sticky; top: 0; z-index: 10;
    background: rgba(20,20,20,0.95);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid #333;
    padding: 0.6rem 1rem;
  }
  header.lean .titlebar {
    display: flex; align-items: center; gap: 0.75rem;
  }
  header.lean h1 {
    margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: 0.02em;
  }
  header.lean .summary { color: var(--muted); font-size: 0.8rem; margin-left: auto; }
  header.lean button.toc-toggle, header.lean .view-toggle {
    background: #333; color: var(--text); border: 1px solid #444;
    border-radius: 4px; cursor: pointer; font-size: 0.8rem;
  }
  header.lean button.toc-toggle { padding: 0.25rem 0.6rem; }
  header.lean button.toc-toggle:hover { background: #404040; }
  header.lean .view-toggle {
    display: inline-flex; padding: 0; overflow: hidden;
  }
  header.lean .view-toggle button {
    background: transparent; color: var(--muted); border: none;
    padding: 0.25rem 0.65rem; cursor: pointer; font-size: 0.8rem;
  }
  header.lean .view-toggle button:hover { color: var(--text); }
  header.lean .view-toggle button.active { background: #4a4a4a; color: var(--text); }

  #toc {
    display: none;
    margin-top: 0.6rem;
    max-height: 60vh; overflow-y: auto;
    background: var(--panel2); border: 1px solid #333; border-radius: 6px;
    padding: 0.6rem 0.75rem;
    font-size: 0.85rem;
  }
  #toc.open { display: block; }
  #toc ul { list-style: none; padding: 0; margin: 0; }
  #toc li.cat { margin-bottom: 0.35rem; }
  #toc .cat-row {
    display: flex; align-items: center; gap: 0.4rem;
    cursor: pointer; user-select: none;
    padding: 0.15rem 0;
  }
  #toc .cat-row:hover { color: var(--accent); }
  #toc .cat-caret { display: inline-block; width: 0.7rem; transition: transform 0.15s; color: var(--muted); }
  #toc li.cat.collapsed .cat-caret { transform: rotate(-90deg); }
  #toc li.cat.collapsed ul.items { display: none; }
  #toc ul.items { padding-left: 1.3rem; margin: 0.2rem 0 0.5rem; }
  #toc ul.items li { padding: 0.1rem 0; }
  #toc ul.items a {
    color: #ccc; text-decoration: none; display: block;
    border-radius: 3px; padding: 0.1rem 0.3rem;
  }
  #toc ul.items a:hover { background: #333; color: var(--accent); }
  #toc ul.items a.starred::before { content: "★ "; color: var(--gold); }

  /* ---------- main content ---------- */
  main { padding: 1rem 1.25rem 3rem; }

  details.category {
    margin: 1.5rem 0 0;
    border-top: 1px solid #333;
  }
  details.category > summary {
    list-style: none; cursor: pointer;
    padding: 0.6rem 0; font-size: 1.15rem; font-weight: 600;
    display: flex; align-items: center; gap: 0.5rem;
  }
  details.category > summary::-webkit-details-marker { display: none; }
  details.category > summary::before {
    content: "▾"; color: var(--muted); width: 1rem; display: inline-block;
    transition: transform 0.15s;
  }
  details.category:not([open]) > summary::before { transform: rotate(-90deg); }
  details.category > summary .count { color: var(--muted); font-weight: normal; font-size: 0.85rem; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1rem; margin-top: 0.5rem; }

  /* ---------- card (item details) ---------- */
  details.card {
    background: var(--panel); border-radius: 8px; overflow: hidden;
    position: relative; display: flex; flex-direction: column;
  }
  details.card.starred { outline: 2px solid var(--gold); }
  details.card > summary {
    list-style: none; cursor: pointer;
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.4rem 0.6rem;
    background: #2c2c2c; border-bottom: 1px solid #333;
    font-size: 0.85rem;
  }
  details.card > summary::-webkit-details-marker { display: none; }
  details.card > summary .caret {
    color: var(--muted); width: 0.8rem; transition: transform 0.15s;
    flex-shrink: 0;
  }
  details.card:not([open]) > summary .caret { transform: rotate(-90deg); }
  details.card > summary .thumb {
    width: 32px; height: 32px; border-radius: 3px;
    object-fit: cover; flex-shrink: 0; background: #111;
  }
  details.card > summary .summary-name {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    flex: 1; color: #ddd;
  }
  details.card.starred > summary .summary-name::after { content: " ★"; color: var(--gold); }
  details.card.diverged { box-shadow: inset 3px 0 0 var(--accent); }

  /* star toggle button in expanded body */
  button.star-toggle {
    background: transparent; border: 1px solid #444; color: var(--muted);
    padding: 0.2rem 0.5rem; border-radius: 4px; cursor: pointer;
    font-size: 0.8rem; margin-bottom: 0.4rem;
  }
  button.star-toggle:hover { background: #333; color: var(--text); }
  button.star-toggle.on { color: var(--gold); border-color: var(--gold); }

  .img-wrap { background: #111; aspect-ratio: 1 / 1; display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .img-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .meta { padding: 0.6rem 0.75rem; font-size: 0.85rem; }
  .meta .note { color: #ddd; margin-bottom: 0.4rem; min-height: 1.2em; }
  .meta .tags { display: flex; gap: 0.4rem; flex-wrap: wrap; font-size: 0.7rem; color: var(--muted); margin-bottom: 0.3rem; }
  .meta .tags span { background: #333; padding: 0.1rem 0.4rem; border-radius: 3px; }
  .meta a.src { color: var(--accent); text-decoration: none; word-break: break-all; font-size: 0.7rem; }
  .meta a.src:hover { text-decoration: underline; }
  details.card.failed .img-wrap { background: #3a1a1a; color: #f88; font-size: 0.8rem; padding: 1rem; text-align: center; }
  details.card.failed .img-wrap a { color: #fbb; }
  .todo { background: #3a2a1a; color: #fc8; padding: 0.3rem 0.5rem; font-size: 0.7rem; margin-top: 0.3rem; border-radius: 3px; }

  /* anchor offset so sticky header doesn't cover targets */
  details.card, details.category { scroll-margin-top: 4rem; }

  /* ---------- view modes ---------- */
  /* default: list view shows .grid (cards), hides .gallery */
  body[data-view="list"] .gallery { display: none; }
  body[data-view="gallery"] .grid { display: none; }

  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .gallery .tile {
    position: relative;
    aspect-ratio: 1 / 1;
    background: #111; border-radius: 4px; overflow: hidden;
    cursor: pointer; border: none; padding: 0;
  }
  .gallery .tile img {
    width: 100%; height: 100%; object-fit: cover; display: block;
    transition: transform 0.15s;
  }
  .gallery .tile:hover img { transform: scale(1.05); }
  .gallery .tile.starred { outline: 2px solid var(--gold); outline-offset: -2px; }
  .gallery .tile.starred::after {
    content: "★"; position: absolute; top: 4px; right: 6px;
    color: var(--gold); font-size: 0.9rem; text-shadow: 0 0 3px #000;
  }
  .gallery .tile.failed {
    background: #3a1a1a; color: #f88; font-size: 0.7rem;
    display: flex; align-items: center; justify-content: center;
    text-align: center; padding: 0.4rem;
  }

  /* ---------- modal ---------- */
  .modal-backdrop {
    display: none;
    position: fixed; inset: 0; z-index: 100;
    background: rgba(0,0,0,0.85);
    align-items: center; justify-content: center;
    padding: 2rem;
  }
  .modal-backdrop.open { display: flex; }
  .modal {
    background: var(--panel); border-radius: 8px;
    max-width: min(1100px, 95vw); max-height: 92vh;
    display: flex; flex-direction: column; overflow: hidden;
    position: relative;
  }
  .modal .img-wrap {
    background: #000; flex: 1; min-height: 0;
    display: flex; align-items: center; justify-content: center;
  }
  .modal .img-wrap img { max-width: 100%; max-height: 75vh; object-fit: contain; display: block; }
  .modal .modal-meta { padding: 0.75rem 1rem 1rem; border-top: 1px solid #333; }
  .modal .modal-meta .note { font-size: 1rem; color: #eee; margin-bottom: 0.5rem; }
  .modal .modal-meta .tags { display: flex; gap: 0.4rem; flex-wrap: wrap; font-size: 0.75rem; color: var(--muted); margin-bottom: 0.4rem; }
  .modal .modal-meta .tags span { background: #333; padding: 0.1rem 0.4rem; border-radius: 3px; }
  .modal .modal-meta a.src { color: var(--accent); font-size: 0.8rem; word-break: break-all; }
  .modal .modal-meta button.star-toggle { margin-right: 0.5rem; }
  .modal .close {
    position: absolute; top: 0.5rem; right: 0.5rem;
    background: rgba(0,0,0,0.6); color: #fff; border: none;
    width: 2rem; height: 2rem; border-radius: 50%; cursor: pointer;
    font-size: 1.2rem; line-height: 1;
  }
  .modal .close:hover { background: rgba(0,0,0,0.9); }
  .modal .nav {
    position: absolute; top: 50%; transform: translateY(-50%);
    background: rgba(0,0,0,0.5); color: #fff; border: none;
    width: 2.5rem; height: 3rem; cursor: pointer; font-size: 1.5rem;
  }
  .modal .nav.prev { left: 0; border-radius: 0 4px 4px 0; }
  .modal .nav.next { right: 0; border-radius: 4px 0 0 4px; }
  .modal .nav:hover { background: rgba(0,0,0,0.8); }
  .modal .nav:disabled { opacity: 0.2; cursor: default; }
</style>
</head>
<body>
<header class="lean">
  <div class="titlebar">
    <h1>Tattoo Lookbook</h1>
    <button class="toc-toggle" id="toc-toggle" aria-expanded="false">Contents</button>
    <div class="view-toggle" role="group" aria-label="View mode">
      <button data-view="list" class="active">List</button>
      <button data-view="gallery">Gallery</button>
    </div>
    <span class="summary">__SUMMARY__</span>
  </div>
  <nav id="toc" aria-label="Table of contents">__TOC__</nav>
</header>
<div class="modal-backdrop" id="modal" role="dialog" aria-modal="true" aria-hidden="true">
  <div class="modal">
    <button class="close" id="modal-close" aria-label="Close">×</button>
    <button class="nav prev" id="modal-prev" aria-label="Previous">‹</button>
    <button class="nav next" id="modal-next" aria-label="Next">›</button>
    <div class="img-wrap"><img id="modal-img" src="" alt=""></div>
    <div class="modal-meta">
      <div class="note" id="modal-note"></div>
      <div style="margin-bottom: 0.5rem;">
        <button class="star-toggle" type="button" id="modal-star" aria-pressed="false">
          <span class="star-glyph">☆</span> <span class="star-label">star</span>
        </button>
      </div>
      <div class="tags" id="modal-tags"></div>
      <a class="src" id="modal-src" href="#" target="_blank"></a>
    </div>
  </div>
</div>
<main>
__SECTIONS__
</main>
<script>
/* Embedded item metadata for the modal — single source per item id. */
const ITEM_DATA = __ITEM_DATA__;

(() => {
  // ---------- TOC show/hide ----------
  const tocBtn = document.getElementById('toc-toggle');
  const toc = document.getElementById('toc');
  tocBtn.addEventListener('click', () => {
    const open = toc.classList.toggle('open');
    tocBtn.setAttribute('aria-expanded', String(open));
  });

  // ---------- TOC category collapse (purely visual) ----------
  toc.querySelectorAll('.cat-row').forEach(row => {
    row.addEventListener('click', () => {
      row.parentElement.classList.toggle('collapsed');
    });
  });

  // ---------- TOC link click: ensure ancestors are open; in gallery mode, redirect item links to category ----------
  toc.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      let id = a.getAttribute('href').slice(1);
      // In gallery mode, item links jump to the parent category instead.
      if (document.body.dataset.view === 'gallery' && id.startsWith('item-')) {
        const card = document.getElementById(id);
        const cat = card && card.closest('details.category');
        if (cat) {
          e.preventDefault();
          cat.open = true;
          cat.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return;
        }
      }
      const target = document.getElementById(id);
      if (!target) return;
      let el = target;
      while (el) {
        if (el.tagName === 'DETAILS') el.open = true;
        el = el.parentElement;
      }
    });
  });

  // ---------- View mode toggle (list / gallery) ----------
  const VIEW_KEY = 'tattoo_lookbook.view.v1';
  const viewButtons = document.querySelectorAll('.view-toggle button[data-view]');
  function setView(mode) {
    document.body.dataset.view = mode;
    viewButtons.forEach(b => b.classList.toggle('active', b.dataset.view === mode));
    localStorage.setItem(VIEW_KEY, mode);
  }
  viewButtons.forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  setView(localStorage.getItem(VIEW_KEY) || 'list');

  // ---------- Star overrides (localStorage) ----------
  const STORAGE_KEY = 'tattoo_lookbook.star_overrides.v1';

  function loadOverrides() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
    catch { return {}; }
  }
  function saveOverrides(o) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(o));
  }

  /**
   * Effective star state = override if present, else markdown's value.
   * Diverged = override exists AND differs from markdown.
   */
  function applyStar(card, overrides) {
    const id = card.dataset.id;
    const mdStarred = card.dataset.mdStarred === 'true';
    const override = overrides[id];
    const effective = (override === undefined) ? mdStarred : override;
    const diverged = (override !== undefined) && (override !== mdStarred);

    card.classList.toggle('starred', effective);
    card.classList.toggle('diverged', diverged);

    const btn = card.querySelector('button.star-toggle');
    if (btn) {
      btn.classList.toggle('on', effective);
      btn.setAttribute('aria-pressed', String(effective));
      btn.querySelector('.star-glyph').textContent = effective ? '★' : '☆';
      btn.querySelector('.star-label').textContent =
        effective ? (diverged ? 'starred (local)' : 'starred')
                  : (diverged ? 'unstarred (local)' : 'star');
    }

    // mirror to TOC entry
    const tocLink = document.querySelector(`#toc a[href="#${card.id}"]`);
    if (tocLink) tocLink.classList.toggle('starred', effective);
  }

  /* Apply effective star state to gallery tiles (mirrors card state). */
  function applyTileStar(id, effective) {
    document.querySelectorAll(`.gallery .tile[data-id="${id}"]`).forEach(t => {
      t.classList.toggle('starred', effective);
    });
  }

  /* Effective star helper used by modal & toggles. */
  function effectiveStar(id) {
    const card = document.querySelector(`details.card[data-id="${id}"]`);
    if (!card) return false;
    return card.classList.contains('starred');
  }

  /* Toggle star for an item id; updates card, tile, modal. */
  function toggleStar(id) {
    const card = document.querySelector(`details.card[data-id="${id}"]`);
    if (!card) return;
    const mdStarred = card.dataset.mdStarred === 'true';
    const current = card.classList.contains('starred');
    const next = !current;
    const o = loadOverrides();
    if (next === mdStarred) delete o[id];
    else o[id] = next;
    saveOverrides(o);
    applyStar(card, o);
    applyTileStar(id, next);
    if (modalState.id === id) renderModalStar();
  }

  function init() {
    const overrides = loadOverrides();
    const cards = document.querySelectorAll('details.card[data-id]');
    cards.forEach(card => {
      applyStar(card, overrides);
      applyTileStar(card.dataset.id, card.classList.contains('starred'));
      const btn = card.querySelector('button.star-toggle');
      if (!btn) return;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleStar(card.dataset.id);
      });
    });
  }
  init();

  // ---------- Modal ----------
  const modal = document.getElementById('modal');
  const modalImg = document.getElementById('modal-img');
  const modalNote = document.getElementById('modal-note');
  const modalTags = document.getElementById('modal-tags');
  const modalSrc = document.getElementById('modal-src');
  const modalStar = document.getElementById('modal-star');
  const modalClose = document.getElementById('modal-close');
  const modalPrev = document.getElementById('modal-prev');
  const modalNext = document.getElementById('modal-next');

  const modalState = { id: null, ids: [], idx: -1 };

  function renderModalStar() {
    if (!modalState.id) return;
    const eff = effectiveStar(modalState.id);
    modalStar.classList.toggle('on', eff);
    modalStar.setAttribute('aria-pressed', String(eff));
    modalStar.querySelector('.star-glyph').textContent = eff ? '★' : '☆';
    modalStar.querySelector('.star-label').textContent = eff ? 'starred' : 'star';
  }

  function openModal(id, siblingIds) {
    const data = ITEM_DATA[id];
    if (!data) return;
    modalState.id = id;
    modalState.ids = siblingIds || [id];
    modalState.idx = modalState.ids.indexOf(id);

    if (data.image && data.status !== 'failed') {
      modalImg.src = data.image;
      modalImg.style.display = '';
      modalImg.alt = data.note || '';
    } else {
      modalImg.removeAttribute('src');
      modalImg.style.display = 'none';
    }
    modalNote.textContent = data.note || '(no description)';
    if (data.todo) {
      modalNote.textContent += '  —  TODO: ' + data.todo;
    }
    const tags = [];
    if (data.kind) tags.push(data.kind);
    tags.push(data.status);
    if (data.owned) tags.push('owned');
    if (data.status === 'failed' && data.error) tags.push('error: ' + data.error);
    modalTags.innerHTML = tags.map(t =>
      `<span>${t.replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]))}</span>`
    ).join('');
    modalSrc.href = data.url;
    modalSrc.textContent = data.url;

    modalPrev.disabled = modalState.idx <= 0;
    modalNext.disabled = modalState.idx < 0 || modalState.idx >= modalState.ids.length - 1;

    renderModalStar();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    modalState.id = null;
    modalState.ids = [];
    modalState.idx = -1;
  }

  function navModal(delta) {
    const ni = modalState.idx + delta;
    if (ni < 0 || ni >= modalState.ids.length) return;
    openModal(modalState.ids[ni], modalState.ids);
  }

  modalClose.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  modalPrev.addEventListener('click', () => navModal(-1));
  modalNext.addEventListener('click', () => navModal(1));
  modalStar.addEventListener('click', () => { if (modalState.id) toggleStar(modalState.id); });
  document.addEventListener('keydown', (e) => {
    if (!modal.classList.contains('open')) return;
    if (e.key === 'Escape') closeModal();
    else if (e.key === 'ArrowLeft') navModal(-1);
    else if (e.key === 'ArrowRight') navModal(1);
  });

  // Wire up gallery tiles
  document.querySelectorAll('details.category').forEach(cat => {
    const tiles = cat.querySelectorAll('.gallery .tile[data-id]');
    const ids = Array.from(tiles).map(t => t.dataset.id);
    tiles.forEach(tile => {
      tile.addEventListener('click', () => openModal(tile.dataset.id, ids));
    });
  });
})();
</script>
</body>
</html>
"""


def render_html(records: list[dict]) -> str:
    by_cat: dict[str, list[dict]] = {}
    for r in records:
        by_cat.setdefault(r["category"], []).append(r)

    # build a slug for each category for anchors
    def slugify(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    sections = []
    toc_cats = []
    for cat, recs in by_cat.items():
        cat_slug = "cat-" + slugify(cat)
        cards = []
        toc_items = []
        for r in recs:
            item_anchor = "item-" + r["id"]
            classes = ["card"]
            if r["starred"]:
                classes.append("starred")
            if r["status"] == "failed":
                classes.append("failed")

            # display name = note, fallback to host or id
            display_name = r["note"] or urllib.parse.urlparse(r["url"]).netloc or r["id"]

            # collapsed-summary thumbnail
            if r["status"] != "failed" and r.get("image"):
                thumb_html = f'<img class="thumb" src="{html.escape(r["image"])}" loading="lazy" alt="">'
            else:
                thumb_html = '<span class="thumb" style="display:inline-block;background:#3a1a1a;"></span>'

            # expanded body
            if r["status"] == "failed":
                body_img = (
                    f'<div class="img-wrap">FAILED: {html.escape(r.get("error", ""))}'
                    f'<br><a href="{html.escape(r["url"])}" target="_blank">view source</a></div>'
                )
            else:
                body_img = (
                    f'<div class="img-wrap">'
                    f'<a href="{html.escape(r["url"])}" target="_blank">'
                    f'<img src="{html.escape(r["image"])}" loading="lazy" alt="{html.escape(r["note"])}">'
                    f'</a></div>'
                )

            tags = [r["kind"]] if r["kind"] else []
            tags.append(r["status"])
            if r["owned"]:
                tags.append("owned")
            tag_html = "".join(f"<span>{html.escape(t)}</span>" for t in tags)
            todo_html = (
                f'<div class="todo">TODO: {html.escape(r["todo"])}</div>'
                if r["todo"] else ""
            )

            md_starred = "true" if r["starred"] else "false"
            cards.append(
                f'<details class="{" ".join(classes)}" id="{item_anchor}" '
                f'data-id="{r["id"]}" data-md-starred="{md_starred}" open>'
                f'<summary>'
                f'<span class="caret">▾</span>'
                f'{thumb_html}'
                f'<span class="summary-name">{html.escape(display_name)}</span>'
                f'</summary>'
                f'{body_img}'
                f'<div class="meta">'
                f'<button class="star-toggle" type="button" aria-pressed="false">'
                f'<span class="star-glyph">☆</span> <span class="star-label">star</span>'
                f'</button>'
                f'<div class="tags">{tag_html}</div>'
                f'{todo_html}'
                f'<a class="src" href="{html.escape(r["url"])}" target="_blank">{html.escape(r["url"])}</a>'
                f'</div></details>'
            )

            star_cls = " class=\"starred\"" if r["starred"] else ""
            toc_items.append(
                f'<li><a href="#{item_anchor}"{star_cls}>{html.escape(display_name)}</a></li>'
            )

        # gallery view tiles for the same items
        tiles = []
        for r in recs:
            tile_classes = ["tile"]
            if r["starred"]:
                tile_classes.append("starred")
            if r["status"] == "failed":
                tile_classes.append("failed")
            display_name = r["note"] or urllib.parse.urlparse(r["url"]).netloc or r["id"]
            if r["status"] != "failed" and r.get("image"):
                inner = (
                    f'<img src="{html.escape(r["image"])}" loading="lazy" '
                    f'alt="{html.escape(display_name)}">'
                )
            else:
                inner = f'<span>{html.escape(display_name)}<br>(failed)</span>'
            tiles.append(
                f'<button type="button" class="{" ".join(tile_classes)}" '
                f'data-id="{r["id"]}" aria-label="{html.escape(display_name)}">{inner}</button>'
            )

        sections.append(
            f'<details class="category" id="{cat_slug}" open>'
            f'<summary>{html.escape(cat)} <span class="count">({len(recs)})</span></summary>'
            f'<div class="grid">{"".join(cards)}</div>'
            f'<div class="gallery">{"".join(tiles)}</div>'
            f'</details>'
        )
        toc_cats.append(
            f'<li class="cat">'
            f'<div class="cat-row"><span class="cat-caret">▾</span>'
            f'<a href="#{cat_slug}" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;">'
            f'{html.escape(cat)}</a> <span style="color:var(--muted);font-size:0.75rem;">({len(recs)})</span>'
            f'</div>'
            f'<ul class="items">{"".join(toc_items)}</ul>'
            f'</li>'
        )

    toc_html = f'<ul>{"".join(toc_cats)}</ul>'

    ok = sum(1 for r in records if r["status"] in ("ok", "manual"))
    failed = sum(1 for r in records if r["status"] == "failed")
    summary = f"{len(records)} items · {ok} fetched · {failed} failed"

    # Item data for modal (id-keyed)
    item_data = {
        r["id"]: {
            "url": r["url"],
            "image": r.get("image"),
            "note": r.get("note", ""),
            "kind": r.get("kind", ""),
            "status": r.get("status", ""),
            "starred": bool(r.get("starred", False)),
            "owned": bool(r.get("owned", False)),
            "todo": r.get("todo", ""),
            "error": r.get("error", ""),
        }
        for r in records
    }
    item_data_json = json.dumps(item_data)

    return (HTML_TEMPLATE
            .replace("__SUMMARY__", html.escape(summary))
            .replace("__TOC__", toc_html)
            .replace("__ITEM_DATA__", item_data_json)
            .replace("__SECTIONS__", "\n".join(sections)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="Tribute: Outer Wilds",
                    help="Filter to one category (default: Outer Wilds). Use '' for all.")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if cached.")
    ap.add_argument("--no-fetch", action="store_true",
                    help="Skip fetching, render existing index.json only.")
    args = ap.parse_args()

    cat = args.category or None

    if args.no_fetch:
        if not INDEX_PATH.exists():
            print("no index.json yet; run without --no-fetch first", file=sys.stderr)
            sys.exit(1)
        records = json.loads(INDEX_PATH.read_text())
    else:
        records = build(cat, args.force)

    HTML_PATH.write_text(render_html(records))
    print(f"\nWrote {HTML_PATH}")
    print(f"Open: file://{HTML_PATH}")


if __name__ == "__main__":
    main()
