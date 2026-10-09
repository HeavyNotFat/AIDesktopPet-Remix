(function () {
  const { dom } = QW;
  const { state, currentChat } = QW.store;

  const ICON_SEND = '<svg class="i" viewBox="0 0 24 24"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/></svg>';
  const ICON_STOP = '<svg class="i" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/></svg>';
  const ICON_TRASH = '<svg class="i" viewBox="0 0 24 24"><path d="M5 7h14M10 11v6M14 11v6M7 7l1 12h8l1-12M9.5 7V4.5h5V7"/></svg>';
  const DOTS = '<span class="dots"><i></i><i></i><i></i></span>';

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatText(text) {
    return text.split(/```/).map((part, i) => {
      if (i % 2 === 1) {
        const nl = part.indexOf('\n');
        const body = nl >= 0 ? part.slice(nl + 1) : part;
        return '<pre><code>' + esc(body.replace(/\n$/, '')) + '</code></pre>';
      }
      const t = part.trim();
      if (!t) return '';
      return '<div class="para">' +
        esc(t)
          .replace(/`([^`\n]+)`/g, '<code>$1</code>')
          .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>') +
        '</div>';
    }).join('');
  }

  function history(onOpen, onDelete) {
    const q = dom.searchInput.value.trim().toLowerCase();
    const list = state.chats
      .filter(c => !q || c.title.toLowerCase().includes(q) || c.messages.some(m => m.content.toLowerCase().includes(q)))
      .sort((a, b) => b.updated - a.updated);

    dom.history.textContent = '';

    if (!list.length) {
      const empty = document.createElement('div');
      empty.className = 'history-empty';
      empty.textContent = q ? '没有找到相关对话' : '暂无对话记录';
      dom.history.appendChild(empty);
      return;
    }

    for (const chat of list) {
      const item = document.createElement('div');
      item.className = 'history-item' + (chat.id === state.currentId ? ' active' : '');
      item.title = chat.title;

      const title = document.createElement('span');
      title.className = 'title';
      title.textContent = chat.title;

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'del';
      del.title = '删除对话';
      del.setAttribute('aria-label', '删除对话');
      del.innerHTML = ICON_TRASH;
      del.addEventListener('click', e => {
        e.stopPropagation();
        onDelete(chat.id);
      });

      item.addEventListener('click', () => onOpen(chat.id));
      item.append(title, del);
      dom.history.appendChild(item);
    }
  }

  function attachmentNode(item, live) {
    if (item.kind === 'image') {
      const figure = document.createElement('figure');
      figure.className = 'att-img';
      const img = document.createElement('img');
      // 有原图就用原图，否则用缩略图
      img.src = (live && item.preview) || item.thumb || item.preview || '';
      img.alt = item.name || '图片';
      img.loading = 'lazy';
      figure.appendChild(img);
      const caption = document.createElement('figcaption');
      caption.textContent = (item.name || '图片') + ' · ' + QW.attach.human(item.size || 0);
      figure.appendChild(caption);
      return figure;
    }

    const chip = document.createElement('div');
    chip.className = 'att-file';
    chip.textContent = '📄 ' + (item.name || '文件') + ' · ' + QW.attach.human(item.size || 0);
    chip.title = item.name || '';
    return chip;
  }

  function messages() {
    const chat = currentChat();
    const empty = !chat || chat.messages.length === 0;
    dom.stage.dataset.empty = String(empty);
    dom.inner.textContent = '';
    if (empty) return;

    for (const m of chat.messages) {
      const div = document.createElement('div');
      div.className = 'msg ' + m.role + (m.error ? ' error' : '') + (m.cached ? ' cached' : '');
      if (m.role === 'user') div.textContent = m.content;
      else div.innerHTML = formatText(m.content);

      if (m.attachments && m.attachments.length) {
        const box = document.createElement('div');
        box.className = 'att-list';
        for (const item of m.attachments) box.appendChild(attachmentNode(item, !!item.preview));
        div.appendChild(box);
      }

      dom.inner.appendChild(div);
    }

    if (state.pending && state.pending.chatId === chat.id) {
      const wait = document.createElement('div');
      wait.className = 'msg assistant streaming';
      wait.innerHTML = state.pending.text ? formatText(state.pending.text) : DOTS;
      state.pending.node = wait;
      dom.inner.appendChild(wait);
    }

    dom.messages.scrollTop = dom.messages.scrollHeight;
  }

  function streamChunk(text) {
    const pending = state.pending;
    if (!pending) return;

    pending.text = (pending.text || '') + text;
    if (!pending.node) {
      messages();
      return;
    }
    pending.node.innerHTML = formatText(pending.text);
    dom.messages.scrollTop = dom.messages.scrollHeight;
  }

  function sendButton() {
    if (state.pending) {
      dom.sendBtn.innerHTML = ICON_STOP;
      dom.sendBtn.disabled = false;
      dom.sendBtn.setAttribute('aria-label', '停止');
    } else {
      const hasContent = !!dom.input.value.trim() || (QW.attach.pending.length > 0);
      dom.sendBtn.innerHTML = ICON_SEND;
      dom.sendBtn.disabled = !hasContent || !state.model;
      dom.sendBtn.setAttribute('aria-label', '发送');
    }
  }

  function modelSeesImages() {
    // 后端没明确标记 vision 时不做拦截
    const current = state.models.find(m => m.value === state.model);
    return !current || current.vision !== false;
  }

  function attachments() {
    const pending = QW.attach.pending;
    dom.attachBar.textContent = '';
    dom.attachBar.hidden = pending.length === 0;

    const hasImage = pending.some(item => item.kind === 'image');
    if (hasImage && !modelSeesImages()) {
      const warn = document.createElement('div');
      warn.className = 'att-warn';
      warn.textContent = '当前模型看不了图片（纯文本模型），换成带 vision 的模型再发。';
      dom.attachBar.appendChild(warn);
    }

    pending.forEach((item, index) => {
      const chip = document.createElement('div');
      chip.className = 'att-chip';
      chip.title = item.name;

      if (item.kind === 'image' && item.thumb) {
        const img = document.createElement('img');
        img.src = item.thumb;
        img.alt = item.name;
        chip.appendChild(img);
      } else {
        const mark = document.createElement('span');
        mark.className = 'mark';
        mark.textContent = '📄';
        chip.appendChild(mark);
      }

      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = item.name + ' · ' + QW.attach.human(item.size);
      chip.appendChild(name);

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'del';
      del.textContent = '×';
      del.title = '移除';
      del.setAttribute('aria-label', '移除附件');
      del.addEventListener('click', () => QW.attach.remove(index));
      chip.appendChild(del);

      dom.attachBar.appendChild(chip);
    });
  }

  function greeting(name) {
    dom.helloName.textContent = name;
    dom.hello.classList.add('ready');
  }

  function autosize() {
    dom.input.style.height = 'auto';
    dom.input.style.height = Math.min(dom.input.scrollHeight, 200) + 'px';
  }

  QW.render = { history, messages, sendButton, greeting, autosize, streamChunk, attachments };
})();