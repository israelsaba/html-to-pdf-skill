---
name: html-to-pdf
description: Use when converting one or more public website URLs into high-fidelity PDFs from browser-rendered screenshots, with cookie-consent handling, URL/timestamp provenance footers, and a configurable output folder.
---

# HTML to PDF

Use the browser-rendered screenshot workflow rather than `page.pdf()` or a browser print dialog when visual fidelity is the priority. This preserves the page's loaded fonts, responsive layout, images, colors, and fixed-position elements as seen in Chromium.

## Command

Run the renderer from the skill directory with one URL or a list of URLs and choose the output folder:

```bash
python3 "$SKILL_DIR/render_with_provenance.py" \
  --output-folder html-to-pdf \
  https://example.com/page-a \
  https://example.com/page-b
```

For pages that require an existing Chrome login, use a temporary copy of the saved Chrome user-data directory. Do not launch against a profile that is currently open in Chrome:

```bash
python3 "$SKILL_DIR/render_with_provenance.py" \
  --chrome-profile /path/to/copied-chrome-profile \
  --profile-directory Default \
  --output-folder html-to-pdf \
  https://example.com/private-page
```

The output filename is derived from each URL path. If no output folder is supplied, PDFs are written to `html-to-pdf/`.

## Workflow

1. Launch Chromium through Playwright with a fixed desktop viewport and a high device scale factor.
2. Wait for DOM content, fonts, network activity, lazy-loaded content, and images to settle.
3. Search every frame for common cookie-consent controls. Accept the broadest consent option before capturing the page.
4. Expand visible `Leia mais` controls before capture.
5. Dismiss blocking sign-in, cookie, and modal overlays using their visible close or dismiss controls.
6. Remove advertising iframes, ad slots, publicity overlays, and their reserved blocks without removing article content.
7. Capture one viewport at a time while scrolling through the full document.
8. Add a footer to each captured page containing the source URL and the local access timestamp.
9. Combine the images into a PDF and inspect page count, dimensions, and readability.

## Notes

- Keep the browser viewport and locale explicit for reproducible output.
- Do not remove the provenance footer from public-source captures.
- Do not preserve advertisements or ad placeholders in the generated PDF.
- Treat a `Leia mais` control belonging to the article body as a content control that should be expanded when possible. Do not open recommendation widgets such as `Veja mais notícias`.
- If a consent banner remains, add its selector to `accept_consent` in `~/.config/opencode/skills/html-to-pdf/render_with_provenance.py` and rerun.
- A screenshot-based PDF is intentionally image-based. Use browser print/PDF only when selectable text is more important than pixel fidelity.
- Capture only pages the user is authorized to access. Do not copy cookies, credentials, or private browser profiles into the repository or output folder.
