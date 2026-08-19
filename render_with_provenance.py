import argparse
import re
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


VIEWPORT = {"width": 1440, "height": 900}
FOOTER_HEIGHT = 54


def font(size):
    path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    return ImageFont.truetype(path, size)


def wait_for_page(page):
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        print("  networkidle timeout; continuing with the loaded page", flush=True)
    page.evaluate("document.fonts.ready")
    page.evaluate(
        """
        async () => {
          for (let y = 0; y < document.documentElement.scrollHeight; y += 700) {
            window.scrollTo(0, y);
            await new Promise(requestAnimationFrame);
          }
          window.scrollTo(0, 0);
        }
        """
    )
    sleep(2)


def accept_consent(page):
    # Cookie platforms vary by region and may render inside an iframe.
    selectors = [
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Allow all')",
        "button:has-text('Allow All')",
        "button:has-text('Accept cookies')",
        "button:has-text('Accept Cookies')",
        "button:has-text('Aceitar todos')",
        "button:has-text('Aceitar Todos')",
        "button:has-text('Aceitar tudo')",
        "button:has-text('Aceitar Tudo')",
        "button:has-text('I agree')",
        "button:has-text('Agree')",
        "[id*='accept-all' i]",
        "[id*='acceptAll' i]",
        "[class*='accept-all' i]",
    ]
    for frame in page.frames:
        for selector in selectors:
            try:
                button = frame.locator(selector).first
                if button.count() and button.is_visible():
                    button.click(timeout=5_000)
                    page.wait_for_timeout(1_500)
                    return True
            except (PlaywrightTimeoutError, PlaywrightError):
                continue
    return False


def prepare_page(page):
    dismissed = 0
    for selector in [
        "[aria-label='Dismiss']",
        ".modal__dismiss",
        "button[aria-label='Close']",
        "button[aria-label='Fechar']",
    ]:
        controls = page.locator(selector)
        for index in range(controls.count()):
            try:
                control = controls.nth(index)
                if control.is_visible():
                    control.click(timeout=2_000)
                    dismissed += 1
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

    read_more = page.locator(
        "#r7-article-content button, #r7-article-content a, #r7-article-content [role='button'], "
        "#r7-article-content [class*='read-more' i], #r7-article-content [id*='read-more' i]"
    )
    expanded = 0
    if read_more.count():
        for index in range(read_more.count()):
            try:
                control = read_more.nth(index)
                if control.is_visible() and re.fullmatch(
                    r"\s*Leia mais\s*", control.inner_text(), re.IGNORECASE
                ) and control.get_attribute("aria-expanded") == "false":
                    control.click(timeout=2_000)
                    expanded += 1
            except (PlaywrightTimeoutError, PlaywrightError):
                pass

    # Remove ad slots and overlays while preserving article content and layout.
    page.evaluate(
        """
        () => {
          const selectors = [
            'iframe[src*="doubleclick"]',
            'iframe[src*="googlesyndication"]',
            'iframe[src*="googleadservices"]',
            'iframe[id*="google_ads_iframe" i]',
            'ins.adsbygoogle',
            '[data-ad-slot]',
            '#R7_header',
            '#R7_retangulo_lateral_1',
            '#R7_retangulo_lateral_3',
            '#R7_sticky_lateral',
            '[class^="ad-header-size"]',
            '[class^="ad-skeleton-fixed"]',
            '[class*="ima-ad-container"]',
            '[id^="slider_ima"]',
            '[class*="article-layout__footer-fixed"]'
          ];
          document.querySelectorAll(selectors.join(',')).forEach((element) => {
            element.style.setProperty('display', 'none', 'important');
            if (
              element.parentElement &&
              element.tagName === 'IFRAME' &&
              !['HTML', 'BODY'].includes(element.parentElement.tagName)
            ) {
              element.parentElement.style.setProperty('display', 'none', 'important');
            }
          });
          document.querySelectorAll('#r7-article-content, .b-article-body__content-container').forEach((element) => {
            element.style.setProperty('height', 'auto', 'important');
            element.style.setProperty('max-height', 'none', 'important');
            element.style.setProperty('overflow', 'visible', 'important');
            element.style.setProperty('-webkit-line-clamp', 'unset', 'important');
          });
          document.querySelectorAll('body *').forEach((element) => {
            const text = (element.innerText || '').trim().toLowerCase();
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            const isAdPlaceholder =
              (text === 'publicidade' || text === 'continua depois da publicidade') &&
              element.className.toString().includes('bg-wl-neutral-50') &&
              rect.width >= 250;
            if (isAdPlaceholder) {
              element.style.setProperty('display', 'none', 'important');
            }
          });
        }
        """
    )
    page.wait_for_timeout(500)
    return dismissed, expanded


