"""Conferências do modelo: pressupostos, micronumerosidade e testes de hipóteses.

Cada função recebe o Contexto e devolve uma Conferencia com o veredito,
o método, a explicação e, quando reprovada, sugestões de correção.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..estatistica import durbin_watson as dw
from ..estatistica import testes as T
from ..sisdea.modelo import ModeloSisDEA
from .base import (ATENDE, NAO_ATENDE, NAO_VERIFICAVEL, Conferencia, Linha, fmt)

ORDEM_GRAUS = ["III", "II", "I"]


# ----------------------------------------------------------------------------
# Contexto: resíduos e regressores transformados alinhados por dado
# ----------------------------------------------------------------------------
@dataclass
class Contexto:
    m: ModeloSisDEA
    crit: dict
    alfa: float
    e: Optional[np.ndarray] = None           # resíduos padronizados (Resíduo / DP)
    dados: List[int] = field(default_factory=list)
    X: Optional[np.ndarray] = None           # com constante, regressores transformados
    nomes_x: List[str] = field(default_factory=list)
    motivo_sem_x: str = ""
    consistencia: Dict = field(default_factory=dict)
    observacoes: List[str] = field(default_factory=list)

    @property
    def x_confiavel(self) -> bool:
        return self.X is not None and self.consistencia.get("ok", False)


def preparar_contexto(m: ModeloSisDEA, crit: dict) -> Contexto:
    ctx = Contexto(m=m, crit=crit, alfa=crit.get("nivel_significancia_testes", 0.05))
    res = [r for r in m.residuos if r.padronizado is not None]
    if res:
        ctx.e = np.array([r.padronizado for r in res])
        ctx.dados = [r.dado for r in res]

    # --- regressores transformados (para as regressões auxiliares) ---
    if ctx.e is None:
        ctx.motivo_sem_x = "a tabela de resíduos não foi encontrada"
        return ctx
    transf = {r.nome: r.transformacao for r in m.regressores if not r.eh_intercepto}
    habilitados = {a.id: a for a in m.amostra if not a.desabilitado}
    if not habilitados:
        ctx.motivo_sem_x = ("a tabela de dados da amostra, com os valores das variáveis numéricas, não foi "
                            "encontrada no relatório")
        return ctx
    if all(d in habilitados for d in ctx.dados):
        linhas = [habilitados[d] for d in ctx.dados]
    elif len(habilitados) == len(ctx.dados):
        linhas = [habilitados[i] for i in sorted(habilitados)]
        ctx.observacoes.append("Os números da tabela de resíduos não coincidem com os IDs da amostra; "
                               "os dados foram associados pela ordem.")
    else:
        ctx.motivo_sem_x = "não foi possível associar a tabela de resíduos à tabela de dados"
        return ctx

    colunas = []
    for v in m.independentes:
        if v.nome not in transf:
            ctx.motivo_sem_x = f"a transformação da variável '{v.nome}' não consta nos testes de hipóteses"
            return ctx
        f = T.funcao_transformacao(transf[v.nome])
        if f is None:
            ctx.motivo_sem_x = f"transformação '{transf[v.nome]}' da variável '{v.nome}' não reconhecida"
            return ctx
        brutos = [a.valores.get(v.nome) for a in linhas]
        if any(b is None for b in brutos):
            ctx.motivo_sem_x = f"há valores ausentes ou não numéricos na variável '{v.nome}'"
            return ctx
        with np.errstate(all="ignore"):
            col = f(np.array(brutos, dtype=float))
        if not np.all(np.isfinite(col)):
            ctx.motivo_sem_x = f"a transformação de '{v.nome}' gerou valores inválidos"
            return ctx
        colunas.append(col)
        ctx.nomes_x.append(v.nome)
    ctx.X = T.com_constante(np.column_stack(colunas)) if colunas else None
    ctx.consistencia = _confere_leitura(ctx, linhas)
    return ctx


def _confere_leitura(ctx: Contexto, linhas) -> Dict:
    """Confirma que dados + transformações lidos reproduzem os resíduos do relatório.
    Serve apenas para validar a LEITURA; as conclusões usam os valores do SisDEA."""
    m = ctx.m
    dep = m.variavel_dependente
    rot = next((r.transformacao for r in m.regressores if r.eh_intercepto), None)
    if dep is None or rot is None or ctx.X is None:
        return {"ok": False, "motivo": "transformação da variável dependente não identificada"}
    f = T.funcao_transformacao(rot)
    y = [a.valores.get(dep.nome) for a in linhas]
    if f is None or any(v is None for v in y):
        return {"ok": False, "motivo": "não foi possível ler a variável dependente"}
    with np.errstate(all="ignore"):
        yt = f(np.array(y, dtype=float))
    X = ctx.X
    escala = np.abs(X).max(axis=0)
    b, *_ = np.linalg.lstsq(X / escala, yt, rcond=None)
    r = yt - (X / escala) @ b
    gl = len(yt) - X.shape[1]
    if gl <= 0:
        return {"ok": False, "motivo": "graus de liberdade insuficientes"}
    s = np.sqrt(r @ r / gl)
    dif = float(np.max(np.abs(r / s - ctx.e)))
    tol = ctx.crit.get("consistencia_leitura", {}).get("tolerancia_residuo_padronizado", 0.01)
    return {"ok": dif <= tol, "diferenca_maxima": dif, "tolerancia": tol,
            "motivo": "" if dif <= tol else "os resíduos reconstituídos não coincidem com os do relatório"}


def _teste_dict(t: T.ResultadoTeste) -> dict:
    return asdict(t)


def _decide_por_maioria(resultados: List[T.ResultadoTeste]) -> Optional[bool]:
    validos = [r for r in resultados if r.rejeita_h0 is not None]
    if not validos:
        return None
    nao_rejeitam = sum(1 for r in validos if not r.rejeita_h0)
    return nao_rejeitam > len(validos) / 2


def _linha_teste(t: T.ResultadoTeste, alfa: float, h0: str) -> Linha:
    if t.p_valor is None:
        return Linha(t.nome, "não aplicável", "", NAO_VERIFICAVEL)
    concl = f"rejeita {h0}" if t.rejeita_h0 else f"não rejeita {h0}"
    return Linha(t.nome, f"p-valor = {T.fmt_p(t.p_valor)} ({concl})",
                 f"p-valor > {fmt(alfa * 100, 0)}%", NAO_ATENDE if t.rejeita_h0 else ATENDE)


# ----------------------------------------------------------------------------
# 1. Linearidade
# ----------------------------------------------------------------------------
def linearidade(ctx: Contexto) -> Conferencia:
    c = ctx.crit["linearidade"]
    rmin = c["r_minimo"]
    m = ctx.m
    pares = []
    if "equacao" in c["verificar"]:
        pares.append(("R da equação de regressão (transformada)", m.r_equacao))
    if "funcao" in c["verificar"]:
        pares.append(("R da função estimativa (escala original)", m.r_funcao))
    linhas, falhas, ausentes = [], [], []
    for nome, r in pares:
        if r is None:
            ausentes.append(nome)
            linhas.append(Linha(nome, "não informado", f"> {fmt(rmin)}", NAO_VERIFICAVEL))
            continue
        ok = r > rmin
        linhas.append(Linha(nome, fmt(r, 4), f"> {fmt(rmin)}", ATENDE if ok else NAO_ATENDE))
        if not ok:
            falhas.append((nome, r))
    como = (f"Leitura do campo \"Coeficiente de correlação\" do relatório. O SisDEA informa dois valores: "
            f"o primeiro é o R da equação de regressão, na escala transformada; o segundo é o R da função "
            f"estimativa, calculado na escala original da variável dependente. Ambos foram comparados com o "
            f"mínimo de {fmt(rmin)} recomendado pela {c['fonte']}.")
    if len(ausentes) == len(pares):
        return Conferencia("linearidade", "Linearidade", NAO_VERIFICAVEL,
                           "O coeficiente de correlação não foi encontrado no relatório.", como,
                           "Sem o coeficiente de correlação não é possível fazer a conferência.", linhas)
    if falhas:
        nomes = "; ".join(f"{n.split(' (')[0]} = {fmt(r, 4)}" for n, r in falhas)
        return Conferencia(
            "linearidade", "Linearidade", NAO_ATENDE,
            f"Coeficiente de correlação abaixo de {fmt(rmin)}.", como,
            f"{nomes}. Valores abaixo de {fmt(rmin)} indicam que as variáveis, com as transformações "
            f"adotadas, explicam de forma fraca a variação do valor. Quando apenas o R da função estimativa "
            f"fica baixo, o ajuste é bom na escala transformada mas se perde ao voltar para a escala original.",
            linhas, sugestoes=[
                "Testar outras transformações das variáveis independentes e da dependente.",
                "Verificar se falta alguma variável explicativa relevante (localização, padrão, etc.).",
                "Examinar dados discrepantes e a homogeneidade da amostra.",
            ])
    return Conferencia(
        "linearidade", "Linearidade", ATENDE,
        f"Coeficientes de correlação acima de {fmt(rmin)}.", como,
        "Os coeficientes indicam forte correlação entre os valores observados e os estimados pelo modelo, "
        "tanto na escala transformada quanto na escala original.", linhas,
        observacoes=["O coeficiente de correlação mede o poder de explicação do modelo. A linearidade de cada "
                     "variável também deve ser observada nos gráficos de resíduos do relatório."])


# ----------------------------------------------------------------------------
# 2. Normalidade
# ----------------------------------------------------------------------------
def normalidade(ctx: Contexto) -> Conferencia:
    c = ctx.crit["normalidade"]
    m = ctx.m
    linhas, falhas = [], []
    for faixa in c["faixas"]:
        lida = next((f for f in m.normalidade if abs(f.sigma - faixa["sigma"]) < 1e-6), None)
        rot = f"Resíduos entre −{fmt(faixa['sigma'], 2 if faixa['sigma'] % 1 else 0)}σ e +{fmt(faixa['sigma'], 2 if faixa['sigma'] % 1 else 0)}σ"
        crit_txt = f"{fmt(faixa['minimo'], 0)}% a {fmt(faixa['maximo'], 0)}%"
        if lida is None or lida.modelo is None:
            linhas.append(Linha(rot, "não informado", crit_txt, NAO_VERIFICAVEL))
            falhas.append(rot)
            continue
        ok = faixa["minimo"] <= lida.modelo <= faixa["maximo"]
        linhas.append(Linha(rot, fmt(lida.modelo, 0, True), crit_txt, ATENDE if ok else NAO_ATENDE))
        if not ok:
            falhas.append(rot)
    como = (f"Comparação da distribuição dos resíduos padronizados informada pelo SisDEA com os intervalos "
            f"sugeridos pelo {c['fonte']}.")
    if not falhas:
        return Conferencia("normalidade", "Normalidade dos resíduos", ATENDE,
                           "A distribuição dos resíduos está dentro dos intervalos de referência.", como,
                           "As proporções de resíduos em cada intervalo são compatíveis com uma distribuição "
                           "normal, o que valida os testes de hipóteses do modelo.", linhas)

    if ctx.e is None or len(ctx.e) < 8:
        return Conferencia("normalidade", "Normalidade dos resíduos", NAO_ATENDE,
                           "A distribuição dos resíduos está fora dos intervalos de referência.", como,
                           "Os resíduos não foram encontrados (ou são poucos) para aplicar os testes estatísticos.",
                           linhas, sugestoes=_sug_normalidade())
    como += (" Como houve divergência, foram aplicados aos resíduos padronizados os testes de aderência "
             f"Qui-quadrado, Kolmogorov-Smirnov (com correção de Lilliefors) e Jarque-Bera, ao nível de "
             f"{fmt(ctx.alfa * 100, 0)}%. H0: os resíduos seguem distribuição normal. "
             "A decisão é tomada pela maioria dos testes.")
    mapa = {"qui_quadrado": T.qui_quadrado, "kolmogorov_smirnov": T.kolmogorov_smirnov_lilliefors,
            "jarque_bera": T.jarque_bera}
    res = [mapa[t](ctx.e, ctx.alfa) for t in c["testes_quando_faixas_falham"] if t in mapa]
    for r in res:
        linhas.append(_linha_teste(r, ctx.alfa, "a normalidade"))
    obs = [f"{r.nome}: {r.observacao}" for r in res if r.observacao]
    normal = _decide_por_maioria(res)
    fora = ", ".join(falhas)
    if normal:
        rejeitam = [r.nome for r in res if r.rejeita_h0]
        extra = f" Apenas {', '.join(rejeitam)} rejeitou a normalidade." if rejeitam else \
            " Nenhum dos testes rejeitou a hipótese de normalidade."
        return Conferencia(
            "normalidade", "Normalidade dos resíduos", ATENDE,
            "Fora do intervalo de referência em uma ou mais faixas, mas a normalidade foi confirmada pelos testes.",
            como, f"Faixa(s) fora do intervalo: {fora}. Os testes estatísticos, que são mais confiáveis que a "
                  f"simples contagem por faixas, indicam que não há evidência para rejeitar a normalidade dos "
                  f"resíduos.{extra}", linhas, observacoes=obs,
            testes=[_teste_dict(r) for r in res])
    return Conferencia(
        "normalidade", "Normalidade dos resíduos", NAO_ATENDE,
        "Os resíduos não apresentam distribuição normal.", como,
        f"Faixa(s) fora do intervalo: {fora}, e a maioria dos testes estatísticos rejeitou a normalidade. "
        "Sem normalidade, os testes t e F do modelo perdem validade.", linhas,
        sugestoes=_sug_normalidade(), observacoes=obs, testes=[_teste_dict(r) for r in res])


def _sug_normalidade() -> List[str]:
    return ["Verificar os dados com maiores resíduos (outliers) quanto a erros de cadastro ou de informação.",
            "Testar outra transformação da variável dependente (ln(y), 1/y, y½).",
            "Verificar se falta variável explicativa relevante.",
            "Ampliar a amostra, se possível."]


# ----------------------------------------------------------------------------
# 3. Homocedasticidade
# ----------------------------------------------------------------------------
def _sem_x(ctx: Contexto) -> str:
    if ctx.X is None:
        return ctx.motivo_sem_x or "os regressores não puderam ser montados"
    return ctx.consistencia.get("motivo", "a leitura dos dados não pôde ser confirmada")


def homocedasticidade(ctx: Contexto) -> Conferencia:
    c = ctx.crit["homocedasticidade"]
    como = ("Testes aplicados aos resíduos padronizados do relatório, por meio de regressões auxiliares contra "
            "as variáveis independentes já transformadas (lidas da tabela de dados e da coluna \"Transf.\"). "
            f"Nível de significância de {fmt(ctx.alfa * 100, 0)}%. H0: a variância dos resíduos é constante "
            "(homocedasticidade). A decisão é tomada pela maioria dos testes.")
    if ctx.e is None or not ctx.x_confiavel:
        return Conferencia("homocedasticidade", "Homocedasticidade", NAO_VERIFICAVEL,
                           "Não foi possível aplicar os testes.", como,
                           f"Os testes não foram aplicados porque {_sem_x(ctx)}.")
    res = []
    for t in c["testes"]:
        if t == "park":
            res.append(T.park(ctx.e, ctx.X, ctx.nomes_x, ctx.alfa))
        elif t == "white":
            res.append(T.white(ctx.e, ctx.X, ctx.alfa))
        elif t == "breusch_pagan":
            res.append(T.breusch_pagan(ctx.e, ctx.X, ctx.alfa))
    linhas = [_linha_teste(r, ctx.alfa, "a homocedasticidade") for r in res]
    obs = [f"{r.nome}: {r.observacao}" for r in res if r.observacao]
    for r in res:
        if r.nome == "Park" and r.detalhes.get("variavel_critica") and r.p_valor is not None:
            obs.append(f"Park: menor p-valor na variável \"{r.detalhes['variavel_critica']}\".")
    ok = _decide_por_maioria(res)
    if ok is None:
        return Conferencia("homocedasticidade", "Homocedasticidade", NAO_VERIFICAVEL,
                           "Nenhum teste pôde ser aplicado.", como, "Os testes não se aplicam a estes dados.",
                           linhas, observacoes=obs)
    rejeitam = [r.nome for r in res if r.rejeita_h0]
    if ok:
        extra = f" Divergência: {', '.join(rejeitam)} indicou heterocedasticidade." if rejeitam else ""
        return Conferencia("homocedasticidade", "Homocedasticidade", ATENDE,
                           "Os resíduos apresentam variância constante.", como,
                           "A maioria dos testes não rejeitou a hipótese de homocedasticidade: a dispersão dos "
                           f"resíduos não depende das variáveis do modelo.{extra}", linhas,
                           observacoes=obs, testes=[_teste_dict(r) for r in res])
    return Conferencia(
        "homocedasticidade", "Homocedasticidade", NAO_ATENDE,
        "Há indícios de heterocedasticidade.", como,
        f"{', '.join(rejeitam)} rejeitou(aram) a hipótese de variância constante. Com heterocedasticidade, "
        "os estimadores continuam não viesados, mas os erros-padrão (e, portanto, os testes t e F) deixam de "
        "ser confiáveis.", linhas,
        sugestoes=["Testar a transformação logarítmica (ou outra) da variável dependente.",
                   "Verificar a variável apontada pelo teste de Park e testar outra transformação para ela.",
                   "Avaliar se a amostra mistura segmentos de mercado distintos.",
                   "Conferir o gráfico de resíduos × valores estimados do relatório."],
        observacoes=obs, testes=[_teste_dict(r) for r in res])


# ----------------------------------------------------------------------------
# 4. Autocorrelação
# ----------------------------------------------------------------------------
_ROT_DW = {"autorregressao_positiva": "Autorregressão positiva",
           "autorregressao_negativa": "Autorregressão negativa",
           "inconclusiva": "Região não conclusiva",
           "nao_autorregressao": "Não autorregressão"}


def autocorrelacao(ctx: Contexto) -> Conferencia:
    c = ctx.crit["autocorrelacao"]
    m = ctx.m
    como = ("O relatório do SisDEA não traz o teste de Durbin-Watson; a estatística D foi calculada a partir da "
            "coluna \"Resíduo / DP\", na ordem em que os dados aparecem. Os limites dL e dU foram obtidos pela "
            f"distribuição exata para n dados e k variáveis independentes, com {c['descricao_confianca']} de "
            "confiança (5% em cada cauda). Na região não conclusiva aplica-se o teste de Breusch-Godfrey.")
    if ctx.e is None:
        return Conferencia("autocorrelacao", "Autocorrelação", NAO_VERIFICAVEL,
                           "Resíduos não encontrados.", como, "Sem resíduos não é possível calcular a estatística D.")
    n, k = len(ctx.e), m.k
    d = dw.estatistica_dw(ctx.e)
    try:
        dl, du = dw.valores_criticos(n, k, c["alfa_cada_cauda"])
    except ValueError as ex:
        return Conferencia("autocorrelacao", "Autocorrelação", NAO_VERIFICAVEL,
                           "Graus de liberdade insuficientes.", como, str(ex))
    regiao = dw.classificar(d, dl, du)
    linhas = [Linha("D calculado", fmt(d, 4)),
              Linha("dL / dU", f"{fmt(dl, 3)} / {fmt(du, 3)}", f"n = {n}, k = {k}"),
              Linha("Região", f"{_ROT_DW[regiao]} ({c['descricao_confianca']})",
                    f"{fmt(du, 3)} < D < {fmt(4 - du, 3)}",
                    ATENDE if regiao == "nao_autorregressao" else
                    (None if regiao == "inconclusiva" else NAO_ATENDE))]
    obs = ["O teste só tem significado quando a ordem dos dados é relevante (ex.: dados ordenados por data ou "
           "por alguma característica). Em amostras sem ordenação lógica, o resultado depende da ordem de entrada."]
    obs += ctx.observacoes
    testes = [{"nome": "Durbin-Watson", "estatistica": d, "dL": dl, "dU": du, "regiao": regiao}]
    if regiao == "nao_autorregressao":
        return Conferencia("autocorrelacao", "Autocorrelação", ATENDE,
                           "Não autorregressão.", como,
                           f"D = {fmt(d, 4)} está entre dU = {fmt(du, 3)} e 4 − dU = {fmt(4 - du, 3)}: não há "
                           "evidência de correlação entre resíduos consecutivos.", linhas,
                           observacoes=obs, testes=testes)
    sug = ["Verificar se a ordem dos dados segue algum critério (data, região, área) e se esse critério "
           "deveria entrar no modelo como variável.",
           "Verificar omissão de variável relevante ou forma funcional inadequada."]
    if regiao == "inconclusiva":
        if not ctx.x_confiavel:
            return Conferencia("autocorrelacao", "Autocorrelação", NAO_VERIFICAVEL,
                               "Região não conclusiva; teste complementar não aplicado.", como,
                               f"D = {fmt(d, 4)} caiu na região não conclusiva e o teste de Breusch-Godfrey não "
                               f"pôde ser aplicado porque {_sem_x(ctx)}.", linhas, observacoes=obs, testes=testes)
        bg = T.breusch_godfrey(ctx.e, ctx.X, ctx.alfa)
        linhas.append(_linha_teste(bg, ctx.alfa, "a ausência de autocorrelação"))
        testes.append(_teste_dict(bg))
        if not bg.rejeita_h0:
            return Conferencia("autocorrelacao", "Autocorrelação", ATENDE,
                               "Região não conclusiva no Durbin-Watson; ausência de autocorrelação confirmada.",
                               como, f"D = {fmt(d, 4)} caiu na região não conclusiva. O teste de Breusch-Godfrey "
                                     f"(p-valor = {T.fmt_p(bg.p_valor)}) não rejeitou a hipótese de ausência de "
                                     "autocorrelação.", linhas, observacoes=obs, testes=testes)
        return Conferencia("autocorrelacao", "Autocorrelação", NAO_ATENDE,
                           "Há indícios de autocorrelação dos resíduos.", como,
                           f"D = {fmt(d, 4)} caiu na região não conclusiva e o teste de Breusch-Godfrey "
                           f"(p-valor = {T.fmt_p(bg.p_valor)}) rejeitou a ausência de autocorrelação.",
                           linhas, sugestoes=sug, observacoes=obs, testes=testes)
    return Conferencia("autocorrelacao", "Autocorrelação", NAO_ATENDE,
                       f"{_ROT_DW[regiao]}.", como,
                       f"D = {fmt(d, 4)} está fora da região de não autorregressão "
                       f"({fmt(du, 3)} a {fmt(4 - du, 3)}): resíduos consecutivos estão correlacionados.",
                       linhas, sugestoes=sug, observacoes=obs, testes=testes)


# ----------------------------------------------------------------------------
# 5. Multicolinearidade
# ----------------------------------------------------------------------------
def multicolinearidade(ctx: Contexto) -> Conferencia:
    c = ctx.crit["multicolinearidade"]
    lim = c["correlacao_maxima"]
    m = ctx.m
    dep = m.variavel_dependente
    tabelas = {"isoladas": ("Correlações isoladas", m.corr_isoladas),
               "influencia": ("Correlações de influência", m.corr_influencia)}
    linhas, violacoes, lidas = [], [], 0
    for chave in c["tabelas"]:
        nome_tab, mat = tabelas[chave]
        if not mat.valores:
            linhas.append(Linha(nome_tab, "tabela não encontrada", "", NAO_VERIFICAVEL))
            continue
        lidas += 1
        aliases = [a for a, nome in mat.aliases.items() if not (dep and nome == dep.nome)]
        maior = None
        for i, a in enumerate(aliases):
            for b in aliases[i + 1:]:
                v = mat.valores.get(a, {}).get(b)
                if v is None:
                    continue
                if maior is None or abs(v) > abs(maior[2]):
                    maior = (a, b, v)
                if abs(v) > lim:
                    violacoes.append((nome_tab, mat.aliases[a], mat.aliases[b], v))
        if maior:
            a, b, v = maior
            linhas.append(Linha(f"{nome_tab}: maior par", f"{mat.aliases[a]} × {mat.aliases[b]} = {fmt(v, 2)}",
                                f"|r| ≤ {fmt(lim, 2)}", ATENDE if abs(v) <= lim else NAO_ATENDE))
    como = (f"Leitura das tabelas de correlações parciais (isoladas e de influência) do relatório, considerando "
            f"apenas os pares entre variáveis independentes. A correlação de cada variável com a dependente não "
            f"entra nesta conferência. Limite: |r| ≤ {fmt(lim, 2)}.")
    if lidas == 0:
        return Conferencia("multicolinearidade", "Multicolinearidade", NAO_VERIFICAVEL,
                           "Tabelas de correlação não encontradas.", como,
                           "Sem as tabelas de correlações parciais não é possível fazer a conferência.", linhas)
    if violacoes:
        txt = "; ".join(f"{a} × {b} = {fmt(v, 2)} ({t.lower()})" for t, a, b, v in violacoes)
        return Conferencia(
            "multicolinearidade", "Multicolinearidade", NAO_ATENDE,
            f"Há pares de variáveis independentes com correlação acima de {fmt(lim, 2)}.", como,
            f"{txt}. Variáveis fortemente correlacionadas entre si tornam os coeficientes instáveis e podem "
            "distorcer a contribuição de cada uma no valor estimado.", linhas,
            sugestoes=["Avaliar a retirada de uma das variáveis correlacionadas.",
                       "Combinar as variáveis correlacionadas numa única variável, se fizer sentido técnico.",
                       "Verificar se o imóvel avaliando segue a mesma estrutura de correlação da amostra.",
                       "Ampliar a amostra com dados que quebrem a correlação."])
    return Conferencia("multicolinearidade", "Multicolinearidade", ATENDE,
                       f"Nenhum par de variáveis independentes ultrapassa {fmt(lim, 2)}.", como,
                       "As variáveis independentes não apresentam correlação forte entre si, o que indica "
                       "ausência de multicolinearidade relevante.", linhas)


# ----------------------------------------------------------------------------
# 6. Outliers e pontos influenciantes
# ----------------------------------------------------------------------------
def outliers(ctx: Contexto) -> Conferencia:
    c = ctx.crit["outliers"]
    m = ctx.m
    linhas, falhas, obs = [], [], []
    pct = m.pct_outliers
    if pct is None and m.n_outliers is not None and m.n:
        pct = 100.0 * m.n_outliers / m.n
    if pct is None:
        linhas.append(Linha("Outliers", "não informado", f"≤ {fmt(c['percentual_maximo'], 0)}%", NAO_VERIFICAVEL))
    else:
        ok = pct <= c["percentual_maximo"] + 1e-9
        linhas.append(Linha("Outliers", f"{m.n_outliers if m.n_outliers is not None else '—'} "
                                        f"({fmt(pct, 2, True)})", f"≤ {fmt(c['percentual_maximo'], 0)}% dos dados",
                            ATENDE if ok else NAO_ATENDE))
        if not ok:
            falhas.append("outliers")
    lista_out = []
    if ctx.e is not None:
        lim = c["limite_residuo_padronizado"]
        lista_out = [(d, v) for d, v in zip(ctx.dados, ctx.e) if abs(v) > lim]
        if lista_out:
            linhas.append(Linha("Dados com |resíduo/DP| > " + fmt(lim, 0),
                                ", ".join(f"dado {d} ({fmt(v, 2)})" for d, v in lista_out)))
        if m.n_outliers is not None and len(lista_out) != m.n_outliers:
            obs.append(f"O relatório informa {m.n_outliers} outlier(s), mas {len(lista_out)} dado(s) têm "
                       f"|resíduo/DP| > {fmt(lim, 0)}.")
    cooks = [(r.dado, r.cook) for r in m.residuos if r.cook is not None]
    if cooks:
        d_max, c_max = max(cooks, key=lambda x: x[1])
        acima = [(d, v) for d, v in cooks if v > c["cook_maximo"]]
        linhas.append(Linha("Maior distância de Cook", f"{fmt(c_max, 4)} (dado {d_max})",
                            f"≤ {fmt(c['cook_maximo'], 2)}", NAO_ATENDE if acima else ATENDE))
        if acima:
            falhas.append("cook")
    else:
        linhas.append(Linha("Distância de Cook", "coluna não encontrada", "", NAO_VERIFICAVEL))
    como = (f"Leitura da quantidade de outliers informada pelo SisDEA (resíduo padronizado acima de "
            f"{fmt(c['limite_residuo_padronizado'], 0)} desvios) e comparação com {fmt(c['percentual_maximo'], 0)}% "
            f"dos dados utilizados; leitura da coluna \"DCook\" da tabela de resíduos e comparação com "
            f"{fmt(c['cook_maximo'], 2)}.")
    if pct is None and not cooks:
        return Conferencia("outliers", "Outliers e pontos influenciantes", NAO_VERIFICAVEL,
                           "Informações não encontradas.", como, "O relatório não traz outliers nem distância de Cook.",
                           linhas, observacoes=obs)
    if falhas:
        partes = []
        if "outliers" in falhas:
            partes.append(f"o percentual de outliers ({fmt(pct, 2, True)}) supera {fmt(c['percentual_maximo'], 0)}%")
        if "cook" in falhas:
            partes.append(f"há dado(s) com distância de Cook acima de {fmt(c['cook_maximo'], 2)}, "
                          "ou seja, com influência excessiva sobre os coeficientes")
        return Conferencia("outliers", "Outliers e pontos influenciantes", NAO_ATENDE,
                           "Há outliers em excesso ou pontos muito influentes.", como,
                           "Não atende porque " + " e ".join(partes) + ".", linhas,
                           sugestoes=["Verificar os dados apontados quanto a erro de digitação ou de informação.",
                                      "Investigar se o dado pertence ao mesmo mercado da amostra.",
                                      "Retirar o dado somente com justificativa técnica registrada no laudo.",
                                      "Verificar se falta variável que explique o comportamento do dado."],
                           observacoes=obs)
    expl = "O percentual de outliers está dentro do limite e nenhum dado tem influência excessiva sobre o modelo."
    if pct is not None and abs(pct - c["percentual_maximo"]) < 1e-9:
        expl = (f"O percentual de outliers é exatamente o limite de {fmt(c['percentual_maximo'], 0)}%, "
                "o que atende ao critério; nenhum dado tem influência excessiva sobre o modelo.")
    if lista_out:
        obs.append("Convém confirmar no laudo que o(s) outlier(s) foram verificados: "
                   + ", ".join(f"dado {d}" for d, _ in lista_out) + ".")
    return Conferencia("outliers", "Outliers e pontos influenciantes", ATENDE,
                       "Outliers e distância de Cook dentro dos limites.", como, expl, linhas, observacoes=obs)


# ----------------------------------------------------------------------------
# 7. Micronumerosidade
# ----------------------------------------------------------------------------
def _minimo_micro(n: int, regras: List[dict]) -> (float, str):
    for r in regras:
        if r["n_ate"] is None or n <= r["n_ate"]:
            if r["tipo"] == "percentual":
                return r["minimo"] / 100.0 * n, f"≥ {fmt(r['minimo'], 0)}% de n = {fmt(r['minimo'] / 100.0 * n, 1)}"
            return r["minimo"], f"≥ {r['minimo']}"
    return 0, ""


def micronumerosidade(ctx: Contexto) -> Conferencia:
    c = ctx.crit["micronumerosidade"]
    m = ctx.m
    vars_ = [v for v in m.independentes if v.sujeita_micronumerosidade]
    usados = [a for a in m.amostra if not a.desabilitado]
    n = len(usados) or (m.n or 0)
    como = ("Identificação, na descrição das variáveis, das variáveis dicotômicas e de códigos alocados; "
            "contagem, na tabela de dados (apenas dados habilitados), da quantidade de dados em cada categoria; "
            f"comparação com o mínimo da {c['fonte']}: n ≤ 30 → nj ≥ 3; 30 < n ≤ 100 → nj ≥ 10% de n; "
            "n > 100 → nj ≥ 10.")
    if not vars_:
        return Conferencia("micronumerosidade", "Micronumerosidade", ATENDE,
                           "O modelo não tem variáveis dicotômicas ou de códigos alocados.", como,
                           "A conferência de micronumerosidade não se aplica a este modelo.")
    if not usados:
        return Conferencia("micronumerosidade", "Micronumerosidade", NAO_VERIFICAVEL,
                           "Os valores das variáveis não constam na tabela de dados.", como,
                           "Para contar os dados por categoria de "
                           + ", ".join(f"\"{v.nome}\"" for v in vars_) + " é preciso a tabela de dados com os "
                           "valores das variáveis numéricas, que não foi encontrada no relatório.",
                           sugestoes=["Incluir no laudo a tabela de dados completa do SisDEA ou enviar o arquivo "
                                      ".rtf gerado pelo SisDEA."])
    minimo, txt_min = _minimo_micro(n, c["regras"])
    linhas, falhas = [], []
    for v in vars_:
        valores = [a.valores.get(v.nome) for a in usados]
        cont: Dict[float, int] = {}
        for x in valores:
            if x is not None:
                cont[x] = cont.get(x, 0) + 1
        for cat in sorted(cont):
            ok = cont[cat] >= minimo - 1e-9
            linhas.append(Linha(f"{v.nome} = {fmt(cat, 0) if float(cat).is_integer() else fmt(cat, 2)}",
                                f"{cont[cat]} dado(s)", txt_min, ATENDE if ok else NAO_ATENDE))
            if not ok:
                falhas.append(f"{v.nome} = {fmt(cat, 0) if float(cat).is_integer() else fmt(cat, 2)} "
                              f"({cont[cat]} dado(s))")
    if falhas:
        return Conferencia("micronumerosidade", "Micronumerosidade", NAO_ATENDE,
                           "Há categorias com dados insuficientes.", como,
                           f"Com n = {n}, cada categoria precisa de {txt_min} dados. Abaixo do mínimo: "
                           + "; ".join(falhas) + ". Com poucos dados, o efeito da categoria no valor fica mal "
                           "estimado.", linhas,
                           sugestoes=["Obter mais dados de mercado na(s) categoria(s) com poucos dados.",
                                      "Agrupar categorias, quando houver justificativa técnica.",
                                      "Avaliar a retirada da variável do modelo."])
    return Conferencia("micronumerosidade", "Micronumerosidade", ATENDE,
                       "Todas as categorias têm a quantidade mínima de dados.", como,
                       f"Com n = {n}, cada categoria precisa de {txt_min} dados, e todas atendem.", linhas)


# ----------------------------------------------------------------------------
# 8. Significância dos regressores (t)
# ----------------------------------------------------------------------------
def _grau(valor: float, graus: Dict[str, float]) -> Optional[str]:
    for g in ORDEM_GRAUS:
        if valor <= graus[g] + 1e-9:
            return g
    return None


def significancia_regressores(ctx: Contexto) -> Conferencia:
    c = ctx.crit["significancia_regressores"]
    g = c["graus"]
    regs = [r for r in ctx.m.regressores if not r.eh_intercepto]
    como = (f"Leitura da significância (teste t de Student bicaudal) de cada variável independente na tabela de "
            f"testes de hipóteses. Faixas ({c['fonte']}): ≤ {g['III']}% Grau III; ≤ {g['II']}% Grau II; "
            f"≤ {g['I']}% Grau I. A linha da variável dependente corresponde ao intercepto; ela é mostrada "
            "apenas como informação e não entra no resultado.")
    if not regs:
        return Conferencia("significancia_regressores", "Significância dos regressores (t de Student)",
                           NAO_VERIFICAVEL, "Tabela de testes de hipóteses não encontrada.", como,
                           "Sem a tabela não é possível fazer a conferência.")
    linhas, graus, reprov = [], [], []
    for r in regs:
        if r.significancia is None:
            linhas.append(Linha(r.nome, "não informado", "", NAO_VERIFICAVEL))
            continue
        gr = _grau(r.significancia, g)
        graus.append(gr)
        linhas.append(Linha(r.nome, f"{fmt(r.significancia, 2, True)} (t = {fmt(r.t, 2)})",
                            f"Grau {gr}" if gr else f"> {g['I']}%", ATENDE if gr else NAO_ATENDE))
        if gr is None:
            reprov.append(r)
    obs = []
    interc = next((r for r in ctx.m.regressores if r.eh_intercepto), None)
    if interc is not None:
        valor = (f"{fmt(interc.significancia, 2, True)} (t = {fmt(interc.t, 2)})"
                 if interc.significancia is not None else "não informado")
        linhas.append(Linha(f"Intercepto (linha \"{interc.nome}\")", valor, "apenas informativo"))
        obs.append(f"A linha \"{interc.nome}\" da tabela de testes de hipóteses traz o teste t do intercepto "
                   "(constante da equação), e não da variável dependente. O valor é mostrado apenas como "
                   "informação: a NBR 14653-2 exige a significância de cada regressor (variável independente), "
                   "não do intercepto.")
    if reprov:
        nomes = ", ".join(f"{r.nome} ({fmt(r.significancia, 2, True)})" for r in reprov)
        return Conferencia("significancia_regressores", "Significância dos regressores (t de Student)",
                           NAO_ATENDE, f"Há variável com significância acima de {g['I']}%.", como,
                           f"{nomes}: a significância supera o limite máximo de {g['I']}%, ou seja, não há "
                           "segurança estatística de que a variável influencia o valor.", linhas,
                           sugestoes=["Retirar a variável não significativa ou testar outra transformação.",
                                      "Verificar a qualidade da informação dessa variável nos dados.",
                                      "Ampliar a amostra para aumentar a precisão da estimativa."],
                           observacoes=obs)
    pior = max(graus, key=ORDEM_GRAUS.index)
    limitantes = [r.nome for r in regs if r.significancia is not None and _grau(r.significancia, g) == pior]
    expl = f"Todas as variáveis têm significância de no máximo {g[pior]}%, o que corresponde ao Grau {pior}."
    sug = []
    if pior != "III":
        expl += f" A faixa é definida por: {', '.join(limitantes)}."
        sug = [f"Para reduzir a significância, avaliar outra transformação para {', '.join(limitantes)} "
               "ou ampliar a amostra."]
    return Conferencia("significancia_regressores", "Significância dos regressores (t de Student)", ATENDE,
                       f"Todas as variáveis são significativas (faixa do Grau {pior}).", como, expl,
                       linhas, sugestoes=sug, observacoes=obs, grau=pior)


# ----------------------------------------------------------------------------
# 9. Significância do modelo (F)
# ----------------------------------------------------------------------------
def significancia_modelo(ctx: Contexto) -> Conferencia:
    c = ctx.crit["significancia_modelo"]
    g = c["graus"]
    m = ctx.m
    como = (f"Leitura da significância do modelo (teste F de Snedecor). Faixas ({c['fonte']}): "
            f"≤ {g['III']}% Grau III; ≤ {g['II']}% Grau II; ≤ {g['I']}% Grau I.")
    if m.significancia_modelo is None:
        return Conferencia("significancia_modelo", "Significância do modelo (F de Snedecor)", NAO_VERIFICAVEL,
                           "Significância do modelo não encontrada.", como,
                           "Sem esse valor não é possível fazer a conferência.")
    gr = _grau(m.significancia_modelo, g)
    linhas = [Linha("F calculado", fmt(m.f_calculado, 2)),
              Linha("Significância do modelo", fmt(m.significancia_modelo, 2, True),
                    f"Grau {gr}" if gr else f"> {g['I']}%", ATENDE if gr else NAO_ATENDE)]
    if gr is None:
        return Conferencia("significancia_modelo", "Significância do modelo (F de Snedecor)", NAO_ATENDE,
                           f"Significância do modelo acima de {g['I']}%.", como,
                           "Não há segurança estatística de que o conjunto das variáveis explica o valor.",
                           linhas, sugestoes=["Rever a escolha das variáveis e suas transformações.",
                                              "Verificar dados discrepantes e a homogeneidade da amostra."])
    return Conferencia("significancia_modelo", "Significância do modelo (F de Snedecor)", ATENDE,
                       f"O modelo é significativo (faixa do Grau {gr}).", como,
                       f"A significância de {fmt(m.significancia_modelo, 2, True)} é inferior ao limite de "
                       f"{g[gr]}%, o que rejeita a hipótese de que todos os coeficientes são nulos.", linhas, grau=gr)


TODAS = [linearidade, normalidade, homocedasticidade, autocorrelacao, multicolinearidade, outliers,
         micronumerosidade, significancia_regressores, significancia_modelo]
