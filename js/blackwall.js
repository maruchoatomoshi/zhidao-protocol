function setCasinoBlackwallState(enabled) {
  const content = document.getElementById('casinoPlayContent');
  if (!content) return;

  if (enabled) {
    if (!casinoPlayOriginalMarkup) {
      casinoPlayOriginalMarkup = content.innerHTML;
    }
    if (content.dataset.blackwallActive === '1') return;
    content.innerHTML =
      '<div class="blackwall-screen"><div class="blackwall-title">BlackWall 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
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
      '<div class="blackwall-screen"><div class="blackwall-title">BlackWall 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
    content.dataset.blackwallActive = '1';
    return;
  }

  if (content.dataset.blackwallActive === '1') {
    content.innerHTML = shopStoreOriginalMarkup;
  }
  delete content.dataset.blackwallActive;
}
