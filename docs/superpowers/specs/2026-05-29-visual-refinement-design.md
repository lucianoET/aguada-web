# Design: Refinamento Visual — Aguada Web
**Data:** 2026-05-29  
**Escopo:** Abordagem B — paleta, tipografia, espaçamento, sem tocar lógica JS/API

---

## Objetivo

Melhorar a aparência das páginas do sistema hidráulico refinando o CSS existente. Nenhuma mudança de comportamento, rotas, banco ou WebSocket.

---

## Arquivos Modificados

| Arquivo | O que muda |
|---|---|
| `frontend/assets/aguada.css` | Variáveis de fonte, paleta claro, tokens de sombra |
| `frontend/assets/style.css` | Header adaptado ao tema, variáveis duplicadas removidas |
| `frontend/painel.html` | CSS inline: tank cards reescritos, hero KPI refinado |

As demais páginas (`scada`, `dados`, `alertas`, `manutencao`, `qualidade`, `ete`, `relatorio_tabelas`, `documentacao`) herdam o header corrigido via `style.css` sem alteração individual.

---

## 1. Tipografia

**Problema atual:** `--mono` aponta para `'Courier New'` e `--sans` para `system-ui`, apesar de JetBrains Mono e DM Sans estarem carregadas via Google Fonts no `<head>` do painel.

**Correção em `aguada.css`:**
```css
--mono: 'JetBrains Mono', 'Courier New', monospace;
--sans: 'DM Sans', system-ui, -apple-system, sans-serif;
```

**Regra de uso (aplicar em todo CSS novo/editado):**
- Labels, nomes, textos de interface → `font-family: var(--sans)`
- Valores numéricos, aliases, timestamps, KPIs → `font-family: var(--mono)`

---

## 2. Paleta — Tema Claro

**Problema atual:** fundo frio/flat, sem profundidade nos cards.

**Mudanças em `aguada.css` (`:root`):**
```css
--bg:   #f0f4f8;   /* era #f1f5f9 — ligeiramente mais quente */
--card: #ffffff;   /* sem mudança, mas ganha sombra via token */
--card-shadow: 0 1px 3px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.04);
```

Tema escuro: sem alteração de paleta (aprovado nos mockups).

---

## 3. Header — `style.css`

**Problema atual:** `.admin-header` usa `background: linear-gradient(135deg, #1e3a5f, #2d4a6f)` hardcoded — ignora `data-theme` e quebra no tema claro.

**Correção:**
```css
.admin-header {
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  /* remove gradient hardcoded */
}
.admin-header-brand { color: var(--text); }
.admin-nav a { color: var(--text3); }
.admin-nav a:hover { color: var(--text2); background: transparent; }
.admin-nav a.active {
  border-bottom-color: var(--blue);   /* era #10b981 hardcoded */
  color: var(--text);
}
```

Status dot e demais elementos do header adaptam automaticamente via variáveis já existentes.

---

## 4. Cards de Reservatório — `painel.html`

### Estrutura do card (aprovada nos mockups B/C)

```
┌─────────────────────────────────┐  ← border colorida no warn
│ Nome Reservatório    RAP-01  ●  │  ← DM Sans 13px bold + alias Mono 9px + dot
│                                 │
│ 4,900    m³  │  70%             │  ← Mono 30px + Mono 22px, cor pelo estado
│                                 │
│  [água subindo do fundo]        │  ← position: absolute, sem texto dentro
│                                 │
│ Capacidade   7,000 m³           │  ← grade 2×2, Mono 11px, empurrada pro rodapé
│ Cons. diário 1,240 L            │
│ Taxa cons.   52 L/h             │
│ Última leit. 05:43              │
└─────────────────────────────────┘
```

### Implementação

- Container: `position: relative; overflow: hidden; height: 240px; border-radius: 12px`
- Água: `position: absolute; left:0; right:0; bottom:0; border-top: 2px solid` — sem texto
- Conteúdo: `position: absolute; inset:0; z-index:2; display:flex; flex-direction:column; padding: 12px 13px`
- Spacer flex entre KPI e rodapé empurra detalhes para baixo

### Estados visuais

Thresholds existentes no `painelApp()`: `critical` = pct ≤ 20, `warning` = pct 21–35, `ok` = pct > 35.

| Estado | Condição | Borda card | Cor volume/% | Água | Dot |
|---|---|---|---|---|---|
| ok | pct > 35 | `var(--border)` | `var(--blue)` / `#93c5fd` dark | azul translúcido | verde com glow |
| warn | pct 21–35 | âmbar `#fde68a` | `var(--yellow)` / `#fcd34d` dark | âmbar translúcido | âmbar com glow |
| critical | pct ≤ 20 | vermelho `var(--red-dim)` | `var(--red)` / `#f87171` dark | vermelha translúcida | vermelho com glow |
| offline | `!r.online` | `var(--border)` | `var(--text3)` | cinza translúcida | vermelho sem glow |

### Dados extras — consumo e taxa

Endpoint existente: `GET /api/consumption?alias=RAP-01&date=2026-05-29`

O frontend já chama esse endpoint ao abrir o modal de reservatório. Para o card do painel, chamar o mesmo endpoint na inicialização do `painelApp()` e armazenar no objeto do reservatório (`r.consumed_l`, `r.rate_lh`, `r.last_ts`).

Campos adicionais no card:
- **Capacidade:** `r.capacity_l` — já disponível via `/api/reservoirs` (campo `capacity_l`)
- **Cons. diário:** `r.consumed_l` — do `/api/consumption`
- **Taxa cons.:** `r.rate_lh` — calculado: `consumed_l / horas_decorridas_hoje`
- **Última leit.:** `r.ts` formatado como `HH:MM`

---

## 5. Hero KPI Strip — `painel.html`

Ajustes no CSS inline existente:

- Adiciona `box-shadow: var(--card-shadow)` nos `.hero-kpi` (tema claro)
- Labels (`hero-kpi-lbl`): `font-family: var(--sans)` explícito
- Valores (`hero-kpi-val`): `font-family: var(--mono)` explícito
- Tags de contexto (`hero-kpi-side`): substituir texto solto por span com `border-radius: 999px; padding: 3px 8px; background: var(--bg3); border: 1px solid var(--border2)` — igual ao mockup aprovado

---

## 6. Variáveis Duplicadas — `style.css`

Remover ou redirecionar para `aguada.css` as seguintes variáveis que criam conflito:

```css
/* REMOVER de style.css — já definidas em aguada.css: */
--background-light, --border-color, --text-dark, --text-muted,
--success-green, --warning-orange, --danger-red
```

`--primary-blue`, `--accent-purple`, `--accent-pink` podem permanecer se usados em componentes específicos de outras páginas (verificar durante implementação).

---

## Fora do Escopo

- Lógica JavaScript, Alpine.js, WebSocket
- Rotas FastAPI, banco SQLite
- Página SCADA (tem design próprio ISA-101, não tocar)
- Responsividade — manter media queries existentes

---

## Critérios de Sucesso

1. Ambos os temas (claro/escuro) funcionam corretamente — header adapta ao tema
2. JetBrains Mono aparece nos valores numéricos, DM Sans nas labels
3. Cards de reservatório exibem: nome, volume m³, %, capacidade, consumo diário, taxa, última leitura
4. Água preenche card sem texto sobreposto
5. Estado warn acende borda âmbar e cor de alerta nos valores
6. Nenhum teste quebra (`pytest`)
