# betting_logic.py

# --- DISCLAIMER ---
# Betting strategies are tools for managing bets and do not guarantee profit.
# Games of chance like Dragon Tiger have an inherent house edge.
# All betting systems carry risk, and you can lose your entire bankroll.
# Please gamble responsibly and be aware of the risks involved.


class BettingStrategy:
    def __init__(self, preferred_side='auto'): # Default to 'auto'
        self.history = []
        self.consecutive_losses = 0
        self.consecutive_wins = 0 # Added for strategies that might use it (e.g., Paroli)
        self.max_history_length = 50 # Max history items to keep
        # Ensure preferred_side is one of the valid options, default to 'auto'
        self.preferred_side = preferred_side.lower() if preferred_side.lower() in ['dragon', 'tiger', 'auto'] else 'auto'

    def analyze(self, game_state):
        """
        Decides which side to bet on.
        If preferred_side is 'dragon' or 'tiger', it returns that.
        If 'auto', it returns a default (e.g., 'dragon'), or subclasses can implement specific 'auto' logic.
        """
        if self.preferred_side == 'dragon':
            return 'dragon' # Always bet Dragon if preferred
        elif self.preferred_side == 'tiger':
            return 'tiger' # Always bet Tiger if preferred
        else: # 'auto'
            # Subclasses can override this for more complex 'auto' logic based on game_state
            # Default behavior for base class 'auto' is to return 'dragon'
            return 'dragon' # Default choice if preferred_side is 'auto' and strategy doesn't override

    def should_continue(self, max_losses):
        """Check if we should continue betting"""
        return self.consecutive_losses < max_losses

    def update_history(self, result):
        """Update betting history and consecutive win/loss counts."""
        # Ensure result is one of 'win', 'loss', 'tie' for consistent handling
        if result not in ['win', 'loss', 'tie']:
            # If an unknown result (e.g. 'dragon'/'tiger' directly from outcome), treat as 'loss' or handle as needed
            # For now, we assume 'win', 'loss', 'tie' is correctly determined before this call.
            pass # Or log a warning for unexpected result format if necessary

        if result == 'loss':
            self.consecutive_losses += 1
            self.consecutive_wins = 0 # Reset consecutive wins on a loss
        elif result == 'win':
            self.consecutive_losses = 0
            self.consecutive_wins += 1 # Track consecutive wins
        else: # 'tie'
             # For ties, typically the progression doesn't change.
             # Consecutive losses/wins are not reset by a tie in this base implementation.
             # Specific strategies can override this if they need different tie logic.
            pass # Consecutive losses/wins remain unchanged on a tie

        self.history.append(result)
        # Limit history size if needed
        if len(self.history) > self.max_history_length:
            self.history.pop(0)


    def get_bet_amount(self, base_amount):
        """
        Calculates the bet amount.
        Base strategy: always bet the base amount.
        Subclasses should override this for more complex logic.
        """
        return base_amount

class MartingaleStrategy(BettingStrategy):
    def __init__(self, preferred_side='auto'):
        super().__init__(preferred_side=preferred_side)

    def get_bet_amount(self, base_amount):
        """
        Martingale strategy: Double the bet after each loss, reset to base after a win.
        Ties do not change the progression (bet amount remains the same as the previous round).
        """
        # The base class update_history resets consecutive_losses on win/tie.
        # So, if consecutive_losses is 0, it means the last outcome was win or tie.
        if self.consecutive_losses == 0:
            return base_amount
        else: # Implies the last result was 'loss'
            # Cap the bet to avoid extremely large bets, e.g., max 7-8 losses
            # (2^7 = 128 * base_amount, 2^8 = 256 * base_amount)
            # This should ideally be configurable or tied to bankroll.
            # For now, let's cap the effect of consecutive_losses for Martingale.
            effective_losses = min(self.consecutive_losses, 8) # Cap at 8 doublings
            return base_amount * (2 ** effective_losses)

    # analyze and should_continue are inherited from BettingStrategy.
    # Martingale's 'auto' side choice defaults to 'dragon' via the base class.


