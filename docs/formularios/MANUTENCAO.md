---
title: Formulário de Manutenção Preventiva
month: _____________
year: _____________
---

# FORMULÁRIO DE MANUTENÇÃO PREVENTIVA

## Informações Gerais

| Campo | Valor |
|-------|-------|
| Período | ___/___/______ a ___/___/______ |
| Responsável | _________________________ |
| Tipo Manutenção | [ ] Semanal [ ] Mensal [ ] Trimestral |

## Checklist de Verificação

### Sensores e Hardware

- [ ] RCON online e respondendo
- [ ] RCAV online e respondendo
- [ ] RB03 online e respondendo
- [ ] IE01 online e respondendo
- [ ] IE02 online e respondendo
- [ ] Gateway conectado ao WiFi
- [ ] LED gateway: Verde piscando
- [ ] Alimentação: 5V confirmado

### Sistema Backend

- [ ] Todos os containers rodando (`docker ps`)
- [ ] Backend respondendo: `curl http://localhost:3000/health`
- [ ] PostgreSQL conectando
- [ ] Redis respondendo
- [ ] Nginx servindo frontend

### Dados e Coleta

- [ ] Dashboard mostrando dados atualizados
- [ ] Nenhuma lacuna de > 1 hora em dados
- [ ] Últimas leituras de todos os sensores < 5 min
- [ ] Nenhum alerta crítico ativo
- [ ] Histórico carregando corretamente

### Espaço e Performance

- [ ] Espaço em disco: ___% (Mínimo 20% livre)
- [ ] Memória RAM: ___% (Máximo 80%)
- [ ] CPU: ___% (Máximo 70%)
- [ ] Banco de dados: ___MB (Máximo 10GB)

## Limpeza Física

- [ ] Sensor RCON limpo e seco
- [ ] Sensor RCAV limpo e seco
- [ ] Sensor RB03 limpo e seco
- [ ] Sensor IE01 limpo e seco
- [ ] Sensor IE02 limpo e seco
- [ ] Gateway verificado visualmente

**Observações sobre limpeza:** ___________________________________

## Testes Funcionais

### Teste de Válvulas

| Sensor | Entrada OK | Saída OK | Observações |
|--------|-----------|---------|-------------|
| RCON | [ ] ✓ [ ] ✗ | [ ] ✓ [ ] ✗ | _____________ |
| RCAV | [ ] ✓ [ ] ✗ | [ ] ✓ [ ] ✗ | _____________ |
| RB03 | [ ] ✓ [ ] ✗ | [ ] ✓ [ ] ✗ | _____________ |
| IE01 | [ ] ✓ [ ] ✗ | [ ] ✓ [ ] ✗ | _____________ |
| IE02 | [ ] ✓ [ ] ✗ | [ ] ✓ [ ] ✗ | _____________ |

### Teste de Fluxo

| Sensor | Fluxo Detectado | Status |
|--------|-----------------|--------|
| RCON | [ ] Sim [ ] Não | [ ] OK [ ] ❌ |
| RCAV | [ ] Sim [ ] Não | [ ] OK [ ] ❌ |
| RB03 | [ ] Sim [ ] Não | [ ] OK [ ] ❌ |
| IE01 | [ ] Sim [ ] Não | [ ] OK [ ] ❌ |
| IE02 | [ ] Sim [ ] Não | [ ] OK [ ] ❌ |

## Backup e Segurança

- [ ] Backup realizado com sucesso
- [ ] Arquivo de backup testado
- [ ] Arquivo de backup armazenado em local seguro
- [ ] Credenciais verificadas
- [ ] Permissões de acesso revisadas

**Local do backup:** ________________________________________

## Problemas Identificados

| Problema | Severidade | Ação | Responsável | Prazo |
|----------|-----------|------|-------------|-------|
| _________ | [ ] Alta [ ] Média [ ] Baixa | _____ | _________ | ___/___/__ |
| _________ | [ ] Alta [ ] Média [ ] Baixa | _____ | _________ | ___/___/__ |
| _________ | [ ] Alta [ ] Média [ ] Baixa | _____ | _________ | ___/___/__ |

## Resumo Executivo

**Status Geral:** [ ] OPERACIONAL [ ] COM RESTRIÇÕES [ ] CRÍTICO

**Taxa de Disponibilidade:** _____%

**Leituras Coletadas Este Período:** ___________

**Próxima Manutenção Programada:** ___/___/______

**Observações Finais:** ________________________________________

---

**Responsável:** _________________________ **Data:** ___/___/______

**Supervisor:** _________________________ **Assinado:** [ ]

---
*Este formulário deve ser arquivado para referência histórica*
