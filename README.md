# Voata WhatsApp Bot (Render Blueprint)

Este repositório contém um bot simples para WhatsApp Cloud API + OpenAI, pronto para deploy no Render.

## Arquivos
- `app.py` — servidor Flask com webhook do WhatsApp e chamada ao LLM com o prompt da Voata.
- `requirements.txt` — dependências Python.
- `Procfile` — comando de start para o Render (Gunicorn).
- `render.yaml` — Blueprint do Render (deploy com 1 clique).

## Variáveis de ambiente (no Render)
- `WHATSAPP_TOKEN` — token (Bearer) da Meta (WhatsApp Cloud API).
- `WHATSAPP_PHONE_ID` — ID do número (WhatsApp Cloud API).
- `OPENAI_API_KEY` — chave da OpenAI (ou outro provedor compatível).

## Webhook (Meta)
- Callback URL: `https://SEU-SERVICO.onrender.com/webhook`
- Verify Token: `VOATA2025` (mesmo valor definido em `app.py`)

## Teste
1. No painel da Meta, cadastre a URL do webhook e o Verify Token.
2. Envie mensagem para o número de teste da Meta (ou seu número oficial conectado).
3. O bot responderá com base no bloco `WA_MSG` do prompt da Voata.
