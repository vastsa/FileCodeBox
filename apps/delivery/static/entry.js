// 上游主题仍单独构建；使用小型入口桥接其 hash 路由，后台页面可直接进入寄件管理。
(() => {
  const nav = document.createElement('nav');
  nav.className = 'filerelay-entry'; nav.setAttribute('aria-label', '寄件功能');
  const send = document.createElement('a'); send.href = '/delivery'; send.textContent = '凭码寄件'; nav.append(send);
  const manage = document.createElement('a'); manage.href = '/delivery/admin'; manage.textContent = '寄件管理'; nav.append(manage);
  const update = () => { manage.hidden = !window.location.hash.startsWith('#/admin'); };
  window.addEventListener('hashchange', update); update(); document.body.append(nav);
})();
