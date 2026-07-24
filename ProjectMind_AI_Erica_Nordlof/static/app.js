(() => {
  document.querySelectorAll("[data-modal-open]").forEach((button) => button.addEventListener("click", () => document.getElementById(button.dataset.modalOpen)?.showModal()));
  document.querySelectorAll("[data-modal-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog")?.close()));
  document.querySelectorAll("[data-confirm]").forEach((form) => form.addEventListener("submit", (event) => { if (!window.confirm(form.dataset.confirm || "Är du säker?")) event.preventDefault(); }));
  const tabs = document.querySelectorAll("[data-tab]"); const panels = document.querySelectorAll("[data-tab-panel]");
  tabs.forEach((tab) => tab.addEventListener("click", () => { tabs.forEach((x) => x.classList.remove("active")); panels.forEach((x) => x.hidden = true); tab.classList.add("active"); const target = document.querySelector(`[data-tab-panel="${tab.dataset.tab}"]`); if (target) target.hidden = false; }));
  document.querySelectorAll("[data-copy-text]").forEach((button) => button.addEventListener("click", async () => { try { await navigator.clipboard.writeText(button.dataset.copyText || ""); const old = button.textContent; button.textContent = "Kopierat"; setTimeout(() => button.textContent = old, 1200); } catch { button.textContent = "Kunde inte kopiera"; } }));
  document.querySelectorAll("[data-autogrow]").forEach((textarea) => { const resize = () => { textarea.style.height = "auto"; textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`; }; textarea.addEventListener("input", resize); resize(); });
})();
