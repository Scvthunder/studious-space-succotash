import os
import sys
import time
import configparser
import threading
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
import webbrowser

# Attempt to import WebDriverException and check its availability
try:
    from selenium.common.exceptions import WebDriverException
    _ = WebDriverException # Test if the name is now defined
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] >>> DEBUG: 'from selenium.common.exceptions import WebDriverException' executed. WebDriverException IS LOCALLY DEFINED.")
except ImportError:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] >>> CRITICAL DEBUG: FAILED to import WebDriverException from selenium.common.exceptions. ImportError.")
    WebDriverException = None # Define it as None to prevent further NameErrors if import fails
except NameError: # Should not happen if import was successful
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] >>> CRITICAL DEBUG: NameError after attempting to import WebDriverException. This is unexpected.")
    WebDriverException = None # Define as None
# Local application imports
from browser_control import GameController
from betting_logic import BettingStrategy, MartingaleStrategy, FibonacciStrategy, DAlembertStrategy, ParoliStrategy

# --- Initial Module Load Log ---
initial_load_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
print(f"[{initial_load_timestamp}] >>> DragonTigerBot/web_app.py (THIS VERSION) IS BEING LOADED <<<")

# --- Flask App Setup ---
_current_script_dir = os.path.dirname(os.path.abspath(__file__))
_template_dir = os.path.join(_current_script_dir, 'templates')

app = Flask(__name__, template_folder=_template_dir)
app.secret_key = "dt_bot_secret_key_!@#"

# --- Global Bot State ---
bot_state = {
    "is_running": False,
    "logs": [],
    "status": {"current_action": "Idle", "last_result": "N/A", "consecutive_losses": 0, "current_bet_amount": 0, "player_balance": "N/A"},
    "latest_screenshot_filename": None,
    "thread": None,
    "stop_event": threading.Event()
}
MAX_LOGS = 200 # Max logs to keep in memory for the UI
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screenshots')
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

