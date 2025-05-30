def cadastrar_aluno(nome: str, whatsapp: str, tentativas: int = 60) -> tuple[str | None, str | None]:
    for i in range(tentativas):
        cpf = proximo_cpf(i)
        login = cpf  # seu login é o cpf gerado
        email = f"{login}@cedbrasilia.com.br"
        cadastro = {
            "token": TOKEN_KEY,
            "nome": nome,
            "email": email,           # <-- email fictício obrigatório
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
