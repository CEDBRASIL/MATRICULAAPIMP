# main.py – FastAPI completo
# Obtém token da unidade a cada /checkout para evitar token expirado

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, requests, mercadopago, threading
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ─────────────── CORS ─────────────── #
origins = [
    "https://seudominio.com",  # troque pelo domínio do site
    "http://localhost",
    "*",                       # use * só para teste
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────── Variáveis ─────────── #
OM_BASE         = os.getenv("OM_BASE")          # https://meuappdecursos.com.br/ws/v2
BASIC_B64       = os.getenv("BASIC_B64")        # Basic Auth
UNIDADE_ID      = os.getenv("UNIDADE_ID")       # ex: 4158
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")  # Mercado Pago
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")  # Discord logs

CPF_PREFIXO = "20254158"
cpf_lock    = threading.Lock()

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ─────────────── Model ─────────────── #
class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    cursos: list[int]

# ─────────────── Util ──────────────── #
def log(msg: str):
    print(msg)
    if DISCORD_WEBHOOK:
        try: requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
        except: pass

def obter_token() -> str:
    """Busca token dinâmico da unidade."""
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        log(f"[TOKEN] Atualizado: {token}")
        return token
    log(f"[TOKEN] Falha {r.status_code} {r.text}")
    raise HTTPException(500, "Falha ao obter token da unidade")

def total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise HTTPException(500, "Não foi possível obter total de alunos")

def proximo_cpf(incr: int = 0) -> str:
    with cpf_lock:
        seq = total_alunos() + 1 + incr
        return CPF_PREFIXO + str(seq).zfill(3)

# ─────────────── Cadastro ───────────── #
def cadastrar_aluno(nome: str, whatsapp: str, token: str, tentativas=60):
    for i in range(tentativas):
        cpf   = proximo_cpf(i)
        email = f"{cpf}@cedbrasilia.com.br"
        payload = {
            "token": token,
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
            "complemento": "",
            "bairro": "Centro",
            "cep": "70000-000"
        }
        r = requests.post(f"{OM_BASE}/alunos", data=payload,
                          headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
        log(f"[CADASTRO] tent.{i+1}/{tentativas} | {r.status_code} {r.text}")
        if r.ok and r.json().get("status") == "true":
            return r.json()["data"]["id"], cpf
        if "já está em uso" not in (r.json() or {}).get("info","").lower():
            break
    return None, None

# ─────────────── Matrícula ───────────── #
def matricular(aluno_id: str, cursos: list[int], token: str) -> bool:
    payload = {"token": token, "cursos": ",".join(map(str, cursos))}
    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}", data=payload,
                      headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=10)
    log(f"[MATRÍCULA] {r.status_code} {r.text}")
    return r.ok and r.json().get("status") == "true"

# ─────────────── MP Preferência ───────── #
def mp_link(titulo: str, price: float) -> str | None:
    pref = {"items":[{"title":titulo,"quantity":1,"unit_price":price}]}
    r = sdk.preference().create(pref)
    if r["status"] == 201:
        return r["response"]["init_point"]
    log(f"[MP] Erro preferência {r}")
    return None

# ─────────────── Endpoints ───────────── #
@app.post("/checkout")
def checkout(data: CheckoutData):
    token = obter_token()                       # token fresco a cada chamada
    aluno_id, usuario = cadastrar_aluno(data.nome, data.whatsapp, token)
    if not aluno_id:
        raise HTTPException(400, "Falha ao cadastrar aluno")
    if not matricular(aluno_id, data.cursos, token):
        raise HTTPException(400, "Falha ao matricular aluno")

    link = mp_link(f"Matrícula - {data.nome}", 59.90)
    if not link:
        raise HTTPException(500, "Falha ao gerar link de pagamento")

    log(f"✅ Sucesso {data.nome} | Login {usuario}")
    return {"status":"sucesso","aluno_id":aluno_id,"usuario":usuario,"mp_link":link}

@app.get("/secure")
def secure():
    return {"status":"ativo"}
