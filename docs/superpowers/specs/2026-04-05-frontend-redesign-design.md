# Aguada — Redesign do Frontend (Fase 1)

**Data:** 2026-04-05  
**Projeto:** aguada-web (`/home/luc/Dev/aguada-web`)  
**Escopo:** Redesign completo do frontend. Backend (FastAPI + SQLite + Docker) inalterado.

---

## Contexto

O sistema Aguada monitora reservatórios hidráulicos da CMASM via sensores ESP32-C3 (ESP-NOW). Versões de referência:

- **aguada-web** — backend Python/FastAPI, SQLite, Docker, WebSocket ao vivo. Frontend: HTML puro + Alpine.js + Tailwind CSS. **Base do projeto.**
- **aguada3** — backend PHP/MySQL. Frontend com CSS escuro próprio, sidebar fixa, estilo industrial. **Referência visual.**
- **aguada2** (`/home/luc/Dev/aguada2-main`) — versão PHP com CSS próprio (aguada2.css), sidebar fixa, diagrama SCADA SVG completo com topologia real (Ilha das Flores → linha submarina → Ilha do Engenho). **Referência para o SCADA SVG e CSS.** Coordenadas da CMASM: `[-22.84, -43.10]`.
- **xAguada** (GitHub: luctronics-ET/xAguada) — versão anterior com topologia de rede completa em JSON (`network_topology.json`, `reservoirs.json`). **Referência de dados/domínio.**

O redesign mantém todo o backend do aguada-web e migra o frontend para o estilo visual do aguada3.

---

## Decisões de Design

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Base do projeto | aguada-web | Backend mais completo: FastAPI, WebSocket, Docker, SQLite |
| Estilo visual | aguada3 | Tema escuro industrial, CSS semântico, variáveis bem definidas |
| Abordagem | Migração incremental | Risco menor, sempre tem versão funcionando |
| Navegação | Sidebar colapsável | Mais itens de menu, estilo SCADA, área útil maior |
| Tema | Escuro como padrão, claro simplificado | DNA do sistema; claro existe mas não é prioridade |
| CSS | aguada.css + Tailwind utilitários | Semântica do aguada3 + conveniência do Tailwind existente |
| Dependências JS | Vendors offline em `assets/vendor/` | Sem internet, arquivos estáticos simples |
| Mapa | Leaflet + OSM tiles locais | Offline, posições corretas da CMASM |
| Dashboard | Mapa OSM com marcadores | Visão geográfica dos reservatórios |
| SCADA | Página separada, diagrama SVG | Espaço adequado para diagrama de blocos complexo |

---

## Estrutura de Páginas

| Arquivo | Título | Substitui |
|---------|--------|-----------|
| `index.html` | Dashboard | `index.html` (reescrito) |
| `scada.html` | SCADA | `scada.html` (reescrito) |
| `analise.html` | Análise | `history.html` + `consumption.html` + `abastecimento.html` + `dados.html` |
| `report.html` | Relatório | `report.html` (migrado) |
| `dispositivos.html` | Dispositivos | `dispositivos.html` (migrado) |
| `documentacao.html` | Documentação | `documentacao.html` (migrado + expandido) |

Páginas antigas consolidadas (`history.html`, `consumption.html`, `abastecimento.html`, `dados.html`) removidas após validação da Etapa 4.

---

## Sistema de Design

### Paleta de cores

```css
/* Tema escuro (padrão — :root) */
--bg:         #0b0f14;   /* fundo principal */
--bg2:        #111820;   /* sidebar, topbar */
--bg3:        #161e28;   /* hover, inputs */
--card:       #192030;   /* cards */
--border:     #1e2d3d;
--border2:    #243344;
--text:       #c9d4e0;
--text2:      #6b82a0;
--text3:      #3d556e;
--blue:       #3b82f6;
--blue-dim:   #1e3a5f;
--green:      #22c55e;   /* normal / ligada / aberta */
--green-dim:  #14532d;
--yellow:     #f59e0b;   /* atenção */
--yellow-dim: #78350f;
--red:        #ef4444;   /* crítico / falha */
--red-dim:    #7f1d1d;
--cyan:       #06b6d4;   /* accent logo/marca */
--mono:       'Courier New', Courier, monospace;
--sans:       system-ui, -apple-system, 'Segoe UI', sans-serif;

/* Tema claro ([data-theme="light"]) */
--bg:         #f1f5f9;
--bg2:        #ffffff;
--bg3:        #e2e8f0;
--card:       #ffffff;
--border:     #e2e8f0;
--text:       #1e293b;
--text2:      #64748b;
--text3:      #94a3b8;
/* Cores de status idênticas — não mudam entre temas */
```

### Cores ISA-101

| Estado | Cor | CSS var |
|--------|-----|---------|
| Normal / Ligada / Aberta | Verde | `--green` |
| Atenção / Baixo | Amarelo | `--yellow` |
| Crítico / Falha / Fechada | Vermelho | `--red` |
| Offline / Desconhecido | Cinza | `--text3` |
| Em manutenção | Amarelo | `--yellow` |

