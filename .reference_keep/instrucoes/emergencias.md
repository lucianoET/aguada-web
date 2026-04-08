# 🚨 Procedimentos de Emergência - AGUADA

## Alerta Crítico: Vazamento Detectado

### RCON com Vazamento

1. **Imediato**
   - ✋ PARAR abastecimento
   - 📞 Contatar operador responsável
   - 🔴 Ativar sirene/alarme

2. **Confirmação**
   ```bash
   # Verificar leitura em tempo real
   curl http://192.168.0.100:3000/api/latest/RCON | jq .
   ```

3. **Ações**
   - Fechar válvula de entrada
   - Inspecionar fisicamente o reservatório
   - Registrar hora e volume perdido

4. **Recuperação**
   - Reparar vazamento
   - Limpar sensores
   - Recalibrar (ver guide de calibração)
   - Reiniciar coleta de dados

## Sensor Offline

### RCAV não responde há > 5 minutos

1. **Verificar conectividade**
   ```bash
   # Ping gateway
   ping 192.168.0.124
   
   # Verificar logs
   docker-compose logs gateway | tail -50
   ```

2. **Reiniciar sensor**
   - Desligar ESP32 por 10 segundos
   - Religar
   - Aguardar 30 segundos

3. **Se persistir**
   - Verificar WiFi do gateway
   - Testar outro sensor próximo
   - Reiniciar gateway

### Gateway completamente offline

1. **Power cycle**
   ```bash
   # Desligar por 30 segundos
   # Religar
   # Aguardar 60 segundos
   ```

2. **Verificar LED**
   - Verde piscando: Normal
   - Vermelho: Erro
   - Apagado: Sem alimentação

3. **Se LED vermelho**
   - Verificar conexão WiFi
   - Reiniciar roteador
   - Reflashar gateway

## Falha do Backend

### Sistema respondendo com erro 500

1. **Restart imediato**
   ```bash
   docker-compose restart backend
   ```

2. **Se continuar**
   ```bash
   # Ver logs
   docker-compose logs backend | tail -100
   
   # Rebuild imagem
   docker-compose build --no-cache backend
   docker-compose up -d backend
   ```

3. **Último recurso**
   ```bash
   # Parar tudo e reconstruir
   docker-compose down
   docker-compose up -d
   ```

## Banco de Dados Corrompido

### Erro ao conectar PostgreSQL

1. **Verificar container**
   ```bash
   docker ps | grep postgres
   # Se não estiver rodando:
   docker-compose up -d postgres
   ```

2. **Executar FSCK**
   ```bash
   docker exec aguada-postgres pg_dump -U aguada aguada > /tmp/backup.sql
   ```

3. **Se FSCK falhar**
   - Restaurar backup anterior
   - Reiniciar container
   - Verificar espaço em disco

## Disco Cheio (< 5% livre)

1. **Identificar espaço**
   ```bash
   du -sh /* | sort -rh
   docker system df
   ```

2. **Limpar dados antigos**
   ```sql
   DELETE FROM leituras_raw 
   WHERE datetime < NOW() - INTERVAL '7 days';
   VACUUM FULL leituras_raw;
   ```

3. **Limpar Docker**
   ```bash
   docker system prune -a
   ```

## Ataque / Acesso Não Autorizado

1. **Isolamento imediato**
   - Desconectar gateway da rede WiFi
   - Parar backend: `docker-compose stop backend`

2. **Investigação**
   ```bash
   # Ver logs de acesso
   docker-compose logs backend | grep "POST\|PUT\|DELETE"
   
   # Verificar atividades anormais
   docker exec aguada-postgres psql -U aguada -c "SELECT * FROM leituras_raw WHERE timestamp > NOW() - INTERVAL '1 hour';"
   ```

3. **Recuperação**
   - Restaurar backup limpo
   - Reiniciar todos os containers
   - Revisar credenciais
   - Reconectar gateway

## Falta de Energia

### Após Retorno da Energia

1. **Aguardar 2 minutos** para estabilização
2. **Iniciar sistema**
   ```bash
   docker-compose up -d
   ```
3. **Verificar status**
   ```bash
   docker ps
   docker-compose logs
   ```

### Para Outages Frequentes

- Instalar UPS (No-Break)
- Configurar auto-restart de containers
- Implementar monitoramento remoto

## Contatos de Emergência

| Papel | Nome | Telefone | Email |
|-------|------|----------|-------|
| Técnico Principal | - | - | - |
| Supervisor | - | - | - |
| Emergência 24/7 | - | - | - |

## Checklist Pós-Emergência

- [ ] Todos os 5 sensores online
- [ ] Dados sendo coletados normalmente
- [ ] Dashboard mostrando valores atuais
- [ ] Nenhum alerta crítico pendente
- [ ] Backup realizado
- [ ] Incidente documentado
- [ ] Causa raiz identificada
- [ ] Plano de prevenção criado

---
*Versão 1.0 - 17 de novembro de 2025*
