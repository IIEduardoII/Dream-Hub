# Dream Hub v1.1.0 - Central Pessoal de Produtividade, Tempo, Finanças e Ideias

Sistema pessoal autônomo Local-First e Personal Cloud Edge para **Gestão de Tarefas & Recorrências**, **Gestão de Tempo (Pomodoro via Timestamp)**, **Gestão Financeira com Gastos e Depósitos Recorrentes** e **Incubadora de Ideias com Conversão em 1 Clique**, projetado para rodar em um smartphone Android residencial via Termux, supervisionado pelo `runit` com `termux-wake-lock`, roteado via Nginx e acessível de forma privada e criptografada pela rede **Tailscale**.

---

## 1. Novidades da Versão 1.1.0

1. **Cockpit Unificado "Meu Dia" (`[RF01]` / `/api/cockpit/today`)**:
   - Consolida na tela inicial: tarefas que vencem hoje / urgentes, minutos e ciclos de foco acumulados no dia, saldo líquido mensal (incluindo gastos e depósitos fixos recorrentes) e ideias recentes prontas para conversão.
2. **Zero-Friction Quick Capture Modal Global (`[RF02]`)**:
   - Botão flutuante (`+` FAB) presente em todas as telas para registrar em 1 a 2 toques (< 3 segundos): **Nova Ideia**, **Novo Gasto / Depósito (com opção Recorrente)** ou **Nova Tarefa (com opção Recorrente)**.
3. **Integração Entre Módulos (Fim dos Silos)**:
   - **Ideia → Tarefa com 1 Clique (`[RF12]` / `RN02` / `POST /api/ideas/<id>/convert`)**: Converte qualquer ideia em tarefa em transação atômica (`BEGIN IMMEDIATE`), vinculando `converted_task_id` e atualizando o status para `convertida`.
   - **Finanças ↔ Tarefas**: Lançamentos financeiros podem ser opcionalmente vinculados a uma tarefa/projeto (`task_id`) e a categorias unificadas (`categories`).
   - **Pomodoro ↔ Tarefas (`[RF05]` / `RN03`)**: Ciclos concluídos incrementam automaticamente `completed_pomodoros` da tarefa ativa.
4. **Gastos e Depósitos Recorrentes Fixos (`[RF10]`)**:
   - Ao cadastrar qualquer despesa ou depósito/receita, basta marcar **`🔁 Gasto ou Depósito Recorrente (Fixo)`** (`mensal`, `semanal` ou `anual`).
   - O sistema materializa automaticamente os lançamentos recorrentes a cada novo mês sem necessidade de redigitação manual, exibindo um painel dedicado de **Gastos & Depósitos Recorrentes (Fixos)** com opção de pausar/cancelar a repetição a qualquer momento.
5. **Recorrência Automática de Tarefas (`[RF07]` / `RN04`)**:
   - Tarefas com recorrência (`diaria`, `semanal`, `mensal`) geram automaticamente a próxima ocorrência (D+1, D+7 ou M+1) assim que são marcadas como concluídas.
6. **Busca Client-Side Instantânea (`[RF13]`)**:
   - Filtro textual em tempo real (`< 50ms`) diretamente em memória nas listas de **Tarefas**, **Finanças** e **Ideias**.
7. **Soberania de Dados: Backup SQLite a Quente (`[RF14]`) & Exportação CSV/JSON (`[RF15]`)**:
   - Endpoint `GET /api/system/backup` e script `scripts/backup.sh` usando a API nativa de backup a quente do SQLite WAL (`.backup`).
   - Exportação instantânea em `.CSV` (compatível com Excel/Sheets) e `.JSON` via `GET /api/system/export`.
8. **Otimizações SQLite WAL & Ergonomia OLED (`#000000`) (`[RNF03]`, `[RNF05]`)**:
   - 6 PRAGMAs ativos em toda conexão (`journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `temp_store=MEMORY`, `cache_size=-8000`, `busy_timeout=5000`).
   - Fundo preto puro (`#000000`) para telas AMOLED, alvos de toque `>= 44x44px` e contagem Pomodoro via delta de timestamp resistente ao bloqueio de tela do Android.

---

## 2. Arquitetura e Portas no Smartphone

| Aplicação | Porta HTTP | Porta HTTPS | Porta API Interna | Banco de Dados | Serviço Runit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ritmo** | `8088` | `8443` | `127.0.0.1:8000` | SQLite (`ritmo.db`) | `ritmo-api`, `ritmo-nginx` |
| **Dream Hub (v1.1)** | `8090` | `8445` | `127.0.0.1:8001` | SQLite WAL (`nexus.db`) | `nexus-api`, `nexus-nginx` |

### Como Executar Testes e Fazer Deploy:
```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py" -v
./scripts/deploy-to-termux.sh
```
