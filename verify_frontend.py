import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            print("Navigating to https://uk-49s-dashboard-fixed.onrender.com")
            await page.goto("https://uk-49s-dashboard-fixed.onrender.com", wait_until="networkidle")
            await page.wait_for_timeout(5000) # Wait for scraping to finish
            await page.screenshot(path="screenshot.png", full_page=True)
            print("Screenshot saved as screenshot.png")
            title = await page.title()
            print(f"Page title: {title}")
        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
