# 🛠️ Manutenção Preventiva - AGUADA

## Checklist Semanal

- [ ] Verificar se todos os 5 sensores estão online
- [ ] Confirmar que dados estão sendo atualizados
- [ ] Revisar alertas críticos
- [ ] Verificar espaço em disco (deve estar > 20% livre)
- [ ] Testar conexão WiFi do gateway

## Checklist Mensal

- [ ] Limpeza física dos sensores ultrassônicos
- [ ] Teste de backups
- [ ] Revisão de logs de erro
- [ ] Verificação de integridade de dados
- [ ] Teste de failover

### Limpeza dos Sensores

1. **Desativar coleta** (opcional):
   ```bash
   docker-compose pause backend
   ```

2. **Limpar sensor com pano úmido**
   - Não use abrasivos
   - Evite água em excesso
   - Seque completamente

3. **Aguardar 5 minutos** para estabilização

4. **Executar calibração** (ver guide de calibração)

5. **Reativar coleta**:
   ```bash
   docker-compose unpause backend
   ```

## Checklist Trimestral

- [ ] Backup completo do banco de dados
- [ ] Limpeza de dados antigos (> 90 dias)
- [ ] Atualização de firmware (se disponível)
- [ ] Revisão de performance
- [ ] Teste de recuperação de desastre

### Backup Completo

```bash
# Criar backup
bash scripts/migration.sh

# Selecionar opção 1: "Backup local do banco de dados"
```

### Limpeza de Dados Antigos

```sql
-- Manter últimos 90 dias apenas
DELETE FROM leituras_raw 
WHERE datetime < NOW() - INTERVAL '90 days';

-- Verificar espaço liberado
VACUUM ANALYZE leituras_raw;
```

## Monitoramento de Performance

### Verificar Espaço em Disco

```bash
df -h
# Crítico: < 10% livre
# Alerta: < 20% livre
```

### Verificar Uso de Memória

```bash
docker stats aguada-backend
docker stats aguada-postgres
```

### Verificar Taxa de Dados

```sql
SELECT 
  DATE_TRUNC('hour', datetime) as hora,
  COUNT(*) as total_readings
FROM leituras_raw
WHERE datetime > NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', datetime)
ORDER BY hora DESC;
```

## Procedimentos de Restauração

### Restaurar Backup

```bash
bash scripts/migration.sh
# Selecionar opção 2: "Restaurar backup"
```

### Verificar Integridade do Banco

```sql
-- Verificar tabelas
SELECT schemaname, tablename 
FROM pg_tables 
WHERE schemaname = 'public';

-- Verificar índices
SELECT indexname FROM pg_indexes 
WHERE schemaname = 'public';
```

## Log de Manutenção

Use este template para registrar intervenções:

```
Data: ___/___/______
Tipo: [ ] Limpeza [ ] Calibração [ ] Backup [ ] Reparo [ ] Outro: _______
Sensor(es): RCON / RCAV / RB03 / IE01 / IE02
Descrição: ___________________________________________
Resultado: [ ] OK [ ] FALHA
Próximos passos: ________________________________________
```

---
*Versão 1.0 - 17 de novembro de 2025*
