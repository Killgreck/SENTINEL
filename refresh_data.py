#!/usr/bin/env python3
"""
SENTINEL — Refresh Data (Fase 1)
══════════════════════════════════
Actualiza los datos de precios al día más reciente.
Preserva datos existentes y solo descarga lo que falta.

Uso: python3 refresh_data.py [--full]
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data", "market", "raw")


def refresh_prices(full: bool = False):
    """Descarga/actualiza datos de precios."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("❌ Instala dependencias: pip3 install yfinance pandas pyarrow")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)

    symbols = {
        "BTC-USD": ["1d", "1h"],
        "ETH-USD": ["1d", "1h"],
        "SOL-USD": ["1d", "1h"],
    }

    print(f"\n🛡️  SENTINEL — Refresh Data")
    print(f"    Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    Modo:  {'COMPLETO (2 años)' if full else 'INCREMENTAL'}")
    print(f"    Dir:   {DATA_DIR}\n")

    for symbol, intervals in symbols.items():
        for interval in intervals:
            filename = f"{symbol}_{interval}.parquet"
            filepath = os.path.join(DATA_DIR, filename)

            # Determinar periodo de descarga
            if full or not os.path.exists(filepath):
                # Descarga completa: 2 años para daily, 60 días para hourly
                if interval == "1d":
                    period = "2y"
                else:
                    period = "60d"  # yfinance limita hourly a ~60 días
                print(f"  ⬇️  {symbol} {interval} (completo, {period})...", end=" ", flush=True)
            else:
                # Incremental: leer último timestamp y descargar desde ahí
                existing = pd.read_parquet(filepath)
                
                # Buscar columna de timestamp
                if "Date" in existing.columns:
                    last_date = pd.to_datetime(existing["Date"]).max()
                elif "Datetime" in existing.columns:
                    last_date = pd.to_datetime(existing["Datetime"]).max()
                else:
                    last_date = pd.to_datetime(existing.index).max()
                
                days_behind = (datetime.now() - last_date.to_pydatetime().replace(tzinfo=None)).days

                if days_behind <= 1:
                    print(f"  ✅ {symbol} {interval}: ya actualizado ({last_date.date()})")
                    continue

                period = f"{min(days_behind + 5, 730)}d"  # +5 días de margen
                print(f"  ⬇️  {symbol} {interval} (incremental, {days_behind} días atrás)...", end=" ", flush=True)

            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)

                if df.empty:
                    print(f"❌ sin datos")
                    continue

                # Guardar como Parquet
                df.to_parquet(filepath, engine="pyarrow")
                print(f"✅ {len(df)} filas ({df.index[0].date()} → {df.index[-1].date()})")

            except Exception as e:
                print(f"❌ Error: {e}")

    # Resumen
    print(f"\n  📊 Archivos en {DATA_DIR}:")
    if os.path.exists(DATA_DIR):
        for f in sorted(os.listdir(DATA_DIR)):
            if f.endswith(".parquet"):
                size = os.path.getsize(os.path.join(DATA_DIR, f))
                print(f"     • {f} ({size / 1024:.1f} KB)")

    print(f"\n  ✅ Refresh completado")
    print(f"  💡 Para subir a S3: python3 sync_to_s3.py")


def main():
    parser = argparse.ArgumentParser(description="🛡️ SENTINEL Refresh Data")
    parser.add_argument("--full", action="store_true",
                        help="Descarga completa (ignora datos existentes)")
    args = parser.parse_args()
    refresh_prices(full=args.full)


if __name__ == "__main__":
    main()
