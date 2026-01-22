from flask import Flask, jsonify, send_file, Response, request
from flask_cors import CORS
import os
import re
import ftplib
import threading
import time
from datetime import datetime, timedelta
import requests
from io import BytesIO
from functools import wraps
from PIL import Image
import numpy as np

app = Flask(__name__)

# ============================================
# CONFIGURAÇÃO DE SEGURANÇA
# ============================================

# CORS restrito - apenas domínios permitidos
ALLOWED_ORIGINS = [
    'http://35.225.221.88',
    'https://35.225.221.88',
    'http://dashboardradar.cor.rio',
    'https://dashboardradar.cor.rio',
    'http://localhost:5000',
    'http://127.0.0.1:5000'
]
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/*": {"origins": ALLOWED_ORIGINS}
})

# Token para endpoints administrativos (gere um novo com: python -c "import secrets; print(secrets.token_hex(32))")
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'cor_rio_radar_2024_token_seguro')

# Rate limiting simples (em memória)
rate_limit_store = {}
RATE_LIMIT_WINDOW = 60  # segundos
RATE_LIMIT_MAX_REQUESTS = {
    'gif': 10,      # 10 GIFs por minuto
    'sync': 5,      # 5 syncs por minuto
    'default': 500  # 500 requests por minuto (aumentado para DEV)
}

# ============================================
# CONFIGURAÇÃO DE DIRETÓRIOS
# ============================================

CACHE_DIR = os.environ.get('CACHE_DIR', '/var/www/radar-nowcast/cache')
MENDANHA_DIR = os.path.join(CACHE_DIR, 'mendanha')
SUMARE_DIR = os.path.join(CACHE_DIR, 'sumare')
EXPORT_DIR = os.path.join(CACHE_DIR, 'exports')

os.makedirs(MENDANHA_DIR, exist_ok=True)
os.makedirs(SUMARE_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# ============================================
# CREDENCIAIS VIA VARIÁVEIS DE AMBIENTE
# ============================================

FTP_CONFIG = {
    'host': os.environ.get('FTP_HOST', '82.180.153.43'),
    'user': os.environ.get('FTP_USER', 'u109222483.CorInea'),
    'password': os.environ.get('FTP_PASSWORD', ''),  # OBRIGATÓRIO definir via ambiente
    'path': '/',
    'pattern': r'MDN-.*\.png$'
}

# Verificar se a senha foi configurada
if not FTP_CONFIG['password']:
    print("⚠️  AVISO: FTP_PASSWORD não configurada. Defina a variável de ambiente.")

last_sync = {'mendanha': None, 'sumare': None}
MAX_HOURS = 24

# ============================================
# FILTRO DE CORES - REMOVER UMIDADE (AZUL)
# ============================================

def filter_rain_only(image_path):
    """
    Filtra a imagem do radar para mostrar apenas chuva (verde ou mais intenso).
    Remove os tons azuis que representam apenas umidade.
    
    Baseado na legenda oficial:
    - Azul claro/escuro: 0.10 - 1 mm/h (umidade, não chuva)
    - Verde: ~5 mm/h (chuva leve) - MANTER
    - Amarelo/Laranja: 10-100 mm/h (chuva moderada/forte) - MANTER
    - Vermelho/Magenta: >100 mm/h (chuva muito forte) - MANTER
    """
    try:
        img = Image.open(image_path).convert('RGBA')
        data = np.array(img)
        
        # Separar canais
        r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
        
        # Detectar pixels azuis (umidade):
        # - Azul é dominante (B > R e B > G)
        # - Ou tons de ciano/azul claro
        # Tons azuis típicos do radar: RGB aproximados
        # - Azul escuro: ~(0-50, 50-100, 150-255)
        # - Azul claro/ciano: ~(0-100, 100-200, 200-255)
        
        # Criar máscara para pixels azuis (umidade)
        # Pixel é azul se: B > 100 AND B > R AND B >= G
        blue_mask = (b > 100) & (b > r) & (b >= g)
        
        # Também remover ciano claro (onde G e B são altos mas R é baixo)
        cyan_mask = (b > 150) & (g > 150) & (r < 100)
        
        # Combinar máscaras
        remove_mask = blue_mask | cyan_mask
        
        # Tornar pixels azuis transparentes
        data[remove_mask, 3] = 0
        
        # Criar nova imagem
        filtered_img = Image.fromarray(data, 'RGBA')
        
        # Salvar em buffer
        buffer = BytesIO()
        filtered_img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer
    except Exception as e:
        print(f'Erro no filtro de chuva: {e}')
        return None

# ============================================
# FUNÇÕES DE SEGURANÇA
# ============================================

def sanitize_filename(filename):
    """
    Valida e sanitiza o nome do arquivo para prevenir Path Traversal.
    Retorna None se o arquivo for inválido.
    """
    if not filename:
        return None
    
    # Remover qualquer path - pegar apenas o nome do arquivo
    filename = os.path.basename(filename)
    
    # Verificar caracteres permitidos (apenas letras, números, hífen, underscore, ponto)
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', filename):
        return None
    
    # Deve terminar com .png
    if not filename.lower().endswith('.png'):
        return None
    
    # Não permitir .. ou sequências suspeitas
    if '..' in filename or filename.startswith('.'):
        return None
    
    return filename

def rate_limit(limit_type='default'):
    """Decorator para rate limiting"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            key = f"{client_ip}:{limit_type}"
            now = time.time()
            
            # Limpar entradas antigas
            if key in rate_limit_store:
                rate_limit_store[key] = [t for t in rate_limit_store[key] if now - t < RATE_LIMIT_WINDOW]
            else:
                rate_limit_store[key] = []
            
            # Verificar limite
            max_requests = RATE_LIMIT_MAX_REQUESTS.get(limit_type, RATE_LIMIT_MAX_REQUESTS['default'])
            if len(rate_limit_store[key]) >= max_requests:
                return jsonify({
                    'error': 'Rate limit exceeded. Tente novamente em alguns segundos.',
                    'retry_after': RATE_LIMIT_WINDOW
                }), 429
            
            # Registrar requisição
            rate_limit_store[key].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_admin_token(f):
    """Decorator para proteger endpoints administrativos"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar token no header ou query param
        token = request.headers.get('X-Admin-Token') or request.args.get('token')
        
        if not token or token != ADMIN_TOKEN:
            return jsonify({'error': 'Acesso não autorizado'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# FUNÇÕES DE SINCRONIZAÇÃO
# ============================================

def clean_old_files(directory, max_hours=24):
    """Remove arquivos com mais de X horas"""
    try:
        now = datetime.now()
        cutoff = now - timedelta(hours=max_hours)
        
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff:
                    os.remove(filepath)
                    print(f'Removed old file: {filename}')
    except Exception as e:
        print(f'Clean error: {e}')

def sync_mendanha():
    """Sincroniza imagens do radar Mendanha via FTP"""
    global last_sync
    
    if not FTP_CONFIG['password']:
        print("Erro: FTP_PASSWORD não configurada")
        return
    
    try:
        clean_old_files(MENDANHA_DIR, MAX_HOURS)
        
        ftp = ftplib.FTP(FTP_CONFIG['host'], timeout=30)
        ftp.login(FTP_CONFIG['user'], FTP_CONFIG['password'])
        ftp.cwd(FTP_CONFIG['path'])
        
        files = ftp.nlst()
        radar_files = [f for f in files if re.match(FTP_CONFIG['pattern'], f)]
        radar_files.sort(reverse=True)
        radar_files = radar_files[:20]
        
        existing = set(os.listdir(MENDANHA_DIR))
        
        for filename in radar_files:
            # Validar nome do arquivo do FTP também
            safe_filename = sanitize_filename(filename)
            if safe_filename and safe_filename not in existing:
                local_path = os.path.join(MENDANHA_DIR, safe_filename)
                with open(local_path, 'wb') as f:
                    ftp.retrbinary(f'RETR {filename}', f.write)
                print(f'Downloaded: {safe_filename}')
        
        ftp.quit()
        last_sync['mendanha'] = datetime.now().isoformat()
        
        remaining = len([f for f in os.listdir(MENDANHA_DIR) if f.endswith('.png')])
        print(f'Mendanha sync completed: {remaining} files')
    except Exception as e:
        print(f'Mendanha sync error: {e}')

def sync_sumare():
    """Baixa imagens do radar Sumaré do AlertaRio"""
    global last_sync
    try:
        base_url = 'https://alertario.rio.rj.gov.br/upload/Mapa/semfundo/radar'
        
        for i in range(1, 21):
            filename = f'radar{str(i).zfill(3)}.png'
            url = f'{base_url}{str(i).zfill(3)}.png'
            local_path = os.path.join(SUMARE_DIR, filename)
            
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
            except Exception as e:
                print(f'Error downloading {filename}: {e}')
        
        last_sync['sumare'] = datetime.now().isoformat()
        print(f'Sumaré sync completed: 20 files')
    except Exception as e:
        print(f'Sumaré sync error: {e}')

def sync_loop():
    """Loop de sincronização em background"""
    while True:
        sync_mendanha()
        sync_sumare()
        clean_old_files(EXPORT_DIR, 1)
        time.sleep(120)

sync_thread = threading.Thread(target=sync_loop, daemon=True)
sync_thread.start()

# ============================================
# ENDPOINTS PÚBLICOS (com rate limiting)
# ============================================

@app.route('/api/frames/mendanha')
@rate_limit('default')
def get_mendanha_frames():
    """Lista frames do Mendanha"""
    try:
        files = os.listdir(MENDANHA_DIR)
        files = [f for f in files if f.endswith('.png') and sanitize_filename(f)]
        files.sort()  # Ordem cronológica (mais antigo primeiro)
        files = files[-20:]  # Pegar os 20 mais recentes

        # Extrair timestamp do último frame para detectar atraso
        latest_timestamp = None
        delay_minutes = None
        if files:
            latest_file = files[-1]
            # Formato: MDN-YYYYMMDD-HHMM_...
            match = re.match(r'MDN-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})', latest_file)
            if match:
                year, month, day, hour, minute = match.groups()
                latest_timestamp = f"{year}-{month}-{day}T{hour}:{minute}:00"
                try:
                    frame_time = datetime(int(year), int(month), int(day), int(hour), int(minute))
                    now = datetime.now()
                    delay_minutes = int((now - frame_time).total_seconds() / 60)
                except:
                    pass

        return jsonify({
            'frames': files,
            'count': len(files),
            'latest_timestamp': latest_timestamp,
            'delay_minutes': delay_minutes
        })
    except Exception as e:
        return jsonify({'error': 'Erro interno'}), 500

@app.route('/api/frame/mendanha/<filename>')
@rate_limit('default')
def get_mendanha_frame(filename):
    """Serve uma imagem do Mendanha (com filtro opcional)"""
    # CORREÇÃO: Validar filename contra Path Traversal
    safe_filename = sanitize_filename(filename)
    if not safe_filename:
        return jsonify({'error': 'Nome de arquivo inválido'}), 400
    
    filepath = os.path.join(MENDANHA_DIR, safe_filename)
    
    # Verificação adicional: garantir que está dentro do diretório esperado
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(os.path.realpath(MENDANHA_DIR)):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if os.path.exists(filepath):
        # Verificar se filtro de chuva está ativo
        filter_rain = request.args.get('filter', '') == 'rain'
        
        if filter_rain:
            filtered = filter_rain_only(filepath)
            if filtered:
                response = send_file(filtered, mimetype='image/png')
                response.headers['Cache-Control'] = 'public, max-age=60'
                return response
        
        response = send_file(filepath, mimetype='image/png')
        return response
    return jsonify({'error': 'Arquivo não encontrado'}), 404

@app.route('/api/frames/sumare')
@rate_limit('default')
def get_sumare_frames():
    """Lista frames do Sumaré"""
    try:
        files = os.listdir(SUMARE_DIR)
        files = [f for f in files if f.endswith('.png') and sanitize_filename(f)]
        files.sort()
        return jsonify({'frames': files, 'count': len(files)})
    except Exception as e:
        return jsonify({'error': 'Erro interno'}), 500

@app.route('/api/frame/sumare/<filename>')
@rate_limit('default')
def get_sumare_frame(filename):
    """Serve uma imagem do Sumaré"""
    # CORREÇÃO: Validar filename contra Path Traversal
    safe_filename = sanitize_filename(filename)
    if not safe_filename:
        return jsonify({'error': 'Nome de arquivo inválido'}), 400
    
    filepath = os.path.join(SUMARE_DIR, safe_filename)
    
    # Verificação adicional
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(os.path.realpath(SUMARE_DIR)):
        return jsonify({'error': 'Acesso negado'}), 403
    
    if os.path.exists(filepath):
        response = send_file(filepath, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    return jsonify({'error': 'Arquivo não encontrado'}), 404

@app.route('/api/export/gif/<radar>')
@rate_limit('gif')  # Rate limit específico para GIF (mais restrito)
def export_gif(radar):
    """Gera GIF animado do radar"""
    try:
        from PIL import Image
        
        # Validar radar
        if radar not in ['mendanha', 'sumare']:
            return jsonify({'error': 'Radar inválido'}), 400
        
        directory = MENDANHA_DIR if radar == 'mendanha' else SUMARE_DIR
        
        files = [f for f in os.listdir(directory) if f.endswith('.png') and sanitize_filename(f)]
        files.sort()
        
        if len(files) == 0:
            return jsonify({'error': 'Nenhum frame disponível'}), 404
        
        # Limitar número de frames no GIF para evitar DoS
        files = files[:20]
        
        images = []
        for filename in files:
            filepath = os.path.join(directory, filename)
            try:
                img = Image.open(filepath)
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (0, 0, 0))
                    background.paste(img, mask=img.split()[3])
                    images.append(background)
                else:
                    images.append(img.convert('RGB'))
            except Exception as e:
                print(f'Error loading {filename}: {e}')
        
        if len(images) == 0:
            return jsonify({'error': 'Erro ao carregar imagens'}), 500
        
        output = BytesIO()
        images[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=images[1:],
            duration=500,
            loop=0
        )
        output.seek(0)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'radar_{radar}_{timestamp}.gif'
        
        return send_file(
            output,
            mimetype='image/gif',
            as_attachment=True,
            download_name=filename
        )
        
    except ImportError:
        return jsonify({'error': 'Pillow não instalado'}), 500
    except Exception as e:
        return jsonify({'error': 'Erro ao gerar GIF'}), 500

@app.route('/api/status')
@rate_limit('default')
def get_status():
    """Status da sincronização (informações limitadas)"""
    mendanha_count = len([f for f in os.listdir(MENDANHA_DIR) if f.endswith('.png')]) if os.path.exists(MENDANHA_DIR) else 0
    sumare_count = len([f for f in os.listdir(SUMARE_DIR) if f.endswith('.png')]) if os.path.exists(SUMARE_DIR) else 0
    
    return jsonify({
        'mendanha': {
            'files_count': mendanha_count,
            'last_sync': last_sync['mendanha']
        },
        'sumare': {
            'files_count': sumare_count,
            'last_sync': last_sync['sumare']
        },
        'status': 'ok'
    })

# ============================================
# ENDPOINTS ADMINISTRATIVOS (protegidos)
# ============================================

@app.route('/api/sync/mendanha')
@require_admin_token
@rate_limit('sync')
def manual_sync_mendanha():
    """Sincronização manual do Mendanha - REQUER TOKEN"""
    sync_mendanha()
    return jsonify({'message': 'Sync completed', 'last_sync': last_sync['mendanha']})

@app.route('/api/sync/sumare')
@require_admin_token
@rate_limit('sync')
def manual_sync_sumare():
    """Sincronização manual do Sumaré - REQUER TOKEN"""
    sync_sumare()
    return jsonify({'message': 'Sync completed', 'last_sync': last_sync['sumare']})

@app.route('/api/admin/status')
@require_admin_token
def admin_status():
    """Status detalhado para administradores"""
    mendanha_count = len([f for f in os.listdir(MENDANHA_DIR) if f.endswith('.png')]) if os.path.exists(MENDANHA_DIR) else 0
    sumare_count = len([f for f in os.listdir(SUMARE_DIR) if f.endswith('.png')]) if os.path.exists(SUMARE_DIR) else 0
    
    mendanha_size = sum(os.path.getsize(os.path.join(MENDANHA_DIR, f)) for f in os.listdir(MENDANHA_DIR) if f.endswith('.png')) if os.path.exists(MENDANHA_DIR) else 0
    sumare_size = sum(os.path.getsize(os.path.join(SUMARE_DIR, f)) for f in os.listdir(SUMARE_DIR) if f.endswith('.png')) if os.path.exists(SUMARE_DIR) else 0
    
    return jsonify({
        'mendanha': {
            'last_sync': last_sync['mendanha'],
            'files_count': mendanha_count,
            'size_mb': round(mendanha_size / 1024 / 1024, 2)
        },
        'sumare': {
            'last_sync': last_sync['sumare'],
            'files_count': sumare_count,
            'size_mb': round(sumare_size / 1024 / 1024, 2)
        },
        'max_hours': MAX_HOURS,
        'ftp_configured': bool(FTP_CONFIG['password']),
        'status': 'ok'
    })

# ============================================
# ROTAS PARA DESENVOLVIMENTO (ARQUIVOS ESTÁTICOS)
# ============================================

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def serve_index():
    """Serve index.html para desenvolvimento"""
    return send_file(os.path.join(STATIC_DIR, 'index.html'))

@app.route('/mosaic.html')
def serve_mosaic():
    """Serve mosaic.html para desenvolvimento"""
    return send_file(os.path.join(STATIC_DIR, 'mosaic.html'))

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve arquivos estáticos (logos, etc)"""
    filepath = os.path.join(STATIC_DIR, filename)
    if os.path.exists(filepath) and not '..' in filename:
        return send_file(filepath)
    return jsonify({'error': 'Arquivo não encontrado'}), 404

# ============================================
# TRATAMENTO DE ERROS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint não encontrado'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Erro interno do servidor'}), 500

# ============================================
# INICIALIZAÇÃO
# ============================================

if __name__ == '__main__':
    # CORREÇÃO: Desabilitar debug em produção
    app.run(host='0.0.0.0', port=5000, debug=False)
