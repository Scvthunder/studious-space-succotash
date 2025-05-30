from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

class GameController:
    def __init__(self):
        self.driver = None
        self.wait = None
        
    def start_browser(self, browser_type='chrome'):
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1200,800")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        
    def load_game(self, url):
        self.driver.get(url)
        time.sleep(5)
        
    def get_game_state(self):
        try:
            dragon = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'dragon')]"))
            ).text
            tiger = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'tiger')]"))
            ).text
            return {'dragon': dragon, 'tiger': tiger}
        except Exception as e:
            print(f"Error getting game state: {e}")
            return None
            
    def place_bet(self, bet_type, amount):
        try:
            bet_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(@class,'bet-{bet_type.lower()}')]"))
            )
            bet_button.click()
            time.sleep(1)
            return True
        except Exception as e:
            print(f"Error placing bet: {e}")
            return False
            
    def close(self):
        if self.driver:
            self.driver.quit()
