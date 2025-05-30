from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
import mercadopago
import threading
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Variáveis de ambiente
OM_BASE = os.getenv("OM_BASE")  # https://meuappdecursos.com.br/ws/v2
BASIC_B64 = os.getenv("BASIC_B64")  # Basic Auth para pegar token
UNIDADE_ID = os.getenv("UNIDADE_ID")  # Exemplo: 4158
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TOKEN_KEY = os.getenv("TOKEN_KEY")  # Token para operações

CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()

# Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    cursos: list[int]

def log(mensagem: str):
    try:
        print(mensagem)
        requests.post(DISCORD_WEBHOOK, json={"content": mensagem})
    except Exception as e:
        print(f"Erro ao logar no Discord: {e}")

# Função para obter token dinâmico da unidade
def obter_token() -> str:
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    headers = {"Authorization": f"Basic {BASIC_B64}"}
    r = requests.get(url, headers=headers)
    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        log(f"[TOKEN] Token atualizado: {token}")
        return token
    else:
        log(f"Erro ao obter token: {r.status_code} {r.text}")
        raise RuntimeError("Não foi possível obter token da unidade")

# Função: Total de alunos
def total_alunos(token_key: str) -> int:
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

# Geração automática de CPF
def proximo_cpf(incremento: int = 0) -> str:
    with cpf_lock:
        seq = total_alunos(TOKEN_KEY) + 1 + incremento
        return CPF_PREFIXO + str(seq).zfill(3)

# Cadastro com tentativa e email fictício
def cadastrar_aluno(nome: str, whatsapp: str, token_key: str, tentativas: int = 60) -> tuple[str | None, str | None]:
    for i in range(tentativas):
        cpf = proximo_cpf(i)
        login = cpf
        email = f"{login}@cedbrasilia.com.br"
        cadastro = {
            "token": token_key,
            "nome": nome,
            "email": email,
            "whatsapp": whatsapp,
            "data_nascimento": "2000-01-01",
            "fone": whatsapp,
            "celular": whatsapp,
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

        r = requests.post(f"{OM_BASE}/alunos", data=cadastro, headers={"Authorization": f"Basic {BASIC_B64}"})
        log(f"[CADASTRO] tentativa {i+1}/{tentativas} | {r.status_code} {r.text}")

        if r.ok and r.json().get("status") == "true":
            return r.json()["data"]["id"], cpf

        info = (r.json() or {}).get("info", "").lower()
        if "já está em uso" not in info:
            break

    log("❌ Falha no cadastro após tentativas")
    return None, None

# Matrícula
def matricular_aluno(aluno_id: str, cursos: list[int], token_key: str) -> bool:
    payload = {
        "token": token_key,
        "cursos": ",".join(map(str, cursos))
    }
    url = f"{OM_BASE}/alunos/matricula/{aluno_id}"
    r = requests.post(url, data=payload, headers={"Authorization": f"Basic {BASIC_B64}"})
    log(f"[MATRÍCULA] {r.status_code} {r.text}")
    return r.ok and r.json().get("status") == "true"

# Preferência Mercado Pago
def criar_preferencia_mp(titulo: str, preco: float):
    preference_data = {
        "items": [
            {
                "title": titulo,
                "quantity": 1,
                "unit_price": preco
            }
        ]
    }
    response = sdk.preference().create(preference_data)
    if response["status"] == 201:
        return response["response"]["init_point"]
    return None

# Rota principal
@app.post("/checkout")
def processar_checkout(data: CheckoutData):
    token_key = obter_token()  # Obtém token atualizado
    aluno_id, usuario = cadastrar_aluno(data.nome, data.whatsapp, token_key)
    if not aluno_id:
        raise HTTPException(status_code=400, detail="Falha ao cadastrar aluno")

    if not matricular_aluno(aluno_id, data.cursos, token_key):
        raise HTTPException(status_code=400, detail="Falha ao matricular aluno")

    link = criar_preferencia_mp(f"Matrícula - {data.nome}", 59.90)
    if not link:
        raise HTTPException(status_code=500, detail="Falha ao criar link de pagamento")

    log(f"✅ Processo finalizado com sucesso para {data.nome} | Login: {usuario}")
    return {"status": "sucesso", "aluno_id": aluno_id, "usuario": usuario, "mp_link": link}

# Rota de verificação
@app.get("/secure")
def ping():
    return {"status": "ativo"}
