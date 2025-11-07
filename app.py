import os
import json
import re
from flask import Flask, request, jsonify
import requests

# ========= ENV =========
WHATSAPP_TOKEN     = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID  = os.getenv("WHATSAPP_PHONE_ID", "")  # EX.: 884755701380784  (ID numérico!)
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")

# ========= PROMPT =========
VOATA_PROMPT = """
## ✅ Prompt de Comando — Agente WhatsApp Voata (v1.3)

Papel (persona):
Você é o Agente Voata WhatsApp, assistente automático da recepção da Voata Odontologia (slogan: “Sorrir diferente”).
Seu papel é acolher, entender a demanda, coletar informações essenciais, facilitar o agendamento e manter o atendimento organizado para a Yasmim, responsável única pelo WhatsApp da clínica.

IMPORTANTE:
- Todas as conversas acontecem sempre pelo WhatsApp da Yasmim (este número).
- Nunca transfira o paciente para outro número.
- A Dra. Cleyde não fala diretamente com pacientes por WhatsApp/telefone.
- Dúvidas clínicas: enviar para avaliação interna e a Yasmim retorna a resposta ao paciente.

Estrutura da Clínica:
- Recepção/Agendamentos: Yasmim (este número)
- Pós-venda (pacientes em tratamento): Cristina (outro número – não repassar automaticamente)
- Direção clínica: Dra. Cleyde (sem contato direto com pacientes)

Endereço e dados fixos:
- Avenida Brasília, 1888 (sobreloja) – Bairro São Benedito – Santa Luzia/MG (esquina com Rua Alvorada)
- Maps: https://maps.app.goo.gl/DDwjsc34BRqjpG5w6
- Horário: Seg–Sex 08:00–18:00 | Sáb 08:00–12:00
- Estacionamento: pago próximo e também pode estacionar na rua.
- CRM: Simples Dental
- Serviços: Cosmética do Sorriso, Ortodontia, Implantes, Check-up com câmera intraoral (Skycam 60x)

Objetivos do agente:
1) Identificar intenção.
2) Coletar nome + período + motivo.
3) Sugerir 2 opções de horário.
4) Confirmar e registrar.
5) Enviar instruções anti-falta.
6) Dúvidas clínicas: avaliação interna → retorno pela Yasmim.

Saída obrigatória (sempre em 2 blocos):
1) WA_MSG: as mensagens que serão enviadas no WhatsApp (texto puro; no máximo 3 bolhas curtas).
2) CRM_ACTION: um JSON válido, curto, com uma das intenções:
   create_lead, schedule_appointment, update_lead, reschedule, cancel, handoff_human, send_reminder, no_action
   - Quando houver dúvida clínica, use: {"intent":"handoff_human","assignee":"Yasmim","reason":"dúvida clínica para avaliação interna"}

Regras:
- Sem diagnóstico, prescrição ou valores exatos sem avaliação.
- Não prometa ligação da Dra. Cleyde.
- Use sempre o mesmo link do Maps quando falar de endereço.
- Se o paciente sumir: um follow-up gentil depois (~24h).

Templates (resumidos):
1) Boas-vindas:
  WA_MSG:
    - "Olá! Sou o assistente da recepção da Voata 😊 Como posso te ajudar hoje?"
    - "Quer agendar uma avaliação de qual tratamento?"
    - "Pode me passar seu nome completo e melhor período (manhã/tarde/sábado)?"
  CRM_ACTION: {"intent":"create_lead","channel":"whatsapp"}

2) Horários:
  WA_MSG:
    - "Perfeito, [NOME]! Tenho [DIA/HH:MM] ou [DIA/HH:MM]. Qual prefere?"
    - "Na avaliação você vê tudo em tela com câmera intraoral (Skycam 60x) ✨"
  CRM_ACTION:
    {"intent":"schedule_appointment","name":"[NOME]","phone":"[WHATS]","treatment":"[TRATAMENTO]","preferred_slots":["[DIA/HH:MM]","[DIA/HH:MM]"],"notes":"primeira avaliação"}

3) Confirmação + anti-falta:
  WA_MSG:
    - "Agendado! ✅ [DIA/HH:MM] aqui na Voata."
    - "Chegue 10 min antes para cadastro. Se precisar reagendar, é só avisar."
    - "Endereço: Avenida Brasília, 1888 (sobreloja), São Benedito – Santa Luzia/MG (esq. Rua Alvorada). Maps: https://maps.app.goo.gl/DDwjsc34BRqjpG5w6. Estacionamento: pago próximo e pode parar na rua."
  CRM_ACTION:
    {"intent":"update_lead","notes":"Agendamento confirmado [DIA/HH:MM]; enviar lembrete 24h antes"}

4) Dúvida clínica:
  WA_MSG:
    - "Entendi 😊 Para garantir orientação segura, vou verificar internamente com a equipe clínica e te retorno por aqui, tudo bem?"
  CRM_ACTION:
    {"intent":"handoff_human","assignee":"Yasmim","reason":"dúvida clínica para avaliação interna"}
"""

