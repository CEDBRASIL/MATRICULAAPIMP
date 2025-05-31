from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, json, base64, requests, mercadopago, threading, datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ───────────── CURSOS → PLANOS ───────────── #
CURSO_PLANO_MAP = {
    "Excel PRO":                          [161, 197, 201],
    "Desigh Gráfico":                     [254, 751, 169],
    "Analise & Desenvolvimento de Sistemas": [590, 176, 239, 203],
    "Administração":                      [129, 198, 156, 154],
    "Inglês Fluente":                     [263, 280, 281],
    "Inglês Kids":                        [266],
    "Informática Essencial":              [130, 599, 161, 160, 162],
    "Especialista em Marketing & Vendas": [123, 199, 202, 264, 441, 780, 828, 829, 236, 734],
    "Pacote Office":                      [161, 197, 201, 160, 162],
}

OM_BASE         = os.getenv("OM_BASE")
BASIC_B64       = os.getenv("BASIC_B64")
UNIDADE_ID      = os.getenv("UNIDADE_ID")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
CHATPRO_URL     = os.getenv("CHATPRO_URL")
CHATPRO_TOKEN   = os.getenv("CHATPRO_TOKEN")

print(f"TESTE {MP_ACCESS_TOKEN}")

DISCORD_FIXO = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_APIKEY = "2712587"
CALLMEBOT_PHONE = "+556186660241"

CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Ajuste para garantir que o ambiente de teste seja usado
is_test_mode = MP_ACCESS_TOKEN.startswith("TEST-")

# Ajustar URLs e valores para o ambiente de teste
back_url = "https://www.test.com/obrigado" if is_test_mode else "https://www.cedbrasilia.com.br/obrigado"
notification_url = "https://www.test.com/webhook" if is_test_mode else "https://matriculaapimp.onrender.com/webhook"
transaction_amount = 1.00 if is_test_mode else 49.90

class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    email: str
    cursos: list[str]

def log(msg: str):
    print(msg)
    for webhook in [DISCORD_WEBHOOK, DISCORD_FIXO]:
        if webhook:
            try:
                requests.post(webhook, json={"content": msg}, timeout=4)
            except: pass

def enviar_callmebot(msg: str):
    try:
        params = {
            "phone": CALLMEBOT_PHONE,
            "text": msg,
            "apikey": CALLMEBOT_APIKEY
        }
        requests.get(CALLMEBOT_URL, params=params, timeout=10)
    except: pass

def obter_token_unidade() -> str:
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError(f"Falha token unidade: {r.status_code}")

def total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise RuntimeError("Falha total alunos")

def proximo_cpf(incr: int = 0) -> str:
    with cpf_lock:
        seq = total_alunos() + 1 + incr
        return CPF_PREFIXO + str(seq).zfill(3)

def cadastrar_aluno(nome: str, whatsapp: str, email: str, token_key: str, cursos: list[int]) -> tuple[str | None, str | None]:
    for i in range(60):
        cpf = proximo_cpf(i)
        payload = {
            "token": token_key,
            "nome": nome,
            "email": email,
            "whatsapp": whatsapp,
            "fone": whatsapp,
            "celular": whatsapp,
            "data_nascimento": "2000-01-01",
            "doc_cpf": cpf,
            "doc_rg": "000000000",
            "pais": "Brasil",
            "uf": "DF",
            "cidade": "Brasília",
            "endereco": "Não informado",
            "bairro": "Centro",
            "cep": "70000-000",
            "complemento": "",
            "numero": "0",
            "unidade_id":"4158",
            "senha": "123456"  # Set default password
            

        }
        r = requests.post(f"{OM_BASE}/alunos", data=payload,
                          headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        log(f"[CAD] tent {i+1}/60 | {r.status_code} | {r.text[:80]}")
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            if matricular_aluno(aluno_id, cursos, token_key):
                enviar_callmebot("✅ Matrícula gerada com sucesso.")
                return aluno_id, cpf
        if "já está em uso" not in (r.json() or {}).get("info", "").lower():
            break
    return None, None

def matricular_aluno(aluno_id: str, cursos: list[str], token_key: str) -> bool:
    if not cursos:
        log("[MAT] Nenhum curso informado para matrícula.")
        return False

    # Mapear os nomes dos cursos para seus respectivos IDs
    cursos_ids = []
    for curso in cursos:
        cursos_ids.extend(CURSO_PLANO_MAP.get(curso, []))

    if not cursos_ids:
        log("[MAT] Nenhum ID de curso válido encontrado.")
        return False

    # Garantir que os IDs dos cursos sejam enviados como uma string separada por vírgulas
    cursos_str = ",".join(map(str, cursos_ids))
    payload = {
        "token": token_key,
        "cursos": cursos_str
    }
    log(f"[MAT] Enviando payload: {payload}")

    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}",
                      data=payload,
                      headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    log(f"[MAT] {r.status_code} | {r.text[:80]}")

    if not r.ok:
        log(f"[MAT] Erro ao matricular aluno {aluno_id}: {r.text}")

    return r.ok and r.json().get("status") == "true"

def criar_assinatura(nome: str, whatsapp: str, email: str, cursos: list[int]) -> str:
    data = {"nome": nome, "whatsapp": whatsapp, "email": email, "cursos": cursos}
    ext_ref = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    payload = {
        "reason": f"Assinatura CED – {nome}",
        "external_reference": ext_ref,
        "payer_email": email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": transaction_amount,
            "currency_id": "BRL",
            "payment_methods_allowed": {
                "payment_types": ["ticket", "credit_card"]  # Adiciona boleto bancário e cartão de crédito
            }
        },
        "back_url": back_url,
        "notification_url": notification_url
    }
    r = sdk.preapproval().create(payload)
    if r["status"] == 201:
        return r["response"]["init_point"]
    log(f"[MP] Falha assinatura {r}")
    detailed_error = f"[MP] Falha assinatura | Status: {r['status']} | Erro: {r['response']}"
    log(detailed_error)
    requests.post(DISCORD_FIXO, json={"content": detailed_error}, timeout=4)
    raise HTTPException(500, f"Falha ao criar assinatura: {r['response']}")

