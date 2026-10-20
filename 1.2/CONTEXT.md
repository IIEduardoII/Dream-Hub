# CONTEXT.md - Dream Hub v1.2.0 (Sistema Pessoal Unificado)

## 1. Visão Geral e Estado Atual do Projeto

* **Nome do Sistema**: Dream Hub
* **Versão Atual**: `1.2.0`
* **Objetivo**: Plataforma unificada Local-First e Personal Cloud Edge para Gestão de Tarefas, Metas Transversais, Base de Conhecimento / Modo Anotações (Markdown + Anexos), Gestão Financeira (Extrato, Motor de Contas Fixas Recorrentes e Projeção 30/60/90 dias), Gestão de Tempo (Pomodoro via timestamp) e Incubadora de Ideias.
* **Ambiente de Hospedagem**: Smartphone Android via Termux, Nginx (`client_max_body_size 15m`), Gunicorn/Flask e SQLite 3 (Modo WAL com 6 PRAGMAs de concorrência) + diretório `uploads/`.
* **Portas Alocadas e Operacionais**:
  * Frontend & Proxy HTTP: `8090`
  * Frontend & Proxy HTTPS: `8445`
  * Backend API Interna: `127.0.0.1:8001` (Gunicorn/Flask)
  * Banco de Dados: SQLite WAL em `~/nexus-termux/nexus.db`
  * Armazenamento Físico de Anexos: `~/nexus-termux/uploads/`

---

## 2. Grafo de Tarefas Concluídas (v1.0 -> v1.1 -> v1.2)

- [x] **v1.1.0**: Cockpit "Meu Dia", Quick Capture Modal Global (`+` FAB), Categorias Unificadas, Conversão Atômica Ideia -> Tarefa, Recorrência de Tarefas, Backup SQLite a quente e Exportação CSV/JSON.
- [x] **v1.2.0 - Fase 1: Migração Relacional Expand-and-Contract e Anexos Descentralizados**
  - [x] Tabelas `attachments`, `goals`, `notes` e `recurring_rules` + migração automática de transações `is_recurring=1` para `recurring_rules`.
  - [x] Colunas `goal_id` em `tasks` e `transactions`, e `recurring_rule_id` em `transactions`.
  - [x] Upload e gestão de arquivos físicos em `uploads/` com remoção física imediata (`os.remove`) ao excluir anexo ou registro pai (`RN01`).
- [x] **v1.2.0 - Fase 2: Metas Transversais (`goals`) & Modo Anotações (`notes`)**
  - [x] Suporte a metas monetárias, quantitativas e qualitativas (`target_value = NULL`, *"Estudar até aprender"*).
  - [x] Auto-incremento de metas ao concluir tarefas/pomodoros ou registrar transações vinculadas.
  - [x] Caderno de Anotações com pastas, tags, fixação e leitor/editor Markdown OLED livre de distrações.
- [x] **v1.2.0 - Fase 3: Motor de Contas Fixas (`recurring_rules`) & Simulador de Projeção Financeira**
  - [x] Visibilidade imediata de contas fixas futuras na aba `Contas Fixas & Recorrências`, com edição, pausa/retomada e exclusão sem afetar o histórico passado (`RN03`).
  - [x] Endpoint `GET /api/finance/projection?months=3` e aba `Projeção (1-3m)` para simulação de fluxo de caixa em 30, 60 e 90 dias.
  - [x] Suíte de testes automatizados TDD com 13 testes passando (`OK`).
