(() => {
  const menuButton = document.querySelector('[data-menu-toggle]');
  const sidebar = document.querySelector('[data-sidebar]');
  if (menuButton && sidebar) {
    menuButton.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', (event) => {
      if (window.innerWidth <= 760 && sidebar.classList.contains('open') &&
          !sidebar.contains(event.target) && !menuButton.contains(event.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm || 'Är du säker?')) event.preventDefault();
    });
  });

  const chatInput = document.querySelector('[data-chat-input]');
  const composer = document.querySelector('[data-composer]');
  if (chatInput) {
    const resize = () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = `${Math.min(chatInput.scrollHeight, 180)}px`;
    };
    chatInput.addEventListener('input', resize);
    chatInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (chatInput.value.trim() || composer?.querySelector('input[type=file]')?.files.length) {
          composer.requestSubmit();
        }
      }
    });
    resize();
  }

  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!chatInput) return;
      chatInput.value = button.dataset.prompt || '';
      chatInput.dispatchEvent(new Event('input'));
      chatInput.focus();
    });
  });

  const latest = document.getElementById('latest');
  if (latest) latest.scrollIntoView({ block: 'end' });
})();
