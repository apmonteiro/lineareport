"""Testes automatizados. Executar na pasta backend:  python -m unittest -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linea.analise import analisar  # noqa: E402
from linea.estatistica.durbin_watson import valores_criticos  # noqa: E402
from linea.relatorio.exportar import exportar  # noqa: E402
from linea.sisdea.parser import ErroLeitura, interpretar  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, "dados", "Relatorio_Ex_4_Teste.rtf"), "rb") as _f:
    EX4 = _f.read()


def variante(**trocas):
    dados = EX4
    for antigo, novo in trocas.values():
        assert antigo.encode() in dados, antigo
        dados = dados.replace(antigo.encode(), novo.encode(), 1)
    return dados


def por_id(res):
    return {c["id"]: c for c in res["conferencias"]}


class TestLeitura(unittest.TestCase):
    def test_parametros_ex4(self):
        m = interpretar(EX4)
        self.assertEqual((m.n, m.k), (20, 3))
        self.assertAlmostEqual(m.r_equacao, 0.9732271)
        self.assertAlmostEqual(m.r_funcao, 0.7676914)
        self.assertEqual([r.transformacao for r in m.regressores], ["1/x", "1/x²", "x½", "1/y"])
        self.assertTrue(m.regressores[-1].eh_intercepto)
        self.assertEqual(len(m.residuos), 20)
        self.assertAlmostEqual(m.residuos[12].padronizado, -2.351022)
        self.assertEqual(m.pontos_fundamentacao_sisdea, {1: None, 2: 2, 3: None, 4: None, 5: 1, 6: 3})
        self.assertEqual(m.amostra[16].valores["Dist ao metrô"], 1350.0)
        self.assertEqual(m.avisos, [])

    def test_arquivo_invalido(self):
        with self.assertRaises(ErroLeitura):
            interpretar(b"isto nao e rtf")
        with self.assertRaises(ErroLeitura):
            interpretar(b"{\\rtf1\\ansi Um texto qualquer\\par}")


class TestDurbinWatson(unittest.TestCase):
    def test_tabela_savin_white(self):
        for n, k, esperado in [(20, 3, (0.998, 1.676)), (15, 1, (1.077, 1.361)), (50, 2, (1.462, 1.628))]:
            self.assertEqual(valores_criticos(n, k), esperado)


class TestEx4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = analisar(EX4, "Ex4.rtf")
        cls.c = por_id(cls.res)

    def test_todas_atendem(self):
        self.assertEqual(self.res["resumo"], {"atende": 9, "nao_atende": 0, "nao_verificavel": 0})

    def test_leitura_consistente(self):
        self.assertTrue(self.res["leitura"]["consistencia"]["ok"])
        self.assertLess(self.res["leitura"]["consistencia"]["diferenca_maxima"], 1e-4)

    def test_dw(self):
        dw = self.c["autocorrelacao"]["testes"][0]
        self.assertAlmostEqual(dw["estatistica"], 2.2149, places=4)
        self.assertEqual(dw["regiao"], "nao_autorregressao")

    def test_normalidade_faixa_1_falha_mas_testes_confirmam(self):
        n = self.c["normalidade"]
        self.assertEqual(n["linhas"][0]["status"], "nao_atende")
        self.assertEqual(len(n["testes"]), 3)

    def test_exportacao(self):
        self.assertTrue(exportar(self.res, "pdf").startswith(b"%PDF"))
        self.assertTrue(exportar(self.res, "docx").startswith(b"PK"))
        self.assertTrue(exportar(self.res, "odt").startswith(b"PK"))


with open(os.path.join(AQUI, "dados", "Relatorio_Ex_7_Teste.rtf"), "rb") as _f:
    EX7 = _f.read()


class TestEx7(unittest.TestCase):
    """Dado 3 desabilitado, variável dicotômica e regressores não significativos."""

    @classmethod
    def setUpClass(cls):
        cls.res = analisar(EX7, "Ex7.rtf")
        cls.c = por_id(cls.res)

    def test_dado_desabilitado(self):
        m = interpretar(EX7)
        self.assertEqual(m.n, 59)
        self.assertTrue(next(a for a in m.amostra if a.id == 3).desabilitado)
        self.assertNotIn(3, [r.dado for r in m.residuos])
        self.assertTrue(self.res["leitura"]["consistencia"]["ok"])
        self.assertEqual(self.res["leitura"]["avisos"], [])

    def test_micronumerosidade_com_dicotomica(self):
        itens = {l["item"]: l["valor"] for l in self.c["micronumerosidade"]["linhas"]}
        self.assertEqual(itens["Tipo = 0"], "41 dado(s)")
        self.assertEqual(itens["Tipo = 1"], "18 dado(s)")
        self.assertEqual(itens["Padrão construtivo = 1"], "10 dado(s)")

    def test_t_reprova(self):
        t = self.c["significancia_regressores"]
        self.assertEqual(t["status"], "nao_atende")
        reprovadas = [l["item"] for l in t["linhas"] if l["status"] == "nao_atende"]
        self.assertEqual(reprovadas, ["Idade aparente", "Tipo"])
        interc = t["linhas"][-1]
        self.assertEqual(interc["item"], 'Intercepto (linha "Valor total")')
        self.assertEqual(interc["valor"], "0,04% (t = -3,80)")
        self.assertIsNone(interc["status"])

    def test_dw_inconclusivo_usa_breusch_godfrey(self):
        a = self.c["autocorrelacao"]
        self.assertEqual(a["testes"][0]["regiao"], "inconclusiva")
        self.assertEqual(a["testes"][1]["nome"], "Breusch-Godfrey")
        self.assertEqual(a["status"], "atende")

    def test_resumo(self):
        self.assertEqual(self.res["resumo"], {"atende": 8, "nao_atende": 1, "nao_verificavel": 0})


class TestReprovacoes(unittest.TestCase):
    def test_reprovacoes(self):
        dados = variante(t=("\\fs20 23,57\\cell", "\\fs20 35,57\\cell"),
                         out=("\\fs20 5,00%\\cell", "\\fs20 10,00%\\cell"),
                         r=("/ 0,7676914\\cell", "/ 0,6100000\\cell"),
                         cook=("\\fs20 0,53641000\\cell", "\\fs20 1,53641000\\cell"))
        c = por_id(analisar(dados, "v.rtf"))
        self.assertEqual(c["significancia_regressores"]["status"], "nao_atende")
        self.assertEqual(c["outliers"]["status"], "nao_atende")
        self.assertEqual(c["linearidade"]["status"], "nao_atende")
        for k in ("significancia_regressores", "outliers", "linearidade"):
            self.assertTrue(c[k]["sugestoes"])

    def test_leitura_inconsistente_bloqueia_testes_auxiliares(self):
        # altera um valor da amostra: os resíduos deixam de ser reproduzidos
        dados = variante(a=("\\fs20 1.800.000,00\\cell", "\\fs20 2.800.000,00\\cell"))
        res = analisar(dados, "v.rtf")
        self.assertFalse(res["leitura"]["consistencia"]["ok"])
        self.assertEqual(por_id(res)["homocedasticidade"]["status"], "nao_verificavel")


class TestPDF(unittest.TestCase):
    """O PDF deve produzir exatamente a mesma leitura do RTF.
    Os PDFs de teste foram gerados a partir dos RTFs (impressão em PDF)."""

    def _compara(self, ex):
        from dataclasses import asdict
        with open(os.path.join(AQUI, "dados", f"Relatorio_Ex_{ex}_Teste.pdf"), "rb") as f:
            pdf = f.read()
        rtf = EX4 if ex == 4 else EX7
        a, b = asdict(interpretar(rtf)), asdict(interpretar(pdf))
        for campo in a:
            if campo in ("pontos_fundamentacao_sisdea", "secoes_encontradas", "versao_sisdea"):
                continue
            self.assertEqual(a[campo], b[campo], f"Ex. {ex}: campo '{campo}' difere entre RTF e PDF")
        ra, rb = analisar(rtf, "x.rtf"), analisar(pdf, "x.pdf")
        self.assertEqual(ra["resumo"], rb["resumo"])
        self.assertTrue(rb["leitura"]["consistencia"]["ok"])

    def test_ex4_pdf_igual_rtf(self):
        self._compara(4)

    def test_ex7_pdf_igual_rtf(self):
        # Ex. 7 tem dado desabilitado, tabela de dados dividida e números quebrados no meio
        self._compara(7)

    def test_pdf_sem_texto(self):
        import io
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.rect(100, 100, 200, 200, fill=1)
        c.save()
        with self.assertRaises(ErroLeitura) as ctx:
            interpretar(buf.getvalue())
        self.assertIn("digitalizado", str(ctx.exception))


class TestCasosDoLaudoReal(unittest.TestCase):
    """Situações encontradas no primeiro PDF real (laudo gerado pelo Word)."""

    def test_numeracao_em_fonte_de_simbolo(self):
        from linea.sisdea.parser_pdf import _sem_simbolos
        self.assertEqual(_sem_simbolos("\uf031\uf033\uf029 TABELA DE RESÍDUOS"), "13) TABELA DE RESÍDUOS")

    def test_variavel_texto_nao_entra_no_modelo(self):
        from linea.sisdea.modelo import ModeloSisDEA, Variavel, Regressor
        m = ModeloSisDEA(variaveis=[
            Variavel("Área total", "Numérica", "Quantitativa", "", True),
            Variavel("Endereço", "Texto", "Texto", "", True),
            Variavel("Topografia", "Numérica", "Dicotomica", "", False),
            Variavel("Valor total", "Numérica", "Dependente", "", True)])
        self.assertEqual([v.nome for v in m.independentes], ["Área total"])
        m.regressores = [Regressor("Área total", "x", 5.0, 0.0), Regressor("Valor total", "y", 1.0, 1.0, True)]
        self.assertEqual(m.k, 1)


    def test_numero_quebrado_antes_e_depois_da_virgula(self):
        from linea.sisdea.parser_pdf import _eh_fragmento
        self.assertTrue(_eh_fragmento([",00"], "1.200.000"))      # quebra antes da vírgula
        self.assertTrue(_eh_fragmento(["0"], "8.200.000,0"))      # quebra depois da vírgula
        self.assertFalse(_eh_fragmento(["0"], "137.088,23"))      # valor já completo
        self.assertFalse(_eh_fragmento(["12", "240,00"], "1,0"))  # linha de dado nova

    def test_numero_milhar_sem_decimais(self):
        from linea.sisdea.parser import numero
        self.assertEqual(numero("1.200.000"), 1200000.0)
        self.assertEqual(numero("1.500,00"), 1500.0)
        self.assertEqual(numero("-6,711229599E-07"), -6.711229599e-07)


    def test_dependente_pelo_modelo_e_nao_pela_classificacao(self):
        # SisDEA pode manter "Dependente" na descrição de uma variável usada como independente
        from linea.sisdea.modelo import ModeloSisDEA, Variavel, Regressor
        from linea.sisdea.parser import _valida
        m = ModeloSisDEA(variaveis=[
            Variavel("Padrão", "Numérica", "Qualitativa (Códigos Alocados)", "", True),
            Variavel("Area Útil", "Numérica", "Dependente", "", True),
            Variavel("Valor Unitário", "Numérica", "Dependente", "", True)],
            regressores=[Regressor("Padrão", "x", -16.4, 0.0), Regressor("Area Útil", "1/x²", 2.8, 0.79),
                         Regressor("Valor Unitário", "1/y½", 33.7, 0.0, True)])
        self.assertEqual(m.nome_dependente, "Valor Unitário")
        self.assertEqual([v.nome for v in m.independentes], ["Padrão", "Area Útil"])
        _valida(m)
        self.assertTrue(any("Area Útil" in a and "Dependente" in a for a in m.avisos))


if __name__ == "__main__":
    unittest.main()
