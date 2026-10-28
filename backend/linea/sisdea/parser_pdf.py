"""Leitura do relatório do SisDEA em PDF.

O PDF não guarda a estrutura de tabelas como o RTF: guarda palavras soltas com
posição na página. Por isso a leitura é feita linha a linha, usando o que se sabe
do layout do SisDEA:
  - seções localizadas pelo título, como no RTF;
  - tabelas numéricas lidas pela quantidade de números no fim da linha;
  - nomes de variáveis que quebram em duas linhas reconstituídos pelos nomes
    conhecidos (descrição das variáveis);
  - a tabela de descrição das variáveis lida pela posição das colunas;
  - na tabela de dados, números quebrados no meio ("8.200.000,0" + "0") são reunidos.
A conferência de consistência dos resíduos (feita depois) confirma se a leitura deu certo.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .modelo import (FaixaNormalidade, LinhaAmostra, MatrizCorrelacao, ModeloSisDEA, Regressor, Residuo,
                     Variavel)
from .parser import SECOES, SECOES_OBRIGATORIAS, ErroLeitura, _valida, inteiro, normaliza, numero

_RODAPE = ("RELATORIOS ESTATISTICOS", "SISDEA HOME", "WWW.PELLISISTEMAS")
_NUM = r"-?[\d.]+(?:,\d+)?%?"
_RE_NUM = re.compile(rf"^{_NUM}$")


@dataclass
class Palavra:
    texto: str
    x0: float
    x1: float


@dataclass
class Linha:
    palavras: List[Palavra]
    pagina: int
    texto: str = ""

    def __post_init__(self):
        self.texto = " ".join(p.texto for p in self.palavras)

    @property
    def tokens(self) -> List[str]:
        return [p.texto for p in self.palavras]


def canon(txt: str) -> str:
    """Forma canônica para comparar nomes quebrados em linhas ('Desabil itado' == 'Desabilitado')."""
    return re.sub(r"[^0-9A-Z]", "", normaliza(txt))


def _eh_num(t: str) -> bool:
    return bool(_RE_NUM.match(t))


# -----------------------------------------------------------------------------
# Extração das linhas
# -----------------------------------------------------------------------------
def _linhas_pdf(dados: bytes) -> List[Linha]:
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise ErroLeitura("Leitura de PDF indisponível: instale o pacote 'pdfplumber'.") from e
    linhas: List[Linha] = []
    try:
        pdf = pdfplumber.open(io.BytesIO(dados))
    except Exception as e:  # noqa: BLE001
        raise ErroLeitura(f"Não foi possível abrir o PDF: {e}") from e
    with pdf:
        for n, pg in enumerate(pdf.pages, start=1):
            palavras = pg.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False)
            palavras.sort(key=lambda w: (round(w["top"]), w["x0"]))
            grupo: List[dict] = []
            topo = None
            for w in palavras:
                if topo is not None and abs(w["top"] - topo) > 2.5:
                    linhas.append(_monta(grupo, n))
                    grupo = []
                if not grupo:
                    topo = w["top"]
                grupo.append(w)
            if grupo:
                linhas.append(_monta(grupo, n))
    linhas = [l for l in linhas if not normaliza(l.texto).startswith(_RODAPE)]
    # cabeçalhos/rodapés próprios do laudo: linhas idênticas repetidas em quase todas as páginas
    n_pag = max((l.pagina for l in linhas), default=0)
    if n_pag >= 3:
        from collections import Counter
        paginas_por_texto = Counter()
        for t in {(l.texto, l.pagina) for l in linhas}:
            paginas_por_texto[t[0]] += 1
        repetidas = {t for t, c in paginas_por_texto.items() if c >= max(3, 0.6 * n_pag)}
        linhas = [l for l in linhas if l.texto not in repetidas]
    if not linhas:
        raise ErroLeitura("O PDF não contém texto (pode ser um documento digitalizado). "
                          "Gere o PDF a partir do relatório do SisDEA, sem escanear.")
    return linhas


def _sem_simbolos(txt: str) -> str:
    """O Word grava a numeração automática ('1)', '13)') com fontes de símbolo, que viram
    caracteres da área privada do Unicode (U+F031 = '1'). Converte de volta."""
    return "".join(chr(ord(c) - 0xF000) if 0xF020 <= ord(c) <= 0xF0FF else c for c in txt)


def _monta(grupo: List[dict], pagina: int) -> Linha:
    grupo.sort(key=lambda w: w["x0"])
    return Linha([Palavra(_sem_simbolos(w["text"]), w["x0"], w["x1"]) for w in grupo], pagina)


def _divide_secoes(linhas: List[Linha]) -> Dict[str, List[Linha]]:
    secoes: Dict[str, List[Linha]] = {}
    atual = None
    for l in linhas:
        t = re.sub(r"^\d+\)\s*", "", normaliza(l.texto))
        achou = next((k for k, pref in SECOES.items() if t.startswith(pref)), None)
        if achou and achou not in secoes:
            atual = achou
            secoes[atual] = []
            continue
        if atual:
            secoes[atual].append(l)
    return secoes


def _pares(linhas: List[Linha]) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for l in linhas:
        if ":" in l.texto:
            rot, val = l.texto.split(":", 1)
            d[normaliza(rot).strip()] = val.strip()
    return d


# -----------------------------------------------------------------------------
# Descrição das variáveis (leitura posicional)
# -----------------------------------------------------------------------------
_TIPOS = {"NUMERICA", "TEXTO"}


def _variaveis(linhas: List[Linha]) -> List[Variavel]:
    cab = next((l for l in linhas if l.tokens and normaliza(l.tokens[0]) == "NOME"), None)
    if cab is None:
        return []
    rotulos = {"NOME": "nome", "TIPO": "tipo", "CLASSIFICACAO": "classificacao",
               "DESCRICAO": "descricao", "HABILITADA": "habilitada"}
    inicio = {}
    for p in cab.palavras:
        chave = rotulos.get(normaliza(p.texto))
        if chave and chave not in inicio:
            inicio[chave] = p.x0
    if len(inicio) < 4:
        return []
    ordem = sorted(inicio.items(), key=lambda kv: kv[1])

    def coluna(p: Palavra) -> str:
        escolhida = ordem[0][0]
        for nome, x in ordem:
            if p.x0 >= x - 3:
                escolhida = nome
        return escolhida

    regs: List[Dict[str, List[str]]] = []
    for l in linhas[linhas.index(cab) + 1:]:
        cols: Dict[str, List[str]] = {}
        for p in l.palavras:
            cols.setdefault(coluna(p), []).append(p.texto)
        hab = [t for t in l.tokens if normaliza(t) in ("SIM", "NAO")]
        nova = any(normaliza(t) in _TIPOS for t in cols.get("tipo", []))
        if nova:
            regs.append({k: list(v) for k, v in cols.items()})
            if hab:
                regs[-1]["habilitada"] = [hab[-1]]
                for k in ("descricao", "classificacao"):
                    if regs[-1].get(k) and regs[-1][k][-1] == hab[-1]:
                        regs[-1][k] = regs[-1][k][:-1]
        elif regs:
            for k, v in cols.items():
                if k != "habilitada":
                    regs[-1].setdefault(k, []).extend(v)
    out = []
    for r in regs:
        hab = " ".join(r.get("habilitada", [])) or "Sim"
        out.append(Variavel(nome=" ".join(r.get("nome", [])), tipo=" ".join(r.get("tipo", [])),
                            classificacao=" ".join(r.get("classificacao", [])),
                            descricao=" ".join(r.get("descricao", [])),
                            habilitada=normaliza(hab).startswith("SIM")))
    return out


# -----------------------------------------------------------------------------
# Tabelas "nome + números"
# -----------------------------------------------------------------------------
def _resolve_nome(nome: str, conhecidos: List[str]) -> str:
    c = canon(nome)
    for k in conhecidos:
        if canon(k) == c:
            return k
    return nome


def _linhas_nome_numeros(linhas: List[Linha], padrao: re.Pattern, conhecidos: List[str]) -> List[Tuple[str, re.Match]]:
    """Lê linhas 'nome ... valores'. Junta nomes quebrados em duas linhas usando os nomes conhecidos."""
    canon_conh = [canon(k) for k in conhecidos]
    res: List[Tuple[str, re.Match]] = []
    prefixo = ""
    for l in linhas:
        m = padrao.match(l.texto)
        if m:
            nome = (prefixo + " " + m.group(1)).strip()
            prefixo = ""
            res.append((nome, m))
            continue
        # linha sem números: pedaço de nome
        if res and canon(res[-1][0]) not in canon_conh and \
                any(k.startswith(canon(res[-1][0] + l.texto)) for k in canon_conh):
            res[-1] = (res[-1][0] + " " + l.texto, res[-1][1])
        elif any(k.startswith(canon(prefixo + l.texto)) for k in canon_conh):
            prefixo = (prefixo + " " + l.texto).strip()
    return [(_resolve_nome(n, conhecidos), m) for n, m in res]


_RE_HIP = re.compile(rf"^(.*\S)\s+(\S+)\s+({_NUM})\s+({_NUM})$")
_RE_CORR = re.compile(rf"^(.*?)\s+(x\d+|y)\s+((?:{_NUM}\s*)+)$")
_RE_NORMAL = re.compile(r"entre\s*-\s*(\d+(?:,\d+)?)\D.*?(\d+(?:,\d+)?)%\s+(\d+(?:,\d+)?)%\s*$")


def _matriz(linhas: List[Linha], conhecidos: List[str]) -> MatrizCorrelacao:
    m = MatrizCorrelacao()
    cab = next((l for l in linhas if l.tokens[:2] and normaliza(l.tokens[0]) == "VARIAVEL"), None)
    if cab is None:
        return m
    aliases = cab.tokens[2:]
    corpo = linhas[linhas.index(cab) + 1:]
    for nome, mt in _linhas_nome_numeros(corpo, _RE_CORR, conhecidos):
        alias = mt.group(2)
        vals = mt.group(3).split()
        m.aliases[alias] = nome
        m.valores[alias] = {a: numero(v) for a, v in zip(aliases, vals)}
    return m


# -----------------------------------------------------------------------------
# Tabela de dados (amostra)
# -----------------------------------------------------------------------------
def _amostra(linhas: List[Linha], variaveis: List[Variavel], avisos: List[str]) -> List[LinhaAmostra]:
    # apenas a parte de variáveis numéricas
    inicio = next((i for i, l in enumerate(linhas) if normaliza(l.texto).startswith("VARIAVEIS NUMERICAS")), -1)
    linhas = linhas[inicio + 1:]
    numericas = [v.nome for v in variaveis if normaliza(v.tipo).startswith("NUMER")]
    textos = {canon(v.nome): v.nome for v in variaveis if normaliza(v.tipo).startswith("TEXTO")}
    so_texto: List[str] = []
    registros: Dict[int, LinhaAmostra] = {}
    ordem: List[int] = []
    pos_var = 0
    i = 0
    while i < len(linhas):
        l = linhas[i]
        if not (l.tokens and normaliza(l.tokens[0]) == "ID"):
            i += 1
            continue
        # cabeçalho (pode ocupar várias linhas)
        cab = [l]
        i += 1
        while i < len(linhas) and not (linhas[i].tokens and linhas[i].tokens[0].isdigit()):
            cab.append(linhas[i])
            i += 1
        celulas = [canon(c) for c in _celulas_cabecalho(cab)]
        celulas = [c for c in celulas if c not in ("ID", "DESABILITADO")]
        if celulas and all(c in textos for c in celulas):
            # parte da tabela só com variáveis de texto (bairro, código, endereço): não interessa
            so_texto.extend(textos[c] for c in celulas if textos[c] not in so_texto)
            while i < len(linhas) and not (linhas[i].tokens and normaliza(linhas[i].tokens[0]) == "ID"):
                i += 1
            continue
        por_canon = {canon(n): n for n in numericas}
        if celulas and all(c in por_canon for c in celulas):
            colunas = [por_canon[c] for c in celulas]
        else:
            colunas = _colunas_por_cabecalho("".join(celulas), numericas, pos_var)
        if colunas is None:
            avisos.append("Não foi possível identificar as colunas da tabela de dados no PDF.")
            return list(registros.values())
        pos_var = numericas.index(colunas[-1]) + 1
        # linhas de dados
        def esperado(t: List[str]) -> int:
            return 1 + (1 if len(t) > 1 and t[1] == "*" else 0) + len(colunas)

        atual: Optional[List[str]] = None
        while i < len(linhas) and not (linhas[i].tokens and normaliza(linhas[i].tokens[0]) == "ID"):
            toks = linhas[i].tokens
            i += 1
            if not toks:
                continue
            if atual is not None and _eh_fragmento(toks, atual[-1]):
                atual[-1] += toks[0]                     # número quebrado: "8.200.000,0"+"0" ou "1.200.000"+",00"
            elif atual is not None and len(atual) < esperado(atual):
                atual.extend(toks)                       # linha da tabela quebrada em duas
            elif toks[0].isdigit():
                atual = list(toks)                       # novo dado
            else:
                continue
            if len(atual) >= esperado(atual):
                _grava(atual, colunas, registros, ordem)
    if not registros and so_texto:
        avisos.append("A tabela de dados do relatório traz apenas as variáveis de texto ("
                      + ", ".join(so_texto) + "). Os valores das variáveis numéricas não constam no documento, "
                      "por isso não é possível contar a micronumerosidade nem aplicar os testes que dependem "
                      "dos regressores. Inclua a tabela completa no laudo ou envie o .rtf do SisDEA.")
    return [registros[k] for k in ordem]


def _celulas_cabecalho(cab: List[Linha], espaco_max: float = 4.0) -> List[str]:
    """Reconstitui as células de um cabeçalho que ocupa várias linhas.
    Palavras separadas por um espaço comum formam uma célula; as linhas de baixo
    são empilhadas na coluna com que mais se sobrepõem na horizontal."""
    def agrupa(l: Linha):
        grupos: List[List[Palavra]] = []
        for p in l.palavras:
            if grupos and p.x0 - grupos[-1][-1].x1 <= espaco_max:
                grupos[-1].append(p)
            else:
                grupos.append([p])
        return [(g[0].x0, g[-1].x1, "".join(w.texto for w in g)) for g in grupos]

    colunas = [[x0, x1, txt] for x0, x1, txt in agrupa(cab[0])]
    for l in cab[1:]:
        for x0, x1, txt in agrupa(l):
            melhor = max(colunas, key=lambda c: min(c[1], x1) - max(c[0], x0))
            melhor[2] += txt
    return [c[2] for c in colunas]


def _eh_fragmento(toks: List[str], anterior: str) -> bool:
    """Linha com um único pedaço de número que completa o último valor da linha anterior.
    Linhas de dados novas têm sempre ao menos dois tokens (ID e um valor)."""
    if len(toks) != 1:
        return False
    t = toks[0]
    if re.fullmatch(r",\d{1,4}", t):                # "1.200.000" + ",00"
        return "," not in anterior
    if re.fullmatch(r"\d{1,2}", t):                 # "8.200.000,0" + "0"
        return _decimais_incompletos(anterior)
    return False


def _decimais_incompletos(t: str) -> bool:
    return bool(re.search(r",\d?$", t))


def _grava(toks: List[str], colunas: List[str], registros: Dict[int, LinhaAmostra], ordem: List[int]) -> None:
    ident = int(toks[0])
    desab = len(toks) > 1 and toks[1] == "*"
    valores = toks[2:] if desab else toks[1:]
    if ident not in registros:
        registros[ident] = LinhaAmostra(id=ident, desabilitado=desab)
        ordem.append(ident)
    reg = registros[ident]
    reg.desabilitado = reg.desabilitado or desab
    for c, v in zip(colunas, valores):
        reg.valores[c] = numero(v)


def _colunas_por_cabecalho(alvo: str, nomes: List[str], inicio: int) -> Optional[List[str]]:
    """Encontra a sequência de variáveis cujos nomes, juntos, formam o cabeçalho."""
    for ini in list(range(inicio, len(nomes))) + list(range(0, inicio)):
        acumulado = ""
        for fim in range(ini, len(nomes)):
            acumulado += canon(nomes[fim])
            if acumulado == alvo:
                return nomes[ini:fim + 1]
            if not alvo.startswith(acumulado):
                break
    return None


# -----------------------------------------------------------------------------
# Montagem do modelo
# -----------------------------------------------------------------------------
def interpretar_pdf(dados: bytes) -> ModeloSisDEA:
    linhas = _linhas_pdf(dados)
    secoes = _divide_secoes(linhas)
    m = ModeloSisDEA()
    m.secoes_encontradas = list(secoes.keys())
    faltando = [SECOES[s].title() for s in SECOES_OBRIGATORIAS if s not in secoes]
    if len(faltando) == len(SECOES_OBRIGATORIAS):
        raise ErroLeitura("O PDF não parece ser um relatório estatístico do SisDEA "
                          "(nenhuma das seções esperadas foi encontrada).")
    for f in faltando:
        m.avisos.append(f"Seção não encontrada no relatório: {f}.")

    p = _pares(secoes.get("info_basicas", []))
    m.autor, m.modelo = p.get("AUTOR", ""), p.get("MODELO", "")
    m.data, m.tipologia = p.get("DATA DO MODELO", ""), p.get("TIPOLOGIA", "")

    p = _pares(secoes.get("info_complementares", []))
    m.total_variaveis = inteiro(p.get("TOTAL DE VARIAVEIS"))
    m.variaveis_utilizadas = inteiro(p.get("VARIAVEIS UTILIZADAS NO MODELO"))
    m.total_dados = inteiro(p.get("TOTAL DE DADOS"))
    m.dados_utilizados = inteiro(p.get("DADOS UTILIZADOS NO MODELO"))

    m.variaveis = _variaveis(secoes.get("variaveis", []))
    nomes = [v.nome for v in m.variaveis]

    p = _pares(secoes.get("coeficientes", []))
    partes = [numero(x) for x in p.get("COEFICIENTE DE CORRELACAO", "").split("/")]
    if partes:
        m.r_equacao = partes[0]
    if len(partes) > 1:
        m.r_funcao = partes[1]
    m.r2 = numero(p.get("COEFICIENTE DE DETERMINACAO"))
    m.f_calculado = numero(p.get("FISHER - SNEDECOR"))
    m.significancia_modelo = numero(p.get("SIGNIFICANCIA DO MODELO (%)"))

    for l in secoes.get("normalidade", []):
        mt = _RE_NORMAL.search(l.texto)
        if mt:
            m.normalidade.append(FaixaNormalidade(numero(mt.group(1)), numero(mt.group(2)), numero(mt.group(3))))

    p = _pares(secoes.get("outliers", []))
    m.n_outliers = inteiro(p.get("QUANTIDADE DE OUTLIERS"))
    m.pct_outliers = numero(p.get("% DE OUTLIERS"))

    m.equacao = " ".join(l.texto for l in secoes.get("equacao", []))

    hip = [l for l in secoes.get("hipoteses", []) if normaliza(l.texto)[:9] != "VARIAVEIS"]
    for nome, mt in _linhas_nome_numeros(hip, _RE_HIP, nomes):
        m.regressores.append(Regressor(nome=nome, transformacao=mt.group(2), t=numero(mt.group(3)),
                                       significancia=numero(mt.group(4)),
                                       eh_intercepto="y" in mt.group(2).lower()))

    m.corr_isoladas = _matriz(secoes.get("corr_isoladas", []), nomes)
    m.corr_influencia = _matriz(secoes.get("corr_influencia", []), nomes)

    for l in secoes.get("residuos", []):
        t = l.tokens
        if len(t) == 7 and t[0].isdigit() and all(_eh_num(x) for x in t[1:]):
            m.residuos.append(Residuo(dado=int(t[0]), padronizado=numero(t[5]), cook=numero(t[6]),
                                      percentual=numero(t[4])))

    m.amostra = _amostra(secoes.get("amostra", []), m.variaveis, m.avisos)
    _valida(m)
    return m
