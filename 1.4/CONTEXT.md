# CONTEXT.md - Dream Hub v1.4.0 (Sistema Pessoal Unificado)

## 1. Visão Geral e Estado Atual do Projeto

* **Nome do Sistema**: Dream Hub
* **Versão Atual**: `1.4.0`
* **Objetivo**: Plataforma unificada Local-First e Personal Cloud Edge (Custo de Infraestrutura R$ 0,00, Pure OLED Dark `#000000`, Limpeza Visual Extrema sem emojis) para:
  * **Dashboard Central Redesenhado**: 3 Widgets Prioritários em destaque no topo (`Widget Finanças`, `Widget Rotina do Dia` e `Widget Meta em Destaque` com seletor rápido inline quando há >= 2 metas), seguidos dos 4 KPIs superiores e seções executivas.
  * **Modo Rotinas Diárias (`#view-routines`)**: Módulo completo e isolado (`daily_routines`, `daily_routine_tasks`, `daily_routine_logs`, `daily_routine_interruptions`, `daily_routine_comments`, `daily_routine_suspensions`) com transição automática à meia-noite (`00:00`) para `em_andamento` e notificação push imediata (`notified_at`), botão `Interromper` com pausa automática de cronômetro via Web Worker (`pomodoro-worker.js`) e justificativa obrigatória (`reason`), retomada no mesmo dia (`Retomar`), comentários cronológicos, distinção semântica entre Cancelamento Manual Imediato (`status = 'cancelada'`, card atenuado WCAG AA >= 4.5:1) e Suspensão Temporária Agendada (`date_range` ou `days_of_week`), Calendário Mensal/Semanal, Histórico com correlação de sono e Monitoramento de Sono com horários planejados (`user_settings`) e 4 estados de conformidade (`no_horario`, `nao_conseguiu_dormir`, `dormiu_menos`, `dormiu_mais`).
  * **Módulo Ritmo Unificado com Evolução por Exercício**: Treinos Ativos com `+ Série` ad-hoc no histórico e Comentários por exercício, Cronômetro de Descanso Flutuante resiliente, Calendário com ação rápida de `Concluído`/`Stop`, e **Painel de Evolução de Cargas e Volume por Exercício** (Gráfico SVG nativo interativo `< 300ms` com alternância entre `Carga Máxima (kg)` `MAX(load)`, `Volume Total (kg x reps)` `SUM(load * reps)` e `Repetições Totais`, filtros temporais `1m`/`3m`/`6m`/`1y`/`all` e filtro estrito de sessões finalizadas `RN05`).
  * **Gestão de Tarefas**: Kanban, Lista, Recorrências, Status `Stop` e Histórico de Execuções com busca por dia.
  * **Metas Transversais**: Barra de progresso, percentagem (`0%`-`100%`) e seleção de meta em destaque no Dashboard.
  * **Base de Conhecimento / Modo Anotações e Ideias**: Texto Livre, Markdown, Anexos e Modo Checklist Interativo.
  * **Gestão Financeira**: Extrato, Importação/Exportação CSV inteligente (`Educação`, `Saúde`, `Lazer` e `Outros`), Motor de Contas Fixas Recorrentes, Projeção 30/60/90 dias e Remoção Total Segura.
* **Ambiente de Produção**: Smartphone Android (Redmi A3) via Termux + Runit + Tailscale, Nginx (`client_max_body_size 15m`), Gunicorn/Flask e SQLite 3 (Modo WAL com 6 PRAGMAs obrigatórios) + diretório `uploads/`.
* **Portas Alocadas e Operacionais**:
  * Frontend & Proxy HTTP: `8090` (`http://100.107.212.104:8090`)
  * Frontend & Proxy HTTPS: `8445` (`https://dreamapk.duckdns.org:8445` / `https://100.107.212.104:8445`)
  * Backend API Interna: `127.0.0.1:8001` (Gunicorn/Flask)
  * Banco de Dados: SQLite WAL em `~/nexus-termux/nexus.db`
  * Armazenamento Físico de Anexos: `~/nexus-termux/uploads/`
  * Sincronização em Nuvem (Google Drive via `rclone`): `gdrive:Dream_Hub` e `gdrive:DreamHub_Backups`

---

## 2. Grafo de Evolução e Entregas Concluídas (v1.0 -> v1.1 -> v1.2 -> v1.3.0 -> v1.3.1 -> v1.3.2 -> v1.4.0)

