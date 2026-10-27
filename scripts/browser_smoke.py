"""Optional Chromium checks. Install playwright separately; not needed by the app.

Creates a sample forecast on the target service. Run against a demo workspace.
"""

from __future__ import annotations

import argparse


def main() -> None:
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--chromium", help="Optional installed Chromium executable path")
    args = parser.parse_args()
    errors: list[str] = []
    with sync_playwright() as p:
        options = {"headless": True}
        if args.chromium:
            options["executable_path"] = args.chromium
        browser = p.chromium.launch(**options)
        try:
            desktop = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = desktop.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.base_url)
            page.wait_for_function("!document.querySelector('#connection-label').textContent.includes('Checking')")
            page.locator('[data-view="telemetry"]').click()
            page.locator("#tab-sample").click()
            page.locator("#load-sample").click()
            page.wait_for_function("document.querySelector('#row-count').textContent === '24 / 24 rows'")
            page.locator("#run-data-forecast").click()
            page.wait_for_function("document.querySelector('#global-notice').textContent.includes('Forecast ready')", timeout=120_000)
            if page.locator("#forecast-rows tr").count() != 24:
                raise RuntimeError("Expected 24 forecast rows")
            for view in ("overview", "controller", "alerts", "copilot", "model", "settings", "forecast"):
                page.locator(f'[data-view="{view}"]').click()

            mobile = browser.new_context(viewport={"width": 390, "height": 844})
            mobile.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError');}})")
            phone = mobile.new_page()
            phone.on("pageerror", lambda error: errors.append(str(error)))
            phone.goto(args.base_url)
            phone.wait_for_function("!document.querySelector('#connection-label').textContent.includes('Checking')")
            phone.locator("#theme-toggle").click()
            if not phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth"):
                raise RuntimeError("Mobile layout overflows horizontally")

            page.route("**/api/sample", lambda route: route.abort())
            page.locator('[data-view="telemetry"]').click()
            page.locator("#tab-sample").click()
            page.locator("#load-sample").click()
            page.wait_for_function("document.querySelector('#global-notice').textContent.includes('Cannot reach the GridSense backend')")
            if errors:
                raise RuntimeError("Browser exceptions: " + "; ".join(errors))
            print("PASS: real forecast, 24 rows, navigation, mobile layout, blocked storage, and browser network error recovery.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
