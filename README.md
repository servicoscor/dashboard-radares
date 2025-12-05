# 🌧️ Radar Nowcast - COR Rio

Sistema de visualização e análise de tendência de chuva em tempo real para o Centro de Operações Rio.

![Status](https://img.shields.io/badge/status-produção-green)
![Version](https://img.shields.io/badge/version-2.3.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-yellow)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 📋 Índice

- [Sobre o Projeto](#-sobre-o-projeto)
- [Funcionalidades](#-funcionalidades)
- [Arquitetura](#-arquitetura)
- [Tecnologias](#-tecnologias)
- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [API Reference](#-api-reference)
- [Segurança](#-segurança)
- [Estrutura de Arquivos](#-estrutura-de-arquivos)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)
- [Contribuição](#-contribuição)

---

## 🎯 Sobre o Projeto

O **Radar Nowcast** é uma plataforma web desenvolvida para o Centro de Operações Rio (COR) que integra múltiplas fontes de dados de radar meteorológico, permitindo a visualização em tempo real da movimentação de chuvas na região metropolitana do Rio de Janeiro.

### Objetivos

- Centralizar a visualização de dados de múltiplos radares meteorológicos
- Fornecer análise automática de núcleos de chuva com direção e velocidade
- Permitir exportação de animações para relatórios e comunicação
- Oferecer interface intuitiva para operadores do COR

---

## ✨ Funcionalidades

### Radares Integrados

| Radar | Fonte | Cobertura | Método |
|-------|-------|-----------|--------|
| **Mendanha** | INEA (FTP) | Região Metropolitana RJ | API com filtro de chuva |
| **Sumaré** | AlertaRio | Cidade do Rio de Janeiro | API proxy |
| **Niterói** | Defesa Civil Niterói | Niterói e região | Iframe integrado |

### Recursos Principais

- 🎬 **Animação Suave** - Pré-carregamento de frames para reprodução fluida
- 🧭 **Setas de Direção** - Análise automática de movimento dos núcleos de chuva
- 📊 **Detecção de Núcleos** - Identificação e classificação por intensidade (mm/h)
- 🌧️ **Filtro de Chuva** - Remove umidade (azul) e mostra apenas precipitação real
- 🌙 **Modo Escuro/Claro** - Tema com paleta oficial da Prefeitura do Rio
- 🗺️ **5 Tipos de Mapa** - Escuro, Claro, Ruas, Satélite, Topográfico
- 📥 **Exportação GIF** - Download de animações para compartilhamento
- ⛶ **Modo Fullscreen** - Visualização expandida sem sidebar
- 📱 **Página Mosaico** - 3 radares simultâneos com layouts configuráveis
- 🔄 **Auto-refresh** - Atualização automática a cada 2 minutos
- 🧹 **Limpeza Automática** - Remoção de arquivos com mais de 24h
- 📱 **Design Responsivo** - Funciona em desktop, tablet e celular

### Layouts do Mosaico

```
Layout 1: [1][2][3]     Layout 2: [  1  ]     Layout 3: [1][2]     Layout 4: [1][2]
          3 colunas               [2][3]                [  3  ]              [1][3]
```

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTE (Browser)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  index.html │  │ mosaic.html │  │   Leaflet   │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         NGINX (Proxy)                            │
│                    http://35.225.221.88                          │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK + GUNICORN (:5000)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  API REST   │  │ Rate Limit  │  │   Auth      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
          │                               │
          ▼                               ▼
┌──────────────────┐            ┌──────────────────┐
│   FTP INEA       │            │   AlertaRio API  │
│   (Mendanha)     │            │   (Sumaré)       │
│  82.180.153.43   │            │  alertario.rio   │
└──────────────────┘            └──────────────────┘
```

### Fluxo de Dados

1. **Sincronização (Background Thread)**
   - A cada 2 minutos, o backend baixa novos frames
   - Mendanha: FTP do INEA (20 arquivos mais recentes)
   - Sumaré: HTTP do AlertaRio (20 frames fixos)

2. **Requisição do Cliente**
   - Frontend solicita lista de frames disponíveis
   - Pré-carrega todas as imagens antes de animar
   - Alterna opacidade dos overlays (sem recarregar)

3. **Análise de Núcleos**
   - Canvas analisa pixels de cada frame
   - Detecta clusters de cores (intensidade dBZ)
   - Calcula movimento entre frames consecutivos
   - Desenha setas indicando direção e velocidade

---

## 🛠️ Tecnologias

### Backend
- **Python 3.11+** - Linguagem principal
- **Flask** - Framework web
- **Gunicorn** - WSGI HTTP Server (produção)
- **Flask-CORS** - Cross-Origin Resource Sharing
- **Pillow** - Processamento de imagens (GIF)
- **NumPy** - Processamento de arrays (filtro de chuva)
- **Requests** - Cliente HTTP

### Frontend
- **HTML5 / CSS3 / JavaScript** - Base
- **Leaflet.js** - Mapas interativos
- **Canvas API** - Análise de imagens

### Infraestrutura
- **Google Cloud Platform** - VM Compute Engine
- **Ubuntu 24.04** - Sistema Operacional
- **Nginx** - Reverse Proxy
- **Supervisor** - Gerenciador de processos
- **Git/GitHub** - Versionamento

---

## 📦 Requisitos

### Sistema
- Ubuntu 20.04+ ou Debian 11+
- Python 3.11+
- Nginx
- Supervisor
- 1GB RAM mínimo
- 10GB disco

### Acesso
- Credenciais FTP INEA (Mendanha)
- Acesso à internet (AlertaRio)

---

## 🚀 Instalação

### 1. Clonar Repositório

```bash
cd /var/www
sudo git clone https://github.com/servicoscor/dashboard-radares.git radar-nowcast
cd radar-nowcast
```

### 2. Criar Ambiente Virtual

```bash
sudo python3 -m venv venv
sudo venv/bin/pip install --upgrade pip
sudo venv/bin/pip install flask flask-cors requests pillow gunicorn numpy
```

### 3. Criar Diretórios

```bash
sudo mkdir -p cache/mendanha cache/sumare cache/exports
sudo mkdir -p /var/log/radar-nowcast
sudo chown -R www-data:www-data /var/www/radar-nowcast
sudo chown -R www-data:www-data /var/log/radar-nowcast
```

### 4. Configurar Supervisor

```bash
sudo nano /etc/supervisor/conf.d/radar-nowcast.conf
```

```ini
[program:radar-nowcast]
directory=/var/www/radar-nowcast
command=/var/www/radar-nowcast/venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 server:app
user=www-data
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/radar-nowcast/error.log
stdout_logfile=/var/log/radar-nowcast/access.log
environment=
    FTP_HOST="82.180.153.43",
    FTP_USER="seu_usuario",
    FTP_PASSWORD="sua_senha",
    ADMIN_TOKEN="seu_token_seguro"
```

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start radar-nowcast
```

### 5. Configurar Nginx

```bash
sudo nano /etc/nginx/sites-available/radar-nowcast
```

```nginx
server {
    listen 80;
    server_name seu-dominio.com.br;

    root /var/www/radar-nowcast;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/radar-nowcast /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## ⚙️ Configuração

### Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `FTP_HOST` | IP do servidor FTP INEA | Sim |
| `FTP_USER` | Usuário FTP | Sim |
| `FTP_PASSWORD` | Senha FTP | Sim |
| `ADMIN_TOKEN` | Token para endpoints admin | Sim |

### Gerar Token Seguro

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📡 API Reference

### Endpoints Públicos

#### Listar Frames

```http
GET /api/frames/mendanha
GET /api/frames/sumare
```

**Resposta:**
```json
{
  "frames": ["MDN-20251203-1200.png", "MDN-20251203-1150.png"],
  "count": 20
}
```

#### Obter Frame

```http
GET /api/frame/mendanha/{filename}
GET /api/frame/mendanha/{filename}?filter=rain
GET /api/frame/sumare/{filename}
```

**Parâmetros Query:**
- `filter=rain` - Remove pixels de umidade (azul), mostrando apenas precipitação real (apenas Mendanha)

**Resposta:** Imagem PNG

#### Exportar GIF

```http
GET /api/export/gif/{radar}
```

**Parâmetros:** `radar` = `mendanha` ou `sumare`

**Resposta:** Arquivo GIF animado

**Rate Limit:** 5 requisições/minuto

#### Status

```http
GET /api/status
```

**Resposta:**
```json
{
  "mendanha": {"files_count": 20, "last_sync": "2025-12-03T22:32:56"},
  "sumare": {"files_count": 20, "last_sync": "2025-12-03T22:33:01"},
  "status": "ok"
}
```

### Endpoints Administrativos

Requerem header `X-Admin-Token` ou query param `?token=`

#### Sync Manual

```http
GET /api/sync/mendanha?token=SEU_TOKEN
GET /api/sync/sumare?token=SEU_TOKEN
```

#### Status Detalhado

```http
GET /api/admin/status?token=SEU_TOKEN
```

---

## 🔒 Segurança

### Medidas Implementadas

| Proteção | Descrição |
|----------|-----------|
| **Path Traversal** | Validação e sanitização de nomes de arquivo |
| **Rate Limiting** | Limite de requisições por IP (100/min geral, 5/min GIF) |
| **CORS Restrito** | Apenas domínios autorizados |
| **Token Admin** | Endpoints sensíveis protegidos |
| **Credenciais** | Via variáveis de ambiente (não no código) |
| **Gunicorn** | Servidor de produção (sem debug) |

### Recomendações

1. **Alterar token padrão** antes de publicar
2. **Configurar HTTPS** com Let's Encrypt
3. **Firewall** - Liberar apenas portas 80/443
4. **Trocar senha FTP** periodicamente
5. **Monitorar logs** em `/var/log/radar-nowcast/`

---

## 📁 Estrutura de Arquivos

```
/var/www/radar-nowcast/
├── index.html          # Página principal
├── mosaic.html         # Página mosaico (3 radares)
├── server.py           # Backend Flask
├── logo-cor.png        # Logo COR Rio (modo escuro)
├── logo-cor-azul.png   # Logo COR Rio (modo claro)
├── venv/               # Ambiente virtual Python
├── cache/
│   ├── mendanha/       # Frames do radar Mendanha
│   ├── sumare/         # Frames do radar Sumaré
│   └── exports/        # GIFs temporários
└── README.md           # Documentação
```

---

## 🔧 Troubleshooting

### Backend não inicia

```bash
# Verificar logs
sudo tail -f /var/log/radar-nowcast/error.log

# Verificar status
sudo supervisorctl status radar-nowcast

# Reiniciar
sudo supervisorctl restart radar-nowcast
```

### Frames não carregam

```bash
# Verificar se há arquivos
ls -la /var/www/radar-nowcast/cache/mendanha/

# Forçar sync manual
curl "http://localhost:5000/api/sync/mendanha?token=SEU_TOKEN"
```

### Erro de permissão

```bash
sudo chown -R www-data:www-data /var/www/radar-nowcast
```

### FTP não conecta

```bash
# Testar conexão manualmente
ftp 82.180.153.43
```

### Nginx 502 Bad Gateway

```bash
# Verificar se Flask está rodando
sudo supervisorctl status radar-nowcast

# Verificar porta
curl http://localhost:5000/api/status
```

---

## 🗺️ Roadmap

- [x] Radar Mendanha (INEA)
- [x] Radar Sumaré (AlertaRio)
- [x] Radar Niterói (Defesa Civil)
- [x] Detecção de núcleos com setas
- [x] Exportação GIF
- [x] Modo fullscreen
- [x] Página mosaico
- [x] Correções de segurança
- [x] Filtro de chuva (remove umidade)
- [x] Modo escuro/claro
- [x] Paleta oficial Prefeitura Rio
- [x] Design responsivo (mobile)
- [ ] SSL/HTTPS (Let's Encrypt)
- [ ] Histórico de eventos
- [ ] Alertas automáticos
- [ ] Integração com Telegram/WhatsApp
- [ ] Dashboard de métricas

---

## 👥 Contribuição

1. Fork o projeto
2. Crie sua branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

---

## 📄 Licença

Este projeto é de uso interno do Centro de Operações Rio (COR).

---

## 📞 Contato

**Centro de Operações Rio**
- Website: [cor.rio](https://cor.rio)
- Dashboard: [dashboardradar.cor.rio](https://dashboardradar.cor.rio)
- GitHub: [@servicoscor](https://github.com/servicoscor)

---

<p align="center">
  Desenvolvido com ☁️ para o <strong>Centro de Operações Rio</strong>
</p>
