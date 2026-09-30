/* Melhorias progressivas do front. Tudo funciona sem JS (formulários e links comuns);
   o JS adiciona toasts, confirmações, máscaras, autocompletar e animações. Sem inline (CSP). */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const readJSON = (id) => { const el = document.getElementById(id); try { return el ? JSON.parse(el.textContent) : null; } catch { return null; } };

  /* ---------- barra de progresso de navegação ---------- */
  const bar = $("#nav-progress");
  const startBar = () => { if (bar) { bar.classList.remove("on"); void bar.offsetWidth; bar.classList.add("on"); } };
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (a && !a.target && !a.hasAttribute("download") && a.origin === location.origin && !a.href.includes("#") && !e.metaKey && !e.ctrlKey && !a.dataset.bsToggle) startBar();
  });
  window.addEventListener("pageshow", () => bar && bar.classList.remove("on"));

  /* ---------- toasts ---------- */
  const ICONS = { success: "bi-check-circle-fill", error: "bi-exclamation-octagon-fill", warning: "bi-exclamation-triangle-fill", info: "bi-info-circle-fill" };
  function toast(tipo, msg, ms = 5200) {
    const box = $("#toasts"); if (!box) return;
    const el = document.createElement("div");
    el.className = `toast-app ${tipo}`; el.setAttribute("role", tipo === "error" ? "alert" : "status");
    el.innerHTML = `<i class="bi ${ICONS[tipo] || ICONS.info} t-icon"></i><div class="t-msg"></div><button type="button" class="t-x" aria-label="Fechar"><i class="bi bi-x-lg"></i></button><div class="t-bar" style="--dur:${ms}ms"></div>`;
    $(".t-msg", el).textContent = msg;
    const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 280); };
    $(".t-x", el).addEventListener("click", close);
    box.appendChild(el); setTimeout(close, ms);
  }
  window.toast = toast;
  (readJSON("flash-data") || []).forEach((f, i) => setTimeout(() => toast(f.tipo, f.msg), 120 + i * 140));

  /* ---------- barra lateral (mobile) ---------- */
  const side = $(".app-sidebar"), back = $(".sidebar-backdrop");
  const setSide = (open) => { side?.classList.toggle("open", open); back?.classList.toggle("open", open); };
  $$("[data-sidebar-toggle]").forEach((b) => b.addEventListener("click", () => setSide(!side.classList.contains("open"))));
  back?.addEventListener("click", () => setSide(false));

  /* ---------- confirmação (modal) e prompt de motivo ---------- */
  const confirmEl = $("#confirmModal");
  if (confirmEl && window.bootstrap) {
    const modal = new bootstrap.Modal(confirmEl);
    let pending = null;
    const field = $("#confirmReason", confirmEl), fieldWrap = $("#confirmReasonWrap", confirmEl), okBtn = $("#confirmOk", confirmEl);
    document.addEventListener("submit", (e) => {
      const f = e.target;
      if (!f.matches("form[data-confirm]") || f.dataset.confirmed) return;
      e.preventDefault(); pending = f;
      $("#confirmTitle", confirmEl).textContent = f.dataset.confirmTitle || "Confirmar ação";
      $("#confirmText", confirmEl).textContent = f.dataset.confirm;
      okBtn.textContent = f.dataset.confirmLabel || "Confirmar";
      const danger = f.dataset.confirmDanger !== undefined;
      okBtn.className = "btn " + (danger ? "btn-danger" : "btn-primary");
      $(".modal-icon", confirmEl).className = "modal-icon" + (danger ? " danger" : "");
      $(".modal-icon i", confirmEl).className = "bi " + (f.dataset.confirmIcon || (danger ? "bi-exclamation-triangle" : "bi-question-circle"));
      const askReason = f.dataset.prompt;
      fieldWrap.classList.toggle("d-none", !askReason); field.required = !!askReason; field.value = "";
      if (askReason) { $("#confirmReasonLabel", confirmEl).textContent = f.dataset.promptLabel || "Motivo"; field.placeholder = f.dataset.promptPlaceholder || ""; }
      modal.show();
    }, true);
    okBtn.addEventListener("click", () => {
      if (!pending) return;
      if (field.required && field.value.trim().length < 3) { field.classList.add("is-invalid"); field.focus(); return; }
      field.classList.remove("is-invalid");
      if (pending.dataset.prompt) {
        let h = pending.querySelector(`input[name="${pending.dataset.prompt}"]`);
        if (!h) { h = document.createElement("input"); h.type = "hidden"; h.name = pending.dataset.prompt; pending.appendChild(h); }
        h.value = field.value.trim();
      }
      pending.dataset.confirmed = "1"; modal.hide(); pending.requestSubmit();
    });
    confirmEl.addEventListener("shown.bs.modal", () => { if (!fieldWrap.classList.contains("d-none")) field.focus(); else okBtn.focus(); });
  }

  /* ---------- envio: botão em "carregando" (evita duplo clique) ---------- */
  document.addEventListener("submit", (e) => {
    const f = e.target;
    if (e.defaultPrevented || f.dataset.noLoading !== undefined || f.matches("form[data-confirm]:not([data-confirmed])")) return;
    if (f.method === "get" && f.hasAttribute("data-autosubmit-form")) return;
    const btn = f.querySelector('button[type="submit"]:not([data-no-loading])');
    if (btn && !btn.disabled) {
      startBar();
      setTimeout(() => { btn.disabled = true; btn.dataset.label = btn.innerHTML; btn.innerHTML = '<span class="spinner"></span> Aguarde…'; }, 0);
    }
  });
  window.addEventListener("pageshow", (e) => { if (e.persisted) $$('button[type="submit"][disabled]').forEach((b) => { b.disabled = false; if (b.dataset.label) b.innerHTML = b.dataset.label; }); });

  /* ---------- filtros com envio automático ---------- */
  $$("[data-autosubmit]").forEach((el) => {
    const submit = () => el.form.requestSubmit();
    if (el.matches("input[type=text], input[type=search]")) {
      el.addEventListener("input", debounce(submit, 500));
      // mantém o foco/cursor ao recarregar
      if (new URLSearchParams(location.search).get(el.name) && document.referrer.startsWith(location.origin)) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
    } else el.addEventListener("change", submit);
  });

  /* ---------- máscaras ---------- */
  const masks = {
    cpf: (v) => v.replace(/\D/g, "").slice(0, 11).replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2"),
    cep: (v) => v.replace(/\D/g, "").slice(0, 8).replace(/(\d{5})(\d)/, "$1-$2"),
    tel: (v) => { const d = v.replace(/\D/g, "").slice(0, 11); if (d.length <= 2) return d ? `(${d}` : ""; if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`; if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`; return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`; },
    uf: (v) => v.replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase(),
  };
  $$("[data-mask]").forEach((el) => { const fn = masks[el.dataset.mask]; if (!fn) return; el.value = fn(el.value); el.addEventListener("input", () => { el.value = fn(el.value); }); });

  /* ---------- mostrar/ocultar senha ---------- */
  $$("[data-toggle-password]").forEach((b) => b.addEventListener("click", () => {
    const i = $(b.dataset.togglePassword); if (!i) return;
    const show = i.type === "password"; i.type = show ? "text" : "password";
    $("i", b).className = "bi " + (show ? "bi-eye-slash" : "bi-eye");
  }));

  /* ---------- upload: arrastar e soltar ---------- */
  $$(".dropzone").forEach((dz) => {
    const input = $("input[type=file]", dz), label = $(".dz-label", dz);
    const idle = label.innerHTML;
    const human = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
    const maxMb = Number(dz.dataset.maxMb) || 0;
    const show = () => {
      const g = input.files[0];
      if (g && maxMb && g.size > maxMb * 1048576) {  // o servidor (e a Vercel, acima de 4,5 MB) recusaria
        toast("error", `Arquivo maior que o máximo permitido (${maxMb} MB).`);
        input.value = "";
      }
      const f = input.files[0]; label.innerHTML = f ? `<span class="dz-file"><i class="bi bi-file-earmark-check"></i> ${f.name.replace(/</g, "&lt;")}</span><br><small class="text-muted">${human(f.size)} — clique para trocar</small>` : idle;
    };
    input.addEventListener("change", show);
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("drag")));
    dz.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); } });
  });

  /* ---------- linhas clicáveis ---------- */
  document.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-href]");
    if (tr && !e.target.closest("a, button, form, input, .dropdown")) location.href = tr.dataset.href;
  });

  /* ---------- contador animado ---------- */
  $$("[data-count]").forEach((el) => {
    const alvo = parseInt(el.dataset.count, 10); if (isNaN(alvo) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t0 = performance.now(), dur = 900;
    const tick = (t) => { const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(alvo * e).toLocaleString("pt-BR"); if (p < 1) requestAnimationFrame(tick); };
    el.textContent = "0"; requestAnimationFrame(tick);
  });

  /* ---------- datetime-local: padrão = agora, máximo = agora ---------- */
  const localNow = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
  $$("input[data-now]").forEach((i) => { i.max = localNow(); if (!i.value && i.dataset.now === "default") i.value = localNow(); });

  /* ---------- modais que se preenchem a partir do botão que os abriu ---------- */
  document.addEventListener("show.bs.modal", (e) => {
    const b = e.relatedTarget, m = e.target; if (!b) return;
    const d = b.dataset;
    const form = $("form[data-modal-form]", m);
    if (d.modalAction && form) form.action = d.modalAction;
    if (d.modalFields) Object.entries(JSON.parse(d.modalFields)).forEach(([k, v]) => { const i = m.querySelector(`[name="${k}"]`); if (i) i.value = v ?? ""; });
    if (d.modalTexts) Object.entries(JSON.parse(d.modalTexts)).forEach(([k, v]) => { const t = m.querySelector(`[data-text="${k}"]`); if (t) t.textContent = v; });
    if (d.modalOptions) Object.entries(JSON.parse(d.modalOptions)).forEach(([k, opts]) => {
      const s = m.querySelector(`select[name="${k}"]`); if (!s) return;
      s.innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join(""); s.dispatchEvent(new Event("change"));
    });
    $$(".is-invalid", m).forEach((x) => x.classList.remove("is-invalid"));
  });
  // motivo obrigatório para certos status (lista vinda do servidor)
  $$("select[data-exige-motivo]").forEach((s) => {
    const exigem = JSON.parse(s.dataset.exigeMotivo), alvo = $(s.dataset.motivoTarget);
    const sync = () => { const obrig = exigem.includes(s.value); alvo.required = obrig; const req = $(".req", alvo.closest(".mb-3")?.querySelector("label") || document); if (req) req.classList.toggle("d-none", !obrig); };
    s.addEventListener("change", sync); sync();
  });
  $$(".modal").forEach((m) => m.addEventListener("shown.bs.modal", () => { const f = $("input:not([type=hidden]):not([type=checkbox]), textarea, select", m); if (f && !f.closest(".d-none")) f.focus({ preventScroll: true }); }));

  /* ---------- seletor de mulher (autocompletar) ---------- */
  $$(".picker").forEach((p) => {
    const input = $(".picker-input input", p), hidden = $("input.picker-id", p), results = $(".picker-results", p), chip = $(".picker-chip", p);
    const url = p.dataset.url; let items = [], idx = -1;
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const initials = (n) => n.split(/\s+/).filter(Boolean).map((x, i, a) => (i === 0 || i === a.length - 1) ? x[0] : "").join("").toUpperCase();
    const pick = (it) => {
      hidden.value = it.id; $(".picker-name", chip).textContent = it.nome; p.classList.add("has-value"); results.classList.remove("open");
      const nm = $("input.picker-nome", p); if (nm) nm.value = it.nome;
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const clear = () => { hidden.value = ""; const nm = $("input.picker-nome", p); if (nm) nm.value = ""; p.classList.remove("has-value"); input.value = ""; input.focus(); hidden.dispatchEvent(new Event("change", { bubbles: true })); };
    $(".picker-clear", p)?.addEventListener("click", clear);
    const render = () => {
      results.innerHTML = items.length ? items.map((it, i) => `<button type="button" class="picker-item${i === idx ? " focus" : ""}" data-i="${i}"><span class="avatar avatar-sm">${esc(initials(it.nome))}</span><span><span class="row-title d-block">${esc(it.nome)}</span><span class="row-sub">${esc(it.sub || "")}</span></span></button>`).join("") : `<div class="picker-empty">Nenhuma mulher encontrada</div>`;
      results.classList.add("open");
    };
    const search = debounce(async () => {
      const q = input.value.trim(); if (q.length < 2) { results.classList.remove("open"); return; }
      try { const r = await fetch(`${url}?q=${encodeURIComponent(q)}`, { headers: { Accept: "application/json" } }); if (r.redirected) return location.reload(); items = await r.json(); idx = -1; render(); } catch { /* ignora */ }
    }, 250);
    input.addEventListener("input", search);
    input.addEventListener("keydown", (e) => {
      if (!results.classList.contains("open")) return;
      if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(idx + 1, items.length - 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(idx - 1, 0); render(); }
      else if (e.key === "Enter" && idx >= 0) { e.preventDefault(); pick(items[idx]); }
      else if (e.key === "Escape") results.classList.remove("open");
    });
    results.addEventListener("click", (e) => { const b = e.target.closest(".picker-item"); if (b) pick(items[+b.dataset.i]); });
    document.addEventListener("click", (e) => { if (!p.contains(e.target)) results.classList.remove("open"); });
  });

  /* ---------- botão voltar ---------- */
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => (history.length > 1 ? history.back() : (location.href = "/"))));

  /* ---------- dicas (tooltips do Bootstrap) ---------- */
  if (window.bootstrap) $$("[data-bs-toggle=tooltip]").forEach((t) => new bootstrap.Tooltip(t));
})();
