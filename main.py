from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, json, base64, requests, mercadopago, threading, datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ─────────── CORS ─────────── #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajuste p/ domínio do site em produção
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ─────────── Variáveis ─────── #
OM_BASE         = os.getenv("OM_BASE")
BASIC_B64       = os.getenv("BASIC_B64")
UNIDADE_ID      = os.getenv("UNIDADE_ID")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
CHATPRO_URL     = os.getenv("CHATPRO_URL")
CHATPRO_TOKEN   = os.getenv("CHATPRO_TOKEN")

CPF_PREFIXO = "20254158"
cpf_lock    = threading.Lock()

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ─────────── Modelos ───────── #
class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    email: str
    cursos: list[int]

# ─────────── Utilidades ────── #
def log(msg: str):
    print(msg)
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=4)
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

# ─────────── Cadastro & Matrícula ────── #
def cadastrar_aluno(nome: str, whatsapp: str, email: str, token_key: str,
                    cursos: list[int]) -> tuple[str | None, str | None]:
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
            "cep": "70000-000"
        }
        r = requests.post(f"{OM_BASE}/alunos",
                          data=payload,
                          headers={"Authorization": f"Basic {BASIC_B64}"},
                          timeout=10)
        log(f"[CAD] tent {i+1}/60 | {r.status_code}")
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            if matricular_aluno(aluno_id, cursos, token_key):
                return aluno_id, cpf
        if "já está em uso" not in (r.json() or {}).get("info", "").lower():
            break
    return None, None

def matricular_aluno(aluno_id: str, cursos: list[int], token_key: str) -> bool:
    payload = {"token": token_key, "cursos": ",".join(map(str, cursos))}
    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}",
                      data=payload,
                      headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    log(f"[MAT] {r.status_code}")
    return r.ok and r.json().get("status") == "true"

# ─────────── Mercado Pago (assinatura) ───── #
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
        "transaction_amount": 49.90,
        "currency_id": "BRL"
    },
    "back_url": "https://www.cedbrasilia.com.br/obrigado",
    "notification_url": "https://matriculaapimp.onrender.com/webhook"
}

    r = sdk.preapproval().create(payload)
    if r["status"] == 201:
        return r["response"]["init_point"]
    log(f"[MP] Falha assinatura {r}")
    raise HTTPException(500, "Falha ao criar assinatura")

# ─────────── ChatPro ───── #
def enviar_whatsapp(numero: str, mensagem: str):
    numero = numero if numero.startswith("55") else f"55{numero}"
    headers = {"Content-Type": "application/json",
               "Authorization": CHATPRO_TOKEN}
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

# ─────────── Endpoints ───── #
@app.post("/checkout")
def checkout(data: CheckoutData):
    link = criar_assinatura(data.nome, data.whatsapp, data.email, data.cursos)
    return {"status": "link-gerado", "mp_link": link}

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
    if data.get("status") != "authorized":
        return {"status": "nao autorizado"}

    ext_ref = data.get("external_reference")
    aluno_data = json.loads(base64.urlsafe_b64decode(ext_ref).decode())
    nome     = aluno_data["nome"]
    whatsapp = aluno_data["whatsapp"]
    email    = aluno_data["email"]
    cursos   = aluno_data["cursos"]

    token_unit = obter_token_unidade()
    aluno_id, cpf_final = cadastrar_aluno(nome, whatsapp, email, token_unit, cursos)
    if not aluno_id:
        log("❌ Webhook: falha cadastro após pagamento")
        return {"status": "falha_cadastro"}

    mensagem = montar_msg(nome, cpf_final, cursos)
    enviar_whatsapp(whatsapp, mensagem)
    log(f"✅ Webhook concluído | aluno {aluno_id}")
    return {"status": "ok"}

@app.get("/secure")
def secure():
    return {"status": "ativo"}
