"""Estatística de Durbin-Watson e seus valores críticos (dL, dU).

Os limites dL e dU são calculados pela distribuição exata (método de Imhof),
da mesma forma que as tabelas de Savin & White (1977). Assim o app funciona
para qualquer n e k sem depender de uma tabela embutida.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import numpy as np
from scipy import integrate, optimize


def estatistica_dw(residuos) -> float:
    e = np.asarray(residuos, dtype=float)
    return float(np.sum(np.diff(e) ** 2) / np.sum(e ** 2))


def _prob_menor(lambdas: np.ndarray, d: float) -> float:
    """P( sum(l_i z_i^2) / sum(z_i^2) < d ),  z_i ~ N(0,1)  (Imhof, 1961)."""
    lam = lambdas - d

    def integrando(u):
        if u == 0:
            return 0.5 * np.sum(lam)
        theta = 0.5 * np.sum(np.arctan(lam * u))
        rho = np.prod((1.0 + (lam * u) ** 2) ** 0.25)
        return np.sin(theta) / (u * rho)

    val, _ = integrate.quad(integrando, 0, np.inf, limit=500)
    p_maior = 0.5 + val / np.pi
    return float(min(max(1.0 - p_maior, 0.0), 1.0))


@lru_cache(maxsize=256)
def valores_criticos(n: int, k: int, alfa: float = 0.05) -> Tuple[float, float]:
    """dL e dU para n observações e k regressores (sem contar o intercepto)."""
    p = k + 1
    if n - p < 2:
        raise ValueError("Graus de liberdade insuficientes para o Durbin-Watson.")
    j = np.arange(1, n + 1)
    nu = 2.0 * (1.0 - np.cos(np.pi * (j - 1) / n))  # autovalores da matriz do DW
    nu.sort()
    lam_l = nu[1:n - p + 1]          # menores n-p autovalores não nulos
    lam_u = nu[p:n]                  # maiores n-p autovalores

    def quantil(lams):
        return optimize.brentq(lambda d: _prob_menor(lams, d) - alfa,
                               lams.min() + 1e-9, lams.max() - 1e-9, xtol=1e-6)

    return round(quantil(lam_l), 3), round(quantil(lam_u), 3)


def classificar(d: float, dl: float, du: float) -> str:
    """Classifica nas cinco regiões do teste bicaudal."""
    if d < dl:
        return "autorregressao_positiva"
    if d <= du:
        return "inconclusiva"
    if d < 4 - du:
        return "nao_autorregressao"
    if d <= 4 - dl:
        return "inconclusiva"
    return "autorregressao_negativa"
