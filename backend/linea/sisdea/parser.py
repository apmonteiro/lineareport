"""Interpreta os blocos do RTF gerado pelo SisDEA e monta um ModeloSisDEA.

As seções do relatório são localizadas pelo título (ex.: "TESTES DE HIPÓTESES"),
e não pela numeração, que o SisDEA gera automaticamente e pode variar
conforme as opções de impressão escolhidas.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from ..rtf.reader import Bloco, Paragrafo, Tabela, ler_blocos
from .modelo import (FaixaNormalidade, LinhaAmostra, MatrizCorrelacao,
                     ModeloSisDEA, Regressor, Residuo, Variavel)


class ErroLeitura(Exception):
    """Arquivo não reconhecido como relatório do SisDEA."""


# chave interna -> prefixo do título normalizado
SECOES = {
    "info_basicas": "INFORMACOES BASICAS",
    "info_complementares": "INFORMACOES COMPLEMENTARES",
    "variaveis": "DESCRICAO DAS VARIAVEIS",
    "descritivas": "ESTATISTICAS DESCRITIVAS",
    "coeficientes": "COEFICIENTES DE CORRELACAO",
    "normalidade": "NORMALIDADE DOS RESIDUOS",
    "outliers": "OUTLIERS DO MODELO",
    "anova": "ANALISE DA VARIANCIA",
    "equacao": "EQUACAO DE REGRESSAO",
    "hipoteses": "TESTES DE HIPOTESES",
    "corr_isoladas": "CORRELACOES PARCIAIS ISOLADAS",
    "corr_influencia": "CORRELACOES PARCIAIS INFLUENCIA",
    "residuos": "TABELA DE RESIDUOS",
    "fundamentacao": "TABELA DE FUNDAMENTACAO",
    "graficos_aderencia": "GRAFICOS DE ADERENCIA",
    "graficos_elasticidade": "GRAFICOS DE ELASTICIDADE",
    "amostra": "TABELA DE DADOS",
    "estimativas": "ESTIMATIVAS DE VALORES",
}

# Seções indispensáveis para as conferências
SECOES_OBRIGATORIAS = ["variaveis", "coeficientes", "normalidade", "hipoteses",
                       "residuos", "amostra"]


def normaliza(txt: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", txt)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def numero(txt: Optional[str]) -> Optional[float]:
    """Converte número no formato brasileiro ('1.500,00', '5,00%', '-6,7E-07')."""
    if txt is None:
        return None
    s = txt.strip().replace("%", "").replace(" ", "").replace(" ", "")
    if not s or s in {"-", "--"} or not re.search(r"\d", s):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):    # '1.200.000' (milhar sem decimais)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def inteiro(txt: Optional[str]) -> Optional[int]:
    v = numero(txt)
    return int(round(v)) if v is not None else None


def _divide_secoes(blocos: List[Bloco]) -> Dict[str, List[Bloco]]:
    secoes: Dict[str, List[Bloco]] = {}
    atual: Optional[str] = None
    for b in blocos:
        if isinstance(b, Paragrafo):
            t = normaliza(b.texto)
            achou = None
            for chave, prefixo in SECOES.items():
                if t.startswith(prefixo):
                    achou = chave
                    break
            if achou:
                atual = achou
                secoes.setdefault(atual, [])
                secoes[atual].append(b)  # o próprio título (útil p/ equação)
                continue
        if atual:
            secoes[atual].append(b)
    return secoes


def _tabelas(blocos: List[Bloco]) -> List[Tabela]:
    return [b for b in blocos if isinstance(b, Tabela)]


def _pares(blocos: List[Bloco]) -> Dict[str, str]:
    """Tabelas de duas colunas 'rótulo: valor' viram dicionário normalizado."""
    d: Dict[str, str] = {}
    for tab in _tabelas(blocos):
        for linha in tab.linhas:
            if len(linha) >= 2:
                d[normaliza(linha[0]).rstrip(":").strip()] = linha[1]
    return d


def _tabela_por_chave(blocos: List[Bloco], cabecalho0: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """Junta tabelas (inclusive quebradas em páginas ou em colunas) cujo cabeçalho
    começa com `cabecalho0`. Retorna (colunas, {chave: [valores na ordem das colunas]})."""
    colunas: List[str] = []
    linhas: Dict[str, Dict[str, str]] = {}
    ordem: List[str] = []
    alvo = normaliza(cabecalho0)
    for tab in _tabelas(blocos):
        if not tab.linhas or normaliza(tab.linhas[0][0]) != alvo:
            continue
        cab = tab.linhas[0]
        for c in cab[1:]:
            if c not in colunas:
                colunas.append(c)
        for linha in tab.linhas[1:]:
            if not linha or normaliza(linha[0]) == alvo:
                continue  # cabeçalho repetido
            chave = linha[0].strip()
            if chave not in linhas:
                linhas[chave] = {}
                ordem.append(chave)
            for c, v in zip(cab[1:], linha[1:]):
                linhas[chave][c] = v
    return colunas, {k: [linhas[k].get(c, "") for c in colunas] for k in ordem}


def _matriz(blocos: List[Bloco]) -> MatrizCorrelacao:
    m = MatrizCorrelacao()
    for tab in _tabelas(blocos):
        if not tab.linhas or len(tab.linhas[0]) < 3:
            continue
        cab = tab.linhas[0]
        aliases_col = cab[2:]
        for linha in tab.linhas[1:]:
            if len(linha) < 3:
                continue
            nome, alias = linha[0], linha[1]
            m.aliases[alias] = nome
            m.valores.setdefault(alias, {})
            for a, v in zip(aliases_col, linha[2:]):
                m.valores[alias][a] = numero(v)
    return m


def interpretar(dados: bytes) -> ModeloSisDEA:
    """Aceita o relatório do SisDEA em RTF ou em PDF (detectado pelo conteúdo)."""
    if dados.lstrip()[:5] == b"%PDF-":
        from .parser_pdf import interpretar_pdf
        return interpretar_pdf(dados)
    try:
        blocos = ler_blocos(dados)
    except Exception as e:  # noqa: BLE001
        raise ErroLeitura(f"Não foi possível ler o arquivo RTF: {e}") from e

    secoes = _divide_secoes(blocos)
    m = ModeloSisDEA()
    m.secoes_encontradas = list(secoes.keys())

    faltando = [SECOES[s].title() for s in SECOES_OBRIGATORIAS if s not in secoes]
    if len(faltando) == len(SECOES_OBRIGATORIAS):
        raise ErroLeitura("O arquivo não parece ser um relatório estatístico do SisDEA "
                          "(nenhuma das seções esperadas foi encontrada).")
    for f in faltando:
        m.avisos.append(f"Seção não encontrada no relatório: {f}.")

    for b in blocos:
        if isinstance(b, Paragrafo) and "SISDEA" in normaliza(b.texto) and "VERS" in normaliza(b.texto):
            m.versao_sisdea = b.texto
            break

    # 1) informações básicas
    p = _pares(secoes.get("info_basicas", []))
    m.autor, m.modelo = p.get("AUTOR", ""), p.get("MODELO", "")
    m.data, m.tipologia = p.get("DATA DO MODELO", ""), p.get("TIPOLOGIA", "")

    # 2) informações complementares
    p = _pares(secoes.get("info_complementares", []))
    m.total_variaveis = inteiro(p.get("TOTAL DE VARIAVEIS"))
    m.variaveis_utilizadas = inteiro(p.get("VARIAVEIS UTILIZADAS NO MODELO"))
    m.total_dados = inteiro(p.get("TOTAL DE DADOS"))
    m.dados_utilizados = inteiro(p.get("DADOS UTILIZADOS NO MODELO"))

    # 3) variáveis
    for tab in _tabelas(secoes.get("variaveis", [])):
        for linha in tab.linhas[1:]:
            if len(linha) >= 5 and normaliza(linha[0]) != "NOME":
                m.variaveis.append(Variavel(
                    nome=linha[0], tipo=linha[1], classificacao=linha[2],
                    descricao=linha[3], habilitada=normaliza(linha[4]).startswith("SIM")))

    # 5) coeficientes
    p = _pares(secoes.get("coeficientes", []))
    rs = p.get("COEFICIENTE DE CORRELACAO", "")
    partes = [numero(x) for x in rs.split("/")]
    if partes:
        m.r_equacao = partes[0]
    if len(partes) > 1:
        m.r_funcao = partes[1]
    m.r2 = numero(p.get("COEFICIENTE DE DETERMINACAO"))
    m.f_calculado = numero(p.get("FISHER - SNEDECOR"))
    m.significancia_modelo = numero(p.get("SIGNIFICANCIA DO MODELO (%)"))

    # 6) normalidade
    for tab in _tabelas(secoes.get("normalidade", [])):
        for linha in tab.linhas[1:]:
            if len(linha) < 3:
                continue
            achado = re.search(r"-\s*(\d+(?:,\d+)?)", linha[0])
            sigma = numero(achado.group(1)) if achado else None
            if sigma is not None:
                m.normalidade.append(FaixaNormalidade(sigma, numero(linha[1]), numero(linha[2])))

    # 7) outliers
    p = _pares(secoes.get("outliers", []))
    m.n_outliers = inteiro(p.get("QUANTIDADE DE OUTLIERS"))
    m.pct_outliers = numero(p.get("% DE OUTLIERS"))

    # 9) equação
    eq = [b.texto for b in secoes.get("equacao", [])[1:] if isinstance(b, Paragrafo)]
    m.equacao = " ".join(eq)

    # 10) testes de hipóteses
    for tab in _tabelas(secoes.get("hipoteses", [])):
        for linha in tab.linhas[1:]:
            if len(linha) >= 4 and normaliza(linha[0]) != "VARIAVEIS":
                m.regressores.append(Regressor(
                    nome=linha[0], transformacao=linha[1], t=numero(linha[2]),
                    significancia=numero(linha[3]),
                    eh_intercepto="y" in linha[1].lower()))

    # 11/12) correlações
    m.corr_isoladas = _matriz(secoes.get("corr_isoladas", []))
    m.corr_influencia = _matriz(secoes.get("corr_influencia", []))

    # 13) resíduos
    colunas, linhas = _tabela_por_chave(secoes.get("residuos", []), "Dado")
    idx = {normaliza(c): i for i, c in enumerate(colunas)}
    i_pad, i_cook, i_pct = idx.get("RESIDUO / DP"), idx.get("DCOOK"), idx.get("RESIDUO (%)")
    for chave, vals in linhas.items():
        dado = inteiro(chave)
        if dado is None:
            continue
        m.residuos.append(Residuo(
            dado=dado,
            padronizado=numero(vals[i_pad]) if i_pad is not None else None,
            cook=numero(vals[i_cook]) if i_cook is not None else None,
            percentual=numero(vals[i_pct]) if i_pct is not None else None))

    # 14) fundamentação (pontos atribuídos pelo SisDEA)
    for tab in _tabelas(secoes.get("fundamentacao", [])):
        for linha in tab.linhas[1:]:
            item = inteiro(linha[0]) if linha else None
            if item is not None:
                m.pontos_fundamentacao_sisdea[item] = inteiro(linha[-1]) if linha[-1].strip() else None

    # 17) amostra (só a tabela de variáveis numéricas)
    blocos_num: List[Bloco] = []
    modo = "numericas"
    for b in secoes.get("amostra", [])[1:]:
        if isinstance(b, Paragrafo):
            t = normaliza(b.texto)
            if t.startswith("VARIAVEIS TEXTO"):
                modo = "texto"
            elif t.startswith("VARIAVEIS NUMERICAS"):
                modo = "numericas"
        elif modo == "numericas":
            blocos_num.append(b)
    colunas, linhas = _tabela_por_chave(blocos_num, "ID")
    for chave, vals in linhas.items():
        ident = inteiro(chave)
        if ident is None:
            continue
        reg = dict(zip(colunas, vals))
        desab = normaliza(reg.pop("Desabilitado", ""))
        m.amostra.append(LinhaAmostra(
            id=ident,
            desabilitado=bool(desab) and desab not in {"NAO", "N"},
            valores={c: numero(v) for c, v in reg.items()}))

    _valida(m)
    return m


def _valida(m: ModeloSisDEA) -> None:
    if not m.variaveis:
        m.avisos.append("Não foi possível ler a descrição das variáveis.")
    if m.variavel_dependente is None:
        m.avisos.append("Variável dependente não identificada no relatório.")
    dep = m.nome_dependente
    for v in m.variaveis:
        if v.dependente and v.nome != dep:
            m.avisos.append(f"A descrição das variáveis classifica \"{v.nome}\" como Dependente, mas no modelo ela "
                            f"é usada como variável independente (a dependente é \"{dep}\"). Confira a "
                            "classificação no cadastro do SisDEA.")
    usados = [a for a in m.amostra if not a.desabilitado]
    if m.dados_utilizados is not None and m.amostra and len(usados) != m.dados_utilizados:
        m.avisos.append(f"A tabela de dados tem {len(usados)} dados habilitados, mas o relatório "
                        f"informa {m.dados_utilizados} dados utilizados.")
    if m.dados_utilizados is not None and m.residuos and len(m.residuos) != m.dados_utilizados:
        m.avisos.append(f"A tabela de resíduos tem {len(m.residuos)} linhas, mas o relatório "
                        f"informa {m.dados_utilizados} dados utilizados.")


def interpretar_arquivo(caminho: str) -> ModeloSisDEA:
    with open(caminho, "rb") as f:
        return interpretar(f.read())
