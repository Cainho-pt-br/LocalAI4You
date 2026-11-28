# Segurança

## Como avisar sobre uma falha

Use **Security → Report a vulnerability** neste repositório (aviso privado do GitHub). Não abra issue pública para
falhas de segurança. Inclua o que é afetado (site, app local, pacote da Microsoft Store), como reproduzir e o impacto.
A resposta vem em até 7 dias.

## O que está no escopo

- O app local (`download/LocalIntelligence/`): o painel em `127.0.0.1:8765`, downloads de modelos, o acesso remoto opcional.
- O site `localai4you.com.br` e o intermediário `/api/coleta`.
- Os pacotes publicados (release `app-latest` e Microsoft Store).

Fora do escopo: o Ollama, o LM Studio e os modelos de terceiros, que têm seus próprios canais.

## Como conferir um download

Cada release traz `SHA256SUMS.txt`. Depois de baixar:

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

No Windows (PowerShell): `Get-FileHash LocalAI4You-Windows.zip -Algorithm SHA256` e compare com o arquivo.
