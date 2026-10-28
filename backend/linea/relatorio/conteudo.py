"""Monta o conteúdo do relatório em uma estrutura neutra, usada pelos três
exportadores (.docx, .odt e .pdf). Assim o texto é o mesmo em todos os formatos."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

VERDE = "1E7B34"
VERMELHO = "B3261E"
CINZA = "5F6368"
COR_STATUS = {"atende": VERDE, "nao_atende": VERMELHO, "nao_verificavel": CINZA, None: None}
ROTULO = {"atende": "Atende", "nao_atende": "Não atende", "nao_verificavel": "Não verificável", None: ""}

AVISO = ("Esta análise é uma ferramenta de apoio. Ela confere, de forma automática, os parâmetros do relatório "
         "estatístico do SisDEA. A escolha e a responsabilidade pelo modelo de regressão são do avaliador.")


@dataclass
class Elemento:
    tipo: str                      # titulo, secao, subsecao, paragrafo, tabela, lista, aviso
    texto: str = ""
    cor: Optional[str] = None
    negrito: bool = False
    rotulo: str = ""               # prefixo em negrito ("Como foi feito: ")
    cabecalho: List[str] = field(default_factory=list)
    linhas: List[List[str]] = field(default_factory=list)
    cores_linhas: List[Optional[str]] = field(default_factory=list)
    itens: List[str] = field(default_factory=list)
    larguras: List[float] = field(default_factory=list)  # frações da largura útil


def montar(res: dict) -> List[Elemento]:
    E: List[Elemento] = []
    mod = res["modelo"]
    E.append(Elemento("titulo", "Análise do Relatório Estatístico do SisDEA"))
    E.append(Elemento("paragrafo", f"{res['app']['nome']} {res['app']['versao']} · gerado em {res['gerado_em']}",
                      cor=CINZA))
    E.append(Elemento("aviso", AVISO))

    E.append(Elemento("secao", "1. Identificação do modelo"))
    ident = [["Arquivo", res.get("arquivo") or "—"], ["Modelo", mod["modelo"] or "—"],
             ["Autor", mod["autor"] or "—"], ["Data do modelo", mod["data"] or "—"],
             ["Tipologia", mod["tipologia"] or "—"],
             ["Dados utilizados (n)", str(mod["n"] or "—")],
             ["Variáveis independentes (k)", str(mod["k"])],
             ["Variável dependente", mod["variavel_dependente"] or "—"]]
    E.append(Elemento("tabela", cabecalho=["Campo", "Conteúdo"], linhas=ident, larguras=[0.32, 0.68]))
    if mod.get("equacao"):
        E.append(Elemento("paragrafo", mod["equacao"], rotulo="Equação: "))

    r = res["resumo"]
    E.append(Elemento("secao", "2. Conferências"))
    E.append(Elemento("paragrafo",
                      f"{r['atende']} conferência(s) atendida(s), {r['nao_atende']} não atendida(s) e "
                      f"{r['nao_verificavel']} não verificável(is)."))
    for i, c in enumerate(res["conferencias"], start=1):
        cor = COR_STATUS[c["status"]]
        E.append(Elemento("subsecao", f"2.{i} {c['titulo']} — {ROTULO[c['status']]}", cor=cor))
        E.append(Elemento("paragrafo", c["como_foi_feito"], rotulo="Como foi feito: "))
        if c["linhas"]:
            E.append(Elemento("tabela", cabecalho=["Item", "Valor", "Critério"],
                              linhas=[[l["item"], l["valor"], l["criterio"]] for l in c["linhas"]],
                              cores_linhas=[COR_STATUS[l["status"]] for l in c["linhas"]],
                              larguras=[0.40, 0.35, 0.25]))
        E.append(Elemento("paragrafo", c["explicacao"], rotulo="Resultado: ", cor=cor))
        if c["sugestoes"]:
            rot = "Sugestões para corrigir:" if c["status"] == "nao_atende" else "Sugestões:"
            E.append(Elemento("paragrafo", rot, negrito=True, cor=cor if c["status"] == "nao_atende" else None))
            E.append(Elemento("lista", itens=c["sugestoes"], cor=cor if c["status"] == "nao_atende" else None))
        for o in c["observacoes"]:
            E.append(Elemento("paragrafo", o, rotulo="Observação: ", cor=CINZA))

    E.append(Elemento("secao", "3. Leitura do arquivo"))
    lei = res["leitura"]
    E.append(Elemento("paragrafo", lei["texto_consistencia"]))
    for a in lei["avisos"]:
        E.append(Elemento("paragrafo", a, rotulo="Aviso: ", cor=VERMELHO))
    return E
