(function () {
  const { MAX_ATTACHMENTS, MAX_ATTACHMENT_BYTES } = QW.config;

  const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'];
  const TEXT_EXT = ['txt', 'md', 'markdown', 'rst', 'log', 'csv', 'tsv', 'json', 'jsonl', 'yaml', 'yml',
    'toml', 'ini', 'cfg', 'conf', 'env', 'py', 'js', 'ts', 'tsx', 'jsx', 'css', 'html', 'htm', 'xml',
    'sql', 'sh', 'bat', 'ps1', 'java', 'c', 'h', 'cpp', 'go', 'rs'];

  let pending = [];
  let onChange = () => {};
  let onNotice = () => {};

  function extOf(name) {
    const parts = String(name || '').toLowerCase().split('.');
    return parts.length > 1 ? parts.pop() : '';
  }

  function isImage(file) {
    if ((file.type || '').startsWith('image/')) return true;
    return IMAGE_EXT.includes(extOf(file.name));
  }

  function humanSize(size) {
    if (size < 1024) return size + ' B';
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
    return (size / 1024 / 1024).toFixed(1) + ' MB';
  }

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || '');
        const comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(new Error('读取失败'));
      reader.readAsDataURL(file);
    });
  }

  function readDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('读取失败'));
      reader.readAsDataURL(file);
    });
  }

  function thumbnail(dataUrl) {
    // 历史记录里只留小图：localStorage 装不下原图
    return new Promise(resolve => {
      const img = new Image();
      img.onload = () => {
        const size = 96;
        const scale = Math.min(size / img.width, size / img.height, 1);
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        try {
          resolve(canvas.toDataURL('image/jpeg', 0.7));
        } catch (e) {
          resolve('');
        }
      };
      img.onerror = () => resolve('');
      img.src = dataUrl;
    });
  }

  async function toEntry(file) {
    const kind = isImage(file) ? 'image' : 'file';
    const entry = {
      kind,
      name: file.name || (kind === 'image' ? '剪切板图片.png' : '未命名'),
      mime: file.type || '',
      size: file.size,
      base64: await readBase64(file)
    };

    if (kind === 'image') {
      const dataUrl = file.type || file.name ? await readDataUrl(file) : '';
      entry.preview = dataUrl;
      entry.thumb = await thumbnail(dataUrl);
    } else if (TEXT_EXT.includes(extOf(entry.name))) {
      try {
        entry.preview = await file.text();
      } catch (e) {}
    }
    return entry;
  }

  // 历史记录里没必要存整张图，只留缩略图和小段文本预览
  function toStored(entry) {
    const stored = { kind: entry.kind, name: entry.name, mime: entry.mime, size: entry.size };
    if (entry.kind === 'image') {
      stored.thumb = entry.thumb || '';
    } else if (entry.preview) {
      stored.preview = entry.preview.slice(0, 400);
    }
    return stored;
  }

  function toPayload(entry) {
    return { name: entry.name, mime: entry.mime, data: entry.base64 };
  }

  async function addFiles(files) {
    const list = Array.from(files || []);
    let added = 0;
    for (const file of list) {
      if (pending.length >= MAX_ATTACHMENTS) {
        onNotice('最多一次带 ' + MAX_ATTACHMENTS + ' 个附件', 'warning');
        break;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        onNotice(file.name + ' 太大了（上限 ' + humanSize(MAX_ATTACHMENT_BYTES) + '）', 'warning');
        continue;
      }
      try {
        pending.push(await toEntry(file));
        added += 1;
      } catch (e) {
        onNotice('读不了 ' + file.name, 'error');
      }
    }
    if (added) onChange();
    return added;
  }

  function collectFiles(data) {
    // 浏览器之间不一致：Chrome 给 files，Firefox 有时只在 items 里给
    const files = [];
    for (const file of Array.from((data && data.files) || [])) files.push(file);
    for (const item of Array.from((data && data.items) || [])) {
      if (item.kind !== 'file' || typeof item.getAsFile !== 'function') continue;
      const file = item.getAsFile();
      if (file) files.push(file);
    }

    const seen = new Set();
    return files.filter(file => {
      const key = (file.name || '') + ':' + (file.size || 0) + ':' + (file.type || '');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function isImageFile(file) {
    if ((file.type || '').startsWith('image/')) return true;
    return IMAGE_EXT.includes(extOf(file.name));
  }

  function handlePaste(event) {
    const data = event.clipboardData;
    if (!data) return false;

    const files = collectFiles(data).filter(isImageFile);
    if (!files.length) return false;
    event.preventDefault();
    addFiles(files);
    return true;
  }

  function handleDrop(event) {
    const data = event.dataTransfer;
    if (!data) return false;

    const files = collectFiles(data);
    if (!files.length) return false;
    event.preventDefault();
    addFiles(files);
    return true;
  }

  function remove(index) {
    pending.splice(index, 1);
    onChange();
  }

  function take() {
    const items = pending.slice();
    pending = [];
    onChange();
    return items;
  }

  function clear() {
    pending = [];
    onChange();
  }

  function init(options) {
    onChange = options.onChange || onChange;
    onNotice = options.onNotice || onNotice;
  }

  QW.attach = {
    init, addFiles, handlePaste, handleDrop, remove, take, clear, toStored, toPayload,
    humanSize, isImage, human: humanSize, collectFiles,
    get pending() { return pending; }
  };
})();
