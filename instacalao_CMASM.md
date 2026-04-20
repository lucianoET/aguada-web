# Instalação CMASM

Guia de implantação do Aguada Web no local real da CMASM.

## Parâmetros definidos para a instalação

- Servidor Aguada Web: `192.168.10.141`
- AP WiFi: `192.168.10.201`
- Rede sugerida: `192.168.10.0/24`
- HTTP do sistema: `80`
- MQTT do broker: `1883`
- Senha do WiFi: manter a mesma já utilizada hoje

## O que precisa ser alterado

### 1. No servidor Aguada Web

O servidor precisa ter IP fixo `192.168.10.141`.

O sistema Aguada Web não precisa gravar o IP do AP. O que importa para o software é:

- a máquina ficar acessível na LAN
- a porta `80` servir o frontend
- a porta `1883` aceitar a conexão MQTT do gateway

### 2. No AP WiFi

O AP deve ser configurado com IP de gerenciamento `192.168.10.201`.

Checklist do AP:

- SSID igual ao esperado pelo gateway
- senha igual à já usada no ambiente atual
- canal WiFi estável
- DHCP configurado de forma compatível com a rede local
- não usar faixa que conflite com `192.168.10.141` e `192.168.10.201`

Sugestão de reserva de rede:

- `192.168.10.1` a `192.168.10.99` para infraestrutura fixa
- `192.168.10.100` a `192.168.10.199` para DHCP
- `192.168.10.141` reservado ao servidor Aguada Web
- `192.168.10.201` reservado ao AP

### 3. No gateway/firmware WiFi

O ponto mais importante é o destino MQTT.

O gateway deve publicar no broker MQTT do servidor:

- MQTT host: `192.168.10.141`
- MQTT port: `1883`

O IP `192.168.10.201` do AP não entra como destino MQTT. Ele serve apenas para administração do AP.

## Forma recomendada de instalar

Use a stack Docker padrão do projeto. Ela já sobe:

- broker MQTT
- backend FastAPI
- nginx

## Operação offline

Sim. O sistema pode operar sem internet depois de instalado.

Em operação normal, o Aguada Web depende apenas de:

- rede local entre host, AP e gateway
- broker MQTT local
- backend local
- arquivos estáticos locais do frontend
- banco SQLite local

O frontend da aplicação não depende de CDN externa para funcionar. Os assets JS, CSS e tiles usados pela aplicação já estão no workspace.

O ponto crítico para funcionamento offline não é o código da aplicação, e sim a disponibilidade prévia de:

- imagens Docker
- dependências do host
- configuração local correta

Por isso foi criada a pasta `.offline_install/` no workspace.

### 1. Preparar o servidor Linux

Instalar dependências base:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

Opcional para administração mais simples:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Definir IP fixo do servidor

Configurar a interface de rede do computador servidor para usar `192.168.10.141`.

Isso pode ser feito por Netplan, NetworkManager ou pela interface gráfica do sistema operacional. O importante é que o IP permaneça fixo.

Validar depois:

```bash
ip addr
ping 192.168.10.201
```

### 3. Clonar o repositório

```bash
git clone https://github.com/luctronics-ET/aguada-web.git
cd aguada-web
```

### 4. Criar o `.env` local da instalação

Crie um `.env` local no servidor. Exemplo mínimo:

```env
TZ=America/Sao_Paulo
HTTP_PORT=80
```

Observação importante:

- no modo Docker padrão, o broker MQTT é interno à stack
- por isso o `GW_MQTT_HOST` do backend continua sendo o serviço `mqtt`
- quem precisa apontar para `192.168.10.141` é o gateway WiFi em campo

Se quiser registrar esse contexto no arquivo local sem impacto funcional, pode usar um comentário operacional fora do versionamento, por exemplo:

```env
TZ=America/Sao_Paulo
HTTP_PORT=80

# Referência operacional CMASM
# Servidor: 192.168.10.141
# AP: 192.168.10.201
```

### 5. Subir a stack

```bash
docker compose up -d
```

### 6. Validar a instalação

```bash
docker compose ps
docker compose logs -f app
curl http://127.0.0.1/api/reservoirs
curl http://127.0.0.1/api/gateway
```

Testes esperados na rede:

- navegador em outro computador acessa `http://192.168.10.141/`
- gateway consegue conectar em `192.168.10.141:1883`
- relatórios PDF são gerados normalmente

## Configuração do gateway no local real

Antes da ida a campo, confirmar no gateway:

