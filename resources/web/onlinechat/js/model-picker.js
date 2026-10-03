(function () {
  const { dom } = QW;
  const { state, saveModel } = QW.store;

  let status = 'loading';
  let onRetry = () => {};
  let onSelect = () => {};

  function close() {
    dom.modelMenu.hidden = true;
    dom.modelBtn.setAttribute('aria-expanded', 'false');
  }

  function open() {
    dom.modelMenu.hidden = false;
    dom.modelBtn.setAttribute('aria-expanded', 'true');
  }

  function showLoading() {
    status = 'loading';
    dom.modelBtn.classList.remove('error');
    dom.modelBtn.title = '';
    dom.modelLabel.textContent = '加载模型…';
    dom.modelMenu.textContent = '';
    close();
  }

  function showError(message) {
    status = 'error';
    dom.modelBtn.classList.add('error');
    dom.modelBtn.title = message || '';
    dom.modelLabel.textContent = '模型加载失败，点击重试';
    dom.modelMenu.textContent = '';
    close();
  }

  function render() {
    status = 'ready';
    dom.modelBtn.classList.remove('error');
    dom.modelBtn.title = '';

    const current = state.models.find(m => m.value === state.model) || state.models[0];
    dom.modelLabel.textContent = current.label;
    dom.modelMenu.textContent = '';

    for (const m of state.models) {
      const opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'model-opt' + (m.value === state.model ? ' on' : '');
      opt.setAttribute('role', 'option');
      opt.setAttribute('aria-selected', String(m.value === state.model));

      const name = document.createElement('span');
      name.textContent = m.label;
      opt.appendChild(name);

      if (m.value === state.model) {
        const tick = document.createElement('span');
        tick.textContent = '✓';
        opt.appendChild(tick);
      }

      opt.addEventListener('click', () => {
        state.model = m.value;
        saveModel();
        render();
        close();
        onSelect();
      });

      dom.modelMenu.appendChild(opt);
    }
  }

  function init(options) {
    onRetry = options.onRetry;
    onSelect = options.onSelect;

    dom.modelBtn.addEventListener('click', e => {
      e.stopPropagation();
      if (status === 'error') onRetry();
      else if (status === 'ready') {
        if (dom.modelMenu.hidden) open();
        else close();
      }
    });

    document.addEventListener('click', e => {
      if (!dom.modelBtn.contains(e.target) && !dom.modelMenu.contains(e.target)) close();
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') close();
    });
  }

  QW.modelPicker = { init, showLoading, showError, render };
})();