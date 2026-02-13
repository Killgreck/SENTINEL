"""
SENTINEL Cortex — LLM Agent (Fase 3)
═════════════════════════════════════
Agente que usa LLMs (AWS Bedrock / Claude) para análisis de sentimiento
y toma de decisiones de trading.

Funciona como el "Slow Brain" del sistema dual.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from cortex.agents.base_agent import BaseAgent

# Load .env from project root
_sentinel_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_sentinel_root, ".env"))

HOLD = 0
BUY = 1
SELL = 2


class LLMAgent(BaseAgent):
    """
    Agente de trading basado en LLM.

    Arquitectura de Dos Niveles:
    - Slow Brain (LLM): Analiza contexto macro cada N pasos
    - Decisión: Combina señal del LLM con indicadores rápidos

    Soporta:
    - AWS Bedrock (Claude, Nova)
    - Cache local (SQLite) para evitar llamadas redundantes
    - Modo offline con sentimiento pre-computado
    """

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        region: str = None,
        llm_interval: int = 24,  # Cada cuántos pasos consultar al LLM
        cache_db: Optional[str] = None,
        offline_mode: bool = None,  # Auto-detect based on API key availability
    ):
        super().__init__(name=f"LLM({model_id.split('.')[-1][:20]})")
        self.model_id = model_id
        self.region = region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.llm_interval = llm_interval
        self._bedrock_api_key = os.getenv("BEDROCK_API_KEY")
        self._reasoning = ""
        self._last_llm_signal = "NEUTRAL"
        self._last_llm_confidence = 0.0

        # Auto-detect offline mode: use online if API key is available
        if offline_mode is None:
            self.offline_mode = self._bedrock_api_key is None
        else:
            self.offline_mode = offline_mode

        if not self.offline_mode and self._bedrock_api_key:
            print(f"  🧠 LLMAgent: Bedrock API key loaded, online mode enabled")

        # Cache SQLite
        self._cache_db = cache_db
        self._cache_conn = None
        if cache_db:
            self._init_cache(cache_db)

        # Bedrock client (lazy init)
        self._bedrock_client = None


    def _init_cache(self, db_path: str):
        """Inicializa cache SQLite para respuestas LLM."""
        self._cache_conn = sqlite3.connect(db_path)
        self._cache_conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                response TEXT,
                timestamp TEXT
            )
        """)
        self._cache_conn.commit()

    def _get_bedrock_client(self):
        """Lazy initialization del cliente Bedrock."""
        if self._bedrock_client is None:
            try:
                import boto3
                self._bedrock_client = boto3.client(
                    "bedrock-runtime", region_name=self.region
                )
            except Exception as e:
                print(f"  ⚠️  No se pudo conectar a Bedrock: {e}")
                self._bedrock_client = None
        return self._bedrock_client

    def decide(self, observation: dict) -> int:
        self._step_count += 1

        prices = observation.get("prices")
        if prices is None or len(prices) < 10:
            self._reasoning = "Datos insuficientes"
            return HOLD

        sentiment = observation.get("sentiment", 0.0)
        current_price = observation.get("current_price", 0.0)
        position = observation.get("position", 0.0)
        has_position = position > 0

        # --- Consultar LLM cada N pasos ---
        if self._step_count % self.llm_interval == 1:
            if self.offline_mode:
                # Usar sentimiento pre-computado como proxy del LLM
                self._analyze_offline(sentiment, prices)
            else:
                self._analyze_with_llm(observation)

        # --- Combinar señal LLM con indicadores rápidos ---
        signal = self._last_llm_signal
        confidence = self._last_llm_confidence

        # Indicadores rápidos de respaldo
        closes = prices[:, 3]
        sma_10 = float(closes[-10:].mean()) if len(closes) >= 10 else current_price
        price_vs_sma = (current_price - sma_10) / sma_10 if sma_10 > 0 else 0

        reasons = [f"LLM={signal}(conf={confidence:.0%})", f"Sent={sentiment:.2f}"]

        if signal == "BULLISH" and confidence > 0.5:
            if not has_position:
                self._reasoning = " | ".join(reasons) + " → BUY"
                return BUY
        elif signal == "BEARISH" and confidence > 0.5:
            if has_position:
                self._reasoning = " | ".join(reasons) + " → SELL"
                return SELL
        elif signal == "NEUTRAL":
            # En neutral, usar indicadores rápidos
            if price_vs_sma > 0.03 and has_position:
                self._reasoning = f"Neutral + SMA desvío +{price_vs_sma:.1%} → SELL"
                return SELL
            elif price_vs_sma < -0.03 and not has_position:
                self._reasoning = f"Neutral + SMA desvío {price_vs_sma:.1%} → BUY"
                return BUY

        self._reasoning = " | ".join(reasons) + " → HOLD"
        return HOLD

    def _analyze_offline(self, sentiment: float, prices):
        """Análisis sin LLM usando sentimiento pre-computado."""
        closes = prices[:, 3]

        # Tendencia de precios
        if len(closes) >= 5:
            recent_return = (closes[-1] - closes[-5]) / closes[-5]
        else:
            recent_return = 0.0

        # Combinar sentimiento + tendencia
        combined_score = sentiment * 0.6 + (1.0 if recent_return > 0 else -1.0) * 0.4

        if combined_score > 0.2:
            self._last_llm_signal = "BULLISH"
            self._last_llm_confidence = min(abs(combined_score), 1.0)
        elif combined_score < -0.2:
            self._last_llm_signal = "BEARISH"
            self._last_llm_confidence = min(abs(combined_score), 1.0)
        else:
            self._last_llm_signal = "NEUTRAL"
            self._last_llm_confidence = 0.3

    def _analyze_with_llm(self, observation: dict):
        """Consulta al LLM para análisis de sentimiento/mercado."""
        client = self._get_bedrock_client()
        if client is None:
            self._analyze_offline(observation.get("sentiment", 0.0), observation["prices"])
            return

        prices = observation["prices"]
        closes = prices[:, 3]
        current_price = observation.get("current_price", closes[-1])

        # Construir prompt
        prompt = self._build_prompt(closes, current_price, observation.get("sentiment", 0.0))

        # Check cache
        cache_key = f"{current_price:.0f}_{observation.get('sentiment', 0):.2f}"
        cached = self._check_cache(cache_key)
        if cached:
            self._parse_llm_response(cached)
            return

        try:
            # Llamar a Bedrock
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            })

            response = client.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json",
            )

            response_body = json.loads(response["body"].read())
            result_text = response_body["content"][0]["text"]

            # Cache result
            self._save_cache(cache_key, result_text)

            # Parse
            self._parse_llm_response(result_text)

        except Exception as e:
            print(f"  ⚠️  Error llamando LLM: {e}")
            self._analyze_offline(observation.get("sentiment", 0.0), prices)

    def _build_prompt(self, closes, current_price: float, sentiment: float) -> str:
        """Construye el prompt para el LLM."""
        # Calcular estadísticas
        pct_change_24h = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) > 1 else 0
        pct_change_7d = ((closes[-1] - closes[-7]) / closes[-7] * 100) if len(closes) > 7 else 0

        return f"""You are a crypto market analyst. Analyze the following data and provide a trading signal.

MARKET DATA:
- Current price: ${current_price:,.2f}
- 24h change: {pct_change_24h:+.2f}%
- 7d change: {pct_change_7d:+.2f}%
- Pre-computed sentiment score: {sentiment:.2f} (range: -1 bearish to +1 bullish)

Respond ONLY with a JSON object:
{{"signal": "BULLISH" or "BEARISH" or "NEUTRAL", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

    def _parse_llm_response(self, response_text: str):
        """Parsea la respuesta del LLM."""
        try:
            # Intentar extraer JSON
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
                self._last_llm_signal = data.get("signal", "NEUTRAL").upper()
                self._last_llm_confidence = float(data.get("confidence", 0.5))
            else:
                self._last_llm_signal = "NEUTRAL"
                self._last_llm_confidence = 0.3
        except (json.JSONDecodeError, ValueError):
            self._last_llm_signal = "NEUTRAL"
            self._last_llm_confidence = 0.3

    def _check_cache(self, key: str) -> Optional[str]:
        """Busca en cache."""
        if self._cache_conn is None:
            return None
        cursor = self._cache_conn.execute(
            "SELECT response FROM llm_cache WHERE cache_key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _save_cache(self, key: str, response: str):
        """Guarda en cache."""
        if self._cache_conn is None:
            return
        self._cache_conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, response, timestamp) VALUES (?, ?, ?)",
            (key, response, datetime.now().isoformat()),
        )
        self._cache_conn.commit()

    def reset(self):
        super().reset()
        self._last_llm_signal = "NEUTRAL"
        self._last_llm_confidence = 0.0
        self._reasoning = ""

    def get_reasoning(self) -> str:
        return self._reasoning

    def __del__(self):
        if self._cache_conn:
            self._cache_conn.close()
