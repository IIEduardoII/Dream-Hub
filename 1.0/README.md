# Dream Hub - Sistema Pessoal Integrado

O Dream Hub é um sistema pessoal autônomo e de alta performance que roda 24/7 em um smartphone Android como servidor privado via Tailscale. Centraliza a rotina pessoal em quatro pilares fundamentais: **Tarefas** (Kanban, lista e foco), **Tempo** (Pomodoro flexível e customizável por tarefa), **Finanças** (fluxo de caixa, saldo e categorização) e **Segundo Cérebro** para ideias e anotações.

---

## 1. Acesso ao Sistema

Substitua `<SEU_IP_TAILSCALE>` pelo IP do seu dispositivo na rede Tailscale:

* **URL HTTP Direta**: `http://<SEU_IP_TAILSCALE>:8090`
* **URL HTTPS (com certificado local)**: `https://<SEU_IP_TAILSCALE>:8445`
* **Status da Conexão / Health Check**: `http://<SEU_IP_TAILSCALE>:8090/api/health`

### Como Instalar como Aplicativo no Celular (PWA)
1. No seu celular de uso diário conectado ao Tailscale, abra o navegador (Chrome ou Firefox) e acesse `http://<SEU_IP_TAILSCALE>:8090`.
2. Toque nos três pontinhos do navegador e selecione **"Adicionar à tela inicial"** ou **"Instalar aplicativo"**.
3. O ícone do Dream Hub aparecerá na sua gaveta de aplicativos funcionando como um app nativo em tela cheia com Bottom Navigation Bar.

---

## 2. Funcionalidades Entregues

### 1. Início (Dashboard / Overview)
- Métricas em tempo real consolidadas: Tarefas pendentes e contagem de urgências, minutos de foco acumulados no dia, saldo financeiro mensal (Receitas vs Despesas) e total de ideias ativas.
- Botões de ação rápida de um toque para lançar qualquer registro instantaneamente.
- Painel de prioridades imediatas com atalho direto para iniciar cronômetro focado na tarefa.

### 2. Módulo de Tarefas (Tasks)
- Alternador entre **Quadro Kanban** (A Fazer, Em Execução, Concluído) e **Modo Lista**.
- Filtro por prioridade: Urgente, Alta, Média e Baixa.
- Acompanhamento de Pomodoros por tarefa (`🍅 concluídos / previstos • Duração em min`).
- Configuração de **duração personalizada de foco por tarefa** (ex: 15m para tarefas rápidas, 45m ou 60m para deep work).
- Botão "⏱ Focar" que abre o timer Pomodoro com a tarefa já vinculada e sincroniza automaticamente a duração definida para ela.
- **Exclusão de Tarefas**: Botão direto `🗑` no cartão da tarefa e botão `🗑 Excluir` no modal de edição com confirmação de segurança.

### 3. Módulo de Tempo (Pomodoro & Foco)
- Seleção dinâmica de duração de foco:
  - **Presets Rápidos**: `15m`, `25m`, `45m`, `50m`, `60m` e botão `Outro ✎` (qualquer duração entre 1 e 180 minutos).
  - **Ajuste Fino**: Botões `-5m` e `+5m` ao lado do display do cronômetro para adicionar ou reduzir tempo instantaneamente.
  - **Vínculo com Tarefas**: Ao selecionar uma tarefa, o cronômetro sincroniza automaticamente com o tempo configurado nela.
- Display numérico amplo em fonte monospace com modos de Foco, Pausa Curta (5m) e Pausa Longa (15m).
- Alerta sonoro suave sintetizado via Web Audio API ao término de cada ciclo (sem dependência de arquivos de áudio externos).
- Histórico das sessões concluídas no dia.

### 4. Módulo Financeiro (Finanças Pessoais)
- Seletor de mês de competência com cálculo dinâmico de Receitas (+), Despesas (-) e Saldo Líquido.
- Resumo agrupado das despesas por categoria funcional (Alimentação, Moradia, Transporte, Lazer, etc.).
- Extrato com discriminação por data, forma/conta (PIX, Dinheiro, Cartão) e botão para exclusão rápida.
- Armazenamento em centavos inteiros (`amount_cents`) para prevenir erros de precisão monetária.

### 5. Segundo Cérebro (Organização de Ideias)
- Quadro de anotações com suporte a formatação livre e Markdown.
- Classificação por estágios de maturação: **Rascunho** -> **Em Análise** -> **Em Execução** -> **Arquivado**.
- Filtros rápidos por estágio e busca textual em tempo real por título, texto ou tags `#`.

---

## 3. Arquitetura e Execução no Smartphone

O sistema foi desenhado para rodar de forma isolada e leve:

| Aplicação | Porta HTTP | Porta HTTPS | Porta API Interna | Banco de Dados | Serviço Runit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dream Hub** | `8090` | `8445` | `127.0.0.1:8001` | SQLite WAL (`nexus.db`) | `nexus-api`, `nexus-nginx` |

### Comandos de Gestão no Termux:
```bash
# Verificar status dos serviços
SVDIR=$PREFIX/var/service sv status nexus-api nexus-nginx

# Reiniciar serviços após atualizações
SVDIR=$PREFIX/var/service sv restart nexus-api nexus-nginx

# Inspecionar logs
cat ~/.local/share/nexus/log/api/current
cat ~/.local/share/nexus/log/nginx/current
```

### Configuração e Deploy:
1. Copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Preencha com o IP do Tailscale e credenciais SSH do seu celular.
3. Execute o script de deploy:
   ```bash
   ./scripts/deploy-to-termux.sh
   ```

### Rodar Testes Unitários Localmente:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
