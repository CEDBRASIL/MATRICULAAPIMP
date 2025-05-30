// checkout.js

const DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1377845855574556753/Miv-HQ4GBe1SfoXkHJkZ3piQNW_WYTHA09rr9tMqgUnizt47sZG8QdN-pZJMtYxFIHiS";

async function fetchWithTimeout(resource, options = {}, timeout = 10000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  const response = await fetch(resource, {
    ...options,
    signal: controller.signal
  });
  clearTimeout(id);
  return response;
}

async function enviarCheckout() {
  const nome = document.getElementById("nome").value.trim();
  const email = document.getElementById("email").value.trim();
  const whatsappRaw = document.getElementById("whatsapp").value.trim();
  const whatsapp = whatsappRaw.replace(/\D/g, '');

  const cursosSelecionados = Array.from(document.querySelectorAll("input[name='curso']:checked"))
    .map(el => el.value); // agora envia strings

  if (!nome || !email || !whatsapp || cursosSelecionados.length === 0) {
    mostrarMsg("Preencha todos os campos e selecione ao menos um curso.", false);
    return;
  }

  const payload = { nome, email, whatsapp, cursos: cursosSelecionados };

  console.log("Payload enviado:", payload);

  try {
    const resposta = await fetchWithTimeout("https://matriculaapimp.onrender.com/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const resultado = await resposta.json();

    console.log("Resposta da API:", resultado);

    if (resposta.ok) {
      mostrarMsg(`✅ Matrícula iniciada! Redirecionando para pagamento...`, true);

      await enviarLogDiscord(`✅ Matrícula iniciada para: **${nome}** | Email: **${email}**`);

      if (resultado.mp_link) {
        setTimeout(() => {
          window.location.href = resultado.mp_link;
        }, 2000);
      }
    } else {
      const erroMsg = resultado.detail || resultado.message || JSON.stringify(resultado);
      mostrarMsg(`❌ Erro: ${erroMsg}`, false);
      await enviarLogDiscord(`❌ Falha na matrícula para: **${nome}** | Erro: ${erroMsg}`);
    }
  } catch (erro) {
    console.error("Erro na requisição:", erro);
    mostrarMsg("❌ Erro ao conectar com o servidor.", false);
    await enviarLogDiscord(`❌ Erro ao conectar com o servidor para: **${nome}** | Erro: ${erro.message}`);
  }
}

function mostrarMsg(texto, sucesso) {
  const msg = document.getElementById("msg");
  msg.innerHTML = texto;
  msg.className = sucesso ? "text-green-600" : "text-red-600";
}

async function enviarLogDiscord(mensagem) {
  try {
    await fetch(DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: mensagem })
    });
  } catch (err) {
    console.error("Falha ao enviar log para Discord:", err);
  }
}