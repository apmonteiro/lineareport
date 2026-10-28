"""Leitor de RTF em Python puro.

Converte um arquivo RTF numa sequência de blocos:
  - Paragrafo(texto)
  - Tabela(linhas=[[celula, ...], ...])

Imagens, cabeçalhos, rodapés, tabelas de fontes/cores e demais destinos
não textuais são descartados. Caracteres Unicode (\\uN) são decodificados
corretamente (ex.: ½, ², ô), o que conversores genéricos às vezes perdem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Union

# Destinos cujo conteúdo não interessa ao texto do documento.
_DESTINOS_IGNORADOS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "headerl",
    "headerr", "headerf", "footer", "footerl", "footerr", "footerf", "object",
    "themedata", "colorschememapping", "latentstyles", "datastore",
    "xmlnstbl", "listtable", "listoverridetable", "rsidtbl", "generator",
    "pntext", "pntxta", "pntxtb", "fldinst", "nonshppict", "shppict",
    "bkmkstart", "bkmkend", "revtbl", "filetbl", "mmathPr", "wgrffmtfilter",
}

_SIMBOLOS = {"tab": "\t", "line": "\n", "emdash": "—", "endash": "–",
             "bullet": "•", "lquote": "‘", "rquote": "’",
             "ldblquote": "“", "rdblquote": "”", "~": " ",
             "_": "-", "-": ""}


@dataclass
class Paragrafo:
    texto: str


@dataclass
class Tabela:
    linhas: List[List[str]] = field(default_factory=list)


Bloco = Union[Paragrafo, Tabela]


def _limpa(txt: str) -> str:
    return " ".join(txt.replace(" ", " ").split())


class _Estado:
    __slots__ = ("ignorar", "uc")

    def __init__(self, ignorar=False, uc=1):
        self.ignorar = ignorar
        self.uc = uc

    def copia(self):
        return _Estado(self.ignorar, self.uc)


def ler_blocos(dados: bytes | str, codificacao: str = "cp1252") -> List[Bloco]:
    """Lê o conteúdo RTF e devolve a lista de blocos (parágrafos e tabelas)."""
    if isinstance(dados, bytes):
        rtf = dados.decode("latin-1")  # RTF é ASCII de 7 bits; bytes altos via \\'xx
    else:
        rtf = dados
    if not rtf.lstrip().startswith("{\\rtf"):
        raise ValueError("O arquivo não é um RTF válido.")

    blocos: List[Bloco] = []
    pilha: List[_Estado] = []
    estado = _Estado()
    texto: List[str] = []          # parágrafo / célula em construção
    celula_linhas: List[str] = []  # parágrafos dentro da célula atual
    linha_atual: List[str] = []
    tabela: Tabela | None = None
    intbl = False
    pular_fallback = 0             # caracteres de fallback após \uN
    byte_pendente = bytearray()    # bytes \'xx consecutivos (multibyte)

    def descarrega_bytes():
        if byte_pendente:
            texto.append(byte_pendente.decode(codificacao, errors="replace"))
            byte_pendente.clear()

    def fecha_tabela():
        nonlocal tabela
        if tabela is not None and tabela.linhas:
            blocos.append(tabela)
        tabela = None

    def quebra_paragrafo(palavra: str):
        if intbl:
            celula_linhas.append(_limpa("".join(texto)))
            texto.clear()
        elif palavra == "par":
            fecha_tabela()
            t = _limpa("".join(texto))
            if t:
                blocos.append(Paragrafo(t))
            texto.clear()

    def emite(ch: str):
        nonlocal pular_fallback
        if estado.ignorar:
            return
        if pular_fallback > 0:
            pular_fallback -= 1
            return
        texto.append(ch)

    i, n = 0, len(rtf)
    while i < n:
        c = rtf[i]
        if c == "{":
            descarrega_bytes()
            pilha.append(estado.copia())
            i += 1
            # destino opcional {\* ...}
            if rtf.startswith("\\*", i):
                estado.ignorar = True
            continue
        if c == "}":
            descarrega_bytes()
            estado = pilha.pop() if pilha else _Estado()
            pular_fallback = 0
            i += 1
            continue
        if c in "\r\n":
            i += 1
            continue
        if c != "\\":
            descarrega_bytes()
            emite(c)
            i += 1
            continue

        # --- palavra/símbolo de controle ---
        i += 1
        if i >= n:
            break
        c = rtf[i]
        if c == "'":  # byte hexadecimal
            hexa = rtf[i + 1:i + 3]
            i += 3
            if estado.ignorar:
                continue
            if pular_fallback > 0:
                pular_fallback -= 1
                continue
            try:
                byte_pendente.append(int(hexa, 16))
            except ValueError:
                pass
            continue
        descarrega_bytes()
        if not c.isalpha():
            i += 1
            if c in "\\{}":
                emite(c)
            elif c in _SIMBOLOS:
                emite(_SIMBOLOS[c])
            elif c == "*":
                estado.ignorar = True
            elif c in "\r\n" and not estado.ignorar:  # \<newline> equivale a \par
                quebra_paragrafo("par")
            continue
        j = i
        while j < n and rtf[j].isalpha():
            j += 1
        palavra = rtf[i:j]
        k = j
        if k < n and (rtf[k] == "-" or rtf[k].isdigit()):
            k += 1
            while k < n and rtf[k].isdigit():
                k += 1
        param = rtf[j:k] or None
        if k < n and rtf[k] == " ":
            k += 1
        i = k

        if palavra in _DESTINOS_IGNORADOS:
            estado.ignorar = True
            continue
        if palavra == "fldrslt":
            estado.ignorar = False
            continue
        if palavra == "bin" and param:  # dados binários
            i += int(param)
            continue
        if estado.ignorar:
            if palavra == "uc" and param:
                estado.uc = int(param)
            continue
        if palavra == "uc" and param:
            estado.uc = int(param)
        elif palavra == "u" and param:
            cp = int(param)
            if cp < 0:
                cp += 65536
            texto.append(chr(cp))
            pular_fallback = estado.uc
        elif palavra in _SIMBOLOS:
            emite(_SIMBOLOS[palavra])
        elif palavra == "pard":
            intbl = False
        elif palavra == "intbl":
            intbl = True
        elif palavra == "trowd":
            if tabela is None:
                tabela = Tabela()
        elif palavra == "cell":
            celula_linhas.append(_limpa("".join(texto)))
            texto.clear()
            linha_atual.append(" ".join(p for p in celula_linhas if p))
            celula_linhas.clear()
        elif palavra == "row":
            if tabela is None:
                tabela = Tabela()
            tabela.linhas.append(linha_atual)
            linha_atual = []
            texto.clear()
        elif palavra in ("par", "sect", "page"):
            quebra_paragrafo(palavra)
    descarrega_bytes()
    fecha_tabela()
    t = _limpa("".join(texto))
    if t:
        blocos.append(Paragrafo(t))
    return blocos


def ler_arquivo(caminho: str) -> List[Bloco]:
    with open(caminho, "rb") as f:
        return ler_blocos(f.read())
