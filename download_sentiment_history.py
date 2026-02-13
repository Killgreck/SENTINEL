import os
from huggingface_hub import hf_hub_download
from dotenv import load_dotenv

# Configuración de paths relativos al script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
token = os.getenv("HF_TOKEN")

# Configuración
REPO_ID = "danilocorsi/LLMs-Sentiment-Augmented-Bitcoin-Dataset"
DEST_DIR = os.path.join(SCRIPT_DIR, "data", "sentimental", "raw")

def download_sentiment_data():
    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)
        
    print(f"🚀 Downloading from {REPO_ID}...")
    
    # El dataset usualmente viene en archivos CSV o Parquet
    # Intentaremos bajar el archivo principal si lo conocemos, o listar
    try:
        # Nota: Este dataset específico puede tener varios archivos. 
        # Bajaremos el archivo 'dataset.csv' o similar si existe.
        # En HuggingFace podemos bajar carpetas enteras con snapshot_download
        from huggingface_hub import snapshot_download
        
        path = snapshot_download(
            repo_id=REPO_ID,
            local_dir=DEST_DIR,
            repo_type="dataset",
            token=token,
            allow_patterns=["*.parquet", "*.csv", "*.zip"]
        )
        print(f"✅ Data saved to: {path}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    download_sentiment_data()
