#!/usr/bin/env python3
"""Generate a 1280x640 GitHub social-preview PNG.

GitHub uses this image when anyone unfurls a link to the repo
(LinkedIn, Twitter, Slack, Discord). The default is the maintainer's
avatar — replacing it with a designed card lifts click-through 3-5x.

Run via `python scripts/generate_social_preview.py` (Pillow already
in the venv as our cap-pipeline fallback). Outputs
`docs/design/social-preview.png` which you upload via
GitHub → Settings → Social preview.

Design discipline applied:
- Real type hierarchy (3 sizes, never more).
- Dark background that doesn't compete with LinkedIn's UI chrome.
- Anthropic-orange + Patrol-blue accents (signals the tech).
- One concrete number per badge.
- 64-px margins on every edge — text doesn't crowd corners on
  smaller unfurls.

This is deliberately type-only — no clip art, no phone illustrations
that look generic. If you want the iPhone+Android render later,
swap `_render_text_only_layout` for the AI-generated version once
you've produced one.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print(
        "ERROR: Pillow not installed. Run from the project venv:\n"
        "  cd packages/phone-controll && .venv/bin/python "
        "../../scripts/generate_social_preview.py",
        file=sys.stderr,
    )
    sys.exit(1)

# GitHub's documented spec — 1280x640 (2:1). Stay under 1 MB.
WIDTH = 1280
HEIGHT = 640

# Palette — picked so the card reads on every platform's chrome.
BG = (15, 20, 25)          # #0F1419 near-black, slight blue tilt
FG_PRIMARY = (245, 245, 245)
FG_DIM = (140, 145, 155)
ACCENT_ORANGE = (247, 108, 40)  # #F76C28 Anthropic orange
ACCENT_GREEN = (166, 226, 46)   # #A6E22E test-pass green
ACCENT_BLUE = (88, 166, 255)    # #58A6FF GitHub link blue

MARGIN = 64


def _try_font(*candidates: tuple[str, int]) -> ImageFont.ImageFont:
    """Try fonts in order; fall back to Pillow's default.

    macOS / Linux differ in where system fonts live. We try a handful
    of high-quality candidates before falling back to bitmap.
    """
    for name, size in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    draw.text(xy, text, font=font, fill=fill)


def _text_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
) -> int:
    """Pillow ≥ 10 uses textbbox; older versions used textsize."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    font_label: ImageFont.ImageFont,
    font_value: ImageFont.ImageFont,
    accent: tuple[int, int, int],
) -> int:
    """Draw a shields.io-style 2-tone badge. Returns the right-edge X.

    Left half: dim grey background + label.
    Right half: accent background + value.
    """
    pad_x = 14
    pad_y = 8
    label_w = _text_width(draw, label, font_label)
    value_w = _text_width(draw, value, font_value)

    left_w = label_w + 2 * pad_x
    right_w = value_w + 2 * pad_x
    height = 32
    radius = 4

    # Left half — dim grey
    draw.rounded_rectangle(
        (x, y, x + left_w, y + height),
        radius=radius,
        fill=(60, 65, 75),
    )
    # Right half — accent
    draw.rounded_rectangle(
        (x + left_w, y, x + left_w + right_w, y + height),
        radius=radius,
        fill=accent,
    )
    # Cover the inner corners so the two halves butt cleanly
    draw.rectangle(
        (x + left_w - radius, y, x + left_w + radius, y + height),
        fill=accent,
    )
    draw.rectangle(
        (x + left_w - radius, y, x + left_w, y + height),
        fill=(60, 65, 75),
    )

    _draw_text(draw, (x + pad_x, y + pad_y - 2), label, font_label, FG_PRIMARY)
    _draw_text(
        draw,
        (x + left_w + pad_x, y + pad_y - 2),
        value,
        font_value,
        # Dark text on bright accent reads better than white-on-orange.
        (20, 25, 30) if sum(accent) > 380 else FG_PRIMARY,
    )
    return x + left_w + right_w


