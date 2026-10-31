# Dream Hub v1.3.0 - Cockpit Pessoal Unificado (PWA WebAPK & Android)

Plataforma autônoma de produtividade, finanças, saúde física e conhecimento pessoal projetada para rodar com **custo R$ 0,00** em um smartphone servidor residencial (**Termux + Runit + Nginx + Gunicorn + SQLite 3 WAL**), isolada de forma privada na **Tailnet (Tailscale)** com suporte a **Domínio Gratuito (DuckDNS) + HTTPS Oficial (Let's Encrypt DNS-01)** e instalação nativa como **PWA (`WebAPK`)** ou **APK Capacitor**.

---

## 1. Principais Módulos da Versão 1.3.0

1. **Módulo Ritmo Integrado & Sono**:
   - Rotinas, catálogo de exercícios, execução de treinos com cronômetro de descanso, séries/cargas/RPE, Matriz Temporal (Modo Calendário), biometria de peso, fotos de evolução e registro diário de sono.
2. **FAB Global Único (`+`)**:
   - Captura rápida em 1 toque em qualquer tela para Tarefas, Finanças, Ideias, Treinos do Ritmo e Sono.
3. **Pomodoro Resiliente em Segundo Plano**:
   - Persistência de estado via `localStorage` combinada com diferencial de timestamp real (`Date.now()`).
4. **Finanças, Contas Fixas (`recurring_rules`), Projeção 30/60/90d, Metas (`goals`) e Anotações Markdown (`notes`)**:
   - Com suporte a anexos físicos descentralizados (`uploads/` até 15 MB) e zero arquivos órfãos.
5. **HTTPS Oficial (DuckDNS + Let's Encrypt DNS-01) & PWA Nativo (`WebAPK`)**:
   - Emissão de certificado ECC P-256 via `acme.sh` (`dns_duckdns`) sem abrir portas 80/443 no roteador, mantendo `allow 100.64.0.0/10; deny all;` na Tailnet.
   - Manifesto W3C completo com ícones PNG (`192x192`, `512x512`, `maskable`), atalhos de lançador Android (`shortcuts`) e Service Worker Online-First sem cache obsoleto.

---

## 2. Arquitetura e Portas no Servidor Termux

| Serviço | Porta HTTP | Porta HTTPS | API Interna | Banco de Dados | Runit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dream Hub v1.3** | `8090` | `8445` | `127.0.0.1:8001` | SQLite WAL (`~/nexus-termux/nexus.db`) | `nexus-api`, `nexus-nginx` |

---

## 3. Como Configurar HTTPS Oficial (DuckDNS) e Instalar o PWA

1. Copie `.env.example` para `.env` e preencha suas credenciais do Termux e do [DuckDNS](https://www.duckdns.org/):
   ```bash
   cp .env.example .env
   ```
2. Execute a suíte de testes e publique no servidor Termux:
   ```bash
   .venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
   ./scripts/deploy-to-termux.sh
   ```
3. Emita e instale o certificado Let's Encrypt oficial via desafio `DNS-01`:
   ```bash
   ./scripts/setup-https-duckdns.sh
   ```
4. No Chrome Android (com Tailscale ativo), acesse `https://<SEU_SUBDOMINIO>.duckdns.org:8445` e toque em **Menu (`⋮`) -> Instalar aplicativo** (ou use a opção **📲 Instalar Aplicativo** dentro do menu do próprio Dream Hub) para gerar o **WebAPK nativo** na gaveta de apps com tela cheia OLED (`#000000`).