- [x] **v1.0.0**: Arquitetura base Local-First no Termux (Flask + SQLite WAL + Nginx + Runit) acessível via Tailscale.
- [x] **v1.1.0**: Cockpit "Meu Dia", Categorias Unificadas, Conversão Atômica Ideia -> Tarefa, Recorrência de Tarefas, Backup SQLite a quente e Exportação CSV/JSON.
- [x] **v1.2.0**: Anexos Descentralizados físicos (`uploads/`), Metas Transversais (`goals`), Modo Anotações (`notes`), Motor de Contas Fixas (`recurring_rules`) e Simulador de Projeção Financeira (`GET /api/finance/projection`).
- [x] **v1.3.0**: Unificação Total do Módulo Ritmo (`ritmo.sqlite3` -> `nexus.db`), HTTPS Let's Encrypt DNS-01 (`DuckDNS`), PWA `WebAPK` e Capacitor Android APK, e refinamento de CSV Financeiro.
- [x] **v1.3.1**: Modo Checklist em Ideias/Rascunhos (`note_type = 'checklist'`), FAB Contextual Inteligente e limpeza visual com kebab menu (`⋮`).
- [x] **v1.3.2**: Status `Stop` e `task_history` em Tarefas, `+ Série` ad-hoc e Comentários em Treinos Ativos, Cronômetro de Descanso Flutuante resiliente e restauração clean do Dashboard.
- [x] **v1.4.0 - Modo Rotinas Diárias, Redesign do Dashboard Central & Evolução por Exercício no Módulo Ritmo**:
  - [x] **Schema SQLite v1.4.0 (Zero Colisão com `routines` do Ritmo)**: Novas tabelas `daily_routines`, `daily_routine_tasks`, `daily_routine_logs`, `daily_routine_interruptions`, `daily_routine_comments`, `daily_routine_suspensions` e `user_settings`, além de migração idempotente de `sleep_logs` (`planned_bedtime`, `planned_wake_time`, `compliance_status`).
  - [x] **Virada Diária Automática às 00:00 (`RF02`, `US02`, `Decisão 02`)**: Thread daemon em background + hook idempotente que transiciona rotinas ativas automaticamente para `em_andamento` à meia-noite (`00:00`) e registra `notified_at` para disparo de Web Notification imediata no frontend.
  - [x] **Fluxo de Interrupção, Retomada e Comentários (`RF03`, `RF04`, `RNF03`, `Decisão 04`)**: Web Worker dedicado (`frontend/js/pomodoro-worker.js`) com pausa imediata do cronômetro ao acionar `Interromper`, validação estrita de justificativa obrigatória (`HTTP 400` se vazio), retomada no mesmo dia (`Retomar`) e comentários cronológicos.
  - [x] **Cancelamento Manual vs. Suspensão Temporária Agendada (`RF05`, `RF06`, `RN01`, `RN02`, `RNF04`, `US01`)**: Cancelamento manual imediato (`status = 'cancelada'`) com estilo visual atenuado `.routine-card-cancelled` (contraste WCAG AA >= 4.5:1) e bloqueio de início/suspensão até reativação; Suspensão temporária agendada (`date_range` ou `days_of_week`) com retorno automático ao ciclo normal após `end_date`.
  - [x] **Monitoramento de Sono & Sub-abas de Rotinas (`RF07` a `RF10`)**: 4 sub-abas (`Rotina de Hoje`, `Calendário` mensal/semanal, `Histórico` com correlação de sono e `Monitoramento de Sono` com horários planejados e 4 estados de conformidade).
  - [x] **Redesign do Dashboard Central (`RF11`, `RF12`, `RN04`)**: 3 Widgets Prioritários no topo (`Widget Finanças`, `Widget Rotina do Dia` e `Widget Meta em Destaque` com seletor rápido `PUT /api/settings/featured-goal`).
  - [x] **Evolução por Exercício no Módulo Ritmo (`RF13`, `RF14`, `RN05`, `RNF01`, `US03`, `Decisão 03`)**: Endpoints `/api/ritmo/performed-exercises` e `/api/ritmo/exercise-evolution` filtrando estritamente treinos finalizados (`w.finished_at IS NOT NULL`) e séries concluídas (`ws.done = 1`), com gráfico SVG nativo interativo (`Carga Máxima (kg)`, `Volume Total (kg x reps)` e `Repetições Totais`), cache em memória e downsampling automático.
- [x] **v1.4.1 - Ajustes Cirúrgicos no Modo Rotinas e Menu de Navegação**:
  - [x] **Substituição de Pomodoros por Horas e Minutos por Tarefa**: Configuração explícita de `Horas (h)` e `Minutos (m)` por tarefa no modal de rotinas (`daily_routine_tasks.duration_minutes`, `elapsed_seconds`), cálculo dinâmico da Duração Total Planejada (`daily_routines.total_planned_minutes`), painel de execução limpo sem menções a pomodoro (`Controle de Execução & Rotina Ativa`) e exibição de tempos no Dashboard e no Histórico.
  - [x] **Remoção da Aba Obsoleta Sono do Menu (⋮)**: Remoção do botão isolado "Sono" no dropdown de 3 pontinhos, com redirecionamento transparente de acessos residuais para a sub-aba integrada de Monitoramento de Sono dentro de Rotinas (`App.navigateTo('routines')` + `setRoutinesSubTab('sono')`), preservando intacta a ferramenta global `Foco / Pomodoro`.
