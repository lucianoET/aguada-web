# 🔧 Guia de Calibração - AGUADA

## Calibração de Sensores Ultrassônicos

### Procedimento Básico

1. **Preparar o ambiente**
   - Limpe o sensor com pano úmido
   - Remova qualquer obstrução
   - Aguarde 5 minutos para estabilização

2. **Medir referência**
   - Meça manualmente a distância com fita métrica
   - Registre em cm com 1 casa decimal
   - Exemplo: 245.8 cm

3. **Verificar leitura do sensor**
   - Acesse: `http://192.168.0.100:3000/api/latest/{sensor_id}`
   - Compare valor (em cm × 100) com medida real
   - Exemplo: JSON retorna `"distance_cm": 24580` = 245.80 cm

4. **Calcular erro**
   - Erro = Leitura - Referência
   - Tolerância: ±2 cm

### Calibração por Sensor

#### RCON (Altura: 400 cm)
- Altura máxima esperada: 400 cm
- Erro máximo aceitável: ±2 cm
- Intervalo válido: 20-450 cm

#### RCAV (Altura: 350 cm)
- Altura máxima esperada: 350 cm
- Erro máximo aceitável: ±2 cm
- Intervalo válido: 20-450 cm

#### RB03 (Altura: 280 cm)
- Altura máxima esperada: 280 cm
- Erro máximo aceitável: ±2 cm
- Intervalo válido: 20-450 cm

#### IE01 (Altura: 120 cm)
- Altura máxima esperada: 120 cm
- Erro máximo aceitável: ±2 cm
- Intervalo válido: 20-450 cm

#### IE02 (Altura: 150 cm)
- Altura máxima esperada: 150 cm
- Erro máximo aceitável: ±2 cm
- Intervalo válido: 20-450 cm

## Calibração de Válvulas

### Teste de Estado

1. Acione manualmente a válvula
2. Verifique se o sensor registra a mudança (0 ou 1)
3. Aguarde até 30 segundos pelo heartbeat

### Se não houver detecção:

```bash
# Verificar GPIO
esp_idf_2>/dev/ttyACM0 # Abrir monitor serial

# Testar pino manualmente
gpio_get_level(VALVE_IN_PIN)
```

## Calibração de Fluxo (Sound-in)

1. Abra a válvula de entrada
2. Verifique se `sound_in` muda para 1
3. Feche a válvula - deve retornar para 0

### Se houver ruído:

- Aumentar threshold de detecção em config.h
- Recompilar firmware
- Reflashar ESP32

## Teste de Bateria

```bash
# Verificar voltagem (deve estar ~5000 mV)
curl http://192.168.0.100:3000/api/latest/RCON | jq .battery

# Se abaixo de 4800 mV: possível problema de alimentação
```

---
*Versão 1.0 - 17 de novembro de 2025*
