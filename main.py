from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
import mercadopago
from dotenv import load_dotenv
from threading import Lock

load_dotenv()  # carrega variáveis do .env

app = FastAPI()

# ─── Variáveis de ambiente ──────────────────────────────
OM_BASE = os.getenv("OM_BASE")  # Ex: https://meuappdecursos.com.br/ws/v2
BASIC_B64 = os.getenv("BASIC_B64")  # Basic base64 do OM
TOKEN_KEY = os.getenv("TOKEN_KEY")  # Token da unidade OM
UNIDADE_ID = os.getenv("UNIDADE_ID")  # ID da unidade OM
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")  # webhook Discord logs
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")  # Mercado Pago token

# ─── Config Mercado Pago ─────────────────────────────────
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ─── Locks para concorrência ────────────────────────────
cpf_lock = Lock()

# ─── Constantes ─────────────────────────────────────────
CPF_PREFIXO = "20254158"

# ─── Modelos ────────────────────────────────────────────
class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    cursos: list[int]

# ─── Função para logar no Discord ────────────────────────
def log_discord(mensagem: str):
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": mensagem})
    except Exception as e:
        print(f"Erro ao enviar log para Discord: {e}")

# ─── Funções OM ──────────────────────────────────────────

def total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"})
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    # fallback
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"})
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise RuntimeError("Não foi possível obter o total de alunos.")

def proximo_cpf(incremento: int = 0) -> str:
    """Gera CPF sequencial com opção de incrementar manualmente."""
    with cpf_lock:
        seq = total_alunos() + 1 + incremento
        return CPF_PREFIXO + str(seq).zfill(3)

def cadastrar_aluno(nome: str, whatsapp: str, cpf: str, tentativas: int = 60) -> tuple[int | None, str | None]:
    cadastro_base = {
        "token": TOKEN_KEY,
        "nome": nome,
        "doc_cpf": cpf,
        "usuario": cpf,
        "email": f"{cpf}@ced.com",  # necessário para OM, email fake
        "celular": whatsapp,
        "senha": "123456",  # padrão
    }
    for i in range(tentativas):
        cadastro = cadastro_base.copy()
        if i > 0:
            novo_cpf = str(int(cadastro["usuario"]) + 1).zfill(len(cadastro["usuario"]))
            cadastro["usuario"] = novo_cpf
            cadastro["doc_cpf"] = novo_cpf
            cadastro["email"] = f"{novo_cpf}@ced.com"
        r = requests.post(f"{OM_BASE}/alunos", data=cadastro,
                          headers={"Authorization": f"Basic {BASIC_B64}"})
        log_discord(f"[CADASTRO] tentativa {i+1}/{tentativas} | {r.status_code} | {r.text}")
        if r.ok and r.json().get("status") == "true":
            data = r.json()["data"]
            return int(data["id"]), cadastro["usuario"]
        info = (r.json() or {}).get("info", "").lower()
        if "já está em uso" not in info:
            break
    log_discord("❌ Falha no cadastro após tentativas")
    return None, None

def matricular_aluno(aluno_id: int, cursos: list[int]) -> bool:
    url = f"{OM_BASE}/alunos/matricula/{aluno_id}"
    payload = {
        "token": TOKEN_KEY,
        "cursos": ",".join(map(str, cursos))
    }
    r = requests.post(url, data=payload, headers={"Authorization": f"Basic {BASIC_B64}"})
    log_discord(f"[MATRICULA] aluno_id={aluno_id} cursos={cursos} status={r.status_code} resp={r.text}")
    return r.ok and r.json().get("status") == "true"

# ─── Função para criar preferência Mercado Pago ─────────
def criar_preferencia_mp(titulo: str, preco: float):
    preference_data = {
        "items": [
            {
                "title": titulo,
                "quantity": 1,
                "unit_price": preco,
            }
        ]
    }
    preference_response = sdk.preference().create(preference_data)
    if preference_response["status"] == 201:
        return preference_response["response"]["init_point"]
    return None

# ─── Endpoint principal para checkout ───────────────────
@app.post("/checkout")
def processar_checkout(data: CheckoutData):
    try:
        cpf_usuario = proximo_cpf()
        aluno_id, usuario = cadastrar_aluno(data.nome, data.whatsapp, cpf_usuario)
        if not aluno_id:
            raise HTTPException(status_code=400, detail="Falha ao cadastrar aluno")
        if not matricular_aluno(aluno_id, data.cursos):
            raise HTTPException(status_code=400, detail="Falha ao matricular aluno")

        preco = 59.90  # valor fixo, ajuste se quiser
        titulo = f"Matrícula - {data.nome}"
        mp_link = criar_preferencia_mp(titulo, preco)
        if not mp_link:
            raise HTTPException(status_code=500, detail="Falha ao criar preferência de pagamento")

        log_discord(f"✅ Processo finalizado com sucesso para {data.nome} | Login: {usuario}")

        return {"status": "sucesso", "aluno_id": aluno_id, "usuario": usuario, "mp_link": mp_link}
    except Exception as e:
        log_discord(f"❌ Erro no /checkout: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")

# ─── Endpoint para checar instância ativa ───────────────
@app.get("/secure")
def renovar_token():
    log_discord("🔄 Ping recebido em /secure - instância ativa")
    return {"status": "ativo"}
