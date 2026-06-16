// ===== Тяньхао — фразы дня =====

const TIANHAO_IMGS = [
  'tianhao_explaining.png',
  'tianhao_explaining2.png',
  'tianhao_idea.png',
  'tianhao_smiling_explaining.png',
  'tianhao_thinking.png',
  'tianhao_thinking2.png',
].map(f => 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/' + f);
const TIANHAO_TRIP_START = '2026-07-05'; // день 1
const TIANHAO_SEEN_KEY = 'tianhaoPhrasesSeen';

const TIANHAO_PHRASES = [
  // День 1
  { day: 1, period: 1, chinese: '不好意思，打扰一下。', pinyin: 'Bù hǎoyìsi, dǎrǎo yíxià.', russian: 'Извините, можно вас побеспокоить?', note: 'Эта фраза открывает почти любой вежливый вопрос.' },
  { day: 1, period: 2, chinese: '请问，洗手间在哪儿？', pinyin: 'Qǐngwèn, xǐshǒujiān zài nǎr?', russian: 'Подскажите, где туалет?', note: 'Первая фраза настоящего выживания в Китае.' },
  // День 2
  { day: 2, period: 1, chinese: '请再说一遍。', pinyin: 'Qǐng zài shuō yí biàn.', russian: 'Пожалуйста, повторите ещё раз.', note: 'Не стесняйся просить повторить. Это нормально.' },
  { day: 2, period: 2, chinese: '我听不懂。', pinyin: 'Wǒ tīng bù dǒng.', russian: 'Я не понимаю на слух.', note: 'Лучше честно сказать, чем делать вид, что всё понял.' },
  // День 3
  { day: 3, period: 1, chinese: '这里怎么走？', pinyin: 'Zhèlǐ zěnme zǒu?', russian: 'Как сюда пройти?', note: 'Покажи место на карте и скажи эту фразу.' },
  { day: 3, period: 2, chinese: '离这里远吗？', pinyin: 'Lí zhèlǐ yuǎn ma?', russian: 'Это далеко отсюда?', note: 'Очень полезно, когда не понимаешь, идти пешком или ехать.' },
  // День 4
  { day: 4, period: 1, chinese: '我们在这里集合。', pinyin: 'Wǒmen zài zhèlǐ jíhé.', russian: 'Мы собираемся здесь.', note: 'Фраза для точки сбора и групповых перемещений.' },
  { day: 4, period: 2, chinese: '请不要走散。', pinyin: 'Qǐng bú yào zǒu sàn.', russian: 'Пожалуйста, не расходитесь / не теряйтесь.', note: 'Это фраза сопровождающего, но знать её полезно всем.' },
  // День 5
  { day: 5, period: 1, chinese: '我要这个。', pinyin: 'Wǒ yào zhège.', russian: 'Я хочу вот это.', note: 'Покажи пальцем и скажи уверенно.' },
  { day: 5, period: 2, chinese: '不要辣。', pinyin: 'Bú yào là.', russian: 'Не острое, пожалуйста.', note: 'Важная фраза, если не хочешь проверить силу китайского перца.' },
  // День 6
  { day: 6, period: 1, chinese: '请给我一瓶水。', pinyin: 'Qǐng gěi wǒ yì píng shuǐ.', russian: 'Дайте мне, пожалуйста, бутылку воды.', note: 'В Пекине летом эта фраза пригодится постоянно.' },
  { day: 6, period: 2, chinese: '有筷子或者勺子吗？', pinyin: 'Yǒu kuàizi huòzhě sháozi ma?', russian: 'У вас есть палочки или ложка?', note: 'Если приборы не дали сразу — просто спроси.' },
  // День 7
  { day: 7, period: 1, chinese: '可以打包吗？', pinyin: 'Kěyǐ dǎbāo ma?', russian: 'Можно взять с собой?', note: 'Если не доел, еду можно попросить упаковать.' },
  { day: 7, period: 2, chinese: '买单，谢谢。', pinyin: 'Mǎidān, xièxie.', russian: 'Счёт, пожалуйста.', note: 'Коротко, вежливо и понятно.' },
  // День 8
  { day: 8, period: 1, chinese: '这个多少钱？', pinyin: 'Zhège duōshao qián?', russian: 'Сколько это стоит?', note: 'Базовая фраза для магазина, рынка и сувениров.' },
  { day: 8, period: 2, chinese: '可以便宜一点吗？', pinyin: 'Kěyǐ piányi yìdiǎn ma?', russian: 'Можно немного дешевле?', note: 'Иногда работает. Главное — улыбаться.' },
  // День 9
  { day: 9, period: 1, chinese: '可以用支付宝吗？', pinyin: 'Kěyǐ yòng Zhīfùbǎo ma?', russian: 'Можно оплатить Alipay?', note: 'В Китае это один из главных способов оплаты.' },
  { day: 9, period: 2, chinese: '可以付现金吗？', pinyin: 'Kěyǐ fù xiànjīn ma?', russian: 'Можно оплатить наличными?', note: 'Наличные принимают не всегда, но спросить стоит.' },
  // День 10
  { day: 10, period: 1, chinese: '我想去……', pinyin: 'Wǒ xiǎng qù...', russian: 'Я хочу поехать / пойти в…', note: 'После этой фразы просто назови место или покажи его на карте.' },
  { day: 10, period: 2, chinese: '请问，地铁站在哪儿？', pinyin: 'Qǐngwèn, dìtiězhàn zài nǎr?', russian: 'Подскажите, где станция метро?', note: 'Метро — твой лучший друг в Пекине.' },
  // День 11
  { day: 11, period: 1, chinese: '到这里多少钱？', pinyin: 'Dào zhèlǐ duōshao qián?', russian: 'Сколько стоит доехать сюда?', note: 'Покажи адрес или точку на карте.' },
  { day: 11, period: 2, chinese: '请在这里停车。', pinyin: 'Qǐng zài zhèlǐ tíngchē.', russian: 'Остановите здесь, пожалуйста.', note: 'Фраза для такси или машины.' },
  // День 12
  { day: 12, period: 1, chinese: '这里有无线网吗？', pinyin: 'Zhèlǐ yǒu wúxiànwǎng ma?', russian: 'Здесь есть Wi-Fi?', note: 'Можно также сказать Wi-Fi, но 无线网 звучит по-китайски.' },
  { day: 12, period: 2, chinese: '我的手机没电了。', pinyin: 'Wǒ de shǒujī méi diàn le.', russian: 'У меня сел телефон.', note: 'Критическая фраза цифрового выживания.' },
  // День 13
  { day: 13, period: 1, chinese: '我迷路了。', pinyin: 'Wǒ mílù le.', russian: 'Я заблудился.', note: 'Скажи это и сразу покажи адрес общежития или контакт сопровождающего.' },
  { day: 13, period: 2, chinese: '可以帮我一下吗？', pinyin: 'Kěyǐ bāng wǒ yíxià ma?', russian: 'Можете мне помочь?', note: 'Простая и очень сильная фраза.' },
  // День 14
  { day: 14, period: 1, chinese: '我身体不舒服。', pinyin: 'Wǒ shēntǐ bù shūfu.', russian: 'Я плохо себя чувствую.', note: 'Универсальная фраза, если что-то не так.' },
  { day: 14, period: 2, chinese: '我头疼 / 肚子疼。', pinyin: 'Wǒ tóu téng / dùzi téng.', russian: 'У меня болит голова / живот.', note: 'Можно выбрать нужный вариант.' },
  // День 15
  { day: 15, period: 1, chinese: '附近有药店吗？', pinyin: 'Fùjìn yǒu yàodiàn ma?', russian: 'Рядом есть аптека?', note: 'Полезно, если нужны пластыри, таблетки или что-то простое.' },
  { day: 15, period: 2, chinese: '请帮我叫老师。', pinyin: 'Qǐng bāng wǒ jiào lǎoshī.', russian: 'Пожалуйста, позовите учителя.', note: 'Если ситуация серьёзная — не геройствуй.' },
  // День 16
  { day: 16, period: 1, chinese: '我可以拍照吗？', pinyin: 'Wǒ kěyǐ pāizhào ma?', russian: 'Можно сфотографировать?', note: 'В некоторых местах лучше сначала спросить.' },
  { day: 16, period: 2, chinese: '这里可以坐吗？', pinyin: 'Zhèlǐ kěyǐ zuò ma?', russian: 'Здесь можно сесть?', note: 'Полезно в кафе, кампусе, транспорте и очередях.' },
  // День 17
  { day: 17, period: 1, chinese: '这是什么？', pinyin: 'Zhè shì shénme?', russian: 'Что это?', note: 'Базовый вопрос для еды, предметов и странных кнопок.' },
  { day: 17, period: 2, chinese: '这个怎么用？', pinyin: 'Zhège zěnme yòng?', russian: 'Как этим пользоваться?', note: 'Подходит для автоматов, терминалов, стиралок и приложений.' },
  // День 18
  { day: 18, period: 1, chinese: '有大一点的吗？', pinyin: 'Yǒu dà yìdiǎn de ma?', russian: 'Есть побольше?', note: 'Для одежды, обуви, порций и упаковок.' },
  { day: 18, period: 2, chinese: '有小一点的吗？', pinyin: 'Yǒu xiǎo yìdiǎn de ma?', russian: 'Есть поменьше?', note: 'Вторая половина выживания в магазине.' },
  // День 19
  { day: 19, period: 1, chinese: '现在几点？', pinyin: 'Xiànzài jǐ diǎn?', russian: 'Который сейчас час?', note: 'Даже если есть телефон, фраза всё равно полезная.' },
  { day: 19, period: 2, chinese: '我们什么时候出发？', pinyin: 'Wǒmen shénme shíhou chūfā?', russian: 'Когда мы выезжаем / отправляемся?', note: 'Фраза для группы, экскурсий и сборов.' },
  // День 20
  { day: 20, period: 1, chinese: '谢谢你的帮助。', pinyin: 'Xièxie nǐ de bāngzhù.', russian: 'Спасибо за помощь.', note: 'Хорошая фраза, чтобы оставить о себе приятное впечатление.' },
  { day: 20, period: 2, chinese: '辛苦了！', pinyin: 'Xīnkǔ le!', russian: 'Спасибо за труд / вы постарались!', note: 'Очень китайская фраза уважения. Её приятно услышать.' },
];

let _tianhaoPopupTypeTimer = null;
let _tianhaoPollInterval = null;

function _getTianhaoSeen() {
  try { return new Set(JSON.parse(localStorage.getItem(TIANHAO_SEEN_KEY) || '[]')); } catch (e) { return new Set(); }
}
function _markTianhaoSeen(key) {
  try {
    const s = _getTianhaoSeen(); s.add(key);
    localStorage.setItem(TIANHAO_SEEN_KEY, JSON.stringify([...s]));
  } catch (e) {}
}

function _getTripDay() {
  const start = new Date(TIANHAO_TRIP_START + 'T00:00:00+08:00');
  const now = new Date();
  const diff = Math.floor((now - start) / 86400000) + 1;
  return diff;
}

function _getCurrentPeriod() {
  const now = new Date();
  const h = now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai', hour: 'numeric', hour12: false });
  const hour = parseInt(h);
  if (hour >= 13 && hour < 16) return 1;
  if (hour >= 18 && hour < 21) return 2;
  return 0;
}

function getCurrentTianhaoPhrase() {
  const day = _getTripDay();
  const period = _getCurrentPeriod();
  if (day < 1 || day > 20 || period === 0) return null;
  return TIANHAO_PHRASES.find(p => p.day === day && p.period === period) || null;
}

function startTianhaoPoller() {
  if (_tianhaoPollInterval) return;
  checkTianhaoPhrase();
  _tianhaoPollInterval = setInterval(checkTianhaoPhrase, 60000);
}
window.startTianhaoPoller = startTianhaoPoller;

function checkTianhaoPhrase() {
  const phrase = getCurrentTianhaoPhrase();
  renderTianhaoPhraseCard();
  if (!phrase) return;
  const key = `${phrase.day}-${phrase.period}`;
  if (_getTianhaoSeen().has(key)) return;
  _markTianhaoSeen(key);
  showTianhaoPopup(phrase);
}
window.checkTianhaoPhrase = checkTianhaoPhrase;

function renderTianhaoPhraseCard() {
  const el = document.getElementById('tianhaoPhraseCard');
  if (!el) return;
  const day = _getTripDay();
  const period = _getCurrentPeriod();
  const phrase = getCurrentTianhaoPhrase();

  if (day < 1 || day > 20) {
    el.style.display = 'none';
    return;
  }

  el.style.display = 'block';

  if (!phrase) {
    const next = period === 0 && day >= 1 && day <= 20
      ? (new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai', hour: 'numeric', hour12: false }) < 13 ? '13:00' : period === 1 ? '18:00' : 'завтра в 13:00')
      : '';
    el.innerHTML = `
      <div class="card-inner" style="padding:12px 14px;">
        <div style="font-size:9px;font-family:monospace;color:var(--text3);letter-spacing:1px;margin-bottom:6px;">孙天昊提示 // ФРАЗА ДНЯ · ДЕНЬ ${day}</div>
        <div style="font-size:11px;color:var(--text2);">Следующая фраза появится в ${next || 'следующем окне'}</div>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="card-inner" style="padding:12px 14px;cursor:pointer;" onclick="showTianhaoPopup(window._tianhaoCurrentPhrase)">
      <div style="font-size:9px;font-family:monospace;color:var(--text3);letter-spacing:1px;margin-bottom:8px;">孙天昊提示 // ФРАЗА ДНЯ · ДЕНЬ ${day} · ${period === 1 ? '13:00–16:00' : '18:00–21:00'}</div>
      <div style="font-size:22px;font-weight:700;color:var(--text);line-height:1.3;margin-bottom:4px;">${escapeHtml(phrase.chinese)}</div>
      <div style="font-size:11px;color:var(--text3);font-style:italic;margin-bottom:6px;">${escapeHtml(phrase.pinyin)}</div>
      <div style="font-size:13px;color:var(--text2);">${escapeHtml(phrase.russian)}</div>
      <div style="font-size:10px;color:var(--text3);margin-top:6px;border-top:1px solid var(--border);padding-top:6px;">Тяньхао: ${escapeHtml(phrase.note)}</div>
    </div>`;
  window._tianhaoCurrentPhrase = phrase;
}

function showTianhaoPopup(phrase) {
  if (!phrase) return;
  const overlay = document.getElementById('tianhaoPopupOverlay');
  const imageEl = document.getElementById('tianhaoPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('tianhaoPopupText');
  const chineseEl = document.getElementById('tianhaoPopupChinese');
  const pinyinEl = document.getElementById('tianhaoPopupPinyin');
  if (!overlay || !textEl) return;

  if (imageEl) {
    const img = TIANHAO_IMGS[Math.floor(Math.random() * TIANHAO_IMGS.length)];
    imageEl.style.backgroundImage = `url('${img}')`;
    imageEl.style.animation = 'none';
    void imageEl.offsetWidth;
    imageEl.style.animation = '';
  }
  if (box) {
    box.style.animation = 'none';
    void box.offsetWidth;
    box.style.animation = '';
  }

  if (chineseEl) chineseEl.textContent = phrase.chinese;
  if (pinyinEl) pinyinEl.textContent = phrase.pinyin;

  document.body.classList.add('architect-popup-open');
  overlay.style.display = 'flex';
  _typeTianhaoText(`${phrase.russian} — ${phrase.note}`);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}
window.showTianhaoPopup = showTianhaoPopup;

function _typeTianhaoText(text) {
  const textEl = document.getElementById('tianhaoPopupText');
  if (!textEl) return;
  if (_tianhaoPopupTypeTimer) { clearInterval(_tianhaoPopupTypeTimer); _tianhaoPopupTypeTimer = null; }
  textEl.innerHTML = '<span class="tianhao-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.tianhao-popup-typed');
  let i = 0;
  _tianhaoPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(_tianhaoPopupTypeTimer);
      _tianhaoPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeTianhaoPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('tianhaoPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  if (_tianhaoPopupTypeTimer) { clearInterval(_tianhaoPopupTypeTimer); _tianhaoPopupTypeTimer = null; }
  document.body.classList.remove('architect-popup-open');
}
window.closeTianhaoPopup = closeTianhaoPopup;
