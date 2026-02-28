"""
Binance Guard Agent – Safety-first wrapper around Binance API.
Loads credentials from .env, uses ccxt, and enforces balance checks before actions.
"""

import os
import time
from dataclasses import dataclass
from typing import Optional

import ccxt
from dotenv import load_dotenv

# Load environment variables from .env (never hardcode keys)
load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# Minimum account balance in USD below which all actions are blocked
MIN_BALANCE_USD = 10.0


@dataclass
class SafetyCheckResult:
    """Result of a safety check with pass/fail and performance metric."""

    passed: bool
    balance_usd: float
    elapsed_ms: float
    message: str


def create_binance_exchange() -> ccxt.binance:
    """Initialize Binance exchange via ccxt using credentials from .env."""
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        raise ValueError(
            "BINANCE_API_KEY and BINANCE_SECRET_KEY must be set in .env. "
            "Copy .env.example to .env and fill in your keys."
        )
    return ccxt.binance(
        {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET_KEY,
            "enableRateLimit": True,
        }
    )


class BinanceGuard:
    """
    Safety guard for Binance operations.
    Verifies account balance before allowing further actions.
    """

    def __init__(self, exchange: Optional[ccxt.binance] = None) -> None:
        self._exchange = exchange or create_binance_exchange()
        self._blocked = False  # Set to True when check_safety fails

    def check_safety(self) -> SafetyCheckResult:
        """
        Verify that account balance is greater than $10 (MIN_BALANCE_USD).
        If not, block all further actions and return a failed result.
        Returns a result with elapsed time in milliseconds.
        """
        start_ns = time.perf_counter_ns()

        try:
            balance = self._exchange.fetch_balance()
        except ccxt.AuthenticationError as e:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            return SafetyCheckResult(
                passed=False,
                balance_usd=0.0,
                elapsed_ms=elapsed_ms,
                message=f"Authentication failed: {e}",
            )
        except ccxt.ExchangeError as e:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            return SafetyCheckResult(
                passed=False,
                balance_usd=0.0,
                elapsed_ms=elapsed_ms,
                message=f"Exchange error during balance fetch: {e}",
            )

        # Use USDT total as proxy for USD balance (1 USDT ≈ 1 USD)
        usdt = balance.get("USDT") or {}
        total_usdt = float(usdt.get("total") or 0)
        balance_usd = total_usdt

        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        if balance_usd <= MIN_BALANCE_USD:
            self._blocked = True
            return SafetyCheckResult(
                passed=False,
                balance_usd=balance_usd,
                elapsed_ms=elapsed_ms,
                message=f"Blocked: account balance ${balance_usd:.2f} is not greater than ${MIN_BALANCE_USD}. No further actions allowed.",
            )

        return SafetyCheckResult(
            passed=True,
            balance_usd=balance_usd,
            elapsed_ms=elapsed_ms,
            message=f"Safety check passed. Balance: ${balance_usd:.2f}, check took {elapsed_ms:.2f} ms.",
        )

    @property
    def is_blocked(self) -> bool:
        """True if a previous check_safety failed and actions are blocked."""
        return self._blocked

    def ensure_safe(self) -> SafetyCheckResult:
        """
        Run check_safety and raise if blocked. Use before any trade or sensitive action.
        """
        result = self.check_safety()
        if not result.passed:
            raise RuntimeError(result.message)
        return result


if __name__ == "__main__":
    guard = BinanceGuard()
    result = guard.check_safety()
    print(f"Passed: {result.passed}")
    print(f"Balance (USD): ${result.balance_usd:.2f}")
    print(f"Safety check took: {result.elapsed_ms:.2f} ms")
    print(f"Message: {result.message}")
