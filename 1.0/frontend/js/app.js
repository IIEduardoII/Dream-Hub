/**
 * Nexus Hub - Frontend Controller
 * Vanilla ES Modules, zero external build dependencies, high-performance mobile ergonomics.
 */

const App = (() => {
  // App State
  const state = {
    currentView: 'overview',
    taskMode: 'kanban', // 'kanban' or 'list'
    taskPriorityFilter: 'all',
    ideaStageFilter: 'all',
    ideaSearchQuery: '',
    tasks: [],
    ideas: [],
    transactions: [],
    financeMonth: new Date().toISOString().slice(0, 7), // YYYY-MM
    txnType: 'expense',
    
    // Pomodoro Timer State
    timer: {
      mode: 'focus', // 'focus', 'short_break', 'long_break'
      focusMinutes: 25,
      durations: { focus: 25 * 60, short_break: 5 * 60, long_break: 15 * 60 },
      remainingSeconds: 25 * 60,
      isRunning: false,
      intervalId: null,
      selectedTaskId: null,
      startTime: null
    }
  };

  // Utility: Currency Formatter (BRL)
  function formatMoney(cents) {
    const val = (cents || 0) / 100;
    return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  // Utility: Date Formatter
  function formatDate(isoStr) {
    if (!isoStr) return '';
    const parts = isoStr.split('-');
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}`;
    }
    return isoStr;
  }

  // Web Audio Synthesizer: Soft Tibetan chime on timer completion
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
        gain.gain.setValueAtTime(0.2, ctx.currentTime + delay);
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
        throw new Error(err.error || `Erro HTTP ${res.status}`);
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

    // Refresh view data
    if (viewId === 'overview') loadOverviewData();
    else if (viewId === 'tasks') loadTasksData();
    else if (viewId === 'time') loadTimeData();
    else if (viewId === 'finance') loadFinanceData();
    else if (viewId === 'ideas') loadIdeasData();
  }

  // ---------------- OVERVIEW MODULE ----------------
  async function loadOverviewData() {
    try {
      const data = await apiFetch('/api/overview');
      document.getElementById('ov-pending-tasks').innerText = data.pending_tasks;
      document.getElementById('ov-urgent-tasks').innerText = `${data.urgent_tasks} urgentes`;
      
      document.getElementById('ov-focus-min').innerText = `${data.today_focus_minutes}m`;
      document.getElementById('ov-focus-sessions').innerText = `${data.today_pomodoro_sessions} ciclos`;

      document.getElementById('ov-balance').innerText = formatMoney(data.month_balance_cents);
      document.getElementById('ov-finance-flow').innerText = `+${formatMoney(data.month_income_cents)} | -${formatMoney(data.month_expense_cents)}`;

      document.getElementById('ov-ideas-count').innerText = data.active_ideas;

      // Render urgent tasks preview
      const tasks = await apiFetch('/api/tasks?status=todo');
      const urgentList = document.getElementById('ov-urgent-list');
      const urgentTasks = tasks.filter(t => t.priority === 'urgent' || t.priority === 'high').slice(0, 4);

      if (urgentTasks.length === 0) {
        urgentList.innerHTML = `
          <div class="empty-state" style="padding:20px 8px;">
            <div class="empty-title" style="font-size:0.9rem;">Tudo sob controle!</div>
            <div class="empty-desc" style="font-size:0.8rem; margin-bottom:8px;">Nenhuma tarefa urgente pendente no momento.</div>
          </div>
        `;
      } else {
        urgentList.innerHTML = urgentTasks.map(t => `
          <div class="task-card" style="margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
              <span class="task-title" style="font-size:0.875rem;">${escapeHtml(t.title)}</span>
              <span class="badge badge-${t.priority}">${t.priority}</span>
            </div>
            <div class="task-meta" style="margin-top:4px;">
              ${t.due_date ? `<span>📅 ${formatDate(t.due_date)}</span>` : ''}
              <span>🍅 ${t.completed_pomodoros}/${t.estimated_pomodoros}</span>
              <button class="btn btn-secondary btn-sm" style="margin-left:auto; min-height:28px; padding:2px 8px;" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">Focar</button>
            </div>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error('Falha ao carregar overview:', err);
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

  function renderTasks() {
    let filtered = state.tasks;
    if (state.taskPriorityFilter !== 'all') {
      filtered = filtered.filter(t => t.priority === state.taskPriorityFilter);
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
      // Flat List Mode
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

    return `
      <div class="task-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <h4 class="task-title">${escapeHtml(t.title)}</h4>
          <span class="badge badge-${t.priority}">${t.priority}</span>
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
      await apiFetch(`/api/tasks/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: newStatus })
      });
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
      estimated_pomodoros: parseInt(document.getElementById('task-pomodoros-input').value) || 1,
      pomodoro_duration_minutes: parseInt(document.getElementById('task-duration-input').value) || 25,
      category: document.getElementById('task-category-input').value.trim() || 'Geral'
    };

    try {
      if (id) {
        await apiFetch(`/api/tasks/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
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
    const sel = document.getElementById('timer-task-select');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">(Nenhuma tarefa selecionada)</option>' + 
      state.tasks.filter(t => t.status !== 'done' && t.status !== 'archived').map(t => `
        <option value="${t.id}">${escapeHtml(t.title)} (${t.completed_pomodoros}/${t.estimated_pomodoros}🍅 • ${t.pomodoro_duration_minutes || 25}m)</option>
      `).join('');
    sel.value = currentVal;
  }

  function setCustomFocusDuration(minutes) {
    minutes = Math.max(1, Math.min(180, parseInt(minutes) || 25));
    state.timer.focusMinutes = minutes;
    state.timer.durations.focus = minutes * 60;

    // Highlight preset pills or custom pill
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
    toggleTimer(true); // force start
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
    document.title = state.timer.isRunning ? `(${str}) Dream` : 'Dream Hub';
  }

  function toggleTimer(forceStart = false) {
    const btn = document.getElementById('btn-timer-toggle');
    if (state.timer.isRunning && !forceStart) {
      // Pause
      clearInterval(state.timer.intervalId);
      state.timer.isRunning = false;
      btn.innerText = 'Continuar Foco';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-time');
    } else {
      // Start
      if (!state.timer.startTime) state.timer.startTime = new Date().toISOString();
      state.timer.isRunning = true;
      btn.innerText = 'Pausar';
      btn.classList.remove('btn-time');
      btn.classList.add('btn-danger');

      state.timer.intervalId = setInterval(() => {
        if (state.timer.remainingSeconds > 0) {
          state.timer.remainingSeconds--;
          updateTimerDisplay();
        } else {
          // Finished cycle!
          completeTimerSession();
        }
      }, 1000);
    }
  }

  function resetTimer() {
    clearInterval(state.timer.intervalId);
    state.timer.isRunning = false;
    state.timer.startTime = null;
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
    resetTimer();
    playCompletionChime();

    const taskId = document.getElementById('timer-task-select')?.value || null;
    const durationMin = Math.round(state.timer.durations[state.timer.mode] / 60);

    try {
      await apiFetch('/api/time/sessions', {
        method: 'POST',
        body: JSON.stringify({
          task_id: taskId ? parseInt(taskId) : null,
          session_type: state.timer.mode,
          duration_minutes: durationMin,
          started_at: state.timer.startTime || new Date().toISOString(),
          ended_at: new Date().toISOString(),
          completed: 1,
          notes: ''
        })
      });
      loadTimeData();
      loadOverviewData();
      loadTasksData();
      alert('🎉 Ciclo concluído com sucesso!');
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

  // ---------------- FINANCE MODULE ----------------
  function setTxnType(type) {
    state.txnType = type;
    document.getElementById('btn-txn-expense').classList.toggle('active', type === 'expense');
    document.getElementById('btn-txn-income').classList.toggle('active', type === 'income');
  }

  function openFinanceModal() {
    const modal = document.getElementById('modal-finance');
    const form = document.getElementById('form-finance');
    form.reset();
    setTxnType('expense');
    document.getElementById('fin-date-input').value = new Date().toISOString().slice(0, 10);
    modal.classList.add('active');
  }

  async function saveTransaction(e) {
    e.preventDefault();
    const amountVal = parseFloat(document.getElementById('fin-amount-input').value);
    const payload = {
      description: document.getElementById('fin-desc-input').value.trim(),
      amount_cents: Math.round(amountVal * 100),
      type: state.txnType,
      category: document.getElementById('fin-category-select').value,
      account: document.getElementById('fin-account-select').value,
      date: document.getElementById('fin-date-input').value,
      is_settled: 1
    };

    try {
      await apiFetch('/api/finance/transactions', { method: 'POST', body: JSON.stringify(payload) });
      closeModals();
      await loadFinanceData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao registrar transação');
    }
  }

  async function loadFinanceData() {
    const monthInput = document.getElementById('finance-month-input');
    if (monthInput && !monthInput.value) {
      monthInput.value = state.financeMonth;
    }
    const selectedMonth = monthInput ? monthInput.value : state.financeMonth;

    try {
      // 1. Summary
      const summary = await apiFetch(`/api/finance/summary?month=${selectedMonth}`);
      document.getElementById('fin-net-balance').innerText = formatMoney(summary.net_balance_cents);
      document.getElementById('fin-net-balance').style.color = summary.net_balance_cents >= 0 ? 'var(--text-primary)' : 'var(--accent-expense)';
      document.getElementById('fin-total-income').innerText = formatMoney(summary.total_income_cents);
      document.getElementById('fin-total-expense').innerText = formatMoney(summary.total_expense_cents);

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
      const listEl = document.getElementById('finance-transactions-list');
      if (txns.length === 0) {
        listEl.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">💰</div>
            <div class="empty-title">Sem movimentações em ${selectedMonth}</div>
            <div class="empty-desc">Toque no botão abaixo para adicionar sua primeira receita ou despesa.</div>
            <button class="btn btn-finance" onclick="App.openFinanceModal()">+ Novo Lançamento</button>
          </div>
        `;
      } else {
        listEl.innerHTML = txns.map(t => `
          <div class="transaction-item">
            <div class="txn-left">
              <span class="txn-desc">${escapeHtml(t.description)}</span>
              <span class="txn-sub">📅 ${formatDate(t.date)} • ${escapeHtml(t.category)} • ${escapeHtml(t.account)}</span>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
              <span class="txn-amount ${t.type === 'income' ? 'flow-income' : 'flow-expense'}">
                ${t.type === 'income' ? '+' : '-'} ${formatMoney(t.amount_cents)}
              </span>
              <button class="btn btn-danger btn-sm" style="min-height:30px; padding:2px 8px;" onclick="App.deleteTransaction(${t.id})">&times;</button>
            </div>
          </div>
        `).join('');
      }
    } catch (e) {
      showError('finance-transactions-list', 'Falha ao carregar extrato.', () => loadFinanceData());
    }
  }

  async function deleteTransaction(id) {
    if (!confirm('Deseja realmente remover esta movimentação?')) return;
    try {
      await apiFetch(`/api/finance/transactions/${id}`, { method: 'DELETE' });
      await loadFinanceData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir transação');
    }
  }

  // ---------------- IDEAS MODULE ----------------
  async function loadIdeasData() {
    try {
      let url = '/api/ideas?';
      if (state.ideaStageFilter !== 'all') url += `stage=${state.ideaStageFilter}&`;
      if (state.ideaSearchQuery) url += `q=${encodeURIComponent(state.ideaSearchQuery)}&`;

      const ideas = await apiFetch(url);
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
    loadIdeasData();
  }

  let searchTimeout = null;
  function searchIdeas(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.ideaSearchQuery = query.trim();
      loadIdeasData();
    }, 250);
  }

  function renderIdeas() {
    const container = document.getElementById('ideas-list-container');
    if (state.ideas.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">💡</div>
          <div class="empty-title">Nenhuma anotação encontrada</div>
          <div class="empty-desc">Registre hipóteses, projetos, links ou estudos no seu segundo cérebro.</div>
          <button class="btn btn-ideas" onclick="App.openIdeaModal()">+ Nova Ideia</button>
        </div>
      `;
      return;
    }

    const stageMap = {
      raw: 'Rascunho',
      evaluating: 'Em Análise',
      in_action: 'Em Execução',
      archived: 'Arquivado'
    };

    container.innerHTML = state.ideas.map(i => {
      const tags = (i.tags || '').split(',').map(t => t.trim()).filter(Boolean);
      return `
        <div class="idea-card">
          <div class="idea-header">
            <h4 class="idea-title">${escapeHtml(i.title)}</h4>
            <span class="badge badge-medium">${stageMap[i.stage] || i.stage}</span>
          </div>
          ${i.content ? `<div class="idea-content">${escapeHtml(i.content)}</div>` : ''}
          ${tags.length > 0 ? `
            <div class="idea-tags">
              ${tags.map(t => `<span class="tag-badge">#${escapeHtml(t)}</span>`).join('')}
            </div>
          ` : ''}
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding-top:8px; border-top:1px solid var(--border-subtle);">
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="App.openIdeaModal(${i.id})">Editar</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteIdea(${i.id})">Excluir</button>
            </div>
            <select class="form-select" style="min-height:32px; font-size:0.75rem; width:auto; padding:2px 6px;" onchange="App.changeIdeaStage(${i.id}, this.value)">
              <option value="raw" ${i.stage === 'raw' ? 'selected' : ''}>Rascunho</option>
              <option value="evaluating" ${i.stage === 'evaluating' ? 'selected' : ''}>Em Análise</option>
              <option value="in_action" ${i.stage === 'in_action' ? 'selected' : ''}>Em Execução</option>
              <option value="archived" ${i.stage === 'archived' ? 'selected' : ''}>Arquivar</option>
            </select>
          </div>
        </div>
      `;
    }).join('');
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
      await loadIdeasData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir anotação');
    }
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
    // Current date header
    const now = new Date();
    const dateStr = now.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
    const headerDate = document.getElementById('header-date');
    if (headerDate) headerDate.innerText = dateStr;

    // Keyboard shortcuts: Esc to close modals
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModals();
    });

    // Close modal on backdrop click
    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModals();
      });
    });

    // Register Service Worker for PWA
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(err => {
        console.warn('SW registration skipped:', err);
      });
    }

    // Load initial data
    loadOverviewData();
    loadTasksData();
  }

  // Export public API
  return {
    init,
    navigateTo,
    setTaskMode,
    filterTasks,
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
    loadFinanceData,
    deleteTransaction,
    filterIdeas,
    searchIdeas,
    openIdeaModal,
    saveIdea,
    changeIdeaStage,
    deleteIdea,
    closeModals
  };
})();

// Bootstrap when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
