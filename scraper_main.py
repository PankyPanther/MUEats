"""
MUEats Web Scraper
==================
Scrapes dineoncampus.com/MiamiUniversity for today's dining hall menus.

Key fixes:
  - __main__ always uses today's date (no hardcoded date)
  - webdriver-manager auto-downloads correct geckodriver version
  - Retry logic on flaky elements
  - Chrome fallback if Firefox not available
  - Clear error messages for missing drivers
  - Can be run standalone:  python scraper_main.py
  - Or triggered via Flask:  POST /api/scraper/run
"""

from datetime import date as _date
import json, time, sys, os

# ── Driver imports (fail loudly with a helpful message) ──────────────────────
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, WebDriverException
    )
except ImportError:
    print("[!] selenium not installed. Run:  pip install selenium")
    sys.exit(1)


def _make_firefox(headless: bool):
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    try:
        from webdriver_manager.firefox import GeckoDriverManager
        svc = Service(GeckoDriverManager().install())
    except Exception:
        svc = Service()   # use system geckodriver if webdriver-manager fails

    opts = Options()
    if headless:
        opts.add_argument("--headless")
    opts.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    )
    opts.set_preference("permissions.default.image", 2)   # no images → faster
    return webdriver.Firefox(service=svc, options=opts)


def _make_chrome(headless: bool):
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        svc = Service(ChromeDriverManager().install())
    except Exception:
        svc = Service()

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    return webdriver.Chrome(service=svc, options=opts)


