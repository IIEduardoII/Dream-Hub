# DESIGN.md - Sistema Nexus (Design System & UI Guidelines)

## 1. Direção Estética (Anti-AI-Slop)

O **Nexus** adota uma estética funcional, utilitária e focada na produtividade ("industrial/dashboard minimalista"), inspirada em interfaces de alta densidade informativa e excelente ergonomia móvel.

* **Anti-Padrões Proibidos**: Gradientes genéricos roxos e azuis saturados, cartões flutuantes desnecessários com sombras borradas sem função, ícones decorativos sem significado prático, tipografia com baixo contraste.
* **Prioridade Ergonômica**: Mobile-first com barra de navegação inferior (*Bottom Navigation Bar*) para uso com uma só mão no smartphone, alvos de toque mínimos de 44x44px e tema escuro calibrado para telas OLED (máxima economia de bateria no aparelho hospedeiro).

---

## 2. Tokens de Design

### 2.1 Paleta de Cores (OLED Dark Mode Primário)
```css
:root {
  /* Superfícies e Fundos */
  --bg-canvas: #090b10;       /* Preto profundo para economia OLED */
  --bg-surface: #12161f;      /* Painéis e cartões */
  --bg-surface-elevated: #1a202c; /* Modais, drawers e tooltips */
  --bg-surface-active: #242c3d;   /* Estados hover / active */

  /* Linhas e Divisões */
  --border-subtle: #232b3b;
  --border-focus: #3b82f6;

  /* Tipografia e Contraste (WCAG AAA) */
  --text-primary: #f8fafc;    /* Alto contraste (títulos e dados) */
  --text-secondary: #94a3b8;  /* Subtítulos e labels */
  --text-muted: #64748b;      /* Metadados e datas */

  /* Acentos Semânticos Funcionais */
  --accent-tasks: #38bdf8;    /* Ciano para Tarefas */
  --accent-time: #fbbf24;     /* Âmbar/Dourado para Foco & Pomodoro */
  --accent-income: #34d399;   /* Esmeralda para Receitas & Conclusões */
  --accent-expense: #f87171;  /* Coral/Rubi para Despesas & Urgências */
  --accent-ideas: #a78bfa;    /* Púrpura suave para Ideias & Notas */
}
```

### 2.2 Tipografia
* **Família Principal**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` (legibilidade nativa ultra rápida sem overhead de download de fontes).
* **Família Numérica e Código (Moeda, Cronômetro, Metadados)**: `"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace` (largura fixa evita que os números saltem ao cronometrar ou somar valores financeiros).
* **Escala Modular**:
  * `xs`: 0.75rem (12px) - badges e timestamps
  * `sm`: 0.875rem (14px) - labels e metadados
  * `base`: 1rem (16px) - corpo de texto padrão
  * `lg`: 1.125rem (18px) - títulos de seções
  * `xl`: 1.5rem (24px) - saldos e subtítulos destacados
  * `2xl`: 2.25rem (36px) - display numérico do timer Pomodoro

### 2.3 Espaçamento e Grid
* Escala base modular de 4px: `4px`, `8px`, `12px`, `16px`, `24px`, `32px`.
* Cantos arredondados contidos: `radius-sm: 6px`, `radius-md: 10px`, `radius-lg: 14px`.

---

## 3. Matriz Obrigatória dos 5 Estados de Interface

Cada um dos 4 módulos (Tarefas, Tempo, Finanças, Ideias) implementa explicitamente:

| Módulo | 1. Carregamento (Loading) | 2. Vazio (Empty State) | 3. Erro (Error State) | 4. Parcial / Borda | 5. Populado (Ideal) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tarefas** | Skeletons com largura correspondente aos cards | "Nenhuma tarefa cadastrada. Toque em '+' para criar sua primeira tarefa." | Alerta de erro na sincronização com botão 'Tentar novamente' | Tarefas com textos longos truncados com tooltip + 1 tarefa isolada | Colunas Kanban / Lista clara com prioridades coloridas e badges de prazo |
| **Tempo** | Indicador pulsante discreto de estado | "Nenhum bloco de foco hoje. Escolha uma tarefa e inicie seu primeiro Pomodoro." | Falha ao registrar sessão: preserva contador local e oferece retry manual | Timer em pausa ou com sessão superior a 90 minutos | Cronômetro proeminente, indicador de ciclo atual (ex: 2 de 4) e gráfico diário |
| **Finanças** | Skeleton de saldo e histórico | "Sem movimentações este mês. Registre uma receita ou despesa." | Preserva formulário preenchido e exibe causa da rejeição | Transações de alto valor (ex: R$ 999.999,99) sem quebrar o container | Saldo líquido no topo com resumo Receitas (+) vs Despesas (-) e extrato diário |
| **Ideias** | Grid com cartões em skeleton | "Seu segundo cérebro está vazio. Capture uma ideia rápida ou anotação." | Notificação não-bloqueante mantendo o editor de Markdown intacto | Nota com apenas 1 palavra vs texto com milhares de palavras | Grid responsivo de cards com tags coloridas e prévia de formatação |

---

## 4. Requisitos de Acessibilidade e Interação Móvel
* **Navegação por Teclado**: Todo botão, campo de entrada e cartão interativo possui foco visível (`outline: 2px solid var(--border-focus)`).
* **Feedback Tátil**: Estados `:active` com ligeira redução de escala (`transform: scale(0.98)`) para resposta tátil instantânea em telas sensíveis ao toque.
* **Atalhos e Facilidade**: Tecla `Esc` fecha qualquer modal ou drawer aberto; `Enter` submete formulários.
