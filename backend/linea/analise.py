"""Ponto de entrada da análise: RTF (bytes) -> resultado completo (dict serializável)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .conferencias import regras
from .conferencias.base import ATENDE, NAO_ATENDE, NAO_VERIFICAVEL, carregar_criterios, fmt
from .sisdea.parser import interpretar

VERSAO = "0.3.4"


def analisar(dados: bytes, nome_arquivo: str = "", criterios: Optional[dict] = None) -> dict:
    crit = criterios or carregar_criterios()
    m = interpretar(dados)
    ctx = regras.preparar_contexto(m, crit)
    conferencias = []
    for f in regras.TODAS:
        try:
            conferencias.append(f(ctx))
        except Exception as e:  # noqa: BLE001 - uma conferência com erro não derruba as demais
            from .conferencias.base import Conferencia
            conferencias.append(Conferencia(f.__name__, f.__name__.replace("_", " ").title(), NAO_VERIFICAVEL,
                                            "Erro ao executar a conferência.", "", f"Erro interno: {e}"))
    contagem = {s: sum(1 for c in conferencias if c.status == s) for s in (ATENDE, NAO_ATENDE, NAO_VERIFICAVEL)}

    leitura = {"secoes_encontradas": m.secoes_encontradas, "avisos": list(m.avisos) + ctx.observacoes,
               "consistencia": ctx.consistencia, "motivo_sem_regressores": ctx.motivo_sem_x}
    if ctx.consistencia.get("ok"):
        leitura["texto_consistencia"] = (
            "Os dados e as transformações lidos do relatório reproduzem os resíduos informados pelo SisDEA "
            f"(diferença máxima de {fmt(ctx.consistencia['diferenca_maxima'], 6)} no resíduo padronizado). "
            "A leitura do arquivo está consistente.")
    else:
        leitura["texto_consistencia"] = (
            "Não foi possível confirmar a leitura dos dados da amostra"
            + (f" ({ctx.consistencia.get('motivo') or ctx.motivo_sem_x})." if (ctx.consistencia.get('motivo') or ctx.motivo_sem_x) else ".")
            + " As conferências que dependem dos regressores foram marcadas como não verificáveis.")

    return {
        "app": {"nome": "LineaReport", "versao": VERSAO},
        "arquivo": nome_arquivo,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "modelo": {
            "autor": m.autor, "modelo": m.modelo, "data": m.data, "tipologia": m.tipologia,
            "n": m.n, "k": m.k, "total_dados": m.total_dados,
            "variavel_dependente": m.variavel_dependente.nome if m.variavel_dependente else None,
            "variaveis": [{"nome": v.nome, "classificacao": v.classificacao, "habilitada": v.habilitada,
                           "transformacao": next((r.transformacao for r in m.regressores if r.nome == v.nome), "")}
                          for v in m.variaveis],
            "equacao": m.equacao, "r2": m.r2,
        },
        "resumo": contagem,
        "conferencias": [c.para_dict() for c in conferencias],
        "leitura": leitura,
    }
