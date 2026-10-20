# Dream Hub v1.2.0 - Central Pessoal de Produtividade, Metas, Anotações, Tempo, Finanças e Ideias

Sistema pessoal autônomo Local-First e Personal Cloud Edge para **Gestão de Tarefas & Recorrências**, **Módulo Transversal de Metas (`🎯`)**, **Modo Anotações & Base de Conhecimento Markdown**, **Anexos e Arquivos Descentralizados**, **Gestão Financeira com Motor de Contas Fixas e Projeção de Fluxo de Caixa (1-3m)**, **Gestão de Tempo (Pomodoro via Timestamp)** e **Incubadora de Ideias**, projetado para rodar em um smartphone Android residencial via Termux, supervisionado pelo `runit` com `termux-wake-lock`, roteado via Nginx e acessível de forma privada e criptografada pela rede **Tailscale**.

---

## 1. Novidades da Versão 1.2.0

1. **Sistema Descentralizado de Anexos e Arquivos (`[RF01]` / `[RNF01]` / `[RN01]`)**:
   - Upload e visualização de arquivos (PDFs, imagens, comprovantes, áudios, códigos, zip até `15MB`) diretamente em **Tarefas**, **Anotações**, **Ideias** e **Transações Financeiras**.
   - Armazenamento físico otimizado no filesystem (`uploads/` com UUIDv4 + extensão sanitizada), mantendo o `nexus.db` leve e rápido, com exclusão física imediata (`os.remove()`) ao remover um anexo ou entidade pai (zero arquivos órfãos).
2. **Módulo Transversal de Metas & Objetivos (`[RF02]` / `[RF03]` / `[RN02]`)**:
   - Criação de metas **Monetárias** (`R$`), **Quantitativas** (ex: `50 pomodoros`, `12 livros`) ou **Qualitativas / Hábito Contínuo** (*"Estudar até aprender"*, sem teto numérico rígido).
   - Progresso dinâmico (`0%` a `100%`) e incremento automático ao concluir tarefas/pomodoros ou lançar receitas/aportes vinculados a uma meta (`goal_id`).
3. **Modo Anotações & Base de Conhecimento Estruturada (`[RF04]` / `[RNF02]`)**:
   - Novo caderno dedicado (`📝 Anotações`) na barra inferior com organização por **Pastas/Cadernos**, **Tags**, fixação no topo (`📌`), busca instantânea e anexos múltiplos.
   - Modo de leitura/edição livre de distrações sobre fundo OLED `#000000` com renderizador Markdown leve em Vanilla JS (títulos, negrito, blocos de código, citações e checklists).
4. **Motor de Regras Recorrentes (`recurring_rules`) & Simulador de Projeção Financeira (`[RF05]` / `[RF06]` / `[RF07]` / `[RN03]`)**:
   - Sub-abas dedicadas em Finanças: **`[ Extrato Mensal ]`**, **`[ Contas Fixas & Recorrências ]`** e **`[ Projeção (1-3m) ]`**.
   - Contas fixas e salários futuros (ex: vencimento dia 25) aparecem imediatamente na aba de Contas Fixas para edição de valor/vencimento, pausa ou exclusão, sem apagar o histórico passado quando alterados.
   - Simulador de Fluxo de Caixa projetado para **30, 60 e 90 dias (`D+30`, `D+60`, `D+90`)** somando saldo atual + receitas fixas - despesas fixas.
5. **Nova Barra de Navegação Inferior & Atalhos Globais**:
   - Barra inferior com as 5 áreas de maior frequência: **`1. Cockpit`**, **`2. Tarefas`**, **`3. Finanças`**, **`4. Anotações`** e **`5. Tempo`**, mais acesso rápido no cabeçalho e no Cockpit para **`🎯 Metas`** e **`💡 Ideias`**.

---

## 2. Arquitetura e Portas no Smartphone

| Aplicação | Porta HTTP | Porta HTTPS | Porta API Interna | Banco de Dados | Serviço Runit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ritmo** | `8088` | `8443` | `127.0.0.1:8000` | SQLite (`ritmo.db`) | `ritmo-api`, `ritmo-nginx` |
| **Dream Hub (v1.2)** | `8090` | `8445` | `127.0.0.1:8001` | SQLite WAL (`nexus.db`) + `uploads/` | `nexus-api`, `nexus-nginx` |

### Como Executar Testes e Fazer Deploy:
```bash
source .venv/bin/activate
python -m unittest discover -s tests -p "test_*.py" -v
./scripts/deploy-to-termux.sh
```
