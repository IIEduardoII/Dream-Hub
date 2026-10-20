# CONTEXT.md - Dream Hub v1.1.0 (Sistema Pessoal Unificado)

## 1. Visão Geral e Estado Atual do Projeto

* **Nome do Sistema**: Dream Hub
* **Versão Atual**: `1.1.0`
* **Objetivo**: Plataforma unificada Local-First e Personal Cloud Edge para Gestão de Tempo (Pomodoro via timestamp), Gestão de Atividades (Tarefas e Recorrências), Gestão Financeira (Receitas/Depósitos, Despesas e Lançamentos Fixos Recorrentes) e Incubadora de Ideias (Brain Dump com conversão atômica em tarefas).
* **Ambiente de Hospedagem**: Smartphone Android via Termux, Nginx, Gunicorn/Flask e SQLite 3 (Modo WAL com 6 PRAGMAs de concorrência).
* **Portas Alocadas e Operacionais**:
  * Frontend & Proxy HTTP: `8090`
  * Frontend & Proxy HTTPS: `8445`
  * Backend API Interna: `127.0.0.1:8001` (Gunicorn/Flask)
  * Banco de Dados: SQLite WAL em `~/nexus-termux/nexus.db`

---

## 2. Grafo de Tarefas Concluídas (v1.0 -> v1.1)

- [x] **Fase 1 (v1.1): Unificação Relacional, Categorias e 6 PRAGMAs SQLite WAL**
  - [x] Migração idempotente *Expand-and-Contract* preservando 100% dos dados existentes em produção.
  - [x] Tabela `categories` unificada e chaves estrangeiras em `tasks`, `transactions`, `time_sessions` e `ideas`.
- [x] **Fase 2 (v1.1): Cockpit "Meu Dia", Recorrências e Integração Anti-Silo**
  - [x] Endpoint `GET /api/cockpit/today` e `/api/overview`.
  - [x] Conversão atômica (`BEGIN IMMEDIATE`) de Ideia em Tarefa (`POST /api/ideas/<id>/convert`).
  - [x] Recorrência automática de tarefas (`diaria`, `semanal`, `mensal`) ao concluir item (`PATCH /api/tasks/<id>/status` e `PUT /api/tasks/<id>`).
  - [x] Gastos e Depósitos Recorrentes Fixos (`is_recurring`, `recurrence`) com materialização automática mensal idempotente.
  - [x] Backup SQLite a quente (`GET /api/system/backup` + `scripts/backup.sh`) e exportação tabular CSV/JSON (`GET /api/system/export`).
- [x] **Fase 3, 4 e 5 (v1.1): Interface OLED `#000000`, Captura Rápida Global (FAB) e Pomodoro Timestamp**
  - [x] Fundo OLED `#000000` e alvos de toque `>= 44x44px`.
  - [x] Botão flutuante global (`+` FAB) com modal de Captura Rápida em 2 toques.
  - [x] Contagem Pomodoro baseada em timestamp real (`endTime`) resistente à suspensão de tela no Android.
  - [x] Busca e filtros instantâneos Client-Side (`< 50ms`) em Tarefas, Finanças e Ideias.
  - [x] Suíte de testes automatizados TDD com 10 testes de integração cobrindo todas as funcionalidades v1.1.
