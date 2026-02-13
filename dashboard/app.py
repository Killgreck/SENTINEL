#!/usr/bin/env python3
"""
SENTINEL — Dashboard (Fase 5)
Servidor web local para visualizar resultados de backtests y experimentos.

Uso:
    python3 dashboard/app.py
    python3 dashboard/app.py --port 8888
"""

import os
import sys
import json
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))


class DashboardHandler(SimpleHTTPRequestHandler):
    """Handler que sirve el dashboard y provee una API para datos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/experiments":
            self._serve_experiments()
        elif self.path == "/api/backtests":
            self._serve_backtests()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def _serve_experiments(self):
        """API endpoint: lista todos los experimentos."""
        from cortex.experiments.experiment_store import ExperimentStore
        store = ExperimentStore()
        experiments = store.list_all()
        data = [e.to_dict() for e in experiments]

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _serve_backtests(self):
        """API endpoint: lista CSVs de backtests disponibles."""
        results_dir = os.path.join(PROJECT_ROOT, "results")
        backtests = []

        if os.path.exists(results_dir):
            for f in sorted(os.listdir(results_dir)):
                if f.endswith(".csv"):
                    filepath = os.path.join(results_dir, f)
                    try:
                        import pandas as pd
                        df = pd.read_csv(filepath)
                        if not df.empty:
                            backtests.append({
                                "filename": f,
                                "rows": len(df),
                                "columns": list(df.columns),
                                "data": df.to_dict(orient="records")[-50:],
                            })
                    except Exception:
                        pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(backtests, default=str).encode())

    def _serve_status(self):
        """API endpoint: estado del sistema."""
        data_dir = os.path.join(PROJECT_ROOT, "data", "market", "raw")
        parquet_files = []
        if os.path.exists(data_dir):
            for f in os.listdir(data_dir):
                if f.endswith(".parquet"):
                    size = os.path.getsize(os.path.join(data_dir, f))
                    parquet_files.append({"name": f, "size_kb": round(size / 1024, 1)})

        from cortex.experiments.experiment_store import ExperimentStore
        store = ExperimentStore()
        total_experiments = len(store.list_all())

        status = {
            "project": "SENTINEL",
            "version": "0.4.0",
            "data_files": parquet_files,
            "total_experiments": total_experiments,
            "agents_available": ["buy_hold", "statistical", "swing", "contrarian", "llm"],
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(status, default=str).encode())

    def log_message(self, format, *args):
        if "/api/" not in str(args[0]):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="SENTINEL Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Puerto")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), DashboardHandler)
    print(f"\n  SENTINEL Dashboard")
    print(f"  URL: http://localhost:{args.port}")
    print(f"  API: /api/experiments | /api/backtests | /api/status")
    print(f"  Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
