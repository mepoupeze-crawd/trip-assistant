# Luxury Europe Trip Planner — Build Plan (MVP Telegram)

## What We’re Building

Um **bot no Telegram** (MVP) onde o usuário consegue:

* Responder um briefing rápido (origem, 1 país na Europa, nº dias, mês/ano, budget por pessoa, preferências e restrições)
* Receber **um único roteiro final** (não múltiplas opções) com:
  * Sugestão de cidades + dias por cidade (dentro do país)
  * Hotéis (5* e boutique; podendo ter 1–2 noites mais simples se necessário para caber no budget)
  * Atrações e atividades
  * Restaurantes e bares
  * Logística (voo / trem / carro), com margens e descanso quando aplicável
* Output entregue como **PDF + DOCX (Word)** + link compartilhável

Formato inspirado no plano de referência.

---

## Why

Hoje, mesmo viajantes experientes gastam **muitas horas** para:

* Decidir cidades e dividir dias
* Filtrar “armadilhas turísticas” (lotado / ruim / caro sem entregar)
* Garantir **conforto** (hotel/transfer/passeios) e **segurança**
* Montar um roteiro executável (tabela diária)

O MVP existe para:

* Reduzir tempo de planejamento
* Melhorar a qualidade das escolhas (curadoria + regras)
* Aumentar previsibilidade (“vai funcionar”) com links e evidências

---

## Scope Guardrails (MVP)

* **Europa, 1 país por vez**
* **1 roteiro final** por compra (sem variações “A/B/C”)
* **NÃO** aceitar recomendações “pouco avaliadas”, mesmo com editorial / Tablet
* Atualização de base/heurísticas: **trimestral**
* **Não fazemos reservas** (somente entrega do plano)

---

## Stack (infra mais simples possível)

* **Bot**: Telegram Bot API + Node.js (Telegraf) *ou* Python (python-telegram-bot)
* **Backend**: 1 serviço (FastAPI ou Next.js API) com endpoints para geração e pagamento
* **Database**: Postgres (Neon/Supabase) — persistência e histórico de roteiros
* **Queue/Jobs**: BullMQ (Redis) *ou* fila do provider (para geração assíncrona e estável)
* **Storage**: S3 compatível (R2/S3) para PDF/DOCX
* **Payments**: Stripe (internacional) *ou* Mercado Pago (Brasil) — preço teste: **R$100**
* **Doc generation**:
  * PDF: ReportLab
  * DOCX: python-docx
* **Observabilidade**: Sentry + logs estruturados

> Princípio: 1 repo, 1 deploy, mínimo de moving parts, mas com fila para evitar travar o bot.

---

## Components

### 1) Conversation & Intake (Telegram)

Fluxo do bot:

* Origem (cidade/aeroporto)
* Solo/casal
* País (Europa) + (opcional) cidades desejadas
* Nº dias + mês/ano
* Budget por pessoa
* Ritmo: leve/médio/intenso
* Preferências: natureza/cultura/gastronomia (ordem)
* Aversão a multidões: baixa/média/alta
* Preferência de hotel: 5*/boutique/misto
* Restrições: mobilidade, horários, dietas etc.
* Checkout (R$100) → confirma geração

Persistir tudo em `trips` (ver schema) para reuso e auditoria.

---

### 2) Data Connectors (Fontes permitidas + exceções)

Conectores por tipo:

* **Hotéis / editorial**: cntraveler, travelandleisure, nationalgeographic travel, tablet hotels, lalarebelo
* **Atrações/atividades**: getyourguide, tripadvisor (BR)
* **Restaurantes/bares**: worlds50best discovery, guide michelin
* **Reviews/ratings/custo**: Google Maps (ideal via Places API, sem scraping)
* **Voos**: Google Flights como referência
  * MVP viável: usuário informa “aeroporto de saída/chegada + datas” e o sistema estima tempo e inclui regras de margem
  * Evolução: integrar um provedor (ex.: Amadeus/Skyscanner) para tempo/preço sem depender de scraping

**Exceção (quando orçamento inviável):**
* Buscar alternativa em Google ou Booking.

> Importante: evitar scraping de páginas com restrições/ToS; preferir APIs oficiais quando existir (ex.: Places).

---

### 3) Quality & Anti-Trap Rules Engine (core do produto)

Regras mínimas:

* **Sem low-review**:
  * Definir thresholds por tipo (ex.: review_count ≥ 1000 e rating ≥ X)
  * Se não houver 10 opções que passem:
    * expandir raio (bairro) → trocar cidade → reduzir lista (com justificativa)
* **Anti-lotação**:
  * Evitar “top genérico” em horários de pico quando houver alternativa
  * Preferir experiências com horário marcado/capacidade
* **Conforto logístico**:
  * Deslocamento terrestre <3h → priorizar trem/carro
  * Trechos >8h → adicionar descanso (≥8h)
  * Dias de voo internacional → margem + chegada 2–3h antes
* **Orçamento**:
  * Se estourar: permitir 1–2 noites mais simples (mantendo conforto)
  * Trocar bairro/categoria antes de cortar “imperdíveis”
* **Transparência**:
  * Sempre link para a fonte + sinal de confiança (reviews/rating)

---

### 4) Trip Composer (cidades, dias, ritmo)

Responsável por:

