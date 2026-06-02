"""battery: arbitrage optimisation (perfect-foresight LP and rolling-horizon MPC)."""

from .arbitrage import BatteryParams, load_prices, solve_arbitrage

__all__ = ["BatteryParams", "load_prices", "solve_arbitrage"]
