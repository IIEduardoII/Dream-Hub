/**
 * Dream Hub v1.3 Mobile - Frontend Controller
 * Vanilla ES6+, zero external build dependencies, Pure OLED Dark (#000000), Mobile-First ergonomics.
 */

// === CONFIGURAÇÃO HÍBRIDA: WEB BROWSER + ANDROID APK (CAPACITOR + TAILSCALE) ===
const DEFAULT_TAILSCALE_SERVER = 'http://100.107.212.104:8090';
const IS_NATIVE_APK = Boolean(window.Capacitor) || 
    (window.location.hostname === 'localhost' && (!window.location.port || window.location.port === '80' || window.location.protocol === 'capacitor:' || window.location.protocol === 'ionic:'));

function getApiOrigin() {
  if (!IS_NATIVE_APK) return '';
  return (localStorage.getItem('dream_api_origin') || DEFAULT_TAILSCALE_SERVER).replace(/\/+$/, '');
}

const API_ORIGIN = getApiOrigin();

// Intercepta window.fetch automaticamente para prefixar chamadas /api/ e /uploads/ no modo APK
const _originalFetch = window.fetch.bind(window);
window.fetch = function(input, init) {
  if (typeof input === 'string') {
    if (input.startsWith('/api/') || input.startsWith('/uploads/')) {
      input = `${getApiOrigin()}${input}`;
    }
  }
  return _originalFetch(input, init);
};

// Função utilitária para links de download/anexos (<a href="/api/...">)
window.resolveApiUrl = function(path) {
  if (!path) return '';
  const origin = getApiOrigin();
  if (path.startsWith('/api/') || path.startsWith('/uploads/')) return `${origin}${path}`;
  return path;
};

