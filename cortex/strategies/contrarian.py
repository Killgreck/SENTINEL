"""
SENTINEL Cortex — Contrarian Strategy ("The Contrarian" / Judo de Mercado)
═══════════════════════════════════════════════════════════════════════════
Detecta movimientos de manipulación (Pump & Dump) y opera en dirección INVERSA.

Hipótesis: Las noticias falsas o exageradas causan spikes que se revierten.
Mecánica: Detectar spike → Verificar manipulación → Operar INVERSO a la masa.
"""

import numpy as np
from cortex.agents.base_agent import BaseAgent

HOLD = 0
BUY = 1
SELL = 2


class ContrarianStrategy(BaseAgent):
    """
    Estrategia Contrarian para detección de manipulación.

    Flujo:
    1. Detectar spike de precio (>threshold%) en ventana corta
    2. Verificar si volumen es anormalmente alto (>volume_multiplier × avg)
    3. Si sentimiento es extremo + spike → probable manipulación
    4. Operar INVERSO: si pump → SELL, si dump → BUY
    5. Aplicar risk management estricto (max exposure, time limit)
    """

    def __init__(
        self,
        price_spike_threshold: float = 0.03,  # 3% en ventana corta
        volume_multiplier: float = 3.0,        # 3x volumen promedio
        sentiment_extreme: float = 0.5,        # Sentimiento >0.5 o <-0.5
        max_hold_periods: int = 5,             # Máximo de periodos holding
        stop_loss_pct: float = 0.03,           # 3% stop-loss (más ajustado)
    ):
        super().__init__(name="Contrarian")
        self.price_spike_threshold = price_spike_threshold
        self.volume_multiplier = volume_multiplier
        self.sentiment_extreme = sentiment_extreme
        self.max_hold_periods = max_hold_periods
        self.stop_loss_pct = stop_loss_pct

        self._entry_price = 0.0
        self._hold_counter = 0
        self._reasoning = ""
        self._position_direction = None  # "contrarian_long" o "contrarian_short"

    def decide(self, observation: dict) -> int:
        self._step_count += 1

        prices = observation.get("prices")
        if prices is None or len(prices) < 10:
            self._reasoning = "Datos insuficientes"
            return HOLD

        current_price = observation.get("current_price", prices[-1, 3])
        position = observation.get("position", 0.0)
        has_position = position > 0
        sentiment = observation.get("sentiment", 0.0)
        closes = prices[:, 3]
        volumes = prices[:, 4]

        # --- GESTIÓN DE POSICIÓN EXISTENTE ---
        if has_position:
            self._hold_counter += 1
            pnl_pct = (current_price - self._entry_price) / self._entry_price

            # Stop-loss
            if pnl_pct <= -self.stop_loss_pct:
                self._reasoning = f"Contrarian Stop-Loss: PnL={pnl_pct:.1%}"
                self._reset_position()
                return SELL

            # Time-based exit (evitar quedarse atrapado)
            if self._hold_counter >= self.max_hold_periods:
                self._reasoning = f"Contrarian Time-Exit: {self._hold_counter} periodos | PnL={pnl_pct:.1%}"
                self._reset_position()
                return SELL

            # Take-profit si se revirtió el spike
            if pnl_pct >= self.price_spike_threshold:
                self._reasoning = f"Contrarian Take-Profit: reversión detectada PnL={pnl_pct:.1%}"
                self._reset_position()
                return SELL

            self._reasoning = f"Contrarian HOLD ({self._hold_counter}/{self.max_hold_periods}) | PnL={pnl_pct:.1%}"
            return HOLD

        # --- DETECCIÓN DE ANOMALÍA ---
        spike_detected, spike_info = self._detect_spike(closes, volumes)

        if not spike_detected:
            self._reasoning = "Sin anomalía detectada"
            return HOLD

        # --- VERIFICAR MANIPULACIÓN ---
        is_manipulation = self._assess_manipulation(
            spike_info, sentiment
        )

        if not is_manipulation:
            self._reasoning = f"Spike detectado pero no parece manipulación | {spike_info['description']}"
            return HOLD

        # --- EJECUTAR CONTRARIAN ---
        spike_direction = spike_info["direction"]

        if spike_direction == "UP":
            # La masa está comprando (pump) → Nosotros NO compramos (esperamos dump)
            # En un exchange real haríamos short, aquí solo evitamos comprar
            self._reasoning = (
                f"🔄 CONTRARIAN: Pump detectado ({spike_info['pct_change']:.1%}) "
                f"+ Sent={sentiment:.2f} → NO entrar (esperar reversión)"
            )
            return HOLD

        elif spike_direction == "DOWN":
            # La masa está vendiendo (dump/pánico) → Nosotros COMPRAMOS
            self._reasoning = (
                f"🔄 CONTRARIAN: Dump detectado ({spike_info['pct_change']:.1%}) "
                f"+ Sent={sentiment:.2f} → BUY (contra el pánico)"
            )
            self._entry_price = current_price
            self._hold_counter = 0
            self._position_direction = "contrarian_long"
            return BUY

        return HOLD

    def _detect_spike(self, closes: np.ndarray, volumes: np.ndarray) -> tuple:
        """Detecta spikes de precio anormales."""
        if len(closes) < 5:
            return False, {}

        # Cambio de precio en último periodo
        pct_change = (closes[-1] - closes[-2]) / closes[-2]

        # Volumen promedio (últimos 20 periodos, excluyendo el actual)
        avg_volume = np.mean(volumes[-20:-1]) if len(volumes) > 20 else np.mean(volumes[:-1])
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        is_spike = (
            abs(pct_change) >= self.price_spike_threshold
            and volume_ratio >= self.volume_multiplier
        )

        info = {
            "pct_change": pct_change,
            "volume_ratio": volume_ratio,
            "direction": "UP" if pct_change > 0 else "DOWN",
            "description": (
                f"ΔPrice={pct_change:.1%}, Vol={volume_ratio:.1f}x"
            ),
        }

        return is_spike, info

    def _assess_manipulation(self, spike_info: dict, sentiment: float) -> bool:
        """
        Evalúa si el spike es probablemente manipulación.

        Indicadores de manipulación:
        - Sentimiento extremo (demasiado positivo durante pump)
        - Spike abrupto sin fundamentos previos
        """
        pct_change = spike_info["pct_change"]
        volume_ratio = spike_info["volume_ratio"]

        # Pump sospechoso: precio sube + sentimiento muy positivo
        if pct_change > 0 and sentiment > self.sentiment_extreme:
            return True

        # Dump sospechoso: precio baja + sentimiento muy negativo
        if pct_change < 0 and sentiment < -self.sentiment_extreme:
            return True

        # Volumen extremamente alto es sospechoso por sí solo
        if volume_ratio > self.volume_multiplier * 2:
            return True

        return False

    def _reset_position(self):
        """Reinicia estado de posición."""
        self._entry_price = 0.0
        self._hold_counter = 0
        self._position_direction = None

    def reset(self):
        super().reset()
        self._reset_position()
        self._reasoning = ""

    def get_reasoning(self) -> str:
        return self._reasoning