class FibonacciStrategy(BettingStrategy):
    def __init__(self, preferred_side='auto'):
        super().__init__(preferred_side=preferred_side)
        self.fib_sequence = [1, 1] # Starting Fibonacci numbers for multipliers
        self.current_fib_index = 0 # Start at the beginning of the sequence

    def update_history(self, outcome):
        super().update_history(outcome) # Call base to update history list and basic win/loss counts
        if outcome == 'win':
            self.current_fib_index = 0 # Reset Fibonacci progression
        elif outcome == 'loss':
            # Advance in Fibonacci sequence, but don't exceed its length
            if self.current_fib_index < len(self.fib_sequence) - 1:
                self.current_fib_index += 1
            # If at the end of sequence, typically hold or reset (here, hold at last value)
        # On a 'tie', current_fib_index remains unchanged (no progression change)


    def get_bet_amount(self, base_amount):
        # Fibonacci bet amount logic is independent of preferred_side for choosing the side.
        # It depends on its own win/loss sequence for amount.
        # After a win, reset to the first element (or base_amount).
        # After a loss, move to the next element in the sequence.
        if self.consecutive_losses == 0: # This means last outcome was a win or it's the start
            # self.current_fib_index is reset in update_history on a win
            return base_amount # Or self.fib_sequence[0] * base_amount if fib starts > 1 unit

        # Ensure fib_sequence is long enough for the current index
        while self.current_fib_index >= len(self.fib_sequence):
            next_fib = self.fib_sequence[-1] + self.fib_sequence[-2]
            self.fib_sequence.append(next_fib)

        # Use current_fib_index which is managed by update_history
        # Ensure index is within bounds (should be handled by update_history, but belt+suspenders)
        idx = min(self.current_fib_index, len(self.fib_sequence) - 1)
        return self.fib_sequence[idx] * base_amount


    def analyze(self, game_state):
        # If preferred_side is 'dragon' or 'tiger', use that.
        if self.preferred_side in ['dragon', 'tiger']:
            return self.preferred_side
        else: # 'auto' logic for Fibonacci: Alternate bets.
            # This is a simple alternating 'auto' logic for Fibonacci
            if len(self.history) % 2 == 0: # Bet Dragon on even rounds (after 0, 2, 4... outcomes)
                return 'dragon'
            else:
                return 'tiger' # Bet Tiger on odd rounds (after 1, 3, 5... outcomes)


class DAlembertStrategy(BettingStrategy):
    def __init__(self, preferred_side='auto'):
        super().__init__(preferred_side=preferred_side)
        self.current_bet_unit_multiplier = 1 # Start with 1 unit multiplier

    def get_bet_amount(self, base_amount):
        # D'Alembert: Increase bet by one unit after a loss, decrease by one unit after a win.
        # Minimum bet is base_amount (1 unit).
        return self.current_bet_unit_multiplier * base_amount

    def update_history(self, result):
        super().update_history(result) # This updates consecutive_losses
        if result == 'win':
            self.current_bet_unit_multiplier = max(1, self.current_bet_unit_multiplier - 1) # Decrease by 1 unit, min 1
        elif result == 'loss':
            self.current_bet_unit_multiplier += 1 # Increase by 1 unit
        # On 'tie', current_bet_unit_multiplier remains unchanged.

    def analyze(self, game_state):
        # If preferred_side is 'dragon' or 'tiger', use that.
        if self.preferred_side in ['dragon', 'tiger']:
            return self.preferred_side
        else: # 'auto' logic for D'Alembert: Default to 'dragon' via base class.
            # A more complex D'Alembert 'auto' might bet on the side that won the last round,
            # but this requires parsing the actual winning side from game_state['history'],
            # which currently only stores 'win'/'loss'/'tie' relative to the bot's bet.
            return super().analyze(game_state) # Use base class 'auto' ('dragon')


class ParoliStrategy(BettingStrategy):
    """
    Paroli System (Positive Progression):
    - Start with a base bet.
    - After a win, double the bet.
    - After a loss, revert to the base bet.
    - Optionally, reset to base bet after a certain number of consecutive wins (e.g., 3).
    """
    def __init__(self, preferred_side='auto', wins_to_reset=3):
        super().__init__(preferred_side=preferred_side)
        self.wins_to_reset = wins_to_reset # Number of consecutive wins before resetting
        # self.current_bet_multiplier is not strictly needed as get_bet_amount can derive it
        # from self.consecutive_wins and self.wins_to_reset.

    def update_history(self, outcome):
        # Paroli's state depends on consecutive_wins, which is handled by the base class.
        super().update_history(outcome) # This updates self.consecutive_wins and self.consecutive_losses
        # No additional state update needed here for Paroli's core logic.

    def get_bet_amount(self, base_amount):
        # If no wins, or if win streak target met (consecutive_wins >= wins_to_reset)
        if self.consecutive_wins == 0 or self.consecutive_wins >= self.wins_to_reset:
            return base_amount
        else:
            # Double for each win in the current streak, up to wins_to_reset-1
            # e.g. 1st win -> bet 2*base, 2nd win -> bet 4*base
            # The multiplier is 2 raised to the power of the number of consecutive wins.
            return base_amount * (2 ** self.consecutive_wins)

    def should_continue(self, max_consecutive_losses_ignored):
        # Paroli doesn't typically have a max loss condition in its core logic,
        # as losses reset the progression. Bankroll management is external.
        # We can still use the max_losses parameter from config as a safety stop,
        # but it's less integral to the strategy itself than Martingale.
        # Let's use the base class check for consistency as a safety.
        return super().should_continue(max_consecutive_losses_ignored)

    # analyze is inherited from BettingStrategy.
    # Paroli's 'auto' side choice defaults to 'dragon' via the base class.
