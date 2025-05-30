from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
import mercadopago
from dotenv import load_dotenv

load_dotenv()  # para carregar .env

app = FastAPI()

# Variáveis do OM
OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
TOKEN_KEY = os.getenv("TOKEN_KEY")
UNIDADE_ID = os.getenv("UNIDADE_ID")
CPF_PREFIXO = "20254158"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Variáveis Mercado Pago
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

# Cliente Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    cursos: list[int]

def log_discord(mensagem: str):
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": mensagem})
    except Exception as e:
        print(f"Erro ao enviar log para Discord: {e}")

# Funções OM aqui (total_alunos, proximo_cpf, cadastrar_aluno, matricular_aluno) -- mantenha como antes

# Função para criar preferência Mercado Pago
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
        return preference_response["response"]["init_point"]  # URL para checkout
    else:
        return None

@app.post("/checkout")
def processar_checkout(data: CheckoutData):
    cpf_usuario = proximo_cpf()
    aluno_id, usuario = cadastrar_aluno(data.nome, data.whatsapp, cpf_usuario)

    if not aluno_id:
        raise HTTPException(status_code=400, detail="Falha ao cadastrar aluno")

    if not matricular_aluno(aluno_id, data.cursos):
        raise HTTPException(status_code=400, detail="Falha ao matricular aluno")

    # Cria link de pagamento Mercado Pago
    preco = 59.90  # preço fixo ou você pode parametrizar
    titulo = f"Matrícula - {data.nome}"
    mp_link = criar_preferencia_mp(titulo, preco)

    if not mp_link:
        raise HTTPException(status_code=500, detail="Falha ao criar preferência de pagamento")

    log_discord(f"✅ Processo finalizado com sucesso para {data.nome} | Login: {usuario}")

    return {"status": "sucesso", "aluno_id": aluno_id, "usuario": usuario, "mp_link": mp_link}

@app.get("/secure")
def renovar_token():
    log_discord("🔄 Ping recebido em /secure - instância ativa")
    return {"status": "ativo"}
