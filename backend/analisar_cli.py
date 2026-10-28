"""Uso em linha de comando (sem interface):
    python analisar_cli.py relatorio.rtf [--formato pdf|docx|odt|json] [--saida pasta]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from linea.analise import analisar  # noqa: E402
from linea.relatorio.exportar import exportar  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivos", nargs="+")
    ap.add_argument("--formato", default="pdf", choices=["pdf", "docx", "odt", "json"])
    ap.add_argument("--saida", default=".")
    a = ap.parse_args()
    os.makedirs(a.saida, exist_ok=True)
    for caminho in a.arquivos:
        with open(caminho, "rb") as f:
            res = analisar(f.read(), os.path.basename(caminho))
        base = os.path.join(a.saida, "Analise_" + os.path.splitext(os.path.basename(caminho))[0])
        if a.formato == "json":
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
        else:
            with open(f"{base}.{a.formato}", "wb") as f:
                f.write(exportar(res, a.formato))
        r = res["resumo"]
        print(f"{os.path.basename(caminho)}: {r['atende']} atende, {r['nao_atende']} não atende, "
              f"{r['nao_verificavel']} não verificável -> {base}.{a.formato}")
        for c in res["conferencias"]:
            print(f"   [{c['rotulo_status']:>15}] {c['titulo']}: {c['resumo']}")
        for av in res["leitura"]["avisos"]:
            print(f"   AVISO: {av}")
