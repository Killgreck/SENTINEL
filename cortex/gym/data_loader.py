"""
SENTINEL Cortex — DataLoader
═════════════════════════════
Carga y fusiona datos de precios (Parquet) con datos de sentimiento (CSV).
Soporta carga local y desde S3.
"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional, List


# Mapping entre símbolos del config (BTCUSDT) y archivos locales (BTC-USD)
SYMBOL_FILE_MAP = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
}


class DataLoader:
    """Carga y prepara datos para el entorno de simulación."""

    def __init__(self, data_dir: Optional[str] = None):
        """
        Args:
            data_dir: Directorio raíz de datos. Default: SENTINEL/data/
        """
        if data_dir is None:
            sentinel_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            )))
            data_dir = os.path.join(sentinel_root, "data")

        self.data_dir = data_dir
        self.prices_dir = os.path.join(data_dir, "market", "raw")
        self.sentiment_dir = os.path.join(data_dir, "sentimental", "raw")

    def load_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Carga datos de precios OHLCV desde Parquet.

        Args:
            symbol: Símbolo del activo (e.g., "BTCUSDT" o "BTC-USD")
            interval: Intervalo temporal ("1d" o "1h")
            start_date: Fecha inicio (YYYY-MM-DD)
            end_date: Fecha fin (YYYY-MM-DD)

        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume
        """
        # Resolver nombre de archivo
        file_symbol = SYMBOL_FILE_MAP.get(symbol, symbol)
        filename = f"{file_symbol}_{interval}.parquet"
        filepath = os.path.join(self.prices_dir, filename)

        if not os.path.exists(filepath):
            raise FileNotFoundError(
                f"Archivo de precios no encontrado: {filepath}\n"
                f"Ejecuta: python3 download_prices_now.py"
            )

        df = pd.read_parquet(filepath)

        # Normalizar nombre de columna de tiempo
        time_col = None
        for col in ["Date", "Datetime", "timestamp", "date"]:
            if col in df.columns:
                time_col = col
                break

        if time_col is None and df.index.name in ["Date", "Datetime"]:
            df = df.reset_index()
            time_col = df.columns[0]

        if time_col:
            df = df.rename(columns={time_col: "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Normalizar nombres de columnas a minúsculas
        df.columns = [c.lower() for c in df.columns]

        # Asegurar columnas mínimas
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(
                    f"Columna '{col}' no encontrada en {filepath}. "
                    f"Columnas disponibles: {list(df.columns)}"
                )

        df = df[required].copy()
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Filtrar por fechas
        if start_date:
            df = df[df["timestamp"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["timestamp"] <= pd.to_datetime(end_date)]

        df = df.reset_index(drop=True)
        return df

    def load_sentiment(
        self,
        model: str = "gemini-1.5-flash",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Carga datos de sentimiento desde CSV.

        Args:
            model: Modelo de sentimiento a usar
            start_date: Fecha inicio
            end_date: Fecha fin

        Returns:
            DataFrame con columnas: timestamp, sentiment_score
        """
        # Intentar cargar el merged daily primero
        merged_path = os.path.join(self.sentiment_dir, "merged", "merged_daily.csv")

        if os.path.exists(merged_path):
            df = pd.read_csv(merged_path)
        else:
            # Intentar archivo específico del modelo
            pattern = f"merged_daily_{model}_opinion.csv"
            annotated_path = os.path.join(self.sentiment_dir, "annotated", pattern)

            if os.path.exists(annotated_path):
                df = pd.read_csv(annotated_path)
            else:
                print(f"  ⚠️  Datos de sentimiento no encontrados para {model}")
                return pd.DataFrame(columns=["timestamp", "sentiment_score"])

        # Normalizar columnas
        df.columns = [c.lower().strip() for c in df.columns]

        # Buscar columna de fecha
        date_col = None
        for col in ["date", "timestamp", "datetime", "day"]:
            if col in df.columns:
                date_col = col
                break

        if date_col:
            df = df.rename(columns={date_col: "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"])

        # Buscar columna de sentimiento
        sent_col = None
        for col in df.columns:
            if "sentiment" in col or "opinion" in col or "score" in col:
                sent_col = col
                break

        if sent_col and sent_col != "sentiment_score":
            df = df.rename(columns={sent_col: "sentiment_score"})

        if "sentiment_score" not in df.columns:
            # Si no hay columna de sentimiento clara, crear una neutral
            df["sentiment_score"] = 0.0

        # Asegurar que sentiment_score es numérico
        df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce").fillna(0.0)

        # Filtrar por fechas
        if "timestamp" in df.columns:
            if start_date:
                df = df[df["timestamp"] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df["timestamp"] <= pd.to_datetime(end_date)]

        df = df.reset_index(drop=True)
        return df

    def load_merged(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1d",
        sentiment_model: str = "gemini-1.5-flash",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Carga y fusiona precios + sentimiento.

        Args:
            symbol: Símbolo del activo
            interval: Intervalo temporal
            sentiment_model: Modelo de sentimiento
            start_date: Fecha inicio
            end_date: Fecha fin

        Returns:
            DataFrame con OHLCV + sentiment_score
        """
        prices = self.load_prices(symbol, interval, start_date, end_date)
        sentiment = self.load_sentiment(sentiment_model, start_date, end_date)

        if sentiment.empty or "timestamp" not in sentiment.columns:
            prices["sentiment_score"] = 0.0
            return prices

        # Normalizar a solo fecha para merge (en caso de datos diarios)
        prices["merge_date"] = prices["timestamp"].dt.date
        sentiment["merge_date"] = sentiment["timestamp"].dt.date

        # Merge por fecha
        merged = prices.merge(
            sentiment[["merge_date", "sentiment_score"]],
            on="merge_date",
            how="left",
        )
        merged["sentiment_score"] = merged["sentiment_score"].fillna(0.0)
        merged = merged.drop(columns=["merge_date"])

        return merged

    def list_available_data(self) -> dict:
        """Lista los datos disponibles localmente."""
        available = {"prices": [], "sentiment": []}

        if os.path.exists(self.prices_dir):
            for f in os.listdir(self.prices_dir):
                if f.endswith(".parquet"):
                    available["prices"].append(f)

        if os.path.exists(self.sentiment_dir):
            for root, dirs, files in os.walk(self.sentiment_dir):
                for f in files:
                    if f.endswith((".csv", ".parquet")):
                        rel = os.path.relpath(os.path.join(root, f), self.sentiment_dir)
                        available["sentiment"].append(rel)

        return available


if __name__ == "__main__":
    loader = DataLoader()
    print("📊 Datos disponibles:")
    available = loader.list_available_data()
    for category, files in available.items():
        print(f"\n  {category}:")
        for f in files:
            print(f"    • {f}")

    print("\n\n📈 Cargando BTC-USD diario...")
    df = loader.load_prices("BTCUSDT", "1d")
    print(f"  {len(df)} filas | {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(df.tail(3).to_string(index=False))

    print("\n\n🔀 Cargando datos fusionados (precios + sentimiento)...")
    merged = loader.load_merged("BTCUSDT", "1d")
    print(f"  {len(merged)} filas")
    print(merged.tail(3).to_string(index=False))
