# Dream Hub — Central Pessoal de Produtividade, Tempo, Finanças e Ideias

Plataforma unificada de produtividade e gestão pessoal baseada na filosofia **Local-First** e **Personal Cloud Edge**, projetada para operar diretamente em um smartphone Android via **Termux** (Nginx + Gunicorn + Flask + SQLite WAL) com acesso privado via **Tailscale**.

## Estrutura de Versões no Repositório

* **[`1.1/`](./1.1)** *(Versão Atual — v1.1.0)*:
  * **Cockpit Unificado ("Meu Dia")**: Visão consolidada de tarefas que vencem hoje, tempo focado, saldo líquido do mês e ideias recentes.
  * **Captura Rápida Global (Zero-Friction Quick Capture)**: Botão flutuante (`+`) em todas as abas para registrar Ideia, Gasto/Depósito ou Tarefa em 2 toques.
  * **Gastos e Depósitos Recorrentes Fixos**: Renovação automática mensal sem necessidade de recadastrar contas ou depósitos todo mês.
  * **Recorrência Automática de Tarefas**: Tarefas diárias, semanais ou mensais geram automaticamente o próximo ciclo ao serem concluídas.
  * **Integração Entre Módulos**: Conversão atômica de Ideia em Tarefa com 1 clique (`⚡ Virar Tarefa`) e vínculo de custos financeiros a tarefas.
  * **Soberania de Dados**: Backup SQLite a quente (`.db`) e exportação em planilhas `.CSV` e `.JSON`.
  * **Ergonomia OLED (`#000000`) & Pomodoro por Timestamp**: Interface preta pura para telas AMOLED e cronômetro imune ao desligamento de tela do Android.
* **[`1.0/`](./1.0)** *(Versão Inicial — v1.0.0)*:
  * Estrutura fundacional com Quadro Kanban de Tarefas, Cronômetro Pomodoro com Web Audio API, Controle Financeiro Mensal e Segundo Cérebro de Ideias.
