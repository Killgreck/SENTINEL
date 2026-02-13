"""
SENTINEL Cortex — Statistical Agent
═════════════════════════════════════
Agente basado en indicadores técnicos (SMA crossover + RSI + Sentiment).
No requiere LLM — funciona como el "Fast Brain" del sistema dual.
"""

import numpy as np
from cortex.agents.base_agent import BaseAgent

HOLD = 0
BUY = 1
SELL = 2


class StatisticalAgent(BaseAgent):
    """
    Agente estadístico basado en indicadores técnicos.

    Señales:
    - SMA Crossover: SMA(10) cruza por encima de SMA(30) → BUY
    - RSI: RSI < 30 → BUY (sobreventa), RSI > 70 → SELL (sobrecompra)
    - Sentimiento: Amplifica la señal si coincide con el sentimiento
    """

    def __init__(
        self,
        sma_fast: int = 10,
        sma_slow: int = 30,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        sentiment_weight: float = 0.3,
    ):
        super().__init__(name="Statistical")
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.sentiment_weight = sentiment_weight
        self._reasoning = ""

    def decide(self, observation: dict) -> int:
        self._step_count += 1

        prices = observation.get("prices")
        if prices is None or len(prices) < self.sma_slow:
            self._reasoning = "Datos insuficientes para calcular indicadores"
            return HOLD

        # Extraer precios de cierre (columna index 3 = close)
        closes = prices[:, 3]

        # --- Calcular SMA ---
        sma_fast = np.mean(closes[-self.sma_fast:])
        sma_slow_val = np.mean(closes[-self.sma_slow:])

        # --- Calcular RSI ---
        rsi = self._calculate_rsi(closes, self.rsi_period)

        # --- Obtener sentimiento ---
        sentiment = observation.get("sentiment", 0.0)

        # --- Lógica de decisión ---
        signal_score = 0.0
        reasons = []

        # SMA Crossover
        if sma_fast > sma_slow_val:
            signal_score += 0.4
            reasons.append(f"SMA{self.sma_fast}({sma_fast:.0f}) > SMA{self.sma_slow}({sma_slow_val:.0f})")
        elif sma_fast < sma_slow_val:
            signal_score -= 0.4
            reasons.append(f"SMA{self.sma_fast}({sma_fast:.0f}) < SMA{self.sma_slow}({sma_slow_val:.0f})")

        # RSI
        if rsi < self.rsi_oversold:
            signal_score += 0.3
            reasons.append(f"RSI={rsi:.0f} (sobreventa)")
        elif rsi > self.rsi_overbought:
            signal_score -= 0.3
            reasons.append(f"RSI={rsi:.0f} (sobrecompra)")

        # Sentimiento
        if sentiment != 0.0:
            signal_score += sentiment * self.sentiment_weight
            reasons.append(f"Sentiment={sentiment:.2f}")

        # Posición actual
        has_position = observation.get("position", 0.0) > 0

        self._reasoning = " | ".join(reasons) + f" → Score={signal_score:.2f}"

        # Decisión final
        if signal_score > 0.3 and not has_position:
            self._reasoning += " → BUY"
            return BUY
        elif signal_score < -0.3 and has_position:
            self._reasoning += " → SELL"
            return SELL
        else:
            self._reasoning += " → HOLD"
            return HOLD

    def _calculate_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calcula el Relative Strength Index."""
        if len(closes) < period + 1:
            return 50.0  # Neutral

        deltas = np.diff(closes[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)

    def reset(self):
        super().reset()
        self._reasoning = ""

    def get_reasoning(self) -> str:
        return self._reasoning
