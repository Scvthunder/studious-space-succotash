import os
import sys
import time
import configparser
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                            QWidget, QLabel, QPushButton, QTextEdit,
                            QHBoxLayout, QSpinBox, QComboBox)
from PyQt6.QtCore import QObject, QThread, pyqtSignal

# Local application imports
from browser_control import GameController
from betting_logic import BettingStrategy, MartingaleStrategy, FibonacciStrategy, DAlembertStrategy, ParoliStrategy

# --- Constants ---
CONFIG_FILE = 'config.ini'
DEFAULT_BASE_BET = 1
DEFAULT_WAIT_TIME = 10
DEFAULT_MAX_LOSSES = 5
DEFAULT_PREFERRED_SIDE = 'auto'
DEFAULT_STRATEGY = 'Martingale'

class BotWorker(QObject):
    log_message_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    status_update_signal = pyqtSignal(dict) # For sending various status updates

    def __init__(self, game_controller, strategy, config):
        super().__init__()
        self.game_controller = game_controller
        self.strategy = strategy
        self.config = config
        self._is_running = False

    def run(self):
        self._is_running = True
        try:
            browser = self.config.get('SETTINGS', 'browser', fallback='chrome')
            chromedriver_path_config = self.config.get('SETTINGS', 'chromedriver_path', fallback=None) # For web_app consistency
            game_url = self.config.get('SETTINGS', 'game_url', fallback=None)
            if not game_url:
                self.log_message_signal.emit("CRITICAL Error: 'game_url' not found in config. Bot cannot start.")
                self.error_signal.emit("Configuration Error: 'game_url' is missing in config.ini.")
                # self.status_update_signal.emit({"current_action": "Error: Game URL missing in config"}) # Already handled by error_signal
                return

            # These values are now set in the config object by DragonTigerUI before worker starts
            base_amount = self.config.getfloat('BETTING', 'base_amount', fallback=DEFAULT_BASE_BET)
            wait_time = self.config.getfloat('BETTING', 'wait_time_between_bets', fallback=DEFAULT_WAIT_TIME)
            max_losses = self.config.getint('BETTING', 'max_consecutive_losses', fallback=DEFAULT_MAX_LOSSES)
            
            initial_status = {"current_action": "Initializing...", 
                              "last_result": "N/A", 
                              "consecutive_losses": 0, 
                              "current_bet_amount": 0, "player_balance": "N/A"}
            self.status_update_signal.emit(initial_status)

            self.log_message_signal.emit(f"Attempting to start browser: {browser}")
            self.status_update_signal.emit({"current_action": f"Starting {browser}..."})
            self.game_controller.start_browser(browser, explicit_chromedriver_path=chromedriver_path_config)
            self.log_message_signal.emit(f"Loading game from: {game_url}")
            self.status_update_signal.emit({"current_action": f"Loading game: {game_url}"})
            self.game_controller.load_game(game_url) # This can raise an exception

            loop_count = 0
            balance_check_interval = 5 # Check balance every 5 loops
            current_balance = None

            # Initial balance check
            current_balance = self.game_controller.get_player_balance()
            self.status_update_signal.emit({"player_balance": f"{current_balance:.2f}" if isinstance(current_balance, float) else "N/A"})

            while self._is_running:
                loop_count += 1
                if not self.strategy.should_continue(max_losses):
                    self.log_message_signal.emit(f"Max {max_losses} consecutive losses reached. Stopping bot.")
                    self.status_update_signal.emit({"current_action": "Max losses reached. Stopping."})
                    break
                self.log_message_signal.emit("Attempting to get game state...")
                # Ensure XPaths in browser_control.py match the target website.
                if loop_count % balance_check_interval == 0 or current_balance is None:
                    current_balance = self.game_controller.get_player_balance()
                    self.status_update_signal.emit({"player_balance": f"{current_balance:.2f}" if isinstance(current_balance, float) else "N/A"})
                game_state = self.game_controller.get_game_state()

                if not self._is_running: break # Check if stop was called during web interaction

                if game_state:
                    self.log_message_signal.emit(f"Game state received: {game_state}")
                    self.status_update_signal.emit({"current_action": "Analyzing game state..."})
                    # Current BettingStrategy.analyze always returns 'dragon'.
                    # This needs to be enhanced for actual strategies.
                    bet_decision = self.strategy.analyze(game_state)

                    if not self._is_running: break

                    if bet_decision:
                        self.log_message_signal.emit(f"Strategy recommends betting on:  {bet_decision}")
                        # Get bet amount from strategy (which considers base_amount and history)
                        # The strategy's get_bet_amount method needs to be implemented.
                        # For now, it might just return base_amount if not implemented.
                        current_bet_amount = self.strategy.get_bet_amount(base_amount)

                        if isinstance(current_balance, float) and current_bet_amount > current_balance:
                            self.log_message_signal.emit(f"Bet amount {current_bet_amount} exceeds balance {current_balance}. Skipping bet.")
                            self.status_update_signal.emit({"current_action": "Insufficient balance. Skipping bet."})
                            # Wait and continue loop
                            for i in range(int(wait_time), 0, -1): # Use the configured wait time
                                self.status_update_signal.emit({"current_action": f"Waiting (low balance)... {i}s"})
                                time.sleep(1)
                                if not self._is_running: break
                            continue
                        self.log_message_signal.emit(f"Placing bet: {bet_decision} for {current_bet_amount}")
                        self.status_update_signal.emit({"current_action": f"Placing bet: {bet_decision} for {current_bet_amount}", "current_bet_amount": current_bet_amount})

                        # Ensure XPaths for bet buttons in browser_control.py are correct.
                        bet_successful = self.game_controller.place_bet(bet_decision, current_bet_amount)
                        
                        if not self._is_running: break

                        if bet_successful:
                            self.log_message_signal.emit("Bet placed successfully (according to controller).")
                            self.status_update_signal.emit({"current_action": "Bet placed. Determining outcome..."})
                            # !!! CRITICAL PLACEHOLDER !!!
                            # Actual game result (win/loss/tie) needs to be determined here.
                            # This requires reading the game outcome from the web page using GameController.
                            self.log_message_signal.emit("Attempting to determine bet outcome from site...")
                            actual_result_from_site = self.game_controller.get_bet_outcome() # Expects 'dragon', 'tiger', 'tie', or None
                            outcome_for_strategy = 'loss' # Default to loss;
                            
                            if actual_result_from_site is None:
                                self.log_message_signal.emit("Could not determine bet outcome from site. Treating as 'loss' for strategy.")
                                # outcome_for_strategy remains 'loss'
                            else:
                                if actual_result_from_site == 'tie':
                                    outcome_for_strategy = 'tie'
                                    self.log_message_signal.emit(f"Bet outcome: TIE. Strategy will be updated with 'tie'.")
                                elif actual_result_from_site == bet_decision: # bet_decision was 'dragon' or 'tiger'
                                    outcome_for_strategy = 'win'
                                    self.log_message_signal.emit(f"Bet outcome: WIN! (Bet: {bet_decision}, Result: {actual_result_from_site}). Strategy will be updated with 'win'.")
                                else: # actual_result_from_site was 'dragon' or 'tiger', but not what was bet_decision
                                    # outcome_for_strategy remains 'loss'
                                    self.log_message_signal.emit(f"Bet outcome: LOSS. (Bet: {bet_decision}, Result: {actual_result_from_site}). Strategy will be updated with 'loss'.")

                            self.strategy.update_history(outcome_for_strategy)
                            self.log_message_signal.emit(
                                f"Strategy history updated with: '{outcome_for_strategy}'. Raw game outcome: '{actual_result_from_site if actual_result_from_site else 'Unknown'}'. Waiting {wait_time}s for next round."
                            )
                            self.status_update_signal.emit({
                                "current_action": f"Outcome: {actual_result_from_site if actual_result_from_site else 'Unknown'}. Waiting...", # UI can show D/T/T
                                "last_result": actual_result_from_site if actual_result_from_site else "Unknown",
                                "consecutive_losses": self.strategy.consecutive_losses
                            })
                        else:
                            self.log_message_signal.emit(f"Failed to place bet on {bet_decision} (according to controller). Waiting {wait_time}s.")
                            self.status_update_signal.emit({"current_action": "Bet placement failed. Waiting..."})
                    else:
                        self.log_message_signal.emit(f"Strategy recommended no bet this round. Waiting {wait_time}s.")
                        self.status_update_signal.emit({"current_action": "No bet this round. Waiting..."})
                else:
                    self.log_message_signal.emit(f"Could not retrieve game state. Waiting {wait_time}s before retrying.")
                    self.status_update_signal.emit({"current_action": "Failed to get game state. Retrying..."})

                if self._is_running: # Only sleep if still supposed to be running
                    for i in range(int(wait_time), 0, -1):
                        self.status_update_signal.emit({"current_action": f"Waiting for next round... {i}s"})
                        time.sleep(1)
                        if not self._is_running: break
                    # The time.sleep(wait_time) call that was here is redundant,
                    # as the loop above already handles the waiting period and provides feedback.

        except Exception as e:
            self.error_signal.emit(f"Bot Error: {str(e)}")
        finally:
            self.log_message_signal.emit("Bot worker stopping...")
            current_action_on_stop = "Bot stopped."
            if self._is_running: # If it was an unexpected stop due to error
                current_action_on_stop = "Bot stopped due to error."
            self.game_controller.close()
            self.log_message_signal.emit("Browser closed by GameController.")
            self.status_update_signal.emit({"current_action": current_action_on_stop, "last_result": "N/A", "consecutive_losses": 0, "current_bet_amount": 0, "player_balance": "N/A"})
            self._is_running = False
            self.log_message_signal.emit("Bot worker finished execution.")
            self.finished_signal.emit()

    def stop(self):
        self.log_message_signal.emit("Stop signal received by worker.")
        self._is_running = False

class DragonTigerUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.bot_thread = None
        self.bot_worker = None
        self.config = configparser.ConfigParser()
        self.game_controller = GameController(self.config) # Pass config object

        self.load_config()

    def initUI(self):
        self.setWindowTitle("Dragon Tiger Bot")
        self.setGeometry(100, 100, 800, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        # Control buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Bot")
        self.start_btn.setFixedHeight(40)
        self.stop_btn = QPushButton("Stop Bot")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.save_config_btn = QPushButton("Save Config")
        self.save_config_btn.setFixedHeight(40)
        self.clear_logs_btn = QPushButton("Clear Logs") # New button
        self.clear_logs_btn.setFixedHeight(40)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.save_config_btn)
        btn_layout.addWidget(self.clear_logs_btn) # Add to layout

        # Betting controls
        config_layout1 = QHBoxLayout()
        config_layout1.addWidget(QLabel("Base Bet:"))
        self.bet_amount_spinbox = QSpinBox()
        self.bet_amount_spinbox.setRange(1, 1000)
        config_layout1.addWidget(self.bet_amount_spinbox)

        config_layout1.addWidget(QLabel("Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([DEFAULT_STRATEGY, "Fibonacci", "D'Alembert", "Paroli", "BettingStrategy"])
        config_layout1.addWidget(self.strategy_combo)
        
        config_layout2 = QHBoxLayout()
        config_layout2.addWidget(QLabel("Wait Time (s):"))
        self.wait_time_spinbox = QSpinBox()
        self.wait_time_spinbox.setRange(1, 300) # e.g., 1s to 5 minutes
        config_layout2.addWidget(self.wait_time_spinbox)

        config_layout2.addWidget(QLabel("Max Losses:"))
        self.max_losses_spinbox = QSpinBox()
        self.max_losses_spinbox.setRange(1, 100)
        config_layout2.addWidget(self.max_losses_spinbox)

        config_layout3 = QHBoxLayout()
        config_layout3.addWidget(QLabel("Preferred Side:"))
        self.preferred_side_combo = QComboBox()
        self.preferred_side_combo.addItems([DEFAULT_PREFERRED_SIDE.capitalize(), "Dragon", "Tiger"])
        config_layout3.addWidget(self.preferred_side_combo)
        config_layout3.addStretch(1) # Add stretch to push combo to left

        # Status display
        status_layout = QHBoxLayout()
        self.status_action_label = QLabel("Current Action: Idle")
        self.status_result_label = QLabel("Last Result: N/A")
        self.status_losses_label = QLabel("Consecutive Losses: 0")
        self.status_bet_label = QLabel("Current Bet: 0")
        self.status_balance_label = QLabel("Balance: N/A") # New
        
        # Initial style for status action label
        self.status_action_label.setStyleSheet("background-color: lightgray; padding: 2px;")


        v_status_layout1 = QVBoxLayout()
        v_status_layout1.addWidget(self.status_action_label)
        v_status_layout1.addWidget(self.status_result_label)
        v_status_layout1.addWidget(self.status_balance_label) # New
        
        v_status_layout2 = QVBoxLayout()
        v_status_layout2.addWidget(self.status_losses_label)
        v_status_layout2.addWidget(self.status_bet_label)
        status_layout.addLayout(v_status_layout1)
        status_layout.addStretch(1)
        status_layout.addLayout(v_status_layout2)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)

        # Assemble layout
        layout.addLayout(btn_layout)
        layout.addLayout(config_layout1)
        layout.addLayout(config_layout2)
        layout.addLayout(config_layout3)
        layout.addLayout(status_layout) # Add status display
        layout.addWidget(self.log_display)
        central_widget.setLayout(layout)

        self.config_widgets = [
            self.bet_amount_spinbox, self.strategy_combo, 
            self.wait_time_spinbox, self.max_losses_spinbox,
            self.preferred_side_combo, self.save_config_btn
        ]

        # Connect signals
        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn.clicked.connect(self.stop_bot)
        self.save_config_btn.clicked.connect(self.save_config)
        self.clear_logs_btn.clicked.connect(self.clear_logs) # Connect new button

    def load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE) or not self.config.read(CONFIG_FILE):
                self.log_message(f"Warning: '{CONFIG_FILE}' not found or empty. Using default values. Save to create.")
                self.bet_amount_spinbox.setValue(DEFAULT_BASE_BET)
                self.strategy_combo.setCurrentText(DEFAULT_STRATEGY)
                self.wait_time_spinbox.setValue(DEFAULT_WAIT_TIME)
                self.max_losses_spinbox.setValue(DEFAULT_MAX_LOSSES)
                self.preferred_side_combo.setCurrentText(DEFAULT_PREFERRED_SIDE.capitalize())
                self.log_message("Please review settings and click 'Save Config'.")
                self.set_controls_enabled(True) # Keep controls enabled
                self.start_btn.setEnabled(False) # But disable start until config is saved
            else:
                self.log_message(f"Configuration loaded from {CONFIG_FILE}.")
                self.bet_amount_spinbox.setValue(self.config.getint('BETTING', 'base_amount', fallback=DEFAULT_BASE_BET))
                self.strategy_combo.setCurrentText(self.config.get('BETTING', 'strategy', fallback=DEFAULT_STRATEGY))
                self.wait_time_spinbox.setValue(self.config.getint('BETTING', 'wait_time_between_bets', fallback=DEFAULT_WAIT_TIME))
                self.max_losses_spinbox.setValue(self.config.getint('BETTING', 'max_consecutive_losses', fallback=DEFAULT_MAX_LOSSES))
                
                # Critical check for game_url
                if not self.config.get('SETTINGS', 'game_url', fallback=None):
                    self.log_message("CRITICAL: 'game_url' is missing in config.ini. Bot cannot start.")
                    self.start_btn.setEnabled(False)
                    self.status_action_label.setText("Current Action: Error - Game URL missing")
                    self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish
                
                preferred_side_cfg = self.config.get('BETTING', 'preferred_side', fallback=DEFAULT_PREFERRED_SIDE).capitalize()
                if self.preferred_side_combo.findText(preferred_side_cfg) != -1:
                    self.preferred_side_combo.setCurrentText(preferred_side_cfg)
                else:
                    self.preferred_side_combo.setCurrentText(DEFAULT_PREFERRED_SIDE.capitalize())
                self.start_btn.setEnabled(True)
                self.status_action_label.setText("Current Action: Idle")
                self.status_action_label.setStyleSheet("background-color: lightblue; padding: 2px;")

        except configparser.Error as e:
            self.log_message(f"Error reading {CONFIG_FILE}: {e}. Using defaults.")
            self.start_btn.setEnabled(False)
            self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish
        except Exception as e_global: # Catch any other unexpected error during load
            self.log_message(f"Unexpected error loading config: {e_global}. Using defaults.")
            self.start_btn.setEnabled(False)
            self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish

    def save_config(self):
        if not self.config.has_section('SETTINGS'):
            self.config.add_section('SETTINGS')
        if not self.config.has_section('BETTING'):
            self.config.add_section('BETTING')

        self.config.set('BETTING', 'base_amount', str(self.bet_amount_spinbox.value()))
        self.config.set('BETTING', 'strategy', self.strategy_combo.currentText())
        self.config.set('BETTING', 'wait_time_between_bets', str(self.wait_time_spinbox.value()))
        self.config.set('BETTING', 'max_consecutive_losses', str(self.max_losses_spinbox.value()))
        self.config.set('BETTING', 'preferred_side', self.preferred_side_combo.currentText().lower())

        try:
            with open(CONFIG_FILE, 'w') as configfile:
                self.config.write(configfile)
            self.log_message(f"Configuration saved to {CONFIG_FILE}.")
            # Enable start button only if critical configs like game_url are present
            if self.config.get('SETTINGS', 'game_url', fallback=None):
                self.start_btn.setEnabled(True)
            else:
                self.log_message("Warning: 'game_url' is still missing in config. Bot cannot start.")
        except IOError:
            self.log_message(f"Error: Could not write to {CONFIG_FILE}.")

    def log_message(self, msg):
        self.log_display.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def clear_logs(self):
        self.log_display.clear()
        self.log_message("Logs cleared by user.") # Optional: Log the action itself

    def update_status_display(self, status_data):
        if "current_action" in status_data:
            action_text = status_data['current_action']
            if "starting" in action_text.lower() or "running" in action_text.lower() or "placing bet" in action_text.lower() or "analyzing" in action_text.lower() or "waiting" in action_text.lower() :
                self.status_action_label.setStyleSheet("background-color: #CCFFCC; color: black; padding: 2px;") # Greenish
            elif "error" in action_text.lower() or "failed" in action_text.lower():
                self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish
            elif "stopped" in action_text.lower() or "idle" in action_text.lower():
                 self.status_action_label.setStyleSheet("background-color: lightgray; color: black; padding: 2px;") # Grayish

            self.status_action_label.setText(f"Current Action: {status_data['current_action']}")
        if "last_result" in status_data:
            self.status_result_label.setText(f"Last Result: {status_data['last_result']}")
        if "consecutive_losses" in status_data:
            self.status_losses_label.setText(f"Consecutive Losses: {status_data['consecutive_losses']}")
        if "current_bet_amount" in status_data:
            self.status_bet_label.setText(f"Current Bet: {status_data['current_bet_amount']}")
        if "player_balance" in status_data: # New
            self.status_balance_label.setText(f"Balance: {status_data['player_balance']}")

    def set_controls_enabled(self, enabled):
        self.log_message(f"UI Controls {'enabled' if enabled else 'disabled'}.")
        for widget in self.config_widgets:
            widget.setEnabled(enabled)
        # Special handling for start/stop buttons based on overall 'enabled' state
        self.start_btn.setEnabled(enabled) # Start is enabled when controls are enabled
        self.stop_btn.setEnabled(not enabled) # Stop is enabled when controls are disabled (i.e., bot running)

    def start_bot(self):
        if self.bot_thread and self.bot_thread.isRunning():
            self.log_message("Bot is already running.")
            return
        
        # Final check for game_url before starting
        if not self.config.get('SETTINGS', 'game_url', fallback=None):
            self.log_message("Cannot start bot: 'game_url' is missing in the configuration.")
            self.status_action_label.setText("Current Action: Error - Game URL missing")
            self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish
            return

        # Update self.config (in-memory) from UI controls before starting bot
        # This ensures BotWorker gets the latest settings from the UI
        # Ensure sections exist before setting
        if not self.config.has_section('SETTINGS'):
            self.config.add_section('SETTINGS') # For browser, game_url etc.
        if not self.config.has_section('BETTING'):
            self.config.add_section('BETTING')

        try:
            self.config.set('BETTING', 'base_amount', str(self.bet_amount_spinbox.value()))
            self.config.set('BETTING', 'strategy', self.strategy_combo.currentText())
            self.config.set('BETTING', 'wait_time_between_bets', str(self.wait_time_spinbox.value()))
            self.config.set('BETTING', 'max_consecutive_losses', str(self.max_losses_spinbox.value()))
            self.config.set('BETTING', 'preferred_side', self.preferred_side_combo.currentText().lower())
        except Exception as e:
            self.log_message(f"Error preparing config from UI: {e}. Bot may not use latest UI settings.")
            # Decide if bot should start or not if this fails. For now, it will try with existing self.config.

        # Initialize strategy based on current UI selection
        strategy_name_ui = self.strategy_combo.currentText()
        preferred_side_ui = self.preferred_side_combo.currentText().lower()

        strategy_map = {
            "Martingale": MartingaleStrategy,
            "Fibonacci": FibonacciStrategy,
            "D'Alembert": DAlembertStrategy,
            "Paroli": ParoliStrategy,
            "BettingStrategy": BettingStrategy # Fallback
        }
        strategy_class = strategy_map.get(strategy_name_ui, BettingStrategy)
        self.strategy = strategy_class(preferred_side=preferred_side_ui)
        self.log_message(f"Using strategy: {self.strategy.__class__.__name__}, Preferred Side: {self.strategy.preferred_side}")

        self.bot_thread = QThread()
        self.bot_worker = BotWorker(self.game_controller, self.strategy, self.config) # GameController already has config
        self.bot_worker.moveToThread(self.bot_thread)
        # Connect signals
        self.bot_worker.log_message_signal.connect(self.log_message)
        self.bot_worker.error_signal.connect(self.handle_bot_error)
        self.bot_worker.finished_signal.connect(self.on_bot_finished)
        self.bot_worker.status_update_signal.connect(self.update_status_display) # Connect new signal
        self.bot_thread.started.connect(self.bot_worker.run)

        self.set_controls_enabled(False)
        self.bot_thread.start()

    def stop_bot(self):
        if self.bot_worker:
            self.log_message("Sending stop signal to bot...")
            self.bot_worker.stop()
        # UI controls will be re-enabled by on_bot_finished or handle_bot_error

    def handle_bot_error(self, error_message):
        self.log_message(f"ERROR: {error_message}")
        self.status_action_label.setText(f"Current Action: Error - {error_message[:50]}...")
        self.status_action_label.setStyleSheet("background-color: #FFCCCC; color: black; padding: 2px;") # Reddish
        self.set_controls_enabled(True) # Re-enable controls on error

    def on_bot_finished(self):
        self.log_message("Bot has stopped.")
        # Status label update is handled by BotWorker's finally block or update_status_display
        # Ensure the style reflects "stopped" state if not already set by worker
        if "error" not in self.status_action_label.text().lower(): # Don't overwrite error state
            self.status_action_label.setText("Current Action: Bot stopped.")
            self.status_action_label.setStyleSheet("background-color: lightgray; padding: 2px;")

        self.set_controls_enabled(True)

        
        self.bot_worker = None
        self.bot_thread = None

    def closeEvent(self, event):
        self.log_message("Application closing...")
        if self.bot_worker:
            self.log_message("Requesting bot worker to stop (from closeEvent)...")
            self.bot_worker.stop() # Signal the worker to stop its loop

        if self.bot_thread and self.bot_thread.isRunning():
            self.log_message("Waiting for bot thread to finish (from closeEvent)...")
            self.bot_thread.quit() # Request the thread's event loop to exit
            if not self.bot_thread.wait(5000): # Wait up to 5 seconds
                self.log_message("Bot thread did not quit in time (quit signal). Attempting to terminate (from closeEvent).")
                self.bot_thread.terminate() # Force terminate if quit fails
                if not self.bot_thread.wait(2000): # Wait for termination
                    self.log_message("Bot thread did not terminate after terminate() signal (from closeEvent).")
            else:
                self.log_message("Bot thread finished gracefully after quit() signal (from closeEvent).")
        elif self.bot_thread: # If thread exists but is not running
            self.log_message("Bot thread existed but was not running at close. Ensuring cleanup (from closeEvent).")
            self.bot_thread.wait() # Ensure any final cleanup if it finished just now

        self.game_controller.close() # Ensure browser is closed if GameController instance is tied to UI lifecycle
        self.log_message("GameController closed from UI closeEvent.")
        super().closeEvent(event)
