from playwright.async_api import async_playwright
from src.core.config import settings
import os
from datetime import datetime
import asyncio
import time
from src.utils.b2_storage import b2_storage
import base64
from src.utils.logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    def __init__(self):
        self.browser = None
        self.pw = None
        self.pages = {}
        self.contexts = {}
        self.max_full_page_screenshot_pixels = 20_000_000
        self.max_full_page_screenshot_side = 16_384

    async def start(self):
        if not self.pw:
            self.pw = await async_playwright().start()
        if self.browser and not self.browser.is_connected():
            logger.warning("Browser disconnected; resetting browser manager state")
            await self.reset_browser(close_playwright=False)
        if not self.browser:
            self.browser = await self.pw.chromium.launch(headless=settings.HEADLESS)

    async def reset_browser(self, close_playwright: bool = False):
        for thread_id in list(self.pages.keys()):
            await self.close_session(thread_id)
        if self.browser is not None:
            try:
                if self.browser.is_connected():
                    await self.browser.close()
            except Exception as e:
                logger.warning("Browser close failed during reset", extra={"data": {"error": str(e)}})
        self.browser = None
        if close_playwright and self.pw is not None:
            try:
                await self.pw.stop()
            except Exception as e:
                logger.warning("Playwright stop failed during reset", extra={"data": {"error": str(e)}})
            self.pw = None

    async def get_page(self, thread_id: str):
        await self.start()
        page = self.pages.get(thread_id)
        if page is not None and not page.is_closed():
            return page
        if page is not None:
            self.pages.pop(thread_id, None)
            self.contexts.pop(thread_id, None)

        try:
            context = await self.browser.new_context()
        except Exception as e:
            logger.warning("Creating browser context failed; restarting browser once", extra={"data": {"error": str(e)}})
            await self.reset_browser(close_playwright=False)
            await self.start()
            context = await self.browser.new_context()
        page = await context.new_page()
        self.contexts[thread_id] = context
        self.pages[thread_id] = page
        return self.pages[thread_id]

    async def close_session(self, thread_id: str):
        page = self.pages.pop(thread_id, None)
        context = self.contexts.pop(thread_id, None)
        if page is not None:
            try:
                if not page.is_closed():
                    await page.close()
            except Exception as e:
                logger.warning("Page close failed", extra={"data": {"thread_id": thread_id, "error": str(e)}})
        if context is not None:
            try:
                await context.close()
            except Exception as e:
                logger.warning("Context close failed", extra={"data": {"thread_id": thread_id, "error": str(e)}})
            logger.info("Browser session closed", extra={"data": {"thread_id": thread_id}})

    async def navigate(self, url: str, thread_id: str):
        page = await self.get_page(thread_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    async def capture(self, thread_id: str):
        os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)
        page = await self.get_page(thread_id)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as e:
            logger.warning("Page network idle timeout", extra={"data": {"error": str(e)}})
        await asyncio.sleep(0.5)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        file_name = f"steps/{thread_id}_{timestamp}.jpg"

        screenshot = await self._safe_screenshot(page, thread_id)
        current_screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
        public_url = b2_storage.upload_file(screenshot, file_name)
        simplified_tree = await page.evaluate("""() => {
            function getBestXPath(el) {
                if (!el || el === document.body) return '//body';
                var skipId = function(id) {
                    return !id || id.indexOf('agent-') === 0 || /^[0-9a-f\\-]{20,}$/.test(id);
                };
                var tag = el.tagName.toLowerCase();
                if (el.id && !skipId(el.id))
                    return '//*[@id="' + el.id + '"]';
                if (el.name)
                    return '//' + tag + '[@name="' + el.name + '"]';
                var aria = el.getAttribute('aria-label');
                if (aria)
                    return '//*[@aria-label="' + aria + '"]';
                var textTags = ['button', 'a', 'label', 'span', 'h1', 'h2', 'h3', 'th'];
                if (textTags.indexOf(tag) !== -1) {
                    var t = el.innerText ? el.innerText.trim() : '';
                    if (t && t.length < 60 && t.indexOf('\\n') === -1)
                        return '//' + tag + '[normalize-space()="' + t + '"]';
                }
                if (el.placeholder)
                    return '//' + tag + '[@placeholder="' + el.placeholder + '"]';
                if (el.type && el.type !== 'text')
                    return '//' + tag + '[@type="' + el.type + '"]';
                var parts = [];
                var node = el;
                while (node && node.nodeType === 1) {
                    var idx = 1;
                    var sib = node.previousElementSibling;
                    while (sib) { if (sib.tagName === node.tagName) idx++; sib = sib.previousElementSibling; }
                    parts.unshift(node.tagName.toLowerCase() + '[' + idx + ']');
                    node = node.parentElement;
                }
                return '/' + parts.join('/');
            }

            const elements = document.querySelectorAll('button, input, a, select, textarea, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="switch"], [role="checkbox"], [role="radio"], [role="combobox"], [role="searchbox"], [role="slider"], [role="spinbutton"], [role="treeitem"], [onclick]');
            let agentIdCounter = 0;

            return Array.from(elements).map(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = rect.width > 0 &&
                                  rect.height > 0 &&
                                  style.visibility !== 'hidden' &&
                                  style.display !== 'none';
                if (!isVisible) return null;

                const agentId = 'agent-id-' + agentIdCounter++;
                el.setAttribute('data-agent-id', agentId);

                const elementInfo = {
                    tagName: el.tagName,
                    selector: '[data-agent-id="' + agentId + '"]',
                    xpath: getBestXPath(el),
                    id: el.id || 'N/A',
                    placeholder: el.placeholder || '',
                    text: el.innerText?.trim() || el.value || '',
                    role: el.getAttribute('role') || 'N/A',
                    type: el.type || 'N/A'
                };

                var ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel) elementInfo.ariaLabel = ariaLabel;

                if (el.title) elementInfo.title = el.title;

                var testId = el.getAttribute('data-testid')
                          || el.getAttribute('data-test-id')
                          || el.getAttribute('data-test')
                          || el.getAttribute('data-cy');
                if (testId) elementInfo.testId = testId;

                if (['INPUT', 'SELECT', 'TEXTAREA'].indexOf(el.tagName) !== -1) {
                    if (el.name) elementInfo.name = el.name;
                    if (el.autocomplete && el.autocomplete !== 'off' && el.autocomplete !== 'on')
                        elementInfo.autocomplete = el.autocomplete;
                }

                if (el.tagName === 'A' && el.href) {
                    try { elementInfo.href = new URL(el.href).pathname; } catch(e) {}
                }


                if (el.disabled || el.getAttribute('aria-disabled') === 'true')
                    elementInfo.disabled = true;

                if (el.getAttribute('aria-expanded') !== null)
                    elementInfo.ariaExpanded = el.getAttribute('aria-expanded') === 'true';

                if (el.checked || el.getAttribute('aria-checked') !== null)
                    elementInfo.checked = el.checked || el.getAttribute('aria-checked') === 'true';

                if (el.getAttribute('aria-selected') !== null)
                    elementInfo.ariaSelected = el.getAttribute('aria-selected') === 'true';

                if (el.getAttribute('aria-pressed') !== null)
                    elementInfo.ariaPressed = el.getAttribute('aria-pressed') === 'true';

                if (el.readOnly || el.getAttribute('aria-readonly') === 'true')
                    elementInfo.readonly = true;

                var hasPopup = el.getAttribute('aria-haspopup');
                if (hasPopup && hasPopup !== 'false')
                    elementInfo.ariaHasPopup = hasPopup;

                
                if (el.required || el.getAttribute('aria-required') === 'true')
                    elementInfo.required = true;

                if (el.multiple) elementInfo.multiple = true;

                
                if (!elementInfo.text) {
                    var img = el.querySelector('img[alt]');
                    if (img) {
                        elementInfo.text = img.alt;
                    } else {
                        var svg = el.querySelector('svg[aria-label]');
                        if (svg) elementInfo.text = svg.getAttribute('aria-label');
                    }
                }

                
                if (el.tagName === 'SELECT') {
                    elementInfo.options = Array.from(el.options).map(opt => ({
                        label: opt.text,
                        value: opt.value
                    }));
                }

                return elementInfo;
            }).filter(el => el !== null);
        }""")
        return screenshot, str(simplified_tree), public_url, current_screenshot_base64

    async def _safe_screenshot(self, page, thread_id: str):
        full_page = await self._can_take_full_page_screenshot(page, thread_id)
        try:
            return await page.screenshot(
                type="jpeg",
                quality=settings.SCREENSHOT_QUALITY,
                full_page=full_page,
            )
        except Exception as e:
            logger.warning("Screenshot failed; retrying viewport screenshot", extra={"data": {
                "thread_id": thread_id,
                "full_page": full_page,
                "error": str(e),
            }})
            if self._is_closed_error(e):
                await self.reset_browser(close_playwright=False)
                raise
            try:
                return await page.screenshot(
                    type="jpeg",
                    quality=settings.SCREENSHOT_QUALITY,
                    full_page=False,
                )
            except Exception as retry_error:
                logger.error("Viewport screenshot retry failed", extra={"data": {
                    "thread_id": thread_id,
                    "error": str(retry_error),
                }})
                if self._is_closed_error(retry_error):
                    await self.reset_browser(close_playwright=False)
                raise

    async def _can_take_full_page_screenshot(self, page, thread_id: str) -> bool:
        try:
            size = await page.evaluate("""() => {
                const doc = document.documentElement;
                const body = document.body || doc;
                const width = Math.max(
                    doc.scrollWidth || 0,
                    body.scrollWidth || 0,
                    window.innerWidth || 0
                );
                const height = Math.max(
                    doc.scrollHeight || 0,
                    body.scrollHeight || 0,
                    window.innerHeight || 0
                );
                return { width, height };
            }""")
        except Exception as e:
            logger.warning("Could not inspect page size; using viewport screenshot", extra={"data": {
                "thread_id": thread_id,
                "error": str(e),
            }})
            return False

        width = int(size.get("width") or 0)
        height = int(size.get("height") or 0)
        pixels = width * height
        if (
            width <= 0
            or height <= 0
            or width > self.max_full_page_screenshot_side
            or height > self.max_full_page_screenshot_side
            or pixels > self.max_full_page_screenshot_pixels
        ):
            logger.warning("Page too large for full-page screenshot; using viewport screenshot", extra={"data": {
                "thread_id": thread_id,
                "width": width,
                "height": height,
                "pixels": pixels,
            }})
            return False
        return True

    def _is_closed_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return (
            "target page, context or browser has been closed" in message
            or "browser has been closed" in message
            or "browser closed" in message
            or "browser disconnected" in message
        )

    def _normalize_selector(self, selector: str) -> str:
        selector = selector.strip() if selector else selector
        if selector and selector.startswith(("/", "//", "..")):
            return f"xpath={selector}"
        return selector

    async def execute_action(self, action: dict, thread_id: str):
        start = time.perf_counter()
        action_type = action["action_type"]
        selector = action.get("selector", "")
        if selector and not selector.startswith("[data-agent-id") and selector != "N/A":
            logger.debug("Using custom selector", extra={"data": {"selector": selector, "selector_type": "xpath" if selector.startswith(("/", "//", "..")) else "css"}})
        normalized_selector = self._normalize_selector(selector)
        try:
            page = await self.get_page(thread_id)
            if action_type == "click":
                await page.click(normalized_selector, timeout=5000)
            elif action_type == "type":
                await page.fill(normalized_selector, action["value"], timeout=5000)
            elif action_type == "scroll":
                if normalized_selector and normalized_selector != "N/A":
                    await page.locator(normalized_selector).scroll_into_view_if_needed()
                else:
                    y = 500 if action.get("direction") == "down" else -500
                    await page.mouse.wheel(0, y)
            elif action_type == "wait":
                await page.wait_for_load_state("load", timeout=5000)
                await asyncio.sleep(0.5)
            elif action_type == "back":
                await page.go_back(wait_until="load", timeout=10000)
            elif action_type == "reload":
                await page.reload(wait_until="load", timeout=10000)
            elif action_type == "select":
                await page.select_option(normalized_selector, action["value"], timeout=5000)
            elif action_type == "navigate":
                await page.goto(action["url"], wait_until="load", timeout=10000)
        except Exception as e:
            duration = round(time.perf_counter() - start, 2)
            logger.error("Action failed", extra={"data": {
                "action_type": action_type,
                "selector": action.get("selector"),
                "duration_s": duration,
                "error": str(e),
            }})
            return f"Error: {str(e)}"
        duration = round(time.perf_counter() - start, 2)
        logger.debug("Action success", extra={"data": {"action_type": action_type, "duration_s": duration}})
        return "Success"

    async def close(self):
        await self.reset_browser(close_playwright=True)

browser_manager = BrowserManager()
