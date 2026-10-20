/**
 * Dream Hub v1.1 - Frontend Controller
 * Vanilla ES6+, zero external build dependencies, Pure OLED Dark, Mobile-First ergonomics.
 */

const App = (() => {
  const state = {
    currentView: 'overview',
    taskMode: 'kanban', // 'kanban' or 'list'
    taskPriorityFilter: 'all',
    taskSearchQuery: '',
    financeFilter: 'all',
    financeSearchQuery: '',
    ideaStageFilter: 'all',
    ideaSearchQuery: '',
    quickCaptureTab: 'idea', // 'idea', 'finance', 'task'
    tasks: [],
    ideas: [],
    transactions: [],
    recurringTransactions: [],
    financeMonth: new Date().toISOString().slice(0, 7), // YYYY-MM
    txnType: 'expense',

    // Timestamp-based Pomodoro Timer State ([RF03])
    timer: {
      mode: 'focus', // 'focus', 'short_break', 'long_break'
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

  function showToast(msg) {
    const el = document.getElementById('toast-notification');
    if (!el) return;
    el.innerText = msg;
    el.classList.add('show');
    setTimeout(() => {
      el.classList.remove('show');
    }, 3200);
  }

  // Web Audio API Synthesizer ([RF04]): Soft Tibetan sine chime without external MP3
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

      playTone(587.33, 0.0, 1.2); // D5
      playTone(880.00, 0.15, 1.5); // A5
    } catch (e) {
      console.warn('Audio chime unsupported:', e);
    }
  }

  // ---------------- API CLIENT ----------------
  async function apiFetch(endpoint, options = {}) {
    try {
      const res = await fetch(endpoint, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options
      });
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
    else if (viewId === 'ideas') loadIdeasData();
  }

  // ---------------- COCKPIT "MEU DIA" MODULE ([RF01]) ----------------
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

      document.getElementById('ov-ideas-count').innerText = data.active_ideas;

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

  // ---------------- ZERO-FRICTION QUICK CAPTURE MODAL ([RF02]) ----------------
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
    ['idea', 'finance', 'task'].forEach(t => {
      document.getElementById(`qc-tab-${t}`)?.classList.toggle('active', t === tab);
    });

    document.getElementById('qc-idea-fields').style.display = tab === 'idea' ? 'block' : 'none';
    document.getElementById('qc-finance-fields').style.display = tab === 'finance' ? 'block' : 'none';
    document.getElementById('qc-task-fields').style.display = tab === 'task' ? 'block' : 'none';

    const label = document.getElementById('qc-main-label');
    const input = document.getElementById('qc-main-input');
    const amountInput = document.getElementById('qc-amount-input');

    if (tab === 'idea') {
      label.innerText = 'Qual é a sua ideia ou anotação? *';
      input.placeholder = 'Ex: Automatizar backup, novo projeto...';
      if (amountInput) amountInput.required = false;
    } else if (tab === 'finance') {
      label.innerText = 'Descrição do Gasto ou Depósito *';
      input.placeholder = 'Ex: Café, Aluguel, Depósito Mensal...';
      if (amountInput) amountInput.required = true;
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
        showToast(isRec ? '🔁 Lançamento recorrente registrado!' : '💰 Lançamento registrado!');
        if (state.currentView === 'finance') await loadFinanceData();
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

  // ---------------- TASKS MODULE ([RF06], [RF07], [RF13]) ----------------
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

    return `
      <div class="task-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <h4 class="task-title">${escapeHtml(t.title)}</h4>
          <div style="display:flex; gap:4px; align-items:center; flex-shrink:0;">
            ${hasRec ? `<span class="badge badge-recurring" title="Recorrência automática">🔁 ${escapeHtml(t.recurrence)}</span>` : ''}
            <span class="badge badge-${t.priority}">${t.priority}</span>
          </div>
        </div>
        ${t.description ? `<p style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:8px;">${escapeHtml(t.description)}</p>` : ''}
        <div class="task-meta">
          <span>📁 ${escapeHtml(t.category)}</span>
          ${t.due_date ? `<span>📅 ${formatDate(t.due_date)}</span>` : ''}
          <span title="Pomodoros concluídos / previstos e duração">🍅 ${t.completed_pomodoros}/${t.estimated_pomodoros} (${t.pomodoro_duration_minutes || 25}m)</span>
        </div>
        <div class="task-actions">
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="App.openTaskModal(${t.id})">Editar</button>
            <button class="btn btn-secondary btn-sm" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">⏱ Focar</button>
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
    const payload = {
      title: document.getElementById('task-title-input').value.trim(),
      description: document.getElementById('task-desc-input').value.trim(),
      priority: document.getElementById('task-priority-select').value,
      status: document.getElementById('task-status-select').value,
      due_date: document.getElementById('task-due-input').value || null,
      recurrence: document.getElementById('task-recurrence-select').value || 'nenhuma',
      estimated_pomodoros: parseInt(document.getElementById('task-pomodoros-input').value) || 1,
      pomodoro_duration_minutes: parseInt(document.getElementById('task-duration-input').value) || 25,
      category: document.getElementById('task-category-input').value.trim() || 'Geral'
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

  // ---------------- TIME / POMODORO MODULE (Timestamp-accurate [RF03]) ----------------
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
      finSel.innerHTML = '<option value="">(Nenhuma tarefa vinculada)</option>' +
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
    document.title = state.timer.isRunning ? `(${str}) Dream Hub` : 'Dream Hub v1.1';
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
      // Pause: preserve exact remaining seconds
      syncTimerFromTimestamp();
      clearInterval(state.timer.intervalId);
      state.timer.isRunning = false;
      state.timer.endTime = null;
      btn.innerText = 'Continuar Foco';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-time');
    } else {
      // Start with timestamp target ([RF03])
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

  // ---------------- FINANCE MODULE & RECURRING TRANSACTIONS ([RF08], [RF09], [RF10]) ----------------
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
    modal.classList.add('active');
  }

  async function saveTransaction(e) {
    e.preventDefault();
    const amountVal = parseFloat(document.getElementById('fin-amount-input').value);
    const isRec = document.getElementById('fin-recurring-check')?.checked || false;
    const recFreq = isRec ? (document.getElementById('fin-recurrence-select')?.value || 'mensal') : 'nenhuma';
    const linkedTaskId = document.getElementById('fin-task-select')?.value || null;

    const payload = {
      description: document.getElementById('fin-desc-input').value.trim(),
      amount_cents: Math.round(amountVal * 100),
      type: state.txnType,
      category: document.getElementById('fin-category-select').value,
      account: document.getElementById('fin-account-select').value,
      date: document.getElementById('fin-date-input').value,
      task_id: linkedTaskId ? parseInt(linkedTaskId, 10) : null,
      is_settled: 1,
      is_recurring: isRec ? 1 : 0,
      recurrence: recFreq
    };

    try {
      await apiFetch('/api/finance/transactions', { method: 'POST', body: JSON.stringify(payload) });
      closeModals();
      showToast(isRec ? '🔁 Lançamento recorrente salvo!' : '💰 Lançamento salvo!');
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
      // 1. Summary & Recurring Totals
      const summary = await apiFetch(`/api/finance/summary?month=${selectedMonth}`);
      document.getElementById('fin-net-balance').innerText = formatMoney(summary.net_balance_cents);
      document.getElementById('fin-net-balance').style.color = summary.net_balance_cents >= 0 ? 'var(--text-primary)' : 'var(--accent-expense)';
      document.getElementById('fin-total-income').innerText = formatMoney(summary.total_income_cents);
      document.getElementById('fin-total-expense').innerText = formatMoney(summary.total_expense_cents);

      const recIncSub = document.getElementById('fin-rec-income-sub');
      const recExpSub = document.getElementById('fin-rec-expense-sub');
      if (recIncSub) recIncSub.innerText = `🔁 Fixos: ${formatMoney(summary.recurring_income_cents || 0)}`;
      if (recExpSub) recExpSub.innerText = `🔁 Fixos: ${formatMoney(summary.recurring_expense_cents || 0)}`;

      // Render Recurring Fixed Items Card
      state.recurringTransactions = summary.recurring_transactions || [];
      renderRecurringFinance();

      // Categories Breakdown
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

      // 2. Transactions
      const txns = await apiFetch(`/api/finance/transactions?month=${selectedMonth}`);
      state.transactions = txns;
      renderTransactionsList();
    } catch (e) {
      showError('finance-transactions-list', 'Falha ao carregar extrato.', () => loadFinanceData());
    }
  }

  function renderRecurringFinance() {
    const recEl = document.getElementById('fin-recurring-list');
    if (!recEl) return;
    const list = state.recurringTransactions || [];
    if (list.length === 0) {
      recEl.innerHTML = `
        <div class="empty-state" style="padding:18px 12px; margin:4px 0;">
          <div class="empty-desc" style="margin-bottom:8px;">Nenhum gasto ou depósito recorrente cadastrado neste mês.</div>
          <button class="btn btn-secondary btn-sm" onclick="App.openFinanceModal(true)">+ Cadastrar Gasto / Depósito Recorrente</button>
        </div>
      `;
      return;
    }

    recEl.innerHTML = list.map(t => `
      <div class="transaction-item">
        <div class="txn-left">
          <span class="txn-desc">
            <span class="badge badge-recurring">🔁 ${escapeHtml(t.recurrence || 'mensal')}</span>
            ${escapeHtml(t.description)}
          </span>
          <span class="txn-sub">Todo dia ${formatDate(t.date).slice(0, 2)} • ${escapeHtml(t.category)} • ${escapeHtml(t.account)}</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="txn-amount ${t.type === 'income' ? 'flow-income' : 'flow-expense'}">
            ${t.type === 'income' ? '+' : '-'} ${formatMoney(t.amount_cents)}
          </span>
          <button class="btn btn-secondary btn-sm" style="min-height:34px; padding:2px 8px; font-size:0.75rem;" title="Desativar repetição automática" onclick="App.cancelRecurringTransaction(${t.id})">Parar 🔁</button>
        </div>
      </div>
    `).join('');
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

    listEl.innerHTML = filtered.map(t => `
      <div class="transaction-item">
        <div class="txn-left">
          <span class="txn-desc">
            ${escapeHtml(t.description)}
            ${Number(t.is_recurring) === 1 ? `<span class="badge badge-recurring">🔁 ${escapeHtml(t.recurrence || 'mensal')}</span>` : ''}
          </span>
          <span class="txn-sub">
            📅 ${formatDate(t.date)} • ${escapeHtml(t.category)} • ${escapeHtml(t.account)}
            ${t.task_title ? ` • 🔗 ${escapeHtml(t.task_title)}` : ''}
          </span>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <span class="txn-amount ${t.type === 'income' ? 'flow-income' : 'flow-expense'}">
            ${t.type === 'income' ? '+' : '-'} ${formatMoney(t.amount_cents)}
          </span>
          <button class="btn btn-danger btn-sm" style="min-height:36px; min-width:36px; padding:2px 8px;" title="Excluir lançamento" onclick="App.deleteTransaction(${t.id})">&times;</button>
        </div>
      </div>
    `).join('');
  }

  async function cancelRecurringTransaction(id) {
    if (!confirm('Deseja desativar a repetição automática deste lançamento para os próximos meses?')) return;
    try {
      await apiFetch(`/api/finance/transactions/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_recurring: 0, recurrence: 'nenhuma' })
      });
      showToast('🔁 Recorrência desativada');
      await loadFinanceData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao desativar recorrência');
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

  // ---------------- IDEAS MODULE & 1-CLICK TASK CONVERSION ([RF11], [RF12], RN02) ----------------
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
          <div class="empty-title">Nenhuma anotação encontrada</div>
          <div class="empty-desc">Registre hipóteses, projetos, links ou estudos na sua incubadora.</div>
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
    if (!confirm('Deseja realmente remover esta anotação?')) return;
    try {
      await apiFetch(`/api/ideas/${id}`, { method: 'DELETE' });
      showToast('🗑 Ideia excluída');
      await loadIdeasData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir anotação');
    }
  }

  // ---------------- SYSTEM BACKUP ([RF14]) & EXPORT ([RF15]) ----------------
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

  // ---------------- GENERAL MODAL & ERROR UTILITIES ----------------
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

    // Keep Pomodoro countdown accurate even when screen turns off/wakes up ([RF03])
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
  }

  return {
    init,
    navigateTo,
    openQuickCaptureModal,
    setQuickCaptureTab,
    submitQuickCapture,
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
    setTxnType,
    openFinanceModal,
    saveTransaction,
    searchFinanceClientSide,
    filterFinance,
    loadFinanceData,
    cancelRecurringTransaction,
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
