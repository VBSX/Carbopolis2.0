const interviewForm = document.getElementById('interview-form');

if (interviewForm) {
  const npcSelect = document.getElementById('interview-npc');
  const messages = document.getElementById('interview-messages');
  const input = document.getElementById('interview-input');
  const sendButton = interviewForm.querySelector('button[type="submit"]');
  const status = document.getElementById('interview-status');
  const suggestions = document.getElementById('interview-suggestions');
  const avatar = document.getElementById('interview-avatar');
  const npcName = document.getElementById('interview-name');
  const npcRole = document.getElementById('interview-role');
  let busy = false;

  const appendMessage = (role, text) => {
    const message = document.createElement('p');
    message.className = `rpg-message ${role}`;
    message.textContent = text;
    messages.append(message);
    messages.scrollTop = messages.scrollHeight;
    return message;
  };

  const parseNpcReply = rawReply => {
    try {
      const data = JSON.parse(rawReply);
      if (!data || typeof data.resposta !== 'string' || !data.resposta.trim()) {
        return {text: rawReply, structured: false, suggestions: []};
      }
      return {
        text: data.resposta.trim(),
        mood: typeof data.humor === 'string' ? data.humor : '',
        structured: true,
        suggestions: Array.isArray(data.sugestoes)
          ? data.sugestoes.filter(item => typeof item === 'string' && item.trim()).slice(0, 4)
          : []
      };
    } catch (_error) {
      return {text: rawReply, structured: false, suggestions: []};
    }
  };

  const appendNpcReply = (rawReply, npcId, animate = false) => {
    const parsed = parseNpcReply(rawReply);
    const response = document.createElement('div');
    response.className = 'rpg-npc-response';
    const reply = document.createElement('p');
    reply.className = 'rpg-message npc';
    response.append(reply);

    if (parsed.mood) {
      const mood = document.createElement('span');
      mood.className = 'text-xs text-slate-400';
      mood.textContent = parsed.mood;
      response.append(mood);
    }

    if (parsed.structured) {
      const saveButton = document.createElement('button');
      saveButton.type = 'button';
      saveButton.className = 'rpg-save-quote';
      saveButton.textContent = '📌 Salvar depoimento';
      saveButton.addEventListener('click', async () => {
        saveButton.disabled = true;
        saveButton.textContent = 'Salvando...';
        try {
          const saveResponse = await fetch('/api/dossier/save_quote', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({npc: npcId, quote_text: parsed.text})
          });
          const result = await saveResponse.json();
          if (!saveResponse.ok) throw new Error(result.error || 'Não foi possível salvar o depoimento.');
          saveButton.textContent = '✔️ Salvo no Dossiê';
        } catch (error) {
          saveButton.disabled = false;
          saveButton.textContent = 'Falha ao salvar — tentar novamente';
          status.textContent = error.message || 'Não foi possível salvar o depoimento.';
        }
      });
      response.append(saveButton);
    }

    messages.append(response);
    const finished = animate ? typewriter(reply, parsed.text) : Promise.resolve();
    if (!animate) {
      reply.textContent = parsed.text;
    }
    messages.scrollTop = messages.scrollHeight;
    return {...parsed, finished};
  };

  const renderSuggestions = options => {
    suggestions.replaceChildren();
    options.forEach(option => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'quick-reply-btn';
      button.textContent = option;
      button.addEventListener('click', () => {
        if (busy) return;
        input.value = option;
        interviewForm.requestSubmit();
      });
      suggestions.append(button);
    });
  };

  const setBusy = value => {
    busy = value;
    input.disabled = value;
    sendButton.disabled = value;
    npcSelect.disabled = value;
  };

  const typewriter = (element, text) => new Promise(resolve => {
    let index = 0;
    const timer = setInterval(() => {
      element.textContent += text.charAt(index);
      index += 1;
      messages.scrollTop = messages.scrollHeight;
      if (index >= text.length) {
        clearInterval(timer);
        resolve();
      }
    }, 15);
  });

  const selectedNpc = () => npcSelect.selectedOptions[0];

  const loadNpcHistory = async () => {
    if (busy) return;
    const npc = selectedNpc();
    const npcId = npc.value;
    npcName.textContent = npc.dataset.name;
    npcRole.textContent = npc.dataset.role;
    avatar.src = `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(npc.dataset.seed)}`;
    avatar.alt = `Avatar pixelado de ${npc.dataset.name}`;
    messages.replaceChildren();
    suggestions.replaceChildren();
    status.textContent = 'Carregando entrevista...';
    input.disabled = true;
    try {
      const url = interviewForm.dataset.historyUrl.replace('__NPC__', encodeURIComponent(npcId));
      const response = await fetch(url, {headers: {'Accept': 'application/json'}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Não foi possível carregar a entrevista.');
      if (data.messages.length) {
        data.messages.forEach(message => {
          if (message.role === 'user') {
            appendMessage('user', message.text);
          } else {
            appendNpcReply(message.text, npcId);
          }
        });
      } else {
        const empty = document.createElement('p');
        empty.className = 'rpg-empty';
        empty.textContent = 'Selecione um personagem e faça sua primeira pergunta.';
        messages.append(empty);
      }
      status.textContent = '';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      input.disabled = false;
      if (!busy) input.focus();
    }
  };

  npcSelect.addEventListener('change', loadNpcHistory);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      interviewForm.requestSubmit();
    }
  });

  interviewForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const message = input.value.trim();
    if (!message) return;

    const npcId = npcSelect.value;
    appendMessage('user', message);
    input.value = '';
    suggestions.replaceChildren();
    status.textContent = 'O personagem está pensando...';
    setBusy(true);
    try {
      const response = await fetch(interviewForm.dataset.endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({npc: npcId, message})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'A IA está indisponível no momento.');
      status.textContent = `${npcName.textContent} está respondendo...`;
      const parsed = appendNpcReply(data.reply, npcId, true);
      renderSuggestions(parsed.structured ? parsed.suggestions : []);
      await parsed.finished;
      status.textContent = '';
    } catch (error) {
      appendMessage('npc', error.message || 'A IA está indisponível no momento.');
      status.textContent = '';
    } finally {
      setBusy(false);
      input.focus();
    }
  });

  loadNpcHistory();
}
