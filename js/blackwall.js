function setCasinoBlackwallState(enabled) {
  const content = document.getElementById('casinoPlayContent');
  const genshinContent = document.getElementById('casinoGenshinContent');
  const blackwallMarkup =
    '<div class="blackwall-screen"><div class="blackwall-title">ВЕЛИКИЙ КРАСНЫЙ ФАЙРВОЛ</div><div class="blackwall-subtitle">伟大红色防火墙 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';

  if (genshinContent) {
    if (enabled) {
      if (!casinoGenshinOriginalMarkup) {
        casinoGenshinOriginalMarkup = genshinContent.innerHTML;
      }
      if (genshinContent.dataset.blackwallActive !== '1') {
        genshinContent.innerHTML = blackwallMarkup;
        genshinContent.dataset.blackwallActive = '1';
      }
    } else {
      if (genshinContent.dataset.blackwallActive === '1' && casinoGenshinOriginalMarkup) {
        genshinContent.innerHTML = casinoGenshinOriginalMarkup;
      }
      delete genshinContent.dataset.blackwallActive;
    }
  }

  if (!content) return;

  if (enabled) {
    if (!casinoPlayOriginalMarkup) {
      casinoPlayOriginalMarkup = content.innerHTML;
    }
    if (content.dataset.blackwallActive === '1') return;
    content.innerHTML = blackwallMarkup;
    content.dataset.blackwallActive = '1';
    return;
  }

  if (content.dataset.blackwallActive === '1' && casinoPlayOriginalMarkup) {
    content.innerHTML = casinoPlayOriginalMarkup;
  }
  delete content.dataset.blackwallActive;
}

function setShopBlackwallState(enabled) {
  const content = document.getElementById('shopStoreContent');
  if (!content) return;

  if (enabled) {
    if (!shopStoreOriginalMarkup) {
      shopStoreOriginalMarkup = content.innerHTML;
    }
    if (content.dataset.blackwallActive === '1') return;
    content.innerHTML =
      '<div class="blackwall-screen"><div class="blackwall-title">ВЕЛИКИЙ КРАСНЫЙ ФАЙРВОЛ</div><div class="blackwall-subtitle">伟大红色防火墙 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
    content.dataset.blackwallActive = '1';
    return;
  }

  if (content.dataset.blackwallActive === '1') {
    content.innerHTML = shopStoreOriginalMarkup;
  }
  delete content.dataset.blackwallActive;
}
