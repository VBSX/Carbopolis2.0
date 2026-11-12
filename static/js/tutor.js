const tutor = document.querySelector('.ai-tutor');

if (tutor) {
  const launcher = tutor.querySelector('.ai-tutor-launcher');
  const panel = tutor.querySelector('.ai-tutor-panel');
  const closeButton = tutor.querySelector('.ai-chat-close');
  const expandButton = tutor.querySelector('.ai-chat-expand');
  const messages = tutor.querySelector('.ai-tutor-messages');
  const form = tutor.querySelector('.ai-tutor-form');
  const input = form.querySelector('textarea');
  const submitButton = form.querySelector('button');
  const storageKey = `carbopolis-tutor-history-v1-${tutor.dataset.role}`;
  let busy = false;
  let history = [];

  const escapeHtml = text => {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  };

  const renderMarkdown = text => {
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    return html;
  };

  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
    if (Array.isArray(saved)) {
      history = saved.filter(item =>
        item && (item.role === 'user' || item.role === 'model') &&
        typeof item.text === 'string'
      ).slice(-12);
    }
  } catch (error) {
    console.warn('O histórico local do tutor não pôde ser carregado.', error);
  }

  // Renders **bold** and markdown bullets/headings without innerHTML, so model output never injects HTML.
  const setText = (element, text) => {
    element.replaceChildren();
    const clean = text.replace(/^[ \t]*[*-][ \t]+/gm, '• ').replace(/^#{1,6}[ \t]+/gm, '');
    clean.split(/\*\*([\s\S]+?)\*\*/).forEach((part, index) => {
      if (!part) return;
      if (index % 2) {
        const strong = document.createElement('strong');
        strong.textContent = part;
        element.append(strong);
      } else {
        element.append(part);
      }
    });
  };

  const appendMessage = (role, text, extraClass = '') => {
    const message = document.createElement('p');
    message.className = `ai-chat-message ${role} ${extraClass}`.trim();
    if (role === 'assistant') {
      message.innerHTML = renderMarkdown(text);
    } else {
      message.textContent = text;
    }
    messages.append(message);
    messages.scrollTop = messages.scrollHeight;
    return message;
  };

  const saveHistory = () => {
    history = history.slice(-12);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(history));
    } catch (error) {
      console.warn('O histórico do tutor não pôde ser salvo nesta sessão.', error);
    }
  };

  history.forEach(item => appendMessage(item.role === 'user' ? 'user' : 'assistant', item.text));

  const setOpen = open => {
    panel.hidden = !open;
    tutor.classList.toggle('is-open', open);
    launcher.setAttribute('aria-expanded', String(open));
    if (open) input.focus();
  };
  launcher.addEventListener('click', () => setOpen(panel.hidden));
  closeButton.addEventListener('click', () => setOpen(false));
  expandButton.addEventListener('click', () => {
    const expanded = panel.classList.toggle('expanded');
    expandButton.setAttribute('aria-pressed', String(expanded));
    expandButton.setAttribute('aria-label', expanded ? 'Reduzir tutor' : 'Ampliar tutor');
    messages.scrollTop = messages.scrollHeight;
  });

  if (window.visualViewport) {
    let lastHeight = window.visualViewport.height;
    window.visualViewport.addEventListener('resize', () => {
      const height = window.visualViewport.height;
      if (height > lastHeight + 50) {
        // Teclado fechou: forçar reflow do tutor para corrigir position:fixed no mobile
        tutor.style.display = 'none';
        void tutor.offsetHeight;
        tutor.style.display = '';
        if (!panel.hidden) input.focus();
      }
      lastHeight = height;
    });
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const text = input.value.trim();
    if (!text) return;

    const context = history.slice(-12);
    appendMessage('user', text);
    input.value = '';
    busy = true;
    input.disabled = true;
    submitButton.disabled = true;
    const pending = appendMessage('assistant', 'Pensando...');
    try {
      const response = await fetch(tutor.dataset.endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({message: text, history: context})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'A IA está indisponível no momento.');
      pending.innerHTML = renderMarkdown(data.reply);
      history.push({role: 'user', text}, {role: 'model', text: data.reply});
      saveHistory();
    } catch (error) {
      pending.classList.add('error');
      pending.textContent = error.message || 'A IA está indisponível no momento.';
    } finally {
      busy = false;
      input.disabled = false;
      submitButton.disabled = false;
      input.focus();
      messages.scrollTop = messages.scrollHeight;
    }
  });
}
