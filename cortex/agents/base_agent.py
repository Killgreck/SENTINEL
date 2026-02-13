"""
SENTINEL Cortex — Base Agent
══════════════════════════════
Interfaz abstracta para todos los agentes de trading.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseAgent(ABC):
    """Clase base para todos los agentes de trading."""

    def __init__(self, name: str = "BaseAgent"):
        self.name = name
        self._step_count = 0

    @abstractmethod
    def decide(self, observation: dict) -> int:
        """
        Decide la acción a tomar basándose en la observación.

        Args:
            observation: Dict con precios, posición, sentimiento, etc.

        Returns:
            Acción: 0=HOLD, 1=BUY, 2=SELL
        """
        pass

    def reset(self):
        """Reinicia el estado interno del agente."""
        self._step_count = 0

    def get_reasoning(self) -> str:
        """Retorna la explicación de la última decisión (para logging)."""
        return ""

    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}')"
