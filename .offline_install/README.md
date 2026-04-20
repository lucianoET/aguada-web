# Aguada Web Offline Bundle

Esta pasta existe para preparar uma instalação em host com internet lenta ou instável.

## Estado atual do sistema

O Aguada Web está apto a rodar sem internet durante a operação, desde que o host já tenha:

- Docker instalado
- imagens Docker necessárias já carregadas
- workspace copiado com `frontend/`, `backend/`, `tools/`, `data/` e `.env`

O runtime da aplicação não depende de CDN nem de APIs externas de internet. Os assets do frontend já estão locais no repositório.

## O que copiar para o pendrive

- todo o workspace do Aguada Web
- esta pasta `.offline_install/`
- o diretório `data/` com o banco e os PDFs
- os arquivos `.tar` de imagens Docker gerados em `.offline_install/images/`

## Caminho recomendado

1. Na máquina atual com internet estável e Docker funcional, execute `./.offline_install/prepare_offline_bundle.sh`.
2. Copie o workspace inteiro para o pendrive.
3. Na máquina host, copie a pasta para o disco.
4. Ajuste o `.env` local com base em `.offline_install/cmasm.env.example`.
5. Execute `./.offline_install/install_offline_host.sh`.

## Importante

Não copie containers Docker como estratégia principal.

Use:

- `docker save` / `docker load` para imagens
- cópia do workspace para bind mounts
- cópia do diretório `data/` para persistência

No compose atual, o dado persistente principal já está no workspace em `data/`, então copiar essa pasta é suficiente para preservar o banco local.

## Arquivos desta pasta

- `docker-compose.offline.yml` — compose offline usando imagem do app pré-buildada
- `prepare_offline_bundle.sh` — gera backup e exporta imagens Docker
- `install_offline_host.sh` — carrega imagens e sobe a stack no host offline
- `cmasm.env.example` — modelo local para a instalação CMASM
- `wheels/` — wheelhouse Python para contingência sem Docker
- `images/` — destino dos `.tar` de imagens Docker
- `backups/` — destino de backups do diretório `data/`