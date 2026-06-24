// Квиз «Факты о поездке» — обязательный квиз с одной попыткой навсегда.
// Контент (вопросы) полностью задаётся админами через панель «Квиз», без сидов в коде.

let _tripQuizQuestions = [];
let _tripQuizAnswers = {};
let _tripQuizReward = 0;
let _tripQuizPassRatio = 0.7;

async function syncTripQuizBannerVisibility() {
  const banner = document.getElementById('tripQuizBanner');
  if (!banner || !currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/trip-quiz/status/${currentUserId}`);
    const data = await r.json();
    banner.style.display = (data.available && !data.attempted) ? 'block' : 'none';
  } catch (e) {
    banner.style.display = 'none';
  }
}

async function openTripQuizPage() {
  const el = document.getElementById('tripQuizContent');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';

  try {
    const statusR = await fetch(`${API_URL}/api/trip-quiz/status/${currentUserId}`);
    const status = await statusR.json();

    if (!status.available) {
      el.innerHTML = '<div class="empty-state">Квиз пока не настроен администраторами.</div>';
      return;
    }

    if (status.attempted) {
      renderTripQuizResult(el, status);
      return;
    }

    const qR = await fetch(`${API_URL}/api/trip-quiz/questions/${currentUserId}`);
    if (!qR.ok) {
      if (qR.status === 409) {
        const statusR2 = await fetch(`${API_URL}/api/trip-quiz/status/${currentUserId}`);
        renderTripQuizResult(el, await statusR2.json());
        return;
      }
      el.innerHTML = '<div class="empty-state">Ошибка загрузки квиза</div>';
      return;
    }
    const data = await qR.json();
    _tripQuizQuestions = data.questions || [];
    _tripQuizReward = data.reward || 50;
    _tripQuizPassRatio = data.pass_ratio || 0.7;
    _tripQuizAnswers = {};
    renderTripQuizForm(el);
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Ошибка загрузки квиза</div>';
  }
}

function renderTripQuizForm(el) {
  const passPct = Math.round(_tripQuizPassRatio * 100);
  el.innerHTML = `
    <div class="card" style="margin-bottom:10px;">
      <div class="card-inner" style="padding:12px 14px;">
        <div style="font-size:12px;color:var(--text2);">
          Обязательный квиз. Порог прохождения — ${passPct}%. Награда за успех — ${_tripQuizReward}★.
          <strong style="color:#cc4444;">Попытка только одна, повторно пройти будет нельзя.</strong>
        </div>
      </div>
    </div>
    ${_tripQuizQuestions.map((q, i) => `
      <div class="card" style="margin-bottom:10px;">
        <div class="card-inner" style="padding:12px 14px;">
          <div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:10px;">${i + 1}. ${escapeHtml(q.prompt)}</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${['a', 'b', 'c'].map(opt => `
              <button type="button" class="event-option-btn trip-quiz-option" id="tripQuizOpt-${q.id}-${opt}"
                onclick="selectTripQuizAnswer(${q.id}, '${opt}')">${escapeHtml(q['option_' + opt])}</button>
            `).join('')}
          </div>
        </div>
      </div>
    `).join('')}
    <button class="btn btn-primary" style="width:100%;padding:12px;margin-bottom:16px;" onclick="submitTripQuiz()">[ ОТПРАВИТЬ ОТВЕТЫ ]</button>
  `;
}

function selectTripQuizAnswer(questionId, option) {
  _tripQuizAnswers[questionId] = option;
  ['a', 'b', 'c'].forEach(opt => {
    const btn = document.getElementById(`tripQuizOpt-${questionId}-${opt}`);
    if (!btn) return;
    if (opt === option) {
      btn.style.borderColor = 'var(--gold)';
      btn.style.background = 'rgba(212,175,55,0.16)';
    } else {
      btn.style.borderColor = '';
      btn.style.background = '';
    }
  });
}

async function submitTripQuiz() {
  if (Object.keys(_tripQuizAnswers).length < _tripQuizQuestions.length) {
    showToast('Ответь на все вопросы перед отправкой');
    return;
  }

  const confirmed = await showConfirmDialog({
    title: 'Отправить ответы?',
    message: 'После отправки квиз нельзя пройти заново. Проверь все ответы.',
    confirmText: 'Отправить',
  });
  if (!confirmed) return;

  const answers = Object.keys(_tripQuizAnswers).map(qid => ({
    question_id: Number(qid),
    selected_option: _tripQuizAnswers[qid],
  }));

  try {
    const r = await fetch(`${API_URL}/api/trip-quiz/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: currentUserId, answers }),
    });
    if (!r.ok) {
      showToast('Ошибка отправки квиза');
      return;
    }
    const result = await r.json();
    const el = document.getElementById('tripQuizContent');
    renderTripQuizResult(el, {
      score: result.score,
      total: result.total,
      passed: result.passed,
      completed_at: null,
    });
    syncTripQuizBannerVisibility();
    if (typeof loadUserData === 'function') loadUserData();
    if (result.passed) {
      showToast(`✅ Квиз пройден! +${result.reward}★`);
    } else {
      showToast('Квиз завершён');
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

function renderTripQuizResult(el, status) {
  const pct = status.total ? Math.round((status.score / status.total) * 100) : 0;
  el.innerHTML = `
    <div class="card">
      <div class="card-inner" style="padding:18px 14px;text-align:center;">
        <div style="font-size:36px;margin-bottom:8px;">${status.passed ? '✅' : '📍'}</div>
        <div style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:6px;">
          ${status.passed ? 'Квиз пройден' : 'Квиз завершён'}
        </div>
        <div style="font-size:12px;color:var(--text2);">
          Результат: ${status.score}/${status.total} (${pct}%)
        </div>
      </div>
    </div>
  `;
}
