function getRaidThemeKey() {
    return document.body.classList.contains('theme-genshin') ? 'genshin' : 'cyberpunk';
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function setRaidButtonState(text, disabled, background = '', color = '') {
    const btn = document.getElementById('raid-action-btn');
    if (!btn) return;
    btn.disabled = !!disabled;
    btn.innerHTML = `<i class="ti ti-broadcast"></i> ${text}`;
    btn.style.background = background;
    btn.style.color = color;
    btn.style.opacity = disabled ? '0.72' : '1';
}

function setRaidStatusText(text, color = 'var(--text2)') {
    const status = document.getElementById('raid-status-text');
    if (!status) return;
    status.textContent = text;
    status.style.color = color;
}

function setRaidResultPanel(mode = '', title = '', text = '') {
    const panel = document.getElementById('raid-result-panel');
    if (!panel) return;
    if (!mode) {
        panel.style.display = 'none';
        panel.className = 'raid-result-panel';
        panel.innerHTML = '';
        return;
    }
    panel.style.display = 'block';
    panel.className = `raid-result-panel ${mode}`;
    const icon = mode === 'success' ? '✓' : mode === 'danger' ? '✗' : '●';
    panel.innerHTML = `
        <div class="raid-result-icon">${icon}</div>
        <div class="raid-result-title">${escapeHtml(title)}</div>
        <div class="raid-result-text">${escapeHtml(text)}</div>
    `;
    if (mode === 'danger') {
        const content = document.querySelector('.raid-content');
        if (content) {
            content.classList.remove('raid-shake');
            void content.offsetWidth;
            content.classList.add('raid-shake');
            setTimeout(() => content.classList.remove('raid-shake'), 550);
        }
    }
}

function updateRaidRoster(participants = [], currentUserIdValue = currentUserId) {
    const roster = document.getElementById('raid-roster');
    const risk = document.getElementById('raid-roster-risk');
    if (!roster) return;

    const list = Array.isArray(participants) ? participants : [];
    if (!list.length) {
        roster.innerHTML = '<span class="raid-roster-empty">Ожидание бойцов...</span>';
        if (risk) risk.textContent = 'RISK: MEDIUM';
        return;
    }

    roster.innerHTML = list.map((player, index) => {
        const isMe = Number(player.telegram_id) === Number(currentUserIdValue);
        const name = player.name || player.full_name || `Боец ${index + 1}`;
        return `<span class="raid-roster-chip ${isMe ? 'me' : ''}">
            <b>${escapeHtml(String(name).slice(0, 1).toUpperCase())}</b>
            ${escapeHtml(name)}
        </span>`;
    }).join('');

    if (risk) {
        const ready = list.length >= RAID_CONFIG.minPlayers;
        risk.textContent = ready ? 'RISK: HIGH // READY' : 'RISK: MEDIUM';
    }
}

function setRaidProgressVisual(percent, state = 'INIT', hint = 'Neural handshake pending', tone = 'pending') {
    const progressBar = document.getElementById('raid-progress-bar');
    const percentLabel = document.getElementById('raid-progress-percent');
    const hintLabel = document.getElementById('raid-progress-hint');
    const stateLabel = document.getElementById('raid-sync-state');
    if (!progressBar || !percentLabel || !hintLabel || !stateLabel) return;

    const safePercent = Math.max(0, Math.min(Math.round(percent || 0), 100));
    const palette = {
        pending: {
            background: 'linear-gradient(90deg, var(--red), #ff7a18)',
            glow: '0 0 18px rgba(255, 80, 55, 0.42)',
            color: 'var(--text)'
        },
        success: {
            background: 'linear-gradient(90deg, #2ecc71, #6cffb8)',
            glow: '0 0 20px rgba(46, 204, 113, 0.42)',
            color: '#d6ffe9'
        },
        danger: {
            background: 'linear-gradient(90deg, #a30d15, #ff4d5a)',
            glow: '0 0 20px rgba(220, 65, 82, 0.45)',
            color: '#ffd6dc'
        }
    };
    const activeTone = palette[tone] || palette.pending;

    progressBar.style.width = safePercent + '%';
    progressBar.style.background = activeTone.background;
    progressBar.style.boxShadow = activeTone.glow;
    percentLabel.textContent = safePercent + '%';
    hintLabel.textContent = hint;
    stateLabel.textContent = state;
    stateLabel.style.color = activeTone.color;
}

function updateRaidUI(joinedCount, target = RAID_CONFIG.minPlayers) {
    const currentLabel = document.getElementById('raid-current-count');
    const maxLabel = document.getElementById('raid-max-count');
    if (!currentLabel || !maxLabel) return;

    const safeCount = Math.max(0, Math.min(joinedCount || 0, RAID_CONFIG.maxPlayers));
    const safeTarget = Math.max(1, target || RAID_CONFIG.minPlayers);
    const percentage = Math.min((safeCount / safeTarget) * 100, 100);
    const ready = safeCount >= safeTarget;

    currentLabel.innerText = safeCount;
    maxLabel.innerText = safeTarget;
    setRaidProgressVisual(
        percentage,
        ready ? 'READY' : 'ASSEMBLING',
        ready ? 'Отряд собран. Канал готов к запуску.' : `Идёт синхронизация отряда: ${safeCount}/${safeTarget}`,
        ready ? 'success' : 'pending'
    );
}

function prepareRaidVisual() {
    const currentTheme = getRaidThemeKey();
    const config = RAID_CONFIG[currentTheme];
    const bossImg = document.getElementById('boss-img');
    const bossTitle = document.getElementById('boss-title');
    const frame = document.querySelector('.boss-frame');
    const kickerText = document.querySelector('.raid-kicker span:last-child');
    const threatStrip = document.querySelector('.raid-threat-strip');
    const existingPlaceholder = frame ? frame.querySelector('.boss-placeholder') : null;

    if (bossTitle) bossTitle.innerText = config.title;
    if (kickerText) kickerText.textContent = config.kicker || 'MU RAID // 夜间行动';
    if (threatStrip && Array.isArray(config.chips)) {
        threatStrip.innerHTML = config.chips.map(chip => `<span class="raid-chip">${escapeHtml(chip)}</span>`).join('');
    }
    if (existingPlaceholder) existingPlaceholder.remove();
    if (!bossImg) return;

    bossImg.style.display = 'block';
    bossImg.style.backgroundColor = 'transparent';
    bossImg.onload = function() {
        const placeholder = frame ? frame.querySelector('.boss-placeholder') : null;
        if (placeholder) placeholder.remove();
        this.style.display = 'block';
    };
    bossImg.onerror = function() {
        this.style.display = 'none';
        if (!frame || frame.querySelector('.boss-placeholder')) return;

        const placeholder = document.createElement('div');
        placeholder.className = 'boss-placeholder';
        placeholder.style.width = '228px';
        placeholder.style.height = '252px';
        placeholder.style.borderRadius = currentTheme === 'genshin' ? '24px' : '28px';
        placeholder.style.background = config.placeholderColor;
        placeholder.style.display = 'flex';
        placeholder.style.alignItems = 'center';
        placeholder.style.justifyContent = 'center';
        placeholder.style.color = '#fff';
        placeholder.style.fontSize = '40px';
        placeholder.style.fontWeight = 'bold';
        placeholder.style.boxShadow = '0 0 20px ' + config.placeholderColor;
        placeholder.innerText = 'M.Y.';
        Object.assign(placeholder.style, {
            transform: 'scale(0.92) translateY(12px)',
            opacity: '0',
            transition: 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 0.3s',
            animation: 'bossFloat 4s ease-in-out infinite 0.9s'
        });
        frame.appendChild(placeholder);
        setTimeout(() => {
            placeholder.style.transform = 'scale(1) translateY(0)';
            placeholder.style.opacity = '1';
        }, 50);
    };
    bossImg.src = config.img;
}

async function playRaidIntro(token) {
    const steps = [
        { percent: 8, state: 'LINK', hint: 'Нейролинк инициирован', status: 'Поднимаем скрытый канал цели...' },
        { percent: 24, state: 'SCAN', hint: 'Разведка маршрута', status: 'Сканируем коридоры, расписание и окна риска...' },
        { percent: 41, state: 'MASK', hint: 'Маскировка сигнала', status: 'Глушим следы отряда в локальной сети...' },
        { percent: 63, state: 'ROUTE', hint: 'Маршрут отхода', status: 'Собираем точки входа и запасной выход...' },
        { percent: 82, state: 'LOCK', hint: 'Фиксация операции', status: 'Канал почти стабилен. Держим синхронизацию...' },
        { percent: 100, state: 'READY', hint: 'Операция готова', status: 'Контур активен. Можно подключаться к рейду.' }
    ];

    for (const step of steps) {
        if (token !== raidIntroToken) return false;
        setRaidProgressVisual(step.percent, step.state, step.hint, step.percent >= 100 ? 'success' : 'pending');
        setRaidStatusText(step.status, step.percent >= 100 ? '#2ecc71' : 'var(--text2)');
        await sleep(step.percent >= 100 ? 580 : 720);
    }

    return token === raidIntroToken;
}

function closeRaid() {
    const overlay = document.getElementById('raid-overlay');
    raidIntroToken += 1;
    if (overlay) overlay.classList.remove('active');
    if (raidRefreshTimer) {
        clearInterval(raidRefreshTimer);
        raidRefreshTimer = null;
    }
}

async function showRaid() {
    prepareRaidVisual();
    updateRaidUI(0);
    updateRaidRoster([]);
    setRaidResultPanel();
    setRaidStatusText('Синхронизация рейда...');
    setRaidButtonState('Загрузка статуса...', true);

    const overlay = document.getElementById('raid-overlay');
    if (overlay) overlay.classList.add('active');

    if (raidRefreshTimer) {
        clearInterval(raidRefreshTimer);
        raidRefreshTimer = null;
    }

    const introToken = ++raidIntroToken;
    const introCompleted = await playRaidIntro(introToken);
    if (!introCompleted || !document.getElementById('raid-overlay')?.classList.contains('active')) return;

    await loadRaidStatus();

    if (raidRefreshTimer) clearInterval(raidRefreshTimer);
    raidRefreshTimer = setInterval(() => {
        const isOpen = document.getElementById('raid-overlay')?.classList.contains('active');
        if (isOpen && !isJoiningRaid) loadRaidStatus();
    }, 5000);
}

async function loadRaidStatus() {
    try {
        const r = await fetch(`${API_URL}/api/raid/status?telegram_id=${currentUserId || 0}`);
        if (!r.ok) throw new Error('status');

        const data = await r.json();
        const raidLimit = data.limit_today || 3;
        const finishedToday = data.finished_today || 0;
        const requiredPlayers = data.required_players || RAID_CONFIG.minPlayers;
        const numericRemaining = typeof data.remaining_today === 'number'
            ? data.remaining_today
            : Math.max(0, raidLimit - finishedToday);
        const remainingToday = isAdmin ? 'без лимита' : `${numericRemaining}/${raidLimit}`;

        if (!data.raid) {
            updateRaidUI(0, requiredPlayers);
            updateRaidRoster([]);
            setRaidResultPanel();
            setRaidProgressVisual(6, 'STANDBY', 'Операция ждёт первого бойца', 'pending');
            setRaidStatusText(
                isAdmin
                    ? 'Рейд ещё не создан. Админ может запустить одиночный тест или собрать команду.'
                    : `Рейд ещё не собран. Осталось попыток сегодня: ${remainingToday}.`
            );
            setRaidButtonState(
                'Подключиться к нейролинку',
                finishedToday >= raidLimit && !isAdmin
            );
            return;
        }

        const participants = data.participants || [];
        const count = data.count ?? participants.length ?? 0;
        const participantNames = participants.map(p => p.name).filter(Boolean).join(' • ');
        const alreadyJoined = participants.some(p => p.telegram_id === currentUserId);
        updateRaidRoster(participants);

        if (data.raid.status === 'finished') {
            const success = data.raid.result === 'success';
            updateRaidUI(Math.max(count, requiredPlayers), requiredPlayers);
            setRaidProgressVisual(
                100,
                success ? 'VICTORY' : 'FAIL',
                success ? 'Операция прошла. Награда начислена.' : 'Операция сорвана. Ставки потеряны.',
                success ? 'success' : 'danger'
            );
            setRaidResultPanel(
                success ? 'success' : 'danger',
                success ? 'РЕЙД УСПЕШЕН' : 'РЕЙД СОРВАН',
                success
                    ? `Команда вышла чисто. +100★ каждому участнику.`
                    : 'Система заметила отряд. Ставка сгорела.'
            );
            setRaidStatusText(
                success
                    ? `Финал: успех.${participantNames ? ' Отряд: ' + participantNames : ''}`
                    : `Финал: провал.${participantNames ? ' Отряд: ' + participantNames : ''}`,
                success ? '#2ecc71' : '#cc4444'
            );
            setRaidButtonState(
                isAdmin || numericRemaining > 0 ? 'Начать новый рейд' : 'Рейды на сегодня закрыты',
                !isAdmin && numericRemaining <= 0
            );
            return;
        }

        setRaidResultPanel();
        updateRaidUI(count, requiredPlayers);
        setRaidProgressVisual(
            Math.min((count / requiredPlayers) * 100, 100),
            alreadyJoined ? 'LINKED' : 'ASSEMBLING',
            alreadyJoined ? 'Ты уже синхронизирован с отрядом.' : 'Идёт добор бойцов для запуска.',
            count >= requiredPlayers ? 'success' : 'pending'
        );
        setRaidStatusText(
            alreadyJoined
                ? `Ты уже в отряде. Бойцов: ${count}/${requiredPlayers}.${participantNames ? ' ' + participantNames : ''}`
                : `Сбор отряда: ${count}/${requiredPlayers}.${participantNames ? ' ' + participantNames : ''} ${isAdmin ? '' : 'Осталось рейдов: ' + remainingToday + '.'}`,
            alreadyJoined ? '#2ecc71' : 'var(--text2)'
        );
        setRaidButtonState(
            alreadyJoined ? 'Ты уже в отряде' : 'Подключиться к нейролинку',
            alreadyJoined || isJoiningRaid
        );
    } catch(e) {
        updateRaidUI(0);
        updateRaidRoster([]);
        setRaidResultPanel('danger', 'СВЯЗЬ ПОТЕРЯНА', 'Не удалось получить статус операции.');
        setRaidStatusText('Не удалось загрузить статус рейда.', '#cc4444');
        setRaidButtonState('Повторить подключение', false);
    }
}

function getRaidErrorMessage(detail) {
    if (detail === 'Already joined') return 'Ты уже в этом рейде.';
    if (detail === 'Daily raid limit reached') return 'Сегодня лимит рейдов исчерпан. Попробуй завтра.';
    if (detail === 'Not enough points') return 'Недостаточно баллов для рейда.';
    return 'Не удалось присоединиться к рейду.';
}

let raidSelectedAnswer = null;
let raidCurrentQuestion = null;

async function fetchRaidQuestion() {
    try {
        const r = await fetch(`${API_URL}/api/raid/question`);
        if (!r.ok) return null;
        return await r.json();
    } catch(e) { return null; }
}

function showRaidQuestion(question) {
    raidCurrentQuestion = question;
    raidSelectedAnswer = null;

    const block = document.getElementById('raid-question-block');
    const prompt = document.getElementById('raid-q-prompt');
    const opts = document.getElementById('raid-q-options');
    const btn = document.getElementById('raid-q-submit');
    if (!block || !prompt || !opts || !btn) return;

    prompt.textContent = question.prompt;
    opts.innerHTML = ['a', 'b', 'c'].map(opt => `
        <button class="raid-q-option" data-opt="${opt}" onclick="selectRaidAnswer('${opt}')">
            <span class="raid-q-opt-key">${opt.toUpperCase()}</span>
            <span>${escapeHtml(question['option_' + opt])}</span>
        </button>
    `).join('');
    btn.disabled = true;
    block.style.display = 'block';
    setRaidButtonState('Подключиться к нейролинку', true);
}

function selectRaidAnswer(opt) {
    raidSelectedAnswer = opt;
    document.querySelectorAll('.raid-q-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.opt === opt);
    });
    const btn = document.getElementById('raid-q-submit');
    if (btn) btn.disabled = false;
    try { tg.HapticFeedback.selectionChanged(); } catch(e) {}
}