if __name__ == "__main__":
    print(f"--- Debug: Initial os.environ.get('DISPLAY'): {os.environ.get('DISPLAY')}")
    print(f"--- Debug: Initial sys.platform: {sys.platform}")
    print(f"--- Debug: Initial os.environ.get('QT_QPA_PLATFORM'): {os.environ.get('QT_QPA_PLATFORM')}")

    # If DISPLAY is not set (e.g., in a headless environment like a Docker container or SSH session without X forwarding)
    # and we are on Linux, set QT_QPA_PLATFORM to offscreen.
    if "DISPLAY" not in os.environ and sys.platform.startswith('linux'):
        print("--- Debug: Condition met: 'DISPLAY' not in os.environ AND sys.platform.startswith('linux')")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        print(f"--- Debug: Setting QT_QPA_PLATFORM to 'offscreen'")
    else:
        print("--- Debug: Condition NOT met for setting QT_QPA_PLATFORM to 'offscreen'.")
        if "DISPLAY" in os.environ:
            print(f"--- Debug: 'DISPLAY' is set to: {os.environ.get('DISPLAY')}")
        if not sys.platform.startswith('linux'):
            print(f"--- Debug: sys.platform is not Linux: {sys.platform}")


    print(f"--- Debug: Final os.environ.get('QT_QPA_PLATFORM') before QApplication: {os.environ.get('QT_QPA_PLATFORM')}")
    app = QApplication(sys.argv)

    # --- Apply a stylesheet for a more modern look ---
    # This provides a basic dark theme. For "Apple level" polish and extensive animations,
    # much more detailed QSS, custom widget painting, and Qt's animation framework
    # (e.g., QPropertyAnimation) would be required.
    dark_stylesheet = """
        QMainWindow {
            background-color: #2E3B4E; /* Dark blue-gray background */
        }
        QWidget {
            color: #E0E0E0; /* Light gray text for readability */
            font-size: 10pt; /* Slightly larger base font */
            font-family: "Segoe UI", Arial, sans-serif; /* Modern font stack */
        }
        QLabel {
            color: #C5C5C5; /* Slightly dimmer for non-critical labels */
            padding: 3px;
        }
        QPushButton {
            background-color: #4A5A70; /* Button color */
            color: #FFFFFF;
            border: 1px solid #5A6A80;
            padding: 8px 15px;
            border-radius: 4px; /* Rounded corners */
            min-height: 26px;
        }
        QPushButton:hover {
            background-color: #5A6A80;
            border-color: #6A7A90;
        }
        QPushButton:pressed {
            background-color: #3A4A60;
        }
        QPushButton:disabled {
            background-color: #354050;
            color: #787878;
            border-color: #405060;
        }
        QTextEdit {
            background-color: #252E3A; /* Darker background for text areas */
            color: #D0D0D0;
            border: 1px solid #4A5A70;
            border-radius: 4px;
            font-family: "Consolas", "Courier New", monospace; /* Monospaced for logs */
        }
        QSpinBox, QComboBox {
            background-color: #3C4A5E;
            color: #E0E0E0;
            border: 1px solid #5A6A80;
            padding: 5px;
            border-radius: 4px;
            min-height: 22px;
        }
        QComboBox::drop-down {
            border: none;
            background-color: #4A5A70;
            width: 20px;
            border-top-right-radius: 3px; /* Match parent radius */
            border-bottom-right-radius: 3px;
        }
        /* For QComboBox arrow and QSpinBox arrows, custom images are often needed for deep styling.
           The default system arrows will be used here for simplicity. */

        /* Specific labels like status_action_label will still have their dynamic styles
           applied via python, potentially overriding parts of this base style. */
    """
    app.setStyleSheet(dark_stylesheet)
    # --- End of stylesheet application ---

    print("--- Debug: QApplication instantiated.")
    window = DragonTigerUI()
    print("--- Debug: DragonTigerUI instantiated.")
    window.show() # In offscreen mode, this won't render visibly but the app runs
    print("--- Debug: window.show() called.")
    """
    # If running in offscreen mode, automatically try to start the bot.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        print("--- Debug: Headless (offscreen) mode detected. Attempting to auto-start bot...")
        window.log_message("Headless mode: Auto-starting bot...")
        window.start_bot() # This will use the loaded configuration.
    """

    sys.exit(app.exec())
