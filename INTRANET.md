# LineaReport na intranet

Guia para instalar o LineaReport (versão web: Flask + HTML) num servidor da rede interna.
O app não acessa nenhum serviço externo e não grava nada em disco: cada relatório é lido em memória,
analisado e descartado. A fonte da página vem junto com o projeto (`frontend/fontes`).

## Requisitos

- Windows ou Linux com Python 3.10 a 3.13.
- Uma porta liberada na rede interna (padrão 8000).

## 1. Instalação

**Servidor com acesso à internet (direto ou pelo proxy da instituição):** basta rodar
`iniciar_servidor.bat`. Na primeira vez ele cria o ambiente e instala as dependências.
Se houver proxy, defina antes: `set HTTPS_PROXY=http://proxy.instituicao:porta`.

**Servidor sem internet:**

1. Numa máquina com internet, com Windows e a mesma versão do Python do servidor, rode `baixar_pacotes.bat`.
   Ele cria a pasta `pacotes` com todas as dependências.
2. Copie a pasta do projeto inteira, com `pacotes`, para o servidor.
3. No servidor, rode `iniciar_servidor.bat`. Ele instala a partir de `pacotes`, sem internet.

No Linux, o equivalente é:

```
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # ou: pip install --no-index --find-links ../pacotes -r requirements.txt
python servir.py
```

## 2. Execução

`iniciar_servidor.bat` (ou `python servir.py`) usa o servidor waitress, que atende várias pessoas ao mesmo tempo,
e escuta em toda a rede. Os usuários acessam `http://<nome-do-servidor>:8000`.

| Opção | Padrão | Para quê |
|---|---|---|
| `--porta` | 8000 | Porta de acesso |
| `--threads` | 4 | Análises atendidas ao mesmo tempo |
| `--host` | 0.0.0.0 | Use `127.0.0.1` quando o acesso for só pelo proxy reverso |
| `--prefixo` | (vazio) | Subpasta quando publicado atrás de proxy, ex.: `/lineareport` |

As opções também podem vir de variáveis de ambiente: `LINEA_PORTA`, `LINEA_THREADS`, `LINEA_HOST`, `LINEA_PREFIXO`.

Para iniciar junto com o Windows, cadastre `iniciar_servidor.bat` no Agendador de Tarefas
("Ao iniciar o computador") ou como serviço (por exemplo, com o NSSM). No Linux, use um serviço do systemd.

## 3. HTTPS e controle de acesso (opcional, a cargo da TI)

Publique o app atrás do proxy reverso da instituição (IIS com ARR ou nginx), que cuida do certificado e,
se necessário, da autenticação de rede. Exemplo para nginx, publicando em `https://intranet/lineareport/`:

```
location /lineareport/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    client_max_body_size 30m;
}
```

com o app iniciado por `servir.py --host 127.0.0.1 --prefixo /lineareport`. Acesse com a barra no fim do endereço.

## 4. Ajustes

- `frontend/config.js`: em `EMAIL_FEEDBACK`, o e-mail da equipe que recebe os comentários dos usuários.
- `backend/linea/config/criterios.json`: limites das conferências.
- Arquivos enviados têm no máximo 25 MB.
