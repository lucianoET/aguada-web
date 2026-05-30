# Design — Restyle visual do frontend (estilo Home Assistant)

**Data:** 2026-05-30
**Escopo desta sessão:** melhoria visual / consistência das páginas web existentes.
**Fora de escopo (backlog, specs próprios):** armazenamento de laudos/relatórios, configuração de ESP/rede via UI, integração com Home Assistant, deploy Docker, religar sensores, Grafana/InfluxDB.

## Problema

O frontend tem **dois sistemas de design coexistindo e conflitantes**:

- `frontend/assets/aguada.css` — design system correto, tokens dark-aware (`--text3`, `--green`, `--bg2`), vocabulário `.card`/`.table`/`.badge-*`/`.page-header`/`.kpi-card`. Usado pelo `painel.html` (página mais polida = referência).
- `frontend/assets/style.css` — sistema paralelo com tokens próprios hardcoded (`--success-green:#10b981`, `--font-sm`, `--text-muted`, `--border-color`, `--primary-blue`) que **não reagem ao tema escuro**, e classes legadas `.box`/`.page-box`/`.param-card`/`.abadge`/`.alert-item`.

Consequências: `alerts.html` e `qualidade.html` usam hex fixos (ex. `#fef2f2`) que **quebram no dark**; ícones emoji vs SVG; cards/headers/botões divergentes por página.

## Objetivo

Convergir todas as páginas (exceto SCADA, que mantém o esquemático) para um **único token system** e um **kit de componentes com a linguagem visual do Home Assistant**, preservando a paleta de cor Aguada.

## Decisões de design

### 1. Princípio: "HA-inspired, paleta Aguada"
Adotar a **linguagem de forma** do HA (cantos 12px, elevação/sombra suave, respiro generoso, stat big-number, gauges radiais, listas de entidade). **Manter a paleta Aguada** (`--blue #2563eb`, verdes/vermelhos já dark-aware) — NÃO importar o azul HA `#03a9f4`. Cara de HA, marca Aguada.

### 2. Token system único
- `aguada.css` é a fonte única de tokens.
- O bloco `:root` de `style.css` vira **aliases de compatibilidade** → canônicos:
  - `--success-green` → `var(--green)`
  - `--warning-orange` → `var(--yellow)`
  - `--danger-red` → `var(--red)`
  - `--text-muted` → `var(--text3)`
  - `--text-dark` → `var(--text)`
  - `--border-color` → `var(--border)`
  - `--background-light` → `var(--bg)`
  - `--font-base/sm/xs/xxs/lg/xl` → valores fixos (14/12/11/10/16/20 px) — mantidos como conveniência tipográfica.
  - `--primary-blue`/`--primary-light`/`--accent-purple`/`--accent-pink` → mapeados para `var(--blue)`/`var(--cyan)` (sem roxo/rosa fora da paleta).
- Cores hex fixas em páginas/CSS trocadas por tokens `*-dim`/`*` → conserta o dark.
- Classes legadas (`.box`, `.page-box`, `.param-card`, `.abadge`, `.alert-item`) removidas conforme cada página migra. `style.css` encolhe até sobrar só o que é único (ex. `.admin-header` e correlatos), que permanece.

### 3. Kit de componentes HA (novo, em `aguada.css`)
Seção marcada `/* === HA COMPONENT LAYER === */`:
- `.ha-card` — `border-radius:12px`, sombra suave no tema claro / borda no escuro (via `--card-shadow`), `padding:16px`; sub-elemento `.ha-card-title` (15px, weight 500) e `.ha-card-body`.
- `.ha-stat` — card big-number: valor (mono, ~28px), label (uppercase 10px `--text3`), unidade, delta opcional com cor (`--green`/`--red`). Substitui `hero-kpi`/`kpi-card`/`param-card`.
- `.ha-gauge` — **gauge SVG** reutilizável: arco 270°, bandas de severidade verde/amarelo/vermelho nos limiares **40/20/10%** (de `dashboard.yaml`), número central + unidade. Implementado por função JS `renderGauge(el, {value, min, max, unit, severity})` em novo util compartilhado `frontend/assets/ha-ui.js` (carregado pelas páginas que usam gauge).
- `.ha-entities` — lista de linhas rótulo→valor com ícone SVG (estilo `type: entities` do HA); suporta `.ha-divider`.
- `.ha-section` — header de seção com ícone SVG. **Remove emojis** (🚨💧🏭🏰⚙️) substituindo por SVGs inline no padrão já usado no painel.
- Gráficos de série temporal: continuam **Chart.js** (já em `assets/vendor/chart.min.js`). Gauge é SVG (mais nítido, sem plugin extra).

### 4. Mapeamento por página

| Página | Mudança |
|---|---|
| `painel.html` | Referência. Suavizar para a forma HA (rounding/sombra/respiro); hero-KPI → linha de `.ha-stat` + 1 gauge de sistema; tank cards passam a `.ha-card`. |
| `dados.html` | Gráficos Chart.js dentro de `.ha-card`; KPIs → `.ha-stat`; gauges onde couber. |
| `alerts.html` | Itens de alerta → cards de notificação HA usando tokens (conserta dark); resumo → `.ha-entities`. |
| `qualidade.html` | `.param-card` → `.ha-stat`; tabelas → `.table`; emoji → ícone SVG; abas mantêm `.tab-btn`. |
| `manutencao.html` | Conteúdo em `.ha-card`; headers/botões/tabelas/badges unificados. |
| `relatorio_tabelas.html` | Idem — `.ha-card`, `.table`, badges e botões canônicos. |
| `ete.html` | Idem. |
| `documentacao.html` | Idem. |
| `scada.html` | **Só tokens** — esquemático ISA-101 intacto. |

### 5. Componentes como unidades isoladas
Cada página é uma unidade independente que consome o kit compartilhado (`aguada.css` + util de gauge). O kit é a interface; pode-se mudar o interior de uma página sem afetar as outras. `renderGauge` e os componentes CSS têm contrato claro (entrada → render) e são testáveis isoladamente em uma página de exemplo.

## Plano de execução (ordem)

1. **Fundação:** adicionar HA COMPONENT LAYER em `aguada.css`; converter `:root` de `style.css` em aliases; criar util `renderGauge`.
2. **Migração página a página**, `painel.html` primeiro (referência). Cada página verificada em **dark e light** rodando localmente (webapp-testing/screenshot) antes de seguir para a próxima.
3. **Limpeza:** remover CSS/classes legadas mortas ao final.

## Restrições

- **Sem mudança de backend.** Sensores offline → verificação visual usa os dados de fallback/simulação já presentes nas páginas.
- 100% offline; stack atual mantido (HTML puro + Alpine.js + Tailwind compilado + Chart.js/Leaflet vendorizados). Nenhuma dependência nova.
- Tema claro e escuro devem ficar corretos em todas as páginas migradas.

## Critérios de sucesso

- Nenhuma cor hardcoded que quebre no dark nas páginas migradas.
- Todas as páginas (exceto SCADA) usam o kit `.ha-*` e os tokens canônicos.
- `style.css` reduzido aos estilos únicos remanescentes; tokens duplicados eliminados (ou só aliases).
- Visual consistente (cards, headers, botões, badges, tipografia) entre páginas, em ambos os temas.
- Gauges radiais renderizando com bandas de severidade corretas.

## Referências

- Página de referência atual: `frontend/painel.html`.
- Arquitetura de informação do produto e entidades: `homeassistant/dashboard.yaml` + `template_sensors.yaml` (repo `espnow-ha`).
- Memórias: `aguada-product-vision`, `aguada-frontend-design-debt`.
