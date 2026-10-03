"""One-time LinkedIn login helper. Opens a window, you log in, session is saved
to .li-profile for linkedin_sweep.py to reuse."""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
PROFILE = HERE / ".li-profile"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def has_session(ctx):
    return any(c["name"] == "li_at" for c in ctx.cookies())


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False,
            user_agent=UA, viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login", timeout=60000)
        print("BROWSER OPEN - log in to LinkedIn in this window (2FA if needed).", flush=True)
        print("Waiting for session cookie (li_at), up to 15 minutes...", flush=True)
        deadline = time.time() + 900
        while time.time() < deadline:
            if has_session(ctx):
                print("LOGGED IN - session saved to .li-profile. You can close the window.", flush=True)
                time.sleep(5)
                ctx.close()
                return
            time.sleep(5)
        print("TIMEOUT - no login detected in 15 minutes. Run this again when ready.", flush=True)
        ctx.close()


if __name__ == "__main__":
    main()
