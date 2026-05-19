# Social preview image

`social-preview.png` (1280×640, ~35 KB) is the image GitHub uses
when anyone links to the repo on LinkedIn, Twitter, Slack, Discord,
or any other unfurling chat.

## Upload it

1. https://github.com/michal-giza/flutter-dev-agents/settings
2. Scroll to **"Social preview"**.
3. Click **"Edit"** → **"Upload an image"**.
4. Pick `docs/design/social-preview.png`.
5. Save.

## Verify the unfurl

After upload, GitHub caches the image but third-party scrapers may
take ~10 minutes to pick it up. Test with:

```
https://www.opengraph.xyz/url/https%3A%2F%2Fgithub.com%2Fmichal-giza%2Fflutter-dev-agents
```

Or: paste the repo URL into a Slack/Discord DM to yourself and
check the unfurl preview.

## Regenerate

If you bump the test count, tool count, or want a different
tagline, edit the constants in
[`scripts/generate_social_preview.py`](../../scripts/generate_social_preview.py)
and re-run:

```bash
cd packages/phone-controll
.venv/bin/python ../../scripts/generate_social_preview.py
```

Then upload the new PNG via the same GitHub Settings page.

## Why a script and not a static PNG

- **Single source of truth** for the displayed numbers — when 556
  tests becomes 600, you don't need to ask a designer to update.
- **Fonts are baked in** — pulled from system locations on macOS
  (SF Pro, SF Mono) and Linux (DejaVu) so the rendering is
  consistent across machines.
- **No image dependency** beyond Pillow (already in our cap-pipeline
  deps), so contributors can iterate locally without installing
  Figma/Sketch.

## Spec

| Property | Value |
|---|---|
| Dimensions | 1280 × 640 (2:1) |
| Format | PNG, sRGB, 8-bit |
| File size target | < 1 MB (GitHub limit), < 100 KB realistic |
| Margins | 64 px all sides |
| Palette | bg #0F1419 · orange #F76C28 · green #A6E22E · blue #58A6FF |
| Typography | SF Pro (macOS) / DejaVu (Linux) with mono accents |
