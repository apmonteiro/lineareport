"""Inicia o LineaReport localmente: python run_server.py  (abre em http://127.0.0.1:8000)."""
import argparse
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from linea.api import criar_app  # noqa: E402

FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor do LineaReport")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--sem-navegador", action="store_true")
    a = ap.parse_args()
    app = criar_app(os.path.normpath(FRONTEND))
    if not a.sem_navegador:
        webbrowser.open(f"http://{a.host}:{a.porta}")
    app.run(host=a.host, port=a.porta, debug=False)
