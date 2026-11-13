"""Servidor do LineaReport para uso em rede (intranet), com o waitress.

    python servir.py                       # http://<nome-do-servidor>:8000 para toda a rede
    python servir.py --porta 8080 --threads 8
    python servir.py --host 127.0.0.1      # só nesta máquina (atrás de um proxy reverso)

Diferente de run_server.py (uso pessoal), não abre o navegador e usa um servidor de produção,
que atende várias pessoas ao mesmo tempo. Nada é gravado em disco: cada arquivo é analisado em memória.
"""
import argparse
import logging
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from linea.api import criar_app  # noqa: E402

FRONTEND = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor do LineaReport para a rede interna")
    ap.add_argument("--host", default=os.environ.get("LINEA_HOST", "0.0.0.0"),
                    help="endereço de escuta (padrão 0.0.0.0 = todas as interfaces)")
    ap.add_argument("--porta", type=int, default=int(os.environ.get("LINEA_PORTA", "8000")))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("LINEA_THREADS", "4")),
                    help="análises atendidas ao mesmo tempo")
    ap.add_argument("--prefixo", default=os.environ.get("LINEA_PREFIXO", ""),
                    help="caminho quando publicado atrás de proxy reverso, ex.: /lineareport")
    a = ap.parse_args()

    from waitress import serve

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = criar_app(FRONTEND)
    endereco = socket.gethostname() if a.host == "0.0.0.0" else a.host
    print(f"LineaReport disponível em http://{endereco}:{a.porta}{a.prefixo or '/'}  (Ctrl+C para parar)")
    opcoes = dict(host=a.host, port=a.porta, threads=a.threads, url_prefix=a.prefixo,
                  max_request_body_size=30 * 1024 * 1024)
    if a.host == "127.0.0.1":   # atrás de proxy reverso na mesma máquina (IIS, nginx)
        opcoes.update(trusted_proxy="127.0.0.1", clear_untrusted_proxy_headers=True,
                      trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-host", "x-forwarded-for"})
    serve(app, **opcoes)
