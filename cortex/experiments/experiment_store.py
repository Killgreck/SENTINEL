"""
SENTINEL — Experiment Store (Fase 4)
═════════════════════════════════════
Almacena resultados de experimentos en JSON local + DynamoDB opcional.

Cada experimento tiene:
  - ID único (UUID)
  - Config usada (agente, símbolo, params)
  - Métricas resultantes (Sharpe, PnL, Score, etc.)
  - Timestamp
"""

import os
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "experiments")


@dataclass
class ExperimentResult:
    """Resultado completo de un experimento."""
    experiment_id: str
    timestamp: str
    agent_name: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    # Config
    initial_capital: float
    fee_rate: float
    slippage: float
    hold_penalty_rate: float
    risk_per_trade_pct: float
    # Métricas
    final_value: float
    total_pnl: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    profit_factor: float
    score_final: float
    total_hold_penalty: float
    # Extras
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ExperimentStore:
    """
    Almacena y recupera resultados de experimentos.

    Modos:
    - local: JSON files en results/experiments/
    - dynamodb: Tabla DynamoDB (requiere AWS configurado)
    """

    def __init__(self, mode: str = "local", table_name: str = "sentinel-experiments"):
        self.mode = mode
        self.table_name = table_name
        self._dynamodb = None

        os.makedirs(RESULTS_DIR, exist_ok=True)

        if mode == "dynamodb":
            self._init_dynamodb()

    def _init_dynamodb(self):
        """Inicializa conexión a DynamoDB."""
        try:
            import boto3
            self._dynamodb = boto3.resource("dynamodb")
            # Crear tabla si no existe
            self._ensure_table()
        except Exception as e:
            print(f"  ⚠️  DynamoDB no disponible ({e}), usando local")
            self.mode = "local"

    def _ensure_table(self):
        """Crea la tabla DynamoDB si no existe."""
        try:
            table = self._dynamodb.Table(self.table_name)
            table.load()
        except Exception:
            try:
                table = self._dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "experiment_id", "KeyType": "HASH"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "experiment_id", "AttributeType": "S"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                table.wait_until_exists()
                print(f"  ✅ Tabla DynamoDB '{self.table_name}' creada")
            except Exception as e:
                print(f"  ⚠️  No se pudo crear tabla: {e}")

    def save(self, result: ExperimentResult) -> str:
        """Guarda un resultado de experimento."""
        data = result.to_dict()

        # Siempre guardar localmente
        filepath = os.path.join(RESULTS_DIR, f"{result.experiment_id}.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Guardar en DynamoDB si aplica
        if self.mode == "dynamodb" and self._dynamodb:
            try:
                table = self._dynamodb.Table(self.table_name)
                # DynamoDB no soporta float, convertir a Decimal
                from decimal import Decimal
                ddb_data = json.loads(json.dumps(data, default=str), parse_float=Decimal)
                table.put_item(Item=ddb_data)
            except Exception as e:
                print(f"  ⚠️  Error guardando en DynamoDB: {e}")

        return result.experiment_id

    def load(self, experiment_id: str) -> Optional[ExperimentResult]:
        """Carga un experimento por ID."""
        filepath = os.path.join(RESULTS_DIR, f"{experiment_id}.json")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                data = json.load(f)
            return ExperimentResult(**data)
        return None

    def list_all(self) -> List[ExperimentResult]:
        """Lista todos los experimentos guardados localmente."""
        results = []
        if not os.path.exists(RESULTS_DIR):
            return results

        for filename in sorted(os.listdir(RESULTS_DIR)):
            if filename.endswith(".json"):
                filepath = os.path.join(RESULTS_DIR, filename)
                with open(filepath, "r") as f:
                    data = json.load(f)
                try:
                    results.append(ExperimentResult(**data))
                except TypeError:
                    pass  # Skip malformed files
        return results

    def get_leaderboard(self, sort_by: str = "sharpe_ratio", top_n: int = 20) -> list:
        """Genera un ranking de experimentos."""
        results = self.list_all()
        if not results:
            return []

        results.sort(key=lambda r: getattr(r, sort_by, 0), reverse=True)
        return results[:top_n]

    def delete(self, experiment_id: str):
        """Elimina un experimento."""
        filepath = os.path.join(RESULTS_DIR, f"{experiment_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

    def clear_all(self):
        """Elimina todos los experimentos locales."""
        if os.path.exists(RESULTS_DIR):
            for f in os.listdir(RESULTS_DIR):
                if f.endswith(".json"):
                    os.remove(os.path.join(RESULTS_DIR, f))


def generate_experiment_id() -> str:
    """Genera un ID único para el experimento."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    return f"exp_{ts}_{short_uuid}"
