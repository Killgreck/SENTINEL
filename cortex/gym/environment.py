"""
SENTINEL Cortex — Trading Environment
═══════════════════════════════════════
Entorno de simulación de trading compatible con la API de Gymnasium.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, Any

from cortex.gym.exchange_mock import ExchangeMock
from cortex.gym.data_loader import DataLoader


# Acciones
HOLD = 0
BUY = 1
SELL = 2
ACTION_NAMES = {HOLD: "HOLD", BUY: "BUY", SELL: "SELL"}


class TradingEnvironment:
    """
    Entorno de trading para backtesting.

    Sigue la API de Gymnasium (reset/step) sin requerir la dependencia.
    Cada step avanza un timestep en los datos históricos.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float = 100.0,
        fee_rate: float = 0.001,
        slippage: float = 0.0005,
        risk_per_trade_pct: float = 0.1,
        window_size: int = 20,
        symbol: str = "BTCUSDT",
        hold_penalty_rate: float = 0.05,
    ):
        """
        Args:
            data: DataFrame con columnas [timestamp, open, high, low, close, volume, sentiment_score]
            initial_capital: Capital inicial en USD
            fee_rate: Fee del exchange (0.001 = 0.1%)
            slippage: Slippage simulado (0.0005 = 0.05%)
            risk_per_trade_pct: % del capital a arriesgar por trade
            window_size: Número de velas históricas en la observación
            symbol: Símbolo del activo
            hold_penalty_rate: % de cash penalizado por cada HOLD (0.05 = 5%)
        """
        self.data = data.reset_index(drop=True)
        self.initial_capital = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.window_size = window_size
        self.symbol = symbol
        self.hold_penalty_rate = hold_penalty_rate

        self.exchange = ExchangeMock(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage=slippage,
        )

        # Estado interno
        self.current_step: int = 0
        self.done: bool = False
        self.equity_curve: list = []
        self.trade_pnls: list = []
        self.step_log: list = []

        # Score system (0-1000): decreases on losses/penalties, increases on gains
        self.score: float = 1000.0
        self.score_history: list = []
        self.total_hold_penalty: float = 0.0

        # Precomputar returns para observación
        self.data["returns"] = self.data["close"].pct_change().fillna(0)

    @property
    def total_steps(self) -> int:
        return len(self.data)

    def reset(self) -> dict:
        """Reinicia el entorno. Retorna la observación inicial."""
        self.current_step = self.window_size  # Empezar después de la ventana
        self.done = False
        self.exchange.reset()
        self.equity_curve = []
        self.trade_pnls = []
        self.step_log = []
        self.score = 1000.0
        self.score_history = []
        self.total_hold_penalty = 0.0

        return self._get_observation()

    def step(self, action: int) -> Tuple[dict, float, bool, bool, dict]:
        """
        Ejecuta un paso en el entorno.

        Args:
            action: 0=HOLD, 1=BUY, 2=SELL

        Returns:
            (observation, reward, terminated, truncated, info)
        """
        if self.done:
            raise RuntimeError("Environment is done. Call reset().")

        row = self.data.iloc[self.current_step]
        price = row["close"]
        timestamp = row["timestamp"]
        prev_value = self.exchange.get_portfolio_value({self.symbol: price})

        # Ejecutar acción
        fill = None
        action_name = ACTION_NAMES.get(action, "UNKNOWN")
        hold_penalty = 0.0

        if action == HOLD:
            # ═══ HOLD PENALTY: 5% del cash por cada step sin operar ═══
            penalty = self.exchange.cash * self.hold_penalty_rate
            if penalty > 0.01:  # Mínimo $0.01 para aplicar
                self.exchange.cash -= penalty
                self.total_hold_penalty += penalty
                hold_penalty = penalty

        elif action == BUY:
            # Comprar con risk_per_trade_pct del portfolio
            trade_amount = prev_value * self.risk_per_trade_pct
            fill = self.exchange.buy(
                self.symbol, trade_amount, price, timestamp
            )

        elif action == SELL:
            # Vender toda la posición
            fill = self.exchange.sell(
                self.symbol, quantity=None, market_price=price, timestamp=timestamp
            )
            if fill:
                # Calcular PnL del round-trip
                pos = self.exchange.positions.get(self.symbol)
                self.trade_pnls.append(fill.total_cost - fill.quantity * fill.price)

        # Calcular nuevo valor del portfolio
        current_value = self.exchange.get_portfolio_value({self.symbol: price})
        self.equity_curve.append(current_value)

        # Reward = cambio porcentual del portfolio
        reward = (current_value - prev_value) / prev_value if prev_value > 0 else 0.0

        # ═══ SCORE SYSTEM: sube con ganancias, baja con pérdidas/penalties ═══
        if reward > 0:
            self.score += reward * 100  # Ganancias incrementan score
        elif reward < 0:
            self.score += reward * 150  # Pérdidas penalizan 1.5x más
        if hold_penalty > 0:
            self.score -= (hold_penalty / self.initial_capital) * 50
        self.score = max(0.0, min(1000.0, self.score))  # Clamp 0-1000
        self.score_history.append(self.score)

        # Log
        self.step_log.append({
            "timestamp": timestamp,
            "action": action_name,
            "price": price,
            "portfolio_value": current_value,
            "cash": self.exchange.cash,
            "position_qty": (
                self.exchange.positions[self.symbol].quantity
                if self.symbol in self.exchange.positions
                else 0.0
            ),
            "reward": reward,
            "score": self.score,
            "hold_penalty": hold_penalty,
            "sentiment": row.get("sentiment_score", 0.0),
        })

        # Avanzar
        self.current_step += 1
        terminated = self.current_step >= len(self.data) - 1
        self.done = terminated

        # Info adicional
        info = {
            "fill": fill,
            "portfolio_value": current_value,
            "score": self.score,
            "hold_penalty": hold_penalty,
            "total_hold_penalty": self.total_hold_penalty,
            "step": self.current_step,
            "total_steps": self.total_steps,
        }

        observation = self._get_observation() if not terminated else {}

        return observation, reward, terminated, False, info

    def _get_observation(self) -> dict:
        """Construye la observación actual para el agente."""
        idx = self.current_step

        # Ventana de precios OHLCV
        start = max(0, idx - self.window_size)
        window = self.data.iloc[start:idx]

        prices = window[["open", "high", "low", "close", "volume"]].values
        returns = window["returns"].values

        # Posición actual
        pos_qty = 0.0
        if self.symbol in self.exchange.positions:
            pos_qty = self.exchange.positions[self.symbol].quantity

        current_price = self.data.iloc[idx]["close"]
        portfolio_value = self.exchange.get_portfolio_value(
            {self.symbol: current_price}
        )

        # Sentimiento
        sentiment = self.data.iloc[idx].get("sentiment_score", 0.0)

        return {
            "prices": prices,               # (window_size, 5) OHLCV
            "returns": returns,              # (window_size,) retornos
            "current_price": current_price,  # Precio actual
            "position": pos_qty,             # Cantidad de activo
            "portfolio_value": portfolio_value,
            "cash": self.exchange.cash,
            "sentiment": sentiment,
            "score": self.score,             # Score actual (0-1000)
            "timestamp": self.data.iloc[idx]["timestamp"],
            "step": idx,
        }

    def get_step_log_df(self) -> pd.DataFrame:
        """Retorna el log de pasos como DataFrame."""
        return pd.DataFrame(self.step_log)

    def render(self):
        """Imprime estado actual del entorno."""
        if self.current_step >= len(self.data):
            return

        row = self.data.iloc[self.current_step]
        price = row["close"]
        value = self.exchange.get_portfolio_value({self.symbol: price})
        summary = self.exchange.get_summary({self.symbol: price})

        print(
            f"  Step {self.current_step}/{self.total_steps} | "
            f"{row['timestamp']} | "
            f"Price: ${price:,.2f} | "
            f"Portfolio: ${value:.2f} | "
            f"Return: {summary['total_return_pct']:+.1f}%"
        )
