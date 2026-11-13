"""Monta a versão "no navegador" do LineaReport (pasta estática, sem servidor de aplicação).

    python navegador/montar.py                 # gera navegador/dist
    python navegador/montar.py --saida C:/pasta

Reaproveita a página de frontend/ e o código de backend/linea, que roda no navegador com o Pyodide.
O resultado é uma pasta de arquivos estáticos: basta publicá-la em qualquer servidor web (IIS, Apache,
nginx, GitHub Pages...). Precisa de internet só aqui, para baixar as bibliotecas Python puras (pip).
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.join(RAIZ, "navegador")
# Bibliotecas Python puras (instaladas no navegador sem dependências; as demais vêm do Pyodide).
RODAS = ["pdfminer.six==20260107", "pdfplumber==0.11.10", "python-docx==1.2.0", "odfpy==1.4.1",
         "reportlab==5.1.0"]


def trocar(texto: str, antigo: str, novo: str) -> str:
    if antigo not in texto:
        raise SystemExit(f"Trecho não encontrado em index.html: {antigo[:60]}")
    return texto.replace(antigo, novo, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default=os.path.join(AQUI, "dist"))
    a = ap.parse_args()
    saida = os.path.abspath(a.saida)
    if os.path.isdir(saida):
        shutil.rmtree(saida)

    # 1) página
    shutil.copytree(os.path.join(RAIZ, "frontend"), saida)
    shutil.copy(os.path.join(AQUI, "motor.js"), saida)
    with open(os.path.join(saida, "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = trocar(html, '<script src="app.js"></script>',
                  '<script src="rodas.js"></script>\n<script src="motor.js"></script>\n<script src="app.js"></script>')
    html = trocar(html, "Nada é guardado no servidor.", "O arquivo não sai do seu computador.")
    html = trocar(html, '    <div id="carregando"',
                  '    <p id="motor-status" class="motor-status" role="status" hidden></p>\n    <div id="carregando"')
    with open(os.path.join(saida, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(saida, "estilo.css"), "a", encoding="utf-8") as f:
        f.write("\n/* versão no navegador */\n"
                ".motor-status { margin-top: 12px; color: var(--tinta-suave); font-size: 0.92rem; }\n"
                ".motor-status.motor-erro { color: var(--falha); }\n")

    # 2) código Python do LineaReport
    linea = os.path.join(RAIZ, "backend", "linea")
    with zipfile.ZipFile(os.path.join(saida, "linea.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for pasta, subpastas, arquivos in os.walk(linea):
            subpastas[:] = [d for d in subpastas if d != "__pycache__"]
            for nome in arquivos:
                if not nome.endswith(".pyc"):
                    caminho = os.path.join(pasta, nome)
                    z.write(caminho, os.path.relpath(caminho, os.path.dirname(linea)))

    # 3) bibliotecas Python puras (.whl)
    rodas = os.path.join(saida, "rodas")
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", rodas, *RODAS], check=True)
    nomes = sorted(n for n in os.listdir(rodas) if n.endswith(".whl"))
    with open(os.path.join(saida, "rodas.js"), "w", encoding="utf-8") as f:
        f.write("window.LINEA_RODAS = " + repr(nomes).replace("'", '"') + ";\n")
    # GitHub Pages: não processar com Jekyll
    open(os.path.join(saida, ".nojekyll"), "w").close()
    print(f"Pronto: {saida}")


if __name__ == "__main__":
    main()
