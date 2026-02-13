"""
SENTINEL Cortex — Swing Strategy
══════════════════════════════════
Estrategia de Swing Trading: opera en marcos temporales de horas/días.
"""

from cortex.agents.base_agent import BaseAgent

HOLD = 0
BUY = 1
SELL = 2


class SwingStrategy(BaseAgent):
    """
    Swing Trading basado en tendencia + sentimiento.

    Reglas:
    - Compra cuando precio cruza SMA(20) hacia arriba + sentimiento positivo
    - Vende cuando precio cruza SMA(20) hacia abajo o stop-loss
    - Stop-loss: -5% desde entrada
    - Take-profit: +10% desde entrada
    """

    def __init__(
        self,
        sma_period: int = 20,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        sentiment_threshold: float = 0.1,
    ):
        super().__init__(name="Swing")
        self.sma_period = sma_period
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.sentiment_threshold = sentiment_threshold
        self._entry_price = 0.0
        self._reasoning = ""

    def decide(self, observation: dict) -> int:
        self._step_count += 1

        prices = observation.get("prices")
        if prices is None or len(prices) < self.sma_period:
            self._reasoning = "Datos insuficientes"
            return HOLD

        current_price = observation.get("current_price", prices[-1, 3])
        position = observation.get("position", 0.0)
        has_position = position > 0
        sentiment = observation.get("sentiment", 0.0)
        closes = prices[:, 3]

        sma = float(closes[-self.sma_period:].mean())

        # --- Si tenemos posición: verificar stop-loss / take-profit ---
        if has_position and self._entry_price > 0:
            pnl_pct = (current_price - self._entry_price) / self._entry_price

            if pnl_pct <= -self.stop_loss_pct:
                self._reasoning = f"Stop-Loss: PnL={pnl_pct:.1%} ≤ -{self.stop_loss_pct:.0%}"
                self._entry_price = 0.0
                return SELL

            if pnl_pct >= self.take_profit_pct:
                self._reasoning = f"Take-Profit: PnL={pnl_pct:.1%} ≥ +{self.take_profit_pct:.0%}"
                self._entry_price = 0.0
                return SELL

            # Vender si precio cruza SMA hacia abajo
            if current_price < sma * 0.98:  # 2% debajo de SMA
                self._reasoning = f"Precio ${current_price:.0f} < SMA20 ${sma:.0f} — tendencia bajista"
                self._entry_price = 0.0
                return SELL

        # --- Si NO tenemos posición: buscar entrada ---
        if not has_position:
            # Precio por encima de SMA + sentimiento positivo
            if current_price > sma and sentiment >= self.sentiment_threshold:
                self._reasoning = (
                    f"Entrada: Precio ${current_price:.0f} > SMA20 ${sma:.0f} "
                    f"+ Sent={sentiment:.2f}"
                )
                self._entry_price = current_price
                return BUY

            # Precio rebota desde SMA (soporte)
            if 0.98 * sma <= current_price <= 1.01 * sma and sentiment > 0:
                self._reasoning = f"Rebote en SMA20: ${current_price:.0f} ≈ ${sma:.0f}"
                self._entry_price = current_price
                return BUY

        self._reasoning = f"HOLD | Price=${current_price:.0f} | SMA20=${sma:.0f} | Sent={sentiment:.2f}"
        return HOLD

    def reset(self):
        super().reset()
        self._entry_price = 0.0
        self._reasoning = ""

    def get_reasoning(self) -> str:
        return self._reasoning
