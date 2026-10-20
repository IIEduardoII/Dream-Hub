# GLOSSARY.md & Registros de Decisões Arquiteturais (ADRs) - Nexus

## 1. Linguagem Ubíqua e Entidades do Domínio

### 1.1 Módulo de Tarefas (Task Management)
* **Task (Tarefa)**: Unidade de trabalho acionável com ciclo de vida definido.
  * `id`: Identificador único (INTEGER PRIMARY KEY autoincrement).
  * `title`: Nome sucinto e imperativo da ação (TEXT, não nulo).
  * `description`: Detalhamento e critérios de conclusão (TEXT).
  * `status`: Estado atual no fluxo Kanban (`todo`, `in_progress`, `done`, `archived`).
  * `priority`: Nível de urgência/impacto (`low`, `medium`, `high`, `urgent`).
  * `due_date`: Data limite de entrega no formato ISO `YYYY-MM-DD`.
  * `estimated_pomodoros`: Estimativa de blocos de foco previstos (INTEGER).
  * `completed_pomodoros`: Blocos de foco efetivamente executados (INTEGER).
  * `pomodoro_duration_minutes`: Duração personalizada do bloco de foco para esta tarefa em minutos (INTEGER, padrão: 25).
  * `category`: Agrupamento temático ou projeto (ex: "Trabalho", "Pessoal", "Estudos").

### 1.2 Módulo de Gestão de Tempo (Time & Pomodoro)
* **TimeBlock / PomodoroSession (Sessão de Foco)**: Intervalo cronometrado dedicado a uma tarefa ou estudo.
  * `id`: Identificador único.
  * `task_id`: Associação opcional a uma Tarefa (FOREIGN KEY).
  * `session_type`: Natureza do bloco (`focus`, `short_break`, `long_break`).
  * `duration_minutes`: Duração planejada (padrão: 25min foco, 5min pausa curta, 15min pausa longa).
  * `started_at`: Timestamp de início (ISO 8601).
  * `ended_at`: Timestamp de finalização (ISO 8601).
  * `completed`: Booleano indicando se o ciclo foi concluído sem interrupção.

### 1.3 Módulo de Gestão Financeira (Financial Tracking)
* **Transaction (Transação Financeira)**: Movimentação de recursos (receita ou despesa).
  * `id`: Identificador único.
  * `description`: Descrição clara da operação (TEXT).
  * `amount_cents`: Valor monetário armazenado em centavos (INTEGER, ex: R$ 50,25 = 5025) para prevenir erros de ponto flutuante.
  * `type`: Tipo da movimentação (`income` para receitas, `expense` para despesas).
  * `category`: Categoria funcional (Alimentação, Moradia, Transporte, Lazer, Saúde, Salário, Investimentos, Outros).
  * `account`: Conta de origem/destino (`Carteira`, `Conta Corrente`, `Cartão de Crédito`, `Reserva`).
  * `date`: Data de competência da transação (`YYYY-MM-DD`).
  * `is_settled`: Booleano (pago/recebido ou pendente).

### 1.4 Módulo de Ideias e Notas (Second Brain / Knowledge)
* **IdeaNote (Nota / Ideia)**: Registro de insights, planos, projetos embrionários ou referências.
  * `id`: Identificador único.
  * `title`: Título representativo da ideia.
  * `content`: Conteúdo textual com suporte a formatação Markdown.
  * `stage`: Maturação da ideia (`raw` / Rascunho, `evaluating` / Em Análise, `in_action` / Em Execução, `archived` / Arquivado).
  * `tags`: Lista de etiquetas para busca facetada (TEXT com valores separados por vírgula).
  * `created_at` / `updated_at`: Timestamps de auditoria.

---

## 2. Architecture Decision Records (ADRs)

### ADR 001: Arquitetura de Execução no Dispositivo (Termux / Android Server)
* **Contexto**: O sistema será hospedado 24/7 no smartphone Android via Termux, com restrições de bateria, memória RAM e armazenamento flash. Já existe outro serviço em execução (`Ritmo`).
* **Decisão**: Utilizar backend Python enxuto (FastAPI ou Flask nativo com SQLite em modo WAL) + Frontend SPA/PWA estático servido pelo Nginx.
* **Consequência**: Consumo de RAM inferior a 45MB, zero latência, inicialização em < 1 segundo, sem necessidade de daemons pesados como PostgreSQL ou MySQL.

### ADR 002: Alocação de Portas e Isolamento de Rede
* **Contexto**: O sistema Ritmo já ocupa as portas 8088 (HTTP), 8443 (HTTPS) e 8000 (Gunicorn).
* **Decisão**: 
  * Nexus HTTP: `8090`
  * Nexus HTTPS: `8445` (ou HTTP direto via Tailscale na porta 8090)
  * Nexus Backend API: `127.0.0.1:8001`
  * Diretório no Termux: `~/nexus-termux`
  * Restrição de segurança: `allow 127.0.0.1; allow 100.64.0.0/10; deny all;`
* **Consequência**: Nenhuma interferência operacional no Ritmo. Ambos convivem de forma independente no supervisor `runit`.

### ADR 003: Armazenamento em SQLite com WAL (Write-Ahead Logging)
* **Contexto**: Acesso simultâneo de leitura pelo painel e escrita de timers/transações sem bloqueio de banco.
* **Decisão**: Configurar SQLite com `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA foreign_keys=ON;`.
* **Consequência**: Concorrência de leitura não bloqueante, integridade garantida mesmo se o Termux for interrompido pelo SO Android.

### ADR 004: Interface PWA Responsiva Mobile-First Sem Build Step no Celular
* **Contexto**: Compilar bundles pesados de Node.js consome muita CPU no smartphone.
* **Decisão**: Frontend desenvolvido em HTML5 moderno, CSS com variáveis semânticas e JavaScript ES Modules nativo no navegador.
* **Consequência**: Carga instantânea, código-fonte 100% inspecionável e editável diretamente pelo Nginx sem necessidade de `npm run build` na máquina hospedeira.