async function submitRaidAnswer() {
    if (!raidSelectedAnswer || !currentUserId || isJoiningRaid) return;
    const block = document.getElementById('raid-question-block');
    const btn = document.getElementById('raid-q-submit');
    if (btn) btn.disabled = true;
    isJoiningRaid = true;
    setRaidProgressVisual(92, 'BREACH', 'Анализ передан. Подключаемся к контуру...', 'pending');
    setRaidButtonState('Синхронизация...', true, '#e67e22', '#fff');
    if (block) block.style.display = 'none';
    await _executeRaidJoin(raidSelectedAnswer, raidCurrentQuestion && raidCurrentQuestion.id);
}

async function _executeRaidJoin(answer, questionId) {
    try {
        const payload = {telegram_id: currentUserId};
        if (answer) payload.answer = answer;
        if (questionId) payload.question_id = questionId;
        const r = await fetch(`${API_URL}/api/raid/join`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await r.json();

        if (!r.ok) {
            showToast(getRaidErrorMessage(data.detail));
            return;
        }

        if (typeof data.new_points === 'number') {
            currentPoints = data.new_points;
            updatePoints();
        }

        const correct = data.answer_correct;
        if (answer) {
            setRaidStatusText(
                correct ? '✓ Анализ точный — уязвимость обнаружена.' : '✗ Анализ промахнулся. Продолжаем операцию.',
                correct ? '#2ecc71' : '#e67e22'
            );
            await sleep(900);
        }

        if (data.launched && data.result === 'success') {
            setRaidProgressVisual(100, 'VICTORY', 'Альфа-цель пробита. Награда зачислена.', 'success');
            setRaidResultPanel('success', 'РЕЙД УСПЕШЕН', 'Команда вышла чисто. +100★ каждому участнику.');
            launchConfetti(80);
        } else if (data.launched && data.result === 'defended') {
            setRaidProgressVisual(100, 'FAIL', 'Контур сорван. Операция провалена.', 'danger');
            setRaidResultPanel('danger', 'РЕЙД СОРВАН', 'Система обнаружила отряд. Ставка сгорела.');
        } else {
            setRaidProgressVisual(
                Math.min(((data.count || 1) / RAID_CONFIG.minPlayers) * 100, 100),
                'LINKED',
                `Бойцов в контуре: ${data.count || 1}/${RAID_CONFIG.minPlayers}`,
                'pending'
            );
        }

        try {
            tg.HapticFeedback.notificationOccurred(
                data.launched && data.result === 'defended' ? 'error' : 'success'
            );
        } catch(e) {}

        showToast(data.message || 'Рейд обновлён.');
        loadLeaderboard();
        loadPoints(currentUserId);
    } catch(e) {
        showToast('Ошибка соединения с рейдом.');
    } finally {
        isJoiningRaid = false;
        loadRaidStatus();
    }
}

async function joinRaid() {
    if (isJoiningRaid) return;
    if (!currentUserId) { showToast('Откройте приложение через Telegram бота'); return; }
    if (currentPoints < 50) { showToast('Недостаточно баллов. Нужно 50★'); return; }

    tg.showPopup({
        title: '⚔️ Вступить в рейд?',
        message: 'Ты ставишь 50★. Если отряд из 3+ человек соберётся — начнётся операция. Правильный анализ цели повышает шансы всей команды на победу.',
        buttons: [{id:'confirm', type:'default', text:'⚔️ В РЕЙД'}, {type:'cancel'}]
    }, async (btnId) => {
        if (btnId !== 'confirm') return;

        setRaidButtonState('Получение задания...', true);
        const question = await fetchRaidQuestion();
        if (question) {
            showRaidQuestion(question);
        } else {
            isJoiningRaid = true;
            setRaidProgressVisual(92, 'BREACH', 'Подключаем тебя к скрытому контуру...', 'pending');
            setRaidButtonState('Синхронизация...', true, '#e67e22', '#fff');
            await _executeRaidJoin(null, null);
        }
    });
}

// ===== RIPPLE ЭФФЕКТ =====
