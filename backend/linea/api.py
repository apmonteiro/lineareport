"""API HTTP (Flask). Não guarda nada: o arquivo é lido em memória, analisado e descartado.

Rotas:
  GET  /api/saude                  -> verificação simples
  POST /api/analisar               -> multipart com o campo 'arquivo' (.rtf ou .pdf); devolve a análise em JSON
  POST /api/exportar/<formato>     -> corpo JSON = análise; devolve o relatório (docx, odt ou pdf)
"""
from __future__ import annotations

import io
import os
import re

from flask import Flask, jsonify, request, send_file, send_from_directory

from .analise import VERSAO, analisar
from .relatorio.exportar import FORMATOS, exportar
from .sisdea.parser import ErroLeitura

TAMANHO_MAXIMO_MB = 25


def criar_app(pasta_frontend: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO_MB * 1024 * 1024
    origem_cors = os.environ.get("LINEA_CORS_ORIGEM", "")

    @app.after_request
    def cors(resp):
        if origem_cors:
            resp.headers["Access-Control-Allow-Origin"] = origem_cors
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @app.get("/api/saude")
    def saude():
        return jsonify({"status": "ok", "versao": VERSAO})

    @app.post("/api/analisar")
    def rota_analisar():
        arq = request.files.get("arquivo")
        if arq is None or not arq.filename:
            return jsonify({"erro": "Nenhum arquivo enviado. Selecione o relatório do SisDEA em .rtf ou .pdf."}), 400
        if not arq.filename.lower().endswith((".rtf", ".pdf")):
            return jsonify({"erro": "O arquivo precisa ser .rtf ou .pdf (relatório estatístico do SisDEA)."}), 400
        dados = arq.read()
        try:
            res = analisar(dados, arq.filename)
        except ErroLeitura as e:
            return jsonify({"erro": str(e)}), 422
        except Exception as e:  # noqa: BLE001
            app.logger.exception("Falha na análise")
            return jsonify({"erro": f"Erro inesperado ao analisar o arquivo: {e}"}), 500
        return jsonify(res)

    @app.post("/api/exportar/<formato>")
    def rota_exportar(formato: str):
        if formato not in FORMATOS:
            return jsonify({"erro": "Formato não suportado. Use docx, odt ou pdf."}), 400
        res = request.get_json(silent=True)
        if not res or "conferencias" not in res:
            return jsonify({"erro": "Envie o resultado da análise para gerar o relatório."}), 400
        conteudo = exportar(res, formato)
        base = re.sub(r"[^\w\-]+", "_", os.path.splitext(res.get("arquivo") or "modelo")[0]).strip("_")
        return send_file(io.BytesIO(conteudo), mimetype=FORMATOS[formato], as_attachment=True,
                         download_name=f"Analise_{base or 'modelo'}.{formato}")

    @app.errorhandler(413)
    def grande(_e):
        return jsonify({"erro": f"Arquivo maior que {TAMANHO_MAXIMO_MB} MB."}), 413

    if pasta_frontend and os.path.isdir(pasta_frontend):
        @app.get("/")
        def inicio():
            return send_from_directory(pasta_frontend, "index.html")

        @app.get("/<path:caminho>")
        def estaticos(caminho):
            return send_from_directory(pasta_frontend, caminho)

    return app
