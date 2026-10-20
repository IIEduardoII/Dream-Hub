# CONTEXT.md - Dream Hub (Sistema Pessoal Unificado)

## 1. Visão Geral e Estado Atual do Projeto

* **Nome do Sistema**: Dream Hub (Gestão Pessoal Integrada)
* **Objetivo**: Sistema autônomo e unificado para Gestão de Tarefas, Gestão de Tempo (Pomodoro/Foco), Gestão Financeira Pessoal e Organização de Ideias (Segundo Cérebro).
* **Ambiente de Hospedagem**: Smartphone Android via Termux, Nginx e Python Gunicorn/Flask/SQLite.
* **Acesso**: Rede privada Tailscale (`100.64.0.0/10`), restrito com Nginx (`allow 127.0.0.1; allow 100.64.0.0/10; deny all;`).
* **Portas Alocadas e Operacionais**:
  * Frontend & Proxy HTTP: `http://<TAILSCALE_IP>:8090`
  * Frontend & Proxy HTTPS: `https://<TAILSCALE_IP>:8445`
  * Backend API Interna: `127.0.0.1:8001` (Gunicorn/Flask)
  * Banco de Dados: SQLite WAL em `~/nexus-termux/nexus.db`

---

## 2. Arquitetura Técnica em Produção

```
                             [ Cliente: Celular / PC via Tailscale ]
                                                │
                                    ┌───────────┴───────────┐
                                    ▼                       ▼
                              HTTP :8090              HTTPS :8445
                                    │                       │
                                    └───────────┬───────────┘
                                                ▼
                                    [ Nginx (Worker no Termux) ]
                                                │
                          ┌─────────────────────┴─────────────────────┐
                          ▼                                           ▼
                 Arquivos Estáticos PWA                     Proxy Reverso `/api/`
                 (HTML5, CSS3, JS Vanilla)                            │
                                                                      ▼
                                                          [ Gunicorn / Flask API ]
                                                               (127.0.0.1:8001)
                                                                      │
                                                                      ▼
                                                             [ SQLite com WAL ]
                                                            (`nexus_database.db`)
```

---

## 3. Grafo de Tarefas e Tracer-Bullets

- [x] **Etapa 0: Descoberta e Engenharia Preliminar**
  - [x] Leitura de requisitos e análise de infraestrutura do smartphone servidor via Termux.
  - [x] Alinhamento via perguntas com o usuário sobre convivência de portas e stack.
  - [x] Criação de `GLOSSARY.md`, `DESIGN.md` e `CONTEXT.md`.
- [x] **Etapa 1: Backend de Dados e APIs RESTful com TDD**
  - [x] Esquema SQLite com tabelas relacionais (`tasks`, `time_sessions`, `transactions`, `ideas`), índices e modo WAL.
  - [x] API REST para Tarefas (CRUD, filtros por status/prioridade, contadores de pomodoro, exclusão).
  - [x] API REST para Tempo/Pomodoro (Iniciar/Finalizar sessão, estatísticas diárias, tempo por tarefa).
  - [x] API REST para Finanças (Lançamentos de receita/despesa, cálculo de saldo, agregação mensal).
  - [x] API REST para Ideias (CRUD, tags, estágios de maturação, busca por texto).
  - [x] Suíte de testes unitários automatizados cobrindo cada endpoint e invariantes de dados (7 testes passando).
- [x] **Etapa 2: Frontend PWA Responsivo e Ergonomia Mobile**
  - [x] Shell da aplicação com Bottom Nav Bar e tema Dark OLED nativo.
  - [x] Módulo Tarefas: Quadro Kanban com drag-and-drop / toque e modo Lista com filtros rápidos e botão de exclusão.
  - [x] Módulo Tempo: Cronômetro Pomodoro interativo com presets rápidos (15m, 25m, 45m, 50m, 60m), ajuste fino e sincronização automática da duração da tarefa.
  - [x] Módulo Finanças: Dashboard com saldo em destaque, resumo de receitas/despesas e modal de lançamento rápido.
  - [x] Módulo Ideias: Quadro de cartões por estágio e editor com prévia Markdown e busca dinâmica.
  - [x] Implementação rigorosa da Matriz dos 5 Estados de UI em todos os módulos.
- [x] **Etapa 3: Empacotamento, Scripts de Deploy e Instalação no Termux**
  - [x] Configuração do Nginx (`nginx-nexus.conf`) e scripts de inicialização supervisionados via `runit` (`nexus-api` e `nexus-nginx`).
  - [x] Script de deploy automatizado via SSH (`scripts/deploy-to-termux.sh`).
  - [x] Testes de integração end-to-end e verificação de saúde da aplicação em produção no smartphone via Tailscale.
