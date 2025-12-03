from flask import Flask, jsonify, send_file, Response
from flask_cors import CORS
import os
import re
import ftplib
import threading
import time
from datetime import datetime, timedelta
import requests
from io import BytesIO

app = Flask(__name__)
CORS(app)

# Configuração
CACHE_DIR = '/var/www/radar-nowcast/cache'
MENDANHA_DIR = os.path.join(CACHE_DIR, 'mendanha')
SUMARE_DIR = os.path.join(CACHE_DIR, 'sumare')
EXPORT_DIR = os.path.join(CACHE_DIR, 'exports')

# Criar diretórios
os.makedirs(MENDANHA_DIR, exist_ok=True)
os.makedirs(SUMARE_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# FTP Mendanha
FTP_CONFIG = {
    'host': '82.180.153.43',
    'user': 'u109222483.CorInea',
    'password': 'Inea$123Qwe!!',
    'path': '/',
    'pattern': r'MDN-.*\.png$'
}

last_sync = {'mendanha': None, 'sumare': None}

# Limite de horas para manter imagens
MAX_HOURS = 24

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
    try:
        # Limpar arquivos antigos (mais de 24h)
        clean_old_files(MENDANHA_DIR, MAX_HOURS)
        
        ftp = ftplib.FTP(FTP_CONFIG['host'])
        ftp.login(FTP_CONFIG['user'], FTP_CONFIG['password'])
        ftp.cwd(FTP_CONFIG['path'])
        
        files = ftp.nlst()
        radar_files = [f for f in files if re.match(FTP_CONFIG['pattern'], f)]
        radar_files.sort(reverse=True)
        radar_files = radar_files[:20]  # Limitar a 20 frames
        
        existing = set(os.listdir(MENDANHA_DIR))
        
        for filename in radar_files:
            if filename not in existing:
                local_path = os.path.join(MENDANHA_DIR, filename)
                with open(local_path, 'wb') as f:
                    ftp.retrbinary(f'RETR {filename}', f.write)
                print(f'Downloaded: {filename}')
        
        ftp.quit()
        last_sync['mendanha'] = datetime.now().isoformat()
        
        # Contar arquivos restantes
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
        
        # Limpar exports antigos (mais de 1 hora)
        clean_old_files(EXPORT_DIR, 1)
        
        time.sleep(120)  # 2 minutos

# Iniciar thread de sincronização
sync_thread = threading.Thread(target=sync_loop, daemon=True)
sync_thread.start()

@app.route('/api/frames/mendanha')
def get_mendanha_frames():
    """Lista frames do Mendanha"""
    try:
        files = os.listdir(MENDANHA_DIR)
        files = [f for f in files if f.endswith('.png')]
        files.sort(reverse=True)
        files = files[:20]  # Limitar a 20 frames
        return jsonify({'frames': files, 'count': len(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/frame/mendanha/<filename>')
def get_mendanha_frame(filename):
    """Serve uma imagem do Mendanha"""
    filepath = os.path.join(MENDANHA_DIR, filename)
    if os.path.exists(filepath):
        response = send_file(filepath, mimetype='image/png')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/frames/sumare')
def get_sumare_frames():
    """Lista frames do Sumaré"""
    try:
        files = os.listdir(SUMARE_DIR)
        files = [f for f in files if f.endswith('.png')]
        files.sort()
        return jsonify({'frames': files, 'count': len(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/frame/sumare/<filename>')
def get_sumare_frame(filename):
    """Serve uma imagem do Sumaré"""
    filepath = os.path.join(SUMARE_DIR, filename)
    if os.path.exists(filepath):
        response = send_file(filepath, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/export/gif/<radar>')
def export_gif(radar):
    """Gera GIF animado do radar"""
    try:
        from PIL import Image
        
        if radar == 'mendanha':
            directory = MENDANHA_DIR
        elif radar == 'sumare':
            directory = SUMARE_DIR
        else:
            return jsonify({'error': 'Radar inválido'}), 400
        
        # Listar arquivos
        files = [f for f in os.listdir(directory) if f.endswith('.png')]
        files.sort()
        
        if len(files) == 0:
            return jsonify({'error': 'Nenhum frame disponível'}), 404
        
        # Carregar imagens
        images = []
        for filename in files:
            filepath = os.path.join(directory, filename)
            try:
                img = Image.open(filepath)
                # Converter para RGB se necessário (GIF não suporta RGBA bem)
                if img.mode == 'RGBA':
                    # Criar fundo preto
                    background = Image.new('RGB', img.size, (0, 0, 0))
                    background.paste(img, mask=img.split()[3])
                    images.append(background)
                else:
                    images.append(img.convert('RGB'))
            except Exception as e:
                print(f'Error loading {filename}: {e}')
        
        if len(images) == 0:
            return jsonify({'error': 'Erro ao carregar imagens'}), 500
        
        # Gerar GIF
        output = BytesIO()
        images[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=images[1:],
            duration=500,  # 500ms por frame
            loop=0
        )
        output.seek(0)
        
        # Nome do arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'radar_{radar}_{timestamp}.gif'
        
        return send_file(
            output,
            mimetype='image/gif',
            as_attachment=True,
            download_name=filename
        )
        
    except ImportError:
        return jsonify({'error': 'Pillow não instalado. Execute: pip install Pillow'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def get_status():
    """Status da sincronização"""
    mendanha_count = len([f for f in os.listdir(MENDANHA_DIR) if f.endswith('.png')]) if os.path.exists(MENDANHA_DIR) else 0
    sumare_count = len([f for f in os.listdir(SUMARE_DIR) if f.endswith('.png')]) if os.path.exists(SUMARE_DIR) else 0
    
    # Calcular espaço usado
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
        'status': 'ok'
    })

@app.route('/api/sync/mendanha')
def manual_sync_mendanha():
    """Sincronização manual do Mendanha"""
    sync_mendanha()
    return jsonify({'message': 'Sync completed', 'last_sync': last_sync['mendanha']})

@app.route('/api/sync/sumare')
def manual_sync_sumare():
    """Sincronização manual do Sumaré"""
    sync_sumare()
    return jsonify({'message': 'Sync completed', 'last_sync': last_sync['sumare']})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