# ========= LLM =========
import openai
openai.api_key = OPENAI_API_KEY

def run_llm(user_text: str) -> str:
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VOATA_PROMPT},
                {"role": "user", "content": f"MENSAGEM DO PACIENTE:\n{user_text}"}
            ],
            temperature=0.2
        )
        return resp.choices[0].message["content"].strip()
    except Exception as e:
        return (
            "WA_MSG:\n"
            "- Oi! Tivemos uma instabilidade agora. Pode repetir sua mensagem, por favor?\n\n"
            "CRM_ACTION:\n"
            '{"intent":"no_action","notes":"erro LLM: ' + str(e).replace('"', "'") + '"}'
        )

# ========= Parsers =========
WA_PATTERN  = re.compile(r"WA_MSG\s*:\s*(.+?)(?:\n\n|CRM_ACTION)", re.DOTALL | re.IGNORECASE)
CRM_PATTERN = re.compile(
    r"CRM_ACTION\s*:\s*```json\s*(\{.*?\})\s*```|CRM_ACTION\s*:\s*(\{.*?\})",
    re.DOTALL | re.IGNORECASE
)

def parse_llm_output(text: str):
    wa = ""
    m = WA_PATTERN.search(text)
    if m:
        wa = re.sub(r"^\-\s*", "", m.group(1).strip(), flags=re.MULTILINE)

    crm = {"intent": "no_action"}
    m2 = CRM_PATTERN.search(text)
    if m2:
        raw = (m2.group(1) or m2.group(2) or "").strip()
        try:
            crm = json.loads(raw)
        except Exception:
            pass
    return wa, crm

# ========= WhatsApp send =========
def send_whatsapp_text(to: str, body: str):
    # normaliza para +55...
    to = (to or "").strip()
    if not to.startswith("+"):
        to = "+" + to

    ZAPI_INSTANCE = "3E53BE161E0B2107E3C2428BC0F148DA"
    ZAPI_TOKEN    = "85E59C4B87C6C6CE65A2333C"
    # Se sua instância estiver com "Exigir Client Token" ligado em Segurança,
    # preencha abaixo com o Client Token configurado lá. Se estiver desligado, deixe vazio.
    ZAPI_CLIENT_TOKEN = ""  # exemplo: "ff4a66...bf981s" (se ativo na Z-API)

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}/send-text"

    headers = {"Content-Type": "application/json"}
    if ZAPI_CLIENT_TOKEN:
        headers["Client-Token"] = ZAPI_CLIENT_TOKEN

    data = {"phone": to, "message": body}

    print(">>> ENVIANDO VIA Z-API PARA:", to)
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=20)
        print("=== ZAPI RESP ===", resp.status_code, resp.text[:300])
    except Exception as e:
        print("=== ZAPI ERROR ===", repr(e))



# ========= Flask =========
def _get_first(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            # tenta extrair texto de dicionários comuns da Z-API
            for k in ("message", "text", "body", "content"):
                if isinstance(v.get(k), str) and v.get(k).strip():
                    return v.get(k).strip()
        # arrays não são esperados aqui
    return ""

@app.route("/zapi-webhook", methods=["POST"])
def zapi_webhook():
    data = request.get_json(force=True, silent=True) or {}
    print(">>> ZAPI IN RAW:", json.dumps(data)[:800])

    # Z-API manda vários formatos; estes campos são os mais comuns:
    from_me   = bool(data.get("fromMe", False))
    phone     = _get_first(
        data.get("phone"),
        data.get("from"),
        data.get("sender"),
        (data.get("message") or {}).get("from"),
        (data.get("contact") or {}).get("phone"),
        (data.get("conversation") or {}).get("phone"),
    )
    text_in   = _get_first(
        data.get("text"),
        data.get("message"),
        data.get("body"),
        (data.get("message") or {}),
        (data.get("data") or {}),
    )

    # Evita loop: ignore mensagens enviadas pela própria conta (fromMe = True)
    if from_me:
        print(">>> IGNORADO (fromMe=True)")
        return jsonify({"status": "ignored", "reason": "fromMe"}), 200

    # Se veio sem telefone, ignora
    if not phone:
        print(">>> IGNORADO (sem phone)")
        return jsonify({"status": "ignored", "reason": "no phone"}), 200

    # Se não é texto, responda educadamente
    if not text_in:
        send_whatsapp_text(phone, "Oi! Por enquanto consigo entender apenas mensagens de texto 😊")
        return jsonify({"status": "ok"}), 200

    print("FROM_RAW_ZAPI:", phone)
    print("TEXT_IN:", text_in)

    # LLM
    llm_out = run_llm(text_in)
    print("---- LLM RAW (ZAPI) ----\n", llm_out)
    wa_msg, crm_json = parse_llm_output(llm_out)
    print("---- CRM_ACTION (ZAPI) ----\n", crm_json)

    send_whatsapp_text(phone, wa_msg)
    return jsonify({"status": "ok"}), 200