### Tipografia

- Interface geral: `var(--sans)` 14px
- Códigos, timestamps, valores numéricos técnicos: `var(--mono)`
- Hierarquia: section-title 10px uppercase tracking-wide → label 11px → body 13-14px → valor 18-24px bold

---

## Layout Global

```
┌──[42px sidebar colapsada / 220px expandida]──────────────────┐
│ Logo "A" / "AGUADA"  (hover/toggle expande)                  │
│ ─────────────────────────────────────────                    │
│ [ícone] Dashboard                                            │
│ [ícone] SCADA                                                │
│ [ícone] Análise                                              │
│ ─── separador ───                                            │
│ [ícone] Relatório                                            │
│ [ícone] Dispositivos                                         │
│ [ícone] Documentação                                         │
│ ─────────────────────────────────────────                    │
│ [●] GW online / sim / off                                    │
├──────────────────────────────────────────────────────────────┤
│ topbar: [Título página]  [subtítulo]    [WS status] [☀/🌙]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   .content  (overflow-y: auto)                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Responsividade:**
- ≥ 1024px: sidebar colapsada por padrão, expande com hover ou toggle
- < 1024px: sidebar oculta, aparece como overlay ao clicar no toggle
- < 768px: layout de coluna única nos cards

---

## Dependências Offline

**`frontend/assets/vendor/`**

| Arquivo | Versão | Uso |
|---------|--------|-----|
| `alpine.min.js` | 3.x | Reatividade Alpine.js (todas as páginas) |
| `chart.min.js` | 4.4.x | Gráficos (Análise, Dashboard) |
| `leaflet.min.js` | 1.9.x | Mapa OSM (Dashboard) |
| `leaflet.min.css` | 1.9.x | Estilos do mapa |

**`scripts/download_vendors.py`** — script Python que baixa os vendors e tiles OSM para a área da CMASM. Executar uma vez antes do deploy.

**`frontend/assets/leaflet-tiles/`** — tiles OSM pré-baixados em zoom 13–17 para as coordenadas da CMASM. Leaflet configurado com `L.tileLayer('assets/leaflet-tiles/{z}/{x}/{y}.png')`.

---

## Arquivos Novos / Modificados

```
frontend/
  assets/
    aguada.css              ← NOVO: sistema de design completo
    vendor/
      alpine.min.js         ← NOVO: Alpine.js offline
      chart.min.js          ← NOVO: Chart.js offline (copiar de aguada3)
      leaflet.min.js        ← NOVO
      leaflet.min.css       ← NOVO
    leaflet-tiles/          ← NOVO: tiles OSM locais
  index.html                ← REESCRITO: Dashboard + mapa
  scada.html                ← REESCRITO: diagrama SVG melhorado
  analise.html              ← NOVO: Histórico+Consumo+Abastecimento+Dados
  report.html               ← MIGRADO: novo estilo
  dispositivos.html         ← MIGRADO: novo estilo
  documentacao.html         ← MIGRADO + expandido com docs xAguada
  shared.js                 ← ATUALIZADO: offline, toggleTheme, sidebarState

backend/
  reservoirs.yaml           ← ATUALIZADO: adicionar lat/lng por reservatório

scripts/
  download_vendors.py       ← NOVO: baixa Alpine, Chart.js, Leaflet, tiles OSM
