"""
SENTINEL Cortex — Exchange Mock
════════════════════════════════
Simula un exchange de criptomonedas (Binance) con fees y slippage realistas.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Fill:
    """Resultado de una operación ejecutada."""
    timestamp: datetime
    symbol: str
    side: str           # "BUY" o "SELL"
    quantity: float     # Cantidad del activo
    price: float        # Precio de ejecución (con slippage)
    fee: float          # Fee pagado en USD
    total_cost: float   # Costo total (quantity * price + fee)


@dataclass
class Position:
    """Posición abierta en un activo."""
    symbol: str
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    total_invested: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.quantity > 1e-10

    def value_at(self, current_price: float) -> float:
        """Valor de mercado de la posición."""
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """PnL no realizado."""
        if not self.is_open:
            return 0.0
        return (current_price - self.avg_entry_price) * self.quantity


class ExchangeMock:
    """
    Simulador de exchange con fees y slippage realistas.

    Simula el comportamiento de Binance:
    - Fee estándar: 0.1% por operación
    - Slippage: 0.05% simulado por impacto de mercado
    """

    def __init__(
        self,
        initial_capital: float = 100.0,
        fee_rate: float = 0.001,
        slippage: float = 0.0005,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage

        # Estado
        self.cash: float = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Fill] = []
        self.realized_pnl: float = 0.0

    def reset(self):
        """Reinicia el exchange al estado inicial."""
        self.cash = self.initial_capital
        self.positions = {}
        self.trade_history = []
        self.realized_pnl = 0.0

    def buy(
        self,
        symbol: str,
        usd_amount: float,
        market_price: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Fill]:
        """
        Ejecuta una orden de compra.

        Args:
            symbol: Símbolo del activo (e.g., "BTCUSDT")
            usd_amount: Monto en USD a invertir
            market_price: Precio de mercado actual
            timestamp: Timestamp del trade

        Returns:
            Fill con detalles de la operación, o None si no hay fondos
        """
        if usd_amount <= 0:
            return None

        # No gastar más de lo que tenemos
        usd_amount = min(usd_amount, self.cash)
        if usd_amount < 0.01:  # Mínimo $0.01
            return None

        # Aplicar slippage (compramos ligeramente más caro)
        execution_price = market_price * (1 + self.slippage)

        # Calcular fee
        fee = usd_amount * self.fee_rate

        # Cantidad efectiva después de fee
        effective_usd = usd_amount - fee
        quantity = effective_usd / execution_price

        # Actualizar cash
        self.cash -= usd_amount

        # Actualizar posición
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

        pos = self.positions[symbol]
        # Calcular nuevo precio promedio
        total_qty = pos.quantity + quantity
        if total_qty > 0:
            pos.avg_entry_price = (
                (pos.avg_entry_price * pos.quantity + execution_price * quantity)
                / total_qty
            )
        pos.quantity = total_qty
        pos.total_invested += effective_usd

        # Crear y registrar fill
        fill = Fill(
            timestamp=timestamp or datetime.now(),
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            price=execution_price,
            fee=fee,
            total_cost=usd_amount,
        )
        self.trade_history.append(fill)
        return fill

    def sell(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        market_price: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Fill]:
        """
        Ejecuta una orden de venta.

        Args:
            symbol: Símbolo del activo
            quantity: Cantidad a vender (None = vender todo)
            market_price: Precio de mercado actual
            timestamp: Timestamp del trade

        Returns:
            Fill con detalles, o None si no hay posición
        """
        if symbol not in self.positions or not self.positions[symbol].is_open:
            return None

        pos = self.positions[symbol]

        # Si no se especifica cantidad, vender todo
        if quantity is None:
            quantity = pos.quantity

        quantity = min(quantity, pos.quantity)
        if quantity < 1e-10:
            return None

        # Aplicar slippage (vendemos ligeramente más barato)
        execution_price = market_price * (1 - self.slippage)

        # Valor bruto de la venta
        gross_value = quantity * execution_price

        # Fee
        fee = gross_value * self.fee_rate

        # Valor neto
        net_value = gross_value - fee

        # PnL realizado
        cost_basis = pos.avg_entry_price * quantity
        trade_pnl = net_value - cost_basis
        self.realized_pnl += trade_pnl

        # Actualizar cash
        self.cash += net_value

        # Actualizar posición
        pos.quantity -= quantity
        if pos.quantity < 1e-10:
            pos.quantity = 0.0
            pos.avg_entry_price = 0.0
            pos.total_invested = 0.0

        fill = Fill(
            timestamp=timestamp or datetime.now(),
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            price=execution_price,
            fee=fee,
            total_cost=net_value,
        )
        self.trade_history.append(fill)
        return fill

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calcula el valor total del portfolio.

        Args:
            current_prices: Dict de {symbol: price}

        Returns:
            Valor total = cash + valor de todas las posiciones
        """
        total = self.cash
        for symbol, pos in self.positions.items():
            if pos.is_open and symbol in current_prices:
                total += pos.value_at(current_prices[symbol])
        return total

    def get_total_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """PnL no realizado total."""
        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.is_open and symbol in current_prices:
                total += pos.unrealized_pnl(current_prices[symbol])
        return total

    def get_summary(self, current_prices: Dict[str, float]) -> dict:
        """Resumen del estado del portfolio."""
        portfolio_value = self.get_portfolio_value(current_prices)
        return {
            "cash": round(self.cash, 2),
            "portfolio_value": round(portfolio_value, 2),
            "total_return_pct": round(
                (portfolio_value / self.initial_capital - 1) * 100, 2
            ),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(
                self.get_total_unrealized_pnl(current_prices), 2
            ),
            "total_trades": len(self.trade_history),
            "open_positions": {
                s: {
                    "qty": round(p.quantity, 8),
                    "avg_price": round(p.avg_entry_price, 2),
                    "current_value": round(
                        p.value_at(current_prices.get(s, 0)), 2
                    ),
                }
                for s, p in self.positions.items()
                if p.is_open
            },
        }

    def __repr__(self):
        return (
            f"ExchangeMock(cash=${self.cash:.2f}, "
            f"positions={len([p for p in self.positions.values() if p.is_open])}, "
            f"trades={len(self.trade_history)})"
        )
