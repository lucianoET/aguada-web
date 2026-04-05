# Aguada — Roadmap & Status

> Este arquivo é a interface principal de comunicação entre o usuário, agentes e sessões futuras.
> Atualize ao iniciar/concluir fases. A especificação completa está em `AGUADA_SYSTEM_DOC.md`.

---

## Estado Atual — 2026-03-18

Gateway USB clássico validado em hardware com bridge/MQTT/Home Assistant. O sistema já publica status/health/ACK do gateway e discovery MQTT para entidades diagnósticas do próprio gateway.

---

## Fases

### Fase 1 — Firmware Node (sensor + relay + NVS boot)
**Status: ✅ Escrito** — não testado em hardware

Arquivos:
- `firmware/node/src/main.cpp` — loop principal, modo sensor/relay, boot NVS
- `firmware/node/src/nvs_config.cpp` — leitura/gravação NVS
- `firmware/node/src/ultrasonic.cpp` — driver HC-SR04
- `firmware/node/src/sensor_filter.cpp` — outlier reject + média móvel
- `firmware/node/src/espnow_radio.cpp` — ESP-NOW init, CRC-16 tx/rx
- `firmware/node/src/mesh.cpp` — tabela de vizinhos, relay, score

Pendente:
- [ ] Compilar com `pio run` no ESP32-C3
- [ ] Testar leitura HC-SR04 em bancada
- [ ] Verificar gravação NVS e boot relay vs sensor

---

### Fase 2 — Protocolo Binário v3 + CRC-16
**Status: ✅ Implementado**

- `firmware/shared/protocol.h` — struct 16 bytes, static_assert, todos os tipos/flags
- CRC-16/CCITT em `crc16.h` (node e gateway têm cópia local)

Pendente:
- [ ] Teste de loopback: node → gateway → verificar JSON no serial

---

### Fase 3 — Filtros
**Status: ✅ Implementado**

- Layer 1: rejeição de outlier (delta > `filter_outlier_cm`)
- Layer 2: média móvel (janela `filter_window`)
- Layer 3: threshold de envio (`filter_threshold_cm`) + envio forçado + heartbeat

Pendente:
- [ ] Validar com sensor real em superfície de água

---

### Fase 4 — Gateway USB + JSON Serial
**Status: ✅ Validado em hardware**

- `firmware/gateway/src/main.cpp` — recebe ESP-NOW, serializa JSON, parseia comandos
- `firmware/gateway/src/espnow_gw.cpp` — CRC verify, cache de MACs por node_id
- Tempo: bridge.py envia `{"cmd":"SETTIME","ts":...}` no startup
- Observabilidade: `GATEWAY_READY`, `GATEWAY_STATUS`, `CMD_ACK`

Pendente:
- [ ] Implementar configuração estendida item-a-item no node/gateway
- [ ] Decidir se cache MAC continuará existindo ou será removido

---

### Fase 5 — bridge.py + MQTT + HA Discovery
**Status: ✅ Validado em hardware**

- `tools/bridge.py` — lê serial, calcula level/volume, publica MQTT, HA Discovery
- `tools/reservoirs.yaml` — parâmetros dos 5 nodes CMASM
- `tools/nvs_tool.py` — CLI para enviar CONFIG/RESTART via gateway
- Publica `aguada/gateway/status`, `aguada/gateway/health`, `aguada/gateway/ack`
- Publica MQTT Discovery do gateway USB (online + sensores diagnósticos)

Pendente:
- [ ] Ajustar Callback API do Paho MQTT para eliminar deprecation warning
- [ ] Publicar/consumir ACK consolidado quando a configuração estendida for implementada

---

### Fase 6 — CMD_CONFIG via ESP-NOW
**Status: 🟠 Parcial**

Gateway envia `PKT_CMD_CONFIG` com `FLAG_CONFIG_PENDING`. Hoje o fluxo suporta apenas `num_sensors` e parâmetros de bateria compactados no pacote de 16 bytes.

Direção aprovada para evolução:
- manter `espnow_packet_t` em 16 bytes
- transportar configuração estendida item-a-item usando:
	- `vbat` → `config_group`
	- `reserved` → `config_item`
	- `distance_cm` → `config_value_u16`
	- `seq` → transação
	- `flags` → controle/ACK

Pendente:
- [x] Definir mapeamento de grupos/itens/ACK no protocolo compartilhado
- [ ] Implementar encoder no bridge/gateway
- [ ] Implementar staging + commit no node
- [ ] Consolidar ACK final de transação

---

### Fase 7 — Mesh Relay + Tabela de Vizinhos
**Status: ✅ Escrito** — não testado

- `mesh.cpp`: atualiza vizinhos ao receber qualquer pacote, expira por timeout
- Node em modo relay (`num_sensors=0`) retransmite com TTL decrement + dedup por seq
- Score: `rssi - hops_to_gw × 10`

Pendente:
- [ ] Testar topologia CMASM com 2+ nodes

---

### Fase 8 — OTA via ESP-NOW
**Status: ⬜ Não iniciado**

Protocolo definido no spec (PKT_OTA_BLOCK, PKT_OTA_END + SHA-256).
Partições `app0`/`app1` já configuradas em `partitions.csv`.

---

### Fase 9 — Deep Sleep (bateria)
**Status: ⬜ Não iniciado**

Incompatível com modo relay. NVS flag `deep_sleep_enabled`.

---

### Fase 10 — Balanço Hídrico + Dashboard HA
**Status: 🟠 Parcial / repriorizada**

Já existe uma base relevante em `homeassistant/`:

- `dashboard.yaml` com múltiplas views (visão geral, consumo, vazamentos, castelos, bombas, cisternas, sistema, mobile)
- `template_sensors.yaml` com agregados, consumo 24h, taxa de variação, médias e alarmes
- `statistics_sensors.yaml` com min/max 24h, taxa em janela e médias 7d
- `automations.yaml` com alertas de nível, gateway, vazamento e relatório diário

