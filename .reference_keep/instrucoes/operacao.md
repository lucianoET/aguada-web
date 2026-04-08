# 📖 Manual de Operação - AGUADA

## Inicialização do Sistema

### Startup Padrão

```bash
# 1. Verificar status dos containers
docker ps

# 2. Se não estiver rodando, iniciar
docker-compose -f docker-compose.yml up -d

# 3. Verificar logs
docker-compose logs -f backend
```

### Painel de Controle

1. Acesse: `http://192.168.0.100:3000`
2. Use credenciais (se necessário): admin/admin123
3. Aguarde 30 segundos para os dados começarem a aparecer

## Monitoramento em Tempo Real

### Dashboard Principal (`/index.html`)
- Visualiza os 5 reservatórios em tempo real
- Atualiza a cada 10 segundos
- Cores: Verde (bom), Amarelo (aviso), Vermelho (crítico)

### Histórico (`/history.html`)
- Filtrar por sensor e período
- Gráficos de tendência
- Export para CSV

### Alertas (`/alerts.html`)
- Lista de eventos críticos
- Histórico de notificações
- Ações manuais

## Operações Comuns

### Pausar Coleta de Dados

```bash
docker-compose pause backend
```

### Reiniciar o Sistema

```bash
docker-compose restart
```

### Acessar Banco de Dados

```bash
docker exec -it aguada-postgres psql -U aguada -d aguada
```

### Ver Dados Brutos

```sql
SELECT * FROM leituras_raw 
ORDER BY datetime DESC 
LIMIT 100;
```

## Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Dashboard não carrega | Verificar se backend está rodando: `docker ps` |
| Sensores offline | Verificar conexão WiFi do gateway |
| Dados desatualizados | Reiniciar containers: `docker-compose restart` |
| Banco de dados cheio | Executar limpeza: `psql -f scripts/cleanup.sql` |

---
*Versão 1.0 - 17 de novembro de 2025*