def _render() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Headline candidates by descending priority. SF Pro on macOS,
    # DejaVu on Linux, Pillow default last-resort.
    headline_font = _try_font(
        ("/System/Library/Fonts/SFNS.ttf", 72),
        ("/System/Library/Fonts/Helvetica.ttc", 72),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72),
        ("DejaVuSans-Bold.ttf", 72),
    )
    sub_font = _try_font(
        ("/System/Library/Fonts/SFNS.ttf", 28),
        ("/System/Library/Fonts/Helvetica.ttc", 28),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28),
        ("DejaVuSans.ttf", 28),
    )
    side_heading_font = _try_font(
        ("/System/Library/Fonts/SFNSBold.ttf", 16),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16),
        ("DejaVuSans-Bold.ttf", 16),
    )
    side_item_font = _try_font(
        ("/System/Library/Fonts/SFNS.ttf", 22),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22),
        ("DejaVuSans.ttf", 22),
    )
    side_item_mono = _try_font(
        ("/System/Library/Fonts/SFMono.ttf", 20),
        ("/System/Library/Fonts/Menlo.ttc", 20),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20),
        ("DejaVuSansMono.ttf", 20),
    )
    badge_label_font = _try_font(
        ("/System/Library/Fonts/SFNS.ttf", 16),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16),
        ("DejaVuSans.ttf", 16),
    )
    badge_value_font = _try_font(
        ("/System/Library/Fonts/SFNSBold.ttf", 16),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16),
        ("DejaVuSans-Bold.ttf", 16),
    )
    footer_font = _try_font(
        ("/System/Library/Fonts/SFMono.ttf", 22),
        ("/System/Library/Fonts/Menlo.ttc", 22),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 22),
        ("DejaVuSansMono.ttf", 22),
    )

    # --- accent bar at top-left, signals "this is a tool, not a slide" ---
    draw.rectangle(
        (MARGIN, MARGIN, MARGIN + 80, MARGIN + 6),
        fill=ACCENT_ORANGE,
    )

    # --- LEFT COLUMN: headline + subhead + badges ---
    left_col_x = MARGIN
    headline_y = MARGIN + 32

    _draw_text(
        draw,
        (left_col_x, headline_y),
        "flutter-dev-agents",
        headline_font,
        FG_PRIMARY,
    )

    sub_y_1 = headline_y + 100
    _draw_text(
        draw,
        (left_col_x, sub_y_1),
        "The first MCP server for autonomous",
        sub_font,
        FG_PRIMARY,
    )
    _draw_text(
        draw,
        (left_col_x, sub_y_1 + 40),
        "Flutter testing on real iPhones",
        sub_font,
        FG_PRIMARY,
    )
    _draw_text(
        draw,
        (left_col_x, sub_y_1 + 80),
        "and Android devices.",
        sub_font,
        FG_PRIMARY,
    )

    # --- badge row, anchored near the footer ---
    badge_y = HEIGHT - MARGIN - 64
    x = left_col_x
    x = _draw_badge(
        draw, x, badge_y, "tools", "110",
        badge_label_font, badge_value_font, ACCENT_ORANGE,
    )
    x = _draw_badge(
        draw, x + 10, badge_y, "tests", "556",
        badge_label_font, badge_value_font, ACCENT_GREEN,
    )
    x = _draw_badge(
        draw, x + 10, badge_y, "license", "Apache-2.0",
        badge_label_font, badge_value_font, ACCENT_BLUE,
    )
    x = _draw_badge(
        draw, x + 10, badge_y, "MCP", "2025-06-18",
        badge_label_font, badge_value_font, ACCENT_ORANGE,
    )

    # --- RIGHT COLUMN: "What's inside" list ---
    # Anchored to the right edge with a subtle accent bar separator.
    right_col_x = 720
    separator_x = right_col_x - 24
    draw.rectangle(
        (separator_x, MARGIN + 32, separator_x + 3, HEIGHT - MARGIN - 32),
        fill=(40, 48, 58),
    )

    side_heading_y = MARGIN + 40
    _draw_text(
        draw,
        (right_col_x, side_heading_y),
        "WHAT'S INSIDE",
        side_heading_font,
        ACCENT_ORANGE,
    )

    # Three lines, each one concrete capability — never adjectives.
    items_y = side_heading_y + 36
    items = [
        ("•", "Patrol + flutter run --machine"),
        ("•", "WebDriverAgent (iOS 17+ RSD routing)"),
        ("•", "uiautomator2 + adb fallback"),
        ("•", "Cross-session device locks"),
        ("•", "Tiered tools for small LLMs"),
        ("•", "SBOM + CVE gating + runbook"),
    ]
    for i, (bullet, text) in enumerate(items):
        y = items_y + i * 36
        _draw_text(draw, (right_col_x, y), bullet, side_item_font, ACCENT_ORANGE)
        _draw_text(
            draw, (right_col_x + 24, y), text, side_item_mono, FG_PRIMARY,
        )

    # --- footer URL (bottom-right, dim) ---
    footer_text = "github.com/michal-giza/flutter-dev-agents"
    footer_w = _text_width(draw, footer_text, footer_font)
    _draw_text(
        draw,
        (WIDTH - MARGIN - footer_w, HEIGHT - MARGIN - 18),
        footer_text,
        footer_font,
        FG_DIM,
    )

    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "docs" / "design"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "social-preview.png"

    img = _render()
    # PNG max-compress; this image is < 100 KB easily.
    img.save(out_path, format="PNG", optimize=True, compress_level=9)

    # Surface the file path + size so the script doubles as a one-shot
    # smoke test ("did it actually write?").
    size_kb = out_path.stat().st_size / 1024
    print(f"✓ wrote {out_path}  ({size_kb:.1f} KB)")
    print()
    print("Upload to GitHub:")
    print("  Settings → Social preview → Edit → drag-drop this PNG.")
    print()
    print("Verify the unfurl:")
    print(
        "  https://www.opengraph.xyz/url/"
        "https%3A%2F%2Fgithub.com%2Fmichal-giza%2Fflutter-dev-agents"
    )


if __name__ == "__main__":
    main()
