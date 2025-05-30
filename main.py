from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests

app = FastAPI()

# Variáveis de ambiente
OM_BASE = os.getenv("OM_BASE")
BASIC_B64 = os.getenv("BASIC_B64")
TOKEN_KEY = os.getenv("TOKEN_KEY")
UNIDADE_ID = os.getenv("UNIDADE_ID")
CPF_PREFIXO = "20254158"

# Model de entrada
class CheckoutData(BaseModel):
    nome: str
    whatsapp: str
    cursos: list[int]

def total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"})
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    return 0

def proximo_cpf() -> str:
    seq = total_alunos() + 1
    return CPF_PREFIXO + str(seq).zfill(3)

def cadastrar_aluno(nome: str, whatsapp: str, usuario: str) -> tuple[int|None, str|None]:
    for i in range(60):
        cpf = str(int(usuario) + i).zfill(len(usuario))
        payload = {
            'token': TOKEN_KEY,
            'nome': nome,
            'celular': whatsapp,
            'doc_cpf': cpf,
            'usuario': cpf,
            'email': f"{cpf}@ced.com",
            'senha': '123456'
        }
        headers = {"Authorization": f"Basic {BASIC_B64}"}
        r = requests.post(f"{OM_BASE}/alunos", data=payload, headers=headers)
        if r.ok and r.json().get("status") == "true":
            return r.json()["data"]["id"], cpf
        info = (r.json() or {}).get("info", "").lower()
        if "já está em uso" not in info:
            break
    return None, None

def matricular_aluno(aluno_id: int, cursos: list[int]) -> bool:
    payload = {
        'token': TOKEN_KEY,
        'cursos': ','.join(map(str, cursos))
    }
    headers = {"Authorization": f"Basic {BASIC_B64}"}
    r = requests.post(f"{OM_BASE}/alunos/matricula/{aluno_id}", data=payload, headers=headers)
    return r.ok and r.json().get("status") == "true"

@app.post("/checkout")
def processar_checkout(data: CheckoutData):
    cpf_usuario = proximo_cpf()
    aluno_id, usuario = cadastrar_aluno(data.nome, data.whatsapp, cpf_usuario)

    if not aluno_id:
        raise HTTPException(status_code=400, detail="Falha ao cadastrar aluno")

    if not matricular_aluno(aluno_id, data.cursos):
        raise HTTPException(status_code=400, detail="Falha ao matricular aluno")

    return {"status": "sucesso", "aluno_id": aluno_id, "usuario": usuario}
