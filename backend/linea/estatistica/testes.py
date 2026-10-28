"""Testes estatísticos sobre os resíduos informados pelo SisDEA.

Nenhum teste aqui refaz o modelo do avaliador. Os testes de homocedasticidade
e de autocorrelação usam apenas regressões AUXILIARES (resíduos contra
regressores), como prevê a própria definição de cada teste.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
from scipy import stats


@dataclass
class ResultadoTeste:
    nome: str
    estatistica: Optional[float]
    p_valor: Optional[float]
    gl: Optional[float] = None
    rejeita_h0: Optional[bool] = None
    observacao: str = ""
    detalhes: Dict = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Transformações do SisDEA (x, 1/x, x², 1/x², x½, 1/x½, ln(x), 1/ln(x), ...)
# ----------------------------------------------------------------------------
_EXPOENTES = {"": 1.0, "²": 2.0, "³": 3.0, "½": 0.5, "⅓": 1 / 3, "¼": 0.25}


def funcao_transformacao(rotulo: str) -> Optional[Callable[[np.ndarray], np.ndarray]]:
    """Converte o rótulo da coluna 'Transf.' numa função. None se desconhecido."""
    r = rotulo.strip().replace(" ", "").lower()
    inversa = r.startswith("1/")
    if inversa:
        r = r[2:]
    m = re.fullmatch(r"(?:ln\(([xy])\)|([xy])|e\^?\(?([xy])\)?|exp\(([xy])\))"
                     r"(\^?\(?-?[\d.,/]+\)?|[²³½⅓¼])?", r)
    if not m:
        return None
    base_ln = m.group(1) is not None
    base_exp = m.group(3) is not None or m.group(4) is not None
    exp_txt = (m.group(5) or "").replace("^", "").replace("(", "").replace(")", "")
    if exp_txt in _EXPOENTES:
        expo = _EXPOENTES[exp_txt]
    else:
        try:
            if "/" in exp_txt:
                a, b = exp_txt.split("/")
                expo = float(a) / float(b)
            else:
                expo = float(exp_txt.replace(",", "."))
        except ValueError:
            return None

    def f(v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        if base_ln:
            b = np.log(v)
        elif base_exp:
            b = np.exp(v)
        else:
            b = v
        out = np.power(b, expo)
        return 1.0 / out if inversa else out

    return f


# ----------------------------------------------------------------------------
# Regressão auxiliar
# ----------------------------------------------------------------------------
def _remove_colineares(X: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    """Remove colunas linearmente dependentes (ex.: dicotômica² = dicotômica)."""
    escolhidas: List[int] = []
    for j in range(X.shape[1]):
        cand = escolhidas + [j]
        Xs = X[:, cand]
        Xs = Xs / np.where(np.abs(Xs).max(axis=0) == 0, 1, np.abs(Xs).max(axis=0))
        if np.linalg.matrix_rank(Xs, tol=tol * max(Xs.shape)) == len(cand):
            escolhidas.append(j)
    return X[:, escolhidas]


def r2_auxiliar(y: np.ndarray, X: np.ndarray) -> float:
    """R² de y contra X (X já contém a constante)."""
    Xn = X / np.where(np.abs(X).max(axis=0) == 0, 1, np.abs(X).max(axis=0))
    b, *_ = np.linalg.lstsq(Xn, y, rcond=None)
    r = y - Xn @ b
    sqt = np.sum((y - y.mean()) ** 2)
    return float(1 - (r @ r) / sqt) if sqt > 0 else 0.0


def com_constante(Z: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(Z.shape[0]), Z])


# ----------------------------------------------------------------------------
# Normalidade
# ----------------------------------------------------------------------------
def jarque_bera(e: np.ndarray, alfa: float) -> ResultadoTeste:
    r = stats.jarque_bera(e)
    p = float(r.pvalue)
    return ResultadoTeste("Jarque-Bera", float(r.statistic), p, 2, p < alfa,
                          detalhes={"assimetria": float(stats.skew(e)),
                                    "curtose": float(stats.kurtosis(e, fisher=False))})


def kolmogorov_smirnov_lilliefors(e: np.ndarray, alfa: float,
                                  simulacoes: int = 20000, semente: int = 14653) -> ResultadoTeste:
    """K-S contra a normal com média e desvio estimados (correção de Lilliefors).
    O p-valor é obtido por simulação com semente fixa, logo é reprodutível."""
    e = np.asarray(e, dtype=float)
    n = len(e)

    def d_stat(amostras: np.ndarray) -> np.ndarray:
        z = (amostras - amostras.mean(axis=-1, keepdims=True)) / amostras.std(axis=-1, ddof=1, keepdims=True)
        z.sort(axis=-1)
        cdf = stats.norm.cdf(z)
        i = np.arange(1, n + 1)
        return np.maximum((i / n - cdf).max(axis=-1), (cdf - (i - 1) / n).max(axis=-1))

    d = float(d_stat(e[None, :])[0])
    rng = np.random.default_rng(semente)
    sim = d_stat(rng.standard_normal((simulacoes, n)))
    p = float((np.sum(sim >= d) + 1) / (simulacoes + 1))
    return ResultadoTeste("Kolmogorov-Smirnov (Lilliefors)", d, p, None, p < alfa)


def qui_quadrado(e: np.ndarray, alfa: float) -> ResultadoTeste:
    """Aderência à normal com classes equiprováveis e ao menos 5 dados esperados por classe."""
    e = np.asarray(e, dtype=float)
    n = len(e)
    classes = max(4, min(10, n // 5))
    z = (e - e.mean()) / e.std(ddof=1)
    cortes = stats.norm.ppf(np.linspace(0, 1, classes + 1)[1:-1])
    obs = np.bincount(np.searchsorted(cortes, z), minlength=classes)
    esp = np.full(classes, n / classes)
    gl = classes - 3  # média e desvio estimados
    est = float(np.sum((obs - esp) ** 2 / esp))
    p = float(stats.chi2.sf(est, gl))
    obsv = "Com menos de 20 dados o teste tem baixo poder." if n < 20 else ""
    if n / classes < 5:
        obsv = (obsv + " Frequência esperada por classe abaixo de 5; resultado apenas indicativo.").strip()
    return ResultadoTeste("Qui-quadrado", est, p, gl, p < alfa, obsv,
                          {"classes": classes, "observadas": obs.tolist(), "esperada_por_classe": n / classes})


# ----------------------------------------------------------------------------
# Homocedasticidade
# ----------------------------------------------------------------------------
def breusch_pagan(e: np.ndarray, X: np.ndarray, alfa: float) -> ResultadoTeste:
    """Versão de Koenker (robusta à não normalidade): LM = n·R² de e² contra X."""
    n = len(e)
    Xc = _remove_colineares(X)
    lm = n * r2_auxiliar(e ** 2, Xc)
    gl = Xc.shape[1] - 1
    p = float(stats.chi2.sf(lm, gl))
    return ResultadoTeste("Breusch-Pagan (Koenker)", lm, p, gl, p < alfa)


def white(e: np.ndarray, X: np.ndarray, alfa: float) -> ResultadoTeste:
    """Teste de White: e² contra regressores, quadrados e produtos cruzados.
    Se faltarem graus de liberdade, usa só regressores e quadrados."""
    n = len(e)
    Z = X[:, 1:]
    k = Z.shape[1]
    termos = [Z[:, i] for i in range(k)]
    quad = [Z[:, i] ** 2 for i in range(k)]
    cruz = [Z[:, i] * Z[:, j] for i in range(k) for j in range(i + 1, k)]
    obs = ""
    aux = com_constante(np.column_stack(termos + quad + cruz))
    aux = _remove_colineares(aux)
    if aux.shape[1] >= n - 1:
        aux = _remove_colineares(com_constante(np.column_stack(termos + quad)))
        obs = "Dados insuficientes para os produtos cruzados; usados apenas regressores e seus quadrados."
    lm = n * r2_auxiliar(e ** 2, aux)
    gl = aux.shape[1] - 1
    p = float(stats.chi2.sf(lm, gl))
    return ResultadoTeste("White", lm, p, gl, p < alfa, obs)


def park(e: np.ndarray, X: np.ndarray, nomes: List[str], alfa: float) -> ResultadoTeste:
    """Teste de Park: ln(e²) = a + b·ln(Xj), para cada regressor positivo.
    Rejeita H0 se algum b for significativo."""
    n = len(e)
    e2 = e ** 2
    validos = e2 > 0
    por_var = []
    piores = None
    for j, nome in enumerate(nomes, start=1):
        x = X[:, j]
        if np.any(x[validos] <= 0) or np.allclose(x, x[0]):
            por_var.append({"variavel": nome, "aplicavel": False})
            continue
        lx, ly = np.log(x[validos]), np.log(e2[validos])
        res = stats.linregress(lx, ly)
        p = float(res.pvalue)
        por_var.append({"variavel": nome, "aplicavel": True, "b": float(res.slope),
                        "t": float(res.slope / res.stderr) if res.stderr else None, "p_valor": p})
        if piores is None or p < piores["p_valor"]:
            piores = por_var[-1]
    if piores is None:
        return ResultadoTeste("Park", None, None, None, None,
                              "Nenhum regressor estritamente positivo para aplicar o teste.",
                              {"por_variavel": por_var})
    p_min = piores["p_valor"]
    obs = ""
    nao_aplic = [v["variavel"] for v in por_var if not v["aplicavel"]]
    if nao_aplic:
        obs = "Não aplicável (valores nulos/negativos ou constantes): " + ", ".join(nao_aplic) + "."
    return ResultadoTeste("Park", piores.get("t"), p_min, n - 2, p_min < alfa, obs,
                          {"por_variavel": por_var, "variavel_critica": piores["variavel"]})


# ----------------------------------------------------------------------------
# Autocorrelação
# ----------------------------------------------------------------------------
def breusch_godfrey(e: np.ndarray, X: np.ndarray, alfa: float, defasagens: int = 1) -> ResultadoTeste:
    n = len(e)
    lags = [np.r_[np.zeros(h), e[:-h]] for h in range(1, defasagens + 1)]
    aux = np.column_stack([X] + lags)
    lm = n * r2_auxiliar(e, aux)
    p = float(stats.chi2.sf(lm, defasagens))
    return ResultadoTeste("Breusch-Godfrey", lm, p, defasagens, p < alfa)


def fmt_p(p: Optional[float]) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return "< 0,0001" if p < 1e-4 else f"{p:.4f}".replace(".", ",")
