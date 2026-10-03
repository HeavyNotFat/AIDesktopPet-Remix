(function () {
  const { dom } = QW;
  const { MOBILE_QUERY } = QW.config;

  let onSearch = () => {};

  function isMobile() {
    return window.matchMedia(MOBILE_QUERY).matches;
  }

  function setCollapsed(collapsed) {
    dom.app.classList.toggle('collapsed', collapsed);
    dom.sidebar.inert = collapsed;
  }

  function collapse() {
    setCollapsed(true);
  }

  function expand() {
    setCollapsed(false);
  }

  function collapseOnMobile() {
    if (isMobile()) collapse();
  }

  function toggleSearch(open) {
    const show = typeof open === 'boolean' ? open : dom.searchBox.hidden;
    dom.searchBox.hidden = !show;
    if (show) {
      dom.searchInput.focus();
    } else {
      dom.searchInput.value = '';
      onSearch();
    }
  }

  function init(options) {
    onSearch = options.onSearch;

    dom.collapseBtn.addEventListener('click', collapse);
    dom.expandBtn.addEventListener('click', expand);
    dom.scrim.addEventListener('click', collapse);
    dom.searchBtn.addEventListener('click', () => toggleSearch());
    dom.searchInput.addEventListener('input', () => onSearch());
    dom.searchInput.addEventListener('keydown', e => {
      if (e.key === 'Escape') toggleSearch(false);
    });

    setCollapsed(isMobile());
    requestAnimationFrame(() => requestAnimationFrame(() => dom.app.classList.remove('no-anim')));
  }

  QW.sidebar = { init, collapseOnMobile };
})();