"""Estrutura de dados do relatório do SisDEA, já interpretada."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class Variavel:
    nome: str
    tipo: str
    classificacao: str
    descricao: str
    habilitada: bool

    @property
    def dependente(self) -> bool:
        return "dependente" in self.classificacao.lower()

    @property
    def sujeita_micronumerosidade(self) -> bool:
        c = self.classificacao.lower()
        return "dicot" in c or "alocad" in c


@dataclass
class Regressor:
    nome: str
    transformacao: str
    t: Optional[float]
    significancia: Optional[float]  # em %
    eh_intercepto: bool = False     # linha da variável dependente (= intercepto)


@dataclass
class FaixaNormalidade:
    sigma: float
    curva_normal: Optional[float]  # %
    modelo: Optional[float]        # %


@dataclass
class Residuo:
    dado: int
    padronizado: Optional[float]   # Resíduo / DP
    cook: Optional[float]
    percentual: Optional[float]


@dataclass
class LinhaAmostra:
    id: int
    desabilitado: bool
    valores: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass
class MatrizCorrelacao:
    aliases: Dict[str, str] = field(default_factory=dict)   # alias -> nome
    valores: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)


@dataclass
class ModeloSisDEA:
    autor: str = ""
    modelo: str = ""
    data: str = ""
    tipologia: str = ""
    versao_sisdea: str = ""
    total_variaveis: Optional[int] = None
    variaveis_utilizadas: Optional[int] = None
    total_dados: Optional[int] = None
    dados_utilizados: Optional[int] = None
    variaveis: List[Variavel] = field(default_factory=list)
    r_equacao: Optional[float] = None       # R da equação de regressão (transformada)
    r_funcao: Optional[float] = None        # R da função estimativa (escala original)
    r2: Optional[float] = None
    f_calculado: Optional[float] = None
    significancia_modelo: Optional[float] = None  # %
    normalidade: List[FaixaNormalidade] = field(default_factory=list)
    n_outliers: Optional[int] = None
    pct_outliers: Optional[float] = None
    equacao: str = ""
    regressores: List[Regressor] = field(default_factory=list)
    corr_isoladas: MatrizCorrelacao = field(default_factory=MatrizCorrelacao)
    corr_influencia: MatrizCorrelacao = field(default_factory=MatrizCorrelacao)
    residuos: List[Residuo] = field(default_factory=list)
    pontos_fundamentacao_sisdea: Dict[int, Optional[int]] = field(default_factory=dict)
    amostra: List[LinhaAmostra] = field(default_factory=list)
    secoes_encontradas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    # ---- conveniências ----
    @property
    def nome_dependente(self) -> Optional[str]:
        """Nome da variável dependente segundo o próprio modelo: a linha com transformação em 'y'
        nos testes de hipóteses ou o alias 'y' nas correlações. Só na falta deles usa a
        classificação da descrição das variáveis (que pode estar desatualizada no SisDEA)."""
        for r in self.regressores:
            if r.eh_intercepto:
                return r.nome
        for mat in (self.corr_isoladas, self.corr_influencia):
            if "y" in mat.aliases:
                return mat.aliases["y"]
        for v in self.variaveis:
            if v.dependente:
                return v.nome
        return None

    @property
    def variavel_dependente(self) -> Optional[Variavel]:
        nome = self.nome_dependente
        if nome is None:
            return None
        return next((v for v in self.variaveis if v.nome == nome),
                    Variavel(nome, "Numérica", "Dependente", "", True))

    @property
    def independentes(self) -> List[Variavel]:
        """Variáveis independentes do modelo: habilitadas, não dependentes e não do tipo Texto
        (variáveis de texto, como o endereço, só identificam o dado). Quando a tabela de testes
        de hipóteses foi lida, ela é a referência de quais variáveis entraram no modelo."""
        dep = self.nome_dependente
        cand = [v for v in self.variaveis if v.habilitada and v.nome != dep
                and not v.tipo.strip().lower().startswith("texto")]
        no_modelo = {r.nome for r in self.regressores if not r.eh_intercepto}
        if no_modelo:
            cand = [v for v in cand if v.nome in no_modelo]
        return cand

    @property
    def k(self) -> int:
        return len(self.independentes)

    @property
    def n(self) -> Optional[int]:
        if self.dados_utilizados is not None:
            return self.dados_utilizados
        return len([a for a in self.amostra if not a.desabilitado]) or None

    def para_dict(self) -> dict:
        return asdict(self)
