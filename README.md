# LineaReport

Conferência automática do relatório estatístico do SisDEA (.rtf ou .pdf): pressupostos da regressão linear,
micronumerosidade e testes de hipóteses, conforme a ABNT NBR 14653-2 e as orientações da SPU.
As conferências aparecem detalhadas na página; o relatório (.docx, .odt ou .pdf) é gerado apenas quando o usuário clica em "Exportar relatório" e escolhe o formato.
O app **não refaz o modelo**: lê os valores do relatório. Os testes de homocedasticidade e de
autocorrelação usam só regressões auxiliares sobre os resíduos informados pelo SisDEA.

## Como rodar no Windows

1. Instale o Python 3.10 ou superior (marque "Add Python to PATH").
2. Dê dois cliques em `iniciar.bat`. Na primeira vez, ele instala as dependências.
3. O navegador abre em http://127.0.0.1:8000.

Em outro sistema: `cd backend`, `pip install -r requirements.txt` e `python run_server.py`.

Sem interface (vários arquivos de uma vez):

```
cd backend
python analisar_cli.py pasta\*.rtf --formato pdf --saida resultados
```

Testes automatizados: `cd backend` e `python -m unittest discover -s tests -v`.

## Estrutura

```
backend/
  linea/
    rtf/reader.py            Leitor de RTF em Python puro (tabelas, ½, ², acentos)
    sisdea/parser.py         Localiza as seções do relatório (RTF) e monta o modelo
    sisdea/parser_pdf.py     Mesma leitura a partir do PDF (texto e posição das palavras)
    sisdea/modelo.py         Estrutura de dados do modelo
    estatistica/             Durbin-Watson (dL/dU exatos), BG, BP, White, Park, JB, K-S, qui-quadrado
    conferencias/regras.py   As 9 conferências (texto, critério, sugestões)
    config/criterios.json    TODOS os limites (edite aqui, não no código)
    relatorio/               Conteúdo do relatório e exportação .docx, .odt e .pdf
    analise.py               Orquestra tudo: bytes do RTF -> resultado (JSON)
    api.py                   API Flask (não armazena nada)
  run_server.py              Servidor local (API + frontend)
  analisar_cli.py            Linha de comando
  tests/                     Testes com os modelos Ex. 4 e Ex. 7
frontend/                    Interface (HTML/CSS/JS), separada do backend
  config.js                  Endereço da API e e-mail para comentários
```

## API

| Rota | Entrada | Saída |
|---|---|---|
| `GET /api/saude` | — | versão |
| `POST /api/analisar` | multipart, campo `arquivo` (.rtf ou .pdf) | análise em JSON |
| `POST /api/exportar/{docx,odt,pdf}` | JSON da análise | arquivo do relatório |

Para hospedar o frontend em outro servidor, defina `API_BASE` em `frontend/config.js` e a variável de
ambiente `LINEA_CORS_ORIGEM` no backend com o endereço do frontend.

## Decisões de critério

- **Linearidade:** os dois R do SisDEA (equação, escala transformada; função estimativa, escala original) devem ser > 0,75 (IN SPU).
- **Normalidade:** faixas do Manual da SPU (66–73%, 85–95%, 95–100%). Se alguma falhar, aplicam-se Qui-quadrado, K-S (Lilliefors) e Jarque-Bera a 5%; decide a maioria.
- **Homocedasticidade:** Park, White e Breusch-Pagan (Koenker) a 5%; decide a maioria.
- **Autocorrelação:** o SisDEA não imprime o DW; ele é calculado da coluna "Resíduo / DP". dL e dU vêm da distribuição exata (iguais às tabelas de Savin & White), com 90% (5% por cauda). Na região não conclusiva, aplica-se Breusch-Godfrey.
- **Multicolinearidade:** pares entre variáveis independentes nas tabelas isoladas e de influência; |r| ≤ 0,80. A coluna da dependente é ignorada.
- **Outliers:** ≤ 5% dos dados (5,00% atende). Cook ≤ 1.
- **Micronumerosidade:** variáveis dicotômicas e de códigos alocados, contadas só nos dados habilitados.
- **t e F:** graus da NBR 14653-2. A linha da variável dependente na tabela do t é o intercepto e não entra.
- **Dados desabilitados:** ficam fora de todas as contagens. A tabela de resíduos do SisDEA usa o ID da amostra (confirmado no Ex. 7).
- **Fora do escopo:** o enquadramento no grau de fundamentação não é feito; t e F informam apenas a faixa da significância.
- **PDF:** precisa ter texto (gerado pelo SisDEA, Word ou impressora de PDF). PDF digitalizado (imagem) não é lido. Como o PDF não guarda tabelas, a leitura usa a posição das palavras; a conferência da leitura abaixo confirma o resultado.
- **Conferência da leitura:** o app reconstitui os resíduos a partir dos dados e das transformações lidos. Se não coincidirem com os do relatório, os testes que dependem dos regressores ficam "não verificáveis", em vez de dar um resultado errado.

Fonte DejaVu Sans incluída para o PDF (licença livre, ver `relatorio/fontes`).
