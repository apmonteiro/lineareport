(function () {
  "use strict";
  const CFG = window.LINEA_CONFIG || { API_BASE: "", EMAIL_FEEDBACK: "" };
  const $ = (s) => document.querySelector(s);
  const ROTULO = { atende: "Atende", nao_atende: "Não atende", nao_verificavel: "Não verificável" };
  let analise = null;

  const esc = (t) => String(t == null ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  fetch(CFG.API_BASE + "/api/saude").then((r) => r.json())
    .then((d) => { $("#versao").textContent = d.versao; }).catch(() => {});

  // ---------------- upload ----------------
  const zona = $("#zona"), input = $("#arquivo");
  input.addEventListener("change", () => input.files[0] && enviar(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => {
    e.preventDefault(); zona.classList.add("arrastando");
  }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => {
    e.preventDefault(); zona.classList.remove("arrastando");
  }));
  zona.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) enviar(f);
  });

  function mostraErro(msg) { const el = $("#erro"); el.textContent = msg; el.hidden = !msg; }

  async function enviar(arquivo) {
    mostraErro("");
    if (!/\.(rtf|pdf)$/i.test(arquivo.name)) {
      mostraErro("Selecione um arquivo .rtf ou .pdf com o relatório estatístico do SisDEA.");
      return;
    }
    $("#carregando").hidden = false;
    const fd = new FormData();
    fd.append("arquivo", arquivo);
    try {
      const resp = await fetch(CFG.API_BASE + "/api/analisar", { method: "POST", body: fd });
      const dados = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(dados.erro || `O servidor respondeu com erro ${resp.status}.`);
      analise = dados;
      renderiza(dados);
    } catch (err) {
      mostraErro(err.message.includes("fetch") ?
        "Não foi possível falar com o servidor do LineaReport. Verifique se ele está em execução." : err.message);
    } finally {
      $("#carregando").hidden = true;
      input.value = "";
    }
  }

  // ---------------- resultado ----------------
  function linhasTabela(linhas) {
    if (!linhas.length) return "";
    const corpo = linhas.map((l) => `<tr><td>${esc(l.item)}</td><td class="${esc(l.status || "")}">${esc(l.valor)}</td><td>${esc(l.criterio)}</td></tr>`).join("");
    return `<div class="tabela-rolagem"><table><thead><tr><th>Item</th><th>Valor</th><th>Critério</th></tr></thead><tbody>${corpo}</tbody></table></div>`;
  }

  function renderiza(r) {
    $("#tela-inicial").hidden = true;
    $("#tela-resultado").hidden = false;
    window.scrollTo(0, 0);
    const m = r.modelo;
    $("#r-arquivo").textContent = r.arquivo;
    $("#r-titulo").textContent = `Modelo ${m.modelo || "sem nome"}`;
    const total = r.conferencias.length, ok = r.resumo.atende;
    let placar = `<strong>${ok} de ${total}</strong> conferências atendidas`;
    if (r.resumo.nao_atende) placar += `, <strong style="color:var(--falha)">${r.resumo.nao_atende} não atendida${r.resumo.nao_atende > 1 ? "s" : ""}</strong>`;
    if (r.resumo.nao_verificavel) placar += `, ${r.resumo.nao_verificavel} não verificável(is)`;
    $("#r-placar").innerHTML = placar + ".";

    const ident = [["Autor", m.autor], ["Data do modelo", m.data], ["Tipologia", m.tipologia],
      ["Dados utilizados", m.n], ["Variáveis independentes", m.k], ["Variável dependente", m.variavel_dependente],
      ["Equação", m.equacao]];
    $("#r-ident").innerHTML = ident.filter(([, v]) => v !== null && v !== "")
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

    $("#r-lista").innerHTML = r.conferencias.map((c) => {
      const sug = c.sugestoes.length ? `<h3>${c.status === "nao_atende" ? "Sugestões para corrigir" : "Sugestões"}</h3><ul class="sugestoes ${c.status}">${c.sugestoes.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : "";
      const obs = c.observacoes.map((o) => `<p class="obs">${esc(o)}</p>`).join("");
      return `<li class="item"><details open>
        <summary>
          <span class="carimbo ${c.status}">${ROTULO[c.status]}</span>
          <span class="item-texto"><span class="item-titulo">${esc(c.titulo)}</span><span class="item-resumo">${esc(c.resumo)}</span></span>
          <span class="seta" aria-hidden="true"></span>
        </summary>
        <div class="detalhe">
          <h3>Como foi feito</h3><p>${esc(c.como_foi_feito)}</p>
          ${linhasTabela(c.linhas)}
          <h3>Resultado</h3><p class="explicacao ${c.status}">${esc(c.explicacao)}</p>
          ${sug}${obs}
        </div></details></li>`;
    }).join("");

    const l = r.leitura;
    $("#r-leitura").innerHTML = `<p>${esc(l.texto_consistencia)}</p>` +
      l.avisos.map((a) => `<p class="aviso-leitura">${esc(a)}</p>`).join("");
    $("#versao").textContent = r.app.versao;
    $("#alternar").textContent = "Recolher todas";
  }

  $("#alternar").addEventListener("click", () => {
    const itens = document.querySelectorAll("#r-lista details");
    const abrir = Array.from(itens).every((d) => !d.open);
    itens.forEach((d) => { d.open = abrir; });
    $("#alternar").textContent = abrir ? "Recolher todas" : "Expandir todas";
  });

  // ---------------- exportação ----------------
  const dlg = $("#dlg-export");
  $("#abrir-export").addEventListener("click", () => {
    if (!analise) return;
    $("#erro-export").hidden = true;
    dlg.showModal();
  });

  $("#confirmar-export").addEventListener("click", async () => {
    const fmt = new FormData($("#form-export")).get("formato");
    const b = $("#confirmar-export"), el = $("#erro-export");
    el.hidden = true; b.disabled = true; b.textContent = "Gerando…";
    try {
      const resp = await fetch(CFG.API_BASE + "/api/exportar/" + fmt, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(analise)
      });
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).erro || "Não foi possível gerar o relatório.");
      const blob = await resp.blob();
      const nome = (analise.arquivo || "modelo").replace(/\.(rtf|pdf)$/i, "").replace(/[^\w-]+/g, "_");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = `Analise_${nome}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      dlg.close();
    } catch (err) { el.textContent = err.message; el.hidden = false; }
    finally { b.disabled = false; b.textContent = "Exportar"; }
  });

  $("#novo").addEventListener("click", () => {
    analise = null;
    $("#tela-resultado").hidden = true; $("#tela-inicial").hidden = false;
    $("#fb-texto").value = ""; $("#fb-status").textContent = "";
    window.scrollTo(0, 0);
  });

  // ---------------- comentários ----------------
  $("#fb-enviar").addEventListener("click", async () => {
    const txt = $("#fb-texto").value.trim();
    if (!txt) { $("#fb-status").textContent = "Escreva o comentário antes de enviar."; return; }
    const corpo = `Arquivo: ${analise ? analise.arquivo : "-"}\nModelo: ${analise ? analise.modelo.modelo : "-"}\nVersão: ${analise ? analise.app.versao : "-"}\n\n${txt}`;
    if (CFG.EMAIL_FEEDBACK) {
      window.location.href = `mailto:${CFG.EMAIL_FEEDBACK}?subject=${encodeURIComponent("LineaReport: comentário")}&body=${encodeURIComponent(corpo)}`;
      $("#fb-status").textContent = "Seu programa de e-mail foi aberto com o comentário.";
    } else {
      try { await navigator.clipboard.writeText(corpo); $("#fb-status").textContent = "Comentário copiado. Cole no e-mail ou mensagem para a equipe responsável."; }
      catch { $("#fb-status").textContent = "Não foi possível copiar automaticamente. Selecione e copie o texto."; }
    }
  });
})();