O foco agora deixa de ser “criar dashboard” e passa a ser **segunda geração operacional**:

1. **Melhorar UX das telas do HA**
	- cards mais operacionais para celular e desktop
	- separar visão executiva, operação diária e diagnóstico técnico
	- destacar anomalias, recarga, consumo e intervenções manuais sem poluir a tela principal

2. **Melhorar o cálculo do balanço hídrico**
	- sair do modelo simplificado `max(24h) - min(24h)` como proxy universal
	- introduzir janelas fixas de operação (ex.: 06h/18h) e/ou balanço por turno
	- separar melhor: consumo, recarga, transferência interna e perda suspeita
	- tratar ruído/reabastecimento para não confundir enchimento com “consumo do dia”

3. **Permitir entrada de dados por usuários/operadores**
	- helpers do HA para observações, eventos operacionais e ajustes de contexto
	- registrar intervenções como limpeza, manutenção, recarga externa, bomba ligada/desligada, inspeção de vazamento
	- usar esses inputs para contextualizar o balanço e reduzir falso positivo operacional

Gaps atuais identificados:

- o dashboard já existe, mas ainda está mais “telemetria técnica” do que “centro operacional”
- o sensor `consumo_24h` hoje mede essencialmente **amplitude diária** (`max - min`), o que não equivale sempre a consumo líquido
- a detecção de vazamento usa limiar fixo sobre `change_second`, sem contexto operacional manual

Primeiro incremento já implementado nesta fase:

- `input_boolean.yaml`, `input_select.yaml`, `input_text.yaml`, `input_number.yaml` adicionados em `homeassistant/`
- `configuration.yaml` atualizado para incluir helpers operacionais
- `statistics_sensors.yaml` ganhou sensores de **saldo líquido** (`change`) em 12h e 24h por reservatório
- `template_sensors.yaml` ganhou agregados de saldo e contexto operacional
- `dashboard.yaml` ganhou a view **Operação** para contexto manual + balanço

Pendente:
- [ ] Redesenhar a view principal com foco operacional
- [x] Criar primeira view específica de operação/balanço
- [ ] Definir fórmula-alvo do balanço (consumo, recarga, transferência, perda)
- [x] Criar helpers para entrada manual do operador
- [ ] Integrar eventos manuais às automações e ao dashboard

---

### Fase 11 — PoC ESPHome (avaliação de migração)
**Status: 🟠 Planejado**

Objetivo: decidir com evidências se vale migrar parte do sistema para ESPHome sem perder robustez da malha ESP-NOW.

Escopo do PoC (2 trilhas):
- **Trilha A (híbrida, recomendada):** manter node/gateway/bridge atuais e integrar ESPHome via MQTT/HA para controle/UX.
- **Trilha B (experimental):** 1 nó com ESPHome (Wi-Fi + OTA + deep sleep + sensor ultrassônico) para comparação direta.

Métricas de comparação (coletar por no mínimo 72h):
- Confiabilidade de telemetria: `% de mensagens recebidas` e gaps > 2× intervalo nominal.
- Consumo energético: estimativa de autonomia por bateria (mesma célula e duty-cycle).
- Latência ponta a ponta: medição → entidade HA atualizada.
- Estabilidade OTA: taxa de sucesso e tempo médio de atualização.
- Manutenção: tempo para configurar novo nó e tempo de troubleshooting.

Critério de decisão (Go/No-Go):
- **Go parcial (adoção híbrida):** se ESPHome reduzir esforço operacional sem piorar confiabilidade (>98% entrega) nem autonomia de forma relevante.
- **No-Go para migração total:** se mesh/relay/consumo ficarem piores que o stack atual ESP-NOW.

Entregáveis:
- Relatório curto com tabela comparativa A vs B.
- Recomendação final: manter atual, híbrido, ou plano de migração por fases.
- Lista de riscos (especialmente ESP-NOW mesh, OTA e deep sleep simultâneos).

---

## Próximas Ações Imediatas

1. **Redefinir a Fase 10 no HA** — telas operacionais + cálculo de balanço + helpers de entrada manual
2. **Implementar CFG_GROUP/CFG_ITEM no bridge/gateway/node**
3. **Testar transação CONFIG item-a-item em um node real**
4. **Decidir limpeza final de legados Home Assistant (`mqtt_*_sensors.yaml`)**
5. **Iniciar PoC ESPHome (trilha A)** — criar 1 device ESPHome para consumir/publicar MQTT `aguada/...`

---

## Notas de Arquitetura

- `AGUADA_SYSTEM_DOC.md` é o spec canônico — não alterar comportamento sem refletir lá
- Parâmetros de reservatório **nunca** vão para o node — ficam em `reservoirs.yaml`
- node_id = 2 últimos bytes do MAC — sem cadastro manual
- diretórios `backup_*` são snapshots locais e não devem mais participar do fluxo normal de desenvolvimento

---

## Problemas Conhecidos / Decisões Pendentes

| # | Descrição | Decisão pendente |
|---|-----------|-----------------|
| 1 | CMD_CONFIG full transfer | Protocolo extendido ou chunk via PKT_OTA_BLOCK? |
| 2 | Gateway timestamp sem NTP | Atual: bridge.py envia SETTIME. OK para produção? |
| 3 | node/src/neighbor_table.h era skeleton | Removido para .delete — substituído por mesh.cpp |
| 4 | Balanço hídrico diário | Manter `max-min 24h` como métrica auxiliar e criar balanço por turno/janela fixa? |
| 5 | Entrada manual no HA | Quais eventos/ajustes o operador deve poder registrar na UI? |