class RestaurantScraper:

    BASEURL              = "https://dineoncampus.com/MiamiUniversity/whats-on-the-menu"
    DATEDROPDOWNMENU     = "button[class*='w-full px-4 py-2 text-left cursor-pointer']"
    DATEMONTHSELECTOR    = "button[class*='dp__btn dp__month_year_select']"
    DATEYEARSSELECTOR    = "button[data-dp-element*='overlay-year']"
    LOCATIONDROPDOWNMENU = "button[aria-controls*='location-listbox']"
    LOCATIONOPTIONCSS    = "li[id*='location-option'][role='option']"
    ITEMCONTAINERCSS     = "td[class*='max-w-0 py-5']"
    TITLEBUTTONCSS       = "button[aria-label*='View nutritional information']"
    CLOSEBUTTONCSS       = "button[aria-label*='Close nutrition information modal']"
    PERIODCSS            = "button[aria-controls='period-listbox']"
    MACROELEMENTCSS      = "div[class*='flex justify-between py-1']"
    DESCRIPTIONCSS       = "div[class*='mt-1 pl-2']"

    # ── Init ────────────────────────────────────────────────────────────────
    def __init__(self, target_date: str = None, headless: bool = True,
                 browser: str = "auto"):
        """
        target_date : "YYYY-MM-DD" — defaults to TODAY if not provided
        headless    : run browser in background (True for production)
        browser     : "firefox" | "chrome" | "auto" (tries firefox, falls back to chrome)
        """
        # Always default to today — no hardcoded dates
        self.date = target_date or str(_date.today())
        print(f"[+] Scraper initialised for date: {self.date}")

        self.webDriver = self._init_driver(headless, browser)
        self.webDriver.get(self.BASEURL)
        self.restaurantLocations = self._getLocations()
        self._setDate()

    # ── Driver setup ────────────────────────────────────────────────────────
    def _init_driver(self, headless: bool, browser: str):
        if browser == "firefox":
            return _make_firefox(headless)
        if browser == "chrome":
            return _make_chrome(headless)

        # auto: try Firefox first, fall back to Chrome
        try:
            drv = _make_firefox(headless)
            print("[+] Using Firefox")
            return drv
        except WebDriverException as e:
            print(f"[!] Firefox unavailable ({e}), trying Chrome…")
        try:
            drv = _make_chrome(headless)
            print("[+] Using Chrome")
            return drv
        except WebDriverException as e:
            raise RuntimeError(
                "Neither Firefox nor Chrome is available.\n"
                "Install Firefox:  https://www.mozilla.org/firefox/\n"
                "Or Chrome:        https://www.google.com/chrome/\n"
                f"Original error: {e}"
            )

    # ── Element helpers ──────────────────────────────────────────────────────
    def _wait(self, timeout: int = 20):
        return WebDriverWait(self.webDriver, timeout)

    def _click(self, selector: str, by=By.CSS_SELECTOR, timeout: int = 20,
               retries: int = 3):
        """Click with retry on stale/intercepted elements."""
        last_err = None
        for attempt in range(retries):
            try:
                el = self._wait(timeout).until(EC.element_to_be_clickable((by, selector)))
                self.webDriver.execute_script("arguments[0].scrollIntoView(true);", el)
                self.webDriver.execute_script("arguments[0].click();", el)
                return
            except Exception as e:
                last_err = e
                time.sleep(1)
        raise last_err

    # ── Date navigation ──────────────────────────────────────────────────────
    def _setDate(self):
        parts  = self.date.split("-")
        year, month, day = parts[0], parts[1], parts[2]
        month_map = {
            "01":"Jan","02":"Feb","03":"Mar","04":"Apr",
            "05":"May","06":"Jun","07":"Jul","08":"Aug",
            "09":"Sep","10":"Oct","11":"Nov","12":"Dec"
        }
        try:
            self._click(self.DATEDROPDOWNMENU)
            self._click(self.DATEMONTHSELECTOR)
            self._click(f"[data-test-id='{month_map[month]}']")
            self._click(self.DATEYEARSSELECTOR)
            self._click(f"[data-test-id='{year}']")
            self._click(f"[data-test-id*='{self.date}']")
            time.sleep(2)
            print(f"[+] Date set to {self.date}")
        except Exception as e:
            print(f"[!] Date set failed: {e} — continuing with default date")

    # ── Location / period ────────────────────────────────────────────────────
    def _getLocations(self) -> list[str]:
        self._wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.LOCATIONDROPDOWNMENU)))
        self._click(self.LOCATIONDROPDOWNMENU)
        self._wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, self.LOCATIONOPTIONCSS)))
        els   = self.webDriver.find_elements(By.CSS_SELECTOR, self.LOCATIONOPTIONCSS)
        names = [e.text.strip() for e in els if e.text.strip()]
        self._click(self.LOCATIONDROPDOWNMENU)
        print(f"[+] Found {len(names)} locations: {names}")
        return names

    def _selectLocation(self, name: str):
        self._click(self.LOCATIONDROPDOWNMENU)
        xpath = self._safeXPath(name)
        self._click(xpath, By.XPATH)
        time.sleep(3)

    def _getPeriods(self) -> list[str]:
        self._click(self.PERIODCSS)
        self._wait(10).until(EC.visibility_of_element_located((By.ID, "period-listbox")))
        opts  = self.webDriver.find_elements(By.XPATH, "//ul[@id='period-listbox']/li[@role='option']")
        names = [o.text.strip() for o in opts if o.text.strip()]
        self._click(self.PERIODCSS)
        return names

    def _switchToPeriod(self, name: str):
        self._click(self.PERIODCSS)
        xpath = f"//ul[@id='period-listbox']/li[@role='option' and text()='{name}']"
        self._click(xpath, By.XPATH)
        time.sleep(1.5)

    # ── Nutrition extraction ─────────────────────────────────────────────────
    def _getCalories(self) -> str:
        try:
            return self.webDriver.find_element(
                By.CSS_SELECTOR, "span.text-4xl.font-black").text.strip()
        except Exception:
            return "0"

    def _getAllergens(self) -> str:
        try:
            el = self.webDriver.find_element(By.XPATH, "//p[contains(., 'Allergens:')]")
            return el.text.replace("Allergens:", "").strip() or "None"
        except Exception:
            return "None"

    def _getMacros(self) -> dict:
        macros = {}
        els    = self.webDriver.find_elements(By.CSS_SELECTOR, self.MACROELEMENTCSS)
        for el in els:
            data = el.get_attribute("innerText").split("\n")
            if len(data) == 2:
                macros[data[0].strip()] = data[1].strip()
        return macros

    def _scrapeMacroPanel(self, title_btn) -> dict:
        self.webDriver.execute_script("arguments[0].click();", title_btn)
        self._wait(10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, self.CLOSEBUTTONCSS)))
        info = {
            "calories":  self._getCalories(),
            "allergens": self._getAllergens(),
            "macros":    self._getMacros(),
        }
        self._click(self.CLOSEBUTTONCSS)
        self._wait(10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.CLOSEBUTTONCSS)))
        return info

    def _getRestaurantData(self) -> list[dict]:
        items      = []
        containers = self.webDriver.find_elements(By.CSS_SELECTOR, self.ITEMCONTAINERCSS)
        for container in containers:
            try:
                btn  = container.find_element(By.CSS_SELECTOR, self.TITLEBUTTONCSS)
                try:
                    desc = container.find_element(By.CSS_SELECTOR, self.DESCRIPTIONCSS).text.strip()
                except NoSuchElementException:
                    desc = None
                items.append({
                    "title":       btn.text.strip(),
                    "description": desc or None,
                    "nutrition":   self._scrapeMacroPanel(btn),
                })
            except Exception as e:
                print(f"  [-] Skipped item: {e}")
        return items

    # ── Main scrape ──────────────────────────────────────────────────────────
    def scrapeToJson(self, filename: str = "menu_data.json") -> dict:
        results = {"date": self.date, "restaurants": {}}
        total   = 0

        for restaurant in self.restaurantLocations:
            time.sleep(2)
            try:
                print(f"\n[~] Scraping: {restaurant}")
                self._selectLocation(restaurant)
                results["restaurants"][restaurant] = {}

                periods = self._getPeriods()
                print(f"    Periods: {periods}")

                for period in periods:
                    self._switchToPeriod(period)
                    time.sleep(2)
                    items = self._getRestaurantData()
                    results["restaurants"][restaurant][period] = items
                    total += len(items)
                    print(f"    {period}: {len(items)} items")

            except Exception as e:
                print(f"[-] Failed to scrape {restaurant}: {e}")

        # Save JSON
        with open(filename, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n[+] Done — {total} items across {len(results['restaurants'])} restaurants")
        print(f"[+] Saved to {filename}")
        return results

    def quit(self):
        try:
            self.webDriver.quit()
        except Exception:
            pass

    # ── XPath helper ────────────────────────────────────────────────────────
    @staticmethod
    def _safeXPath(text: str) -> str:
        """Build an XPath that handles apostrophes in restaurant names."""
        if "'" not in text:
            return f"//li[@role='option' and text()='{text}']"
        parts      = text.split("'")
        concat_args = ', "\'", '.join(f'"{p}"' for p in parts)
        return f"//li[@role='option' and . = concat({concat_args})]"


# ── Standalone entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    # Always scrape TODAY — no hardcoded date
    target = sys.argv[1] if len(sys.argv) > 1 else str(_date.today())
    headless = "--headless" in sys.argv or "-h" in sys.argv

    print(f"MUEats Scraper — target date: {target}")
    print(f"Headless: {headless}")
    print("=" * 50)

    scraper = RestaurantScraper(target_date=target, headless=headless)
    try:
        scraper.scrapeToJson(
            os.path.join(os.path.dirname(__file__), "menu_data.json")
        )
    finally:
        scraper.quit()
