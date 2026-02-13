"""
SENTINEL Cortex — Metrics Engine
══════════════════════════════════
Cálculo de métricas de rendimiento para backtesting.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BacktestResult:
    """Resultado completo de un backtest."""
    # Identificación
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str

    # Performance
    initial_capital: float
    final_value: float
    total_pnl: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int

    # Trading
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float

    # Datos completos
    equity_curve: Optional[List[float]] = None
    trade_log: Optional[pd.DataFrame] = None

    def __repr__(self):
        return (
            f"BacktestResult(\n"
            f"  strategy={self.strategy_name}, {self.symbol}\n"
            f"  period={self.start_date} → {self.end_date}\n"
            f"  PnL=${self.total_pnl:+.2f} ({self.total_return_pct:+.1f}%)\n"
            f"  Sharpe={self.sharpe_ratio:.2f}, MaxDD={self.max_drawdown_pct:.1f}%\n"
            f"  Trades={self.total_trades}, WinRate={self.win_rate:.1f}%\n"
            f")"
        )

    def to_dict(self) -> dict:
        """Convierte a diccionario (para JSON/DynamoDB)."""
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_value": round(self.final_value, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 4),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
        }


class MetricsEngine:
    """Calcula métricas de rendimiento de trading."""

    RISK_FREE_RATE = 0.05  # 5% anual (aprox bonos del tesoro US)
    TRADING_DAYS_PER_YEAR = 365  # Crypto opera 24/7

    @staticmethod
    def calculate_returns(equity_curve: List[float]) -> np.ndarray:
        """Calcula retornos porcentuales diarios."""
        values = np.array(equity_curve)
        if len(values) < 2:
            return np.array([0.0])
        returns = np.diff(values) / values[:-1]
        return returns

    @classmethod
    def sharpe_ratio(cls, equity_curve: List[float]) -> float:
        """
        Calcula el Sharpe Ratio anualizado.

        Sharpe = (mean_return - risk_free_daily) / std_return * sqrt(365)
        """
        returns = cls.calculate_returns(equity_curve)
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0

        daily_rf = cls.RISK_FREE_RATE / cls.TRADING_DAYS_PER_YEAR
        excess_returns = returns - daily_rf
        sharpe = (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(
            cls.TRADING_DAYS_PER_YEAR
        )
        return float(sharpe)

    @staticmethod
    def max_drawdown(equity_curve: List[float]) -> tuple:
        """
        Calcula el Maximum Drawdown.

        Returns:
            (max_dd_pct, duration_days)
        """
        values = np.array(equity_curve)
        if len(values) < 2:
            return 0.0, 0

        peak = values[0]
        max_dd = 0.0
        dd_start = 0
        max_dd_duration = 0
        current_dd_start = 0

        for i, val in enumerate(values):
            if val >= peak:
                peak = val
                current_dd_start = i
            else:
                dd = (peak - val) / peak
                if dd > max_dd:
                    max_dd = dd
                    dd_start = current_dd_start
                    max_dd_duration = i - current_dd_start

        return float(max_dd * 100), max_dd_duration  # En porcentaje

    @staticmethod
    def analyze_trades(trade_pnls: List[float]) -> dict:
        """
        Analiza la distribución de trades.

        Args:
            trade_pnls: Lista de PnL por trade

        Returns:
            Dict con métricas de trades
        """
        if not trade_pnls:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
            }

        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p <= 0]

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0

        return {
            "total_trades": len(trade_pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": (len(wins) / len(trade_pnls) * 100) if trade_pnls else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
            "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
            "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        }

    @classmethod
    def calculate_all(
        cls,
        strategy_name: str,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        equity_curve: List[float],
        trade_pnls: List[float],
        trade_log: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        Calcula todas las métricas y retorna un BacktestResult.

        Args:
            strategy_name: Nombre de la estrategia
            symbol: Símbolo del activo
            start_date: Fecha inicio
            end_date: Fecha fin
            initial_capital: Capital inicial
            equity_curve: Lista de valores del portfolio por timestamp
            trade_pnls: Lista de PnL por trade round-trip
            trade_log: DataFrame con detalles de cada trade

        Returns:
            BacktestResult con todas las métricas
        """
        final_value = equity_curve[-1] if equity_curve else initial_capital
        total_pnl = final_value - initial_capital
        total_return_pct = (total_pnl / initial_capital) * 100

        sharpe = cls.sharpe_ratio(equity_curve)
        max_dd_pct, max_dd_duration = cls.max_drawdown(equity_curve)
        trade_stats = cls.analyze_trades(trade_pnls)

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_value=final_value,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration_days=max_dd_duration,
            total_trades=trade_stats["total_trades"],
            winning_trades=trade_stats["winning_trades"],
            losing_trades=trade_stats["losing_trades"],
            win_rate=trade_stats["win_rate"],
            profit_factor=trade_stats["profit_factor"],
            avg_win=trade_stats["avg_win"],
            avg_loss=trade_stats["avg_loss"],
            equity_curve=equity_curve,
            trade_log=trade_log,
        )