def enviar_whatsapp(numero: str, mensagem: str):
    numero = numero if numero.startswith("55") else f"55{numero}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": CHATPRO_TOKEN
    }
    data = {"number": numero, "message": mensagem}
    r = requests.post(CHATPRO_URL, headers=headers, json=data, timeout=10)
    log(f"[CHATPRO] {r.status_code} {r.text[:80]}")

def montar_msg(nome: str, cpf: str, cursos: list[int]):
    lista = ", ".join(map(str, cursos))
    data_pgto = datetime.date.today().strftime("%d/%m/%Y")
    return (
        f"👋 *Seja bem-vindo(a), {nome}!* \n\n"
        f"🔑 *Acesso*\nLogin: *{cpf}*\nSenha: *123456*\n\n"
        f"📚 *Cursos Adquiridos:* \n{lista}\n\n"
        f"💳 *Data de pagamento:* *{data_pgto}*\n\n"
        "🧑‍🏫 *Grupo da Escola:* https://chat.whatsapp.com/Gzn00RNW15ABBfmTc6FEnP\n\n"
        "📱 *Acesse pelo seu dispositivo preferido:*\n"
        "• *Android:* https://play.google.com/store/apps/details?id=br.com.om.app&hl=pt\n"
        "• *iOS:* https://apps.apple.com/fr/app/meu-app-de-cursos/id1581898914\n"
        "• *Computador:* https://ead.cedbrasilia.com.br/\n\n"
        "Caso deseje trocar ou adicionar outros cursos, basta responder a esta mensagem.\n\n"
        "Obrigado por escolher a *CED Cursos*! Estamos aqui para ajudar nos seus objetivos educacionais.\n\n"
        "Atenciosamente, *Equipe CED*"
    )

@app.post("/checkout")
def checkout(data: CheckoutData):
    ids = []
    for curso in data.cursos:
        ids.extend(CURSO_PLANO_MAP.get(curso, []))
    link = criar_assinatura(data.nome, data.whatsapp, data.email, ids)
    return {"status": "link-gerado", "mp_link": link}

@app.get("/secure")
def secure():
    return {"status": "ativo"}

@app.post("/teste-webhook")
def teste_webhook(data: CheckoutData):
    try:
        ext_ref = base64.urlsafe_b64encode(json.dumps({
            "nome": data.nome,
            "whatsapp": data.whatsapp,
            "email": data.email,
            "cursos": data.cursos
        }).encode()).decode()

        # Simulação direta do fluxo com pagamento aprovado
        status_pgto = "authorized"
        nome, whatsapp, email, cursos = data.nome, data.whatsapp, data.email, data.cursos

        log(f"[TESTE] Webhook simulado | Status: {status_pgto} | Nome: {nome}")
        enviar_callmebot("💰 [TESTE] Pagamento aprovado com sucesso.")

        token_unit = obter_token_unidade()
        aluno_id, cpf_final = cadastrar_aluno(nome, whatsapp, email, token_unit, cursos)
        if not aluno_id:
            log("❌ [TESTE] Falha no cadastro")
            return {"status": "falha_cadastro"}

        mensagem = montar_msg(nome, cpf_final, cursos)
        enviar_whatsapp(whatsapp, mensagem)
        log(f"✅ [TESTE] Concluído | aluno {aluno_id}")
        return {"status": "ok", "aluno_id": aluno_id, "cpf": cpf_final}
    except Exception as e:
        log(f"❌ [TESTE] Erro inesperado: {str(e)}")
        return {"status": "erro", "erro": str(e)}

@app.post("/webhook")
async def mp_webhook(req: Request):
    body = await req.json()
    topic = body.get("type") or body.get("topic")
    if topic not in ("preapproval", "authorized_payment"):
        return {"status": "ignorado"}

    preapproval_id = body.get("id") or body.get("data", {}).get("id")
    if not preapproval_id:
        return {"status": "sem id"}

    info = sdk.preapproval().get(preapproval_id)
    if info["status"] != 200:
        return {"status": "erro mp"}

    data = info["response"]
    status_pgto = data.get("status")

    ext_ref = data.get("external_reference")
    if ext_ref:
        aluno_data = json.loads(base64.urlsafe_b64decode(ext_ref).decode())
        nome = aluno_data.get("nome")
    else:
        nome = "N/A"

    # Logar qualquer status
    log(f"📩 Webhook recebido | Status: {status_pgto} | Nome: {nome} | ID: {preapproval_id}")

    if status_pgto != "authorized":
        return {"status": f"ignorado - {status_pgto}"}

    # Continua se autorizado
    aluno_data = json.loads(base64.urlsafe_b64decode(ext_ref).decode())
    nome, whatsapp, email, cursos = aluno_data["nome"], aluno_data["whatsapp"], aluno_data["email"], aluno_data["cursos"]

    enviar_callmebot("💰 Pagamento aprovado com sucesso.")

    token_unit = obter_token_unidade()
    aluno_id, cpf_final = cadastrar_aluno(nome, whatsapp, email, token_unit, cursos)
    if not aluno_id:
        log("❌ Webhook: falha cadastro após pagamento")
        return {"status": "falha_cadastro"}

    mensagem = montar_msg(nome, cpf_final, cursos)
    enviar_whatsapp(whatsapp, mensagem)
    log(f"✅ Webhook concluído | aluno {aluno_id}")
    return {"status": "ok"}