# --- Logging ---
# Configure root logger for basic output, then get specific logger for this app
logging.basicConfig(stream=sys.stdout, level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DragonTigerWebApp") # Specific logger name
logger.setLevel(logging.DEBUG) # Set specific logger level if needed, e.g., DEBUG for more verbosity

# --- Helper Functions ---
def add_log(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S') # More complete timestamp
    log_entry = f"[{timestamp}] {message}"
    bot_state["logs"].append(log_entry)
    if len(bot_state["logs"]) > MAX_LOGS:
        bot_state["logs"].pop(0) 
    logger.info(message) # Log to console via Python logger

def update_status(new_status_partial):
    bot_state["status"].update(new_status_partial)
    logger.debug(f"UI Status updated: {new_status_partial}. Full status: {bot_state['status']}")

def take_screenshot(gc, filename_prefix="ss"):
    if gc and gc.driver:
        # --- Debug check for WebDriverException scope ---
        wde_defined = 'WebDriverException' in globals() or 'WebDriverException' in locals()
        logger.debug(f"In take_screenshot (prefix: {filename_prefix}): Is WebDriverException defined in current scope? {'Yes' if wde_defined else 'NO - POTENTIAL IMPORT ISSUE!'}")
        if not wde_defined:
            add_log("CRITICAL DEBUG: WebDriverException is NOT defined in take_screenshot scope! Check web_app.py imports.")
        logger.debug(f"Attempting to take screenshot with prefix: {filename_prefix}") # Added log
        try:
            logger.debug(f"take_screenshot: Checking/creating screenshot directory: {SCREENSHOT_DIR}")
            if not os.path.exists(SCREENSHOT_DIR):
                os.makedirs(SCREENSHOT_DIR)
                logger.info(f"take_screenshot: Created screenshot directory: {SCREENSHOT_DIR}")
            else:
             logger.debug(f"take_screenshot: Screenshot directory already exists: {SCREENSHOT_DIR}")

            timestamp = time.strftime("%Y%m%d-%H%M%S")
            # Sanitize filename_prefix as well if it comes from dynamic sources
            safe_prefix = secure_filename(filename_prefix)
            filename = f"{safe_prefix}_{timestamp}.png"
            filepath = os.path.join(SCREENSHOT_DIR, filename)
            
            logger.info(f"Attempting to save screenshot via web_app to: {filepath}")
            gc.driver.save_screenshot(filepath) # This will raise an exception on most failures
            logger.info(f"Screenshot saved successfully to {filepath}")

            old_screenshot = bot_state.get("latest_screenshot_filename")
            if old_screenshot and old_screenshot != filename:
                old_filepath = os.path.join(SCREENSHOT_DIR, old_screenshot)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                        logger.debug(f"Removed old screenshot: {old_filepath}")
                    except OSError as e:
                        logger.error(f"Error removing old screenshot {old_filepath}: {e}")
                else:
                    logger.warning(f"Old screenshot file not found for removal: {old_filepath}")
            
            bot_state["latest_screenshot_filename"] = filename
            # Log is now done in bot_logic_thread_func after calling this
            return filename
        except Exception as e_wd: # Changed to generic Exception to handle if WebDriverException is None
            if WebDriverException and isinstance(e_wd, WebDriverException):
                add_log(f"Screenshot WebDriverException: {type(e_wd).__name__} - {e_wd}")
                logger.error(f"Screenshot WebDriverException: {type(e_wd).__name__} - {e_wd}", exc_info=True)
            else:
                add_log(f"Screenshot error (WebDriverException type might be undefined or error is different type): {type(e_wd).__name__} - {e_wd}")
                logger.error(f"Screenshot error (details): {type(e_wd).__name__} - {e_wd}", exc_info=True)
        except Exception as e: # Catch other potential errors (e.g., OS errors during file ops)
            add_log(f"Screenshot error: {type(e).__name__} - {e}")
            logger.error(f"Screenshot error: {type(e).__name__} - {e}", exc_info=True)
    else:
        logger.warning("take_screenshot called but GameController or driver is not available.")
    return None

# --- Bot Logic Thread ---
def bot_logic_thread_func(config_path, username=None, password=None, preferred_bet_from_ui="auto"): # Added preferred_bet_from_ui
    global bot_state
    logger.info("--- BotLogicThread: Starting execution ---") # Added log
    game_controller = None
    try:
        add_log("Bot thread started.")
        logger.info("Bot logic thread initiated.")
        bot_state["stop_event"].clear()

        config = configparser.ConfigParser()
        if not os.path.exists(config_path) or not config.read(config_path):
            add_log(f"CRITICAL Error: Configuration file '{config_path}' not found or empty.")
            update_status({"current_action": "Error: Config not found"})
            logger.critical(f"Configuration file '{config_path}' not found or empty.")
            return # Pass the loaded config object to GameController
        # Pass the loaded config object to GameController
        game_controller = GameController(config) 

        # Load settings from config
        browser = config.get('SETTINGS', 'browser', fallback='chrome')
        login_url = config.get('SETTINGS', 'login_url', fallback=None)
        chromedriver_path_config = config.get('SETTINGS', 'chromedriver_path', fallback=None) # New
        game_url = config.get('SETTINGS', 'game_url', fallback=None)
        if not game_url:
            add_log("CRITICAL Error: 'game_url' not found in config.ini.")
            update_status({"current_action": "Error: Game URL missing"})
            logger.critical("'game_url' not found in config.ini.")
            return

        base_amount = config.getfloat('BETTING', 'base_amount', fallback=1.0)
        wait_time = config.getfloat('BETTING', 'wait_time_between_bets', fallback=10.0)
        max_losses = config.getint('BETTING', 'max_consecutive_losses', fallback=5)
        
        # Use preferred_bet_from_ui if it's 'dragon' or 'tiger', otherwise use config or default to 'auto'
        # This allows UI to override config's preferred_side if UI sends a specific choice.
        if preferred_bet_from_ui in ['dragon', 'tiger']:
            final_preferred_bet_side = preferred_bet_from_ui
            add_log(f"Using betting preference from UI: {final_preferred_bet_side}")
        else: # 'auto' or unexpected value from UI
            final_preferred_bet_side = config.get('BETTING', 'preferred_side', fallback='auto').lower()
            add_log(f"UI preference is '{preferred_bet_from_ui}'. Using config/default preference: {final_preferred_bet_side}")
            if final_preferred_bet_side not in ['dragon', 'tiger', 'auto']:
                add_log(f"Warning: Invalid preferred_side '{final_preferred_bet_side}' in config. Defaulting to 'auto'.")
                final_preferred_bet_side = 'auto'


        strategy_name = config.get('BETTING', 'strategy', fallback='Martingale')

        update_status({"current_action": "Initializing...", "last_result": "N/A", "consecutive_losses": 0, "current_bet_amount": base_amount, "player_balance": "Fetching..."})

        strategy_map = {
            "Martingale": MartingaleStrategy,
            "Fibonacci": FibonacciStrategy,
            "D'Alembert": DAlembertStrategy,
            "Paroli": ParoliStrategy,
            "BettingStrategy": BettingStrategy # Fallback
        }
        strategy_class = strategy_map.get(strategy_name, BettingStrategy)
        # Pass the determined preferred_bet_side to the strategy
        strategy = strategy_class(preferred_side=final_preferred_bet_side) 
        add_log(f"Using strategy: {strategy.__class__.__name__}, effective preference: {strategy.preferred_side}.")


        add_log(f"Attempting to start browser: {browser}...")
        update_status({"current_action": f"Starting {browser}..."})
        game_controller.start_browser(browser, explicit_chromedriver_path=chromedriver_path_config) # Pass configured path
        add_log("Browser started successfully by GameController.")
        
        if login_url and username and password:
            add_log(f"Attempting login to: {login_url} with user: {username[:3]}***")
            update_status({"current_action": "Logging in..."})
            if not game_controller.login(login_url, username, password):
                add_log("Login failed (as reported by GameController). Stopping bot.")
                update_status({"current_action": "Login Failed."})
                ss_login_fail = take_screenshot(game_controller, "login_failed")
                if ss_login_fail: add_log(f"Screenshot on login failure: {ss_login_fail}")
                return 
            add_log("Login successful (or assumed successful by GameController).")
            ss_login_ok = take_screenshot(game_controller, "login_successful")
            if ss_login_ok: add_log(f"Screenshot after login: {ss_login_ok}")
        elif login_url:
            add_log("Login URL provided in config, but no username/password given to bot. Skipping login.")
        
        ss_browser_ready = take_screenshot(game_controller, "browser_ready_for_game")
        if ss_browser_ready: add_log(f"Screenshot browser ready: {ss_browser_ready}")

        add_log(f"Attempting to load game from: {game_url}")
        update_status({"current_action": f"Loading game: {game_url}"})
        game_controller.load_game(game_url) # This can raise an exception
        add_log("Game loaded successfully by GameController.")
        ss_game_loaded = take_screenshot(game_controller, "game_interface_loaded")
        if ss_game_loaded: add_log(f"Screenshot game loaded: {ss_game_loaded}")
            
        loop_count = 0
        balance_check_interval = 5 # Check balance every 5 loops, for example
        current_balance = None

        # Initial balance check
        current_balance = game_controller.get_player_balance()
        update_status({"player_balance": f"{current_balance:.2f} €" if isinstance(current_balance, float) else "N/A"})
        if isinstance(current_balance, float):
            add_log(f"Initial balance check: {current_balance:.2f} €")
        else:
            add_log("Initial balance check: N/A (could not fetch)")

        last_periodic_update_time = 0 # Initialize to ensure first update runs immediately

        while not bot_state["stop_event"].is_set():
            loop_count += 1
            logger.info(f"Bot loop iteration: {loop_count}")

            # --- Periodic Screenshot and Balance Update (every 10 seconds) ---
            current_time = time.time()
            if current_time - last_periodic_update_time >= 10:
                if bot_state["stop_event"].is_set(): logger.info("Stop event detected before periodic update."); break
                add_log("Periodic update: Taking screenshot and checking balance...")
                periodic_ss_name = take_screenshot(game_controller, "periodic_live_view")
                if periodic_ss_name: add_log(f"Periodic screenshot: {periodic_ss_name}")
                
                if bot_state["stop_event"].is_set(): logger.info("Stop event detected after periodic screenshot."); break
                current_balance = game_controller.get_player_balance() # Fetch current balance
                if bot_state["stop_event"].is_set(): logger.info("Stop event detected after periodic balance check."); break

                balance_display_text = f"{current_balance:.2f} €" if isinstance(current_balance, float) else "N/A"
                update_status({"player_balance": balance_display_text})
                add_log(f"Periodic balance update: {balance_display_text}")
                last_periodic_update_time = current_time

            if not strategy.should_continue(max_losses):
                add_log(f"Strategy indicates stop: Max {max_losses} consecutive losses reached.")
                update_status({"current_action": "Max losses reached. Stopping."})
                break
            if bot_state["stop_event"].is_set(): logger.info("Stop event detected before get_game_state."); break

            add_log(f"Loop {loop_count}: Getting game state...")
            update_status({"current_action": "Getting game state..."})
            game_state = game_controller.get_game_state() # Expects {"history": [...]} or None

            if bot_state["stop_event"].is_set(): logger.info("Stop event detected after get_game_state."); break

            if game_state and "history" in game_state: # Ensure game_state is not None and has history
                add_log(f"Game state received: {game_state['history'][-5:] if game_state['history'] else 'No history'}") # Log last 5
                update_status({"current_action": "Analyzing game state..."})
                bet_decision = strategy.analyze(game_state)
                if bot_state["stop_event"].is_set(): logger.info("Stop event detected after analyze."); break

                if bet_decision:
                    current_bet_amount = strategy.get_bet_amount(base_amount)
                    if isinstance(current_balance, float) and current_bet_amount > current_balance:
                        add_log(f"Bet amount {current_bet_amount} exceeds balance {current_balance}. Reducing bet to balance or stopping.")
                        # Option 1: Reduce bet (if strategy allows or if it's a small amount)
                        # current_bet_amount = current_balance 
                        # Option 2: Stop or skip bet
                        add_log("Insufficient balance for planned bet. Skipping bet round.")
                        update_status({"current_action": "Insufficient balance. Skipping bet."})
                        # Wait and continue loop
                        time.sleep(wait_time) # Use the configured wait time
                        if bot_state["stop_event"].is_set(): break
                        continue

                    if bot_state["stop_event"].is_set(): logger.info("Stop event detected before place_bet."); break
                    add_log(f"Strategy recommends betting on: {bet_decision}, Amount: {current_bet_amount}")
                    update_status({"current_action": f"Placing bet: {bet_decision} for {current_bet_amount}", "current_bet_amount": current_bet_amount})
                    
                    bet_successful = game_controller.place_bet(bet_decision, current_bet_amount)
                    ss_bet_attempt = take_screenshot(game_controller, f"bet_attempt_{loop_count}_{bet_decision}")
                    if ss_bet_attempt: add_log(f"Screenshot after bet attempt on {bet_decision}: {ss_bet_attempt}")

                    if bot_state["stop_event"].is_set(): logger.info("Stop event detected after place_bet."); break

                    if bet_successful:
                        add_log("Bet placed (reported by GameController). Determining outcome...")
                        update_status({"current_action": "Bet placed. Waiting for outcome..."})
                        
                        # Add a small delay before trying to get outcome, site might need time
                        # Make this delay interruptible
                        for _ in range(2): # sleep for 2 seconds, checking event each sec
                            if bot_state["stop_event"].is_set(): break
                            time.sleep(1)
                        if bot_state["stop_event"].is_set(): logger.info("Stop event detected during pre-outcome wait."); break

                        actual_result = game_controller.get_bet_outcome() # Expects 'dragon', 'tiger', 'tie', or None
                        bet_outcome_for_strategy = 'loss' # Default to loss

                        if actual_result is None:
                            add_log("Could not determine bet outcome from site. Treating as 'loss' for strategy.")
                            # bet_outcome_for_strategy remains 'loss'
                        else:
                            if actual_result == 'tie':
                                bet_outcome_for_strategy = 'tie'
                                add_log(f"Bet outcome: TIE. Strategy will be updated with 'tie'.")
                            elif actual_result == bet_decision: # bet_decision was 'dragon' or 'tiger'
                                bet_outcome_for_strategy = 'win'
                                add_log(f"Bet outcome: WIN! (Bet: {bet_decision}, Result: {actual_result}). Strategy will be updated with 'win'.")
                            else: # actual_result was 'dragon' or 'tiger', but not what was bet_decision
                                # bet_outcome_for_strategy remains 'loss'
                                add_log(f"Bet outcome: LOSS. (Bet: {bet_decision}, Result: {actual_result}). Strategy will be updated with 'loss'.")

                        if bot_state["stop_event"].is_set(): logger.info("Stop event detected after get_bet_outcome."); break
                        strategy.update_history(bet_outcome_for_strategy)
                        # Log message now reflects the processed outcome for strategy
                        add_log(f"Strategy history updated with: '{bet_outcome_for_strategy}'. Raw game outcome: '{actual_result if actual_result else 'Unknown'}'.")
                        update_status({
                            "current_action": f"Outcome: {actual_result if actual_result else 'Unknown'}. Waiting...",
                            "last_result": actual_result if actual_result else "Unknown",  # UI can still show actual D/T/T
                            "consecutive_losses": strategy.consecutive_losses
                        })
                    else:
                        add_log(f"Failed to place bet on {bet_decision} (reported by GameController).")
                        update_status({"current_action": f"Bet on {bet_decision} failed. Waiting..."})
                        # Consider if a failed bet should count as a loss for the strategy
                        # strategy.update_history('loss') # If a failed placement should advance strategy
                else:
                    add_log(f"Strategy recommended no bet this round.")
                    update_status({"current_action": "No bet this round. Waiting..."})
            else:
                add_log(f"Could not retrieve valid game state. Retrying after wait.")
                update_status({"current_action": "Failed to get game state. Retrying..."})
                if loop_count % 3 == 0: # Take screenshot less frequently on state fail
                    ss_state_fail = take_screenshot(game_controller, f"get_state_fail_{loop_count}")
                    if ss_state_fail: add_log(f"Screenshot on get_state_fail: {ss_state_fail}")

            if bot_state["stop_event"].is_set(): logger.info("Stop event detected before wait period."); break
            
            add_log(f"Waiting for {wait_time:.1f} seconds before next action...")
            for i in range(int(wait_time)): # Loop for 1-second intervals
                if bot_state["stop_event"].is_set(): break
                # Update status every few seconds during wait or on the last second
                remaining_time = int(wait_time) - i
                if i % 3 == 0 or remaining_time <= 1 : 
                     update_status({"current_action": f"Waiting... {remaining_time}s remaining"})
                time.sleep(1)
            if bot_state["stop_event"].is_set(): logger.info("Stop event detected during wait period."); break
            
    except Exception as e:
        error_message = f"CRITICAL BOT ERROR in thread: {type(e).__name__} - {e}"
        add_log(error_message)
        logger.error(error_message, exc_info=True) # Log full traceback
        update_status({"current_action": f"CRITICAL ERROR: {e}"})
        if game_controller and game_controller.driver: 
            ss_critical_err = take_screenshot(game_controller, "bot_critical_error_state")
            if ss_critical_err: add_log(f"Screenshot on critical error: {ss_critical_err}")
    finally:
        add_log("Bot thread is stopping. Initiating browser cleanup...")
        logger.info("Bot logic thread finalizing.")
        if game_controller:
            ss_final_cleanup = take_screenshot(game_controller, "bot_final_cleanup_state")
            if ss_final_cleanup: add_log(f"Final screenshot before browser close: {ss_final_cleanup}")
            try:
                game_controller.close() # Ensure browser is closed
                add_log("Browser closed by GameController.")
            except Exception as e_gc_close:
                add_log(f"Error during GameController.close(): {type(e_gc_close).__name__} - {e_gc_close}")
                logger.error(f"Error during GameController.close() in bot_logic_thread_func finally block: {e_gc_close}", exc_info=True)
        else:
            add_log("GameController was not initialized, no browser to close.")
            
        update_status({"current_action": "Bot stopped.", "last_result": "N/A", "consecutive_losses": 0, "current_bet_amount": 0, "player_balance": "N/A"})
        bot_state["is_running"] = False
        bot_state["thread"] = None # Clear the thread object from state
        add_log("Bot thread finished execution.")
        logger.info("Bot logic thread finished.")

# --- Flask Routes ---
@app.route('/')
def index():
    logger.debug("Serving index.html via / route")
    return render_template('index.html')

@app.route('/start_bot', methods=['POST'])
def start_bot_route():
    global bot_state
    logger.info("==> Received POST request to /start_bot")
    if bot_state["is_running"]:
        logger.warning("Attempted to start bot via /start_bot, but bot is already running.")
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    data = request.get_json()
    if not data:
        logger.error("/start_bot request body is not JSON or is empty.")
        return jsonify({"status": "error", "message": "Request must be JSON and contain credentials."}), 400
        
    # Log the entire received payload for easier debugging of UI-sent data
    logger.info(f"/start_bot received data payload: {data}")
        
    username = data.get('username')
    password = data.get('password')
    preferred_bet = data.get('preferred_bet', 'auto') # Get preferred_bet from UI, default to 'auto'

    logger.info(f"Attempting to start bot with username: {'***' if username else 'None'}, preferred_bet: {preferred_bet}")

    bot_state["is_running"] = True
    bot_state["logs"] = [f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Bot start initiated by web request (Preference: {preferred_bet})..."] 
    bot_state["status"] = {"current_action": "Starting...", "last_result": "N/A", "consecutive_losses": 0, "current_bet_amount": 0, "player_balance": "N/A"}
    bot_state["latest_screenshot_filename"] = None # Reset screenshot on start
    bot_state["stop_event"].clear() # Ensure stop event is clear before starting new thread
    
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    # Create and start a new thread instance, passing preferred_bet
    bot_state["thread"] = threading.Thread(target=bot_logic_thread_func, 
                                           args=(config_path, username, password, preferred_bet), 
                                           name="BotLogicThread")
    bot_state["thread"].daemon = True 
    bot_state["thread"].start()
    
    logger.info("<== /start_bot: Bot start process initiated. Returning success.")
    return jsonify({"status": "success", "message": "Bot start initiated."})

@app.route('/stop_bot', methods=['POST'])
def stop_bot_route():
    global bot_state
    logger.info("==> Received POST request to /stop_bot")
    
    if not bot_state["is_running"]:
        logger.warning("Attempted to stop bot via /stop_bot, but bot is not marked as running.")
        # If thread object exists and is alive, something is inconsistent. Try to stop it anyway.
        if bot_state["thread"] and bot_state["thread"].is_alive():
            logger.warning("Bot state is_running=False, but thread is alive. Attempting to set stop_event.")
            bot_state["stop_event"].set()
            logger.info("<== /stop_bot: Bot not marked running, but stop signal sent. Returning warning.")
            return jsonify({"status": "warning", "message": "Bot not marked running, but stop signal sent to active thread."}), 202 # Accepted
        return jsonify({"status": "error", "message": "Bot is not currently running."}), 400

    if not bot_state["thread"] or not bot_state["thread"].is_alive():
        logger.warning("Attempted to stop bot, but thread is not active or missing. Resetting is_running state.")
        add_log("Bot was marked running but its thread was not active/found. Resetting state.") # Clarify message
        bot_state["is_running"] = False
        bot_state["thread"] = None 
        update_status({"current_action": "Bot stopped (inactive/missing thread)."})
        return jsonify({"status": "error", "message": "Bot thread not active or found. State reset."}), 400

    add_log("Stop signal received by /stop_bot route. Relaying to bot thread...")
    logger.info("Setting stop_event for bot thread via /stop_bot route.")
    bot_state["stop_event"].set()
    
    # Do not join the thread here, as it can make the HTTP request hang.
    # The bot thread's finally block will update is_running state.
    # The UI will reflect the "stopping" state via logs and then "stopped" once the thread finishes.
    logger.info("<== /stop_bot: Stop signal sent. Bot shutting down. Returning success.")
    return jsonify({"status": "success", "message": "Stop signal sent. Bot is shutting down."})

@app.route('/update_manual_status', methods=['POST'])
def update_manual_status_route():
    global bot_state
    logger.info("==> Received POST request to /update_manual_status")

    if bot_state["is_running"]:
        logger.warning("Attempt to manually update status while bot is running. This might be overwritten or cause inconsistencies.")
        # Allow update but with a warning, or disallow completely if preferred.
        # For now, allow but log.

    data = request.get_json()
    if not data:
        logger.error("/update_manual_status request body is not JSON or is empty.")
        return jsonify({"status": "error", "message": "Request must be JSON."}), 400

    updated_fields = []
    if 'current_action' in data:
        bot_state["status"]["current_action"] = str(data['current_action'])
        updated_fields.append("current_action")
    if 'consecutive_losses' in data and isinstance(data['consecutive_losses'], int) and data['consecutive_losses'] >= 0:
        bot_state["status"]["consecutive_losses"] = data['consecutive_losses']
        updated_fields.append("consecutive_losses")
    if 'current_bet_amount' in data and isinstance(data['current_bet_amount'], (int, float)) and data['current_bet_amount'] >= 0:
        bot_state["status"]["current_bet_amount"] = float(data['current_bet_amount'])
        updated_fields.append("current_bet_amount")

    log_msg = f"Manual status update received for: {', '.join(updated_fields) or 'No valid fields'}. New status: {bot_state['status']}"
    add_log(log_msg) # This also logs to console via logger.info
    logger.info(f"<== /update_manual_status: {log_msg}")
    return jsonify({"status": "success", "message": f"Bot status fields ({', '.join(updated_fields)}) updated."})

@app.route('/get_updates')
def get_updates_route():
    # This route is called frequently, so keep logging minimal unless debugging specific update issues.
    # logger.debug("==> Received GET request to /get_updates")
    return jsonify({
        "is_running": bot_state["is_running"],
        "logs": list(bot_state["logs"]), # Return a copy
        "status": dict(bot_state["status"]), # Return a copy
        "screenshot_filename": bot_state["latest_screenshot_filename"]
    })

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    logger.debug(f"==> Serving screenshot: {filename} from {SCREENSHOT_DIR}")
    response = send_from_directory(SCREENSHOT_DIR, filename, as_attachment=False)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/favicon.ico')
def favicon():
    logger.debug("==> Favicon.ico request received.")
    return '', 204 

@app.route('/ping')
def ping():
    logger.debug("==> Ping request received, responding pong.")
    return "pong"

if __name__ == '__main__':
    config_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    if not os.path.exists(config_file_path):
        critical_msg = f"'config.ini' not found at {config_file_path}"
        logger.critical(critical_msg)
        sys.stdout.write(f"CRITICAL: {critical_msg}\n")
        sys.stdout.write("Please create 'config.ini'. Example:\n")
        sys.stdout.write("""
[SETTINGS]
browser = chrome
login_url = https://www.unibet.nl/login
game_url = https://www.unibet.nl/play/dragon-tiger#playforreal
chromedriver_path = /usr/local/bin/chromedriver # Optional: Set to your chromedriver path, or leave blank/remove for Selenium Manager

[BETTING]
base_amount = 1.0
wait_time_between_bets = 10
max_consecutive_losses = 5
preferred_side = dragon # Can be 'dragon', 'tiger', or 'auto'
strategy = Martingale

[BROWSER_ADVANCED]
user_data_directory_strategy = temp # Options: temp, persistent, none. 'temp' creates a new profile each time and deletes it on close. 'persistent' reuses a profile in the project directory. 'none' lets Selenium manage (usually temp).
persistent_user_data_path = chrome_bot_profile # Used only if user_data_directory_strategy = persistent. Path relative to project root.
chromedriver_log_path = logs/chromedriver.log # Path for verbose chromedriver logs, relative to project root.
\n""")
        sys.exit(1)
    
    logger.info("Starting DragonTigerBot Flask Web Application...")
    # The WERKZEUG_RUN_MAIN check is to prevent webbrowser.open from running twice when Flask's reloader is active.
    # Since use_reloader=False, this check might be less critical but doesn't hurt.
    if not os.environ.get("WERKZEUG_RUN_MAIN"): 
        try:
            logger.info("Attempting to open web browser to http://127.0.0.1:5002/") # Changed port
            webbrowser.open('http://127.0.0.1:5002/') # Changed port
        except Exception as e_wb:
            logger.warning(f"Could not open web browser automatically: {e_wb}. Please navigate manually.")

    # use_reloader=False is important for threaded applications to avoid issues
    # with threads being duplicated or not managed correctly by the reloader,
    # and to prevent the bot logic from running multiple times on startup.
    app.run(debug=True, host='0.0.0.0', port=5002, use_reloader=False) # Changed port
