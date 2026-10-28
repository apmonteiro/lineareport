"""Interface Streamlit do LineaReport (para o Streamlit Community Cloud).

Usa o mesmo backend da versão Flask (backend/linea): lê o relatório em memória, analisa e descarta.
Rodar localmente: streamlit run streamlit_app.py
"""
import os
import re
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from linea.analise import VERSAO, analisar  # noqa: E402
from linea.relatorio.exportar import FORMATOS, exportar  # noqa: E402
from linea.sisdea.parser import ErroLeitura  # noqa: E402

ROTULO = {"atende": "Atende", "nao_atende": "Não atende", "nao_verificavel": "Não verificável"}
ICONE = {"atende": "✅", "nao_atende": "❌", "nao_verificavel": "➖"}
COR = {"atende": "#1E7B34", "nao_atende": "#B3261E", "nao_verificavel": "#6B726E"}
NOMES_FORMATO = {"docx": "Word (.docx)", "odt": "LibreOffice / BrOffice (.odt)", "pdf": "PDF (.pdf)"}

st.set_page_config(page_title="LineaReport", page_icon="📈", layout="centered")


@st.cache_data(show_spinner=False, max_entries=20)
def analisar_cache(dados: bytes, nome: str) -> dict:
    return analisar(dados, nome)


@st.cache_data(show_spinner=False, max_entries=20)
def exportar_cache(res: dict, formato: str) -> bytes:
    return exportar(res, formato)


def email_feedback() -> str:
    try:
        return st.secrets.get("EMAIL_FEEDBACK", "")
    except Exception:  # noqa: BLE001 - sem arquivo de secrets
        return os.environ.get("EMAIL_FEEDBACK", "")


def tabela(linhas: list) -> None:
    df = pd.DataFrame([{"Item": l["item"], "Valor": l["valor"], "Critério": l["criterio"]} for l in linhas])
    status = [l.get("status") for l in linhas]

    def cor_valor(col):
        if col.name != "Valor":
            return [""] * len(col)
        return [f"color: {COR[s]}; font-weight: 600" if s in COR else "" for s in status]

    st.dataframe(df.style.apply(cor_valor), hide_index=True, use_container_width=True)


def tela_inicial() -> None:
    st.markdown(
        "Envie o relatório estatístico do SisDEA em .rtf ou .pdf. O LineaReport lê os parâmetros do modelo e "
        "confere os pressupostos da regressão, a micronumerosidade e os testes de hipóteses, conforme a "
        "ABNT NBR 14653-2 e as orientações da SPU.")


def tela_info() -> None:
    st.info("**Isenção de responsabilidade.** Esta ferramenta apoia o avaliador na conferência do relatório "
            "estatístico. A escolha do modelo de regressão e a responsabilidade técnica por ele são do avaliador.")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Como usar")
        st.markdown(
            "1. No SisDEA, gere o relatório estatístico do modelo e salve em .rtf ou em .pdf.\n"
            "2. Carregue o arquivo acima.\n"
            "3. Leia o resultado de cada conferência na página. Se quiser guardar, use **Exportar relatório** "
            "e escolha o formato (.docx, .odt ou .pdf).")
    with c2:
        st.subheader("O que é conferido")
        st.markdown(
            "- Linearidade (coeficientes de correlação)\n- Normalidade dos resíduos\n- Homocedasticidade\n"
            "- Autocorrelação (Durbin-Watson)\n- Multicolinearidade\n- Outliers e distância de Cook\n"
            "- Micronumerosidade\n- Significância dos regressores (t)\n- Significância do modelo (F)")


