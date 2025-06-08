from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service # Keep Service for options if needed, but SeleniumManager will be default
from selenium.webdriver.common.action_chains import ActionChains # Import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, ElementClickInterceptedException
import time
import shutil # For locating the chrome binary
import os # For path joining
import logging # Use Python's logging
import tempfile # For creating unique temporary directories
from werkzeug.utils import secure_filename # For sanitizing screenshot filenames

logger = logging.getLogger("GameController") # Specific logger for this module
logger.setLevel(logging.INFO) # Adjust level as needed

# Directory for screenshots taken directly by GameController (e.g., for CAPTCHAs)
_GC_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UTILITY_SCREENSHOT_DIR = os.path.join(_GC_SCRIPT_DIR, 'gc_screenshots')

class GameController:
    def __init__(self, config=None): # Accept config object
        self.config = config # Store config if needed for future use
        self.driver = None
        self.wait = None 
        self.short_wait = None
        self.is_in_iframe = False # Track iframe state
        self.current_user_data_dir = None # Path to the user data dir for this session if created

        # Ensure the utility screenshot directory exists
        if not os.path.exists(UTILITY_SCREENSHOT_DIR):
            try:
                os.makedirs(UTILITY_SCREENSHOT_DIR)
                logger.info(f"Created utility screenshot directory: {UTILITY_SCREENSHOT_DIR}")
            except OSError as e:
                logger.error(f"Could not create utility screenshot directory {UTILITY_SCREENSHOT_DIR}: {e}")



    def start_browser(self, browser_type='chrome', explicit_chromedriver_path=None):
        logger.info(f"Attempting to start browser: {browser_type}. Explicit ChromeDriver path provided: '{explicit_chromedriver_path}'")
        self.current_user_data_dir = None # Reset for each start attempt

        try:
            options = webdriver.ChromeOptions()
            
            # Core headless and stability options
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu") # Often necessary for headless
            options.add_argument("--window-size=1366,768") # Define viewport

            # Options to reduce interference
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-features=LockProfileCookieDatabase") # May help with profile lock issues
            
            # Stealth options
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36") # Example of a more recent UA
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            # Preferences to disable password saving popups and translation prompts
            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2 # Disable notifications
            }
            options.add_experimental_option("prefs", prefs)

            # --- Attempting a highly unique user-data-dir in a standard temp location ---
            user_data_dir_to_set = None
            try:
                # tempfile.mkdtemp() creates a directory with a unique name.
                user_data_dir_to_set = tempfile.mkdtemp(prefix="chrome_bot_session_")
                self.current_user_data_dir = user_data_dir_to_set # Store for cleanup
                
                logger.info(f"Attempting to use unique user data directory: {user_data_dir_to_set}")
                options.add_argument(f"--user-data-dir={user_data_dir_to_set}")
            except Exception as e_tmpdir:
                logger.error(f"Failed to create unique user data directory using tempfile.mkdtemp(): {e_tmpdir}. Falling back to Selenium-managed temp profile.", exc_info=True)
                self.current_user_data_dir = None # Ensure it's None for cleanup logic
                logger.info("Fallback: Not specifying --user-data-dir. ChromeDriver will use a temporary profile.")
            
            chrome_binary_path = shutil.which("google-chrome")
            if chrome_binary_path:
                options.binary_location = chrome_binary_path
                logger.info(f"Explicitly set Chrome binary location to: {chrome_binary_path}")
            else:
                logger.warning("google-chrome binary not found in PATH. Selenium Manager might struggle if it cannot auto-detect. Ensure Chrome is installed and in PATH.")

            service_instance = None
            if explicit_chromedriver_path and explicit_chromedriver_path.strip():
                logger.info(f"Attempting to initialize ChromeDriver using explicit path: {explicit_chromedriver_path}")
                if not shutil.os.path.exists(explicit_chromedriver_path):
                    logger.error(f"Specified chromedriver_path does not exist: {explicit_chromedriver_path}. Will attempt Selenium Manager.")
                elif not shutil.os.access(explicit_chromedriver_path, shutil.os.X_OK):
                    logger.error(f"Specified chromedriver at {explicit_chromedriver_path} is not executable. Will attempt Selenium Manager.")
                else:
                    try:
                        service_instance = Service(executable_path=explicit_chromedriver_path)
                        logger.info(f"Service object created with explicit ChromeDriver path: {explicit_chromedriver_path}")
                    except Exception as e_service:
                        logger.error(f"Failed to create Service with explicit path {explicit_chromedriver_path}: {e_service}. Will attempt Selenium Manager.")
                        service_instance = None # Ensure it's None so Selenium Manager is tried
            
            if service_instance:
                self.driver = webdriver.Chrome(service=service_instance, options=options)
                logger.info("WebDriver initialized using explicitly provided ChromeDriver path.")
            else:
                logger.info("No valid explicit ChromeDriver path provided or it failed. Attempting to use Selenium Manager (default behavior).")
                # Selenium Manager will try to download/manage chromedriver automatically
                # if no service with executable_path is provided.
                self.driver = webdriver.Chrome(options=options)
                logger.info("WebDriver initialized, relying on Selenium Manager.")

            if not self.driver: # Should not happen if Chrome() constructor doesn't raise exception
                logger.critical("CRITICAL: self.driver is None after attempting initialization. This should not happen.")
                raise WebDriverException("Failed to initialize WebDriver instance.")

            logger.info("Executing script to undefine navigator.webdriver...")
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            self.wait = WebDriverWait(self.driver, 25) # Increased default wait
            self.short_wait = WebDriverWait(self.driver, 10) # Increased short wait
            logger.info("Browser started successfully and configured.")
            self.is_in_iframe = False # Reset iframe state
        except WebDriverException as e: # More specific
            logger.error(f"WebDriverException starting browser: {e}. Check Chrome/ChromeDriver compatibility.", exc_info=True)
            self.driver = None
            raise 
        except Exception as e:
            logger.error(f"Generic error starting browser: {e}", exc_info=True)
            self.driver = None 
            raise 

    def _find_element_by_xpaths(self, xpaths, clickable=False, wait_instance=None, context=None):
        search_context = context if context else self.driver
        effective_wait = wait_instance if wait_instance else (self.short_wait if clickable else self.wait)
        
        last_exception = None
        for xpath_idx, xpath in enumerate(xpaths):
            logger.debug(f"Attempting to find element with XPath ({xpath_idx+1}/{len(xpaths)}): {xpath} (Clickable: {clickable})")
            try:
                if clickable:
                    element = effective_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                else:
                    element = effective_wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
                logger.info(f"Element found and ready with XPath: {xpath}")
                return element
            except TimeoutException:
                logger.warning(f"Timeout finding element with XPath: {xpath}")
                last_exception = TimeoutException(f"Timeout on XPath: {xpath}")
            except Exception as e_find:
                 logger.error(f"Error finding element with XPath {xpath}: {e_find}", exc_info=False) # No need for full stack here often
                 last_exception = e_find
        if last_exception:
            logger.error(f"Element not found after trying all XPaths. Last error type: {type(last_exception).__name__}")
        return None

    def _click_element_robustly(self, element, description="element"):
        if not element:
            logger.error(f"Cannot click robustly: {description} is None.")
            return False
        try:
            # Attempt to scroll the element into view first
            try:
                logger.debug(f"Scrolling {description} into view before click attempt.")
                # Try to scroll to center, might be more reliable
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                time.sleep(0.3) # Slightly longer pause after scroll
            except Exception as e_scroll:
                logger.warning(f"Could not scroll {description} into view: {e_scroll}", exc_info=False)
            
            # Re-check interactability just before Selenium click
            if not element.is_displayed() or not element.is_enabled():
                logger.warning(f"{description} became non-interactable (Displayed: {element.is_displayed()}, Enabled: {element.is_enabled()}) just before Selenium click attempt.")
                # Fall through to other methods, or could return False here if strict

            logger.info(f"Attempting to click {description} via Selenium click().")
            element.click()
            return True
        except ElementClickInterceptedException:
            logger.warning(f"Selenium click() on {description} was intercepted. Trying JavaScript click.")
            try:
                # Re-check interactability just before JavaScript click
                if not element.is_displayed(): 
                    logger.warning(f"{description} is not displayed (is_displayed: {element.is_displayed()}) just before JavaScript click attempt.")

                self.driver.execute_script("arguments[0].click();", element)
                logger.info(f"JavaScript click() on {description} successful.")
                return True
            except Exception as e_jsclick:
                logger.error(f"JavaScript click() on {description} also failed: {e_jsclick}", exc_info=True)
                self.take_utility_screenshot(f"{secure_filename(description)}_js_click_exception")
                logger.info(f"Trying ActionChains click for {description} after JS click failure.")
                try:
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    logger.info(f"ActionChains click() on {description} successful.")
                    return True
                except Exception as e_action_chains:
                    logger.error(f"ActionChains click() on {description} also failed: {e_action_chains}", exc_info=True)
                    self.take_utility_screenshot(f"{secure_filename(description)}_actionchains_click_exception")
                    return False
        except Exception as e_click: # General click error (not intercepted)
            logger.error(f"General error clicking {description} with Selenium click(): {e_click}", exc_info=True)
            self.take_utility_screenshot(f"{secure_filename(description)}_selenium_click_exception")
            # For now, if standard click fails this broadly, we assume a deeper issue.
                return False

    def take_utility_screenshot(self, filename_prefix="gc_ss"):
        if not self.driver:
            logger.warning("take_utility_screenshot called but driver is not available.")
            return None
        
        # Ensure directory exists (it should from __init__, but check again)
        if not os.path.exists(UTILITY_SCREENSHOT_DIR):
            try:
                os.makedirs(UTILITY_SCREENSHOT_DIR)
                logger.info(f"Utility screenshot directory re-checked/created at: {UTILITY_SCREENSHOT_DIR}")
            except OSError as e:
                logger.error(f"Failed to create utility screenshot directory {UTILITY_SCREENSHOT_DIR} during take: {e}")
                return None

        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            safe_prefix = secure_filename(filename_prefix)
            filename = f"{safe_prefix}_{timestamp}.png"
            filepath = os.path.join(UTILITY_SCREENSHOT_DIR, filename)
            
            self.driver.save_screenshot(filepath)
            logger.info(f"Utility screenshot saved by GameController to: {filepath}")
            return filepath
        except WebDriverException as e_wd:
            logger.error(f"Utility screenshot WebDriverException: {type(e_wd).__name__} - {e_wd}", exc_info=True)
        except Exception as e: # Catch other potential errors (e.g., OS errors during file ops)
            logger.error(f"Utility screenshot generic error: {type(e).__name__} - {e}", exc_info=True)
        return None

    def _check_for_recaptcha(self, action_description="page load"):
        """
        Checks for the presence of a Google reCAPTCHA iframe or other common CAPTCHA challenges.
        NOTE: This method *only* detects CAPTCHA. It does NOT attempt to solve it.
        Automated CAPTCHA solving is generally not feasible or reliable with simple automation
        and is against terms of service for many providers. If CAPTCHA is detected,
        the bot should ideally log a critical error and stop or await manual intervention.
        """
        if not self.driver:
            logger.warning("_check_for_recaptcha called but driver is not available.")
            return False
        try:
            # Ensure we are searching from the main document first
            self._ensure_main_document_context()
            
            # Use a very short wait, as CAPTCHAs usually appear quickly if they are to block interaction
            quick_wait = WebDriverWait(self.driver, 3)

            # Check for reCAPTCHA iframes
            captcha_iframes_xpaths = [
                "//iframe[contains(@src, 'recaptcha') and not(contains(@src,'invisible'))]",  # Standard visible reCAPTCHA
                "//iframe[@title='reCAPTCHA' or @title='recaptcha' or @title='reCAPTCHA-uitdaging']"  # Variations by title
            ]
            for xpath in captcha_iframes_xpaths:
                try:
                    iframe_elements = quick_wait.until(EC.presence_of_all_elements_located((By.XPATH, xpath)))
                    if iframe_elements:
                        logger.critical(f"CRITICAL: CAPTCHA iframe (e.g., Google reCAPTCHA) detected after {action_description} using XPath: {xpath}. Bot cannot proceed automatically.")
                        self.take_utility_screenshot(f"captcha_iframe_detected_{action_description.replace(' ', '_')}")
                        return True  # CAPTCHA iframe detected
                except TimeoutException:
                    continue  # This XPath didn't find it, try next

            # Check for common text-based "I am not a bot" challenges or other CAPTCHA providers (outside of iframes)
            text_based_challenge_xpaths = [
                "//*[self::h1 or self::h2 or self::p or self::div][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'verify you are human')]",
                "//*[self::h1 or self::h2 or self::p or self::div][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bevestig dat je geen bot bent')]", # Dutch
                "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), \"i'm not a robot\") or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), \"ik ben geen robot\")]",
                "//div[contains(@class, 'h-captcha') or @data-sitekey[contains(.,'hcaptcha')] or //iframe[contains(@src, 'hcaptcha')]]", # hCaptcha
                "//div[contains(@class, 'cf-turnstile') or @data-sitekey[contains(.,'turnstile')] or //iframe[contains(@src, 'challenges.cloudflare.com/turnstile')]]", # Cloudflare Turnstile
                "//div[contains(text(), 'Please verify you are a human') or contains(text(), 'Bevestig dat u een mens bent')]"
            ]
            for xpath in text_based_challenge_xpaths:
                try:
                    challenge_elements = quick_wait.until(EC.presence_of_all_elements_located((By.XPATH, xpath)))
                    if any(el.is_displayed() for el in challenge_elements): # Check if any found elements are visible
                        logger.critical(f"CRITICAL: Potential text-based/other CAPTCHA challenge detected after {action_description} using XPath: {xpath}. Bot cannot proceed automatically.")
                        self.take_utility_screenshot(f"text_challenge_detected_{action_description.replace(' ', '_')}")
                        return True  # Challenge detected
                except TimeoutException:
                    continue
        except Exception as e:
            logger.error(f"Error during CAPTCHA check: {e}", exc_info=False)
        return False # No definitive CAPTCHA detected

    def _handle_potential_overlays_or_modals(self, action_description="before interaction"):
        """Attempts to find and click common close/accept buttons for overlays or modals."""
        if not self.driver: return
        logger.info(f"Checking for potential overlays/modals {action_description}...")
        self._ensure_main_document_context() # Ensure we are in the main document

        overlay_closer_xpaths = [
            "//button[contains(@aria-label, 'Close') or contains(@aria-label, 'Sluiten') or contains(translate(., 'XYZ', 'xyz'),'close')]", # Common aria-labels
            "//button[contains(@class, 'close') or contains(@class, 'modal-close') or contains(@class, 'popup-close')]", # Common classes
            "//button[normalize-space(.)='×' or normalize-space(.)='X']", # Common text for close
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cookie'))]", # Generic accept, not cookie
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ok')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'begrepen')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'doorgaan')]",
            "//a[contains(@role,'button') and (contains(@aria-label, 'Close') or contains(@aria-label, 'Sluiten'))]" # Links styled as close buttons
        ]
        # Use a very short wait as these should be immediately interactable if present
        quick_overlay_wait = WebDriverWait(self.driver, 2) 
        found_and_clicked_overlay = False
        for xpath_idx, xpath in enumerate(overlay_closer_xpaths):
            try:
                # Find all, then try to click the first visible one
                elements = quick_overlay_wait.until(EC.presence_of_all_elements_located((By.XPATH, xpath)))
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        logger.info(f"Potential overlay/modal found with XPath ({xpath_idx+1}): {xpath}. Attempting to click it.")
                        self._click_element_robustly(element, f"overlay/modal close button ({xpath_idx+1})")
                        time.sleep(0.7) # Brief pause after clicking an overlay
                        found_and_clicked_overlay = True
                        break # Assume one click is enough for this pass
                if found_and_clicked_overlay: break
            except TimeoutException:
                continue # This XPath didn't find anything quickly
            except Exception as e_overlay:
                logger.warning(f"Exception while trying to handle overlay with XPath {xpath}: {e_overlay}", exc_info=False)
        if not found_and_clicked_overlay:
            logger.info(f"No common overlays/modals found or clicked {action_description}.")

    def login(self, login_url, username, password):
        if not self.driver:
            logger.error("Login attempt failed: Browser not started.")
            return False
        try:
            logger.info(f"Navigating to login page: {login_url}")
            self.driver.get(login_url)
            self._ensure_main_document_context() # Ensure we are in main document
            time.sleep(1) 
            
            logger.info("--- Starting Login Sequence ---")
            
            cookie_accept_xpaths = [
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepteer alle cookies')]",
                "//button[@id='onetrust-accept-btn-handler']",
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepteren')]"
            ]
            logger.info("Attempting to handle cookie banner...")
            cookie_button = self._find_element_by_xpaths(cookie_accept_xpaths, clickable=True, wait_instance=self.short_wait)
            if cookie_button:
                if self._click_element_robustly(cookie_button, "cookie accept button"):
                    logger.info("Cookie accept button clicked successfully.")
                    time.sleep(2.0) # Slightly increased pause after cookie interaction
                else:
                    logger.warning("Attempted to click cookie accept button, but click action returned false.")
            else:
                logger.info("Cookie accept button not found or not clickable within timeout. Proceeding...")
            
            # Attempt to handle any other initial overlays AFTER cookie banner
            self._handle_potential_overlays_or_modals(action_description="after cookie handling")

            # Check for CAPTCHA after page load and cookie handling
            if self._check_for_recaptcha(action_description="login page initial load"):
                logger.critical("CAPTCHA detected on login page before form interaction. Cannot proceed with login.")
                # Screenshot is already taken by _check_for_recaptcha
                input("DEBUG: CAPTCHA detected after cookie/overlay handling. Check page. Press Enter to exit...") # DEBUG
                return False


            logger.info("Locating username field...")
            username_field_xpaths = [
                "//input[@name='username']", "//input[@id='username']", "//input[@data-testid='username-input']",
                "//input[contains(@placeholder, 'Gebruikersnaam') or contains(@placeholder, 'Username')]"
            ]
            username_element = self._find_element_by_xpaths(username_field_xpaths, wait_instance=self.wait)
            if not username_element:
                logger.critical("CRITICAL: Username field not found on login page. Check XPaths/page state.")
                self.take_utility_screenshot("username_field_not_found")
                input("DEBUG: Username field NOT found. Check page. Press Enter to exit...") # DEBUG
                return False
            logger.info(f"Username field found. Displayed: {username_element.is_displayed()}, Enabled: {username_element.is_enabled()}")
            try:
                username_element.clear()
                username_element.send_keys(username)
            except Exception as e_user:
                logger.error(f"Error interacting with username field (clear/send_keys): {e_user}", exc_info=True)
                self.take_utility_screenshot("username_field_interaction_error")
                input("DEBUG: Error with username field. Check logs/screenshots. Press Enter to exit...") # DEBUG
                return False
            logger.info(f"Username '{username[:3]}***' entered.")
            time.sleep(0.3)

            logger.info("Locating password field...")
            password_field_xpaths = [
                "//input[@name='password']", "//input[@id='password']", "//input[@type='password']",
                "//input[contains(@placeholder, 'Wachtwoord') or contains(@placeholder, 'Password')]"
            ]
            password_element = self._find_element_by_xpaths(password_field_xpaths, wait_instance=self.wait)
            if not password_element:
                logger.critical("CRITICAL: Password field not found on login page. Check XPaths.")
                self.take_utility_screenshot("password_field_not_found")
                input("DEBUG: Password field NOT found. Check page. Press Enter to exit...") # DEBUG
                return False
            logger.info(f"Password field found. Displayed: {password_element.is_displayed()}, Enabled: {password_element.is_enabled()}")
            try:
                password_element.clear()
                password_element.send_keys(password)
            except Exception as e_pass:
                logger.error(f"Error interacting with password field (clear/send_keys): {e_pass}", exc_info=True)
                self.take_utility_screenshot("password_field_interaction_error")
                input("DEBUG: Error with password field. Check logs/screenshots. Press Enter to exit...") # DEBUG
                return False
            logger.info("Password entered.")
            time.sleep(0.3)
            input("DEBUG: Password entered. Check page. Is it correct? Press Enter to proceed to overlay/CAPTCHA check...") # DEBUG

            # Attempt to handle any overlays that might have appeared after filling fields
            self._handle_potential_overlays_or_modals(action_description="after filling login fields")

            logger.info("Brief pause before attempting to click login button.")
            time.sleep(0.5) # Small explicit pause for page to settle

            # Check for CAPTCHA again, right before clicking login
            if self._check_for_recaptcha(action_description="before login button click"):
                logger.critical("CAPTCHA detected just before attempting to click login button. Cannot proceed.")
                # Screenshot is already taken by _check_for_recaptcha
                input("DEBUG: CAPTCHA detected before login button click. Check page. Press Enter to exit...") # DEBUG
                return False


            login_button_xpaths = [
                "//button[normalize-space(.)='Inloggen']", # Exact text match for button
                "//button[.//span[normalize-space(.)='Inloggen']]", # Text within a child span of a button
                "//button[@type='submit' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inloggen') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login'))]",
                "//button[@data-testid='login-button']",
                "//input[@type='submit' and (contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inloggen') or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login'))]", # Input type submit by value
                "//input[@type='button' and (contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inloggen') or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login'))]", # Input type button by value
                "//a[contains(@role,'button') and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inloggen') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login'))]" # Anchor tags styled as buttons
            ]
            logger.info("Locating and clicking login button...")
            login_button_element = self._find_element_by_xpaths(login_button_xpaths, clickable=True, wait_instance=self.wait)
            
            if not login_button_element:
                logger.critical("CRITICAL: Login button not found/clickable on login page. Check XPaths.")
                self.take_utility_screenshot("login_button_not_found")
                input("DEBUG: Login button NOT found. Check page. Press Enter to exit...") # DEBUG
                return False
            
            time.sleep(0.1) # Tiny pause before checking display/enabled status
            is_disp = login_button_element.is_displayed()
            is_enb = login_button_element.is_enabled()
            logger.info(f"Login button found. Displayed: {is_disp}, Enabled: {is_enb}")
            if not is_disp or not is_enb: # Log a warning if it's found but not interactable
                logger.warning(f"Login button found but may not be interactable (Displayed: {is_disp}, Enabled: {is_enb}). Proceeding with click attempt.")
            logger.debug(f"Login button outerHTML: {login_button_element.get_attribute('outerHTML')[:350]}") # Log more HTML
            input(f"DEBUG: Login button FOUND. Displayed: {is_disp}, Enabled: {is_enb}. Check its HTML in logs. Check page. Press Enter to attempt click...") # DEBUG

            if not self._click_element_robustly(login_button_element, "login button"):
                logger.critical("CRITICAL: Failed to click login button even robustly.")
                self.take_utility_screenshot("login_button_click_failed")
                input("DEBUG: Robust click on login button FAILED. Check page and gc_screenshots. Press Enter to exit...") # DEBUG
                return False
            logger.info("Login button clicked.")
            input("DEBUG: Login button click attempted. Check page for result. Press Enter for post-login checks...") # DEBUG

            logger.info("Waiting for post-login verification (up to 20 seconds)...")
            post_login_indicator_xpaths = [
                "//a[contains(@href, 'logout') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'uitloggen')]",
                "//div[contains(@class, 'user-balance') or @data-testid='user-balance']"
            ]
            login_error_indicator_xpaths = [
                "//div[contains(@class, 'error-message') or contains(@class, 'login-error')]",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'incorrect')]",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'mislukt')]",
                "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'failed')]",
                "//div[contains(text(), 'Ongeldige') or contains(text(), 'Invalid')]" # "Ongeldige gebruikersnaam of wachtwoord"
            ]
            
            # Wait a moment for page transition or error messages
            time.sleep(3) 
            error_element = self._find_element_by_xpaths(login_error_indicator_xpaths, wait_instance=self.short_wait)
            if error_element:
                logger.error(f"Login failed: Error message detected on page after login attempt. Text: '{error_element.text[:100]}'")
                self.take_utility_screenshot("login_error_message_detected")
                return False

            if self._find_element_by_xpaths(post_login_indicator_xpaths, wait_instance=WebDriverWait(self.driver, 15)): # Wait up to 15s more
                logger.info("LOGIN SUCCESSFUL: Post-login element detected.")
                return True
            else:
                current_url = self.driver.current_url.lower()
                logger.warning(f"Login status uncertain: No clear success/error indicator. Current URL: {current_url}")
                if "login" in current_url or "auth" in current_url: # Still on a login-like page
                    logger.error("Still on login page or auth page, assuming login failed.")
                    self.take_utility_screenshot("login_still_on_login_page")
                    return False
                logger.warning("Not on login page and no error found, cautiously assuming login was successful. VERIFY MANUALLY.")
                return True
        except Exception as e:
            logger.error(f"Exception during login process: {e}", exc_info=True)
            self.take_utility_screenshot("login_exception_occurred")
            input(f"DEBUG: Exception during login: {e}. Check logs/screenshots. Press Enter to exit...") # DEBUG
            return False
        # finally: # 'finally' might be too early if login is successful and leads to game page
        #     logger.info("--- Exiting Login Sequence ---")

    def _switch_to_game_iframe_if_present(self):
        if not self.driver: logger.error("Cannot switch to iframe, driver is None."); return False
        self._ensure_main_document_context() # Always start search from main document
        iframe_xpaths = [
            "//iframe[contains(@title, 'Dragon Tiger') or contains(@title, 'Live Casino') or contains(@data-game-name, 'Dragon Tiger')]",
            "//iframe[contains(@id, 'game-iframe') or contains(@class, 'game-iframe') or contains(@src,'evolutiongaming') or contains(@src,'evo-games.com')]", # Common for Evolution games
            "//iframe[@data-product='casino']" # Generic casino iframe
        ]
        logger.info("Attempting to find and switch to game iframe...")
        game_iframe_element = self._find_element_by_xpaths(iframe_xpaths, wait_instance=WebDriverWait(self.driver, 15)) # Give more time for iframe to load
        if game_iframe_element:
            logger.info("Game iframe detected. Switching context...")
            try:
                self.driver.switch_to.frame(game_iframe_element)
                self.is_in_iframe = True
                logger.info("Successfully switched to game iframe.")
                return True
            except Exception as e_iframe:
                logger.error(f"Error switching to game iframe: {e_iframe}", exc_info=True)
                self.is_in_iframe = False # Ensure state is correct
                return False
        else:
            logger.info("No game iframe found after checking common XPaths. Will operate in main document context.")
            self.is_in_iframe = False
        
        return False # Indicates iframe not found or switch failed

    def _ensure_main_document_context(self):
        if self.is_in_iframe:
            try:
                self.driver.switch_to.default_content()
                self.is_in_iframe = False
                logger.info("Switched back to main document context.")
            except Exception as e_switch_back:
                logger.error(f"Error switching back to main document: {e_switch_back}", exc_info=True)
                # This is problematic, subsequent non-iframe operations might fail.

    def load_game(self, url):
        if not self.driver:
            logger.error("load_game failed: Browser not started.")
            raise Exception("Browser not initialized in GameController for load_game.")
        try:
            logger.info(f"Navigating to game URL: {url}")
            self.driver.get(url)
            self._ensure_main_document_context() # Ensure we are in main document
            time.sleep(2) # Allow page to start loading
            logger.info(f"Page {url} loaded. Current URL: {self.driver.current_url}")

            if not self._switch_to_game_iframe_if_present(): # Attempt to switch if iframe exists
                logger.info("Continuing without switching to an iframe as none was detected or switch failed. Game elements will be searched in main document.")
            
            # Now, wait for a game-ready indicator, searching in current context (main or iframe)
            game_ready_indicator_xpaths = [
                "//div[contains(@class,'dragon-tiger-table')]", 
                "//div[@data-game-name='Dragon Tiger']",
                "//div[contains(@class, 'betting-spots-container') and .//div[contains(@class,'bet-spot')]]", # Check for bet spots
                "//div[contains(@class, 'lobby-tables__item--name') and contains(text(), 'Dragon Tiger')]" # // If it lands on a lobby first
            ]
            logger.info(f"Waiting for game interface to be ready (up to 30s in current context: {'iframe' if self.is_in_iframe else 'main doc'})...")
            
            # Use self.driver as context, which is correct whether in iframe or not after switch attempt
            game_interface_element = self._find_element_by_xpaths(game_ready_indicator_xpaths, wait_instance=WebDriverWait(self.driver, 30))

            if not game_interface_element:
                logger.critical("CRITICAL: Game interface did not load or unique indicator not found. Check XPaths and page structure (including iframes).")
                raise TimeoutException("Game interface not detected after extensive search.")
            
            logger.info("GAME LOADED: Dragon Tiger game interface appears to be loaded and ready.")
        except Exception as e:
            logger.error(f"Error loading game at {url}: {e}", exc_info=True)
            raise

    def get_player_balance(self):
        if not self.driver:
            logger.error("get_player_balance: Driver not available.")
            return None
        
        # IMPORTANT: Balance might be outside the game iframe, or inside.
        # Try outside first, then inside if not found.
        balance_value = None
        
        # Ensure main context first for typical balance locations
        self._ensure_main_document_context()
        balance_xpaths = [
            "//span[@data-testid='user-balance']//span[contains(@class,'amount') or contains(@class,'value')]", # Common Unibet pattern
            "//div[contains(@class,'balance-wrapper')]//span[contains(@class,'money') or contains(@class,'amount')]",
            "//span[contains(@class,'balance__value')]"
        ]
        logger.info(f"Attempting to find balance in current context ({'iframe' if self.is_in_iframe else 'main doc'})...")
        balance_element = self._find_element_by_xpaths(balance_xpaths, wait_instance=self.short_wait)
        if balance_element:
            try:
                balance_text = balance_element.text.replace('€', '').replace(',', '.').strip()
                balance_value = float(balance_text)
                logger.info(f"BALANCE FOUND: €{balance_value:.2f} (in {'iframe' if self.is_in_iframe else 'main doc'})")
                return balance_value
            except ValueError:
                logger.error(f"Could not parse balance text: '{balance_element.text}'")
            except Exception as e_bal:
                logger.error(f"Error extracting balance text: {e_bal}")

        # If not found and we are in iframe, try switching to main and searching
        if not balance_value: # If still not found, and we *were* in an iframe, this check is redundant.
                              # If we were NOT in an iframe, and it wasn't found, then it's just not found.
            logger.info("Balance not found in main document. If game has its own balance display, it might be in an iframe.")
            balance_element_main = self._find_element_by_xpaths(balance_xpaths, wait_instance=self.short_wait)
            if balance_element_main:
                try:
                    balance_text = balance_element_main.text.replace('€', '').replace(',', '.').strip()
                    balance_value = float(balance_text)
                    logger.info(f"Balance found in main document context: €{balance_value:.2f}")
                    # Switch back to iframe if we were there before, for subsequent game actions
                    # self._switch_to_game_iframe_if_present() # Re-enter iframe if needed for game actions
                    return balance_value
                except ValueError:
                    logger.error(f"Could not parse balance text from main doc: '{balance_element_main.text}'")
                except Exception as e_bal_main:
                    logger.error(f"Error extracting balance text from main doc: {e_bal_main}")
        
        logger.warning("Player balance element not found on page. Cannot determine balance.")
        # If we switched out of iframe and didn't find balance, try to switch back for game actions
        # if not self.is_in_iframe: # Check if we are in main doc after trying
        #      self._switch_to_game_iframe_if_present() # Attempt to switch back if an iframe was expected for subsequent game actions
        return None

    def get_game_state(self):
        if not self.driver: 
            logger.error("get_game_state: Driver not available.")
            return None
        try:
            # ### CRITICAL: UNIBET.NL DRAGON TIGER - PARSE GAME HISTORY (ROADMAPS) ###
            # Ensure we are in the game iframe if one exists
            if not self.is_in_iframe and not self._switch_to_game_iframe_if_present():
                logger.warning("get_game_state: Could not ensure iframe context. Game state results might be inaccurate.")
            
            # The _switch_to_game_iframe_if_present() in load_game should handle this.
            logger.info("Attempting to get game state (e.g., history)...")
            # Example XPaths (HIGHLY LIKELY TO NEED ADJUSTMENT FOR UNIBET):
            # history_item_xpaths = [
            #    "//div[contains(@class,'results-history__item')]", 
            #    "//div[contains(@class,'roadmap__cell--') and .//*[self::div or self::svg]]" 
            # ]
            # elements = self.driver.find_elements(By.XPATH, history_item_xpaths[1]) # Example
            # parsed_history = []
            # if elements:
            #     logger.info(f"Found {len(elements)} potential history elements.")
            #     for el_idx, el in enumerate(elements[-20:]): # Last 20 results
            #         try:
            #             # More specific checks for Dragon/Tiger/Tie based on Unibet's classes/SVG content
            #             if el.find_element(By.XPATH, ".//*[contains(@class,'dragon') or contains(@data-value,'dragon')]"): # Relative XPath
            #                 parsed_history.append("dragon")
            #             elif el.find_element(By.XPATH, ".//*[contains(@class,'tiger') or contains(@data-value,'tiger')]"):
            #                 parsed_history.append("tiger")
            #             elif el.find_element(By.XPATH, ".//*[contains(@class,'tie') or contains(@data-value,'tie')]"):
            #                 parsed_history.append("tie")
            #             else: logger.debug(f"History element {el_idx} did not match D/T/T pattern.")
            #         except NoSuchElementException:
            #             logger.debug(f"No D/T/T symbol found in history element {el_idx}.")
            #             continue 
            # else:
            #    logger.warning("Game history elements not found using example XPaths.")

            # if not parsed_history:
            #    logger.warning("Could not parse game history. Returning minimal mock data.")
            #    return {"history": ["dragon"]} 

            # logger.info(f"Parsed game history: {parsed_history}")
            # return {"history": parsed_history}

            logger.warning("PLACEHOLDER: get_game_state() needs specific implementation for the target site.")
            import random
            mock_history = [random.choice(["dragon", "tiger", "tie"]) for _ in range(random.randint(5,15))]
            logger.info(f"Returning MOCK game state: {mock_history}")
            return {"history": mock_history}

        except Exception as e:
            logger.error(f"Error getting game state from Unibet: {e}", exc_info=True)
            return None

    def place_bet(self, bet_type, amount):
        if not self.driver: 
            logger.error("place_bet: Driver not available.")
            return False
        try:
            # Ensure we are in the game iframe if one exists
            if not self.is_in_iframe and not self._switch_to_game_iframe_if_present():
                logger.warning("place_bet: Could not ensure iframe context. Bet placement might fail or target wrong elements.")
            
            # Ensure correct iframe context.
            logger.info(f"Attempting to place bet on {bet_type} for amount {amount}...")

            # Step 1: Select Chip (HIGHLY UNIBET SPECIFIC)
            # Example:
            # target_chip_xpath = f"//button[contains(@class,'chip') and (normalize-space(@data-value)='{str(float(amount))}' or normalize-space(.)='{str(int(float(amount)))}')] | //div[contains(@class,'chip') and @data-value='{str(float(amount))}']"
            # logger.info(f"Looking for chip with XPath: {target_chip_xpath}")
            # chip_element = self._find_element_by_xpaths([target_chip_xpath], clickable=True, wait_instance=self.short_wait)
            # if not chip_element:
            #     logger.error(f"CRITICAL: Chip for amount {amount} not found or not clickable on Unibet. Check chip XPaths/mapping.")
            #     return False # This should be a critical failure
            # if not self._click_element_robustly(chip_element, f"chip for amount {amount}"): return False
            # logger.info(f"Chip for amount {amount} selected (or attempted).")
            # time.sleep(0.4) # Small delay after chip selection

            # Step 2: Click Bet Area (Dragon or Tiger)
            bet_area_xpath_map = {
                "dragon": ["//div[contains(@class,'bet-spot-dragon') or @data-bet-type='DRAGON' or @data-qa-id='dragon-bet-spot' or @data-tracking-label='Dragon']"],
                "tiger": ["//div[contains(@class,'bet-spot-tiger') or @data-bet-type='TIGER' or @data-qa-id='tiger-bet-spot' or @data-tracking-label='Tiger']"],
                "tie": ["//div[contains(@class,'bet-spot-tie') or @data-bet-type='TIE' or @data-qa-id='tie-bet-spot' or @data-tracking-label='Tie']"] # If betting on Tie
            }
            selected_bet_area_xpaths = bet_area_xpath_map.get(bet_type.lower())
            if not selected_bet_area_xpaths:
                logger.error(f"Unsupported bet_type: {bet_type}")
                return False
            
            logger.info(f"Attempting to click bet area for {bet_type} using XPaths: {selected_bet_area_xpaths}")
            bet_spot_element = self._find_element_by_xpaths(selected_bet_area_xpaths, clickable=True, wait_instance=self.short_wait)
            if not bet_spot_element:
                logger.error(f"CRITICAL: Bet spot for {bet_type} not found or not clickable. Check XPaths.")
                return False
            if not self._click_element_robustly(bet_spot_element, f"bet spot for {bet_type}"):
                logger.error(f"CRITICAL: Failed to click bet spot for {bet_type} robustly.")
                return False
            logger.info(f"Bet area for {bet_type} clicked.")
            time.sleep(0.5) 

            # Step 3: Confirm Bet (if Unibet has a separate global confirm button)
            # confirm_button_xpaths = [
            #    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') and not(@disabled)]",
            #    "//button[@data-testid='confirm-all-bets-button' and not(@disabled)]"
            # ]
            # confirm_button = self._find_element_by_xpaths(confirm_button_xpaths, clickable=True, wait_instance=self.short_wait)
            # if confirm_button:
            #    if self._click_element_robustly(confirm_button, "global confirm bet button"):
            #        logger.info("Global confirm bet button clicked.")
            #    else:
            #        logger.warning("Failed to click global confirm bet button robustly.") # May or may not be critical
            # else:
            #    logger.info("No global confirm bet button found/needed, or it timed out.")
            
            # Step 4: Wait for Bet Acceptance Confirmation (VERY IMPORTANT for real money)
            # bet_accepted_indicator_xpaths = [
            #     "//div[contains(@class, 'message-bet-accepted') or contains(text(),'Bet Accepted') or contains(text(),'Inzet geaccepteerd')]",
            #     "//div[contains(@class, 'chips-on-table') and .//div[contains(@class,'chip')]]" # Check if chips are visually on the spot
            # ]
            # logger.info("Waiting for bet acceptance confirmation...")
            # if not self._find_element_by_xpaths(bet_accepted_indicator_xpaths, wait_instance=WebDriverWait(self.driver, 7)): # Wait up to 7s
            #     logger.error("CRITICAL: Bet acceptance confirmation not found. Bet may have failed or been rejected.")
            #     return False 
            # logger.info("Bet acceptance confirmed.")
            
            logger.warning(f"PLACEHOLDER: place_bet({bet_type}, {amount}). Assumed successful after clicks.")
            logger.critical("CRITICAL: Real chip selection and bet confirmation logic is needed for the target site.")
            return True 
        except Exception as e:
            logger.error(f"Error placing bet on {bet_type} for Unibet: {e}", exc_info=True)
            return False

    def get_bet_outcome(self):
        if not self.driver: 
            logger.error("get_bet_outcome: Driver not available.")
            return None
        try:
            # Ensure we are in the game iframe if one exists
            if not self.is_in_iframe and not self._switch_to_game_iframe_if_present():
                logger.warning("get_bet_outcome: Could not ensure iframe context. Outcome detection might be inaccurate.")
            
            # Ensure correct iframe context.
            logger.info("Attempting to determine bet outcome...")

            # Wait for results to be displayed. This might be a "Winner is X" message,
            # an update to history, or a visual highlight.
            # Example XPaths (HIGHLY UNIBET SPECIFIC):
            # result_announcement_xpaths = [
            #    "//div[contains(@class,'result-announcement__winner') and not(contains(@style,'display: none'))]", 
            #    "//div[contains(@class,'last-result-display__winner-text')]"
            # ] # These are examples, likely need adjustment
            # logger.info("Waiting for result announcement on Unibet (up to 25 seconds)...")
            #
            # # This is a complex part. You might need to wait for a general "results are in" signal,
            # # then specifically check for Dragon, Tiger, or Tie indicators.
            # # For instance, wait for a container to be populated, then check its content.
            #
            # # A simpler (but potentially less reliable) approach:
            # # Check for elements that specifically indicate Dragon win, Tiger win, or Tie.
            # time.sleep(5) # Give some time for results to appear after betting phase ends.
            #
            # dragon_win_indicator = ["//div[contains(@class,'winner-dragon') or contains(@data-result,'DRAGON_WIN')]"]
            # tiger_win_indicator  = ["//div[contains(@class,'winner-tiger') or contains(@data-result,'TIGER_WIN')]"]
            # tie_indicator        = ["//div[contains(@class,'winner-tie') or contains(@data-result,'TIE')]"]
            #
            # if self._find_element_by_xpaths(dragon_win_indicator, wait_instance=self.short_wait): # Quick check
            #     logger.info("Outcome detected: Dragon")
            #     return "dragon"
            # if self._find_element_by_xpaths(tiger_win_indicator, wait_instance=self.short_wait):
            #     logger.info("Outcome detected: Tiger")
            #     return "tiger"
            # if self._find_element_by_xpaths(tie_indicator, wait_instance=self.short_wait):
            #     logger.info("Outcome detected: Tie")
            #     return "tie"
            #
            # logger.warning("Could not determine specific win/loss/tie from result indicators.")


            logger.warning("PLACEHOLDER: get_bet_outcome(). Returning mock result.")
            logger.critical("CRITICAL: Real outcome detection logic is needed for the target site.")
            import random
            return random.choice(["dragon", "tiger", "tie"])
        except Exception as e:
            logger.error(f"Error determining bet outcome from Unibet: {e}", exc_info=True)
            return None

    def close(self):
        if self.driver:
            try:
                logger.info("Attempting to close browser...")
                self.driver.quit() # quit() is generally preferred over close() for ending session
                logger.info("Browser closed successfully via quit().")
            except Exception as e:
                logger.error(f"Error during browser quit: {e}", exc_info=True)
            finally:
                self.driver = None 
                self.is_in_iframe = False # Reset state
                logger.info("Driver set to None after close attempt.")
        else:
            logger.info("Close called, but browser driver was already None.")

        # Clean up the session-specific user data directory if we created one
        if self.current_user_data_dir and os.path.exists(self.current_user_data_dir):
            logger.info(f"Attempting to remove session user data directory: {self.current_user_data_dir}")
            try:
                shutil.rmtree(self.current_user_data_dir)
                logger.info(f"Successfully removed session user data directory: {self.current_user_data_dir}")
            except Exception as e_rm_close:
                logger.error(f"Error removing session user data directory {self.current_user_data_dir} on close: {e_rm_close}", exc_info=True)
        
        self.current_user_data_dir = None # Clear the path
        logger.info("Cleanup logic for user data directory finished.")
