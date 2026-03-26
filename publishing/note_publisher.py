"""
note.com publisher using Playwright for browser automation
"""

import asyncio
from pathlib import Path
from datetime import datetime
from config.settings import Settings
from storage.models import ArticleData
import logging

logger = logging.getLogger(__name__)


class NotePublisher:
    """Publishes articles to note.com using Playwright"""

    def __init__(self, settings: Settings):
        self.settings = settings

        if not settings.has_note_credentials:
            raise ValueError(
                "note.com credentials required: NOTE_EMAIL and NOTE_PASSWORD in .env"
            )

        try:
            from playwright.async_api import async_playwright
            self.async_playwright = async_playwright
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None
        except ImportError:
            raise ImportError(
                "Playwright not installed. Install with: pip install playwright"
            )

    async def _init_browser(self):
        """Initialize Playwright browser"""
        if self._browser:
            return

        logger.debug("Initializing Playwright browser...")
        try:
            self._playwright = await self.async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            # Save cookies to session file for faster subsequent logins
            cookies_file = Path.cwd() / ".claude" / "note_cookies.json"
            if cookies_file.exists():
                cookies = self._context.cookies()
                # Load saved cookies if available
                try:
                    import json
                    with open(cookies_file) as f:
                        saved_cookies = json.load(f)
                    await self._context.add_cookies(saved_cookies)
                except Exception as e:
                    logger.warning(f"Could not load saved cookies: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def _save_cookies(self):
        """Save browser cookies for future sessions"""
        if self._context:
            try:
                cookies = await self._context.cookies()
                cookies_file = Path.cwd() / ".claude" / "note_cookies.json"
                cookies_file.parent.mkdir(parents=True, exist_ok=True)

                import json
                with open(cookies_file, "w") as f:
                    json.dump(cookies, f)
                logger.debug("Cookies saved for next session")
            except Exception as e:
                logger.warning(f"Could not save cookies: {e}")

    async def _login(self):
        """Login to note.com"""
        logger.info("Logging into note.com...")

        self._page = await self._context.new_page()

        try:
            # Navigate to login page
            await self._page.goto("https://note.com/login", wait_until="networkidle")

            # Fill email
            await self._page.fill(
                'input[type="email"]', self.settings.note_email
            )

            # Fill password
            await self._page.fill(
                'input[type="password"]', self.settings.note_password
            )

            # Click login button
            await self._page.click('button[type="submit"]')

            # Wait for navigation to dashboard
            await self._page.wait_for_url("https://note.com/dashboard", timeout=30000)

            await self._save_cookies()
            logger.info("Successfully logged into note.com")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def publish(self, article: ArticleData, as_draft: bool = None) -> dict:
        """
        Publish article to note.com

        Args:
            article: ArticleData object with title and content
            as_draft: If None, uses settings.note_default_draft

        Returns:
            dict with publication status and URL
        """

        if as_draft is None:
            as_draft = self.settings.note_default_draft

        status = "draft" if as_draft else "public"

        logger.info(f"Publishing article: '{article.title}' (status: {status})")

        try:
            # Initialize browser if needed
            await self._init_browser()

            # Create new page for writing
            self._page = await self._context.new_page()

            # Navigate to new article creation page
            await self._page.goto(
                "https://note.com/compose",
                wait_until="networkidle",
                timeout=30000
            )

            # Wait for editor to load
            await self._page.wait_for_selector(
                '[contenteditable="true"]', timeout=30000
            )

            # Set title
            title_elem = await self._page.query_selector(
                'input[placeholder*="タイトル"]'
            )
            if title_elem:
                await title_elem.fill(article.title)
            else:
                # Fallback: Click first input and type
                await self._page.fill("input", article.title)

            logger.debug("Title entered")

            # Set content (Markdown format)
            # note.com uses a rich editor, we'll paste content
            content_elem = await self._page.query_selector('[contenteditable="true"]')
            if content_elem:
                await content_elem.click()
                await self._page.keyboard.press("Control+A")
                await self._page.keyboard.press("Delete")
                await self._page.keyboard.type(article.content[:1000])  # Type first 1000 chars
                # Paste remaining content
                if len(article.content) > 1000:
                    # Use clipboard for large content
                    import pyperclip
                    pyperclip.copy(article.content)
                    await self._page.keyboard.press("Control+V")

            logger.debug("Content entered")

            # Set status (draft or public)
            if as_draft:
                # Look for draft button/toggle
                draft_button = await self._page.query_selector(
                    'button:has-text("下書きで保存")'
                )
                if draft_button:
                    await draft_button.click()
            else:
                # Find and click publish button
                publish_button = await self._page.query_selector(
                    'button:has-text("投稿")'
                )
                if publish_button:
                    await publish_button.click()

            # Wait for confirmation
            await self._page.wait_for_timeout(2000)

            # Get the article URL if published
            article_url = None
            if not as_draft:
                article_url = self._page.url

            logger.info(
                f"Article published successfully: {article_url or 'draft saved'}"
            )

            return {
                "success": True,
                "status": status,
                "url": article_url,
                "published_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Publication failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def close(self):
        """Close browser and cleanup"""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.debug("Browser closed")

    def publish_sync(self, article: ArticleData, as_draft: bool = None) -> dict:
        """
        Synchronous wrapper for async publish method.
        Use this for non-async contexts.
        """
        return asyncio.run(self.publish(article, as_draft))


# Simplified version without pyperclip dependency
class NotePublisherLite:
    """Lighter version of NotePublisher using WebDriver protocol"""

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.has_note_credentials:
            raise ValueError(
                "note.com credentials required: NOTE_EMAIL and NOTE_PASSWORD in .env"
            )

    async def publish(self, article: ArticleData, as_draft: bool = None) -> dict:
        """Simplified publish using page interactions"""
        from playwright.async_api import async_playwright

        if as_draft is None:
            as_draft = self.settings.note_default_draft

        status = "draft" if as_draft else "public"
        logger.info(f"Publishing '{article.title}' to note.com ({status})...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # Step 1: Login
                await page.goto("https://note.com/login")
                await page.fill('input[type="email"]', self.settings.note_email)
                await page.fill('input[type="password"]', self.settings.note_password)
                await page.click('button[type="submit"]')
                await page.wait_for_url("https://note.com/dashboard", timeout=30000)
                logger.debug("Logged in successfully")

                # Step 2: Go to compose page
                await page.goto("https://note.com/compose")
                await page.wait_for_selector('[contenteditable="true"]', timeout=30000)

                # Step 3: Fill title
                await page.fill(
                    'input[placeholder*="タイトル"]',
                    article.title
                )

                # Step 4: Fill content
                content_box = await page.query_selector('[contenteditable="true"]')
                if content_box:
                    await content_box.click()
                    # For large content, type in chunks
                    await page.type('[contenteditable="true"]', article.content[:5000])

                # Step 5: Save/Publish
                await page.wait_for_timeout(1000)

                if as_draft:
                    # Click save as draft
                    await page.click('button:has-text("下書きで保存")')
                else:
                    # Click publish
                    await page.click('button:has-text("投稿")')

                await page.wait_for_timeout(2000)

                return {
                    "success": True,
                    "status": status,
                    "url": page.url if not as_draft else None,
                    "published_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(f"Publication failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "status": status,
                }
            finally:
                await browser.close()

    def publish_sync(self, article: ArticleData, as_draft: bool = None) -> dict:
        """Synchronous wrapper"""
        return asyncio.run(self.publish(article, as_draft))