- SSID correto
- senha correta
- broker MQTT = `192.168.10.141`
- porta MQTT = `1883`
- tópico conforme firmware atual

Se o firmware estiver hoje apontando para outro IP, essa é a alteração principal para a entrada em produção na CMASM.

## Portas que devem estar liberadas

- `80/tcp` — interface web
- `1883/tcp` — MQTT do gateway

Se houver firewall ativo no servidor:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 1883/tcp
```

## Backup antes da ida a campo

Como o banco local deve ser mantido, faça backup do diretório `data/` antes de instalar ou atualizar.

Se a instalação for feita no mesmo repositório já usado hoje:

```bash
tar czf aguada-backup-$(date +%F-%H%M).tar.gz data/
```

Se for uma máquina nova, restaure depois o conteúdo de `data/` para preservar:

- `data/aguada.db`
- `data/reports/`

## Como criar uma versão com essas configurações

Recomendação: não grave IPs operacionais e senha diretamente no código versionado. Faça a release do software e aplique a configuração do local via `.env` e firmware.

### Opção recomendada

1. Deixe o repositório com configuração genérica.
2. Gere uma tag de release do código.
3. No servidor CMASM, crie um `.env` local com os parâmetros de operação.
4. No gateway, configure o broker MQTT para `192.168.10.141`.

Isso evita expor credenciais e permite reaproveitar a mesma release em outros locais.

## Posso copiar volumes, containers e imagens Docker?

### Imagens Docker

Sim. Essa é a abordagem correta para ambiente offline.

Use:

- `docker save` na máquina de origem
- `docker load` na máquina de destino

Na prática, o melhor caminho é copiar as imagens:

- `aguada-web-app:offline`
- `nginx:alpine`
- `eclipse-mosquitto:2`

### Volumes e dados

Sim, mas no seu caso o mais importante nem é volume Docker nomeado.

No compose atual da release, os dados principais ficam em bind mount local:

- `./data:/data`

Isso significa que copiar o workspace com a pasta `data/` já preserva:

- banco SQLite
- PDFs gerados

Ou seja: para a sua instalação, copiar a pasta do projeto é melhor do que tentar migrar containers.

### Containers Docker

Não é a melhor estratégia.

Containers são descartáveis. O ideal é recriá-los no host novo a partir das imagens já carregadas.

Resumo prático:

- copie o workspace
- copie `data/`
- copie imagens Docker exportadas
- no host novo, rode `docker load` e depois `docker compose up -d`

Não use cópia de container como mecanismo principal de migração.

## Bundle offline preparado no projeto

Foi criada a pasta `.offline_install/` com:

- `README.md`
- `docker-compose.offline.yml`
- `prepare_offline_bundle.sh`
- `install_offline_host.sh`
- `cmasm.env.example`
- `wheels/` com dependências Python baixadas
- `backups/data-current.tar.gz`

Uso recomendado:

1. Na máquina atual, com Docker funcional, execute `./.offline_install/prepare_offline_bundle.sh`.
2. Copie o workspace inteiro para o pendrive.
3. No host de destino, copie a pasta para disco.
4. Ajuste o `.env`.
5. Execute `./.offline_install/install_offline_host.sh`.

### Exemplo de processo de release

```bash
git status
git add .
git commit -m "chore: preparar release CMASM"
git tag -a v1.0.0-cmasm -m "Release CMASM"
```

Depois, no servidor de produção:

```bash
git checkout v1.0.0-cmasm
cp .env.example .env
# editar .env conforme o local
docker compose up -d --build
```

### Se quiser uma versão explicitamente identificada como CMASM

Você pode manter um arquivo local não versionado com os dados operacionais do site, por exemplo:

- `.env`
- `CMASM.local.md`

Esses arquivos não devem entrar no Git se contiverem senha ou detalhes sensíveis.

## Checklist final para amanhã

1. Confirmar IP fixo do servidor `192.168.10.141`.
2. Confirmar IP de gerenciamento do AP `192.168.10.201`.
3. Confirmar SSID e senha esperados pelo gateway.
4. Confirmar gateway apontando MQTT para `192.168.10.141:1883`.
5. Fazer backup de `data/` antes de qualquer mudança.
6. Subir `docker compose up -d`.
7. Testar acesso web em `http://192.168.10.141/`.
8. Testar chegada de leituras no painel.
9. Testar geração de PDF do relatório.
10. Registrar qualquer ajuste feito no local.