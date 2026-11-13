# LineaReport no navegador (protótipo)

Versão do LineaReport que roda inteira no navegador, sem servidor de aplicação. O mesmo código Python
de `backend/linea` é executado pelo [Pyodide](https://pyodide.org) (Python compilado para WebAssembly).
O relatório enviado não sai do computador do usuário.

## Gerar a pasta do site

```
python navegador/montar.py                 # gera navegador/dist
python navegador/montar.py --saida docs    # gera a pasta usada pelo GitHub Pages
```

O resultado é uma pasta de arquivos estáticos (cerca de 10 MB). Publique-a em qualquer servidor web
(IIS, Apache, nginx, SharePoint que sirva .html e .js, GitHub Pages) e coloque o link na página da intranet.
Abrir o `index.html` com dois cliques, sem servidor web, não funciona: o navegador bloqueia o carregamento.

## Como funciona

- Na primeira visita, o navegador baixa o Pyodide e as bibliotecas de cálculo (numpy, scipy etc.),
  cerca de 30 a 50 MB, e leva de 10 a 30 segundos. Depois fica em cache.
- O preparo começa assim que a página abre, enquanto o usuário lê as instruções.
- `motor.js` faz a ponte entre a página (`frontend/app.js`, a mesma da versão com servidor) e o Python.

## Intranet sem acesso à internet

Por padrão o Pyodide vem de `https://cdn.jsdelivr.net/pyodide/v0.27.7/full/`. Se os computadores da
instituição não acessarem esse endereço:

1. Baixe `pyodide-0.27.7.tar.bz2` em https://github.com/pyodide/pyodide/releases/tag/0.27.7 e extraia.
2. Copie para dentro da pasta do site, numa subpasta `pyodide/`, ao menos: `pyodide.js`, `pyodide.asm.js`,
   `pyodide.asm.wasm`, `python_stdlib.zip`, `pyodide-lock.json` e os pacotes `numpy`, `scipy`, `openblas`,
   `lxml`, `libxml`, `libxslt`, `pillow`, `libjpeg`, `cryptography`, `openssl`, `charset_normalizer`,
   `typing_extensions`, `micropip`, `packaging` (arquivos `.whl`/`.zip` com esses nomes).
   Se preferir não escolher, copie a pasta inteira (cerca de 300 MB).
3. Em `config.js`, acrescente `PYODIDE_URL: "pyodide/"`.