def add_footer(image, url, timestamp):
    output = Image.new("RGB", (image.width, image.height + FOOTER_HEIGHT), "white")
    output.paste(image, (0, 0))
    draw = ImageDraw.Draw(output)
    draw.line((0, image.height, image.width, image.height), fill="#c8c8c8", width=2)
    label = f"URL: {url}    |    Captured: {timestamp}"
    draw.text((20, image.height + 17), label, fill="#444444", font=font(20))
    return output


def page_name(url):
    path = urlparse(url).path.strip("/")
    name = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return name or "website"


def render_page(page, output_dir, url):
    print(f"\n[1/4] Loading {url}", flush=True)
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    print("[2/4] Waiting for fonts and lazy-loaded content", flush=True)
    wait_for_page(page)
    consent = accept_consent(page)
    print(f"[3/4] Cookie consent: {'accepted' if consent else 'not shown'}", flush=True)
    wait_for_page(page)
    dismissed, expanded = prepare_page(page)
    print(
        f"  dismissed {dismissed} overlay(s), expanded {expanded} article 'Leia mais' control(s), and removed advertising slots",
        flush=True,
    )
    print(f"  document height after cleanup: {page.evaluate('document.documentElement.scrollHeight')}px", flush=True)

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    page_height = page.evaluate("document.documentElement.scrollHeight")
    page_count = (page_height + VIEWPORT["height"] - 1) // VIEWPORT["height"]
    captures = []
    print(f"[4/4] Capturing {page_count} viewport pages", flush=True)

    for index in range(page_count):
        scroll_y = min(index * VIEWPORT["height"], page_height - VIEWPORT["height"])
        page.evaluate("y => window.scrollTo(0, y)", scroll_y)
        sleep(0.3)
        screenshot = page.screenshot(full_page=False)
        image = Image.open(__import__("io").BytesIO(screenshot)).convert("RGB")
        captures.append(add_footer(image, url, timestamp))
        image.close()
        print(f"  page {index + 1}/{page_count}", flush=True)

    name = page_name(url)
    pdf_path = output_dir / f"{name}.pdf"
    captures[0].save(
        pdf_path,
        "PDF",
        resolution=144,
        save_all=True,
        append_images=captures[1:],
        title=name,
        author="Playwright screenshot renderer",
        subject=f"Source URL: {url}; captured: {timestamp}",
    )
    for capture in captures:
        capture.close()
    print(f"{name}: {page_height}px, {page_count} pages -> {pdf_path}")


def main():
    parser = argparse.ArgumentParser(description="Render websites as high-fidelity, screenshot-based PDFs.")
    parser.add_argument("urls", nargs="+", help="One or more website URLs to capture.")
    parser.add_argument(
        "-o",
        "--output-folder",
        type=Path,
        default=Path(__file__).parent,
        help="Folder where generated PDFs are written (default: html-to-pdf).",
    )
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        help="Chrome user-data directory to use for saved cookies and sessions.",
    )
    parser.add_argument(
        "--profile-directory",
        default="Default",
        help="Chrome profile directory inside --chrome-profile (default: Default).",
    )
    args = parser.parse_args()
    args.output_folder.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        if args.chrome_profile:
            context = playwright.chromium.launch_persistent_context(
                str(args.chrome_profile),
                channel="chrome",
                headless=True,
                args=[
                    f"--profile-directory={args.profile_directory}",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                ],
                viewport=VIEWPORT,
                device_scale_factor=2,
                color_scheme="light",
                locale="en-GB",
            )
            try:
                for url in args.urls:
                    page = context.new_page()
                    try:
                        render_page(page, args.output_folder, url)
                    finally:
                        page.close()
            finally:
                context.close()
            return

        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            for url in args.urls:
                context = browser.new_context(
                    viewport=VIEWPORT,
                    device_scale_factor=2,
                    color_scheme="light",
                    locale="en-GB",
                )
                try:
                    page = context.new_page()
                    render_page(page, args.output_folder, url)
                finally:
                    context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
