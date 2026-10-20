/**
 * Dream Hub v1.2 - Frontend Controller
 * Vanilla ES6+, zero external build dependencies, Pure OLED Dark (#000000), Mobile-First ergonomics.
 */

const App = (() => {
  const state = {
    currentView: 'overview',
    taskMode: 'kanban',
    taskPriorityFilter: 'all',
    taskSearchQuery: '',
    financeSubTab: 'extrato', // 'extrato', 'recorrencias', 'projecao'
    financeFilter: 'all',
    financeSearchQuery: '',
    notesFolderFilter: 'all',
    notesSearchQuery: '',
    goalsCategoryFilter: 'all',
    ideaStageFilter: 'all',
    ideaSearchQuery: '',
    quickCaptureTab: 'idea',
    tasks: [],
    ideas: [],
    notes: [],
    goals: [],
    transactions: [],
    recurringRules: [],
    financeMonth: new Date().toISOString().slice(0, 7),
    txnType: 'expense',

    timer: {
      mode: 'focus',
      focusMinutes: 25,
      durations: { focus: 25 * 60, short_break: 5 * 60, long_break: 15 * 60 },
      remainingSeconds: 25 * 60,
      isRunning: false,
      intervalId: null,
      selectedTaskId: null,
      startTime: null,
      endTime: null
    }
  };

  function formatMoney(cents) {
    const val = (cents || 0) / 100;
    return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    const parts = isoStr.slice(0, 10).split('-');
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}`;
    }
    return isoStr;
  }

  function formatFileSize(bytes) {
    const b = Number(bytes || 0);
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / (1024 * 1024)).toFixed(2)} MB`;
  }

  function showToast(msg) {
    const el = document.getElementById('toast-notification');
    if (!el) return;
    el.innerText = msg;
    el.classList.add('show');
    setTimeout(() => {
      el.classList.remove('show');
    }, 3200);
  }

  // Lightweight Vanilla JS Markdown Renderer ([RNF02] / Section 6.3)
  function renderMarkdown(mdText) {
    if (!mdText) return '<p style="color:var(--text-muted);">Sem conteúdo.</p>';
    let html = escapeHtml(mdText);

    // Code blocks ```...```
    html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
    // Inline code `...`
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    // Headings
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    // Blockquotes
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    // Bold & Italic
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    // Checklists & Bullet lists
    html = html.replace(/^- \[x\] (.+)$/gim, '<div>✅ <span style="text-decoration:line-through;color:var(--text-muted);">$1</span></div>');
    html = html.replace(/^- \[ \] (.+)$/gim, '<div>⬜ $1</div>');
    html = html.replace(/^- (.+)$/gm, '<div>• $1</div>');
    // Line breaks
    html = html.replace(/\n\n+/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return `<p>${html}</p>`;
  }

  function playCompletionChime() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();

      const playTone = (freq, delay, dur) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, ctx.currentTime + delay);
        gain.gain.setValueAtTime(0.22, ctx.currentTime + delay);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + delay + dur);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + delay);
        osc.stop(ctx.currentTime + delay + dur);
      };

      playTone(587.33, 0.0, 1.2);
      playTone(880.00, 0.15, 1.5);
    } catch (e) {
      console.warn('Audio chime unsupported:', e);
    }
  }

  // ---------------- API CLIENT ----------------
  async function apiFetch(endpoint, options = {}) {
    try {
      const headers = { ...(options.headers || {}) };
      if (!(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
      const res = await fetch(endpoint, { ...options, headers });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Falha na requisição' }));
        throw new Error(err.error || err.message || `Erro HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  }

  // ---------------- ROUTER & NAVIGATION ----------------
  function navigateTo(viewId) {
    state.currentView = viewId;
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) targetView.classList.add('active');

    const targetNav = document.querySelector(`.nav-${viewId}`);
    if (targetNav) targetNav.classList.add('active');

    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (viewId === 'overview') loadOverviewData();
    else if (viewId === 'tasks') loadTasksData();
    else if (viewId === 'time') loadTimeData();
    else if (viewId === 'finance') loadFinanceData();
    else if (viewId === 'notes') loadNotesData();
    else if (viewId === 'goals') loadGoalsData();
    else if (viewId === 'ideas') loadIdeasData();
  }

  // ---------------- COCKPIT "MEU DIA" MODULE ----------------
  async function loadOverviewData() {
    try {
      const res = await apiFetch('/api/cockpit/today');
      const data = res.data || res;

      document.getElementById('ov-pending-tasks').innerText = data.pending_tasks;
      document.getElementById('ov-urgent-tasks').innerText = `${data.tasks_due_today_count || 0} hoje • ${data.urgent_tasks} urgentes`;

      document.getElementById('ov-focus-min').innerText = `${data.today_focus_minutes}m`;
      document.getElementById('ov-focus-sessions').innerText = `${data.today_pomodoro_sessions} ciclos`;

      document.getElementById('ov-balance').innerText = formatMoney(data.month_balance_cents);
      document.getElementById('ov-finance-flow').innerText = `+${formatMoney(data.month_income_cents)} | -${formatMoney(data.month_expense_cents)}`;

      const goalsCountEl = document.getElementById('ov-goals-count');
      if (goalsCountEl) goalsCountEl.innerText = `${data.active_goals_count || 0} metas`;
      const ideasSubEl = document.getElementById('ov-ideas-sub');
      if (ideasSubEl) ideasSubEl.innerText = `${data.active_ideas || 0} ideias • ${data.notes_count || 0} notas`;

      // Render Active Goals on Cockpit
      const ovGoalsList = document.getElementById('ov-goals-list');
      if (ovGoalsList) {
        const activeGoals = data.active_goals || [];
        if (activeGoals.length === 0) {
          ovGoalsList.innerHTML = `
            <div class="empty-state" style="padding:16px 8px; margin:0;">
              <div class="empty-desc" style="margin-bottom:8px;">Nenhuma meta ativa. Defina metas de estudo ("estudar até aprender") ou financeiras.</div>
              <button class="btn btn-goals btn-sm" onclick="App.openGoalModal()">+ Criar Primeira Meta</button>
            </div>
          `;
        } else {
          ovGoalsList.innerHTML = activeGoals.map(g => renderGoalCard(g, true)).join('');
        }
      }

      // Render Today's & Priority Tasks
      const urgentList = document.getElementById('ov-urgent-list');
      const dueTasks = data.tasks_due_today || [];

      if (dueTasks.length === 0) {
        urgentList.innerHTML = `
          <div class="empty-state" style="padding:20px 8px;">
            <div class="empty-title" style="font-size:0.9rem;">Tudo sob controle hoje!</div>
            <div class="empty-desc" style="font-size:0.8rem; margin-bottom:8px;">Nenhuma tarefa vencendo hoje ou urgente pendente.</div>
          </div>
        `;
      } else {
        urgentList.innerHTML = dueTasks.slice(0, 5).map(t => `
          <div class="task-card" style="margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
              <span class="task-title" style="font-size:0.875rem;">${escapeHtml(t.title)}</span>
              <div style="display:flex; gap:4px; align-items:center;">
                ${t.recurrence && t.recurrence !== 'nenhuma' ? `<span class="badge badge-recurring">🔁 ${escapeHtml(t.recurrence)}</span>` : ''}
                <span class="badge badge-${t.priority}">${t.priority}</span>
              </div>
            </div>
            <div class="task-meta" style="margin-top:6px;">
              ${t.due_date ? `<span>📅 ${formatDate(t.due_date)}</span>` : ''}
              <span>🍅 ${t.completed_pomodoros}/${t.estimated_pomodoros} (${t.pomodoro_duration_minutes || 25}m)</span>
              <div style="margin-left:auto; display:flex; gap:6px;">
                <button class="btn btn-secondary btn-sm" style="min-height:34px; padding:2px 10px;" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">⏱ Focar</button>
                <button class="btn btn-tasks btn-sm" style="min-height:34px; padding:2px 10px;" onclick="App.updateTaskStatus(${t.id}, 'done')">✓ Concluir</button>
              </div>
            </div>
          </div>
        `).join('');
      }

      // Render Recent Ideas for 1-click conversion
      const recentIdeasEl = document.getElementById('ov-recent-ideas');
      if (recentIdeasEl) {
        const recentIdeas = data.recent_ideas || [];
        if (recentIdeas.length === 0) {
          recentIdeasEl.innerHTML = `
            <div class="empty-state" style="padding:16px 8px;">
              <div class="empty-desc" style="margin-bottom:0;">Nenhuma ideia pendente para converter. Use o botão + para capturar insights.</div>
            </div>
          `;
        } else {
          recentIdeasEl.innerHTML = recentIdeas.map(i => `
            <div class="transaction-item">
              <div class="txn-left">
                <span class="txn-desc">💡 ${escapeHtml(i.title)}</span>
                ${i.content ? `<span class="txn-sub">${escapeHtml(i.content.slice(0, 80))}</span>` : ''}
              </div>
              <button class="btn btn-ideas btn-sm" onclick="App.convertIdeaToTask(${i.id})">⚡ Virar Tarefa</button>
            </div>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Falha ao carregar cockpit:', err);
    }
  }

  // ---------------- ZERO-FRICTION QUICK CAPTURE MODAL ----------------
  function openQuickCaptureModal(defaultTab = 'idea') {
    const modal = document.getElementById('modal-quick-capture');
    const form = document.getElementById('form-quick-capture');
    if (form) form.reset();
    setQuickCaptureTab(defaultTab);
    modal.classList.add('active');
    setTimeout(() => {
      document.getElementById('qc-main-input')?.focus();
    }, 60);
  }

  function setQuickCaptureTab(tab) {
    state.quickCaptureTab = tab;
    ['idea', 'finance', 'task', 'note'].forEach(t => {
      document.getElementById(`qc-tab-${t}`)?.classList.toggle('active', t === tab);
    });

    document.getElementById('qc-idea-fields').style.display = tab === 'idea' ? 'block' : 'none';
    document.getElementById('qc-finance-fields').style.display = tab === 'finance' ? 'block' : 'none';
    document.getElementById('qc-task-fields').style.display = tab === 'task' ? 'block' : 'none';
    const noteFields = document.getElementById('qc-note-fields');
    if (noteFields) noteFields.style.display = tab === 'note' ? 'block' : 'none';

    const label = document.getElementById('qc-main-label');
    const input = document.getElementById('qc-main-input');
    const amountInput = document.getElementById('qc-amount-input');

    if (tab === 'idea') {
      label.innerText = 'Qual é a sua ideia rápida? *';
      input.placeholder = 'Ex: Automatizar backup, novo projeto...';
      if (amountInput) amountInput.required = false;
    } else if (tab === 'finance') {
      label.innerText = 'Descrição do Gasto ou Depósito *';
      input.placeholder = 'Ex: Café, Aluguel, Depósito Mensal...';
      if (amountInput) amountInput.required = true;
    } else if (tab === 'note') {
      label.innerText = 'Título da Anotação *';
      input.placeholder = 'Ex: Resumo de comandos Linux...';
      if (amountInput) amountInput.required = false;
    } else {
      label.innerText = 'Título da Tarefa *';
      input.placeholder = 'Ex: Revisar servidor Termux hoje...';
      if (amountInput) amountInput.required = false;
    }
  }

  async function submitQuickCapture(e) {
    e.preventDefault();
    const text = document.getElementById('qc-main-input').value.trim();
    if (!text) return;

    try {
      if (state.quickCaptureTab === 'idea') {
        const tags = document.getElementById('qc-idea-tags').value.trim();
        await apiFetch('/api/ideas', {
          method: 'POST',
          body: JSON.stringify({ title: text, content: '', stage: 'raw', tags })
        });
        showToast('💡 Ideia capturada!');
        if (state.currentView === 'ideas') await loadIdeasData();
      } else if (state.quickCaptureTab === 'finance') {
        const amountVal = parseFloat(document.getElementById('qc-amount-input').value || '0');
        const finType = document.getElementById('qc-fin-type').value;
        const isRec = document.getElementById('qc-fin-recurring').checked;
        await apiFetch('/api/finance/transactions', {
          method: 'POST',
          body: JSON.stringify({
            description: text,
            amount_cents: Math.round(amountVal * 100),
            type: finType,
            category: finType === 'income' ? 'Salário' : 'Outros',
            account: 'Conta Corrente',
            date: new Date().toISOString().slice(0, 10),
            is_recurring: isRec ? 1 : 0,
            recurrence: isRec ? 'mensal' : 'nenhuma'
          })
        });
        showToast(isRec ? '🔁 Regra e lançamento recorrente salvos!' : '💰 Lançamento registrado!');
        if (state.currentView === 'finance') await loadFinanceData();
      } else if (state.quickCaptureTab === 'note') {
        const content = document.getElementById('qc-note-content')?.value || '';
        await apiFetch('/api/notes', {
          method: 'POST',
          body: JSON.stringify({ title: text, content, folder: 'Geral', tags: '' })
        });
        showToast('📓 Anotação salva no caderno!');
        if (state.currentView === 'notes') await loadNotesData();
      } else if (state.quickCaptureTab === 'task') {
        const priority = document.getElementById('qc-task-priority').value;
        const recurrence = document.getElementById('qc-task-recurrence').value;
        await apiFetch('/api/tasks', {
          method: 'POST',
          body: JSON.stringify({
            title: text,
            priority,
            recurrence,
            due_date: new Date().toISOString().slice(0, 10)
          })
        });
        showToast('✓ Tarefa adicionada!');
        await loadTasksData();
      }
      closeModals();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro na captura rápida');
    }
  }

  // ---------------- PONTO 1: DECENTRALIZED ATTACHMENTS ([RF01], RN01) ----------------
  async function openAttachmentsModal(entityType, entityId, titleLabel = '') {
    document.getElementById('att-entity-type').value = entityType;
    document.getElementById('att-entity-id').value = entityId;
    document.getElementById('att-file-input').value = '';
    const titleEl = document.getElementById('modal-attachments-title');
    if (titleEl) {
      titleEl.innerText = titleLabel ? `📎 Anexos: ${titleLabel}` : '📎 Anexos do Registro';
    }
    document.getElementById('modal-attachments').classList.add('active');
    await loadEntityAttachments(entityType, entityId);
  }

  async function loadEntityAttachments(entityType, entityId) {
    const box = document.getElementById('attachments-list-box');
    if (!box) return;
    try {
      const list = await apiFetch(`/api/attachments/${entityType}/${entityId}`);
      if (list.length === 0) {
        box.innerHTML = `
          <div class="empty-state" style="padding:18px 10px; margin:4px 0;">
            <div class="empty-desc" style="margin-bottom:0;">Nenhum arquivo anexado a este item.</div>
          </div>
        `;
      } else {
        box.innerHTML = list.map(a => `
          <div class="attachment-item">
            <div style="min-width:0; flex:1;">
              <a href="/api/attachments/file/${a.id}" target="_blank" rel="noopener" class="attachment-name">📄 ${escapeHtml(a.filename)}</a>
              <div class="attachment-meta">${formatFileSize(a.file_size)} • ${escapeHtml(a.mime_type)}</div>
            </div>
            <div style="display:flex; gap:6px;">
              <a href="/api/attachments/file/${a.id}?download=1" class="btn btn-secondary btn-sm" title="Baixar arquivo">⬇</a>
              <button type="button" class="btn btn-danger btn-sm" title="Excluir arquivo do disco" onclick="App.deleteAttachment(${a.id}, '${entityType}', ${entityId})">🗑</button>
            </div>
          </div>
        `).join('');
      }
    } catch (e) {
      box.innerHTML = `<div class="error-state">Falha ao listar anexos.</div>`;
    }
  }

  async function uploadAttachment(e) {
    e.preventDefault();
    const entityType = document.getElementById('att-entity-type').value;
    const entityId = document.getElementById('att-entity-id').value;
    const fileInput = document.getElementById('att-file-input');
    const file = fileInput.files[0];
    if (!file) return;

    if (file.size > 15 * 1024 * 1024) {
      alert('O arquivo excede o limite máximo de 15 MB.');
      return;
    }

    const formData = new FormData();
    formData.append('entity_type', entityType);
    formData.append('entity_id', entityId);
    formData.append('file', file);

    const btn = document.getElementById('btn-upload-submit');
    if (btn) {
      btn.disabled = true;
      btn.innerText = 'Enviando...';
    }

    try {
      await apiFetch('/api/uploads', { method: 'POST', body: formData });
      fileInput.value = '';
      showToast('📎 Arquivo anexado com sucesso!');
      await loadEntityAttachments(entityType, entityId);
      refreshCurrentViewCounts();
    } catch (err) {
      alert(err.message || 'Erro ao enviar arquivo');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = '⬆ Enviar e Anexar Arquivo';
      }
    }
  }

  async function deleteAttachment(attachmentId, entityType, entityId) {
    if (!confirm('Remover este anexo permanentemente do banco e do disco?')) return;
    try {
      await apiFetch(`/api/attachments/${attachmentId}`, { method: 'DELETE' });
      showToast('🗑 Anexo removido do disco');
      await loadEntityAttachments(entityType, entityId);
      refreshCurrentViewCounts();
    } catch (e) {
      alert('Erro ao remover anexo');
    }
  }

  function refreshCurrentViewCounts() {
    if (state.currentView === 'tasks') loadTasksData();
    else if (state.currentView === 'finance') loadFinanceData();
    else if (state.currentView === 'notes') loadNotesData();
    else if (state.currentView === 'ideas') loadIdeasData();
  }

  // ---------------- PONTO 2: GOALS & MILESTONES MODULE ([RF02], [RF03], RN02) ----------------
  async function loadGoalsData() {
    try {
      const goals = await apiFetch('/api/goals');
      state.goals = goals;
      renderGoals();
      populateGoalSelectors();
    } catch (e) {
      showError('goals-list-container', 'Falha ao carregar metas.', () => loadGoalsData());
    }
  }

  function populateGoalSelectors() {
    const activeGoals = (state.goals || []).filter(g => g.status === 'em_andamento');
    const taskGoalSel = document.getElementById('task-goal-select');
    if (taskGoalSel) {
      const cur = taskGoalSel.value;
      taskGoalSel.innerHTML = '<option value="">(Nenhuma meta vinculada)</option>' +
        activeGoals.map(g => `<option value="${g.id}">🎯 ${escapeHtml(g.title)} (${g.progress_percent}%)</option>`).join('');
      taskGoalSel.value = cur;
    }
    const finGoalSel = document.getElementById('fin-goal-select');
    if (finGoalSel) {
      const cur = finGoalSel.value;
      finGoalSel.innerHTML = '<option value="">(Nenhuma meta)</option>' +
        activeGoals.map(g => `<option value="${g.id}">🎯 ${escapeHtml(g.title)} (${g.progress_percent}%)</option>`).join('');
      finGoalSel.value = cur;
    }
  }

  function filterGoals(category, btnEl) {
    state.goalsCategoryFilter = category;
    if (btnEl) {
      document.querySelectorAll('#goals-filter-bar .stage-pill').forEach(b => b.classList.remove('active'));
      btnEl.classList.add('active');
    }
    renderGoals();
  }

  function renderGoalCard(g, compact = false) {
    const catLabels = {
      financas: '💰 Finanças',
      estudos: '📚 Estudos',
      atividades: '✓ Atividades',
      pessoal: '🌱 Pessoal'
    };
    const isQual = g.goal_type === 'qualitativa';
    const valStr = g.goal_type === 'monetaria'
      ? `${formatMoney(Math.round((g.current_value || 0) * 100))} / ${g.target_value ? formatMoney(Math.round(g.target_value * 100)) : 'Livre'}`
      : (isQual
          ? `Qualitativa ("Até aprender") • ${g.current_value || 0} ${escapeHtml(g.unit || 'etapas')}`
          : `${g.current_value || 0} / ${g.target_value || '?'} ${escapeHtml(g.unit || '')}`);

    return `
      <div class="goal-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <div>
            <span class="badge badge-goal" style="margin-bottom:4px;">${catLabels[g.category] || g.category}</span>
            <h4 class="task-title" style="margin-bottom:2px;">${escapeHtml(g.title)}</h4>
          </div>
          <span class="badge ${g.status === 'alcancada' ? 'badge-recurring' : 'badge-medium'}">
            ${g.status === 'alcancada' ? '✓ Alcançada' : `${g.progress_percent}%`}
          </span>
        </div>
        ${!compact && g.description ? `<p style="font-size:0.8125rem; color:var(--text-secondary); margin:4px 0;">${escapeHtml(g.description)}</p>` : ''}
        <div class="goal-progress-track">
          <div class="goal-progress-fill" style="width:${Math.min(100, g.progress_percent || 0)}%;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; font-size:0.75rem; color:var(--text-secondary);">
          <span style="font-family:var(--font-mono);">${valStr}</span>
          ${g.deadline ? `<span>📅 Prazo: ${formatDate(g.deadline)}</span>` : ''}
          <div style="display:flex; gap:6px; margin-left:auto;">
            ${g.status !== 'alcancada' ? `
              <button class="btn btn-secondary btn-sm" style="min-height:34px; padding:2px 8px;" onclick="App.promptGoalProgress(${g.id}, '${g.goal_type}')">+ Avançar</button>
              <button class="btn btn-goals btn-sm" style="min-height:34px; padding:2px 8px;" onclick="App.completeGoal(${g.id})">✓ Concluir</button>
            ` : ''}
            ${!compact ? `
              <button class="btn btn-secondary btn-sm" style="min-height:34px; padding:2px 8px;" onclick="App.openGoalModal(${g.id})">Editar</button>
              <button class="btn btn-danger btn-sm" style="min-height:34px; padding:2px 8px;" onclick="App.deleteGoal(${g.id})">🗑</button>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }

  function renderGoals() {
    const container = document.getElementById('goals-list-container');
    if (!container) return;
    let filtered = state.goals || [];
    if (state.goalsCategoryFilter !== 'all') {
      filtered = filtered.filter(g => g.category === state.goalsCategoryFilter);
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🎯</div>
          <div class="empty-title">Nenhuma meta cadastrada</div>
          <div class="empty-desc">Defina metas de estudo ("estudar até aprender"), metas de pomodoros ou metas financeiras de poupança/aquisição.</div>
          <button class="btn btn-goals" onclick="App.openGoalModal()">+ Criar Nova Meta</button>
        </div>
      `;
      return;
    }
    container.innerHTML = filtered.map(g => renderGoalCard(g, false)).join('');
  }

  function onGoalTypeChange(goalType) {
    const targetField = document.getElementById('goal-target-field');
    const unitInput = document.getElementById('goal-unit-input');
    if (goalType === 'qualitativa') {
      if (targetField) targetField.style.display = 'none';
      if (unitInput && unitInput.value === 'R$') unitInput.value = 'sessões';
    } else {
      if (targetField) targetField.style.display = 'block';
      if (unitInput) unitInput.value = goalType === 'monetaria' ? 'R$' : 'pomodoros';
    }
  }

  function openGoalModal(goalId = null) {
    const modal = document.getElementById('modal-goal');
    const form = document.getElementById('form-goal');
    const titleEl = document.getElementById('modal-goal-title');
    form.reset();

    if (goalId) {
      const g = state.goals.find(x => x.id === goalId);
      if (g) {
        titleEl.innerText = 'Editar Meta';
        document.getElementById('goal-id').value = g.id;
        document.getElementById('goal-title-input').value = g.title;
        document.getElementById('goal-desc-input').value = g.description || '';
        document.getElementById('goal-category-select').value = g.category;
        document.getElementById('goal-type-select').value = g.goal_type;
        document.getElementById('goal-current-input').value = g.current_value || 0;
        document.getElementById('goal-target-input').value = g.target_value || '';
        document.getElementById('goal-unit-input').value = g.unit || 'R$';
        document.getElementById('goal-deadline-input').value = g.deadline || '';
        document.getElementById('goal-status-select').value = g.status;
        onGoalTypeChange(g.goal_type);
      }
    } else {
      titleEl.innerText = 'Nova Meta';
      document.getElementById('goal-id').value = '';
      document.getElementById('goal-type-select').value = 'monetaria';
      onGoalTypeChange('monetaria');
    }
    modal.classList.add('active');
  }

  async function saveGoal(e) {
    e.preventDefault();
    const id = document.getElementById('goal-id').value;
    const goalType = document.getElementById('goal-type-select').value;
    const targetRaw = document.getElementById('goal-target-input').value;

    const payload = {
      title: document.getElementById('goal-title-input').value.trim(),
      description: document.getElementById('goal-desc-input').value.trim(),
      category: document.getElementById('goal-category-select').value,
      goal_type: goalType,
      current_value: parseFloat(document.getElementById('goal-current-input').value || '0'),
      target_value: goalType === 'qualitativa' ? null : (targetRaw ? parseFloat(targetRaw) : null),
      unit: document.getElementById('goal-unit-input').value.trim() || 'R$',
      deadline: document.getElementById('goal-deadline-input').value || null,
      status: document.getElementById('goal-status-select').value
    };

    try {
      if (id) {
        await apiFetch(`/api/goals/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/goals', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeModals();
      showToast('🎯 Meta salva!');
      await loadGoalsData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao salvar meta');
    }
  }

  async function promptGoalProgress(goalId, goalType) {
    const label = goalType === 'monetaria' ? 'Informe o valor a somar na meta (R$):' : 'Informe a quantidade a somar no progresso:';
    const val = prompt(label, goalType === 'monetaria' ? '100' : '1');
    if (val === null) return;
    const delta = parseFloat(val.replace(',', '.'));
    if (isNaN(delta)) return;
    try {
      await apiFetch(`/api/goals/${goalId}/progress`, {
        method: 'PATCH',
        body: JSON.stringify({ delta })
      });
      showToast('🎯 Progresso da meta atualizado!');
      await loadGoalsData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao atualizar progresso');
    }
  }

  async function completeGoal(goalId) {
    try {
      await apiFetch(`/api/goals/${goalId}/progress`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'alcancada', delta: 0 })
      });
      showToast('🏆 Parabéns! Meta alcançada!');
      await loadGoalsData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao concluir meta');
    }
  }

  async function deleteGoal(goalId) {
    if (!confirm('Deseja realmente excluir esta meta?')) return;
    try {
      await apiFetch(`/api/goals/${goalId}`, { method: 'DELETE' });
      showToast('🗑 Meta excluída');
      await loadGoalsData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir meta');
    }
  }

  // ---------------- PONTO 3: NOTES / KNOWLEDGE BASE MODULE ([RF04], Section 6.3) ----------------
  async function loadNotesData() {
    try {
      const notes = await apiFetch('/api/notes');
      state.notes = notes;
      renderNotesFolderBar();
      renderNotes();
    } catch (e) {
      showError('notes-list-container', 'Falha ao carregar anotações.', () => loadNotesData());
    }
  }

  function renderNotesFolderBar() {
    const bar = document.getElementById('notes-folder-bar');
    if (!bar) return;
    const folders = Array.from(new Set(['Geral', ...(state.notes || []).map(n => n.folder || 'Geral')]));
    bar.innerHTML = [
      `<button class="stage-pill ${state.notesFolderFilter === 'all' ? 'active' : ''}" onclick="App.filterNotesByFolder('all', this)">📁 Todos (${state.notes.length})</button>`,
      ...folders.map(f => {
        const active = state.notesFolderFilter === f ? 'active' : '';
        return `<button class="stage-pill ${active}" onclick="App.filterNotesByFolder('${escapeHtml(f)}', this)">📓 ${escapeHtml(f)}</button>`;
      })
    ].join('');
  }

  function filterNotesByFolder(folder, btnEl) {
    state.notesFolderFilter = folder;
    renderNotesFolderBar();
    renderNotes();
  }

  function searchNotesClientSide(query) {
    state.notesSearchQuery = (query || '').trim().toLowerCase();
    renderNotes();
  }

  function renderNotes() {
    const container = document.getElementById('notes-list-container');
    if (!container) return;

    let filtered = state.notes || [];
    if (state.notesFolderFilter !== 'all') {
      filtered = filtered.filter(n => (n.folder || 'Geral') === state.notesFolderFilter);
    }
    if (state.notesSearchQuery) {
      const q = state.notesSearchQuery;
      filtered = filtered.filter(n =>
        (n.title || '').toLowerCase().includes(q) ||
        (n.content || '').toLowerCase().includes(q) ||
        (n.folder || '').toLowerCase().includes(q) ||
        (n.tags || '').toLowerCase().includes(q)
      );
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📓</div>
          <div class="empty-title">Nenhuma anotação neste caderno</div>
          <div class="empty-desc">Crie resumos de estudo, documentações em Markdown, listas ou guias técnicos perenes.</div>
          <button class="btn btn-notes" onclick="App.openNoteModal()">+ Nova Anotação</button>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(n => {
      const tags = (n.tags || '').split(',').map(t => t.trim()).filter(Boolean);
      const attCount = Number(n.attachments_count || 0);
      return `
        <div class="note-card ${n.is_pinned ? 'pinned' : ''}">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; margin-bottom:8px;">
            <div>
              <span class="badge badge-medium" style="margin-bottom:4px;">📓 ${escapeHtml(n.folder || 'Geral')}</span>
              ${n.is_pinned ? `<span class="badge badge-high" style="margin-bottom:4px;">📌 Fixada</span>` : ''}
              <h4 class="idea-title">${escapeHtml(n.title)}</h4>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="App.openNoteModal(${n.id}, 'preview')">👁 Ler</button>
          </div>
          <div class="markdown-body" style="max-height:140px; overflow:hidden; margin-bottom:10px; opacity:0.9;">
            ${renderMarkdown((n.content || '').slice(0, 360))}
          </div>
          ${tags.length > 0 ? `
            <div class="idea-tags">
              ${tags.map(t => `<span class="tag-badge">#${escapeHtml(t.replace(/^#/, ''))}</span>`).join('')}
            </div>
          ` : ''}
          <div class="task-actions">
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <button class="btn btn-secondary btn-sm" onclick="App.openNoteModal(${n.id}, 'edit')">✎ Editar</button>
              <button class="btn btn-secondary btn-sm" onclick="App.openAttachmentsModal('note', ${n.id}, '${escapeHtml(n.title)}')">📎 Anexos (${attCount})</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteNote(${n.id})">🗑</button>
            </div>
            <span style="font-size:0.7rem; color:var(--text-muted);">${formatDate(n.updated_at)}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function setNoteModalMode(mode) {
    const editPane = document.getElementById('note-editor-pane');
    const prevPane = document.getElementById('note-preview-pane');
    const rendered = document.getElementById('note-markdown-rendered');

    document.getElementById('btn-note-edit-mode')?.classList.toggle('active', mode === 'edit');
    document.getElementById('btn-note-preview-mode')?.classList.toggle('active', mode === 'preview');

    if (mode === 'preview') {
      editPane.style.display = 'none';
      prevPane.style.display = 'block';
      const md = document.getElementById('note-content-input').value;
      rendered.innerHTML = renderMarkdown(md);
    } else {
      editPane.style.display = 'block';
      prevPane.style.display = 'none';
    }
  }

  function openNoteModal(noteId = null, initialMode = 'edit') {
    const modal = document.getElementById('modal-note');
    const form = document.getElementById('form-note');
    const titleEl = document.getElementById('modal-note-title');
    form.reset();

    if (noteId) {
      const n = state.notes.find(x => x.id === noteId);
      if (n) {
        titleEl.innerText = n.title;
        document.getElementById('note-id').value = n.id;
        document.getElementById('note-title-input').value = n.title;
        document.getElementById('note-folder-input').value = n.folder || 'Geral';
        document.getElementById('note-tags-input').value = n.tags || '';
        document.getElementById('note-pinned-check').checked = Boolean(n.is_pinned);
        document.getElementById('note-content-input').value = n.content || '';
      }
    } else {
      titleEl.innerText = 'Nova Anotação';
      document.getElementById('note-id').value = '';
      document.getElementById('note-folder-input').value = state.notesFolderFilter !== 'all' ? state.notesFolderFilter : 'Geral';
      initialMode = 'edit';
    }
    setNoteModalMode(initialMode);
    modal.classList.add('active');
  }

  async function saveNote(e) {
    e.preventDefault();
    const id = document.getElementById('note-id').value;
    const payload = {
      title: document.getElementById('note-title-input').value.trim(),
      folder: document.getElementById('note-folder-input').value.trim() || 'Geral',
      tags: document.getElementById('note-tags-input').value.trim(),
      is_pinned: document.getElementById('note-pinned-check').checked ? 1 : 0,
      content: document.getElementById('note-content-input').value
    };

    try {
      if (id) {
        await apiFetch(`/api/notes/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/notes', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeModals();
      showToast('📓 Anotação salva!');
      await loadNotesData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao salvar anotação');
    }
  }

  async function deleteNote(noteId) {
    if (!confirm('Deseja excluir esta anotação e seus anexos vinculados?')) return;
    try {
      await apiFetch(`/api/notes/${noteId}`, { method: 'DELETE' });
      showToast('🗑 Anotação excluída');
      await loadNotesData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir anotação');
    }
  }

  // ---------------- TASKS MODULE ----------------
  async function loadTasksData() {
    try {
      const tasks = await apiFetch('/api/tasks');
      state.tasks = tasks;
      renderTasks();
      populateTaskSelectors();
    } catch (err) {
      showError('tasks-kanban-container', 'Falha ao carregar tarefas.', () => loadTasksData());
    }
  }

  function setTaskMode(mode) {
    state.taskMode = mode;
    document.getElementById('btn-kanban-mode').classList.toggle('active', mode === 'kanban');
    document.getElementById('btn-list-mode').classList.toggle('active', mode === 'list');
    document.getElementById('tasks-kanban-container').style.display = mode === 'kanban' ? 'grid' : 'none';
    document.getElementById('tasks-flat-container').style.display = mode === 'list' ? 'block' : 'none';
    renderTasks();
  }

  function filterTasks(type, val, btnEl) {
    state.taskPriorityFilter = val;
    if (btnEl) {
      document.querySelectorAll('#task-filter-bar .stage-pill').forEach(b => b.classList.remove('active'));
      btnEl.classList.add('active');
    }
    renderTasks();
  }

  function searchTasksClientSide(query) {
    state.taskSearchQuery = (query || '').trim().toLowerCase();
    renderTasks();
  }

  function renderTasks() {
    let filtered = state.tasks;
    if (state.taskPriorityFilter === 'recurring') {
      filtered = filtered.filter(t => t.recurrence && t.recurrence !== 'nenhuma');
    } else if (state.taskPriorityFilter !== 'all') {
      filtered = filtered.filter(t => t.priority === state.taskPriorityFilter);
    }

    if (state.taskSearchQuery) {
      const q = state.taskSearchQuery;
      filtered = filtered.filter(t =>
        (t.title || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
      );
    }

    if (state.taskMode === 'kanban') {
      const cols = { todo: [], in_progress: [], done: [] };
      filtered.forEach(t => {
        if (cols[t.status]) cols[t.status].push(t);
        else cols.todo.push(t);
      });

      ['todo', 'in_progress', 'done'].forEach(col => {
        const countEl = document.getElementById(`count-${col}`);
        const listEl = document.getElementById(`tasks-list-${col}`);
        if (countEl) countEl.innerText = cols[col].length;

        if (cols[col].length === 0) {
          listEl.innerHTML = `
            <div class="empty-state" style="padding:16px 8px;">
              <div class="empty-desc" style="margin-bottom:0;">Vazio</div>
            </div>
          `;
        } else {
          listEl.innerHTML = cols[col].map(renderTaskCard).join('');
        }
      });
    } else {
      const container = document.getElementById('tasks-flat-container');
      if (filtered.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">✓</div>
            <div class="empty-title">Nenhuma tarefa encontrada</div>
            <div class="empty-desc">Crie uma nova tarefa ou altere os filtros acima.</div>
            <button class="btn btn-tasks" onclick="App.openTaskModal()">+ Nova Tarefa</button>
          </div>
        `;
      } else {
        container.innerHTML = filtered.map(renderTaskCard).join('');
      }
    }
  }

  function renderTaskCard(t) {
    const nextStatus = t.status === 'todo' ? 'in_progress' : (t.status === 'in_progress' ? 'done' : 'todo');
    const nextLabel = t.status === 'todo' ? 'Iniciar' : (t.status === 'in_progress' ? 'Concluir' : 'Reabrir');
    const hasRec = t.recurrence && t.recurrence !== 'nenhuma';
    const attCount = Number(t.attachments_count || 0);

    return `
      <div class="task-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <h4 class="task-title">${escapeHtml(t.title)}</h4>
          <div style="display:flex; gap:4px; align-items:center; flex-shrink:0;">
            ${hasRec ? `<span class="badge badge-recurring">🔁 ${escapeHtml(t.recurrence)}</span>` : ''}
            <span class="badge badge-${t.priority}">${t.priority}</span>
          </div>
        </div>
        ${t.description ? `<p style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:8px;">${escapeHtml(t.description)}</p>` : ''}
        <div class="task-meta">
          <span>📁 ${escapeHtml(t.category)}</span>
          ${t.due_date ? `<span>📅 ${formatDate(t.due_date)}</span>` : ''}
          <span>🍅 ${t.completed_pomodoros}/${t.estimated_pomodoros} (${t.pomodoro_duration_minutes || 25}m)</span>
        </div>
        <div class="task-actions">
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" onclick="App.openTaskModal(${t.id})">Editar</button>
            <button class="btn btn-secondary btn-sm" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">⏱ Focar</button>
            <button class="btn btn-secondary btn-sm" onclick="App.openAttachmentsModal('task', ${t.id}, '${escapeHtml(t.title)}')">📎 (${attCount})</button>
            <button class="btn btn-danger btn-sm" title="Excluir tarefa" onclick="App.deleteTask(${t.id})">🗑</button>
          </div>
          <button class="btn btn-sm ${t.status === 'in_progress' ? 'btn-tasks' : 'btn-secondary'}" onclick="App.updateTaskStatus(${t.id}, '${nextStatus}')">${nextLabel}</button>
        </div>
      </div>
    `;
  }

  async function updateTaskStatus(id, newStatus) {
    try {
      const updated = await apiFetch(`/api/tasks/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus })
      });
      if (updated.next_recurring_task) {
        showToast(`🔁 Tarefa concluída! Próxima criada para ${formatDate(updated.next_recurring_task.due_date)}`);
      } else if (newStatus === 'done') {
        showToast('✓ Tarefa concluída!');
      }
      await loadTasksData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao atualizar status da tarefa');
    }
  }

  async function deleteTask(taskId) {
    if (!confirm('Deseja realmente excluir esta tarefa?')) return;
    try {
      await apiFetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
      showToast('🗑 Tarefa excluída');
      await loadTasksData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir tarefa: ' + (e.message || 'Falha na requisição'));
    }
  }

  async function deleteCurrentModalTask() {
    const id = document.getElementById('task-id').value;
    if (!id) return;
    closeModals();
    await deleteTask(parseInt(id, 10));
  }

  function openTaskModal(taskId = null) {
    const modal = document.getElementById('modal-task');
    const titleEl = document.getElementById('modal-task-title');
    const deleteBtn = document.getElementById('btn-delete-task-modal');
    const form = document.getElementById('form-task');
    form.reset();
    populateGoalSelectors();

    if (taskId) {
      const task = state.tasks.find(t => t.id === taskId);
      if (task) {
        titleEl.innerText = 'Editar Tarefa';
        if (deleteBtn) deleteBtn.style.display = 'inline-flex';
        document.getElementById('task-id').value = task.id;
        document.getElementById('task-title-input').value = task.title;
        document.getElementById('task-desc-input').value = task.description || '';
        document.getElementById('task-priority-select').value = task.priority;
        document.getElementById('task-status-select').value = task.status;
        document.getElementById('task-due-input').value = task.due_date || '';
        document.getElementById('task-recurrence-select').value = task.recurrence || 'nenhuma';
        document.getElementById('task-pomodoros-input').value = task.estimated_pomodoros || 1;
        document.getElementById('task-duration-input').value = task.pomodoro_duration_minutes || 25;
        document.getElementById('task-category-input').value = task.category || 'Geral';
        const goalSel = document.getElementById('task-goal-select');
        if (goalSel) goalSel.value = task.goal_id || '';
      }
    } else {
      titleEl.innerText = 'Nova Tarefa';
      if (deleteBtn) deleteBtn.style.display = 'none';
      document.getElementById('task-id').value = '';
      document.getElementById('task-status-select').value = 'todo';
      document.getElementById('task-priority-select').value = 'medium';
      document.getElementById('task-recurrence-select').value = 'nenhuma';
      document.getElementById('task-pomodoros-input').value = 1;
      document.getElementById('task-duration-input').value = 25;
    }
    modal.classList.add('active');
  }

  async function saveTask(e) {
    e.preventDefault();
    const id = document.getElementById('task-id').value;
    const goalId = document.getElementById('task-goal-select')?.value || null;
    const payload = {
      title: document.getElementById('task-title-input').value.trim(),
      description: document.getElementById('task-desc-input').value.trim(),
      priority: document.getElementById('task-priority-select').value,
      status: document.getElementById('task-status-select').value,
      due_date: document.getElementById('task-due-input').value || null,
      recurrence: document.getElementById('task-recurrence-select').value || 'nenhuma',
      estimated_pomodoros: parseInt(document.getElementById('task-pomodoros-input').value) || 1,
      pomodoro_duration_minutes: parseInt(document.getElementById('task-duration-input').value) || 25,
      category: document.getElementById('task-category-input').value.trim() || 'Geral',
      goal_id: goalId ? parseInt(goalId, 10) : null
    };

    try {
      if (id) {
        const res = await apiFetch(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
        if (res.next_recurring_task) {
          showToast(`🔁 Próxima tarefa recorrente agendada para ${formatDate(res.next_recurring_task.due_date)}`);
        }
      } else {
        await apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
        showToast('✓ Tarefa salva!');
      }
      closeModals();
      await loadTasksData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao salvar tarefa');
    }
  }

  // ---------------- TIME / POMODORO MODULE ----------------
  function populateTaskSelectors() {
    const activeTasks = state.tasks.filter(t => t.status !== 'done' && t.status !== 'archived');

    const timerSel = document.getElementById('timer-task-select');
    if (timerSel) {
      const currentVal = timerSel.value;
      timerSel.innerHTML = '<option value="">(Nenhuma tarefa selecionada)</option>' +
        activeTasks.map(t => `
          <option value="${t.id}">${escapeHtml(t.title)} (${t.completed_pomodoros}/${t.estimated_pomodoros}🍅 • ${t.pomodoro_duration_minutes || 25}m)</option>
        `).join('');
      timerSel.value = currentVal;
    }

    const finSel = document.getElementById('fin-task-select');
    if (finSel) {
      const currentFinVal = finSel.value;
      finSel.innerHTML = '<option value="">(Nenhuma tarefa)</option>' +
        state.tasks.map(t => `
          <option value="${t.id}">${escapeHtml(t.title)} (${escapeHtml(t.category || 'Geral')})</option>
        `).join('');
      finSel.value = currentFinVal;
    }
  }

  function setCustomFocusDuration(minutes) {
    minutes = Math.max(1, Math.min(180, parseInt(minutes) || 25));
    state.timer.focusMinutes = minutes;
    state.timer.durations.focus = minutes * 60;

    const presets = [15, 25, 45, 50, 60];
    presets.forEach(p => {
      const el = document.getElementById(`dur-pill-${p}`);
      if (el) el.classList.toggle('active', p === minutes);
    });
    const customPill = document.getElementById('dur-pill-custom');
    if (customPill) {
      const isCustom = !presets.includes(minutes);
      customPill.classList.toggle('active', isCustom);
      customPill.innerText = isCustom ? `${minutes}m ✎` : 'Outro ✎';
    }

    if (state.timer.mode === 'focus' && !state.timer.isRunning) {
      state.timer.remainingSeconds = state.timer.durations.focus;
      updateTimerDisplay();
    }
  }

  function promptCustomDuration() {
    const res = prompt('Digite o tempo de foco em minutos (1 a 180):', state.timer.focusMinutes);
    if (res !== null) {
      const num = parseInt(res, 10);
      if (!isNaN(num) && num >= 1 && num <= 180) {
        setCustomFocusDuration(num);
      } else {
        alert('Por favor, informe um tempo válido entre 1 e 180 minutos.');
      }
    }
  }

  function adjustTimerDuration(deltaMinutes) {
    if (state.timer.isRunning) {
      const newSec = state.timer.remainingSeconds + deltaMinutes * 60;
      if (newSec >= 60) {
        state.timer.remainingSeconds = newSec;
        state.timer.endTime = Date.now() + newSec * 1000;
        updateTimerDisplay();
      }
    } else {
      if (state.timer.mode === 'focus') {
        setCustomFocusDuration(state.timer.focusMinutes + deltaMinutes);
      } else {
        const currentSec = state.timer.durations[state.timer.mode];
        const newSec = Math.max(60, currentSec + deltaMinutes * 60);
        state.timer.durations[state.timer.mode] = newSec;
        state.timer.remainingSeconds = newSec;
        updateTimerDisplay();
      }
    }
  }

  function onTaskSelectedForTimer(taskId) {
    const badge = document.getElementById('timer-task-duration-badge');
    if (!taskId) {
      state.timer.selectedTaskId = null;
      if (badge) badge.innerText = '';
      return;
    }

    const task = state.tasks.find(t => t.id === parseInt(taskId));
    if (task) {
      state.timer.selectedTaskId = task.id;
      const taskDur = task.pomodoro_duration_minutes || 25;
      setCustomFocusDuration(taskDur);
      if (badge) badge.innerText = `⏱ ${taskDur}m da tarefa`;
    }
  }

  function startFocusForTask(taskId, taskTitle) {
    navigateTo('time');
    setTimerMode('focus');
    const sel = document.getElementById('timer-task-select');
    if (sel) {
      sel.value = taskId;
      onTaskSelectedForTimer(taskId);
    }
    toggleTimer(true);
  }

  function setTimerMode(mode) {
    if (state.timer.isRunning) resetTimer();
    state.timer.mode = mode;
    state.timer.remainingSeconds = state.timer.durations[mode];

    document.querySelectorAll('.timer-mode-btn').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById(`btn-mode-${mode === 'focus' ? 'focus' : (mode === 'short_break' ? 'short' : 'long')}`);
    if (btn) btn.classList.add('active');

    const focusBar = document.getElementById('focus-durations-bar');
    if (focusBar) {
      focusBar.style.display = mode === 'focus' ? 'flex' : 'none';
    }

    updateTimerDisplay();
  }

  function updateTimerDisplay() {
    const min = Math.floor(state.timer.remainingSeconds / 60);
    const sec = state.timer.remainingSeconds % 60;
    const str = `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    const display = document.getElementById('timer-display');
    if (display) display.innerText = str;
    document.title = state.timer.isRunning ? `(${str}) Dream Hub` : 'Dream Hub v1.2';
  }

  function syncTimerFromTimestamp() {
    if (!state.timer.isRunning || !state.timer.endTime) return;
    const diffSec = Math.max(0, Math.ceil((state.timer.endTime - Date.now()) / 1000));
    state.timer.remainingSeconds = diffSec;
    updateTimerDisplay();
    if (diffSec <= 0) {
      completeTimerSession();
    }
  }

  function toggleTimer(forceStart = false) {
    const btn = document.getElementById('btn-timer-toggle');
    if (state.timer.isRunning && !forceStart) {
      syncTimerFromTimestamp();
      clearInterval(state.timer.intervalId);
      state.timer.isRunning = false;
      state.timer.endTime = null;
      btn.innerText = 'Continuar Foco';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-time');
    } else {
      if (!state.timer.startTime) state.timer.startTime = new Date().toISOString();
      state.timer.endTime = Date.now() + state.timer.remainingSeconds * 1000;
      state.timer.isRunning = true;
      btn.innerText = 'Pausar';
      btn.classList.remove('btn-time');
      btn.classList.add('btn-danger');

      clearInterval(state.timer.intervalId);
      state.timer.intervalId = setInterval(syncTimerFromTimestamp, 500);
    }
  }

  function resetTimer() {
    clearInterval(state.timer.intervalId);
    state.timer.isRunning = false;
    state.timer.startTime = null;
    state.timer.endTime = null;
    state.timer.remainingSeconds = state.timer.durations[state.timer.mode];
    const btn = document.getElementById('btn-timer-toggle');
    if (btn) {
      btn.innerText = 'Iniciar Foco';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-time');
    }
    updateTimerDisplay();
  }

  async function completeTimerSession() {
    const startedIso = state.timer.startTime || new Date().toISOString();
    const modeCompleted = state.timer.mode;
    const durationMin = Math.round(state.timer.durations[modeCompleted] / 60);
    resetTimer();
    playCompletionChime();

    const taskId = document.getElementById('timer-task-select')?.value || null;

    try {
      await apiFetch('/api/time/sessions', {
        method: 'POST',
        body: JSON.stringify({
          task_id: taskId ? parseInt(taskId) : null,
          session_type: modeCompleted,
          duration_minutes: durationMin,
          started_at: startedIso,
          ended_at: new Date().toISOString(),
          completed: 1,
          notes: ''
        })
      });
      loadTimeData();
      loadOverviewData();
      loadTasksData();
      showToast('🎉 Ciclo Pomodoro concluído e creditado!');
    } catch (e) {
      console.error('Falha ao registrar sessão:', e);
    }
  }

  async function loadTimeData() {
    try {
      const sessions = await apiFetch('/api/time/sessions?limit=20');
      const listEl = document.getElementById('time-sessions-list');
      if (sessions.length === 0) {
        listEl.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">⏱</div>
            <div class="empty-title">Nenhum foco registrado hoje</div>
            <div class="empty-desc">Inicie um Pomodoro acima para cronometrar seu tempo de trabalho.</div>
          </div>
        `;
      } else {
        listEl.innerHTML = sessions.map(s => `
          <div class="transaction-item">
            <div class="txn-left">
              <span class="txn-desc">${s.session_type === 'focus' ? '🎯 Foco' : '☕ Pausa'} ${s.task_title ? `- ${escapeHtml(s.task_title)}` : ''}</span>
              <span class="txn-sub">${new Date(s.started_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} • ${s.duration_minutes} minutos</span>
            </div>
            <span class="badge ${s.session_type === 'focus' ? 'badge-high' : 'badge-low'}">Concluído</span>
          </div>
        `).join('');
      }
    } catch (e) {
      showError('time-sessions-list', 'Falha ao carregar sessões.', () => loadTimeData());
    }
  }

  // ---------------- PONTO 4: FINANCE SUB-TABS, RECURRING RULES & PROJECTION ([RF05], [RF06], [RF07]) ----------------
  function setFinanceSubTab(subTab) {
    state.financeSubTab = subTab;
    ['extrato', 'recorrencias', 'projecao'].forEach(t => {
      document.getElementById(`fin-tab-${t}`)?.classList.toggle('active', t === subTab);
      const view = document.getElementById(`fin-subview-${t}`);
      if (view) view.style.display = t === subTab ? 'block' : 'none';
    });

    if (subTab === 'recorrencias') loadRecurringRules();
    else if (subTab === 'projecao') loadFinanceProjection();
    else loadFinanceData();
  }

  function setTxnType(type) {
    state.txnType = type;
    document.getElementById('btn-txn-expense').classList.toggle('active', type === 'expense');
    document.getElementById('btn-txn-income').classList.toggle('active', type === 'income');
  }

  function openFinanceModal(defaultRecurring = false) {
    const modal = document.getElementById('modal-finance');
    const form = document.getElementById('form-finance');
    form.reset();
    setTxnType('expense');
    document.getElementById('fin-date-input').value = new Date().toISOString().slice(0, 10);
    const recCheck = document.getElementById('fin-recurring-check');
    const freqWrap = document.getElementById('fin-recurrence-freq-wrap');
    if (recCheck) recCheck.checked = Boolean(defaultRecurring);
    if (freqWrap) freqWrap.style.display = defaultRecurring ? 'block' : 'none';
    populateTaskSelectors();
    populateGoalSelectors();
    modal.classList.add('active');
  }

  async function saveTransaction(e) {
    e.preventDefault();
    const amountVal = parseFloat(document.getElementById('fin-amount-input').value);
    const isRec = document.getElementById('fin-recurring-check')?.checked || false;
    const recFreq = isRec ? (document.getElementById('fin-recurrence-select')?.value || 'mensal') : 'nenhuma';
    const linkedTaskId = document.getElementById('fin-task-select')?.value || null;
    const linkedGoalId = document.getElementById('fin-goal-select')?.value || null;

    const payload = {
      description: document.getElementById('fin-desc-input').value.trim(),
      amount_cents: Math.round(amountVal * 100),
      type: state.txnType,
      category: document.getElementById('fin-category-select').value,
      account: document.getElementById('fin-account-select').value,
      date: document.getElementById('fin-date-input').value,
      task_id: linkedTaskId ? parseInt(linkedTaskId, 10) : null,
      goal_id: linkedGoalId ? parseInt(linkedGoalId, 10) : null,
      is_settled: 1,
      is_recurring: isRec ? 1 : 0,
      recurrence: recFreq
    };

    try {
      await apiFetch('/api/finance/transactions', { method: 'POST', body: JSON.stringify(payload) });
      closeModals();
      showToast(isRec ? '🔁 Regra fixa e lançamento registrados!' : '💰 Lançamento salvo!');
      await loadFinanceData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao registrar transação');
    }
  }

  function searchFinanceClientSide(query) {
    state.financeSearchQuery = (query || '').trim().toLowerCase();
    renderTransactionsList();
  }

  function filterFinance(filterType, btnEl) {
    state.financeFilter = filterType;
    if (btnEl) {
      document.querySelectorAll('#finance-filter-bar .stage-pill').forEach(b => b.classList.remove('active'));
      btnEl.classList.add('active');
    }
    renderTransactionsList();
  }

  async function loadFinanceData() {
    const monthInput = document.getElementById('finance-month-input');
    if (monthInput && !monthInput.value) {
      monthInput.value = state.financeMonth;
    }
    const selectedMonth = monthInput ? monthInput.value : state.financeMonth;

    try {
      const summary = await apiFetch(`/api/finance/summary?month=${selectedMonth}`);
      document.getElementById('fin-net-balance').innerText = formatMoney(summary.net_balance_cents);
      document.getElementById('fin-net-balance').style.color = summary.net_balance_cents >= 0 ? 'var(--text-primary)' : 'var(--accent-expense)';
      document.getElementById('fin-total-income').innerText = formatMoney(summary.total_income_cents);
      document.getElementById('fin-total-expense').innerText = formatMoney(summary.total_expense_cents);

      const recIncSub = document.getElementById('fin-rec-income-sub');
      const recExpSub = document.getElementById('fin-rec-expense-sub');
      if (recIncSub) recIncSub.innerText = `🔁 Fixos: ${formatMoney(summary.recurring_income_cents || 0)}`;
      if (recExpSub) recExpSub.innerText = `🔁 Fixos: ${formatMoney(summary.recurring_expense_cents || 0)}`;

      state.recurringRules = summary.recurring_rules || [];

      const breakdownCard = document.getElementById('finance-breakdown-card');
      const breakdownList = document.getElementById('fin-categories-list');
      const cats = Object.entries(summary.categories_breakdown || {});
      if (cats.length > 0) {
        breakdownCard.style.display = 'block';
        breakdownList.innerHTML = cats.map(([cat, val]) => `
          <div style="display:flex; justify-content:space-between; font-size:0.875rem;">
            <span style="color:var(--text-secondary);">${escapeHtml(cat)}</span>
            <span style="font-family:var(--font-mono); font-weight:600;">${formatMoney(val)}</span>
          </div>
        `).join('');
      } else {
        breakdownCard.style.display = 'none';
      }

      const txns = await apiFetch(`/api/finance/transactions?month=${selectedMonth}`);
      state.transactions = txns;
      renderTransactionsList();
    } catch (e) {
      showError('finance-transactions-list', 'Falha ao carregar extrato.', () => loadFinanceData());
    }
  }

  function renderTransactionsList() {
    const listEl = document.getElementById('finance-transactions-list');
    if (!listEl) return;

    let filtered = state.transactions || [];
    if (state.financeFilter === 'recurring') {
      filtered = filtered.filter(t => Number(t.is_recurring) === 1);
    } else if (state.financeFilter === 'income' || state.financeFilter === 'expense') {
      filtered = filtered.filter(t => t.type === state.financeFilter);
    }

    if (state.financeSearchQuery) {
      const q = state.financeSearchQuery;
      filtered = filtered.filter(t =>
        (t.description || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q) ||
        (t.account || '').toLowerCase().includes(q) ||
        (t.task_title || '').toLowerCase().includes(q)
      );
    }

    if (filtered.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">💰</div>
          <div class="empty-title">Nenhuma movimentação encontrada</div>
          <div class="empty-desc">Adicione receitas, depósitos ou despesas usando o botão acima.</div>
          <button class="btn btn-finance" onclick="App.openFinanceModal()">+ Novo Lançamento</button>
        </div>
      `;
      return;
    }

    listEl.innerHTML = filtered.map(t => {
      const attCount = Number(t.attachments_count || 0);
      return `
        <div class="transaction-item">
          <div class="txn-left">
            <span class="txn-desc">
              ${escapeHtml(t.description)}
              ${Number(t.is_recurring) === 1 ? `<span class="badge badge-recurring">🔁 ${escapeHtml(t.recurrence || 'mensal')}</span>` : ''}
            </span>
            <span class="txn-sub">
              📅 ${formatDate(t.date)} • ${escapeHtml(t.category)} • ${escapeHtml(t.account)}
              ${t.task_title ? ` • 🔗 ${escapeHtml(t.task_title)}` : ''}
              ${t.goal_title ? ` • 🎯 ${escapeHtml(t.goal_title)}` : ''}
            </span>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="txn-amount ${t.type === 'income' ? 'flow-income' : 'flow-expense'}">
              ${t.type === 'income' ? '+' : '-'} ${formatMoney(t.amount_cents)}
            </span>
            <button class="btn btn-secondary btn-sm" style="min-height:36px; padding:2px 8px;" title="Comprovantes e Anexos" onclick="App.openAttachmentsModal('transaction', ${t.id}, '${escapeHtml(t.description)}')">📎 (${attCount})</button>
            <button class="btn btn-danger btn-sm" style="min-height:36px; min-width:36px; padding:2px 8px;" title="Excluir lançamento" onclick="App.deleteTransaction(${t.id})">&times;</button>
          </div>
        </div>
      `;
    }).join('');
  }

  // --- Recurring Rules Engine ([RF05], [RF06], RN03) ---
  async function loadRecurringRules() {
    const el = document.getElementById('fin-rules-list');
    if (!el) return;
    try {
      const rules = await apiFetch('/api/finance/recurring-rules');
      state.recurringRules = rules;
      if (rules.length === 0) {
        el.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">🔁</div>
            <div class="empty-title">Nenhuma regra fixa cadastrada</div>
            <div class="empty-desc">Cadastre contas fixas (aluguel, internet) ou depósitos recorrentes (salário) para vê-los com antecedência todo mês.</div>
            <button class="btn btn-finance" onclick="App.openRecurringRuleModal()">+ Nova Regra Fixa</button>
          </div>
        `;
        return;
      }

      el.innerHTML = rules.map(r => {
        const isInc = r.type === 'receita';
        const isActive = Number(r.is_active) === 1;
        const amtCents = r.amount_cents || Math.round(Number(r.amount || 0) * 100);
        return `
          <div class="transaction-item" style="${!isActive ? 'opacity:0.6;' : ''}">
            <div class="txn-left">
              <span class="txn-desc">
                <span class="badge ${isActive ? 'badge-recurring' : 'badge-paused'}">${isActive ? '🟢 Ativa' : '⏸ Pausada'}</span>
                ${escapeHtml(r.description)}
              </span>
              <span class="txn-sub">
                📅 Todo dia <strong>${r.day_of_month || 1}</strong> • ${escapeHtml(r.frequency || 'mensal')} • ${escapeHtml(r.category || 'Outros')}
              </span>
            </div>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              <span class="txn-amount ${isInc ? 'flow-income' : 'flow-expense'}">
                ${isInc ? '+' : '-'} ${formatMoney(amtCents)}
              </span>
              <button class="btn btn-secondary btn-sm" onclick="App.openRecurringRuleModal(${r.id})">Editar</button>
              <button class="btn btn-secondary btn-sm" onclick="App.toggleRecurringRuleActive(${r.id}, ${!isActive})">${isActive ? 'Pausar' : 'Reativar'}</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteRecurringRule(${r.id})">🗑</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      showError('fin-rules-list', 'Falha ao carregar regras recorrentes.', () => loadRecurringRules());
    }
  }

  function openRecurringRuleModal(ruleId = null) {
    const modal = document.getElementById('modal-recurring-rule');
    const form = document.getElementById('form-recurring-rule');
    const titleEl = document.getElementById('modal-rule-title');
    form.reset();

    if (ruleId) {
      const r = state.recurringRules.find(x => x.id === ruleId);
      if (r) {
        titleEl.innerText = 'Editar Regra Recorrente';
        document.getElementById('rule-id').value = r.id;
        document.getElementById('rule-type-select').value = r.type;
        document.getElementById('rule-desc-input').value = r.description;
        document.getElementById('rule-amount-input').value = r.amount || (r.amount_cents / 100).toFixed(2);
        document.getElementById('rule-day-input').value = r.day_of_month || 1;
        document.getElementById('rule-freq-select').value = r.frequency || 'mensal';
        document.getElementById('rule-category-input').value = r.category || 'Moradia';
      }
    } else {
      titleEl.innerText = 'Nova Regra Recorrente Fixa';
      document.getElementById('rule-id').value = '';
      document.getElementById('rule-day-input').value = new Date().getDate();
    }
    modal.classList.add('active');
  }

  async function saveRecurringRule(e) {
    e.preventDefault();
    const id = document.getElementById('rule-id').value;
    const payload = {
      type: document.getElementById('rule-type-select').value,
      description: document.getElementById('rule-desc-input').value.trim(),
      amount: parseFloat(document.getElementById('rule-amount-input').value),
      day_of_month: parseInt(document.getElementById('rule-day-input').value, 10),
      frequency: document.getElementById('rule-freq-select').value,
      category: document.getElementById('rule-category-input').value.trim() || 'Moradia',
      apply_current_month: document.getElementById('rule-apply-current-check')?.checked || false
    };

    try {
      if (id) {
        await apiFetch(`/api/finance/recurring-rules/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
        showToast('🔁 Regra recorrente atualizada!');
      } else {
        await apiFetch('/api/finance/recurring-rules', { method: 'POST', body: JSON.stringify(payload) });
        showToast('🔁 Nova regra fixa criada!');
      }
      closeModals();
      await loadRecurringRules();
      await loadFinanceData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao salvar regra recorrente');
    }
  }

  async function toggleRecurringRuleActive(ruleId, makeActive) {
    try {
      await apiFetch(`/api/finance/recurring-rules/${ruleId}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: makeActive })
      });
      showToast(makeActive ? '🟢 Regra reativada!' : '⏸ Regra pausada!');
      await loadRecurringRules();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao alterar status da regra');
    }
  }

  async function deleteRecurringRule(ruleId) {
    if (!confirm('Excluir este template recorrente? Os lançamentos passados serão mantidos no histórico.')) return;
    try {
      await apiFetch(`/api/finance/recurring-rules/${ruleId}`, { method: 'DELETE' });
      showToast('🗑 Regra recorrente removida');
      await loadRecurringRules();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir regra');
    }
  }

  // --- Cashflow Projection Simulator ([RF07]: D+30, D+60, D+90) ---
  async function loadFinanceProjection() {
    const container = document.getElementById('fin-projection-container');
    if (!container) return;
    try {
      const data = await apiFetch('/api/finance/projection?months=3');
      const projs = data.projections || [];

      container.innerHTML = `
        <div class="finance-balance-card" style="margin-bottom:14px;">
          <div class="balance-title">Saldo Atual em Caixa (${escapeHtml(data.base_month)})</div>
          <div class="balance-amount" style="margin-bottom:4px;">${formatMoney(data.current_balance_cents)}</div>
        </div>
        ${projs.map(p => `
          <div class="card" style="background:var(--bg-surface-elevated); margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span class="badge badge-recurring">${escapeHtml(p.horizon_label)} • ${escapeHtml(p.month)}</span>
              <span style="font-family:var(--font-mono); font-size:0.875rem; font-weight:700; color:${p.projected_net_cents >= 0 ? 'var(--accent-income)' : 'var(--accent-expense)'};">
                Saldo Mensal: ${p.projected_net_cents >= 0 ? '+' : ''}${formatMoney(p.projected_net_cents)}
              </span>
            </div>
            <div class="balance-flow" style="padding-top:8px; margin-bottom:10px;">
              <div class="flow-col">
                <div class="flow-label">Receitas Previstas (+)</div>
                <div class="flow-val flow-income">${formatMoney(p.projected_income_cents)}</div>
              </div>
              <div class="flow-col">
                <div class="flow-label">Contas Fixas Agendadas (-)</div>
                <div class="flow-val flow-expense">${formatMoney(p.projected_expense_cents)}</div>
              </div>
              <div class="flow-col">
                <div class="flow-label">Saldo Livre Acumulado</div>
                <div class="flow-val" style="color:var(--text-primary);">${formatMoney(p.cumulative_free_balance_cents)}</div>
              </div>
            </div>
            ${p.items && p.items.length > 0 ? `
              <div style="font-size:0.75rem; color:var(--text-secondary); border-top:1px solid var(--border-subtle); padding-top:8px;">
                ${p.items.map(it => `
                  <div style="display:flex; justify-content:space-between; padding:2px 0;">
                    <span>Dia ${it.day_of_month}: ${escapeHtml(it.description)}</span>
                    <span style="font-family:var(--font-mono); color:${it.type === 'receita' ? 'var(--accent-income)' : 'var(--accent-expense)'};">
                      ${it.type === 'receita' ? '+' : '-'}${formatMoney(it.amount_cents)}
                    </span>
                  </div>
                `).join('')}
              </div>
            ` : `<div style="font-size:0.75rem; color:var(--text-muted);">Nenhuma regra ativa projetada.</div>`}
          </div>
        `).join('')}
      `;
    } catch (e) {
      showError('fin-projection-container', 'Falha ao simular projeção.', () => loadFinanceProjection());
    }
  }

  async function deleteTransaction(id) {
    if (!confirm('Deseja realmente remover esta movimentação?')) return;
    try {
      await apiFetch(`/api/finance/transactions/${id}`, { method: 'DELETE' });
      showToast('🗑 Movimentação removida');
      await loadFinanceData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir transação');
    }
  }

  // ---------------- IDEAS MODULE & 1-CLICK TASK CONVERSION ----------------
  async function loadIdeasData() {
    try {
      const ideas = await apiFetch('/api/ideas');
      state.ideas = ideas;
      renderIdeas();
    } catch (e) {
      showError('ideas-list-container', 'Falha ao carregar ideias.', () => loadIdeasData());
    }
  }

  function filterIdeas(stage, btnEl) {
    state.ideaStageFilter = stage;
    if (btnEl) {
      document.querySelectorAll('#view-ideas .stage-pill').forEach(b => b.classList.remove('active'));
      btnEl.classList.add('active');
    }
    renderIdeas();
  }

  function searchIdeas(query) {
    state.ideaSearchQuery = (query || '').trim().toLowerCase();
    renderIdeas();
  }

  function renderIdeas() {
    const container = document.getElementById('ideas-list-container');
    let filtered = state.ideas || [];

    if (state.ideaStageFilter !== 'all') {
      filtered = filtered.filter(i => i.stage === state.ideaStageFilter);
    }
    if (state.ideaSearchQuery) {
      const q = state.ideaSearchQuery;
      filtered = filtered.filter(i =>
        (i.title || '').toLowerCase().includes(q) ||
        (i.content || '').toLowerCase().includes(q) ||
        (i.tags || '').toLowerCase().includes(q)
      );
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">💡</div>
          <div class="empty-title">Nenhuma ideia encontrada</div>
          <div class="empty-desc">Registre insights rápidos na incubadora e converta em tarefas com 1 clique.</div>
          <button class="btn btn-ideas" onclick="App.openIdeaModal()">+ Nova Ideia</button>
        </div>
      `;
      return;
    }

    const stageMap = {
      raw: 'Bruta / Rascunho',
      evaluating: 'Em Análise',
      in_action: 'Em Ação / Convertida',
      archived: 'Arquivada'
    };

    container.innerHTML = filtered.map(i => {
      const tags = (i.tags || '').split(',').map(t => t.trim()).filter(Boolean);
      const isConverted = i.status === 'convertida' || Boolean(i.converted_task_id);
      const attCount = Number(i.attachments_count || 0);
      return `
        <div class="idea-card">
          <div class="idea-header">
            <h4 class="idea-title">${escapeHtml(i.title)}</h4>
            <div style="display:flex; gap:6px; align-items:center;">
              ${isConverted ? `<span class="badge badge-recurring">✓ Tarefa #${i.converted_task_id || ''}</span>` : ''}
              <span class="badge badge-medium">${stageMap[i.stage] || i.stage}</span>
            </div>
          </div>
          ${i.content ? `<div class="idea-content">${escapeHtml(i.content)}</div>` : ''}
          ${tags.length > 0 ? `
            <div class="idea-tags">
              ${tags.map(t => `<span class="tag-badge">#${escapeHtml(t.replace(/^#/, ''))}</span>`).join('')}
            </div>
          ` : ''}
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-top:10px; padding-top:8px; border-top:1px solid var(--border-subtle);">
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              ${!isConverted ? `<button class="btn btn-ideas btn-sm" onclick="App.convertIdeaToTask(${i.id})">⚡ Converter em Tarefa</button>` : ''}
              <button class="btn btn-secondary btn-sm" onclick="App.openIdeaModal(${i.id})">Editar</button>
              <button class="btn btn-secondary btn-sm" onclick="App.openAttachmentsModal('idea', ${i.id}, '${escapeHtml(i.title)}')">📎 (${attCount})</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteIdea(${i.id})">Excluir</button>
            </div>
            <select class="form-select" style="min-height:38px; font-size:0.75rem; width:auto; padding:4px 8px;" onchange="App.changeIdeaStage(${i.id}, this.value)">
              <option value="raw" ${i.stage === 'raw' ? 'selected' : ''}>Bruta</option>
              <option value="evaluating" ${i.stage === 'evaluating' ? 'selected' : ''}>Em Análise</option>
              <option value="in_action" ${i.stage === 'in_action' ? 'selected' : ''}>Em Ação</option>
              <option value="archived" ${i.stage === 'archived' ? 'selected' : ''}>Arquivar</option>
            </select>
          </div>
        </div>
      `;
    }).join('');
  }

  async function convertIdeaToTask(ideaId) {
    try {
      const res = await apiFetch(`/api/ideas/${ideaId}/convert`, {
        method: 'POST',
        body: JSON.stringify({ priority: 'high' })
      });
      showToast(`⚡ Ideia convertida na Tarefa #${res.task.id}!`);
      await loadIdeasData();
      await loadTasksData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao converter ideia em tarefa');
    }
  }

  function openIdeaModal(ideaId = null) {
    const modal = document.getElementById('modal-idea');
    const titleEl = document.getElementById('modal-idea-title');
    const form = document.getElementById('form-idea');
    form.reset();

    if (ideaId) {
      const idea = state.ideas.find(i => i.id === ideaId);
      if (idea) {
        titleEl.innerText = 'Editar Ideia';
        document.getElementById('idea-id').value = idea.id;
        document.getElementById('idea-title-input').value = idea.title;
        document.getElementById('idea-stage-select').value = idea.stage;
        document.getElementById('idea-content-input').value = idea.content || '';
        document.getElementById('idea-tags-input').value = idea.tags || '';
      }
    } else {
      titleEl.innerText = 'Nova Ideia';
      document.getElementById('idea-id').value = '';
      document.getElementById('idea-stage-select').value = 'raw';
    }
    modal.classList.add('active');
  }

  async function saveIdea(e) {
    e.preventDefault();
    const id = document.getElementById('idea-id').value;
    const payload = {
      title: document.getElementById('idea-title-input').value.trim(),
      stage: document.getElementById('idea-stage-select').value,
      content: document.getElementById('idea-content-input').value.trim(),
      tags: document.getElementById('idea-tags-input').value.trim()
    };

    try {
      if (id) {
        await apiFetch(`/api/ideas/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/ideas', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeModals();
      showToast('💡 Ideia salva!');
      await loadIdeasData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao salvar ideia');
    }
  }

  async function changeIdeaStage(id, newStage) {
    try {
      await apiFetch(`/api/ideas/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ stage: newStage })
      });
      await loadIdeasData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao atualizar estágio');
    }
  }

  async function deleteIdea(id) {
    if (!confirm('Deseja realmente remover esta ideia?')) return;
    try {
      await apiFetch(`/api/ideas/${id}`, { method: 'DELETE' });
      showToast('🗑 Ideia excluída');
      await loadIdeasData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir ideia');
    }
  }

  // ---------------- SYSTEM BACKUP & EXPORT ----------------
  function openSystemModal() {
    document.getElementById('modal-system')?.classList.add('active');
  }

  function downloadHotBackup() {
    window.location.href = '/api/system/backup';
    showToast('💾 Gerando snapshot SQLite a quente...');
  }

  function exportData(module = 'all', format = 'csv') {
    window.location.href = `/api/system/export?module=${encodeURIComponent(module)}&format=${encodeURIComponent(format)}`;
    showToast(`⬇ Baixando exportação (${format.toUpperCase()})...`);
  }

  function closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
  }

  function showError(containerId, message, retryFn) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
      <div class="error-state">
        <span>⚠️ ${escapeHtml(message)}</span>
        <button class="btn btn-secondary btn-sm" onclick="(${retryFn.toString()})()">Tentar Novamente</button>
      </div>
    `;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ---------------- INITIALIZATION ----------------
  function init() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
    const headerDate = document.getElementById('header-date');
    if (headerDate) headerDate.innerText = dateStr;

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModals();
    });

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && state.timer.isRunning) {
        syncTimerFromTimestamp();
      }
    });

    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModals();
      });
    });

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(err => {
        console.warn('SW registration skipped:', err);
      });
    }

    loadOverviewData();
    loadTasksData();
    loadGoalsData();
  }

  return {
    init,
    navigateTo,
    openQuickCaptureModal,
    setQuickCaptureTab,
    submitQuickCapture,
    openAttachmentsModal,
    uploadAttachment,
    deleteAttachment,
    filterGoals,
    onGoalTypeChange,
    openGoalModal,
    saveGoal,
    promptGoalProgress,
    completeGoal,
    deleteGoal,
    filterNotesByFolder,
    searchNotesClientSide,
    setNoteModalMode,
    openNoteModal,
    saveNote,
    deleteNote,
    setTaskMode,
    filterTasks,
    searchTasksClientSide,
    openTaskModal,
    saveTask,
    updateTaskStatus,
    deleteTask,
    deleteCurrentModalTask,
    startFocusForTask,
    setTimerMode,
    setCustomFocusDuration,
    promptCustomDuration,
    adjustTimerDuration,
    onTaskSelectedForTimer,
    toggleTimer,
    resetTimer,
    setFinanceSubTab,
    setTxnType,
    openFinanceModal,
    saveTransaction,
    searchFinanceClientSide,
    filterFinance,
    loadFinanceData,
    openRecurringRuleModal,
    saveRecurringRule,
    toggleRecurringRuleActive,
    deleteRecurringRule,
    loadFinanceProjection,
    deleteTransaction,
    filterIdeas,
    searchIdeas,
    convertIdeaToTask,
    openIdeaModal,
    saveIdea,
    changeIdeaStage,
    deleteIdea,
    openSystemModal,
    downloadHotBackup,
    exportData,
    closeModals
  };
})();

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
