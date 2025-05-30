import sys
import configparser
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                            QWidget, QPushButton, QLabel, QTextEdit)
from browser_control import GameController
from betting_logic import BettingStrategy

class DragonTigerBot(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.game = GameController()
        self.strategy = BettingStrategy()
        self.running = False
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Dragon Tiger Auto Bot")
        self.setGeometry(100, 100, 500, 400)
        
        layout = QVBoxLayout()
        
        self.status = QLabel("Status: Ready")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        
        self.start_btn = QPushButton("Start Bot")
        self.start_btn.clicked.connect(self.start_bot)
        
        self.stop_btn = QPushButton("Stop Bot")
        self.stop_btn.clicked.connect(self.stop_bot)
        
        layout.addWidget(self.status)
        layout.addWidget(self.log)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
    def log_message(self, message):
        self.log.append(message)
        print(message)
        
    def start_bot(self):
        try:
            self.log_message("Starting bot...")
            self.running = True
            self.game.start_browser(self.config['SETTINGS']['browser'])
            self.game.load_game(self.config['SETTINGS']['game_url'])
            
            base_amount = float(self.config['BETTING']['base_amount'])
            wait_time = float(self.config['BETTING']['wait_time_between_bets'])
            max_losses = int(self.config['BETTING']['max_consecutive_losses'])
            
            while self.running:
                game_state = self.game.get_game_state()
                if game_state:
                    bet_type = self.strategy.analyze(game_state)
                    if bet_type:
                        if self.strategy.should_continue(max_losses):
                            self.log_message(f"Placing {bet_type} bet for {base_amount}")
                            if self.game.place_bet(bet_type, base_amount):
                                # In real implementation, you'd check actual result
                                self.strategy.update_history('win')
                            time.sleep(wait_time)
                        else:
                            self.log_message("Max consecutive losses reached, stopping")
                            self.stop_bot()
                    else:
                        self.log_message("No bet recommended this round")
                        time.sleep(wait_time)
                else:
                    self.log_message("Couldn't get game state, retrying...")
                    time.sleep(5)
                    
        except Exception as e:
            self.log_message(f"Error: {str(e)}")
            self.stop_bot()
            
    def stop_bot(self):
        self.log_message("Stopping bot...")
        self.running = False
        self.game.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bot = DragonTigerBot()
    bot.show()
    sys.exit(app.exec())