// Reescreve cliques em links <a href="/api/..."> ou <a href="/uploads/..."> dentro do APK
document.addEventListener('click', (e) => {
  const link = e.target.closest('a[href^="/api/"], a[href^="/uploads/"]');
  if (link && IS_NATIVE_APK) {
    const rawHref = link.getAttribute('href');
    if (rawHref && (rawHref.startsWith('/api/') || rawHref.startsWith('/uploads/'))) {
      link.href = `${getApiOrigin()}${rawHref}`;
    }
  }
}, true);

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
    currentIdeaNoteType: 'text',
    currentIdeaChecklist: [],
    currentNoteType: 'text',
    currentNoteChecklist: [],
    quickCaptureTab: 'idea',
    tasks: [],
    archivedTasks: [],
    taskMode: 'kanban',
    hideDoneColumn: false,
    doneLimit: 8,
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

  function formatDateFull(isoStr) {
    if (!isoStr) return '';
    const parts = isoStr.slice(0, 10).split('-');
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return isoStr;
  }

  function formatFileSize(bytes) {
    const b = Number(bytes || 0);
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / (1024 * 1024)).toFixed(2)} MB`;
  }

  function formatMinutesToHoursAndMinutes(totalMinutes) {
    const mins = Math.max(0, parseInt(totalMinutes, 10) || 0);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h > 0 && m > 0) return `${h}h ${m}min`;
    if (h > 0) return `${h}h`;
    return `${m}min`;
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
    html = html.replace(/^- \[x\] (.+)$/gim, '<div>[x] <span style="text-decoration:line-through;color:var(--text-muted);">$1</span></div>');
    html = html.replace(/^- \[ \] (.+)$/gim, '<div>[ ] $1</div>');
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

  // ---------------- API CLIENT (DIRECT FETCH) ----------------
  async function apiFetch(endpoint, options = {}) {
    // Auto-serialize plain JS objects to JSON strings
    let body = options.body;
    if (body !== undefined && body !== null && !(body instanceof FormData) && typeof body === 'object') {
      body = JSON.stringify(body);
    }

    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    try {
      const res = await fetch(endpoint, { ...options, headers, body });
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
  function toggleNavMenu(e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('dropdown-nav-menu');
    if (menu) menu.classList.toggle('show');
  }

  function closeNavMenu() {
    const menu = document.getElementById('dropdown-nav-menu');
    if (menu) menu.classList.remove('show');
  }

  function setIdeasSubTab(subTab) {
    state.activeIdeasSubTab = subTab;
    const viewIdeas = document.getElementById('ideas-subview-ideas');
    const viewNotes = document.getElementById('ideas-subview-notes');
    const btnIdeas = document.getElementById('btn-ideas-sub-ideas');
    const btnNotes = document.getElementById('btn-ideas-sub-notes');
    const btnNewIdea = document.getElementById('btn-header-new-idea');
    const btnNewNote = document.getElementById('btn-header-new-note');

    if (subTab === 'notes') {
      if (viewIdeas) viewIdeas.style.display = 'none';
      if (viewNotes) viewNotes.style.display = 'block';
      if (btnIdeas) btnIdeas.classList.remove('active');
      if (btnNotes) btnNotes.classList.add('active');
      if (btnNewIdea) btnNewIdea.style.display = 'none';
      if (btnNewNote) btnNewNote.style.display = 'inline-flex';
      loadNotesData();
    } else {
      if (viewIdeas) viewIdeas.style.display = 'block';
      if (viewNotes) viewNotes.style.display = 'none';
      if (btnIdeas) btnIdeas.classList.add('active');
      if (btnNotes) btnNotes.classList.remove('active');
      if (btnNewIdea) btnNewIdea.style.display = 'inline-flex';
      if (btnNewNote) btnNewNote.style.display = 'none';
      loadIdeasData();
    }
  }

  function closeFabSpeedDial() {
    const fabContainer = document.getElementById('fab-container');
    const speedDial = document.getElementById('fab-speed-dial');
    if (fabContainer) fabContainer.classList.remove('open');
    if (speedDial) speedDial.setAttribute('aria-hidden', 'true');
  }

  function closeAllCardMenus() {
    document.querySelectorAll('.card-kebab-menu.show').forEach(el => el.classList.remove('show'));
  }

  function toggleCardMenu(e, menuId) {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const menu = document.getElementById(menuId);
    if (!menu) return;
    const isOpen = menu.classList.contains('show');
    closeAllCardMenus();
    if (!isOpen) {
      menu.classList.add('show');
    }
  }

  function navigateTo(viewId) {
    if (viewId === 'notes') {
      navigateTo('ideas');
      setIdeasSubTab('notes');
      return;
    }
    if (viewId === 'sleep') {
      navigateTo('routines');
      setRoutinesSubTab('sono');
      return;
    }

    state.currentView = viewId;
    closeNavMenu();
    closeFabSpeedDial();
    closeAllCardMenus();
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.dropdown-nav-item').forEach(el => el.classList.remove('active'));

    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) targetView.classList.add('active');

    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (viewId === 'overview') loadOverviewData();
    else if (viewId === 'tasks') loadTasksData();
    else if (viewId === 'time') loadTimeData();
    else if (viewId === 'finance') loadFinanceData();
    else if (viewId === 'goals') loadGoalsData();
    else if (viewId === 'ideas') {
      setIdeasSubTab(state.activeIdeasSubTab || 'ideas');
    }
    else if (viewId === 'ritmo') loadRitmoData();
    else if (viewId === 'routines') loadDailyRoutinesData();
  }

  // Close dropdown menus and FAB speed-dial on outside click
  window.addEventListener('click', (e) => {
    const menu = document.getElementById('dropdown-nav-menu');
    const trigger = document.getElementById('btn-main-menu-trigger');
    if (menu && menu.classList.contains('show')) {
      if (!menu.contains(e.target) && e.target !== trigger) {
        closeNavMenu();
      }
    }

    const fabContainer = document.getElementById('fab-container');
    if (fabContainer && fabContainer.classList.contains('open')) {
      if (!fabContainer.contains(e.target)) {
        closeFabSpeedDial();
      }
    }

    if (!e.target.closest('.card-kebab-wrap')) {
      closeAllCardMenus();
    }
  });

  // ---------------- DASHBOARD CLEAN MODULE (v1.4.0 Redesign Central) ----------------
  function dispatchDailyRoutinePushNotifications(notifications) {
    if (!Array.isArray(notifications) || !notifications.length) return;
    notifications.forEach(n => {
      const msg = n.body || `Sua rotina "${n.title || 'Diária'}" está em andamento.`;
      showToast(msg);
      try {
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification(n.title || 'Dream Hub • Rotina Diária', {
            body: msg,
            icon: '/icons/icon-192.png'
          });
        }
      } catch (_) {}
    });
  }

  async function changeFeaturedGoal(goalId) {
    try {
      await apiFetch('/api/settings/featured-goal', {
        method: 'PUT',
        body: { featured_goal_id: goalId ? parseInt(goalId, 10) : null }
      });
      await loadOverviewData();
      showToast('Meta em destaque atualizada no Dashboard');
    } catch (e) {
      showToast(e.message || 'Erro ao alterar meta em destaque');
    }
  }

  async function loadOverviewData() {
    try {
      const res = await apiFetch('/api/cockpit/today');
      const data = res.data || res;

      if (data.push_notifications && data.push_notifications.length) {
        dispatchDailyRoutinePushNotifications(data.push_notifications);
      }

      // === WIDGET PRIORITÁRIO 1: FINANÇAS (RF11) ===
      const finObj = data.finance || {
        balance_cents: data.month_balance_cents || 0,
        income_cents: data.month_income_cents || 0,
        expense_cents: data.month_expense_cents || 0
      };
      const dashFinBal = document.getElementById('dash-fin-balance');
      if (dashFinBal) {
        dashFinBal.innerText = formatMoney(finObj.balance_cents);
        dashFinBal.style.color = finObj.balance_cents >= 0 ? 'var(--accent-income, #10b981)' : 'var(--accent-expense, #ef4444)';
      }
      const dashFinSum = document.getElementById('dash-fin-summary');
      if (dashFinSum) {
        dashFinSum.innerText = `Entradas: ${formatMoney(finObj.income_cents)} • Saídas: ${formatMoney(finObj.expense_cents)}`;
      }

      // === WIDGET PRIORITÁRIO 2: ROTINA DO DIA (RF11) ===
      const routineToday = data.routine_today || null;
      const dashRoutineTitle = document.getElementById('dash-routine-title');
      const dashRoutineStatus = document.getElementById('dash-routine-status-line');
      const dashRoutineBar = document.getElementById('dash-routine-progress-bar');
      const dashRoutineTasksProg = document.getElementById('dash-routine-tasks-progress');
      const dashRoutineCta = document.getElementById('dash-routine-cta-btn');

      if (routineToday) {
        const statusMap = {
          em_andamento: 'Em Andamento',
          concluida: 'Concluída Hoje',
          interrompida: 'Interrompida',
          suspensa: 'Suspensa Temporariamente',
          cancelada: 'Cancelada Manualmente'
        };
        const stLabel = statusMap[routineToday.status] || routineToday.status;
        if (dashRoutineTitle) dashRoutineTitle.innerText = routineToday.title;
        if (dashRoutineStatus) {
          dashRoutineStatus.innerText = `Status: ${stLabel}${routineToday.scheduled_time ? ` • Horário: ${routineToday.scheduled_time}` : ''}`;
        }
        const pct = Math.min(100, Math.max(0, Number(routineToday.progress_percent || 0)));
        if (dashRoutineBar) dashRoutineBar.style.width = `${pct}%`;
        if (dashRoutineTasksProg) {
          const plannedText = routineToday.total_planned_label
            ? ` • ${routineToday.total_planned_label} planejados`
            : (routineToday.total_planned_minutes ? ` • ${formatMinutesToHoursAndMinutes(routineToday.total_planned_minutes)} planejados` : '');
          dashRoutineTasksProg.innerText = `${routineToday.done_tasks || 0}/${routineToday.total_tasks || 0} tarefas (${pct}%)${plannedText}`;
        }
        if (dashRoutineCta) {
          dashRoutineCta.innerText = routineToday.status === 'em_andamento' ? 'Executar Agora' : 'Ver Rotina';
        }
      } else {
        if (dashRoutineTitle) dashRoutineTitle.innerText = 'Nenhuma rotina ativa hoje';
        if (dashRoutineStatus) dashRoutineStatus.innerText = 'Crie uma rotina diária automatizada';
        if (dashRoutineBar) dashRoutineBar.style.width = '0%';
        if (dashRoutineTasksProg) dashRoutineTasksProg.innerText = '0/0 tarefas (0%)';
        if (dashRoutineCta) dashRoutineCta.innerText = '+ Criar Rotina';
      }

      // === WIDGET PRIORITÁRIO 3: META EM DESTAQUE (RF12, RN04) ===
      const featGoal = data.featured_goal || null;
      const availGoals = data.available_goals || data.active_goals || [];
      const goalSelectEl = document.getElementById('dash-featured-goal-select');
      const dashGoalTitle = document.getElementById('dash-goal-title');
      const dashGoalValues = document.getElementById('dash-goal-values');
      const dashGoalBar = document.getElementById('dash-goal-progress-bar');
      const dashGoalCat = document.getElementById('dash-goal-category-badge');
      const dashGoalPct = document.getElementById('dash-goal-pct');

      if (goalSelectEl) {
        if (availGoals.length >= 2) {
          goalSelectEl.style.display = 'inline-block';
          goalSelectEl.innerHTML = availGoals.map(g =>
            `<option value="${g.id}" ${featGoal && Number(g.id) === Number(featGoal.id) ? 'selected' : ''}>${escapeHtml(g.title)} (${g.progress_percent}%)</option>`
          ).join('');
        } else {
          goalSelectEl.style.display = 'none';
        }
      }

      if (featGoal) {
        const gPct = Math.min(100, Math.max(0, Number(featGoal.progress_percent || 0)));
        const valText = featGoal.goal_type === 'monetaria'
          ? `${formatMoney(Math.round((featGoal.current_value || 0) * 100))} de ${featGoal.target_value ? formatMoney(Math.round(featGoal.target_value * 100)) : 'Livre'}`
          : `${featGoal.current_value || 0} / ${featGoal.target_value || '?'} ${featGoal.unit || ''}`;
        if (dashGoalTitle) dashGoalTitle.innerText = featGoal.title;
        if (dashGoalValues) dashGoalValues.innerText = valText;
        if (dashGoalBar) dashGoalBar.style.width = `${gPct}%`;
        if (dashGoalCat) dashGoalCat.innerText = (featGoal.category || 'Geral').toUpperCase();
        if (dashGoalPct) dashGoalPct.innerText = `${gPct}%`;
      } else {
        if (dashGoalTitle) dashGoalTitle.innerText = 'Nenhuma meta ativa';
        if (dashGoalValues) dashGoalValues.innerText = 'Cadastre uma meta para acompanhar o progresso';
        if (dashGoalBar) dashGoalBar.style.width = '0%';
        if (dashGoalCat) dashGoalCat.innerText = 'SEM META';
        if (dashGoalPct) dashGoalPct.innerText = '0%';
      }

      const pendingEl = document.getElementById('ov-pending-tasks');
      if (pendingEl) pendingEl.innerText = data.pending_tasks ?? 0;
      const urgentEl = document.getElementById('ov-urgent-tasks');
      if (urgentEl) urgentEl.innerText = `${data.tasks_due_today_count || 0} hoje • ${data.urgent_tasks || 0} urgentes`;

      const focusMinEl = document.getElementById('ov-focus-min');
      if (focusMinEl) focusMinEl.innerText = `${data.today_focus_minutes || 0}m`;
      const focusSessEl = document.getElementById('ov-focus-sessions');
      if (focusSessEl) focusSessEl.innerText = `${data.today_pomodoro_sessions || 0} ciclos`;

      const balanceEl = document.getElementById('ov-balance');
      if (balanceEl) balanceEl.innerText = formatMoney(data.month_balance_cents);
      const flowEl = document.getElementById('ov-finance-flow');
      if (flowEl) flowEl.innerText = `+${formatMoney(data.month_income_cents)} | -${formatMoney(data.month_expense_cents)}`;

      const goalsCountEl = document.getElementById('ov-goals-count');
      if (goalsCountEl) goalsCountEl.innerText = `${data.active_goals_count || 0} metas`;
      const ideasSubEl = document.getElementById('ov-ideas-sub');
      if (ideasSubEl) ideasSubEl.innerText = `${data.active_ideas || 0} ideias • ${data.notes_count || 0} notas`;

      // 1. Render Active Goals with Percentage & Progress Bar
      const ovGoalsList = document.getElementById('ov-goals-list');
      if (ovGoalsList) {
        const activeGoals = data.active_goals || [];
        if (activeGoals.length === 0) {
          ovGoalsList.innerHTML = `
            <div class="dashboard-clean-empty">
              <span>Nenhuma meta ativa no momento.</span>
              <button class="btn btn-goals btn-sm" onclick="App.openGoalModal()">+ Criar Meta</button>
            </div>
          `;
        } else {
          ovGoalsList.innerHTML = activeGoals.map(g => renderGoalCard(g, true)).join('');
        }
      }

      // 2. Render Priority & Due Tasks of the Day (Clean Cards)
      const urgentList = document.getElementById('ov-urgent-list');
      if (urgentList) {
        const dueTasks = data.tasks_due_today || [];
        if (dueTasks.length === 0) {
          urgentList.innerHTML = `<div class="dashboard-clean-empty">Tudo sob controle hoje! Nenhuma tarefa urgente ou vencendo hoje.</div>`;
        } else {
          urgentList.innerHTML = dueTasks.slice(0, 5).map(t => `
            <div class="dashboard-clean-item">
              <div class="dashboard-clean-item-main">
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:2px;">
                  <span class="badge badge-${t.priority}">${escapeHtml(t.priority)}</span>
                  ${t.recurrence && t.recurrence !== 'nenhuma' ? `<span class="badge badge-recurring">${escapeHtml(t.recurrence)}</span>` : ''}
                  ${Number(t.streak_count || 0) > 0 ? `<span class="badge badge-streak">${t.streak_count}d</span>` : ''}
                </div>
                <span class="dashboard-clean-item-title">${escapeHtml(t.title)}</span>
                <span class="dashboard-clean-item-sub">
                  ${t.due_date ? `Prazo: ${formatDate(t.due_date)} • ` : ''}Pomodoros: ${t.completed_pomodoros || 0}/${t.estimated_pomodoros || 1} (${t.pomodoro_duration_minutes || 25}m)
                </span>
              </div>
              <div style="display:flex; gap:6px; flex-shrink:0;">
                <button class="btn btn-secondary btn-sm" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">Focar</button>
                <button class="btn btn-tasks btn-sm" onclick="App.updateTaskStatus(${t.id}, 'done')">Concluir</button>
              </div>
            </div>
          `).join('');
        }
      }

      // 3. Render Recent Ideas for 1-Click Conversion
      const recentIdeasEl = document.getElementById('ov-recent-ideas');
      if (recentIdeasEl) {
        const recentIdeas = data.recent_ideas || [];
        if (recentIdeas.length === 0) {
          recentIdeasEl.innerHTML = `<div class="dashboard-clean-empty">Nenhuma ideia pendente para converter. Use o botão + para capturar insights.</div>`;
        } else {
          recentIdeasEl.innerHTML = recentIdeas.map(i => {
            let subText = '';
            if (i.note_type === 'checklist') {
              const items = parseChecklistItems(i.content);
              const doneCnt = items.filter(it => it.done).length;
              subText = `Checklist • ${doneCnt}/${items.length} concluídos`;
            } else if (i.content) {
              subText = i.content.slice(0, 80);
            }
            return `
              <div class="dashboard-clean-item">
                <div class="dashboard-clean-item-main">
                  <span class="dashboard-clean-item-title">${escapeHtml(i.title)}</span>
                  ${subText ? `<span class="dashboard-clean-item-sub">${escapeHtml(subText)}</span>` : ''}
                </div>
                <button class="btn btn-ideas btn-sm" onclick="App.convertIdeaToTask(${i.id})">Virar Tarefa</button>
              </div>
            `;
          }).join('');
        }
      }
    } catch (err) {
      console.error('Falha ao carregar dashboard:', err);
    }
  }

  // ---------------- CONTEXTUAL SMART FAB ----------------
  function getActiveTabId() {
    const activeSection = document.querySelector('.view-section.active');
    if (activeSection && activeSection.id) {
      return activeSection.id.replace(/^view-/, '');
    }
    return state.currentView || 'overview';
  }

  function handleFabClick(e) {
    if (e) e.stopPropagation();
    const activeTab = getActiveTabId();

    // SE a aba ativa for o Dashboard ('overview'): exibir menu secundário (Speed Dial)
    if (activeTab === 'overview') {
      const fabContainer = document.getElementById('fab-container');
      const speedDial = document.getElementById('fab-speed-dial');
      if (!fabContainer) {
        openTaskModal();
        return;
      }
      const isOpen = fabContainer.classList.toggle('open');
      if (speedDial) speedDial.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
      return;
    }

    // SE a aba ativa for qualquer outra: ignorar menu secundário e abrir modal principal da aba atual
    closeFabSpeedDial();

    if (activeTab === 'finance') {
      if (state.financeSubTab === 'recorrencias') {
        openRecurringRuleModal();
      } else {
        openFinanceModal();
      }
    } else if (activeTab === 'tasks') {
      openTaskModal();
    } else if (activeTab === 'ritmo') {
      openStartWorkoutModal();
    } else if (activeTab === 'goals') {
      openGoalModal();
    } else if (activeTab === 'ideas') {
      if (state.activeIdeasSubTab === 'notes') {
        openNoteModal();
      } else {
        openIdeaModal();
      }
    } else if (activeTab === 'sleep') {
      openSleepModal();
    } else if (activeTab === 'routines') {
      openDailyRoutineModal();
    } else if (activeTab === 'time') {
      openTaskModal();
    } else {
      openTaskModal();
    }
  }

  // ---------------- PONTO 1: DECENTRALIZED ATTACHMENTS ([RF01], RN01) ----------------
  async function openAttachmentsModal(entityType, entityId, titleLabel = '') {
    document.getElementById('att-entity-type').value = entityType;
    document.getElementById('att-entity-id').value = entityId;
    document.getElementById('att-file-input').value = '';
    const titleEl = document.getElementById('modal-attachments-title');
    if (titleEl) {
      titleEl.innerText = titleLabel ? `Anexos: ${titleLabel}` : 'Anexos do Registro';
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
              <a href="/api/attachments/file/${a.id}" target="_blank" rel="noopener" class="attachment-name">${escapeHtml(a.filename)}</a>
              <div class="attachment-meta">${formatFileSize(a.file_size)} • ${escapeHtml(a.mime_type)}</div>
            </div>
            <div style="display:flex; gap:6px;">
              <a href="/api/attachments/file/${a.id}?download=1" class="btn btn-secondary btn-sm" title="Baixar arquivo">Baixar</a>
              <button type="button" class="btn btn-danger btn-sm" title="Excluir arquivo do disco" onclick="App.deleteAttachment(${a.id}, '${entityType}', ${entityId})">Excluir</button>
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
      showToast('Arquivo anexado com sucesso!');
      await loadEntityAttachments(entityType, entityId);
      refreshCurrentViewCounts();
    } catch (err) {
      alert(err.message || 'Erro ao enviar arquivo');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = 'Enviar e Anexar Arquivo';
      }
    }
  }

  async function deleteAttachment(attachmentId, entityType, entityId) {
    if (!confirm('Remover este anexo permanentemente do banco e do disco?')) return;
    try {
      await apiFetch(`/api/attachments/${attachmentId}`, { method: 'DELETE' });
      showToast('Anexo removido do disco');
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
        activeGoals.map(g => `<option value="${g.id}">${escapeHtml(g.title)} (${g.progress_percent}%)</option>`).join('');
      taskGoalSel.value = cur;
    }
    const finGoalSel = document.getElementById('fin-goal-select');
    if (finGoalSel) {
      const cur = finGoalSel.value;
      finGoalSel.innerHTML = '<option value="">(Nenhuma meta)</option>' +
        activeGoals.map(g => `<option value="${g.id}">${escapeHtml(g.title)} (${g.progress_percent}%)</option>`).join('');
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
    const isQual = g.goal_type === 'qualitativa';
    const valStr = g.goal_type === 'monetaria'
      ? `${formatMoney(Math.round((g.current_value || 0) * 100))} / ${g.target_value ? formatMoney(Math.round(g.target_value * 100)) : 'Livre'}`
      : (isQual
          ? `${g.current_value || 0} ${escapeHtml(g.unit || 'etapas')}`
          : `${g.current_value || 0} / ${g.target_value || '?'} ${escapeHtml(g.unit || '')}`);

    const menuId = `kebab-goal-${g.id}`;

    return `
      <div class="goal-card">
        <div class="card-top-row">
          <div class="card-header">
            <div class="card-badges">
              <span class="badge ${g.status === 'alcancada' ? 'badge-recurring' : 'badge-goal'}">
                ${g.status === 'alcancada' ? 'Alcançada' : `${g.progress_percent}%`}
              </span>
            </div>
            <h4 class="task-title">${escapeHtml(g.title)}</h4>
          </div>
          ${!compact ? `
            <div class="card-kebab-wrap">
              <button type="button" class="btn-card-kebab" onclick="App.toggleCardMenu(event, '${menuId}')" aria-label="Mais opções">&#8942;</button>
              <div class="card-kebab-menu" id="${menuId}">
                <button type="button" class="card-kebab-item" onclick="App.openGoalModal(${g.id})">Editar</button>
                ${g.status !== 'alcancada' ? `<button type="button" class="card-kebab-item" onclick="App.completeGoal(${g.id})">Concluir Meta</button>` : ''}
                <button type="button" class="card-kebab-item danger" onclick="App.deleteGoal(${g.id})">Excluir</button>
              </div>
            </div>
          ` : ''}
        </div>
        <div class="goal-progress-track">
          <div class="goal-progress-fill" style="width:${Math.min(100, g.progress_percent || 0)}%;"></div>
        </div>
        <div class="task-actions">
          <span style="font-family:var(--font-mono); font-size:0.78rem; color:var(--text-secondary);">${valStr}</span>
          ${g.status !== 'alcancada' ? `
            <button class="btn btn-goals btn-sm" onclick="App.promptGoalProgress(${g.id}, '${g.goal_type}')">+ Avançar</button>
          ` : ''}
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
      showToast('Meta salva!');
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
      showToast('Progresso da meta atualizado!');
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
      showToast('Parabéns! Meta alcançada!');
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
      showToast('Meta excluída');
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
      `<button class="stage-pill ${state.notesFolderFilter === 'all' ? 'active' : ''}" onclick="App.filterNotesByFolder('all', this)">Todos (${state.notes.length})</button>`,
      ...folders.map(f => {
        const active = state.notesFolderFilter === f ? 'active' : '';
        return `<button class="stage-pill ${active}" onclick="App.filterNotesByFolder('${escapeHtml(f)}', this)">${escapeHtml(f)}</button>`;
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

  // ---------------- CHECKLIST ENGINE (DOM MANIPULATION PURA) ----------------
  function parseChecklistItems(rawContent) {
    if (!rawContent) return [];
    if (Array.isArray(rawContent)) {
      return rawContent
        .map(it => ({ text: String(it?.text ?? '').trim(), done: Boolean(it?.done) }))
        .filter(it => it.text.length > 0);
    }
    const str = String(rawContent).trim();
    if (!str) return [];
    if (str.startsWith('[')) {
      try {
        const parsed = JSON.parse(str);
        if (Array.isArray(parsed)) {
          return parsed
            .map(it => ({
              text: String(typeof it === 'object' && it !== null ? (it.text ?? '') : it).trim(),
              done: Boolean(typeof it === 'object' && it !== null ? it.done : false)
            }))
            .filter(it => it.text.length > 0);
        }
      } catch (e) {}
    }
    return str
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean)
      .map(line => ({ text: line, done: false }));
  }

  function renderChecklistPreviewForCard(entityType, entityId, contentStr) {
    const items = parseChecklistItems(contentStr);
    const total = items.length;
    const doneCount = items.filter(it => it.done).length;

    const checkSvgDone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    const checkSvgPending = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="4" ry="4"></rect></svg>`;

    const itemsHtml = items.length > 0
      ? `<div class="checklist-card-preview">
          ${items.map((it, idx) => `
            <div class="checklist-card-item ${it.done ? 'done' : ''}" onclick="App.toggleCardChecklistItem('${entityType}', ${entityId}, ${idx})">
              ${it.done ? checkSvgDone : checkSvgPending}
              <span>${escapeHtml(it.text)}</span>
            </div>
          `).join('')}
        </div>`
      : `<div class="checklist-card-preview"><div style="font-size:0.75rem; color:var(--text-muted);">Checklist vazio</div></div>`;

    const counterHtml = `<span class="checklist-counter-badge">${doneCount}/${total} concluídos</span>`;
    return { itemsHtml, counterHtml, doneCount, total };
  }

  function toggleCardChecklistItem(entityType, entityId, itemIndex) {
    const isNote = entityType === 'note';
    const collection = isNote ? state.notes : state.ideas;
    const record = (collection || []).find(r => r.id === Number(entityId));
    if (!record) return;

    const items = parseChecklistItems(record.content);
    if (!items[itemIndex]) return;
    items[itemIndex].done = !items[itemIndex].done;

    const serialized = JSON.stringify(items);
    record.note_type = 'checklist';
    record.content = serialized;

    if (isNote) {
      renderNotes();
      apiFetch(`/api/notes/${record.id}`, {
        method: 'PUT',
        body: {
          title: record.title,
          folder: record.folder || 'Geral',
          tags: record.tags || '',
          is_pinned: record.is_pinned ? 1 : 0,
          note_type: 'checklist',
          content: serialized
        }
      }).catch(e => console.error(e));
    } else {
      renderIdeas();
      apiFetch(`/api/ideas/${record.id}`, {
        method: 'PUT',
        body: {
          title: record.title,
          stage: record.stage || 'raw',
          tags: record.tags || '',
          note_type: 'checklist',
          content: serialized
        }
      }).catch(e => console.error(e));
    }
  }

  function persistChecklistModalChange(target = 'idea') {
    const isNote = target === 'note';
    const items = isNote ? state.currentNoteChecklist : state.currentIdeaChecklist;
    const serialized = JSON.stringify(items);

    if (isNote) {
      const id = document.getElementById('note-id')?.value;
      if (!id) return;
      const title = document.getElementById('note-title-input')?.value.trim();
      const folder = document.getElementById('note-folder-input')?.value.trim() || 'Geral';
      const tags = document.getElementById('note-tags-input')?.value.trim() || '';
      const is_pinned = document.getElementById('note-pinned-check')?.checked ? 1 : 0;
      const rec = (state.notes || []).find(n => n.id === Number(id));
      if (rec) {
        rec.note_type = 'checklist';
        rec.content = serialized;
        renderNotes();
      }
      apiFetch(`/api/notes/${id}`, {
        method: 'PUT',
        body: {
          title: title || rec?.title || 'Nota',
          folder,
          tags,
          is_pinned,
          note_type: 'checklist',
          content: serialized
        }
      }).catch(e => console.error(e));
    } else {
      const id = document.getElementById('idea-id')?.value;
      if (!id) return;
      const title = document.getElementById('idea-title-input')?.value.trim();
      const stage = document.getElementById('idea-stage-select')?.value || 'raw';
      const tags = document.getElementById('idea-tags-input')?.value.trim() || '';
      const rec = (state.ideas || []).find(i => i.id === Number(id));
      if (rec) {
        rec.note_type = 'checklist';
        rec.content = serialized;
        renderIdeas();
      }
      apiFetch(`/api/ideas/${id}`, {
        method: 'PUT',
        body: {
          title: title || rec?.title || 'Ideia',
          stage,
          tags,
          note_type: 'checklist',
          content: serialized
        }
      }).catch(e => console.error(e));
    }
  }

  function renderChecklistDom(target = 'idea') {
    const isNote = target === 'note';
    const ulId = isNote ? 'note-checklist-list' : 'idea-checklist-list';
    const ul = document.getElementById(ulId);
    if (!ul) return;

    const items = isNote ? state.currentNoteChecklist : state.currentIdeaChecklist;
    ul.innerHTML = '';

    items.forEach((item, index) => {
      const li = document.createElement('li');
      li.className = 'checklist-item' + (item.done ? ' done' : '');

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = Boolean(item.done);

      const textSpan = document.createElement('span');
      textSpan.className = 'checklist-item-text';
      textSpan.textContent = item.text;
      if (item.done) {
        textSpan.style.textDecoration = 'line-through';
      }

      checkbox.addEventListener('change', () => {
        item.done = checkbox.checked;
        li.classList.toggle('done', item.done);
        textSpan.style.textDecoration = item.done ? 'line-through' : 'none';
        persistChecklistModalChange(target);
      });

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'checklist-item-remove';
      removeBtn.title = 'Remover item';
      removeBtn.textContent = '×';
      removeBtn.addEventListener('click', () => {
        items.splice(index, 1);
        renderChecklistDom(target);
        persistChecklistModalChange(target);
      });

      li.appendChild(checkbox);
      li.appendChild(textSpan);
      li.appendChild(removeBtn);
      ul.appendChild(li);
    });
  }

  function addChecklistItemFromInput(target = 'idea') {
    const isNote = target === 'note';
    const inputId = isNote ? 'note-checklist-new-input' : 'idea-checklist-new-input';
    const inputEl = document.getElementById(inputId);
    if (!inputEl) return;

    const text = inputEl.value.trim();
    if (!text) return;

    const items = isNote ? state.currentNoteChecklist : state.currentIdeaChecklist;
    items.push({ text, done: false });
    inputEl.value = '';
    renderChecklistDom(target);
    persistChecklistModalChange(target);
    inputEl.focus();
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
          
          <div class="empty-title">Nenhuma anotação neste caderno</div>
          <div class="empty-desc">Crie resumos de estudo, documentações em Markdown, listas ou guias técnicos perenes.</div>
          <button class="btn btn-notes" onclick="App.openNoteModal()">+ Nova Anotação</button>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(n => {
      const attCount = Number(n.attachments_count || 0);
      const isChecklist = n.note_type === 'checklist';
      const chkData = isChecklist ? renderChecklistPreviewForCard('note', n.id, n.content) : null;
      const menuId = `kebab-note-${n.id}`;

      return `
        <div class="note-card ${n.is_pinned ? 'pinned' : ''}">
          <div class="card-top-row">
            <div class="card-header">
              <div class="card-badges">
                <span class="badge badge-medium">${escapeHtml(n.folder || 'Geral')}</span>
                ${n.is_pinned ? `<span class="badge badge-high">Fixada</span>` : ''}
              </div>
              <h4 class="idea-title">${escapeHtml(n.title)}</h4>
            </div>
            <div class="card-kebab-wrap">
              <button type="button" class="btn-card-kebab" onclick="App.toggleCardMenu(event, '${menuId}')" aria-label="Mais opções">&#8942;</button>
              <div class="card-kebab-menu" id="${menuId}">
                <button type="button" class="card-kebab-item" onclick="App.openNoteModal(${n.id}, '${isChecklist ? 'checklist' : 'edit'}')">Editar</button>
                <button type="button" class="card-kebab-item" onclick="App.openNoteModal(${n.id}, 'preview')">Ler / Preview</button>
                <button type="button" class="card-kebab-item" onclick="App.openAttachmentsModal('note', ${n.id}, '${escapeHtml(n.title)}')">Anexos (${attCount})</button>
                <button type="button" class="card-kebab-item danger" onclick="App.deleteNote(${n.id})">Excluir</button>
              </div>
            </div>
          </div>
          ${isChecklist ? chkData.itemsHtml : `
            <div class="markdown-body" style="max-height:140px; overflow:hidden; margin-bottom:10px; opacity:0.9;">
              ${renderMarkdown((n.content || '').slice(0, 360))}
            </div>
          `}
          <div class="task-actions">
            <div>
              ${isChecklist ? chkData.counterHtml : `<span style="font-size:0.75rem; color:var(--text-muted);">${formatDate(n.updated_at)}</span>`}
            </div>
            <button class="btn btn-secondary btn-sm" onclick="App.openNoteModal(${n.id}, '${isChecklist ? 'checklist' : 'preview'}')">${isChecklist ? 'Abrir' : 'Ler'}</button>
          </div>
        </div>
      `;
    }).join('');
  }

  function setNoteModalMode(mode) {
    const prevType = state.currentNoteType || 'text';
    const editPane = document.getElementById('note-editor-pane');
    const prevPane = document.getElementById('note-preview-pane');
    const rendered = document.getElementById('note-markdown-rendered');
    const textGroup = document.getElementById('note-text-group');
    const chkGroup = document.getElementById('note-checklist-group');
    const typeInput = document.getElementById('note-type-input');
    const textarea = document.getElementById('note-content-input');

    document.getElementById('btn-note-edit-mode')?.classList.toggle('active', mode === 'edit');
    document.getElementById('btn-note-checklist-mode')?.classList.toggle('active', mode === 'checklist');
    document.getElementById('btn-note-preview-mode')?.classList.toggle('active', mode === 'preview');

    if (mode === 'preview') {
      editPane.style.display = 'none';
      prevPane.style.display = 'block';
      if (state.currentNoteType === 'checklist') {
        const mdLines = (state.currentNoteChecklist || []).map(it => `- [${it.done ? 'x' : ' '}] ${it.text}`).join('\n');
        rendered.innerHTML = renderMarkdown(mdLines);
      } else {
        const md = textarea ? textarea.value : '';
        rendered.innerHTML = renderMarkdown(md);
      }
    } else if (mode === 'checklist') {
      editPane.style.display = 'block';
      prevPane.style.display = 'none';
      if (prevType === 'text' && textarea && textarea.value.trim()) {
        const rawVal = textarea.value.trim();
        if (rawVal.startsWith('[')) {
          state.currentNoteChecklist = parseChecklistItems(rawVal);
        } else {
          state.currentNoteChecklist = textarea.value
            .split('\n')
            .map(line => line.trim())
            .filter(Boolean)
            .map(text => ({ text, done: false }));
        }
      }
      if (textGroup) textGroup.style.display = 'none';
      if (chkGroup) chkGroup.style.display = 'block';
      if (typeInput) typeInput.value = 'checklist';
      state.currentNoteType = 'checklist';
      renderChecklistDom('note');
    } else {
      editPane.style.display = 'block';
      prevPane.style.display = 'none';
      if (prevType === 'checklist' && Array.isArray(state.currentNoteChecklist) && state.currentNoteChecklist.length > 0 && textarea) {
        textarea.value = state.currentNoteChecklist.map(it => it.text).join('\n');
      }
      if (textGroup) textGroup.style.display = 'block';
      if (chkGroup) chkGroup.style.display = 'none';
      if (typeInput) typeInput.value = 'text';
      state.currentNoteType = 'text';
    }
  }

  function openNoteModal(noteId = null, initialMode = 'edit') {
    const modal = document.getElementById('modal-note');
    const form = document.getElementById('form-note');
    const titleEl = document.getElementById('modal-note-title');
    form.reset();
    state.currentNoteChecklist = [];
    state.currentNoteType = 'text';

    if (noteId) {
      const n = state.notes.find(x => x.id === noteId);
      if (n) {
        titleEl.innerText = n.title;
        document.getElementById('note-id').value = n.id;
        document.getElementById('note-title-input').value = n.title;
        document.getElementById('note-folder-input').value = n.folder || 'Geral';
        document.getElementById('note-tags-input').value = n.tags || '';
        document.getElementById('note-pinned-check').checked = Boolean(n.is_pinned);
        if (n.note_type === 'checklist') {
          state.currentNoteType = 'checklist';
          state.currentNoteChecklist = parseChecklistItems(n.content);
          document.getElementById('note-content-input').value = '';
          if (initialMode === 'edit') initialMode = 'checklist';
        } else {
          state.currentNoteType = 'text';
          document.getElementById('note-content-input').value = n.content || '';
        }
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
    const isChecklist = state.currentNoteType === 'checklist';
    const pendingInput = document.getElementById('note-checklist-new-input');
    if (isChecklist && pendingInput && pendingInput.value.trim()) {
      state.currentNoteChecklist.push({ text: pendingInput.value.trim(), done: false });
      pendingInput.value = '';
    }
    const payload = {
      title: document.getElementById('note-title-input').value.trim(),
      folder: document.getElementById('note-folder-input').value.trim() || 'Geral',
      tags: document.getElementById('note-tags-input').value.trim(),
      is_pinned: document.getElementById('note-pinned-check').checked ? 1 : 0,
      note_type: isChecklist ? 'checklist' : 'text',
      content: isChecklist ? JSON.stringify(state.currentNoteChecklist) : document.getElementById('note-content-input').value
    };

    try {
      if (id) {
        await apiFetch(`/api/notes/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/notes', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeModals();
      showToast('Anotação salva!');
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
      showToast('Anotação excluída');
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

  async function setTaskMode(mode) {
    state.taskMode = mode;
    document.getElementById('btn-kanban-mode')?.classList.toggle('active', mode === 'kanban');
    document.getElementById('btn-list-mode')?.classList.toggle('active', mode === 'list');
    document.getElementById('btn-archived-mode')?.classList.toggle('active', mode === 'archived');
    document.getElementById('tasks-kanban-container').style.display = mode === 'kanban' ? 'grid' : 'none';
    document.getElementById('tasks-flat-container').style.display = mode === 'list' ? 'block' : 'none';
    const archContainer = document.getElementById('tasks-archived-container');
    if (archContainer) archContainer.style.display = mode === 'archived' ? 'block' : 'none';

    if (mode === 'archived') {
      await loadArchivedTasks();
    } else {
      renderTasks();
    }
  }

  function toggleDoneColumn() {
    state.hideDoneColumn = !state.hideDoneColumn;
    const btn = document.getElementById('btn-toggle-done-col');
    const colDone = document.getElementById('col-done');
    if (btn) {
      btn.innerText = state.hideDoneColumn ? 'Mostrar Concluídas' : 'Ocultar Concluídas';
    }
    if (colDone) {
      colDone.classList.toggle('hidden-col', state.hideDoneColumn);
    }
  }

  function loadMoreDoneTasks() {
    state.doneLimit += 8;
    renderTasks();
  }

  async function archiveAllDoneTasks() {
    if (!confirm('Deseja arquivar todas as tarefas concluídas do quadro? Elas continuarão salvas na aba "Arquivo".')) return;
    try {
      const res = await apiFetch('/api/tasks/archive_all_done', { method: 'POST' });
      showToast(`${res.archived_count || 0} tarefa(s) arquivada(s)!`);
      await loadTasksData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao arquivar tarefas concluídas');
    }
  }

  async function loadArchivedTasks() {
    const container = document.getElementById('tasks-archived-container');
    if (!container) return;
    container.innerHTML = '<div class="skeleton" style="height:60px;"></div>';
    try {
      const archived = await apiFetch('/api/tasks?status=archived');
      state.archivedTasks = archived || [];
      renderArchivedTasks();
    } catch (e) {
      showError('tasks-archived-container', 'Falha ao carregar arquivo de tarefas', () => loadArchivedTasks());
    }
  }

  function renderArchivedTasks() {
    const container = document.getElementById('tasks-archived-container');
    if (!container) return;
    if (state.archivedTasks.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          
          <div class="empty-title">Nenhuma tarefa arquivada</div>
          <div class="empty-desc">Tarefas concluídas há mais de 24 horas são transferidas para cá automaticamente para manter o quadro Kanban ágil e limpo.</div>
          <button class="btn btn-secondary" onclick="App.setTaskMode('kanban')">Voltar ao Quadro</button>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
        <span style="font-size:0.875rem; color:var(--text-secondary);">Tarefas no Arquivo: <b>${state.archivedTasks.length}</b></span>
        <button class="btn btn-secondary btn-sm" onclick="App.setTaskMode('kanban')">← Voltar ao Quadro</button>
      </div>
      ${state.archivedTasks.map(t => renderTaskCard(t, true)).join('')}
    `;
  }

  async function unarchiveTask(taskId) {
    try {
      await apiFetch(`/api/tasks/${taskId}/archive`, { method: 'POST' });
      showToast('Tarefa desarquivada para o quadro!');
      await loadArchivedTasks();
      await loadTasksData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao desarquivar tarefa');
    }
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
      const cols = { todo: [], in_progress: [], stopped: [], done: [] };
      filtered.forEach(t => {
        if (cols[t.status]) cols[t.status].push(t);
        else cols.todo.push(t);
      });

      const colDone = document.getElementById('col-done');
      if (colDone) {
        colDone.classList.toggle('hidden-col', state.hideDoneColumn);
      }

      ['todo', 'in_progress', 'stopped', 'done'].forEach(col => {
        const countEl = document.getElementById(`count-${col}`);
        const listEl = document.getElementById(`tasks-list-${col}`);
        if (countEl) countEl.innerText = cols[col].length;

        if (cols[col].length === 0) {
          if (listEl) {
            listEl.innerHTML = `
              <div class="empty-state" style="padding:16px 8px;">
                <div class="empty-desc" style="margin-bottom:0;">Vazio</div>
              </div>
            `;
          }
          if (col === 'done') {
            const loadMoreEl = document.getElementById('done-load-more-container');
            if (loadMoreEl) loadMoreEl.style.display = 'none';
          }
        } else {
          let items = cols[col];
          if (col === 'done') {
            const loadMoreEl = document.getElementById('done-load-more-container');
            const btnLoadMore = document.getElementById('btn-load-more-done');
            if (items.length > state.doneLimit) {
              items = items.slice(0, state.doneLimit);
              if (loadMoreEl) loadMoreEl.style.display = 'block';
              if (btnLoadMore) btnLoadMore.innerText = `Carregar anteriores (+${cols.done.length - state.doneLimit})`;
            } else {
              if (loadMoreEl) loadMoreEl.style.display = 'none';
            }
          }
          if (listEl) listEl.innerHTML = items.map(t => renderTaskCard(t, false)).join('');
        }
      });
    } else {
      const container = document.getElementById('tasks-flat-container');
      if (filtered.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-title">Nenhuma tarefa encontrada</div>
            <div class="empty-desc">Crie uma nova tarefa ou altere os filtros acima.</div>
            <button class="btn btn-tasks" onclick="App.openTaskModal()">+ Nova Tarefa</button>
          </div>
        `;
      } else {
        container.innerHTML = filtered.map(t => renderTaskCard(t, false)).join('');
      }
    }
  }

  function renderTaskCard(t, isArchivedView = false) {
    const hasRec = t.recurrence && t.recurrence !== 'nenhuma';
    const streak = Number(t.streak_count || 0);
    const attCount = Number(t.attachments_count || 0);
    const menuId = `kebab-task-${isArchivedView ? 'arch-' : ''}${t.id}`;

    let primaryActionHtml = '';
    if (isArchivedView) {
      primaryActionHtml = `<button class="btn btn-secondary btn-sm" onclick="App.unarchiveTask(${t.id})">Desarquivar</button>`;
    } else if (t.status === 'in_progress') {
      primaryActionHtml = `<button class="btn btn-tasks btn-sm" onclick="App.updateTaskStatus(${t.id}, 'done')">Concluir</button>`;
    } else if (t.status === 'stopped') {
      primaryActionHtml = `<button class="btn btn-tasks btn-sm" onclick="App.updateTaskStatus(${t.id}, 'in_progress')">Retomar</button>`;
    } else if (t.status === 'todo') {
      primaryActionHtml = `<button class="btn btn-tasks btn-sm" onclick="App.updateTaskStatus(${t.id}, 'in_progress')">Iniciar</button>`;
    } else {
      primaryActionHtml = `<button class="btn btn-secondary btn-sm" onclick="App.updateTaskStatus(${t.id}, 'todo')">Reabrir</button>`;
    }

    return `
      <div class="task-card">
        <div class="card-top-row">
          <div class="card-header">
            <div class="card-badges">
              ${streak > 0 ? `<span class="badge badge-streak" title="Ofensiva diária consecutiva">${streak}d</span>` : ''}
              ${t.status === 'stopped' ? '<span class="badge badge-stopped">Stop</span>' : ''}
              <span class="badge badge-${t.priority}">${t.priority}</span>
            </div>
            <h3 class="task-title">${escapeHtml(t.title)}</h3>
          </div>
          <div class="card-kebab-wrap">
            <button type="button" class="btn-card-kebab" onclick="App.toggleCardMenu(event, '${menuId}')" aria-label="Mais opções">&#8942;</button>
            <div class="card-kebab-menu" id="${menuId}">
              ${!isArchivedView ? `
                <button type="button" class="card-kebab-item" onclick="App.openTaskModal(${t.id})">Editar Detalhes</button>
                <button type="button" class="card-kebab-item" onclick="App.startFocusForTask(${t.id}, '${escapeHtml(t.title)}')">Focar (Pomodoro)</button>
                ${t.status === 'in_progress' ? `<button type="button" class="card-kebab-item" onclick="App.updateTaskStatus(${t.id}, 'stopped')">Pausar (Stop)</button>` : ''}
                ${t.status !== 'done' ? `<button type="button" class="card-kebab-item" onclick="App.updateTaskStatus(${t.id}, 'done')">Marcar Concluída</button>` : ''}
                ${hasRec ? `<button type="button" class="card-kebab-item" onclick="App.openTaskHistoryModal(${t.id}, '${escapeHtml(t.title)}')">Histórico</button>` : ''}
                <button type="button" class="card-kebab-item" onclick="App.openAttachmentsModal('task', ${t.id}, '${escapeHtml(t.title)}')">Anexos (${attCount})</button>
              ` : `
                <button type="button" class="card-kebab-item" onclick="App.unarchiveTask(${t.id})">Desarquivar</button>
              `}
              <button type="button" class="card-kebab-item danger" onclick="App.deleteTask(${t.id})">Excluir</button>
            </div>
          </div>
        </div>
        <div class="task-actions">
          <span class="task-meta">${t.due_date ? formatDate(t.due_date) : escapeHtml(t.category || 'Geral')}</span>
          <div style="display:flex; align-items:center; gap:8px;">
            ${hasRec ? `<button type="button" class="btn btn-secondary btn-sm" onclick="App.openTaskHistoryModal(${t.id}, '${escapeHtml(t.title)}')">Histórico</button>` : ''}
            ${primaryActionHtml}
          </div>
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
      if (updated.cycle_completed || updated.streak_incremented) {
        showToast(`Ofensiva aumentada! ${updated.streak_count} dia${updated.streak_count > 1 ? 's' : ''} seguidos! Próximo ciclo: ${formatDate(updated.next_due_date)}`);
      } else if (newStatus === 'done') {
        showToast('Tarefa concluída!');
      } else if (newStatus === 'stopped') {
        showToast('Tarefa interrompida (Stop).');
      } else if (newStatus === 'in_progress') {
        showToast('Tarefa em andamento.');
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
      showToast('Tarefa excluída');
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
          showToast(`Próxima tarefa recorrente agendada para ${formatDate(res.next_recurring_task.due_date)}`);
        }
      } else {
        await apiFetch('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
        showToast('Tarefa salva!');
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
          <option value="${t.id}">${escapeHtml(t.title)} (${t.completed_pomodoros}/${t.estimated_pomodoros} pom • ${t.pomodoro_duration_minutes || 25}m)</option>
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
      customPill.innerText = isCustom ? `${minutes}m` : 'Outro';
    }

    if (state.timer.mode === 'focus' && !state.timer.isRunning) {
      state.timer.remainingSeconds = state.timer.durations.focus;
      updateTimerDisplay();
    }
    savePomodoroState();
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
        savePomodoroState();
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
        savePomodoroState();
      }
    }
  }

  function onTaskSelectedForTimer(taskId) {
    const badge = document.getElementById('timer-task-duration-badge');
    if (!taskId) {
      state.timer.selectedTaskId = null;
      if (badge) badge.innerText = '';
      savePomodoroState();
      return;
    }

    const task = state.tasks.find(t => t.id === parseInt(taskId));
    if (task) {
      state.timer.selectedTaskId = task.id;
      const taskDur = task.pomodoro_duration_minutes || 25;
      setCustomFocusDuration(taskDur);
      if (badge) badge.innerText = `${taskDur}m da tarefa`;
      savePomodoroState();
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
    savePomodoroState();
  }

  function updateTimerDisplay() {
    const min = Math.floor(state.timer.remainingSeconds / 60);
    const sec = state.timer.remainingSeconds % 60;
    const str = `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    const display = document.getElementById('timer-display');
    if (display) display.innerText = str;
    document.title = state.timer.isRunning ? `(${str}) Dream Hub` : 'Dream Hub v1.3';
  }

  function savePomodoroState() {
    try {
      const data = {
        mode: state.timer.mode,
        focusMinutes: state.timer.focusMinutes,
        durations: state.timer.durations,
        remainingSeconds: state.timer.remainingSeconds,
        isRunning: state.timer.isRunning,
        startTime: state.timer.startTime,
        endTime: state.timer.endTime,
        selectedTaskId: state.timer.selectedTaskId
      };
      localStorage.setItem('dreamhub_pomodoro_state', JSON.stringify(data));
    } catch (e) {
      console.warn('Erro ao salvar estado do Pomodoro:', e);
    }
  }

  function loadPomodoroState() {
    try {
      const raw = localStorage.getItem('dreamhub_pomodoro_state');
      if (!raw) return;
      const data = JSON.parse(raw);
      state.timer.mode = data.mode || 'focus';
      state.timer.focusMinutes = data.focusMinutes || 25;
      state.timer.durations = data.durations || { focus: 25 * 60, short_break: 5 * 60, long_break: 15 * 60 };
      state.timer.selectedTaskId = data.selectedTaskId || null;
      state.timer.startTime = data.startTime || null;

      if (data.isRunning && data.endTime) {
        const now = Date.now();
        if (now < data.endTime) {
          state.timer.endTime = data.endTime;
          state.timer.remainingSeconds = Math.max(0, Math.ceil((data.endTime - now) / 1000));
          state.timer.isRunning = true;
          clearInterval(state.timer.intervalId);
          state.timer.intervalId = setInterval(syncTimerFromTimestamp, 500);

          const btn = document.getElementById('btn-timer-toggle');
          if (btn) {
            btn.innerText = 'Pausar';
            btn.classList.remove('btn-time');
            btn.classList.add('btn-danger');
          }
        } else {
          state.timer.remainingSeconds = 0;
          state.timer.isRunning = false;
          completeTimerSession();
        }
      } else {
        state.timer.remainingSeconds = data.remainingSeconds !== undefined ? data.remainingSeconds : state.timer.durations[state.timer.mode];
        state.timer.isRunning = false;
      }

      document.querySelectorAll('.timer-mode-btn').forEach(b => b.classList.remove('active'));
      const btn = document.getElementById(`btn-mode-${state.timer.mode === 'focus' ? 'focus' : (state.timer.mode === 'short_break' ? 'short' : 'long')}`);
      if (btn) btn.classList.add('active');

      const presets = [15, 25, 45, 50, 60];
      presets.forEach(p => {
        const el = document.getElementById(`dur-pill-${p}`);
        if (el) el.classList.toggle('active', p === state.timer.focusMinutes);
      });
      const customPill = document.getElementById('dur-pill-custom');
      if (customPill) {
        const isCustom = !presets.includes(state.timer.focusMinutes);
        customPill.classList.toggle('active', isCustom);
        customPill.innerText = isCustom ? `${state.timer.focusMinutes}m` : 'Outro';
      }

      updateTimerDisplay();
    } catch (e) {
      console.warn('Erro ao restaurar estado do Pomodoro:', e);
    }
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
      if (btn) {
        btn.innerText = 'Continuar Foco';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-time');
      }
      savePomodoroState();
    } else {
      if (!state.timer.startTime) state.timer.startTime = new Date().toISOString();
      state.timer.endTime = Date.now() + state.timer.remainingSeconds * 1000;
      state.timer.isRunning = true;
      if (btn) {
        btn.innerText = 'Pausar';
        btn.classList.remove('btn-time');
        btn.classList.add('btn-danger');
      }

      clearInterval(state.timer.intervalId);
      state.timer.intervalId = setInterval(syncTimerFromTimestamp, 500);
      savePomodoroState();
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
    savePomodoroState();
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
      showToast('Ciclo Pomodoro concluído e creditado!');
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
            
            <div class="empty-title">Nenhum foco registrado hoje</div>
            <div class="empty-desc">Inicie um Pomodoro acima para cronometrar seu tempo de trabalho.</div>
          </div>
        `;
      } else {
        listEl.innerHTML = sessions.map(s => `
          <div class="transaction-item">
            <div class="txn-left">
              <span class="txn-desc">${s.session_type === 'focus' ? 'Foco' : 'Pausa'} ${s.task_title ? `- ${escapeHtml(s.task_title)}` : ''}</span>
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
      showToast(isRec ? 'Regra fixa e lançamento registrados!' : 'Lançamento salvo!');
      await loadFinanceData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao registrar transação');
    }
  }

  function openFinanceImportModal() {
    const modal = document.getElementById('modal-finance-import');
    if (!modal) return;
    const form = document.getElementById('form-finance-import');
    if (form) form.reset();
    const resultBox = document.getElementById('import-result-box');
    if (resultBox) {
      resultBox.style.display = 'none';
      resultBox.innerHTML = '';
    }
    modal.classList.add('active');
  }

  async function submitFinanceImport(e) {
    e.preventDefault();
    const fileInput = document.getElementById('import-file-input');
    const accountSelect = document.getElementById('import-account-select');
    const submitBtn = document.getElementById('btn-submit-import');
    const resultBox = document.getElementById('import-result-box');

    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      alert('Selecione um arquivo .OFX ou .CSV para importar.');
      return;
    }

    const file = fileInput.files[0];
    const account = accountSelect ? accountSelect.value : 'Nubank';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('account', account);

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerText = 'Processando...';
    }

    try {
      const res = await apiFetch('/api/finances/import', {
        method: 'POST',
        body: formData
      });

      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = `
          <div style="font-weight:600; margin-bottom:4px; color:var(--accent-income);">Importação concluída!</div>
          <div>Lançamentos importados: <strong>${res.imported || 0}</strong></div>
          <div>Duplicados conciliados: <strong>${res.reconciled_duplicates || 0}</strong></div>
          <div>Total processados: <strong>${res.total_processed || 0}</strong></div>
        `;
      }

      showToast(`Importação concluída: ${res.imported || 0} novos, ${res.reconciled_duplicates || 0} conciliados!`);
      await loadFinanceData();
      loadOverviewData();

      setTimeout(() => {
        closeModals();
      }, 1600);
    } catch (err) {
      alert('Erro na importação: ' + (err.message || 'Falha ao processar arquivo'));
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = 'Importar e Conciliar';
      }
    }
  }

  function searchFinanceClientSide(query) {
    state.financeSearchQuery = (query || '').trim().toLowerCase();
    renderTransactionsList();
  }

  function filterFinance(filterType, btnEl) {
    state.financeFilter = filterType;
    const pills = document.querySelectorAll('#finance-filter-bar .stage-pill');
    pills.forEach(b => b.classList.remove('active'));
    if (btnEl) {
      btnEl.classList.add('active');
    } else if (filterType && filterType.startsWith('cat:')) {
      const catLabel = filterType.slice(4).toLowerCase();
      pills.forEach(b => {
        if ((b.textContent || '').trim().toLowerCase() === catLabel) {
          b.classList.add('active');
        }
      });
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
      if (recIncSub) recIncSub.innerText = `Fixos: ${formatMoney(summary.recurring_income_cents || 0)}`;
      if (recExpSub) recExpSub.innerText = `Fixos: ${formatMoney(summary.recurring_expense_cents || 0)}`;

      state.recurringRules = summary.recurring_rules || [];

      const breakdownCard = document.getElementById('finance-breakdown-card');
      const breakdownList = document.getElementById('fin-categories-list');
      const cats = Object.entries(summary.categories_breakdown || {});
      if (cats.length > 0) {
        breakdownCard.style.display = 'block';
        breakdownList.innerHTML = cats.map(([cat, val]) => `
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.875rem; cursor:pointer; padding:4px 6px; border-radius:6px; background:var(--bg-surface-elevated);" title="Clique para filtrar por ${escapeHtml(cat)}" onclick="App.filterFinance('cat:${escapeHtml(cat)}')">
            <span style="color:var(--text-primary); font-weight:500;">${escapeHtml(cat)}</span>
            <span style="font-family:var(--font-mono); font-weight:600; color:var(--accent-expense);">${formatMoney(val)}</span>
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

  async function updateTransactionCategory(txnId, newCategory) {
    try {
      await apiFetch(`/api/finance/transactions/${txnId}`, {
        method: 'PATCH',
        body: JSON.stringify({ category: newCategory })
      });
      showToast(`Categoria alterada para ${newCategory}`);
      await loadFinanceData();
    } catch (e) {
      showToast('Erro ao alterar categoria');
    }
  }

  function renderTransactionsList() {
    const listEl = document.getElementById('finance-transactions-list');
    const statsBar = document.getElementById('finance-list-stats-bar');
    if (!listEl) return;

    let filtered = state.transactions || [];
    if (state.financeFilter === 'recurring') {
      filtered = filtered.filter(t => Number(t.is_recurring) === 1);
    } else if (state.financeFilter === 'income' || state.financeFilter === 'expense') {
      filtered = filtered.filter(t => t.type === state.financeFilter);
    } else if (state.financeFilter && state.financeFilter.startsWith('cat:')) {
      const targetCat = state.financeFilter.slice(4).toLowerCase();
      filtered = filtered.filter(t => (t.category || 'Outros').toLowerCase() === targetCat);
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
      if (statsBar) statsBar.style.display = 'none';
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">Nenhuma movimentação encontrada</div>
          <div class="empty-desc">Nenhum lançamento corresponde ao filtro atual.</div>
          <button class="btn btn-secondary btn-sm" onclick="App.filterFinance('all', document.querySelector('#finance-filter-bar .stage-pill'))">Mostrar Todos</button>
        </div>
      `;
      return;
    }

    // Calcula somas da listagem filtrada para conferência transparente
    let incCents = 0;
    let expCents = 0;
    filtered.forEach(t => {
      if (t.type === 'income') incCents += (t.amount_cents || 0);
      else expCents += (t.amount_cents || 0);
    });
    const netFiltered = incCents - expCents;

    if (statsBar) {
      statsBar.style.display = 'flex';
      statsBar.innerHTML = `
        <div>Mostrando <strong>${filtered.length}</strong> de <strong>${(state.transactions || []).length}</strong> registros</div>
        <div>Saldo do filtro: <strong style="color:${netFiltered >= 0 ? 'var(--accent-income)' : 'var(--accent-expense)'};">${formatMoney(netFiltered)}</strong> (Receitas: ${formatMoney(incCents)} | Despesas: ${formatMoney(expCents)})</div>
      `;
    }

    const availableCats = ['Educação', 'Saúde', 'Lazer', 'Alimentação', 'Transporte', 'Moradia', 'Salário', 'Outros'];

    listEl.innerHTML = filtered.map(t => {
      const attCount = Number(t.attachments_count || 0);
      const isReconciled = Number(t.reconciled || 0) === 1;
      const isRec = Number(t.is_recurring || 0) === 1;
      const src = t.source || 'manual';
      const curCat = t.category || 'Outros';
      const catOptions = availableCats.includes(curCat) ? availableCats : [curCat, ...availableCats];

      let sourceBadge = '';
      if (src === 'webhook') {
        sourceBadge = '<span class="badge badge-source-webhook" title="Capturado via Notificação em Tempo Real">Notificação</span>';
      } else if (src === 'ofx') {
        sourceBadge = '<span class="badge badge-source-statement" title="Importado via Extrato OFX">Extrato OFX</span>';
      } else if (src === 'csv') {
        sourceBadge = '<span class="badge badge-source-statement" title="Importado via Extrato CSV">Extrato CSV</span>';
      }

      const reconciledBadge = isReconciled ? '<span class="badge badge-reconciled" title="Auditado e conciliado com extrato bancário">Conciliado</span>' : '';
      const recBadge = isRec ? `<span class="badge badge-recurring">${escapeHtml(t.recurrence || 'mensal')}</span>` : '';

      return `
        <div class="transaction-item">
          <div class="txn-left">
            <div class="txn-desc">
              <span>${escapeHtml(t.description)}</span>
              ${sourceBadge}
              ${reconciledBadge}
              ${recBadge}
            </div>
            <div class="txn-sub" style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:4px;">
              <strong>${formatDateFull(t.date)}</strong>
              <span>•</span>
              <select class="form-select" style="width:auto; min-height:26px; padding:1px 22px 1px 8px; font-size:0.75rem; border-radius:6px; background:var(--bg-surface-elevated);" title="Alterar categoria" onchange="App.updateTransactionCategory(${t.id}, this.value)">
                ${catOptions.map(c => `<option value="${escapeHtml(c)}" ${c === curCat ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}
              </select>
              <span>•</span>
              <span>${escapeHtml(t.account || 'Conta Corrente')}</span>
              ${t.task_title ? `<span>• Tarefa: ${escapeHtml(t.task_title)}</span>` : ''}
              ${t.goal_title ? `<span>• Meta: ${escapeHtml(t.goal_title)}</span>` : ''}
            </div>
          </div>
          <div class="txn-right-col" style="display:flex; align-items:center; gap:8px;">
            <span class="txn-amount ${t.type === 'income' ? 'flow-income' : 'flow-expense'}">
              ${t.type === 'income' ? '+' : '-'} ${formatMoney(t.amount_cents)}
            </span>
            <button class="btn btn-secondary btn-sm" style="min-height:36px; padding:2px 8px;" title="Comprovantes e Anexos" onclick="App.openAttachmentsModal('transaction', ${t.id}, '${escapeHtml(t.description)}')">${attCount > 0 ? `Anexos (${attCount})` : '+ Anexo'}</button>
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
                <span class="badge ${isActive ? 'badge-recurring' : 'badge-paused'}">${isActive ? 'Ativa' : 'Pausada'}</span>
                ${escapeHtml(r.description)}
              </span>
              <span class="txn-sub">
                Todo dia <strong>${r.day_of_month || 1}</strong> • ${escapeHtml(r.frequency || 'mensal')} • ${escapeHtml(r.category || 'Outros')}
              </span>
            </div>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              <span class="txn-amount ${isInc ? 'flow-income' : 'flow-expense'}">
                ${isInc ? '+' : '-'} ${formatMoney(amtCents)}
              </span>
              <button class="btn btn-secondary btn-sm" onclick="App.openRecurringRuleModal(${r.id})">Editar</button>
              <button class="btn btn-secondary btn-sm" onclick="App.toggleRecurringRuleActive(${r.id}, ${!isActive})">${isActive ? 'Pausar' : 'Reativar'}</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteRecurringRule(${r.id})">Excluir</button>
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
        showToast('Regra recorrente atualizada!');
      } else {
        await apiFetch('/api/finance/recurring-rules', { method: 'POST', body: JSON.stringify(payload) });
        showToast('Nova regra fixa criada!');
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
      showToast(makeActive ? 'Regra reativada!' : 'Regra pausada!');
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
      showToast('Regra recorrente removida');
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
      showToast('Movimentação removida');
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

    const isIdeaConverted = (i) => i.status === 'convertida' || Boolean(i.converted_task_id) || i.stage === 'in_action';

    if (state.ideaStageFilter === 'all') {
      filtered = filtered.filter(i => !isIdeaConverted(i) && i.stage !== 'archived');
    } else if (state.ideaStageFilter === 'in_action') {
      filtered = filtered.filter(i => isIdeaConverted(i));
    } else if (state.ideaStageFilter === 'archived') {
      filtered = filtered.filter(i => i.stage === 'archived');
    } else {
      filtered = filtered.filter(i => i.stage === state.ideaStageFilter && !isIdeaConverted(i));
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
          
          <div class="empty-title">Nenhuma ideia encontrada</div>
          <div class="empty-desc">Registre insights rápidos na incubadora e converta em tarefas com 1 clique.</div>
          <button class="btn btn-ideas" onclick="App.openIdeaModal()">+ Nova Ideia</button>
        </div>
      `;
      return;
    }

    const stageMap = {
      raw: 'Bruta',
      evaluating: 'Em Análise',
      in_action: 'Em Ação',
      archived: 'Arquivada'
    };

    container.innerHTML = filtered.map(i => {
      const isConverted = isIdeaConverted(i);
      const attCount = Number(i.attachments_count || 0);
      const isChecklist = i.note_type === 'checklist';
      const chkData = isChecklist ? renderChecklistPreviewForCard('idea', i.id, i.content) : null;
      const menuId = `kebab-idea-${i.id}`;

      return `
        <div class="idea-card">
          <div class="card-top-row">
            <div class="card-header">
              <div class="card-badges">
                ${isConverted ? `<span class="badge badge-recurring">Tarefa #${i.converted_task_id || ''}</span>` : ''}
                <span class="badge badge-medium">${stageMap[i.stage] || i.stage}</span>
              </div>
              <h4 class="idea-title">${escapeHtml(i.title)}</h4>
            </div>
            <div class="card-kebab-wrap">
              <button type="button" class="btn-card-kebab" onclick="App.toggleCardMenu(event, '${menuId}')" aria-label="Mais opções">&#8942;</button>
              <div class="card-kebab-menu" id="${menuId}">
                <button type="button" class="card-kebab-item" onclick="App.openIdeaModal(${i.id})">Editar</button>
                ${!isConverted ? `<button type="button" class="card-kebab-item" onclick="App.convertIdeaToTask(${i.id})">Converter em Tarefa</button>` : ''}
                <button type="button" class="card-kebab-item" onclick="App.openAttachmentsModal('idea', ${i.id}, '${escapeHtml(i.title)}')">Anexos (${attCount})</button>
                ${i.stage !== 'evaluating' ? `<button type="button" class="card-kebab-item" onclick="App.changeIdeaStage(${i.id}, 'evaluating')">Mover p/ Em Análise</button>` : ''}
                ${i.stage !== 'archived' ? `<button type="button" class="card-kebab-item" onclick="App.changeIdeaStage(${i.id}, 'archived')">Arquivar Ideia</button>` : `<button type="button" class="card-kebab-item" onclick="App.changeIdeaStage(${i.id}, 'raw')">Restaurar p/ Bruta</button>`}
                <button type="button" class="card-kebab-item danger" onclick="App.deleteIdea(${i.id})">Excluir</button>
              </div>
            </div>
          </div>
          ${isChecklist ? chkData.itemsHtml : (i.content ? `<div class="idea-content">${escapeHtml(i.content)}</div>` : '')}
          <div class="task-actions">
            <div>${isChecklist ? chkData.counterHtml : ''}</div>
            <button class="btn btn-secondary btn-sm" onclick="App.openIdeaModal(${i.id})">Editar</button>
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
      showToast(`Ideia convertida na Tarefa #${res.task.id}!`);
      await loadIdeasData();
      await loadTasksData();
      loadOverviewData();
    } catch (err) {
      alert(err.message || 'Erro ao converter ideia em tarefa');
    }
  }

  function setIdeaNoteType(targetType = 'text') {
    const prevType = state.currentIdeaNoteType;
    const textGroup = document.getElementById('idea-text-group');
    const chkGroup = document.getElementById('idea-checklist-group');
    const typeInput = document.getElementById('idea-note-type-input');
    const textarea = document.getElementById('idea-content-input');

    document.getElementById('btn-idea-type-text')?.classList.toggle('active', targetType === 'text');
    document.getElementById('btn-idea-type-checklist')?.classList.toggle('active', targetType === 'checklist');

    if (targetType === 'checklist') {
      if (prevType === 'text' && textarea && textarea.value.trim()) {
        const rawVal = textarea.value.trim();
        if (rawVal.startsWith('[')) {
          state.currentIdeaChecklist = parseChecklistItems(rawVal);
        } else {
          state.currentIdeaChecklist = textarea.value
            .split('\n')
            .map(line => line.trim())
            .filter(Boolean)
            .map(text => ({ text, done: false }));
        }
      }
      if (textGroup) textGroup.style.display = 'none';
      if (chkGroup) chkGroup.style.display = 'block';
      if (typeInput) typeInput.value = 'checklist';
      state.currentIdeaNoteType = 'checklist';
      renderChecklistDom('idea');
    } else {
      if (prevType === 'checklist' && Array.isArray(state.currentIdeaChecklist) && state.currentIdeaChecklist.length > 0 && textarea) {
        textarea.value = state.currentIdeaChecklist.map(it => it.text).join('\n');
      }
      if (textGroup) textGroup.style.display = 'block';
      if (chkGroup) chkGroup.style.display = 'none';
      if (typeInput) typeInput.value = 'text';
      state.currentIdeaNoteType = 'text';
    }
  }

  function openIdeaModal(ideaId = null) {
    const modal = document.getElementById('modal-idea');
    const titleEl = document.getElementById('modal-idea-title');
    const form = document.getElementById('form-idea');
    const deleteBtn = document.getElementById('btn-delete-modal-idea');
    form.reset();
    state.currentIdeaChecklist = [];
    state.currentIdeaNoteType = 'text';

    if (ideaId) {
      const idea = state.ideas.find(i => i.id === ideaId);
      if (idea) {
        titleEl.innerText = 'Editar Ideia';
        document.getElementById('idea-id').value = idea.id;
        document.getElementById('idea-title-input').value = idea.title;
        document.getElementById('idea-stage-select').value = idea.stage;
        document.getElementById('idea-tags-input').value = idea.tags || '';
        if (idea.note_type === 'checklist') {
          state.currentIdeaNoteType = 'checklist';
          state.currentIdeaChecklist = parseChecklistItems(idea.content);
          document.getElementById('idea-content-input').value = '';
          setIdeaNoteType('checklist');
        } else {
          state.currentIdeaNoteType = 'text';
          document.getElementById('idea-content-input').value = idea.content || '';
          setIdeaNoteType('text');
        }
        if (deleteBtn) deleteBtn.style.display = 'inline-block';
      }
    } else {
      titleEl.innerText = 'Nova Ideia';
      document.getElementById('idea-id').value = '';
      document.getElementById('idea-stage-select').value = 'raw';
      setIdeaNoteType('text');
      if (deleteBtn) deleteBtn.style.display = 'none';
    }
    modal.classList.add('active');
  }

  async function deleteCurrentModalIdea() {
    const id = document.getElementById('idea-id').value;
    if (!id) return;
    closeModals();
    await deleteIdea(Number(id));
  }

  async function saveIdea(e) {
    e.preventDefault();
    const id = document.getElementById('idea-id').value;
    const isChecklist = state.currentIdeaNoteType === 'checklist';
    const pendingInput = document.getElementById('idea-checklist-new-input');
    if (isChecklist && pendingInput && pendingInput.value.trim()) {
      state.currentIdeaChecklist.push({ text: pendingInput.value.trim(), done: false });
      pendingInput.value = '';
    }
    const payload = {
      title: document.getElementById('idea-title-input').value.trim(),
      stage: document.getElementById('idea-stage-select').value,
      note_type: isChecklist ? 'checklist' : 'text',
      content: isChecklist ? JSON.stringify(state.currentIdeaChecklist) : document.getElementById('idea-content-input').value.trim(),
      tags: document.getElementById('idea-tags-input').value.trim()
    };

    try {
      if (id) {
        await apiFetch(`/api/ideas/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await apiFetch('/api/ideas', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeModals();
      showToast('Ideia salva!');
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
      showToast('Ideia excluída');
      await loadIdeasData();
      loadOverviewData();
    } catch (e) {
      alert('Erro ao excluir ideia');
    }
  }

  // ---------------- SYSTEM BACKUP, EXPORT & MOBILE CONFIG (RF02, RF03, RF04) ----------------
  function openSystemModal() {
    const input = document.getElementById('setting-api-origin');
    if (input) {
      input.value = localStorage.getItem('dream_api_origin') || (IS_NATIVE_APK ? DEFAULT_TAILSCALE_SERVER : window.location.origin);
    }
    const badge = document.getElementById('setting-app-mode-badge');
    if (badge) {
      badge.innerText = IS_NATIVE_APK ? 'Aplicativo Android Nativo (APK)' : 'Navegador Web / PWA';
    }
    testServerConnection();
    document.getElementById('modal-system')?.classList.add('active');
  }

  function saveServerOrigin() {
    const input = document.getElementById('setting-api-origin');
    if (!input) return;
    const val = input.value.trim().replace(/\/+$/, '');
    if (!val) {
      localStorage.removeItem('dream_api_origin');
      showToast('Restaurado para o endereço padrão da Tailscale.');
    } else {
      localStorage.setItem('dream_api_origin', val);
      showToast(`Servidor configurado: ${val}`);
    }
    testServerConnection();
  }

  async function testServerConnection() {
    const statusEl = document.getElementById('setting-api-status');
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--text-muted); font-size:0.8125rem;">Testando comunicação com o servidor...</span>';
    try {
      const origin = getApiOrigin();
      const testUrl = `${origin}/api/health`;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 3500);
      const res = await _originalFetch(testUrl, { signal: ctrl.signal });
      clearTimeout(timer);
      if (res.ok) {
        const data = await res.json();
        if (statusEl) {
          statusEl.innerHTML = `<span style="color:#22c55e; font-size:0.8125rem; font-weight:600;">Conectado ao ${data.app || 'Dream Hub'} (${data.version || 'v1.3.0'}) via Tailscale!</span>`;
        }
      } else {
        if (statusEl) {
          statusEl.innerHTML = `<span style="color:#ef4444; font-size:0.8125rem;">Servidor respondeu com código HTTP ${res.status}.</span>`;
        }
      }
    } catch (e) {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#ef4444; font-size:0.8125rem;">Servidor inalcançável. Verifique se o Tailscale está ativo neste aparelho e se o Redmi A3 está online.</span>';
      }
    }
  }

  function triggerSafeDownload(url, toastMsg = 'Iniciando download...') {
    const fullUrl = window.resolveApiUrl(url);
    const a = document.createElement('a');
    a.href = fullUrl;
    a.setAttribute('download', '');
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (a.parentNode) a.parentNode.removeChild(a);
    }, 400);
    if (toastMsg) showToast(toastMsg);
  }

  function downloadHotBackup() {
    triggerSafeDownload('/api/system/backup', 'Baixando snapshot SQLite (.db)...');
  }

  function exportData(module = 'all', format = 'csv', month = '') {
    let url = `/api/system/export?module=${encodeURIComponent(module)}&format=${encodeURIComponent(format)}`;
    if (month && month !== 'all') {
      url += `&month=${encodeURIComponent(month)}`;
    }
    triggerSafeDownload(url, `Baixando exportação (${format.toUpperCase()})...`);
  }

  function openFinanceExportModal() {
    const modal = document.getElementById('modal-finance-export');
    if (!modal) return;
    const monthInput = document.getElementById('finance-month-input');
    const curMonth = monthInput ? monthInput.value : state.financeMonth;
    const labelEl = document.getElementById('fin-export-month-label');
    if (labelEl) {
      labelEl.innerText = curMonth || 'Mês Atual';
    }
    const scopeCur = document.getElementById('fin-export-scope-current');
    if (scopeCur) scopeCur.checked = true;
    modal.classList.add('active');
  }

  function confirmFinanceExport(format = 'csv') {
    const isAll = document.getElementById('fin-export-scope-all')?.checked;
    const monthInput = document.getElementById('finance-month-input');
    const selectedMonth = isAll ? 'all' : (monthInput ? monthInput.value : state.financeMonth);
    exportData('finance', format, selectedMonth);
    closeModals();
  }

  function openFinanceClearModal() {
    const modal = document.getElementById('modal-finance-clear');
    if (!modal) return;
    const monthInput = document.getElementById('finance-month-input');
    const curMonth = monthInput ? monthInput.value : state.financeMonth;
    const labelEl = document.getElementById('fin-clear-month-label');
    if (labelEl) {
      labelEl.innerText = curMonth || 'Mês Atual';
    }
    const scopeAll = document.getElementById('fin-clear-scope-all');
    if (scopeAll) scopeAll.checked = true;
    const incRules = document.getElementById('fin-clear-include-rules');
    if (incRules) incRules.checked = false;
    modal.classList.add('active');
  }

  async function confirmFinanceClear(e) {
    if (e) e.preventDefault();
    const isMonth = document.getElementById('fin-clear-scope-month')?.checked;
    const monthInput = document.getElementById('finance-month-input');
    const selectedMonth = monthInput ? monthInput.value : state.financeMonth;
    const includeRules = Boolean(document.getElementById('fin-clear-include-rules')?.checked);

    const scopeText = isMonth ? `do mês ${selectedMonth}` : 'de TODO o histórico';
    const rulesText = includeRules ? ' e TODAS as regras fixas' : '';
    if (!confirm(`CONFIRMAÇÃO FINAL: Deseja realmente excluir todas as movimentações financeiras ${scopeText}${rulesText}? Esta ação NÃO poderá ser desfeita!`)) {
      return;
    }

    const submitBtn = document.getElementById('btn-submit-clear-finance');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerText = 'Excluindo...';
    }

    try {
      const res = await apiFetch('/api/finance/clear', {
        method: 'POST',
        body: {
          scope: isMonth ? 'month' : 'all',
          month: selectedMonth,
          include_rules: includeRules
        }
      });

      closeModals();
      showToast(`Remoção concluída: ${res.deleted_transactions || 0} lançamentos apagados.`);
      await loadFinanceData();
      loadOverviewData();
    } catch (err) {
      alert('Erro ao limpar finanças: ' + (err.message || 'Falha na requisição'));
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = 'Zerar e Excluir';
      }
    }
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('active');
  }

  function closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
  }

  function showError(containerId, message, retryFn) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
      <div class="error-state">
        <span>${escapeHtml(message)}</span>
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

    loadPomodoroState();

    // Listeners do Construtor Dinâmico de Checklist (DOM Manipulation pura)
    const btnIdeaChkAdd = document.getElementById('btn-idea-checklist-add');
    if (btnIdeaChkAdd) {
      btnIdeaChkAdd.addEventListener('click', () => addChecklistItemFromInput('idea'));
    }
    const inputIdeaChk = document.getElementById('idea-checklist-new-input');
    if (inputIdeaChk) {
      inputIdeaChk.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          addChecklistItemFromInput('idea');
        }
      });
    }

    const btnNoteChkAdd = document.getElementById('btn-note-checklist-add');
    if (btnNoteChkAdd) {
      btnNoteChkAdd.addEventListener('click', () => addChecklistItemFromInput('note'));
    }
    const inputNoteChk = document.getElementById('note-checklist-new-input');
    if (inputNoteChk) {
      inputNoteChk.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          addChecklistItemFromInput('note');
        }
      });
    }

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModals();
    });

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        syncTimerFromTimestamp();
        syncRitmoRestTimerFromTimestamp();
      }
    });

    window.addEventListener('focus', () => {
      syncTimerFromTimestamp();
      syncRitmoRestTimerFromTimestamp();
    });

    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModals();
      });
    });

    setupPwaLifecycle();
    initRoutineWebWorker();

    loadOverviewData();
    loadTasksData();
    loadGoalsData();

    // Suporte a atalhos de ícone do Android PWA (manifest shortcuts ?tab=...)
    try {
      const params = new URLSearchParams(window.location.search);
      const initialTab = params.get('tab');
      const allowedTabs = ['overview', 'finance', 'tasks', 'ritmo', 'ideas', 'goals', 'sleep', 'time', 'notes', 'routines'];
      if (initialTab && allowedTabs.includes(initialTab)) {
        navigateTo(initialTab);
      }
    } catch (_) {}
  }

  // ==================== PWA / WEBAPK LIFECYCLE ====================
  let deferredPwaPrompt = null;

  function isStandalonePwa() {
    return IS_NATIVE_APK ||
      (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
      window.navigator.standalone === true;
  }

  function setupPwaLifecycle() {
    const installBtn = document.getElementById('btn-install-pwa');

    if (IS_NATIVE_APK) {
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.getRegistrations().then(regs => {
          regs.forEach(r => r.unregister());
        }).catch(() => {});
      }
      if (installBtn) installBtn.style.display = 'none';
      return;
    }

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' })
        .then(reg => { reg.update().catch(() => {}); })
        .catch(err => { console.warn('PWA SW registration skipped:', err); });
    }

    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPwaPrompt = e;
      if (installBtn && !isStandalonePwa()) {
        installBtn.style.display = 'block';
      }
    });

    window.addEventListener('appinstalled', () => {
      deferredPwaPrompt = null;
      if (installBtn) installBtn.style.display = 'none';
      showToast('Dream Hub instalado como aplicativo nativo!');
    });
  }

  async function installPwa() {
    const menu = document.getElementById('dropdown-nav-menu');
    if (menu) menu.classList.remove('open');

    if (deferredPwaPrompt) {
      deferredPwaPrompt.prompt();
      const choice = await deferredPwaPrompt.userChoice;
      if (choice && choice.outcome === 'accepted') {
        deferredPwaPrompt = null;
        const installBtn = document.getElementById('btn-install-pwa');
        if (installBtn) installBtn.style.display = 'none';
      }
      return;
    }

    showToast('No Chrome Android (HTTPS :8445), abra o menu ⋮ e toque em "Instalar aplicativo".');
  }

  // ==================== RITMO MODULE (v1.3 FASE 2) ====================
  let currentActiveWorkout = null;
  let allExercisesList = [];
  let allRoutinesList = [];
  let selectedRitmoMonth = new Date().toISOString().slice(0, 7);

  // ---------------- TIMER FLUTUANTE DE DESCANSO (Date.now() Resiliente) ----------------
  let ritmoRestTimerInterval = null;
  let ritmoRestTimerEndMs = 0;

  function formatRestClock(totalSeconds) {
    const sec = Math.max(0, Math.ceil(totalSeconds));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function syncRitmoRestTimerFromTimestamp() {
    if (!ritmoRestTimerEndMs) return;
    const widget = document.getElementById('ritmo-rest-timer-widget');
    const clockEl = document.getElementById('ritmo-rest-timer-clock');
    const remainingSec = Math.ceil((ritmoRestTimerEndMs - Date.now()) / 1000);
    if (remainingSec <= 0) {
      stopRitmoRestTimer();
      playCompletionChime();
      showToast('Tempo de descanso finalizado! Próxima série.');
      return;
    }
    if (clockEl) {
      clockEl.textContent = formatRestClock(remainingSec);
    }
    if (widget && widget.style.display === 'none') {
      widget.style.display = 'flex';
    }
  }

  function startRitmoRestTimer(restSeconds = 90, exerciseName = 'Descanso') {
    const durationSec = Math.max(5, parseInt(restSeconds, 10) || 90);
    ritmoRestTimerEndMs = Date.now() + durationSec * 1000;

    const widget = document.getElementById('ritmo-rest-timer-widget');
    const labelEl = document.getElementById('ritmo-rest-timer-label');
    const clockEl = document.getElementById('ritmo-rest-timer-clock');

    if (labelEl) labelEl.textContent = exerciseName ? `Descanso • ${exerciseName}` : 'Descanso';
    if (clockEl) clockEl.textContent = formatRestClock(durationSec);
    if (widget) widget.style.display = 'flex';

    if (ritmoRestTimerInterval) {
      clearInterval(ritmoRestTimerInterval);
    }
    ritmoRestTimerInterval = setInterval(() => {
      syncRitmoRestTimerFromTimestamp();
    }, 1000);
  }

  function adjustRitmoRestTimer(deltaSeconds) {
    if (!ritmoRestTimerEndMs) return;
    ritmoRestTimerEndMs = Math.max(Date.now() + 1000, ritmoRestTimerEndMs + (deltaSeconds * 1000));
    syncRitmoRestTimerFromTimestamp();
  }

  function stopRitmoRestTimer() {
    if (ritmoRestTimerInterval) {
      clearInterval(ritmoRestTimerInterval);
      ritmoRestTimerInterval = null;
    }
    ritmoRestTimerEndMs = 0;
    const widget = document.getElementById('ritmo-rest-timer-widget');
    if (widget) widget.style.display = 'none';
  }

  function setRitmoTab(tab) {
    ['treino', 'calendario', 'rotinas', 'exercicios', 'peso', 'historico'].forEach(t => {
      const el = document.getElementById(`ritmo-subview-${t}`);
      const btn = document.getElementById(`btn-ritmo-${t}`);
      if (el) el.style.display = (t === tab) ? 'block' : 'none';
      if (btn) btn.classList.toggle('active', t === tab);
    });
    if (tab === 'treino') loadActiveWorkout();
    else if (tab === 'calendario') loadRitmoCalendar(selectedRitmoMonth);
    else if (tab === 'rotinas') loadRoutines();
    else if (tab === 'exercicios') loadExercises();
    else if (tab === 'peso') {
      loadWeightHistory();
      loadEvolutionPhotos();
      loadRitmoExerciseEvolutionInit();
    }
    else if (tab === 'historico') loadWorkoutsHistory();
  }

  async function loadRitmoData() {
    await loadActiveWorkout();
    loadExercises();
    loadRoutines();
    if (selectedRitmoMonth) loadRitmoCalendar(selectedRitmoMonth);
  }

  // ---------------- CALENDÁRIO / MATRIZ TEMPORAL (RF04) ----------------
  function onRitmoCalendarMonthChange(mVal) {
    if (!mVal) return;
    selectedRitmoMonth = mVal;
    loadRitmoCalendar(mVal);
  }

  async function loadRitmoCalendar(monthStr) {
    const gridEl = document.getElementById('ritmo-calendar-grid');
    const monthInput = document.getElementById('ritmo-calendar-month-input');
    const monthTitle = document.getElementById('ritmo-calendar-month-title');
    if (!gridEl) return;

    if (!monthStr) {
      monthStr = selectedRitmoMonth || new Date().toISOString().slice(0, 7);
    }
    selectedRitmoMonth = monthStr;
    if (monthInput && monthInput.value !== monthStr) {
      monthInput.value = monthStr;
    }

    try {
      const [yStr, mStr] = monthStr.split('-');
      const year = parseInt(yStr, 10);
      const month = parseInt(mStr, 10);
      const monthDate = new Date(year, month - 1, 1);
      const monthLabel = monthDate.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
      if (monthTitle) {
        monthTitle.innerText = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
      }

      const [monthData, workouts] = await Promise.all([
        apiFetch(`/api/calendar/month?month=${monthStr}`),
        apiFetch(`/api/workouts?month=${monthStr}`)
      ]);

      const trainedSet = new Set(monthData.trained_dates || []);
      const stoppedSet = new Set(monthData.stopped_dates || []);
      const scheduledSet = new Set(monthData.scheduled_dates || []);
      const todayStr = new Date().toISOString().slice(0, 10);

      const totalWorkoutsEl = document.getElementById('ritmo-cal-total-workouts');
      const trainedDaysEl = document.getElementById('ritmo-cal-trained-days');
      const scheduledDaysEl = document.getElementById('ritmo-cal-scheduled-days');
      if (totalWorkoutsEl) totalWorkoutsEl.innerText = (workouts || []).length;
      if (trainedDaysEl) trainedDaysEl.innerText = trainedSet.size + stoppedSet.size;
      if (scheduledDaysEl) scheduledDaysEl.innerText = scheduledSet.size;

      const firstDayWeekIndex = new Date(year, month - 1, 1).getDay();
      const daysInMonth = new Date(year, month, 0).getDate();

      let html = '';
      const weekdays = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
      weekdays.forEach(w => {
        html += `<div class="calendar-weekday">${w}</div>`;
      });

      for (let i = 0; i < firstDayWeekIndex; i++) {
        html += `<div class="calendar-day empty"></div>`;
      }

      for (let day = 1; day <= daysInMonth; day++) {
        const dStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const isTrained = trainedSet.has(dStr);
        const isStopped = stoppedSet.has(dStr);
        const isScheduled = scheduledSet.has(dStr);
        const isToday = (dStr === todayStr);

        const classes = ['calendar-day'];
        if (isToday) classes.push('today');
        if (isTrained) classes.push('trained');
        if (isStopped) classes.push('stopped');
        if (isScheduled) classes.push('scheduled');

        let dotsHtml = '';
        if (isTrained) dotsHtml += '<span class="cal-dot trained" title="Treino realizado"></span>';
        if (isStopped) dotsHtml += '<span class="cal-dot stopped" title="Treino interrompido (Stop)"></span>';
        if (isScheduled) dotsHtml += '<span class="cal-dot scheduled" title="Treino agendado"></span>';

        html += `
          <button type="button" class="${classes.join(' ')}" onclick="App.openRitmoDayDetails('${dStr}')" aria-label="Dia ${day}">
            <span>${day}</span>
            <div class="calendar-day-dots">${dotsHtml}</div>
          </button>
        `;
      }

      gridEl.innerHTML = html;
    } catch (e) {
      console.error('Falha ao renderizar calendário do Ritmo:', e);
      gridEl.innerHTML = `<div class="error-state" style="grid-column:1/-1;">Erro ao carregar calendário: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function openRitmoDayDetails(dateStr) {
    const modal = document.getElementById('modal-ritmo-day-details');
    const title = document.getElementById('ritmo-day-modal-title');
    const body = document.getElementById('ritmo-day-modal-body');
    if (!modal || !body) return;

    const [y, m, d] = dateStr.split('-');
    const formatted = `${d}/${m}/${y}`;
    if (title) title.innerText = `Detalhes de ${formatted}`;
    body.innerHTML = '<div class="skeleton"></div><p style="text-align:center; color:var(--text-muted); font-size:0.875rem;">Carregando estado do dia...</p>';
    modal.classList.add('active');

    try {
      const [dayData, routines] = await Promise.all([
        apiFetch(`/api/calendar/day/${dateStr}`),
        apiFetch('/api/routines')
      ]);
      allRoutinesList = routines || [];

      let contentHtml = '';
      const stateType = dayData.state;

      if ((stateType === 'past_trained' || stateType === 'today_trained') && dayData.workout) {
        const w = dayData.workout;
        let setsSummary = '';
        (w.items || []).forEach(it => {
          const completedSets = (it.sets || []).filter(s => s.done);
          setsSummary += `<div style="font-size:0.8125rem; margin-bottom:4px;"><strong>${escapeHtml(it.name)}</strong>: ${completedSets.length}/${(it.sets || []).length} séries concluídas${it.notes ? ` • <em>${escapeHtml(it.notes)}</em>` : ''}</div>`;
        });

        contentHtml = `
          <div class="temporal-card temporal-past-trained">
            <span style="color:#22c55e; font-size:0.75rem; font-weight:700; text-transform:uppercase;">
              ${stateType === 'today_trained' ? 'Treino Concluído' : 'Treino Realizado no Passado'}
            </span>
            <h4 style="font-size:1.1rem; font-weight:700; margin:4px 0 8px;">${escapeHtml(w.routine_name)}</h4>
            <div style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:12px;">
              ${w.finished_at ? `Finalizado às ${w.finished_at.slice(11, 16)}` : `Data: ${formatted}`}
              ${w.notes ? `<br><em>Notas: ${escapeHtml(w.notes)}</em>` : ''}
            </div>
            <div class="card" style="margin-bottom:12px; background:rgba(0,0,0,0.2);">
              ${setsSummary || '<span class="text-muted">Nenhum exercício registrado</span>'}
            </div>
            <div style="display:flex; justify-content:flex-end;">
              <button class="btn btn-secondary btn-sm" style="color:var(--danger, #ef4444);" onclick="App.deleteWorkoutFromCalendar(${w.id}, '${dateStr}')">Excluir Registro</button>
            </div>
          </div>
        `;
      } else if (stateType === 'past_stopped' && dayData.workout) {
        const w = dayData.workout;
        let setsSummary = '';
        (w.items || []).forEach(it => {
          const completedSets = (it.sets || []).filter(s => s.done);
          setsSummary += `<div style="font-size:0.8125rem; margin-bottom:4px;"><strong>${escapeHtml(it.name)}</strong>: ${completedSets.length}/${(it.sets || []).length} séries registradas${it.notes ? ` • <em>${escapeHtml(it.notes)}</em>` : ''}</div>`;
        });

        contentHtml = `
          <div class="temporal-card temporal-past-stopped">
            <span style="color:#ef4444; font-size:0.75rem; font-weight:700; text-transform:uppercase;">
              Treino Interrompido (Stop)
            </span>
            <h4 style="font-size:1.1rem; font-weight:700; margin:4px 0 8px;">${escapeHtml(w.routine_name)}</h4>
            <div style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:12px;">
              Status: Não concluído / Interrompido<br>
              ${w.finished_at ? `Interrompido às ${w.finished_at.slice(11, 16)}` : `Data: ${formatted}`}
              ${w.notes ? `<br><em>Notas: ${escapeHtml(w.notes)}</em>` : ''}
            </div>
            <div class="card" style="margin-bottom:12px; background:rgba(0,0,0,0.2);">
              ${setsSummary || '<span class="text-muted">Nenhum exercício registrado</span>'}
            </div>
            <div style="display:flex; justify-content:flex-end;">
              <button class="btn btn-secondary btn-sm" style="color:var(--danger, #ef4444);" onclick="App.deleteWorkoutFromCalendar(${w.id}, '${dateStr}')">Excluir Registro</button>
            </div>
          </div>
        `;
      } else if (stateType === 'past_rest') {
        contentHtml = `
          <div class="temporal-card temporal-past-rest">
            <h4 style="font-size:1.05rem; font-weight:700; margin-bottom:6px;">Dia de Descanso</h4>
            <p style="font-size:0.8125rem; color:var(--text-muted); margin-bottom:0;">
              Nenhum treino realizado nesta data. Dias passados permanecem preservados como histórico imutável de descanso.
            </p>
          </div>
        `;
      } else if (stateType === 'today_ready' || stateType === 'today_idle') {
        const sched = dayData.schedules && dayData.schedules[0];
        const activeW = dayData.workout && !dayData.workout.finished_at ? dayData.workout : null;

        contentHtml = `
          <div class="temporal-card temporal-today-ready">
            <span style="color:var(--accent-primary); font-size:0.75rem; font-weight:700; text-transform:uppercase;">
              ${activeW ? 'Sessão em Andamento Hoje' : (sched ? 'Treino de Hoje Agendado' : 'Pronto para Treinar Hoje')}
            </span>
            <h4 style="font-size:1.15rem; font-weight:700; margin:6px 0 10px;">
              ${escapeHtml(activeW ? activeW.routine_name : (sched ? sched.routine_name : 'Escolha uma Rotina'))}
            </h4>
            <p style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:14px;">
              ${activeW ? 'Sua sessão já foi iniciada. Retome a execução das séries:' : (sched ? 'Altere o estado diretamente ou inicie a sessão completa:' : 'Você pode iniciar seu treino agora mesmo:')}
            </p>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              ${activeW ? `
                <button class="btn btn-primary btn-sm" onclick="App.closeModals(); App.setRitmoTab('treino');">Retomar Treino →</button>
              ` : (sched ? `
                <button class="btn btn-primary btn-sm" onclick="App.startWorkoutSubmitFromRoutine(${sched.routine_id}); App.closeModals();">Iniciar Sessão</button>
                <button class="btn btn-tasks btn-sm" onclick="App.updateScheduleStatus(${sched.id}, 'concluido', '${dateStr}')">Marcar Concluído</button>
                <button class="btn btn-warning btn-sm" onclick="App.updateScheduleStatus(${sched.id}, 'stopped', '${dateStr}')">Interrompido (Stop)</button>
                <button class="btn btn-secondary btn-sm" onclick="App.deleteRitmoSchedule(${sched.id}, '${dateStr}')">Remover</button>
              ` : `
                <button class="btn btn-primary btn-sm" onclick="App.closeModals(); App.openStartWorkoutModal();">Iniciar Novo Treino</button>
              `)}
            </div>
          </div>
        `;

        if (!activeW && !sched && routines.length > 0) {
          contentHtml += `
            <div class="card" style="margin-top:12px;">
              <div class="card-title">Ou agende uma rotina para hoje</div>
              <div style="display:flex; gap:8px;">
                <select id="cal-schedule-routine-select" class="form-select" style="flex:1;">
                  ${routines.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join('')}
                </select>
                <button class="btn btn-secondary btn-sm" onclick="App.scheduleRoutineForDay(document.getElementById('cal-schedule-routine-select').value, '${dateStr}')">Agendar</button>
              </div>
            </div>
          `;
        }
      } else if (stateType === 'future_scheduled') {
        const sched = dayData.schedules && dayData.schedules[0];
        contentHtml = `
          <div class="temporal-card temporal-future-scheduled">
            <span style="color:#eab308; font-size:0.75rem; font-weight:700; text-transform:uppercase;">Treino Agendado</span>
            <h4 style="font-size:1.1rem; font-weight:700; margin:6px 0 8px;">${escapeHtml(sched ? sched.routine_name : 'Rotina')}</h4>
            <p style="font-size:0.8125rem; color:var(--text-muted); margin-bottom:14px;">
              Treino programado na sua Matriz Temporal para o dia ${formatted}. Altere diretamente o estado caso deseje:
            </p>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <button class="btn btn-tasks btn-sm" onclick="App.updateScheduleStatus(${sched.id}, 'concluido', '${dateStr}')">Marcar Concluído</button>
              <button class="btn btn-warning btn-sm" onclick="App.updateScheduleStatus(${sched.id}, 'stopped', '${dateStr}')">Interrompido (Stop)</button>
              <button class="btn btn-secondary btn-sm" style="color:var(--danger, #ef4444);" onclick="App.deleteRitmoSchedule(${sched.id}, '${dateStr}')">Cancelar Agendamento</button>
            </div>
          </div>
        `;
      } else {
        // future_empty
        contentHtml = `
          <div class="card">
            <h4 style="font-size:1rem; font-weight:700; margin-bottom:8px;">Programar Treino Futuro (${formatted})</h4>
            <p style="font-size:0.8125rem; color:var(--text-muted); margin-bottom:12px;">
              Defina com antecedência qual rotina muscular você pretende treinar nesta data.
            </p>
            ${routines.length ? `
              <div style="display:flex; gap:8px;">
                <select id="cal-schedule-routine-select" class="form-select" style="flex:1;">
                  ${routines.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join('')}
                </select>
                <button class="btn btn-primary btn-sm" onclick="App.scheduleRoutineForDay(document.getElementById('cal-schedule-routine-select').value, '${dateStr}')">Agendar Dia</button>
              </div>
            ` : `<p class="empty" style="font-size:0.8125rem; color:var(--text-muted);">Nenhuma rotina cadastrada ainda.</p>`}
          </div>
        `;
      }

      body.innerHTML = contentHtml;
    } catch (e) {
      body.innerHTML = `<div class="error-state">Erro ao carregar dados do dia: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function updateScheduleStatus(scheduleId, newStatus, dateStr) {
    try {
      await apiFetch(`/api/calendar/schedule/${scheduleId}/status`, {
        method: 'PATCH',
        body: { status: newStatus }
      });
      showToast(newStatus === 'concluido' ? 'Agendamento marcado como Concluído!' : 'Agendamento marcado como Interrompido (Stop)!');
      await loadRitmoCalendar(selectedRitmoMonth);
      if (dateStr) openRitmoDayDetails(dateStr);
    } catch (e) {
      showToast(e.message || 'Erro ao atualizar estado do agendamento');
    }
  }

  async function scheduleRoutineForDay(routineId, dateStr) {
    if (!routineId) return alert('Selecione uma rotina');
    try {
      await apiFetch('/api/calendar/schedule', {
        method: 'POST',
        body: { routine_id: parseInt(routineId), scheduled_at: dateStr }
      });
      showToast('Rotina agendada com sucesso!');
      await loadRitmoCalendar(selectedRitmoMonth);
      openRitmoDayDetails(dateStr);
    } catch (e) {
      alert(e.message || 'Erro ao agendar rotina');
    }
  }

  async function deleteRitmoSchedule(scheduleId, dateStr) {
    if (!confirm('Deseja remover este agendamento?')) return;
    try {
      await apiFetch(`/api/calendar/schedule/${scheduleId}`, { method: 'DELETE' });
      showToast('Agendamento removido');
      await loadRitmoCalendar(selectedRitmoMonth);
      openRitmoDayDetails(dateStr);
    } catch (e) {
      alert(e.message || 'Erro ao remover agendamento');
    }
  }

  async function deleteWorkoutFromCalendar(workoutId, dateStr) {
    if (!confirm('Deseja realmente excluir o registro deste treino?')) return;
    try {
      await apiFetch(`/api/workouts/${workoutId}`, { method: 'DELETE' });
      showToast('Treino excluído');
      await loadRitmoCalendar(selectedRitmoMonth);
      openRitmoDayDetails(dateStr);
    } catch (e) {
      alert(e.message || 'Erro ao excluir treino');
    }
  }

  async function loadActiveWorkout() {
    try {
      const container = document.getElementById('ritmo-active-workout-container');
      if (!container) return;
      const res = await apiFetch('/api/workouts/active');
      currentActiveWorkout = res;

      if (!res) {
        container.innerHTML = `
          <div class="empty-state">
            <p style="font-size:1rem; font-weight:600; margin-bottom:8px;">Nenhum treino em andamento</p>
            <p style="font-size:0.8125rem; color:var(--text-muted); margin-bottom:16px;">Selecione uma rotina para iniciar a sua sessão de treino hoje.</p>
            <button class="btn btn-primary" onclick="App.openStartWorkoutModal()">Iniciar Treino Agora</button>
          </div>
        `;
        return;
      }

      let itemsHtml = '';
      (res.items || []).forEach((item) => {
        let setsHtml = '';
        (item.sets || []).forEach((s, sIdx) => {
          setsHtml += `
            <div class="set-row ${s.done ? 'done' : ''}">
              <span style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono); text-align:center;">#${sIdx + 1}</span>
              <input type="number" step="0.5" class="form-input" style="padding:4px 8px; font-size:0.875rem;" value="${s.load || 0}" placeholder="kg"
                     onchange="App.updateSetValues(${item.id}, ${s.id}, this.value, null)">
              <input type="number" class="form-input" style="padding:4px 8px; font-size:0.875rem;" value="${s.reps || 0}" placeholder="reps"
                     onchange="App.updateSetValues(${item.id}, ${s.id}, null, this.value)">
              <div style="text-align:center;">
                <input type="checkbox" ${s.done ? 'checked' : ''} onchange="App.toggleWorkoutSet(${item.id}, ${s.id}, this.checked)">
              </div>
            </div>
          `;
        });

        itemsHtml += `
          <div class="card" style="margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px;">
              <div>
                <div style="font-weight:700; font-size:0.9375rem;">${escapeHtml(item.name)}</div>
                <div style="font-size:0.72rem; color:var(--text-muted);">Descanso: ${item.rest || 90}s</div>
              </div>
              <button type="button" class="btn btn-secondary btn-sm" onclick="App.addAdHocWorkoutSet(${item.id})">+ Série</button>
            </div>
            <div style="display:grid; grid-template-columns:36px 1fr 1fr 44px; gap:10px; font-size:0.7rem; color:var(--text-muted); margin-bottom:4px; padding:0 10px;">
              <span style="text-align:center;">SÉRIE</span>
              <span>CARGA (KG)</span>
              <span>REPS</span>
              <span style="text-align:center;">OK</span>
            </div>
            ${setsHtml}
            <div style="margin-top:10px;">
              <input type="text" class="form-input" style="padding:6px 10px; font-size:0.8125rem;"
                     placeholder="Comentários do exercício nesta sessão..."
                     value="${escapeHtml(item.notes || '')}"
                     onchange="App.updateWorkoutItemNotes(${item.id}, this.value)">
            </div>
          </div>
        `;
      });

      container.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:8px; flex-wrap:wrap;">
          <div>
            <span style="font-size:0.75rem; color:#22c55e; font-weight:700; text-transform:uppercase;">TREINO EM ANDAMENTO</span>
            <h3 style="font-size:1.15rem; font-weight:700;">${escapeHtml(res.routine_name)}</h3>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" onclick="App.discardActiveWorkout(${res.id})">Descartar</button>
            <button class="btn btn-warning btn-sm" onclick="App.stopActiveWorkout(${res.id})">Interromper (Stop)</button>
            <button class="btn btn-primary btn-sm" onclick="App.finishActiveWorkout(${res.id})">Finalizar Treino</button>
          </div>
        </div>
        ${itemsHtml}
      `;
    } catch (e) {
      console.error('Falha ao carregar treino ativo:', e);
    }
  }

  async function addAdHocWorkoutSet(itemId) {
    if (!itemId) return;
    try {
      const res = await apiFetch(`/api/workout_items/${itemId}/sets`, {
        method: 'POST',
        body: {}
      });
      if (res && res.workout) {
        currentActiveWorkout = res.workout;
      }
      await loadActiveWorkout();
      showToast('Série adicional inserida na sessão!');
    } catch (e) {
      showToast('Erro ao adicionar série: ' + e.message);
    }
  }

  async function updateWorkoutItemNotes(itemId, notesVal) {
    if (!itemId) return;
    try {
      if (currentActiveWorkout && currentActiveWorkout.items) {
        const it = currentActiveWorkout.items.find(x => x.id === itemId);
        if (it) it.notes = notesVal;
      }
      await apiFetch(`/api/workout_items/${itemId}`, {
        method: 'PATCH',
        body: { notes: notesVal }
      });
    } catch (e) {
      showToast('Erro ao salvar comentário: ' + e.message);
    }
  }

  async function openStartWorkoutModal() {
    try {
      const res = await apiFetch('/api/routines');
      allRoutinesList = res;
      const select = document.getElementById('select-workout-routine');
      if (select) {
        select.innerHTML = '<option value="">Selecione uma rotina...</option>' +
          res.map(r => `<option value="${r.id}">${r.name} (${(r.items || []).length} exercícios)</option>`).join('');
      }
      openModal('modal-start-workout');
    } catch (e) {
      showToast('Erro ao listar rotinas: ' + e.message);
    }
  }

  async function startWorkoutSubmit(e) {
    e.preventDefault();
    const rId = document.getElementById('select-workout-routine').value;
    if (!rId) return;
    try {
      await apiFetch('/api/workouts', {
        method: 'POST',
        body: { routine_id: parseInt(rId, 10) }
      });
      closeModals();
      setRitmoTab('treino');
      showToast('Treino iniciado com sucesso!');
    } catch (err) {
      showToast(err.message);
    }
  }

  async function toggleWorkoutSet(itemId, setId, done) {
    if (!currentActiveWorkout) return;
    try {
      let targetItem = null;
      for (const it of currentActiveWorkout.items) {
        if (it.id === itemId) {
          targetItem = it;
          for (const s of it.sets) {
            if (s.id === setId) s.done = done;
          }
        }
      }
      await apiFetch(`/api/workouts/${currentActiveWorkout.id}`, {
        method: 'PUT',
        body: currentActiveWorkout
      });
      if (done && targetItem) {
        startRitmoRestTimer(targetItem.rest || 90, targetItem.name);
      }
      loadActiveWorkout();
    } catch (e) {
      showToast('Erro ao atualizar série: ' + e.message);
    }
  }

  async function updateSetValues(itemId, setId, loadVal, repsVal) {
    if (!currentActiveWorkout) return;
    try {
      for (const it of currentActiveWorkout.items) {
        if (it.id === itemId) {
          for (const s of it.sets) {
            if (s.id === setId) {
              if (loadVal !== null) s.load = parseFloat(loadVal) || 0;
              if (repsVal !== null) s.reps = parseInt(repsVal, 10) || 0;
            }
          }
        }
      }
      await apiFetch(`/api/workouts/${currentActiveWorkout.id}`, {
        method: 'PUT',
        body: currentActiveWorkout
      });
    } catch (e) {
      console.error(e);
    }
  }

  async function finishActiveWorkout(wId) {
    if (!confirm('Deseja realmente finalizar esta sessão de treino?')) return;
    try {
      if (currentActiveWorkout) {
        currentActiveWorkout.finish = true;
        await apiFetch(`/api/workouts/${wId}`, {
          method: 'PUT',
          body: currentActiveWorkout
        });
      }
      stopRitmoRestTimer();
      showToast('Treino concluído e salvo no histórico!');
      loadActiveWorkout();
    } catch (e) {
      showToast(e.message);
    }
  }

  async function discardActiveWorkout(wId) {
    if (!confirm('Tem certeza que deseja descartar este treino? Os dados da sessão atual serão excluídos.')) return;
    try {
      await apiFetch(`/api/workouts/${wId}`, { method: 'DELETE' });
      stopRitmoRestTimer();
      showToast('Treino descartado.');
      loadActiveWorkout();
    } catch (e) {
      showToast(e.message);
    }
  }

  async function stopActiveWorkout(wId) {
    if (!confirm('Deseja interromper este treino (Stop)? Ele será registrado no histórico como não concluído.')) return;
    try {
      await apiFetch(`/api/workouts/${wId}`, {
        method: 'PUT',
        body: { stop: true }
      });
      stopRitmoRestTimer();
      showToast('Treino interrompido (Stop) registrado.');
      loadActiveWorkout();
      loadRitmoCalendar();
    } catch (e) {
      showToast(e.message);
    }
  }

  async function loadRoutines() {
    try {
      const container = document.getElementById('ritmo-routines-list');
      if (!container) return;
      const res = await apiFetch('/api/routines');
      allRoutinesList = res;
      if (!res.length) {
        container.innerHTML = '<div class="empty-state">Nenhuma rotina cadastrada ainda. Crie uma nova rotina!</div>';
        return;
      }
      container.innerHTML = res.map(r => `
        <div class="routine-card">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h4 style="font-size:1.05rem; font-weight:700;">${escapeHtml(r.name)}</h4>
            <span class="tag-badge">${(r.items || []).length} exercícios</span>
          </div>
          <div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:12px;">
            Grupos: ${escapeHtml(r.target_muscle_groups || 'Geral')}
          </div>
          <ul style="padding-left:18px; font-size:0.8125rem; color:var(--text-muted); margin-bottom:14px; line-height:1.6;">
            ${(r.items || []).map(i => `<li>${escapeHtml(i.name)} — ${i.sets}x${i.target_reps || i.reps} (${i.rest}s descanso)</li>`).join('')}
          </ul>
          <div style="display:flex; gap:8px;">
            <button class="btn btn-primary btn-sm" onclick="App.startWorkoutSubmitFromRoutine(${r.id})">Iniciar</button>
            <button class="btn btn-secondary btn-sm" onclick="App.openRoutineModal(${r.id})">Editar</button>
            <button class="btn btn-secondary btn-sm" onclick="App.deleteRoutine(${r.id})">Excluir</button>
          </div>
        </div>
      `).join('');
    } catch (e) {
      console.error(e);
    }
  }

  async function startWorkoutSubmitFromRoutine(rId) {
    if (!rId) return;
    try {
      await apiFetch('/api/workouts', {
        method: 'POST',
        body: { routine_id: parseInt(rId, 10) }
      });
      setRitmoTab('treino');
      showToast('Treino iniciado com sucesso!');
    } catch (err) {
      showToast(err.message);
    }
  }

  async function deleteRoutine(rId) {
    if (!confirm('Deseja excluir esta rotina?')) return;
    try {
      await apiFetch(`/api/routines/${rId}`, { method: 'DELETE' });
      showToast('Rotina excluída.');
      loadRoutines();
    } catch (e) {
      showToast(e.message);
    }
  }

  async function openRoutineModal(routineId = null) {
    const idInput = document.getElementById('routine-id');
    const nameInput = document.getElementById('routine-name-input');
    const musclesInput = document.getElementById('routine-muscles-input');
    const titleEl = document.getElementById('modal-routine-title');
    const container = document.getElementById('routine-items-editor-container');
    container.innerHTML = '';

    if (routineId) {
      if (titleEl) titleEl.innerText = 'Editar Rotina de Treino';
      let routine = (allRoutinesList || []).find(r => r.id === routineId);
      if (!routine) {
        try {
          routine = await apiFetch(`/api/routines/${routineId}`);
        } catch (e) {
          console.error(e);
        }
      }
      if (idInput) idInput.value = routineId;
      if (nameInput) nameInput.value = routine ? routine.name : '';
      if (musclesInput) musclesInput.value = routine ? (routine.target_muscle_groups || '') : '';
      if (routine && routine.items && routine.items.length) {
        routine.items.forEach(item => {
          addRoutineExerciseRow(item.exercise_id, item.sets, item.reps || item.target_reps, item.rest);
        });
      } else {
        addRoutineExerciseRow();
      }
    } else {
      if (titleEl) titleEl.innerText = 'Nova Rotina de Treino';
      if (idInput) idInput.value = '';
      if (nameInput) nameInput.value = '';
      if (musclesInput) musclesInput.value = '';
      addRoutineExerciseRow();
    }
    openModal('modal-routine');
  }

  function addRoutineExerciseRow(selectedExId = null, setsVal = 3, repsVal = 10, restVal = 90) {
    const container = document.getElementById('routine-items-editor-container');
    const idx = container.children.length;
    const div = document.createElement('div');
    div.className = 'routine-item-row';
    div.style = 'background:#000000; border:1px solid var(--border-subtle); border-radius:var(--radius-sm); padding:10px; margin-bottom:8px;';

    const options = (allExercisesList || []).map(e => {
      const isSel = (selectedExId && Number(e.id) === Number(selectedExId)) ? 'selected' : '';
      return `<option value="${e.id}" ${isSel}>${escapeHtml(e.name)} (${escapeHtml(e.muscle_group)})</option>`;
    }).join('');

    div.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:0.75rem; color:var(--text-muted);">Exercício #${idx + 1}</span>
        <button type="button" class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:0.7rem;" onclick="this.closest('.routine-item-row').remove()">Remover</button>
      </div>
      <div class="form-group" style="margin-bottom:8px;">
        <select class="form-select routine-ex-select" required>
          ${options || '<option value="1">Exercício Padrão</option>'}
        </select>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;">
        <div>
          <label style="font-size:0.7rem; color:var(--text-muted);">Séries</label>
          <input type="number" class="form-input routine-ex-sets" value="${setsVal || 3}" min="1" max="20" style="padding:4px 8px;">
        </div>
        <div>
          <label style="font-size:0.7rem; color:var(--text-muted);">Reps</label>
          <input type="number" class="form-input routine-ex-reps" value="${repsVal || 10}" min="1" max="100" style="padding:4px 8px;">
        </div>
        <div>
          <label style="font-size:0.7rem; color:var(--text-muted);">Descanso (s)</label>
          <input type="number" class="form-input routine-ex-rest" value="${restVal || 90}" min="0" max="600" style="padding:4px 8px;">
        </div>
      </div>
    `;
    container.appendChild(div);
  }

  async function saveRoutineSubmit(e) {
    e.preventDefault();
    const id = document.getElementById('routine-id').value;
    const name = document.getElementById('routine-name-input').value.trim();
    const muscles = document.getElementById('routine-muscles-input').value.trim();
    const rows = document.querySelectorAll('.routine-item-row');
    const items = [];
    rows.forEach(r => {
      const exId = r.querySelector('.routine-ex-select').value;
      const sets = r.querySelector('.routine-ex-sets').value;
      const reps = r.querySelector('.routine-ex-reps').value;
      const rest = r.querySelector('.routine-ex-rest').value;
      if (exId) {
        items.push({
          exercise_id: parseInt(exId, 10),
          sets: parseInt(sets, 10) || 3,
          reps: parseInt(reps, 10) || 10,
          rest: parseInt(rest, 10) || 90
        });
      }
    });

    if (!items.length) {
      showToast('Adicione pelo menos 1 exercício à rotina.');
      return;
    }

    try {
      if (id) {
        await apiFetch(`/api/routines/${id}`, {
          method: 'PUT',
          body: { name, target_muscle_groups: muscles, items }
        });
        showToast('Rotina atualizada com sucesso!');
      } else {
        await apiFetch('/api/routines', {
          method: 'POST',
          body: { name, target_muscle_groups: muscles, items }
        });
        showToast('Rotina criada com sucesso!');
      }
      closeModals();
      loadRoutines();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function loadExercises() {
    try {
      const container = document.getElementById('ritmo-exercises-list');
      if (!container) return;
      const res = await apiFetch('/api/exercises');
      allExercisesList = res;
      renderExercises(res);
    } catch (e) {
      console.error(e);
    }
  }

  function filterExercises(q) {
    const term = (q || '').toLowerCase().trim();
    const filtered = allExercisesList.filter(e => e.name.toLowerCase().includes(term) || e.muscle_group.toLowerCase().includes(term));
    renderExercises(filtered);
  }

  function renderExercises(list) {
    const container = document.getElementById('ritmo-exercises-list');
    if (!container) return;
    if (!list.length) {
      container.innerHTML = '<div class="empty-state">Nenhum exercício encontrado.</div>';
      return;
    }
    container.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${list.map(e => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm);">
            <div>
              <div style="font-weight:600; font-size:0.875rem;">${e.name}</div>
              <div style="font-size:0.75rem; color:var(--text-muted); text-transform:capitalize;">${e.muscle_group} ${e.equipment ? '• ' + e.equipment : ''}</div>
            </div>
            ${e.custom ? `<button class="btn btn-secondary btn-sm" onclick="App.deleteCustomExercise(${e.id})">Excluir</button>` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }

  function openCustomExerciseModal() {
    document.getElementById('custom-ex-name').value = '';
    document.getElementById('custom-ex-equipment').value = '';
    openModal('modal-custom-exercise');
  }

  async function saveCustomExerciseSubmit(e) {
    e.preventDefault();
    const name = document.getElementById('custom-ex-name').value.trim();
    const muscle = document.getElementById('custom-ex-muscle').value;
    const equipment = document.getElementById('custom-ex-equipment').value.trim();
    try {
      await apiFetch('/api/exercises', {
        method: 'POST',
        body: { name, muscle_group: muscle, equipment }
      });
      closeModals();
      loadExercises();
      showToast('Exercício criado com sucesso!');
    } catch (err) {
      showToast(err.message);
    }
  }

  async function deleteCustomExercise(exId) {
    if (!confirm('Deseja excluir este exercício customizado?')) return;
    try {
      await apiFetch(`/api/exercises/${exId}`, { method: 'DELETE' });
      showToast('Exercício excluído.');
      loadExercises();
    } catch (e) {
      showToast(e.message);
    }
  }

  // Peso & Biometria (Ritmo)
  function openWeightModal() {
    document.getElementById('input-weight-val').value = '';
    document.getElementById('input-weight-date').value = new Date().toISOString().slice(0, 10);
    document.getElementById('input-weight-notes').value = '';
    openModal('modal-weight');
  }

  async function saveWeightSubmit(e) {
    e.preventDefault();
    const weight = parseFloat(document.getElementById('input-weight-val').value);
    const dateVal = document.getElementById('input-weight-date').value;
    const notes = document.getElementById('input-weight-notes').value.trim();
    try {
      await apiFetch('/api/metrics/weight', {
        method: 'POST',
        body: { weight, recorded_at: dateVal, notes }
      });
      closeModals();
      await loadWeightHistory();
      showToast('Peso registrado com sucesso!');
    } catch (err) {
      showToast(err.message);
    }
  }

  async function deleteWeightMetric(mId) {
    if (!confirm('Deseja excluir este registro de pesagem?')) return;
    try {
      await apiFetch(`/api/metrics/weight/${mId}`, { method: 'DELETE' });
      showToast('Pesagem excluída com sucesso.');
      await loadWeightHistory();
    } catch (err) {
      showToast(err.message);
    }
  }

  function renderWeightSvg(records) {
    const container = document.getElementById('ritmo-weight-chart-container');
    if (!container) return;

    if (!records || !records.length) {
      container.innerHTML = `
        <div style="text-align:center; padding:28px 12px; color:var(--text-muted); font-size:0.875rem;">
          Nenhum registro de pesagem ainda. Clique em <strong>+ Pesar</strong> para iniciar o acompanhamento!
        </div>
      `;
      return;
    }

    // records are newest-first, reverse to chronological
    const points = records.slice().reverse();
    const weights = points.map(p => p.weight);
    let minW = Math.min(...weights);
    let maxW = Math.max(...weights);

    if (minW === maxW) {
      minW = minW - 1;
      maxW = maxW + 1;
    } else {
      const margin = (maxW - minW) * 0.15 || 0.5;
      minW = Math.floor((minW - margin) * 10) / 10;
      maxW = Math.ceil((maxW + margin) * 10) / 10;
    }

    const rangeW = maxW - minW || 1;
    const width = 560;
    const height = 180;
    const padL = 40;
    const padR = 24;
    const padT = 24;
    const padB = 30;
    const chartW = width - padL - padR;
    const chartH = height - padT - padB;

    const coords = points.map((p, idx) => {
      const x = points.length === 1 ? padL + chartW / 2 : padL + (idx / (points.length - 1)) * chartW;
      const y = padT + chartH - ((p.weight - minW) / rangeW) * chartH;
      return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, weight: p.weight, date: p.recorded_at };
    });

    const pathD = coords.reduce((acc, pt, idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`, '');
    const fillD = `${pathD} L ${coords[coords.length - 1].x} ${padT + chartH} L ${coords[0].x} ${padT + chartH} Z`;

    const gridLines = [minW, (minW + maxW) / 2, maxW].map(val => {
      const y = padT + chartH - ((val - minW) / rangeW) * chartH;
      return `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3,3" />
        <text x="${padL - 6}" y="${y + 3}" text-anchor="end" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)">${val.toFixed(1)}</text>
      `;
    }).join('');

    const circles = coords.map(pt => `
      <g>
        <circle cx="${pt.x}" cy="${pt.y}" r="4.5" fill="#38bdf8" stroke="#000000" stroke-width="2" />
        <text x="${pt.x}" y="${pt.y - 8}" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700" font-family="var(--font-mono)">${pt.weight}</text>
        <title>${pt.weight} kg em ${pt.date}</title>
      </g>
    `).join('');

    const dateLabels = coords.filter((_, idx) => {
      if (coords.length <= 4) return true;
      return idx === 0 || idx === coords.length - 1 || idx === Math.floor(coords.length / 2);
    }).map(pt => `
      <text x="${pt.x}" y="${height - 8}" text-anchor="middle" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)">${pt.date.slice(5)}</text>
    `).join('');

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; display:block; overflow:visible;">
        <defs>
          <linearGradient id="weightGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.38" />
            <stop offset="100%" stop-color="#2563eb" stop-opacity="0.0" />
          </linearGradient>
        </defs>
        ${gridLines}
        <path d="${fillD}" fill="url(#weightGrad)" />
        <path d="${pathD}" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
        ${circles}
        ${dateLabels}
      </svg>
    `;
  }

  async function loadWeightHistory() {
    try {
      const container = document.getElementById('ritmo-weight-history-list');
      const curEl = document.getElementById('ritmo-weight-current');
      const deltaEl = document.getElementById('ritmo-weight-delta');
      const countEl = document.getElementById('ritmo-weight-count');
      const minmaxEl = document.getElementById('ritmo-weight-minmax');

      const res = await apiFetch('/api/metrics/weight');

      if (!res || !res.length) {
        if (curEl) curEl.innerText = '-- kg';
        if (deltaEl) deltaEl.innerText = '-- kg total';
        if (countEl) countEl.innerText = '0 pesagens';
        if (minmaxEl) minmaxEl.innerText = 'Mín: -- kg • Máx: -- kg';
        renderWeightSvg([]);
        if (container) container.innerHTML = '<div class="empty-state">Nenhuma pesagem registrada ainda.</div>';
        return;
      }

      const curW = res[0].weight;
      const firstW = res[res.length - 1].weight;
      const totalDelta = Math.round((curW - firstW) * 10) / 10;
      const weights = res.map(r => r.weight);
      const minW = Math.min(...weights);
      const maxW = Math.max(...weights);

      if (curEl) curEl.innerText = `${curW} kg`;
      if (deltaEl) {
        const sign = totalDelta > 0 ? '+' : '';
        deltaEl.innerText = `${sign}${totalDelta} kg total`;
        deltaEl.style.color = totalDelta > 0 ? 'var(--accent-expense)' : (totalDelta < 0 ? 'var(--accent-income)' : 'var(--text-muted)');
      }
      if (countEl) countEl.innerText = `${res.length} pesagem(ns)`;
      if (minmaxEl) minmaxEl.innerText = `Mín: ${minW} kg • Máx: ${maxW} kg`;

      renderWeightSvg(res);

      if (container) {
        container.innerHTML = res.map(m => {
          const deltaStr = m.delta > 0 ? `+${m.delta} kg` : (m.delta < 0 ? `${m.delta} kg` : '0 kg');
          const deltaColor = m.delta > 0 ? 'var(--accent-expense)' : (m.delta < 0 ? 'var(--accent-income)' : 'var(--text-muted)');
          return `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid var(--border-subtle);">
              <div>
                <span style="font-weight:700; font-size:1rem;">${m.weight} kg</span>
                <span style="font-size:0.75rem; color:${deltaColor}; margin-left:8px; font-weight:600;">${deltaStr}</span>
                ${m.notes ? `<div style="font-size:0.75rem; color:var(--text-muted);">${m.notes}</div>` : ''}
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:0.8125rem; color:var(--text-secondary); font-family:var(--font-mono);">${m.recorded_at}</span>
                <button class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:0.75rem;" onclick="App.deleteWeightMetric(${m.id})" title="Excluir">✕</button>
              </div>
            </div>
          `;
        }).join('');
      }
    } catch (e) {
      console.error('Erro ao carregar histórico de peso:', e);
    }
  }

  // Fotos de Evolução (Ritmo)
  async function loadEvolutionPhotos() {
    try {
      const container = document.getElementById('ritmo-photos-gallery');
      if (!container) return;
      const res = await apiFetch('/api/metrics/photos');
      if (!res || !res.length) {
        container.innerHTML = `
          <div class="empty-state" style="grid-column:1/-1; padding:20px 10px;">
            Nenhuma foto de evolução ainda. Clique em <strong>+ Adicionar Foto</strong> para registrar seu progresso!
          </div>
        `;
        return;
      }

      const angleLabels = {
        'frontal': 'Frontal',
        'costas': 'Costas',
        'lateral_esquerda': 'Lateral Esq.',
        'lateral_direita': 'Lateral Dir.'
      };

      container.innerHTML = res.map(p => {
        const url = window.resolveApiUrl('/' + String(p.photo_path || '').replace(/^\/+/, ''));
        return `
        <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); overflow:hidden; display:flex; flex-direction:column;">
          <a href="${url}" target="_blank" rel="noopener" style="display:block; overflow:hidden;">
            <img src="${url}" alt="Foto de Evolução" loading="lazy" style="width:100%; height:130px; object-fit:cover; display:block;">
          </a>
          <div style="padding:8px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="font-size:0.75rem; font-weight:700;">${angleLabels[p.angle] || p.angle}</div>
              <div style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${p.taken_at}</div>
            </div>
            <button class="btn btn-secondary btn-sm" style="padding:2px 6px; font-size:0.75rem;" onclick="App.deleteEvolutionPhoto(${p.id})" title="Excluir Foto">✕</button>
          </div>
        </div>
      `;
      }).join('');
    } catch (e) {
      console.error('Erro ao carregar fotos:', e);
    }
  }

  function openEvolutionPhotoModal() {
    const fileInput = document.getElementById('evo-photo-file');
    if (fileInput) fileInput.value = '';
    const camInput = document.getElementById('evo-photo-camera');
    if (camInput) camInput.value = '';
    const preview = document.getElementById('evo-photo-preview');
    if (preview) { preview.src = ''; preview.style.display = 'none'; }
    const dateInput = document.getElementById('evo-photo-date');
    if (dateInput) dateInput.value = new Date().toISOString().slice(0, 10);
    openModal('modal-evolution-photo');
  }

  function getSelectedEvolutionFile() {
    const cam = document.getElementById('evo-photo-camera');
    if (cam && cam.files && cam.files[0]) return cam.files[0];
    const gal = document.getElementById('evo-photo-file');
    if (gal && gal.files && gal.files[0]) return gal.files[0];
    return null;
  }

  function previewEvolutionPhoto(inputEl) {
    const preview = document.getElementById('evo-photo-preview');
    const f = inputEl && inputEl.files && inputEl.files[0];
    if (!preview || !f) return;
    // Clear the other input so only one source is used
    const otherId = inputEl.id === 'evo-photo-camera' ? 'evo-photo-file' : 'evo-photo-camera';
    const other = document.getElementById(otherId);
    if (other) other.value = '';
    preview.src = URL.createObjectURL(f);
    preview.style.display = 'block';
  }

  // Downscale + re-encode on a canvas (WebView/Capacitor safe). Falls back to the original file.
  async function compressImageFile(file, maxSide = 1600, quality = 0.82) {
    try {
      const url = URL.createObjectURL(file);
      const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = reject;
        el.src = url;
      });
      let { naturalWidth: w, naturalHeight: h } = img;
      if (!w || !h) throw new Error('dimensões inválidas');
      const scale = Math.min(1, maxSide / Math.max(w, h));
      w = Math.round(w * scale); h = Math.round(h * scale);
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      const toBlob = (type) => new Promise(r => canvas.toBlob(b => r(b), type, quality));
      let blob = await toBlob('image/webp');
      let ext = 'webp';
      if (!blob || blob.type !== 'image/webp') { blob = await toBlob('image/jpeg'); ext = 'jpg'; }
      if (!blob) throw new Error('falha no canvas');
      return new File([blob], `evolucao_${Date.now()}.${ext}`, { type: blob.type });
    } catch (err) {
      console.warn('Compressão indisponível, enviando original:', err);
      return file;
    }
  }

  async function saveEvolutionPhotoSubmit(e) {
    e.preventDefault();
    const angle = document.getElementById('evo-photo-angle').value;
    const dateVal = document.getElementById('evo-photo-date').value;
    const original = getSelectedEvolutionFile();

    if (!original) {
      return alert('Tire uma foto ou selecione uma imagem da galeria');
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = 'Enviando...'; }

    try {
      const file = await compressImageFile(original);
      const formData = new FormData();
      formData.append('file', file, file.name || 'foto.jpg');
      formData.append('angle', angle);
      formData.append('taken_at', dateVal);

      await apiFetch('/api/metrics/photos', {
        method: 'POST',
        body: formData
      });
      closeModals();
      await loadEvolutionPhotos();
      showToast('Foto de evolução salva com sucesso!');
    } catch (err) {
      showToast(err.message || 'Falha ao enviar foto');
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = 'Salvar Foto'; }
    }
  }

  async function deleteEvolutionPhoto(pId) {
    if (!confirm('Deseja excluir esta foto de evolução?')) return;
    try {
      await apiFetch(`/api/metrics/photos/${pId}`, { method: 'DELETE' });
      showToast('Foto excluída.');
      await loadEvolutionPhotos();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function loadWorkoutsHistory() {
    try {
      const container = document.getElementById('ritmo-workouts-history-list');
      if (!container) return;
      const res = await apiFetch('/api/workouts');
      if (!res.length) {
        container.innerHTML = '<div class="empty-state">Nenhum treino registrado no histórico ainda.</div>';
        return;
      }
      container.innerHTML = res.map(w => {
        const isStopped = (w.status === 'stopped' || w.status === 'stop');
        const badge = isStopped
          ? '<span class="badge badge-stopped" style="margin-left:8px;">Interrompido / Stop</span>'
          : '<span class="badge badge-low" style="margin-left:8px; color:#22c55e;">Concluído</span>';
        return `
        <div style="padding:12px 14px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-md); margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <div style="display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
              <span style="font-weight:700; font-size:0.9375rem;">${escapeHtml(w.routine_name)}</span>
              ${badge}
            </div>
            <span style="font-size:0.75rem; color:var(--text-secondary); font-family:var(--font-mono);">${w.session_date}</span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted);">
            ${isStopped ? 'Sessão interrompida antes da conclusão • ' : ''}${(w.items || []).length} exercícios registrados
          </div>
        </div>
      `;
      }).join('');
    } catch (e) {
      console.error(e);
    }
  }

  // ==================== SLEEP MODULE (v1.3 FASE 3) ====================
  function renderSleepSvg(logs) {
    const container = document.getElementById('sleep-chart-container');
    if (!container) return;

    if (!logs || !logs.length) {
      container.innerHTML = `
        <div style="text-align:center; padding:18px 10px; color:var(--text-muted); font-size:0.8125rem;">
          Nenhum registro de sono nos últimos dias.
        </div>
      `;
      return;
    }

    const recent = logs.slice(0, 7).reverse();
    const width = 560;
    const height = 110;
    const padL = 36;
    const padR = 20;
    const padT = 16;
    const padB = 26;
    const chartW = width - padL - padR;
    const chartH = height - padT - padB;
    const maxHours = 10;

    const barWidth = Math.min(36, Math.floor(chartW / (recent.length * 1.6)));
    const gap = (chartW - (recent.length * barWidth)) / (recent.length + 1);

    const bars = recent.map((item, idx) => {
      const durHours = (item.duration_minutes || 0) / 60;
      const h = Math.min(chartH, Math.max(4, (durHours / maxHours) * chartH));
      const x = padL + gap + idx * (barWidth + gap);
      const y = padT + chartH - h;

      const color = durHours >= 7 ? '#22c55e' : (durHours >= 6 ? '#f59e0b' : '#ef4444');
      const hoursInt = Math.floor(durHours);
      const minsInt = Math.round((durHours - hoursInt) * 60);

      return `
        <g>
          <rect x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="3" fill="${color}" opacity="0.85">
            <title>${item.sleep_date}: ${hoursInt}h ${minsInt}m (Nota: ${item.quality_rating}/5)</title>
          </rect>
          <text x="${x + barWidth / 2}" y="${y - 4}" text-anchor="middle" fill="#ffffff" font-size="9" font-family="var(--font-mono)">${durHours.toFixed(1)}h</text>
          <text x="${x + barWidth / 2}" y="${height - 8}" text-anchor="middle" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)">${item.sleep_date.slice(5)}</text>
        </g>
      `;
    }).join('');

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; display:block;">
        <line x1="${padL}" y1="${padT + chartH * 0.2}" x2="${width - padR}" y2="${padT + chartH * 0.2}" stroke="rgba(34,197,94,0.25)" stroke-dasharray="3,3" />
        <text x="${padL - 6}" y="${padT + chartH * 0.2 + 3}" text-anchor="end" fill="rgba(34,197,94,0.6)" font-size="8" font-family="var(--font-mono)">8h</text>
        ${bars}
      </svg>
    `;
  }

  async function loadSleepData() {
    try {
      const sumRes = await apiFetch('/api/sleep/summary');
      const hours = Math.floor((sumRes.avg_duration_minutes || 0) / 60);
      const mins = Math.round((sumRes.avg_duration_minutes || 0) % 60);
      const avgDurEl = document.getElementById('sleep-avg-duration');
      const avgQualEl = document.getElementById('sleep-avg-quality');
      if (avgDurEl) avgDurEl.innerText = `${hours}h ${mins}m`;
      if (avgQualEl) avgQualEl.innerText = `Qualidade: ${sumRes.avg_quality_rating || 0}/5`;

      const logsRes = await apiFetch('/api/sleep/logs?days=15');
      const container = document.getElementById('sleep-logs-list');
      const lastDurEl = document.getElementById('sleep-last-duration');
      const lastDateEl = document.getElementById('sleep-last-date');

      if (logsRes && logsRes.length && lastDurEl && lastDateEl) {
        const last = logsRes[0];
        const lH = Math.floor(last.duration_minutes / 60);
        const lM = last.duration_minutes % 60;
        lastDurEl.innerText = `${lH}h ${lM}m`;
        lastDateEl.innerText = `${last.sleep_date} (${last.bedtime} - ${last.wake_time})`;
      } else if (lastDurEl && lastDateEl) {
        lastDurEl.innerText = '--h --m';
        lastDateEl.innerText = 'Nenhum registro';
      }

      renderSleepSvg(logsRes || []);

      if (!container) return;
      if (!logsRes || !logsRes.length) {
        container.innerHTML = '<div class="empty-state">Nenhum registro de sono encontrado. Registre sua primeira noite!</div>';
        return;
      }

      const complianceLabels = {
        no_horario: 'No Horário',
        dormiu_menos: 'Dormiu Menos',
        dormiu_mais: 'Dormiu Mais',
        nao_conseguiu_dormir: 'Não Dormiu'
      };

      container.innerHTML = logsRes.map(l => {
        const lH = Math.floor(l.duration_minutes / 60);
        const lM = l.duration_minutes % 60;
        const compLabel = complianceLabels[l.compliance_status || 'no_horario'] || 'No Horário';
        return `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 14px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); margin-bottom:8px;">
            <div>
              <div style="font-weight:700; font-size:0.9375rem;">${lH}h ${lM}m de sono • <span style="font-size:0.75rem; color:var(--accent-tasks);">${escapeHtml(compLabel)}</span></div>
              <div style="font-size:0.75rem; color:var(--text-muted);">${l.bedtime} às ${l.wake_time} (Meta: ${l.planned_bedtime || '23:00'}-${l.planned_wake_time || '07:00'}) • Nota: ${l.quality_rating}/5 ${l.notes ? '• ' + escapeHtml(l.notes) : ''}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:0.8125rem; color:var(--text-secondary); font-family:var(--font-mono);">${l.sleep_date}</span>
              <button class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:0.75rem;" onclick="App.deleteSleepLog(${l.id})" title="Excluir">✕</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error(e);
    }
  }

  function openSleepModal() {
    const today = new Date().toISOString().slice(0, 10);
    document.getElementById('sleep-date-input').value = today;
    const compSel = document.getElementById('sleep-compliance-select');
    if (compSel) compSel.value = 'no_horario';
    document.getElementById('sleep-bedtime-input').value = state.plannedBedtime || '23:00';
    document.getElementById('sleep-waketime-input').value = state.plannedWakeTime || '07:00';
    document.getElementById('sleep-quality-select').value = '4';
    document.getElementById('sleep-notes-input').value = '';
    openModal('modal-sleep');
  }

  async function deleteSleepLog(logId) {
    if (!confirm('Deseja excluir este registro de sono?')) return;
    try {
      await apiFetch(`/api/sleep/logs/${logId}`, { method: 'DELETE' });
      showToast('Registro de sono excluído.');
      await loadSleepData();
      if (state.currentView === 'routines') loadRoutinesSleepSubTab();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function saveSleepSubmit(e) {
    e.preventDefault();
    const dateVal = document.getElementById('sleep-date-input').value;
    const compliance_status = document.getElementById('sleep-compliance-select')?.value || 'no_horario';
    const bedtime = document.getElementById('sleep-bedtime-input').value;
    const waketime = document.getElementById('sleep-waketime-input').value;
    const quality = parseInt(document.getElementById('sleep-quality-select').value, 10);
    const notes = document.getElementById('sleep-notes-input').value.trim();

    try {
      await apiFetch('/api/sleep/logs', {
        method: 'POST',
        body: {
          sleep_date: dateVal,
          compliance_status,
          bedtime,
          wake_time: waketime,
          planned_bedtime: state.plannedBedtime || '23:00',
          planned_wake_time: state.plannedWakeTime || '07:00',
          quality_rating: quality,
          notes
        }
      });
      closeModals();
      await loadSleepData();
      if (state.currentView === 'routines') loadRoutinesSleepSubTab();
      showToast('Noite de sono registrada com sucesso!');
    } catch (err) {
      showToast(err.message);
    }
  }

  // ==================== TASK HISTORY (v1.3.2 FASE 2) ====================
  let currentTaskHistoryList = [];

  async function openTaskHistoryModal(taskId, taskTitle) {
    try {
      document.getElementById('modal-task-history-title').innerText = `Histórico: ${taskTitle}`;
      const filterInput = document.getElementById('task-history-date-filter');
      if (filterInput) filterInput.value = '';
      openModal('modal-task-history');

      const res = await apiFetch(`/api/tasks/${taskId}/history`);
      currentTaskHistoryList = res || [];
      renderTaskHistory(currentTaskHistoryList);
    } catch (e) {
      showToast('Erro ao carregar histórico: ' + e.message);
    }
  }

  function filterTaskHistory(dateStr) {
    if (!dateStr) {
      renderTaskHistory(currentTaskHistoryList);
      return;
    }
    const q = dateStr.trim().toLowerCase();
    const filtered = currentTaskHistoryList.filter(c => {
      const execDate = (c.execution_date || c.completed_at || '').toLowerCase();
      const notes = (c.notes || '').toLowerCase();
      return execDate.includes(q) || notes.includes(q);
    });
    renderTaskHistory(filtered);
  }

  function renderTaskHistory(list) {
    const container = document.getElementById('task-history-list');
    if (!container) return;
    if (!list.length) {
      container.innerHTML = '<div class="empty-state" style="padding:16px;">Nenhuma execução encontrada.</div>';
      return;
    }
    container.innerHTML = list.map(c => {
      const rawDate = c.execution_date || c.completed_at || '';
      const formattedDate = rawDate.replace('T', ' ').slice(0, 16);
      const notesText = c.notes || 'Execução concluída';
      return `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:var(--radius-sm); margin-bottom:6px; gap:8px;">
          <span style="font-size:0.84rem; font-weight:600; color:var(--text-primary);">${escapeHtml(notesText)}</span>
          <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-secondary); flex-shrink:0;">${escapeHtml(formattedDate)}</span>
        </div>
      `;
    }).join('');
  }

  // ==================== v1.4.0: POMODORO & ROUTINE WEB WORKER (RF08, RNF03) ====================
  let routineWorker = null;
  let routinePomoState = {
    isRunning: false,
    remainingSec: 25 * 60,
    totalDurationSec: 25 * 60,
    routineId: null,
    routineTitle: 'Pomodoro de Rotina',
    elapsedBaseSec: 0
  };

  function formatHmsClock(totalSeconds) {
    const sec = Math.max(0, Math.floor(totalSeconds || 0));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function initRoutineWebWorker() {
    try {
      const saved = localStorage.getItem('dreamhub_routine_pomo_state');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') {
          routinePomoState = { ...routinePomoState, ...parsed };
        }
      }
    } catch (_) {}

    try {
      if (window.Worker) {
        routineWorker = new Worker('/js/pomodoro-worker.js');
        routineWorker.onmessage = (e) => {
          const msg = e.data || {};
          if (msg.type === 'TICK') {
            routinePomoState.remainingSec = msg.remainingSec;
            routinePomoState.isRunning = msg.isRunning;
            updateRoutinePomodoroDom(msg.remainingSec, msg.routineElapsedSec);
          } else if (msg.type === 'COMPLETE') {
            routinePomoState.isRunning = false;
            routinePomoState.remainingSec = routinePomoState.totalDurationSec;
            persistRoutinePomoState();
            updateRoutinePomodoroDom(routinePomoState.remainingSec, msg.routineElapsedSec);
            playCompletionChime();
            showToast('Ciclo Pomodoro da Rotina concluído!');
          }
        };
      }
    } catch (err) {
      console.warn('Web Worker fallback active:', err);
    }
    updateRoutinePomodoroDom(routinePomoState.remainingSec, routinePomoState.elapsedBaseSec);
  }

  function persistRoutinePomoState() {
    try {
      localStorage.setItem('dreamhub_routine_pomo_state', JSON.stringify(routinePomoState));
    } catch (_) {}
  }

  function updateRoutinePomodoroDom(remSec, elapsedSec) {
    const dispEl = document.getElementById('routine-pomo-display');
    const btnEl = document.getElementById('btn-routine-pomo-toggle');
    const labelEl = document.getElementById('routine-active-focus-label');
    const elapsedEl = document.getElementById('routine-active-elapsed-label');

    if (dispEl) {
      const m = Math.floor((remSec || 0) / 60);
      const s = (remSec || 0) % 60;
      dispEl.innerText = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    if (btnEl) {
      btnEl.innerText = routinePomoState.isRunning ? 'Pausar' : 'Iniciar';
    }
    if (labelEl) {
      labelEl.innerText = routinePomoState.routineTitle || 'Rotina Diária';
    }
    if (elapsedEl && elapsedSec !== undefined) {
      elapsedEl.innerText = `Tempo decorrido hoje: ${formatHmsClock(elapsedSec)}`;
    }
  }

  function toggleRoutinePomodoro(routineId = null, routineTitle = null, focusMinutes = null) {
    if (routineId) {
      routinePomoState.routineId = routineId;
    }
    if (routineTitle) {
      routinePomoState.routineTitle = routineTitle;
    }
    if (focusMinutes) {
      const dur = Math.max(1, parseInt(focusMinutes, 10) || 25) * 60;
      routinePomoState.totalDurationSec = dur;
      if (!routinePomoState.isRunning) {
        routinePomoState.remainingSec = dur;
      }
    }

    if (routinePomoState.isRunning) {
      pauseRoutinePomodoro();
    } else {
      routinePomoState.isRunning = true;
      persistRoutinePomoState();
      if (routineWorker) {
        routineWorker.postMessage({
          command: 'START',
          durationSec: routinePomoState.remainingSec || routinePomoState.totalDurationSec,
          mode: 'focus',
          taskId: routinePomoState.routineId
        });
        routineWorker.postMessage({
          command: 'ROUTINE_START',
          routineId: routinePomoState.routineId,
          elapsedSec: routinePomoState.elapsedBaseSec || 0
        });
      }
      updateRoutinePomodoroDom(routinePomoState.remainingSec, routinePomoState.elapsedBaseSec);
    }
  }

  function pauseRoutinePomodoro() {
    routinePomoState.isRunning = false;
    persistRoutinePomoState();
    if (routineWorker) {
      routineWorker.postMessage({ command: 'PAUSE' });
      routineWorker.postMessage({ command: 'ROUTINE_PAUSE' });
    }
    updateRoutinePomodoroDom(routinePomoState.remainingSec, routinePomoState.elapsedBaseSec);
  }

  function resetRoutinePomodoro() {
    routinePomoState.isRunning = false;
    routinePomoState.remainingSec = routinePomoState.totalDurationSec || 25 * 60;
    persistRoutinePomoState();
    if (routineWorker) {
      routineWorker.postMessage({
        command: 'RESET',
        durationSec: routinePomoState.remainingSec
      });
    }
    updateRoutinePomodoroDom(routinePomoState.remainingSec, routinePomoState.elapsedBaseSec);
  }

  // ==================== v1.4.0: MÓDULO ROTINAS DIÁRIAS (RF01 a RF10, RN01 a RN03) ====================
  let dailyRoutinesTodayData = [];
  let allDailyRoutinesMaster = [];
  let activeRoutinesSubTab = 'hoje';
  let routinesCalendarViewMode = 'month';

  function setRoutinesSubTab(tab) {
    activeRoutinesSubTab = tab;
    ['hoje', 'calendario', 'historico', 'sono'].forEach(t => {
      const pane = document.getElementById(`routines-subview-${t}`);
      const btn = document.getElementById(`btn-routines-tab-${t}`);
      if (pane) pane.style.display = (t === tab) ? 'block' : 'none';
      if (btn) btn.classList.toggle('active', t === tab);
    });

    if (tab === 'hoje') loadDailyRoutinesData();
    else if (tab === 'calendario') loadRoutinesCalendar();
    else if (tab === 'historico') loadRoutinesHistory();
    else if (tab === 'sono') loadRoutinesSleepSubTab();
  }

  async function loadDailyRoutinesData() {
    try {
      const [todayRes, masterRes, sleepSettings] = await Promise.all([
        apiFetch('/api/daily-routines/today'),
        apiFetch('/api/daily-routines'),
        apiFetch('/api/settings/sleep').catch(() => ({ planned_bedtime: '23:00', planned_wake_time: '07:00' }))
      ]);

      state.plannedBedtime = sleepSettings.planned_bedtime || '23:00';
      state.plannedWakeTime = sleepSettings.planned_wake_time || '07:00';
      const sleepBanner = document.getElementById('routine-sleep-plan-banner');
      if (sleepBanner) {
        sleepBanner.innerText = `Planejado: Dormir às ${state.plannedBedtime} • Acordar às ${state.plannedWakeTime}`;
      }

      if (todayRes.push_notifications && todayRes.push_notifications.length) {
        dispatchDailyRoutinePushNotifications(todayRes.push_notifications);
      }

      dailyRoutinesTodayData = todayRes.routines || [];
      allDailyRoutinesMaster = masterRes || [];

      renderDailyRoutinesToday();
    } catch (e) {
      console.error('Erro ao carregar rotinas diárias:', e);
    }
  }

  function renderDailyRoutinesToday() {
    const container = document.getElementById('daily-routines-today-list');
    if (!container) return;

    // Combine today's scheduled/logged routines with any cancelled routines so the user can reactivate/edit them (RN01)
    const todayIds = new Set(dailyRoutinesTodayData.map(r => r.routine_id));
    const cancelledOrOther = (allDailyRoutinesMaster || []).filter(m => !todayIds.has(m.id)).map(m => ({
      routine_id: m.id,
      title: m.title,
      description: m.description,
      scheduled_time: m.scheduled_time,
      days_of_week: m.days_of_week,
      pomodoro_target: m.pomodoro_target,
      pomodoro_duration_minutes: m.pomodoro_duration_minutes,
      routine_status: m.status,
      status: m.status === 'cancelada' ? 'cancelada' : 'fora_do_dia',
      total_tasks: (m.tasks || []).length,
      done_tasks: (m.tasks || []).filter(t => t.done).length,
      progress_percent: 0,
      tasks: m.tasks || [],
      interruptions: [],
      comments: []
    }));

    const fullList = [...dailyRoutinesTodayData, ...cancelledOrOther];

    if (fullList.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">Nenhuma rotina diária cadastrada</div>
          <div class="empty-desc">Crie sua rotina diária com checklist e Pomodoro. Às 00:00 de cada dia ativo, ela entrará automaticamente em andamento.</div>
          <button class="btn btn-tasks" onclick="App.openDailyRoutineModal()">+ Nova Rotina Diária</button>
        </div>
      `;
      return;
    }

    const statusBadgeText = {
      em_andamento: 'Em Andamento',
      concluida: 'Concluída',
      interrompida: 'Interrompida',
      suspensa: 'Suspensa Temporariamente',
      cancelada: 'Cancelada Manualmente',
      fora_do_dia: 'Fora do Dia Agendado'
    };

    const cardClassByStatus = {
      em_andamento: 'routine-card-active',
      concluida: 'routine-card-completed',
      interrompida: 'routine-card-interrupted',
      suspensa: 'routine-card-suspended',
      cancelada: 'routine-card-cancelled',
      fora_do_dia: ''
    };

    container.innerHTML = fullList.map(r => {
      const st = r.status || 'em_andamento';
      const isCancelled = (st === 'cancelada' || r.routine_status === 'cancelada');
      const isSuspended = (st === 'suspensa');
      const isInterrupted = (st === 'interrompida');
      const isCompleted = (st === 'concluida');
      const isRunning = (st === 'em_andamento');
      const menuId = `kebab-daily-routine-${r.routine_id}`;

      const tasksHtml = (r.tasks || []).length > 0 ? `
        <div class="checklist-card-preview" style="margin-top:10px;">
          ${(r.tasks || []).map(t => `
            <label class="checklist-card-item ${t.done ? 'done' : ''}" style="display:flex; align-items:center; gap:8px; cursor:${isCancelled ? 'not-allowed' : 'pointer'};">
              <input type="checkbox" ${t.done ? 'checked' : ''} ${isCancelled ? 'disabled' : ''} onchange="App.toggleDailyRoutineTask(${r.routine_id}, ${t.id}, this.checked)">
              <span>${escapeHtml(t.title)}</span>
              <span style="margin-left:auto; font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(t.duration_label || formatMinutesToHoursAndMinutes(t.duration_minutes || t.estimated_minutes || 30))}</span>
            </label>
          `).join('')}
        </div>
      ` : '';

      const interruptionsHtml = (r.interruptions && r.interruptions.length > 0) ? `
        <div style="margin-top:10px; padding:8px 10px; background:rgba(245, 158, 11, 0.07); border-left:2px solid var(--accent-warning); border-radius:4px;">
          <div style="font-size:0.72rem; font-weight:700; color:var(--accent-warning); text-transform:uppercase; margin-bottom:4px;">Interrupções Registradas Hoje</div>
          ${r.interruptions.map(intr => `
            <div style="font-size:0.76rem; color:var(--text-secondary); margin-bottom:3px;">
              <strong style="font-family:var(--font-mono);">${escapeHtml((intr.interrupted_at || '').slice(11, 19))}</strong>
              ${intr.resumed_at ? `→ Retomada às <strong style="font-family:var(--font-mono);">${escapeHtml(intr.resumed_at.slice(11, 19))}</strong>` : '(Pausada)'}:
              <span>${escapeHtml(intr.reason)}</span>
            </div>
          `).join('')}
        </div>
      ` : '';

      const commentsHtml = (r.comments && r.comments.length > 0) ? `
        <div style="margin-top:8px; padding:8px 10px; background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle); border-radius:4px;">
          <div style="font-size:0.72rem; font-weight:700; color:var(--text-secondary); text-transform:uppercase; margin-bottom:4px;">Comentários Cronológicos</div>
          ${r.comments.map(c => `
            <div style="font-size:0.76rem; color:var(--text-primary); margin-bottom:3px;">
              <span style="font-family:var(--font-mono); color:var(--text-muted);">[${escapeHtml((c.created_at || '').slice(11, 16))}]</span>
              ${escapeHtml(c.comment_text)}
            </div>
          `).join('')}
        </div>
      ` : '';

      // RN01: Se cancelada manualmente, bloqueia Iniciar e Agendar Suspensão, permitindo apenas Reativar, Editar ou Excluir
      let actionButtons = '';
      if (isCancelled) {
        actionButtons = `
          <button type="button" class="btn btn-tasks btn-sm" onclick="App.reactivateDailyRoutine(${r.routine_id})">Reativar Rotina</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="App.openDailyRoutineModal(${r.routine_id})">Editar</button>
          <button type="button" class="btn btn-danger btn-sm" onclick="App.deleteDailyRoutine(${r.routine_id})">Excluir</button>
        `;
      } else {
        actionButtons = `
          ${isRunning ? `
            <button type="button" class="btn btn-tasks btn-sm" onclick="App.completeDailyRoutine(${r.routine_id})">Concluir</button>
            <button type="button" class="btn btn-secondary btn-sm" style="color:var(--accent-warning);" onclick="App.openInterruptRoutineModal(${r.routine_id})">Interromper</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="App.toggleRoutinePomodoro(${r.routine_id}, '${escapeHtml(r.title)}', ${r.total_planned_minutes || 30})">Iniciar Timer</button>
          ` : ''}
          ${isInterrupted ? `
            <button type="button" class="btn btn-tasks btn-sm" onclick="App.resumeDailyRoutine(${r.routine_id})">Retomar</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="App.completeDailyRoutine(${r.routine_id})">Concluir</button>
          ` : ''}
          ${(!isRunning && !isInterrupted && !isCompleted) ? `
            <button type="button" class="btn btn-tasks btn-sm" onclick="App.startDailyRoutine(${r.routine_id})">Iniciar Hoje</button>
          ` : ''}
          <button type="button" class="btn btn-secondary btn-sm" onclick="App.openRoutineCommentModal(${r.routine_id})">Comentar</button>
        `;
      }

      const totalPlannedText = r.total_planned_label
        ? ` • ${r.total_planned_label} planejados`
        : (r.total_planned_minutes ? ` • ${formatMinutesToHoursAndMinutes(r.total_planned_minutes)} planejados` : '');

      return `
        <div class="routine-card ${cardClassByStatus[st] || ''}">
          <div class="card-top-row" style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
            <div>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:4px;">
                <span class="badge-routine-status badge-status-${isCancelled ? 'cancelada' : st}">
                  ${escapeHtml(statusBadgeText[isCancelled ? 'cancelada' : st] || st)}
                </span>
                ${r.scheduled_time ? `<span class="routine-card-meta" style="font-size:0.75rem; font-family:var(--font-mono); color:var(--text-secondary);">Início: ${escapeHtml(r.scheduled_time)}</span>` : ''}
                <span class="routine-card-meta" style="font-size:0.75rem; color:var(--text-secondary);">${r.done_tasks || 0}/${r.total_tasks || 0} tarefas (${r.progress_percent || 0}%)${totalPlannedText}</span>
              </div>
              <h4 class="routine-card-title" style="font-size:1.05rem; font-weight:700;">${escapeHtml(r.title)}</h4>
              ${r.description ? `<p class="routine-card-meta" style="font-size:0.8rem; color:var(--text-secondary); margin-top:2px;">${escapeHtml(r.description)}</p>` : ''}
            </div>

            <div class="card-kebab-wrap">
              <button type="button" class="btn-card-kebab" onclick="App.toggleCardMenu(event, '${menuId}')" aria-label="Opções da Rotina">&#8942;</button>
              <div class="card-kebab-menu" id="${menuId}">
                ${isCancelled ? `
                  <button type="button" class="card-kebab-item" onclick="App.reactivateDailyRoutine(${r.routine_id})">Reativar Rotina</button>
                  <button type="button" class="card-kebab-item" onclick="App.openDailyRoutineModal(${r.routine_id})">Editar</button>
                  <button type="button" class="card-kebab-item danger" onclick="App.deleteDailyRoutine(${r.routine_id})">Excluir</button>
                ` : `
                  <button type="button" class="card-kebab-item" onclick="App.openDailyRoutineModal(${r.routine_id})">Editar Rotina</button>
                  <button type="button" class="card-kebab-item" onclick="App.openRoutineSuspensionModal(${r.routine_id})">Suspender Temporariamente</button>
                  <button type="button" class="card-kebab-item danger" onclick="App.cancelDailyRoutine(${r.routine_id})">Cancelar Manualmente</button>
                  <button type="button" class="card-kebab-item danger" onclick="App.deleteDailyRoutine(${r.routine_id})">Excluir</button>
                `}
              </div>
            </div>
          </div>

          ${tasksHtml}
          ${interruptionsHtml}
          ${commentsHtml}

          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-top:12px; padding-top:10px; border-top:1px solid var(--border-subtle);">
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              ${actionButtons}
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  function addDailyRoutineTaskInputRow(titleVal = '', totalMinutesVal = 30) {
    const container = document.getElementById('daily-routine-tasks-builder');
    if (!container) return;
    const totalMinutes = Math.max(1, parseInt(totalMinutesVal, 10) || 30);
    const defaultHours = Math.floor(totalMinutes / 60);
    const defaultMins = totalMinutes % 60;

    const row = document.createElement('div');
    row.className = 'daily-routine-task-row';
    row.style = 'display:grid; grid-template-columns:1fr 70px 70px auto; gap:6px; align-items:center;';
    row.innerHTML = `
      <input type="text" class="form-input dr-task-title" placeholder="Nome da tarefa ou etapa..." value="${escapeHtml(titleVal)}" required>
      <div style="display:flex; align-items:center; gap:2px;">
        <input type="number" class="form-input dr-task-hours" min="0" max="23" value="${defaultHours}" placeholder="0" title="Horas" oninput="App.updateDailyRoutineTotalDuration()" style="padding:6px 6px; text-align:center;">
        <span style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">h</span>
      </div>
      <div style="display:flex; align-items:center; gap:2px;">
        <input type="number" class="form-input dr-task-mins" min="0" max="59" value="${defaultMins}" placeholder="30" title="Minutos" oninput="App.updateDailyRoutineTotalDuration()" style="padding:6px 6px; text-align:center;">
        <span style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">m</span>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" onclick="this.closest('.daily-routine-task-row').remove(); App.updateDailyRoutineTotalDuration();" title="Remover Tarefa">×</button>
    `;
    container.appendChild(row);
    updateDailyRoutineTotalDuration();
  }

  function updateDailyRoutineTotalDuration() {
    let totalMinutes = 0;
    document.querySelectorAll('#daily-routine-tasks-builder .daily-routine-task-row').forEach(row => {
      const h = parseInt(row.querySelector('.dr-task-hours')?.value, 10) || 0;
      const m = parseInt(row.querySelector('.dr-task-mins')?.value, 10) || 0;
      const rowMinutes = (h * 60) + m;
      totalMinutes += Math.max(0, rowMinutes);
    });

    const badge = document.getElementById('daily-routine-total-duration-badge');
    if (badge) {
      badge.innerText = formatMinutesToHoursAndMinutes(totalMinutes || 0);
    }
    return totalMinutes;
  }

  async function openDailyRoutineModal(routineId = null) {
    const form = document.getElementById('form-daily-routine');
    if (form) form.reset();
    const idInput = document.getElementById('daily-routine-id');
    const titleModal = document.getElementById('modal-daily-routine-title');
    const tasksBuilder = document.getElementById('daily-routine-tasks-builder');
    if (tasksBuilder) tasksBuilder.innerHTML = '';

    if (routineId) {
      if (titleModal) titleModal.innerText = 'Editar Rotina Diária';
      let routine = (allDailyRoutinesMaster || []).find(r => Number(r.id) === Number(routineId));
      if (!routine) {
        try {
          routine = await apiFetch(`/api/daily-routines/${routineId}`);
        } catch (e) {
          console.error(e);
        }
      }
      if (routine) {
        if (idInput) idInput.value = routine.id;
        document.getElementById('daily-routine-title-input').value = routine.title || '';
        document.getElementById('daily-routine-desc-input').value = routine.description || '';
        document.getElementById('daily-routine-time-input').value = routine.scheduled_time || '08:00';

        const dows = new Set(String(routine.days_of_week || '0,1,2,3,4,5,6').split(',').map(s => s.trim()));
        document.querySelectorAll('#daily-routine-dow-group input[type="checkbox"]').forEach(cb => {
          cb.checked = dows.has(cb.value);
        });

        if (routine.tasks && routine.tasks.length) {
          routine.tasks.forEach(t => {
            const taskMins = t.duration_minutes !== undefined ? t.duration_minutes : (t.estimated_minutes || 30);
            addDailyRoutineTaskInputRow(t.title, taskMins);
          });
        } else {
          addDailyRoutineTaskInputRow('', 30);
        }
      }
    } else {
      if (titleModal) titleModal.innerText = 'Nova Rotina Diária';
      if (idInput) idInput.value = '';
      document.querySelectorAll('#daily-routine-dow-group input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
      });
      addDailyRoutineTaskInputRow('', 30);
    }

    updateDailyRoutineTotalDuration();
    openModal('modal-daily-routine');
  }

  async function saveDailyRoutineSubmit(e) {
    e.preventDefault();
    const id = document.getElementById('daily-routine-id').value;
    const title = document.getElementById('daily-routine-title-input').value.trim();
    const description = document.getElementById('daily-routine-desc-input').value.trim();
    const scheduled_time = document.getElementById('daily-routine-time-input').value || '08:00';

    const checkedDows = [];
    document.querySelectorAll('#daily-routine-dow-group input[type="checkbox"]:checked').forEach(cb => {
      checkedDows.push(cb.value);
    });
    const days_of_week = checkedDows.length ? checkedDows.join(',') : '0,1,2,3,4,5,6';

    const tasks = [];
    document.querySelectorAll('#daily-routine-tasks-builder .daily-routine-task-row').forEach((row, idx) => {
      const tTitle = row.querySelector('.dr-task-title')?.value.trim();
      const h = parseInt(row.querySelector('.dr-task-hours')?.value, 10) || 0;
      const m = parseInt(row.querySelector('.dr-task-mins')?.value, 10) || 0;
      const duration_minutes = Math.max(1, (h * 60) + m);
      if (tTitle) {
        tasks.push({ title: tTitle, duration_minutes, position: idx });
      }
    });

    if (tasks.length === 0) {
      showToast('Adicione pelo menos uma tarefa para a rotina');
      return;
    }

    try {
      const payload = { title, description, scheduled_time, days_of_week, tasks };
      if (id) {
        await apiFetch(`/api/daily-routines/${id}`, {
          method: 'PUT',
          body: payload
        });
        showToast('Rotina diária atualizada!');
      } else {
        await apiFetch('/api/daily-routines', {
          method: 'POST',
          body: payload
        });
        showToast('Nova rotina diária criada!');
      }
      closeModals();
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message || 'Erro ao salvar rotina diária');
    }
  }

  async function startDailyRoutine(routineId) {
    try {
      await apiFetch(`/api/daily-routines/${routineId}/start`, { method: 'POST', body: {} });
      showToast('Rotina iniciada!');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  // RF03 & Decisão 02: Interromper pausa o timer imediatamente e exige motivo obrigatório
  function openInterruptRoutineModal(routineId) {
    pauseRoutinePomodoro();
    document.getElementById('interrupt-routine-id').value = routineId;
    document.getElementById('interrupt-reason-input').value = '';
    openModal('modal-routine-interrupt');
  }

  async function submitInterruptRoutine(e) {
    e.preventDefault();
    const routineId = document.getElementById('interrupt-routine-id').value;
    const reason = document.getElementById('interrupt-reason-input').value.trim();
    if (!reason) {
      showToast('A justificativa da interrupção é obrigatória.');
      return;
    }
    try {
      pauseRoutinePomodoro();
      await apiFetch(`/api/daily-routines/${routineId}/interrupt`, {
        method: 'POST',
        body: { reason, elapsed_seconds: routinePomoState.elapsedBaseSec || 0 }
      });
      closeModals();
      showToast('Rotina interrompida e justificativa registrada.');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function resumeDailyRoutine(routineId) {
    try {
      await apiFetch(`/api/daily-routines/${routineId}/resume`, { method: 'POST', body: {} });
      showToast('Rotina retomada!');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function completeDailyRoutine(routineId) {
    try {
      pauseRoutinePomodoro();
      await apiFetch(`/api/daily-routines/${routineId}/complete`, {
        method: 'POST',
        body: { elapsed_seconds: routinePomoState.elapsedBaseSec || 0 }
      });
      showToast('Rotina concluída com sucesso!');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  // RF05 & RN01: Cancelamento Manual Imediato
  async function cancelDailyRoutine(routineId) {
    if (!confirm('Deseja cancelar manualmente esta rotina? Ela ficará desativada até ser reativada manualmente.')) return;
    try {
      pauseRoutinePomodoro();
      await apiFetch(`/api/daily-routines/${routineId}/cancel`, { method: 'POST', body: {} });
      showToast('Rotina cancelada manualmente.');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function reactivateDailyRoutine(routineId) {
    try {
      await apiFetch(`/api/daily-routines/${routineId}/reactivate`, { method: 'POST', body: {} });
      showToast('Rotina reativada com sucesso!');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function deleteDailyRoutine(routineId) {
    if (!confirm('Excluir permanentemente esta rotina diária e seu histórico?')) return;
    try {
      await apiFetch(`/api/daily-routines/${routineId}`, { method: 'DELETE' });
      showToast('Rotina excluída.');
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function toggleDailyRoutineTask(routineId, taskId, doneBool) {
    try {
      await apiFetch(`/api/daily-routines/${routineId}/tasks/${taskId}`, {
        method: 'PATCH',
        body: { done: doneBool }
      });
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  // RF04: Comentários Cronológicos na Rotina
  function openRoutineCommentModal(routineId) {
    document.getElementById('comment-routine-id').value = routineId;
    document.getElementById('routine-comment-input').value = '';
    openModal('modal-routine-comment');
  }

  async function submitRoutineComment(e) {
    e.preventDefault();
    const routineId = document.getElementById('comment-routine-id').value;
    const comment_text = document.getElementById('routine-comment-input').value.trim();
    if (!comment_text) return;
    try {
      await apiFetch(`/api/daily-routines/${routineId}/comments`, {
        method: 'POST',
        body: { comment_text }
      });
      closeModals();
      showToast('Comentário registrado na rotina.');
      await loadDailyRoutinesData();
    } catch (err) {
      showToast(err.message);
    }
  }

  // RF06, RN02, US01: Agendamento de Suspensão Temporária
  function setRoutineSuspensionType(typeVal) {
    document.getElementById('suspension-type-input').value = typeVal;
    document.getElementById('btn-susp-type-range')?.classList.toggle('active', typeVal === 'date_range');
    document.getElementById('btn-susp-type-dow')?.classList.toggle('active', typeVal === 'days_of_week');
    const dowWrap = document.getElementById('suspension-dow-wrap');
    if (dowWrap) dowWrap.style.display = (typeVal === 'days_of_week') ? 'block' : 'none';
  }

  async function openRoutineSuspensionModal(preselectedRoutineId = null) {
    if (!allDailyRoutinesMaster || !allDailyRoutinesMaster.length) {
      try {
        allDailyRoutinesMaster = await apiFetch('/api/daily-routines');
      } catch (_) {}
    }
    const activeRoutines = (allDailyRoutinesMaster || []).filter(r => r.status !== 'cancelada');
    if (!activeRoutines.length) {
      showToast('Nenhuma rotina ativa disponível para agendar suspensão.');
      return;
    }
    const sel = document.getElementById('suspension-routine-select');
    if (sel) {
      sel.innerHTML = activeRoutines.map(r =>
        `<option value="${r.id}" ${preselectedRoutineId && Number(r.id) === Number(preselectedRoutineId) ? 'selected' : ''}>${escapeHtml(r.title)}</option>`
      ).join('');
    }
    const today = new Date().toISOString().slice(0, 10);
    document.getElementById('suspension-start-input').value = today;
    document.getElementById('suspension-end-input').value = today;
    document.getElementById('suspension-reason-input').value = '';
    setRoutineSuspensionType('date_range');
    openModal('modal-routine-suspension');
  }

  async function submitRoutineSuspension(e) {
    e.preventDefault();
    const routineId = document.getElementById('suspension-routine-select').value;
    const suspension_type = document.getElementById('suspension-type-input').value || 'date_range';
    const start_date = document.getElementById('suspension-start-input').value;
    const end_date = document.getElementById('suspension-end-input').value;
    const reason = document.getElementById('suspension-reason-input').value.trim();

    const dows = [];
    document.querySelectorAll('#suspension-dow-group input[type="checkbox"]:checked').forEach(cb => dows.push(cb.value));

    try {
      await apiFetch(`/api/daily-routines/${routineId}/suspensions`, {
        method: 'POST',
        body: {
          suspension_type,
          start_date,
          end_date,
          days_of_week: dows.join(','),
          reason
        }
      });
      closeModals();
      showToast('Suspensão temporária agendada com retorno automático!');
      await loadDailyRoutinesData();
      if (activeRoutinesSubTab === 'calendario') loadRoutinesCalendar();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function deleteRoutineSuspension(suspId) {
    if (!confirm('Remover este agendamento de suspensão temporária?')) return;
    try {
      await apiFetch(`/api/daily-routines/suspensions/${suspId}`, { method: 'DELETE' });
      showToast('Suspensão removida.');
      await loadRoutinesCalendar();
      await loadDailyRoutinesData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message);
    }
  }

  // ==================== CALENDÁRIO DE ROTINAS DIÁRIAS (IDÊNTICO AO RITMO) ====================
  let selectedRoutinesMonth = null;

  function onRoutinesCalendarMonthChange(mVal) {
    if (!mVal) return;
    selectedRoutinesMonth = mVal;
    loadRoutinesCalendar(mVal);
  }

  function setRoutinesCalendarViewMode(mode) {
    routinesCalendarViewMode = mode;
    loadRoutinesCalendar();
  }

  async function loadRoutinesCalendar(monthStr) {
    const gridEl = document.getElementById('routines-calendar-grid');
    const monthInput = document.getElementById('routines-calendar-month-input') || document.getElementById('routines-calendar-month');
    const monthTitle = document.getElementById('routines-calendar-month-title');
    const suspListEl = document.getElementById('routines-suspensions-list');
    if (!gridEl) return;

    if (!monthStr) {
      monthStr = selectedRoutinesMonth || (monthInput && monthInput.value) || new Date().toISOString().slice(0, 7);
    }
    selectedRoutinesMonth = monthStr;
    if (monthInput && monthInput.value !== monthStr) {
      monthInput.value = monthStr;
    }

    try {
      const [yStr, mStr] = monthStr.split('-');
      const year = parseInt(yStr, 10);
      const month = parseInt(mStr, 10);
      const monthDate = new Date(year, month - 1, 1);
      const monthLabel = monthDate.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
      if (monthTitle) {
        monthTitle.innerText = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
      }

      const data = await apiFetch(`/api/daily-routines/calendar?month=${monthStr}`);
      const days = data.days || [];
      const suspensions = data.suspensions || [];
      const todayStr = new Date().toISOString().slice(0, 10);

      const daysMap = {};
      let totalRuns = 0;
      const completedDaysSet = new Set();
      const interruptedDaysSet = new Set();
      const suspendedDaysSet = new Set();
      const inProgressDaysSet = new Set();

      days.forEach(d => {
        daysMap[d.date] = d;
        (d.items || []).forEach(it => {
          const st = it.state || it.status;
          if (st === 'concluida') {
            completedDaysSet.add(d.date);
            totalRuns++;
          } else if (st === 'em_andamento') {
            inProgressDaysSet.add(d.date);
            totalRuns++;
          } else if (st === 'interrompida') {
            interruptedDaysSet.add(d.date);
            totalRuns++;
          } else if (st === 'suspensa') {
            suspendedDaysSet.add(d.date);
          }
        });
      });

      const totalRunsEl = document.getElementById('routines-cal-total-runs');
      const completedDaysEl = document.getElementById('routines-cal-completed-days');
      const interruptedDaysEl = document.getElementById('routines-cal-interrupted-days');

      if (totalRunsEl) totalRunsEl.innerText = totalRuns;
      if (completedDaysEl) completedDaysEl.innerText = completedDaysSet.size;
      if (interruptedDaysEl) interruptedDaysEl.innerText = interruptedDaysSet.size + suspendedDaysSet.size;

      const firstDayWeekIndex = new Date(year, month - 1, 1).getDay();
      const daysInMonth = new Date(year, month, 0).getDate();

      let html = '';
      const weekdays = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
      weekdays.forEach(w => {
        html += `<div class="calendar-weekday">${w}</div>`;
      });

      for (let i = 0; i < firstDayWeekIndex; i++) {
        html += `<div class="calendar-day empty"></div>`;
      }

      for (let day = 1; day <= daysInMonth; day++) {
        const dStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const dayData = daysMap[dStr];
        const items = (dayData && dayData.items) || [];
        const isToday = (dStr === todayStr);

        const hasCompleted = items.some(it => (it.state || it.status) === 'concluida');
        const hasInProgress = items.some(it => (it.state || it.status) === 'em_andamento');
        const hasInterrupted = items.some(it => (it.state || it.status) === 'interrompida');
        const hasSuspended = items.some(it => (it.state || it.status) === 'suspensa');
        const hasScheduled = items.some(it => (it.state || it.status) === 'planejada' || (it.state || it.status) === 'agendada');

        const classes = ['calendar-day'];
        if (isToday) classes.push('today');
        if (hasCompleted) classes.push('completed');
        if (hasInProgress) classes.push('in-progress');
        if (hasInterrupted) classes.push('interrupted');
        if (hasSuspended) classes.push('suspended');

        let dotsHtml = '';
        if (hasCompleted) dotsHtml += '<span class="cal-dot completed" title="Rotina concluída"></span>';
        if (hasInProgress) dotsHtml += '<span class="cal-dot in-progress" title="Rotina em andamento"></span>';
        if (hasInterrupted) dotsHtml += '<span class="cal-dot interrupted" title="Rotina interrompida"></span>';
        if (hasSuspended) dotsHtml += '<span class="cal-dot suspended" title="Rotina suspensa"></span>';
        if (!hasCompleted && !hasInProgress && !hasInterrupted && !hasSuspended && hasScheduled) {
          dotsHtml += '<span class="cal-dot scheduled" title="Rotina planejada"></span>';
        }

        html += `
          <button type="button" class="${classes.join(' ')}" onclick="App.openRoutinesDayDetails('${dStr}')" aria-label="Dia ${day}">
            <span>${day}</span>
            <div class="calendar-day-dots">${dotsHtml}</div>
          </button>
        `;
      }

      gridEl.className = 'calendar-grid';
      gridEl.innerHTML = html;

      if (suspListEl) {
        if (!suspensions.length) {
          suspListEl.innerHTML = '<div style="font-size:0.8rem; color:var(--text-muted); padding:8px 0;">Nenhuma suspensão temporária agendada.</div>';
        } else {
          const rMap = {};
          (data.routines || []).forEach(r => { rMap[r.id] = r.title; });
          suspListEl.innerHTML = suspensions.map(s => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 10px; border-bottom:1px solid var(--border-subtle); gap:8px;">
              <div>
                <div style="font-size:0.84rem; font-weight:700;">${escapeHtml(rMap[s.routine_id] || s.routine_title || `Rotina #${s.routine_id}`)} <span class="badge-routine-status badge-status-suspensa">Suspensa</span></div>
                <div style="font-size:0.75rem; color:var(--text-secondary);">Período: ${formatDateFull(s.start_date)} até ${formatDateFull(s.end_date)} ${s.reason ? `• ${escapeHtml(s.reason)}` : ''}</div>
              </div>
              <button type="button" class="btn btn-danger btn-sm" onclick="App.deleteRoutineSuspension(${s.id})">Remover</button>
            </div>
          `).join('');
        }
      }
    } catch (e) {
      console.error('Erro ao carregar calendário de rotinas:', e);
      gridEl.innerHTML = `<div class="error-state" style="grid-column:1/-1;">Erro ao carregar calendário de rotinas: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function openRoutinesDayDetails(dateStr) {
    const modal = document.getElementById('modal-routines-day-details');
    const title = document.getElementById('routines-day-modal-title');
    const body = document.getElementById('routines-day-modal-body');
    if (!modal || !body) return;

    const [y, m, d] = dateStr.split('-');
    const formatted = `${d}/${m}/${y}`;
    if (title) title.innerText = `Detalhes de ${formatted}`;
    body.innerHTML = '<div class="skeleton"></div><p style="text-align:center; color:var(--text-muted); font-size:0.875rem;">Carregando estado do dia...</p>';
    modal.classList.add('active');

    try {
      const dayData = await apiFetch(`/api/daily-routines/day/${dateStr}`);
      const logs = dayData.logs || [];
      const configured = dayData.configured_routines || [];
      const sleep = dayData.sleep;
      const isToday = dayData.is_today;

      let html = '';

      if (logs.length > 0) {
        logs.forEach(l => {
          const st = l.status;
          let cardClass = 'temporal-routine-in-progress';
          let statusLabel = 'Em Andamento';
          let badgeColor = 'var(--accent-tasks)';

          if (st === 'concluida') {
            cardClass = 'temporal-routine-completed';
            statusLabel = 'Concluída';
            badgeColor = '#22c55e';
          } else if (st === 'interrompida') {
            cardClass = 'temporal-routine-interrupted';
            statusLabel = 'Interrompida';
            badgeColor = '#ef4444';
          } else if (st === 'suspensa') {
            cardClass = 'temporal-routine-suspended';
            statusLabel = 'Suspensa';
            badgeColor = '#94a3b8';
          }

          const focusMin = Math.round((l.total_focus_seconds || 0) / 60);
          const tasks = l.tasks || [];
          const tasksDone = tasks.filter(t => t.done).length;
          const tasksSummary = tasks.length > 0
            ? `<div style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:8px;">Subtarefas: ${tasksDone}/${tasks.length} concluídas</div>`
            : '';

          const interruptionsHtml = (l.interruptions || []).map(i => `
            <div style="font-size:0.75rem; color:#ef4444; margin-top:3px;">
              • Pausa às ${(i.interrupted_at || '').slice(11, 16)}: ${escapeHtml(i.reason || 'Sem motivo')}
            </div>
          `).join('');

          const commentsHtml = (l.comments || []).map(c => `
            <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:3px;">
              • [${(c.created_at || '').slice(11, 16)}] ${escapeHtml(c.comment_text)}
            </div>
          `).join('');

          let actionsHtml = '';
          if (isToday) {
            if (st === 'em_andamento') {
              actionsHtml = `
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">
                  <button type="button" class="btn btn-primary btn-sm" onclick="App.closeModals(); App.setRoutinesTab('hoje');">Ir para Hoje →</button>
                  <button type="button" class="btn btn-warning btn-sm" onclick="App.closeModals(); App.openRoutineInterruptModal(${l.routine_id});">Interromper</button>
                  <button type="button" class="btn btn-tasks btn-sm" onclick="App.closeModals(); App.completeDailyRoutine(${l.routine_id});">Concluir</button>
                </div>
              `;
            } else if (st === 'interrompida') {
              actionsHtml = `
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">
                  <button type="button" class="btn btn-tasks btn-sm" onclick="App.closeModals(); App.resumeDailyRoutine(${l.routine_id});">Retomar Rotina</button>
                </div>
              `;
            }
          }

          html += `
            <div class="temporal-card ${cardClass}" style="margin-bottom:10px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span style="color:${badgeColor}; font-size:0.75rem; font-weight:700; text-transform:uppercase;">${statusLabel}</span>
                <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted);">${l.scheduled_time || ''}</span>
              </div>
              <h4 style="font-size:1.05rem; font-weight:700; margin:0 0 6px;">${escapeHtml(l.routine_title)}</h4>
              ${tasksSummary}
              <div style="font-size:0.8rem; color:var(--text-secondary);">
                Foco total: ${focusMin} minutos
                ${l.started_at ? ` • Iniciada às ${l.started_at.slice(11, 16)}` : ''}
                ${l.completed_at ? ` • Concluída às ${l.completed_at.slice(11, 16)}` : ''}
              </div>
              ${interruptionsHtml}
              ${commentsHtml}
              ${actionsHtml}
            </div>
          `;
        });
      } else if (configured.length > 0) {
        configured.forEach(r => {
          const isSusp = r.is_suspended;
          html += `
            <div class="temporal-card ${isSusp ? 'temporal-routine-suspended' : 'temporal-today-ready'}" style="margin-bottom:10px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span style="color:${isSusp ? '#94a3b8' : 'var(--accent-primary)'}; font-size:0.75rem; font-weight:700; text-transform:uppercase;">
                  ${isSusp ? 'Suspensa' : (isToday ? 'Pronta para Hoje' : 'Planejada')}
                </span>
                <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted);">${r.scheduled_time || ''}</span>
              </div>
              <h4 style="font-size:1.05rem; font-weight:700; margin:0 0 6px;">${escapeHtml(r.title)}</h4>
              <p style="font-size:0.8rem; color:var(--text-secondary); margin:0;">
                ${isSusp ? `Suspensão ativa para esta data: ${escapeHtml((r.suspension && r.suspension.reason) || 'Suspensão agendada')}` : (isToday ? 'Rotina programada para hoje. Abra a aba Rotina de Hoje para iniciar.' : 'Rotina regular agendada no ciclo semanal.')}
              </p>
              ${isToday && !isSusp ? `
                <div style="margin-top:10px;">
                  <button type="button" class="btn btn-primary btn-sm" onclick="App.closeModals(); App.setRoutinesTab('hoje');">Abrir Rotina de Hoje →</button>
                </div>
              ` : ''}
            </div>
          `;
        });
      } else {
        html += `
          <div class="temporal-card temporal-past-rest">
            <h4 style="font-size:1.05rem; font-weight:700; margin-bottom:6px;">Dia sem Rotina</h4>
            <p style="font-size:0.8125rem; color:var(--text-muted); margin:0;">
              Nenhuma rotina diária registrada ou programada para esta data.
            </p>
          </div>
        `;
      }

      if (sleep) {
        const sleepHours = Math.floor((sleep.duration_minutes || 0) / 60);
        const sleepMin = (sleep.duration_minutes || 0) % 60;
        const compLabels = {
          no_horario: 'No Horário',
          nao_conseguiu_dormir: 'Não Dormiu',
          dormiu_menos: 'Dormiu Menos',
          dormiu_mais: 'Dormiu Mais'
        };
        html += `
          <div class="card" style="margin-top:10px; background:rgba(0,0,0,0.3); border:1px solid var(--border-subtle); padding:12px;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--accent-tasks); text-transform:uppercase; margin-bottom:4px;">Registro de Sono</div>
            <div style="font-size:0.875rem; font-weight:600; color:var(--text-primary);">
              ${sleepHours}h ${sleepMin}m de sono • <span style="font-size:0.8rem; color:var(--text-secondary);">${compLabels[sleep.compliance_status] || sleep.compliance_status}</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
              ${sleep.bedtime || ''} às ${sleep.wake_time || ''} ${sleep.quality_rating ? `• Avaliação: ${sleep.quality_rating}/5` : ''} ${sleep.notes ? `• ${escapeHtml(sleep.notes)}` : ''}
            </div>
          </div>
        `;
      }

      body.innerHTML = html;
    } catch (e) {
      console.error('Falha ao obter detalhes do dia da rotina:', e);
      body.innerHTML = `<div class="error-state">Erro ao carregar detalhes: ${escapeHtml(e.message)}</div>`;
    }
  }

  // RF10: Sub-aba Histórico de Rotinas com filtro de período e correlação de sono
  function setRoutinesHistoryRange(daysCount) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (daysCount || 30));
    const sEl = document.getElementById('routines-hist-start');
    const eEl = document.getElementById('routines-hist-end');
    if (sEl) sEl.value = start.toISOString().slice(0, 10);
    if (eEl) eEl.value = end.toISOString().slice(0, 10);
    loadRoutinesHistory();
  }

  async function loadRoutinesHistory() {
    const sEl = document.getElementById('routines-hist-start');
    const eEl = document.getElementById('routines-hist-end');
    const listEl = document.getElementById('routines-history-list');
    if (!listEl) return;

    const endStr = (eEl && eEl.value) ? eEl.value : new Date().toISOString().slice(0, 10);
    const startDefault = new Date();
    startDefault.setDate(startDefault.getDate() - 30);
    const startStr = (sEl && sEl.value) ? sEl.value : startDefault.toISOString().slice(0, 10);
    if (sEl && !sEl.value) sEl.value = startStr;
    if (eEl && !eEl.value) eEl.value = endStr;

    try {
      const res = await apiFetch(`/api/daily-routines/history?start_date=${startStr}&end_date=${endStr}`);
      const sum = res.summary || {};
      const rateEl = document.getElementById('routines-hist-rate');
      const compEl = document.getElementById('routines-hist-completed');
      const intrEl = document.getElementById('routines-hist-interrupted');
      const suspEl = document.getElementById('routines-hist-suspended');
      if (rateEl) rateEl.innerText = `${sum.completion_rate || 0}%`;
      if (compEl) compEl.innerText = sum.completed || 0;
      if (intrEl) intrEl.innerText = sum.interrupted || 0;
      if (suspEl) suspEl.innerText = sum.suspended || 0;

      const items = res.items || [];
      if (!items.length) {
        listEl.innerHTML = '<div class="empty-state" style="padding:18px;">Nenhum registro de rotina encontrado no período selecionado.</div>';
        return;
      }

      listEl.innerHTML = items.map(it => {
        const intrList = (it.interruptions || []).map(i =>
          `<div style="font-size:0.74rem; color:var(--accent-warning);">• Pausa às ${escapeHtml((i.interrupted_at || '').slice(11, 19))}: ${escapeHtml(i.reason)}</div>`
        ).join('');
        const commList = (it.comments || []).map(c =>
          `<div style="font-size:0.74rem; color:var(--text-secondary);">• [${escapeHtml((c.created_at || '').slice(11, 16))}] ${escapeHtml(c.comment_text)}</div>`
        ).join('');
        const sleepInfo = it.sleep
          ? `Sono no dia: ${Math.floor((it.sleep.duration_minutes || 0) / 60)}h${(it.sleep.duration_minutes || 0) % 60}m (${escapeHtml(it.sleep.compliance_status || 'no_horario')})`
          : 'Sem registro de sono no dia';

        const plannedLabel = it.total_planned_minutes ? formatMinutesToHoursAndMinutes(it.total_planned_minutes) : '';

        return `
          <div style="padding:12px 14px; background:#000000; border:1px solid var(--border-subtle); border-radius:var(--radius-sm); margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
              <div style="font-weight:700; font-size:0.92rem;">${escapeHtml(it.routine_title)} <span class="badge-routine-status badge-status-${it.status}">${escapeHtml(it.status)}</span>${plannedLabel ? `<span style="font-size:0.75rem; font-family:var(--font-mono); color:var(--text-secondary); margin-left:6px;">(${escapeHtml(plannedLabel)})</span>` : ''}</div>
              <span style="font-family:var(--font-mono); font-size:0.76rem; color:var(--text-secondary);">${formatDateFull(it.log_date)}</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:4px;">${sleepInfo}</div>
            ${intrList}
            ${commList}
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error('Erro ao carregar histórico de rotinas:', e);
    }
  }

  // RF07: Sub-aba Monitoramento de Sono e Conformidade
  async function loadRoutinesSleepSubTab() {
    try {
      const [settings, sumRes, logsRes] = await Promise.all([
        apiFetch('/api/settings/sleep'),
        apiFetch('/api/sleep/summary'),
        apiFetch('/api/sleep/logs?days=30')
      ]);

      state.plannedBedtime = settings.planned_bedtime || '23:00';
      state.plannedWakeTime = settings.planned_wake_time || '07:00';
      const bedIn = document.getElementById('setting-planned-bedtime');
      const wakeIn = document.getElementById('setting-planned-waketime');
      if (bedIn) bedIn.value = state.plannedBedtime;
      if (wakeIn) wakeIn.value = state.plannedWakeTime;

      const compCounts = sumRes.compliance_counts || {};
      const sumBox = document.getElementById('routines-sleep-compliance-summary');
      if (sumBox) {
        sumBox.innerHTML = `
          <div class="metric-card" style="padding:10px;"><div class="metric-label">No Horário</div><div class="metric-value" style="font-size:1.1rem; color:var(--accent-income);">${compCounts.no_horario || 0}</div></div>
          <div class="metric-card" style="padding:10px;"><div class="metric-label">Dormiu Menos</div><div class="metric-value" style="font-size:1.1rem; color:var(--accent-warning);">${compCounts.dormiu_menos || 0}</div></div>
          <div class="metric-card" style="padding:10px;"><div class="metric-label">Dormiu Mais</div><div class="metric-value" style="font-size:1.1rem; color:var(--accent-tasks);">${compCounts.dormiu_mais || 0}</div></div>
          <div class="metric-card" style="padding:10px;"><div class="metric-label">Não Dormiu</div><div class="metric-value" style="font-size:1.1rem; color:var(--accent-expense);">${compCounts.nao_conseguiu_dormir || 0}</div></div>
        `;
      }

      const listEl = document.getElementById('routines-sleep-logs-list');
      if (listEl) {
        if (!logsRes || !logsRes.length) {
          listEl.innerHTML = '<div class="empty-state" style="padding:16px;">Nenhum registro de sono cadastrado.</div>';
        } else {
          const labels = {
            no_horario: 'Dormiu no Horário',
            dormiu_menos: 'Dormiu Menos',
            dormiu_mais: 'Dormiu Mais',
            nao_conseguiu_dormir: 'Não Conseguiu Dormir'
          };
          listEl.innerHTML = logsRes.map(l => {
            const h = Math.floor((l.duration_minutes || 0) / 60);
            const m = (l.duration_minutes || 0) % 60;
            return `
              <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid var(--border-subtle); gap:8px;">
                <div>
                  <div style="font-weight:700; font-size:0.88rem;">${escapeHtml(labels[l.compliance_status] || 'Dormiu no Horário')} • ${h}h ${m}m</div>
                  <div style="font-size:0.75rem; color:var(--text-secondary);">Real: ${l.bedtime} - ${l.wake_time} | Planejado: ${l.planned_bedtime || '23:00'} - ${l.planned_wake_time || '07:00'}</div>
                </div>
                <span style="font-family:var(--font-mono); font-size:0.76rem; color:var(--text-muted);">${l.sleep_date}</span>
              </div>
            `;
          }).join('');
        }
      }
    } catch (e) {
      console.error('Erro ao carregar sub-aba de sono:', e);
    }
  }

  async function saveSleepSettingsSubmit(e) {
    e.preventDefault();
    const planned_bedtime = document.getElementById('setting-planned-bedtime').value || '23:00';
    const planned_wake_time = document.getElementById('setting-planned-waketime').value || '07:00';
    try {
      await apiFetch('/api/settings/sleep', {
        method: 'PUT',
        body: { planned_bedtime, planned_wake_time }
      });
      state.plannedBedtime = planned_bedtime;
      state.plannedWakeTime = planned_wake_time;
      showToast('Horários planejados de sono atualizados!');
      loadRoutinesSleepSubTab();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function quickLogSleepCompliance(complianceStatus) {
    const today = new Date().toISOString().slice(0, 10);
    const bed = state.plannedBedtime || '23:00';
    const wake = state.plannedWakeTime || '07:00';
    try {
      await apiFetch('/api/sleep/logs', {
        method: 'POST',
        body: {
          sleep_date: today,
          bedtime: bed,
          wake_time: wake,
          planned_bedtime: bed,
          planned_wake_time: wake,
          compliance_status: complianceStatus,
          quality_rating: complianceStatus === 'no_horario' ? 5 : (complianceStatus === 'nao_conseguiu_dormir' ? 1 : 3),
          notes: 'Registro rápido pela Rotina de Hoje'
        }
      });
      showToast('Conformidade de sono registrada para hoje!');
    } catch (err) {
      showToast(err.message);
    }
  }

  // ==================== v1.4.0: EVOLUÇÃO POR EXERCÍCIO NO RITMO (RF13, RF14, RN05, RNF01, US03) ====================
  let performedExercisesList = [];
  let selectedEvolutionExerciseId = null;
  let selectedEvolutionMode = 'max_load'; // 'max_load' | 'total_volume' | 'total_reps'
  let selectedEvolutionPeriod = 'all'; // '1m' | '3m' | '6m' | '1y' | 'all'
  const exerciseEvolutionCache = new Map();

  async function loadRitmoExerciseEvolutionInit() {
    try {
      const list = await apiFetch('/api/ritmo/performed-exercises');
      performedExercisesList = list || [];
      renderRitmoEvolutionExerciseOptions(performedExercisesList);
      if (performedExercisesList.length > 0) {
        const firstId = selectedEvolutionExerciseId && performedExercisesList.some(x => Number(x.id) === Number(selectedEvolutionExerciseId))
          ? selectedEvolutionExerciseId
          : performedExercisesList[0].id;
        await selectRitmoEvolutionExercise(firstId);
      } else {
        const chartBox = document.getElementById('ritmo-exercise-evo-chart');
        if (chartBox) {
          chartBox.innerHTML = '<div class="empty-state" style="padding:20px 10px;">Finalize ao menos um treino com séries concluídas para liberar o gráfico de progressão por exercício.</div>';
        }
      }
    } catch (e) {
      console.error('Erro ao inicializar evolução por exercício:', e);
    }
  }

  function renderRitmoEvolutionExerciseOptions(list) {
    const sel = document.getElementById('ritmo-evo-ex-select');
    if (!sel) return;
    if (!list || !list.length) {
      sel.innerHTML = '<option value="">Nenhum exercício com séries concluídas</option>';
      return;
    }
    sel.innerHTML = list.map(ex =>
      `<option value="${ex.id}" ${Number(ex.id) === Number(selectedEvolutionExerciseId) ? 'selected' : ''}>${escapeHtml(ex.name)} (${ex.sessions_count || 0} sessões • PR ${ex.all_time_max_load || 0}kg)</option>`
    ).join('');
  }

  function filterRitmoEvolutionExercises(query) {
    const q = (query || '').trim().toLowerCase();
    const filtered = !q
      ? performedExercisesList
      : performedExercisesList.filter(ex =>
          (ex.name || '').toLowerCase().includes(q) ||
          (ex.muscle_group || '').toLowerCase().includes(q)
        );
    renderRitmoEvolutionExerciseOptions(filtered);
    if (filtered.length > 0) {
      selectRitmoEvolutionExercise(filtered[0].id);
    }
  }

  async function selectRitmoEvolutionExercise(exerciseId) {
    if (!exerciseId) return;
    selectedEvolutionExerciseId = parseInt(exerciseId, 10);
    const sel = document.getElementById('ritmo-evo-ex-select');
    if (sel && Number(sel.value) !== selectedEvolutionExerciseId) {
      sel.value = String(selectedEvolutionExerciseId);
    }
    await fetchAndRenderExerciseEvolution();
  }

  function setRitmoEvolutionMode(mode) {
    selectedEvolutionMode = mode;
    document.getElementById('btn-evo-mode-load')?.classList.toggle('active', mode === 'max_load');
    document.getElementById('btn-evo-mode-volume')?.classList.toggle('active', mode === 'total_volume');
    document.getElementById('btn-evo-mode-reps')?.classList.toggle('active', mode === 'total_reps');
    fetchAndRenderExerciseEvolution();
  }

  function setRitmoEvolutionPeriod(period) {
    selectedEvolutionPeriod = period;
    document.querySelectorAll('#ritmo-evo-period-group .ritmo-evo-period-btn').forEach(btn => {
      const isAct = btn.getAttribute('data-period') === period;
      btn.className = `btn ${isAct ? 'btn-primary' : 'btn-secondary'} btn-sm ritmo-evo-period-btn`;
    });
    fetchAndRenderExerciseEvolution();
  }

  // RNF01: Downsampling LTTB / Decimação se pontos > 250 para manter renderização < 300ms a 60fps
  function downsampleEvolutionPoints(points, maxPoints = 250) {
    if (!Array.isArray(points) || points.length <= maxPoints) return points;
    const sampled = [points[0]];
    const bucketSize = (points.length - 2) / (maxPoints - 2);
    for (let i = 1; i < maxPoints - 1; i++) {
      const idx = Math.min(points.length - 2, Math.floor(1 + (i - 1) * bucketSize));
      sampled.push(points[idx]);
    }
    sampled.push(points[points.length - 1]);
    return sampled;
  }

  async function fetchAndRenderExerciseEvolution() {
    if (!selectedEvolutionExerciseId) return;
    const cacheKey = `${selectedEvolutionExerciseId}:${selectedEvolutionPeriod}`;
    let payload = exerciseEvolutionCache.get(cacheKey);
    if (!payload) {
      try {
        payload = await apiFetch(`/api/ritmo/exercise-evolution?exercise_id=${selectedEvolutionExerciseId}&period=${selectedEvolutionPeriod}`);
        exerciseEvolutionCache.set(cacheKey, payload);
      } catch (e) {
        console.error('Erro ao buscar evolução do exercício:', e);
        return;
      }
    }
    renderRitmoExerciseEvolutionSvg(payload);
  }

  function renderRitmoExerciseEvolutionSvg(payload) {
    const container = document.getElementById('ritmo-exercise-evo-chart');
    const tooltipEl = document.getElementById('ritmo-exercise-evo-tooltip');
    if (tooltipEl) tooltipEl.style.display = 'none';
    if (!container) return;

    const sum = payload?.summary || {};
    const prLoadEl = document.getElementById('ritmo-evo-pr-load');
    const prVolEl = document.getElementById('ritmo-evo-pr-vol');
    const sessCountEl = document.getElementById('ritmo-evo-sessions-count');
    if (prLoadEl) prLoadEl.innerText = `${sum.pr_max_load || 0} kg`;
    if (prVolEl) prVolEl.innerText = `${sum.pr_max_volume || 0} kg`;
    if (sessCountEl) sessCountEl.innerText = sum.sessions_count || 0;

    const rawPoints = payload?.points || [];
    if (!rawPoints.length) {
      container.innerHTML = '<div class="empty-state" style="padding:20px 10px;">Nenhuma sessão finalizada para este exercício no período filtrado.</div>';
      return;
    }

    const points = downsampleEvolutionPoints(rawPoints, 250);
    const metricKey = selectedEvolutionMode === 'total_volume'
      ? 'total_volume'
      : (selectedEvolutionMode === 'total_reps' ? 'total_reps' : 'max_load');
    const unitLabel = selectedEvolutionMode === 'total_reps' ? 'reps' : 'kg';

    const vals = points.map(p => Number(p[metricKey] || 0));
    let minVal = Math.min(...vals);
    let maxVal = Math.max(...vals);
    if (minVal === maxVal) {
      minVal = Math.max(0, minVal - 5);
      maxVal = maxVal + 5;
    } else {
      const pad = (maxVal - minVal) * 0.15;
      minVal = Math.max(0, Math.floor((minVal - pad) * 10) / 10);
      maxVal = Math.ceil((maxVal + pad) * 10) / 10;
    }

    const range = (maxVal - minVal) || 1;
    const width = 560;
    const height = 190;
    const padL = 44;
    const padR = 24;
    const padT = 24;
    const padB = 30;
    const chartW = width - padL - padR;
    const chartH = height - padT - padB;

    const coords = points.map((pt, idx) => {
      const val = Number(pt[metricKey] || 0);
      const x = points.length === 1 ? padL + chartW / 2 : padL + (idx / (points.length - 1)) * chartW;
      const y = padT + chartH - ((val - minVal) / range) * chartH;
      return {
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        val,
        idx,
        raw: pt
      };
    });

    const pathD = coords.reduce((acc, c, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`, '');
    const fillD = `${pathD} L ${coords[coords.length - 1].x} ${padT + chartH} L ${coords[0].x} ${padT + chartH} Z`;

    const gridLines = [minVal, (minVal + maxVal) / 2, maxVal].map(v => {
      const y = padT + chartH - ((v - minVal) / range) * chartH;
      return `
        <line x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3,3" />
        <text x="${padL - 6}" y="${y + 3}" text-anchor="end" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)">${Math.round(v)}</text>
      `;
    }).join('');

    window._currentRitmoEvoPoints = points;

    const circles = coords.map(c => `
      <g style="cursor:pointer;" onclick="App.showRitmoEvoTooltip(${c.idx})">
        <circle cx="${c.x}" cy="${c.y}" r="5" fill="#38bdf8" stroke="#000000" stroke-width="2" />
        <text x="${c.x}" y="${c.y - 8}" text-anchor="middle" fill="#ffffff" font-size="9.5" font-weight="700" font-family="var(--font-mono)">${c.val}${unitLabel}</text>
      </g>
    `).join('');

    const dateLabels = coords.filter((_, idx) => {
      if (coords.length <= 5) return true;
      return idx === 0 || idx === coords.length - 1 || idx === Math.floor(coords.length / 2);
    }).map(c => `
      <text x="${c.x}" y="${height - 8}" text-anchor="middle" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)">${(c.raw.date || '').slice(5)}</text>
    `).join('');

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; display:block; overflow:visible;">
        <defs>
          <linearGradient id="evoExGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35" />
            <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0" />
          </linearGradient>
        </defs>
        ${gridLines}
        <path d="${fillD}" fill="url(#evoExGrad)" />
        <path d="${pathD}" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
        ${circles}
        ${dateLabels}
      </svg>
    `;
  }

  function showRitmoEvoTooltip(pointIndex) {
    const tooltipEl = document.getElementById('ritmo-exercise-evo-tooltip');
    const pts = window._currentRitmoEvoPoints || [];
    const pt = pts[pointIndex];
    if (!tooltipEl || !pt) return;

    const setsStr = (pt.sets_detail || []).map((s, idx) =>
      `Série ${idx + 1}: <strong>${s.load}kg x ${s.reps}</strong>`
    ).join(' • ');

    tooltipEl.style.display = 'block';
    tooltipEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
        <strong>${formatDateFull(pt.date)} — ${escapeHtml(pt.routine_name || 'Treino')}</strong>
        <span style="font-family:var(--font-mono); color:var(--accent-tasks);">Carga Máx: ${pt.max_load} kg | Volume: ${pt.total_volume} kg</span>
      </div>
      <div style="font-size:0.74rem; color:var(--text-secondary);">${setsStr || `${pt.sets_count} séries concluídas`}</div>
    `;
  }

  return {
    init,
    navigateTo,
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
    toggleDoneColumn,
    loadMoreDoneTasks,
    archiveAllDoneTasks,
    loadArchivedTasks,
    unarchiveTask,
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
    openFinanceImportModal,
    submitFinanceImport,
    openFinanceExportModal,
    confirmFinanceExport,
    openFinanceClearModal,
    confirmFinanceClear,
    searchFinanceClientSide,
    filterFinance,
    loadFinanceData,
    updateTransactionCategory,
    openRecurringRuleModal,
    saveRecurringRule,
    toggleRecurringRuleActive,
    deleteRecurringRule,
    loadFinanceProjection,
    deleteTransaction,
    filterIdeas,
    searchIdeas,
    convertIdeaToTask,
    setIdeaNoteType,
    openIdeaModal,
    saveIdea,
    changeIdeaStage,
    deleteIdea,
    deleteCurrentModalIdea,
    toggleCardChecklistItem,
    addChecklistItemFromInput,
    openSystemModal,
    downloadHotBackup,
    exportData,
    saveServerOrigin,
    testServerConnection,
    openModal,
    closeModals,
    handleFabClick,
    closeFabSpeedDial,
    toggleCardMenu,
    setIdeasSubTab,

    // v1.3 Extensions
    toggleNavMenu,
    loadRitmoData,
    setRitmoTab,
    onRitmoCalendarMonthChange,
    loadRitmoCalendar,
    openRitmoDayDetails,
    updateScheduleStatus,
    scheduleRoutineForDay,
    deleteRitmoSchedule,
    deleteWorkoutFromCalendar,
    openStartWorkoutModal,
    startWorkoutSubmit,
    startWorkoutSubmitFromRoutine,
    toggleWorkoutSet,
    updateSetValues,
    addAdHocWorkoutSet,
    updateWorkoutItemNotes,
    startRitmoRestTimer,
    adjustRitmoRestTimer,
    stopRitmoRestTimer,
    finishActiveWorkout,
    discardActiveWorkout,
    stopActiveWorkout,
    deleteRoutine,
    loadWeightHistory,
    openWeightModal,
    saveWeightSubmit,
    deleteWeightMetric,
    loadEvolutionPhotos,
    openEvolutionPhotoModal,
    previewEvolutionPhoto,
    saveEvolutionPhotoSubmit,
    deleteEvolutionPhoto,
    openRoutineModal,
    saveRoutineSubmit,
    addRoutineExerciseRow,
    openCustomExerciseModal,
    saveCustomExerciseSubmit,
    deleteCustomExercise,
    filterExercises,
    loadSleepData,
    openSleepModal,
    saveSleepSubmit,
    deleteSleepLog,
    openTaskHistoryModal,
    filterTaskHistory,
    installPwa,

    // v1.4.0 Extensions (Dashboard Redesign, Rotinas Diárias & Evolução por Exercício)
    changeFeaturedGoal,
    setRoutinesSubTab,
    loadDailyRoutinesData,
    openDailyRoutineModal,
    addDailyRoutineTaskInputRow,
    updateDailyRoutineTotalDuration,
    saveDailyRoutineSubmit,
    startDailyRoutine,
    openInterruptRoutineModal,
    submitInterruptRoutine,
    resumeDailyRoutine,
    completeDailyRoutine,
    cancelDailyRoutine,
    reactivateDailyRoutine,
    deleteDailyRoutine,
    toggleDailyRoutineTask,
    openRoutineCommentModal,
    submitRoutineComment,
    setRoutineSuspensionType,
    openRoutineSuspensionModal,
    submitRoutineSuspension,
    deleteRoutineSuspension,
    onRoutinesCalendarMonthChange,
    openRoutinesDayDetails,
    setRoutinesCalendarViewMode,
    loadRoutinesCalendar,
    setRoutinesHistoryRange,
    loadRoutinesHistory,
    loadRoutinesSleepSubTab,
    saveSleepSettingsSubmit,
    quickLogSleepCompliance,
    toggleRoutinePomodoro,
    pauseRoutinePomodoro,
    resetRoutinePomodoro,
    loadRitmoExerciseEvolutionInit,
    filterRitmoEvolutionExercises,
    selectRitmoEvolutionExercise,
    setRitmoEvolutionMode,
    setRitmoEvolutionPeriod,
    showRitmoEvoTooltip
  };
})();

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