```

---

## Detalhes por Página

### Dashboard (`index.html`)

**Estrutura:**
```
[KPI strip: total | vol médio | críticos | online | última atualização]
[mapa Leaflet — altura: calc(100vh - topbar - kpi-strip)]
```

**Comportamento:**
- Mapa inicializa centrado na CMASM com zoom 15
- Marcadores Leaflet por reservatório: círculo colorido (verde/amarelo/vermelho/cinza) com tooltip `alias + %`
- WebSocket atualiza marcadores em tempo real sem recarregar o mapa
- Clique no marcador → modal lateral deslizante com:
  - Nome, código, status online/offline
  - Barra de nível visual + percentual + volume m³ + nível cm
  - RSSI, última leitura (timestamp)
  - Formulário de leitura manual (modo pct/volume/nível)
- Tiles OSM servidos de `assets/leaflet-tiles/` (fallback: OSM online se arquivo não existir)
- `lat`/`lng` dos reservatórios lidos de `/api/reservoirs` (adicionados ao `reservoirs.yaml`)

**Coordenadas da CMASM:** centro em `[-22.84, -43.10]` (confirmado no aguada2/mapa.php). Posições individuais de cada reservatório a serem adicionadas ao `reservoirs.yaml` — usuário pode gerar export atualizado do OSM para confirmar posições exatas.

---

### SCADA (`scada.html`)

**Estrutura:**
```
[painel principal: diagrama SVG — ~75% largura]
[painel lateral direito: lista de equipamentos — ~25%]
```

**Diagrama SVG:**
- Baseado no diagrama do `aguada2/scada.php` (topologia completa já implementada em SVG): Ilha das Flores (CBIFA, CBIFB, bombas BIF-ELE/BIF-DIE, hidrômetro HID-IF) → linha submarina animada → Ilha do Engenho (CIE1, CIE2, CB03A, CB03B, castelos CON e CAV, bombas B03-ELE/B03-DIE/B02-ELE, hidrômetro HID-PRAIA)
- Ícones PNG de `aguada2/assets/icons/` aproveitados: `pump.png`, `valve.png`, `hydrometer.png`, junções
- Elementos SVG: reservatórios como retângulos/formas trapeziodais com barra de nível animada + %, bombas como círculos, válvulas como losangos, tubos com `stroke-dasharray` animado quando há fluxo
- Cores ISA-101: verde=normal/ligado/aberto, amarelo=atenção, vermelho=crítico/falha, cinza=offline
- Atualização via WebSocket — estados dos equipamentos atualizados sem redesenhar o SVG
- Melhoria sobre aguada2: adicionar estado dinâmico de válvulas (abertas/fechadas) e cores ISA-101 nos tubos

**Painel lateral:**
- Lista de bombas e válvulas com status badge
- Clique → modal de controle: alterar estado (ligada/desligada/manutenção para bombas; aberta/fechada/parcial para válvulas), campo observação, registra log via `/api/manual/pumps` e `/api/manual/valves`
- Hidrômetros listados abaixo: última leitura + botão lançar nova leitura manual

---

### Análise (`analise.html`)

**Quatro abas Alpine.js:**

1. **Histórico** — gráfico de linha Chart.js; seletor de reservatório (todos ou individual); seletor de período (24h / 7d / 30d); usa `/api/history/{alias}`
2. **Consumo** — gráfico de barras (diário/semanal/mensal); usa `/api/consumption`
3. **Abastecimento** — tabela de eventos de entrada + gráfico de linha; usa `/api/manual/reservoirs`
4. **Dados** — tabela paginada de leituras brutas; filtros por reservatório e intervalo de datas; botão exportar CSV (gerado no frontend via Blob)

---

### Relatório (`report.html`)

Migração de estilo. Lógica idêntica à atual: seletor de data → `/api/report/daily` → tabela de resumo por reservatório → botão download PDF (`/api/report/daily.pdf`).

---

### Dispositivos (`dispositivos.html`)

Migração de estilo. Cards por nó ESP32: alias, node_id hex, RSSI, firmware version, uptime, última leitura, status online/offline. Usa `/api/nodes` e `/api/gateway`.

---

### Documentação (`documentacao.html`)

Migração de estilo + conteúdo expandido. Seções expansíveis (accordion Alpine.js):
- Manual de operação (do `aguada-web/frontend/assets/docs/`)
- Instruções de operação (do `xAguada/Documents/instrucoes/operacao.md`)
- Calibração de sensores (`xAguada/Documents/instrucoes/calibracao.md`)
- Procedimentos de emergência (`xAguada/Documents/instrucoes/emergencias.md`)
- Formulários: Manutenção, Calibração, Incidente (`xAguada/Documents/formularios/`)
- Normas técnicas (`aguada-web/frontend/assets/docs/Normas_Tecnicas.md`)

---

## Backend — Alterações Mínimas

Apenas uma alteração no backend: adicionar campos `lat` e `lng` a cada reservatório em `backend/reservoirs.yaml`. O campo já é retornado por `/api/reservoirs` pois o endpoint serializa o YAML inteiro. Nenhuma rota nova necessária para a Fase 1.

```yaml
# Exemplo de adição em reservoirs.yaml
- alias: CON
  nome: Castelo de Consumo
  lat: -23.XXXXX    # coordenada real da CMASM
  lng: -46.XXXXX
  # ... demais campos existentes
```

---

## Sequência de Implementação (Etapas)

| Etapa | Entrega | Arquivos |
|-------|---------|----------|
| 1 | Fundação: CSS + vendors offline + shared.js | `aguada.css`, `vendor/*`, `shared.js`, `download_vendors.py`, `reservoirs.yaml` |
| 2 | Dashboard com mapa Leaflet | `index.html` |
| 3 | SCADA com diagrama SVG melhorado | `scada.html` |
| 4 | Análise unificada | `analise.html` |
| 5 | Relatório + Dispositivos + Documentação | `report.html`, `dispositivos.html`, `documentacao.html` |
| 6 | Polimento: responsividade, ISA-101, tiles locais | todos |

Páginas antigas consolidadas (`history.html`, `consumption.html`, `abastecimento.html`, `dados.html`) removidas ao final da Etapa 4.

---

## Fora de Escopo (Fase 2)

- Página ETE (estação de tratamento de esgoto)
- Qualidade da água (laudos, cloro, limpeza)
- Mapa com tubulação e ícones avançados
- Autenticação / controle de acesso
- Notificações push / alertas por e-mail