def resultado(r: dict) -> None:
    m = r["modelo"]
    st.header(f"Modelo {m['modelo'] or 'sem nome'}")
    total, res = len(r["conferencias"]), r["resumo"]
    placar = f"**{res['atende']} de {total}** conferências atendidas"
    if res["nao_atende"]:
        placar += f", **:red[{res['nao_atende']} não atendida{'s' if res['nao_atende'] > 1 else ''}]**"
    if res["nao_verificavel"]:
        placar += f", {res['nao_verificavel']} não verificável(is)"
    st.markdown(placar + ".")

    ident = [("Arquivo", r["arquivo"]), ("Autor", m["autor"]), ("Data do modelo", m["data"]),
             ("Tipologia", m["tipologia"]), ("Dados utilizados", m["n"]), ("Variáveis independentes", m["k"]),
             ("Variável dependente", m["variavel_dependente"])]
    ident = [(k, str(v)) for k, v in ident if v is not None and v != ""]
    st.dataframe(pd.DataFrame(ident, columns=["Campo", "Conteúdo"]), hide_index=True, use_container_width=True)
    if m["equacao"]:
        st.markdown("**Equação**")
        st.code(m["equacao"], language=None, wrap_lines=True)

    exportacao(r)

    c1, c2 = st.columns([3, 1])
    c1.subheader("Conferências")
    abertas = c2.toggle("Expandir todas", value=True)
    for c in r["conferencias"]:
        with st.expander(f"{ICONE[c['status']]} **{ROTULO[c['status']]}** · {c['titulo']}: {c['resumo']}",
                         expanded=abertas):
            st.markdown("**Como foi feito**")
            st.write(c["como_foi_feito"])
            if c["linhas"]:
                tabela(c["linhas"])
            st.markdown("**Resultado**")
            {"atende": st.success, "nao_atende": st.error}.get(c["status"], st.info)(c["explicacao"])
            if c["sugestoes"]:
                st.markdown("**Sugestões para corrigir**" if c["status"] == "nao_atende" else "**Sugestões**")
                st.markdown("\n".join(f"- {s}" for s in c["sugestoes"]))
            for o in c["observacoes"]:
                st.caption(o)

    st.subheader("Leitura do arquivo")
    leitura = r["leitura"]
    st.write(leitura["texto_consistencia"])
    for a in leitura["avisos"]:
        st.warning(a)

    comentarios(r)


def exportacao(r: dict) -> None:
    with st.container(border=True):
        st.markdown("**Exportar relatório** — identificação do modelo e todas as conferências desta página.")
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        fmt = c1.radio("Formato do arquivo", list(FORMATOS), format_func=NOMES_FORMATO.get, horizontal=True)
        base = re.sub(r"[^\w\-]+", "_", os.path.splitext(r.get("arquivo") or "modelo")[0]).strip("_")
        try:
            with st.spinner("Gerando o relatório…"):
                dados = exportar_cache(r, fmt)
        except Exception as e:  # noqa: BLE001
            st.error(f"Não foi possível gerar o relatório: {e}")
            return
        c2.download_button("Exportar", dados, file_name=f"Analise_{base or 'modelo'}.{fmt}",
                           mime=FORMATOS[fmt], type="primary", use_container_width=True)


def comentarios(r: dict) -> None:
    st.subheader("Informe de erros e comentários")
    st.caption("Encontrou um erro de leitura ou tem uma sugestão? Descreva abaixo. "
               "O texto segue com o nome do arquivo analisado.")
    txt = st.text_area("Comentário", placeholder="Ex.: a variável X foi lida com valor diferente do relatório.",
                       label_visibility="collapsed")
    if not txt.strip():
        return
    corpo = f"Arquivo: {r['arquivo']}\nModelo: {r['modelo']['modelo']}\nVersão: {r['app']['versao']}\n\n{txt.strip()}"
    email = email_feedback()
    if email:
        from urllib.parse import quote
        st.link_button("Enviar comentário por e-mail",
                       f"mailto:{email}?subject={quote('LineaReport: comentário')}&body={quote(corpo)}")
    else:
        st.caption("Copie o texto abaixo (botão no canto) e envie por e-mail ou mensagem à equipe responsável.")
        st.code(corpo, language=None)


st.title("LineaReport")
st.caption("Conferência de modelos de regressão do SisDEA")

arquivo = st.file_uploader("Relatório do SisDEA (.rtf ou .pdf)", type=["rtf", "pdf"],
                           help="A análise começa assim que o arquivo é carregado. Nada é guardado no servidor.")
if arquivo is None:
    tela_inicial()
    tela_info()
else:
    try:
        with st.spinner("Analisando o relatório…"):
            analise = analisar_cache(arquivo.getvalue(), arquivo.name)
    except ErroLeitura as e:
        st.error(str(e))
        analise = None
    except Exception as e:  # noqa: BLE001
        st.error(f"Erro inesperado ao analisar o arquivo: {e}")
        analise = None
    if analise:
        resultado(analise)
    else:
        tela_info()

st.divider()
st.caption(f"LineaReport {VERSAO}. Critérios: ABNT NBR 14653-2, IN SPU e Manual de Avaliações da SPU.")
