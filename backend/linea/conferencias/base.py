"""Estruturas comuns às conferências."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

ATENDE = "atende"
NAO_ATENDE = "nao_atende"
NAO_VERIFICAVEL = "nao_verificavel"

ROTULO_STATUS = {ATENDE: "Atende", NAO_ATENDE: "Não atende", NAO_VERIFICAVEL: "Não verificável"}


@dataclass
class Linha:
    """Uma linha da tabela de valores de uma conferência."""
    item: str
    valor: str
    criterio: str = ""
    status: Optional[str] = None


@dataclass
class Conferencia:
    id: str
    titulo: str
    status: str
    resumo: str                       # uma frase com o veredito
    como_foi_feito: str               # método usado
    explicacao: str                   # por que atende / não atende
    linhas: List[Linha] = field(default_factory=list)
    sugestoes: List[str] = field(default_factory=list)
    observacoes: List[str] = field(default_factory=list)
    grau: Optional[str] = None        # III, II, I ou None
    testes: List[Dict] = field(default_factory=list)

    @property
    def rotulo_status(self) -> str:
        return ROTULO_STATUS[self.status]

    def para_dict(self) -> dict:
        d = asdict(self)
        d["rotulo_status"] = self.rotulo_status
        return d


def carregar_criterios(caminho: Optional[str] = None) -> dict:
    caminho = caminho or os.path.join(os.path.dirname(__file__), "..", "config", "criterios.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def fmt(x: Optional[float], casas: int = 2, pct: bool = False) -> str:
    """Formata número no padrão brasileiro."""
    if x is None:
        return "—"
    s = f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + ("%" if pct else "")
