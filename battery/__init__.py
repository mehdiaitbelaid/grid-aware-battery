"""battery: arbitrage optimisation (perfect-foresight LP and rolling-horizon MPC)."""

from .arbitrage import BatteryParams, load_prices, solve_arbitrage
from .forecast import same_hour_average, persistence, perfect_window
from .mpc import run_mpc

__all__ = [
    "BatteryParams",
    "load_prices",
    "solve_arbitrage",
    "same_hour_average",
    "persistence",
    "perfect_window",
    "run_mpc",
]
