(() => {
  document.querySelectorAll("[data-modal-open]").forEach((button) =>
    button.addEventListener("click", () =>
      document.getElementById(button.dataset.modalOpen)?.showModal()
    )
  );

  document.querySelectorAll("[data-modal-close]").forEach((button) =>
    button.addEventListener("click", () => button.closest("dialog")?.close())
  );

  document.querySelectorAll("[data-confirm]").forEach((form) =>
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm || "Är du säker?")) {
        event.preventDefault();
      }
    })
  );

  const tabs = document.querySelectorAll("[data-tab]");
  const panels = document.querySelectorAll("[data-tab-panel]");

  tabs.forEach((tab) =>
    tab.addEventListener("click", () => {
      tabs.forEach((x) => x.classList.remove("active"));
      panels.forEach((x) => (x.hidden = true));
      tab.classList.add("active");
      const target = document.querySelector(`[data-tab-panel="${tab.dataset.tab}"]`);
      if (target) target.hidden = false;
    })
  );

  document.querySelectorAll("[data-copy-text]").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyText || "");
        const old = button.textContent;
        button.textContent = "Kopierat";
        setTimeout(() => (button.textContent = old), 1200);
      } catch {
        button.textContent = "Kunde inte kopiera";
      }
    })
  );

  document.querySelectorAll("[data-autogrow]").forEach((textarea) => {
    const resize = () => {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
    };
    textarea.addEventListener("input", resize);
    resize();
  });

  document.querySelectorAll("[data-chat-composer]").forEach((form) => {
    const input = form.querySelector("[data-chat-images]");
    const preview = form.querySelector("[data-attachment-preview]");
    const dropZone = form.querySelector("[data-drop-zone]");
    const textarea = form.querySelector("textarea[name='content']");
    const maxImages = Number(form.dataset.maxImages || 4);
    const maxImageMb = Number(form.dataset.maxImageMb || 8);
    const maxBytes = maxImageMb * 1024 * 1024;
    const allowed = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

    if (!input || !preview || !dropZone) return;

    let selectedFiles = [];

    const syncInput = () => {
      const transfer = new DataTransfer();
      selectedFiles.forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
    };

    const renderPreview = () => {
      preview.innerHTML = "";
      preview.hidden = selectedFiles.length === 0;

      selectedFiles.forEach((file, index) => {
        const item = document.createElement("div");
        item.className = "attachment-chip";

        const img = document.createElement("img");
        img.alt = file.name;
        const objectUrl = URL.createObjectURL(file);
        img.src = objectUrl;
        img.onload = () => URL.revokeObjectURL(objectUrl);

        const info = document.createElement("span");
        info.textContent = file.name;

        const remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("aria-label", `Ta bort ${file.name}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => {
          selectedFiles.splice(index, 1);
          syncInput();
          renderPreview();
        });

        item.append(img, info, remove);
        preview.appendChild(item);
      });
    };

    const addFiles = (files) => {
      const incoming = Array.from(files || []).filter((file) =>
        file.type.startsWith("image/")
      );

      for (const file of incoming) {
        if (!allowed.has(file.type)) {
          window.alert(`${file.name}: endast PNG, JPG/JPEG, WEBP och GIF stöds.`);
          continue;
        }

        if (file.size > maxBytes) {
          window.alert(`${file.name}: bilden är större än ${maxImageMb} MB.`);
          continue;
        }

        if (selectedFiles.length >= maxImages) {
          window.alert(`Du kan bifoga högst ${maxImages} bilder per meddelande.`);
          break;
        }

        const duplicate = selectedFiles.some(
          (existing) =>
            existing.name === file.name &&
            existing.size === file.size &&
            existing.lastModified === file.lastModified
        );

        if (!duplicate) selectedFiles.push(file);
      }

      syncInput();
      renderPreview();
    };

    input.addEventListener("change", () => {
      const chosen = Array.from(input.files || []);
      selectedFiles = [];
      addFiles(chosen);
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropZone.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropZone.classList.remove("dragover");
      });
    });

    dropZone.addEventListener("drop", (event) => {
      addFiles(event.dataTransfer?.files);
      textarea?.focus();
    });

    textarea?.addEventListener("paste", (event) => {
      const files = Array.from(event.clipboardData?.files || []);
      const images = files.filter((file) => file.type.startsWith("image/"));
      if (images.length) {
        event.preventDefault();
        addFiles(images);
      }
    });

    form.addEventListener("submit", (event) => {
      const hasText = Boolean(textarea?.value.trim());
      if (!hasText && selectedFiles.length === 0) {
        event.preventDefault();
        textarea?.focus();
        return;
      }

      const submit = form.querySelector("button[type='submit']");
      if (submit) {
        submit.disabled = true;
        submit.textContent = "Skickar…";
      }
    });
  });
})();
