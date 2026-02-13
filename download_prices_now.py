import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Configuración
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data", "market", "raw")
SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD"]
INTERVALS = ["1d", "1h"]  # Diario y Horario
START_DATE = "2020-01-01"

def setup_dirs():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Created directory: {DATA_DIR}")

def download_data(symbol, interval):
    print(f"Downloading {symbol} ({interval})...")
    
    # Yahoo Finance tiene limites para datos horarios (max 730 dias atras)
    # Para diario podemos ir más atrás.
    
    try:
        # Ticker object
        ticker = yf.Ticker(symbol)
        
        # Download
        # period="max" intenta traer todo, pero limitado por intervalo
        if interval == "1h":
            # Para 1h, bajamos los ultimos 2 años (limite de YF)
            df = ticker.history(period="2y", interval=interval)
        else:
            df = ticker.history(start=START_DATE, interval=interval)
            
        if df.empty:
            print(f"⚠️ No data found for {symbol} {interval}")
            return

        # Save to Parquet (fast & efficient)
        filename = f"{symbol}_{interval}.parquet"
        filepath = os.path.join(DATA_DIR, filename)
        
        # Reset index to keep Date/Datetime as a column
        df.reset_index(inplace=True)
        
        df.to_parquet(filepath)
        print(f"✅ Saved {len(df)} rows to {filepath}")
        
        # Preview
        print(df.tail(3)[['Close', 'Volume']])
        print("-" * 30)
        
    except Exception as e:
        print(f"❌ Error downloading {symbol}: {str(e)}")

def main():
    setup_dirs()
    print(f"🚀 Starting Price Downloader to {DATA_DIR}")
    
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            download_data(symbol, interval)
            
    print("\n🏁 Download complete. Data is ready for the Gym.")

if __name__ == "__main__":
    main()
