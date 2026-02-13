"""
SENTINEL Cortex — Buy & Hold Agent
════════════════════════════════════
Agente baseline: compra en el primer paso y mantiene hasta el final.
"""

from cortex.agents.base_agent import BaseAgent

HOLD = 0
BUY = 1
SELL = 2


class BuyHoldAgent(BaseAgent):
    """
    Estrategia Buy & Hold (baseline).

    Compra todo el capital en el primer paso y no hace nada más.
    Sirve como benchmark para comparar otras estrategias.
    """

    def __init__(self):
        super().__init__(name="BuyHold")
        self._has_bought = False

    def decide(self, observation: dict) -> int:
        self._step_count += 1

        if not self._has_bought:
            self._has_bought = True
            self._reasoning = "Primer paso: comprar y mantener"
            return BUY

        self._reasoning = "Mantener posición"
        return HOLD

    def reset(self):
        super().reset()
        self._has_bought = False
        self._reasoning = ""

    def get_reasoning(self) -> str:
        return self._reasoning
