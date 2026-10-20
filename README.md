# Dream Hub — Central Pessoal de Produtividade, Metas, Anotações, Tempo, Finanças e Ideias

Plataforma unificada de produtividade e gestão pessoal baseada na filosofia **Local-First** e **Personal Cloud Edge**, projetada para operar diretamente em um smartphone Android via **Termux** (Nginx + Gunicorn + Flask + SQLite WAL) com acesso privado via **Tailscale**.

## Estrutura de Versões no Repositório

* **[`1.2/`](./1.2)** *(Versão Atual — v1.2.0)*:
  * **Sistema Descentralizado de Anexos e Arquivos (`uploads/`)**: Upload e visualização de arquivos até 15 MB (PDFs, imagens, comprovantes, códigos, documentos) diretamente em **Tarefas**, **Anotações**, **Ideias** e **Transações Financeiras**, com limpeza física automática no disco ao excluir registros.
  * **Módulo Transversal de Metas & Objetivos (`🎯`)**: Suporte a metas **Monetárias (`R$`)**, **Quantitativas** (ex: 50 pomodoros, 12 livros) e **Qualitativas / Hábito Contínuo** (*"Estudar até aprender"*), com incremento automático ao concluir tarefas/pomodoros ou lançar receitas vinculadas.
  * **Modo Anotações & Base de Conhecimento (`📝`)**: Caderno dedicado com organização por pastas/cadernos, tags, fixação no topo, anexos múltiplos e modo de leitura/edição livre de distrações em tela preta OLED `#000000` com suporte a Markdown.
  * **Motor de Regras Recorrentes (`recurring_rules`) & Projeção de Fluxo de Caixa (1-3m)**: Sub-abas em Finanças para **Extrato Mensal**, **Contas Fixas & Recorrências** (exibindo imediatamente contas futuras como dia 25 para edição, pausa ou exclusão sem afetar o histórico passado) e **Projeção Financeira (30, 60 e 90 dias)**.
* **[`1.1/`](./1.1)** *(Versão v1.1.0)*:
  * **Cockpit Unificado ("Meu Dia")**: Visão consolidada de tarefas que vencem hoje, tempo focado, saldo líquido do mês e ideias recentes.
  * **Captura Rápida Global (Zero-Friction Quick Capture)**: Botão flutuante (`+`) em todas as abas para registrar Ideia, Gasto/Depósito ou Tarefa em 2 toques.
  * **Recorrência Automática de Tarefas & Conversão Ideia → Tarefa**: Conversão atômica em 1 clique (`⚡ Virar Tarefa`), backup SQLite a quente (`.db`), exportação `.CSV`/`.JSON`, fundo OLED (`#000000`) e Pomodoro por timestamp.
* **[`1.0/`](./1.0)** *(Versão Inicial — v1.0.0)*:
  * Estrutura fundacional com Quadro Kanban de Tarefas, Cronômetro Pomodoro com Web Audio API, Controle Financeiro Mensal e Segundo Cérebro de Ideias.
