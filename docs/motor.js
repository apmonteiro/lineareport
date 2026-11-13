// Motor do LineaReport no navegador: roda o mesmo código Python do servidor (backend/linea)
// dentro do navegador com o Pyodide. O relatório não sai do computador do usuário.
(function () {
  "use strict";
  const CFG = window.LINEA_CONFIG || {};
  // Endereço do Pyodide. Na intranet sem internet, aponte para uma cópia local (veja navegador/README.md).
  const PYODIDE_URL = (CFG.PYODIDE_URL || "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/").replace(/\/?$/, "/");
  const PACOTES_PYODIDE = ["numpy", "scipy", "lxml", "pillow", "cryptography", "charset-normalizer",
                           "typing-extensions", "micropip"];
  const RODAS = window.LINEA_RODAS || [];   // gerado por montar.py (rodas.js)
  const MIME = { docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 odt: "application/vnd.oasis.opendocument.text", pdf: "application/pdf" };

  function aviso(texto, erro) {
    const el = document.getElementById("motor-status");
    if (!el) return;
    el.textContent = texto || "";
    el.hidden = !texto;
    el.classList.toggle("motor-erro", !!erro);
  }

  function carregaScript(src) {
    return new Promise((ok, falha) => {
      const s = document.createElement("script");
      s.src = src; s.onload = ok;
      s.onerror = () => falha(new Error("Não foi possível baixar o Pyodide de " + src));
      document.head.appendChild(s);
    });
  }

  async function iniciar() {
    const t0 = performance.now();
    aviso("Preparando o analisador no navegador… Na primeira vez pode levar até 30 segundos.");
    await carregaScript(PYODIDE_URL + "pyodide.js");
    const py = await window.loadPyodide({ indexURL: PYODIDE_URL });
    aviso("Preparando o analisador: carregando bibliotecas de cálculo…");
    await py.loadPackage(PACOTES_PYODIDE);
    aviso("Preparando o analisador: carregando o LineaReport…");
    const base = new URL(".", document.baseURI);
    const urls = RODAS.map((r) => new URL("rodas/" + r, base).href);
    await py.runPythonAsync(`import micropip\nawait micropip.install(${JSON.stringify(urls)}, deps=False)`);
    const zip = await fetch(new URL("linea.zip", base)).then((r) => {
      if (!r.ok) throw new Error("linea.zip não encontrado (" + r.status + ")");
      return r.arrayBuffer();
    });
    py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/app" });
    py.runPython(`
import sys, json
sys.path.insert(0, "/home/pyodide/app")
from linea.analise import analisar as _analisar, VERSAO
from linea.relatorio.exportar import exportar as _exportar
from linea.sisdea.parser import ErroLeitura

def linea_analisar(dados, nome):
    try:
        return json.dumps({"ok": _analisar(bytes(dados.to_py()), nome)}, default=str)
    except ErroLeitura as e:
        return json.dumps({"erro": str(e)})
    except Exception as e:
        return json.dumps({"erro": f"Erro inesperado ao analisar o arquivo: {e}"})

def linea_exportar(texto, formato):
    return _exportar(json.loads(texto), formato)
`);
    aviso("");
    console.info(`LineaReport: analisador pronto em ${Math.round(performance.now() - t0)} ms`);
    return py;
  }

  let pronto = null;
  function motor() {
    if (!pronto) {
      pronto = iniciar().catch((e) => {
        pronto = null;
        aviso("Não foi possível preparar o analisador no navegador: " + e.message.replace(/\.?$/, ".") +
              " Recarregue a página. Se persistir, avise a equipe responsável.", true);
        throw e;
      });
    }
    return pronto;
  }

  window.LineaMotor = {
    async versao() { return (await motor()).globals.get("VERSAO"); },
    async analisar(arquivo) {
      const py = await motor();
      const dados = new Uint8Array(await arquivo.arrayBuffer());
      const r = JSON.parse(py.globals.get("linea_analisar")(dados, arquivo.name));
      if (r.erro) throw new Error(r.erro);
      return r.ok;
    },
    async exportar(analise, formato) {
      const py = await motor();
      const proxy = py.globals.get("linea_exportar")(JSON.stringify(analise), formato);
      const bytes = proxy.toJs();
      proxy.destroy();
      return new Blob([bytes], { type: MIME[formato] || "application/octet-stream" });
    },
  };

  // começa a preparar assim que a página abre, enquanto o usuário lê as instruções
  window.addEventListener("load", () => { motor().catch(() => {}); });
})();