* Sugerir cidades dentro do país (quando usuário não define)
* Distribuir dias por cidade (baseado em densidade de experiências + deslocamento)
* Montar agenda diária:
  * manhã / tarde / noite
  * alternância leve/intenso
  * reservas/horários sugeridos (quando aplicável)
  * inserção de deslocamentos entre cidades

Output deve sempre aderir ao formato de tabela exigido pelo produto.

---

### 5) Document Generator (PDF + DOCX)

Gera 2 arquivos:

1) **Listas por cidade**
   * Hotéis (10)
   * Atrações (10)
   * Atividades (10)
   * Restaurantes (10)
   * Bares (10)

2) **Tabela diária**
| Data | Hospedagem | Cidade | Manhã | Tarde | Noite |

Regras:
* Datas no padrão dd/mm (dia da semana)
* bullets curtos em manhã/tarde/noite
* indicar deslocamentos na linha do dia

---

### 6) Delivery & Link Sharing

* Upload PDF/DOCX no storage
* Enviar ao usuário:
  * link do PDF
  * link do DOCX
  * (opcional) link de visualização (Google Drive/Doc) — fase 2

---

## Data Model (Postgres)

Tabelas mínimas:

* `users`: id, telegram_id, name, email (opcional), created_at
* `trips`: id, user_id, origin, country, dates_or_month, days, party_size, budget_per_person, preferences_json, created_at
* `trip_outputs`: id, trip_id, status (`queued|running|done|failed`), pdf_url, docx_url, created_at
* `recommendations`: id, trip_id, city, type (`hotel|attraction|activity|restaurant|bar`), name, rating, review_count, price_hint, source_name, source_url
* `payments`: id, trip_id, provider, amount, currency, status, created_at

---

## Backend API (serviço único)

Endpoints MVP:

* `POST /api/trips` — cria trip a partir do briefing
* `POST /api/payments/create` — cria checkout
* `POST /api/payments/webhook` — confirma pagamento
* `POST /api/trips/:id/generate` — enfileira geração
* `GET /api/trips/:id/status` — status
* `GET /api/trips/:id/output` — links do PDF/DOCX

---

## Dependencies Between Components

```

Bot intake → Trip record → Payment confirmed → Queue job
Queue job → Data connectors → Rules engine → Trip composer
Trip composer → Document generator → Storage upload → Bot delivery

````

---

## Acceptance Criteria (MVP)

1. Usuário conversa com o bot e consegue informar briefing completo (Europa, 1 país).
2. Usuário paga **R$100** e recebe confirmação de início.
3. Em até X minutos, o bot entrega **PDF + DOCX** com:
   * Listas por cidade (10 itens por categoria quando possível)
   * Tabela diária no formato exato
4. Nenhuma recomendação abaixo do mínimo de qualidade (rating/review_count) entra no output.
5. Se o orçamento estourar, o sistema:
   * ajusta hotéis permitindo 1–2 noites mais simples **ou**
   * troca bairro/cidade
   e registra a justificativa no output (curto e objetivo).
6. Logs + rastreabilidade: para qualquer roteiro, conseguimos ver fontes usadas e regras acionadas.

---

## Risks and Mitigations

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Dependência de fontes sem API (ex.: Flights/Maps) | alto | Preferir APIs oficiais (Places) e provedores de voo; evitar scraping; fallback: usuário informa voo/horário. |
| “Roteiro bonito e errado” (alucinação) | alto | Forçar links/evidências por item; bloquear itens sem fonte; checagens de consistência (dias/locomoção). |
| Não conseguir 10 itens “bons” em cidades pequenas | médio | Expandir raio/bairro → trocar cidade → reduzir lista com justificativa; nunca baixar threshold silenciosamente. |
| Estouro de orçamento | alto | Budget engine por faixas; permitir 1–2 noites mais simples; priorizar trocas de bairro/categoria. |
| Links quebrados / conteúdo muda | médio | Verificação automática de links + cache trimestral + retentativa em geração. |
| Experiências lotadas mesmo com bom review | médio | Heurística anti-lotação (horários, dias, alternativas) + priorizar experiências com horário marcado. |
| Usuário espera reserva/concierge | médio | Deixar explícito: “entregamos plano, não reservamos” + upsell futuro. |

---

## Validation

### Local

```bash
# bot + api
npm install
npm run dev

# (se python para docs)
pip install -r requirements.txt
python -m app.generate_sample
````

### Quick checks

```bash
# criar trip
curl -s -X POST http://localhost:3000/api/trips \
  -H "Content-Type: application/json" \
  -d '{"origin":"GRU","country":"Italy","days":10,"month":"09/2026","party":"couple","budgetPerPersonBRL":30000,"prefs":{"pace":"medium","focus":["food","culture","nature"],"crowds":"high","hotel":"mixed"}}'

# enfileirar geração
curl -s -X POST http://localhost:3000/api/trips/TRIP_ID/generate
```

### Manual E2E (5 minutos)

1. Abrir bot → preencher briefing (1 país Europa)
2. Pagar → receber confirmação
3. Receber PDF/DOCX → checar:

   * listas por cidade
   * tabela diária no formato correto
4. Checar que nenhum item tem reviews abaixo do mínimo
5. Testar um caso com budget baixo → verificar 1–2 noites mais simples e justificativa
