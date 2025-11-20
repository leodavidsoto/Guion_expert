#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import subprocess
from pathlib import Path
import threading
import time
import os
import json
import sys
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'guion-experts-secret'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=180,  # Aumentado a 3 minutos
    ping_interval=30,
    async_mode='threading'
)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
connected_clients = 0

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    ollama_running = subprocess.run(['pgrep', 'ollama'], capture_output=True).returncode == 0
    return jsonify({
        'status': 'ok',
        'ollama': ollama_running,
        'connected_clients': connected_clients
    })

@app.route('/api/structures/all')
def get_all_structures():
    try:
        structures_file = BASE_DIR / "config" / "structures.json"
        if not structures_file.exists():
            return jsonify({'error': 'structures.json not found'}), 404
        
        with open(structures_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/experts')
def get_experts():
    experts = {
        'clasificador': {'name': 'Clasificador', 'icon': '🎯', 'description': 'Detecta formato y estructura'},
        'concepto': {'name': 'Conceptor', 'icon': '💡', 'description': 'Desarrolla concepto narrativo'},
        'arquitecto': {'name': 'Arquitecto', 'icon': '🏗️', 'description': 'Estructura narrativa'},
        'escaletista': {'name': 'Escaletista', 'icon': '📋', 'description': 'Genera escaleta'},
        'dialoguista': {'name': 'Dialoguista', 'icon': '💬', 'description': 'Escribe diálogos'},
        'prompts_sd': {'name': 'Prompts SD', 'icon': '🎨', 'description': 'Prompts Stable Diffusion'},
        'prompts_veo': {'name': 'Prompts Veo', 'icon': '🎬', 'description': 'Prompts video AI'},
        'localizador': {'name': 'Localizador', 'icon': '🇨🇱', 'description': 'Adapta a español chileno'}
    }
    return jsonify(experts)

@app.route('/api/projects')
def get_projects():
    projects = []
    if OUTPUT_DIR.exists():
        for p in sorted(OUTPUT_DIR.iterdir(), reverse=True):
            if p.is_dir() and not p.name.startswith('.'):
                formato = "Desconocido"
                estructura = "Desconocida"
                
                clasificacion_file = p / "clasificacion" / "result.txt"
                if clasificacion_file.exists():
                    try:
                        content = clasificacion_file.read_text(encoding='utf-8', errors='ignore')
                        for line in content.split('\n'):
                            line = line.strip()
                            if 'FORMATO' in line.upper() and ':' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    formato = parts[1].strip()
                            if 'ESTRUCTURA' in line.upper() and ':' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    estructura = parts[1].strip()
                    except Exception as e:
                        print(f"Error leyendo {clasificacion_file}: {e}")
                
                projects.append({
                    'id': p.name,
                    'formato': formato,
                    'estructura': estructura,
                    'created': p.stat().st_mtime
                })
    
    return jsonify(projects[:30])

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    idea = data.get('idea', '').strip()
    
    if not idea:
        return jsonify({'error': 'Idea requerida'}), 400
    
    formato = data.get('formato')
    estructura = data.get('estructura')
    auto_detect = data.get('auto_detect', True)
    
    thread = threading.Thread(
        target=run_pipeline_thread, 
        args=(idea, formato, estructura, auto_detect)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_pipeline_thread(idea, formato=None, estructura=None, auto_detect=True):
    try:
        socketio.emit('log', {'type': 'info', 'message': '🚀 Iniciando pipeline...'})
        socketio.emit('log', {'type': 'info', 'message': f'💡 Idea: {idea[:100]}'})
        
        if not auto_detect:
            if formato:
                socketio.emit('log', {'type': 'info', 'message': f'📺 Formato manual: {formato}'})
            if estructura:
                socketio.emit('log', {'type': 'info', 'message': f'📖 Estructura manual: {estructura}'})
        
        cmd = [str(BASE_DIR / "ejecutar.sh"), idea]
        
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['TERM'] = 'xterm'
        
        if not auto_detect:
            if formato:
                env['FORCE_FORMATO'] = formato
            if estructura:
                env['FORCE_ESTRUCTURA'] = estructura
        
        socketio.emit('log', {'type': 'info', 'message': '⚙️  Ejecutando pipeline...'})
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=str(BASE_DIR),
            env=env
        )
        
        line_count = 0
        timeout = 3600  # ⏱️ AUMENTADO A 1 HORA
        start_time = time.time()
        last_heartbeat = start_time
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                process.kill()
                socketio.emit('log', {'type': 'error', 'message': '❌ Timeout: Proceso tomó más de 1 hora'})
                break
            
            # Heartbeat cada 30 segundos
            if time.time() - last_heartbeat > 30:
                mins = int(elapsed / 60)
                socketio.emit('log', {'type': 'info', 'message': f'💓 Activo: {mins} min - {line_count} líneas'})
                last_heartbeat = time.time()
            
            line = process.stdout.readline()
            
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            
            line = line.rstrip()
            if line:
                line_count += 1
                
                log_type = 'output'
                if '✓' in line or 'OK' in line or 'completado' in line.lower() or 'success' in line.lower():
                    log_type = 'success'
                elif '✗' in line or 'ERROR' in line or 'error' in line.lower() or 'failed' in line.lower():
                    log_type = 'error'
                elif '→' in line or 'INFO' in line or '...' in line:
                    log_type = 'info'
                
                socketio.emit('log', {'type': log_type, 'message': line})
                
                if line_count % 50 == 0:
                    socketio.emit('log', {'type': 'info', 'message': f'📊 Progreso: {line_count} líneas'})
        
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            socketio.emit('log', {'type': 'error', 'message': '❌ El proceso no respondió'})
        
        if process.returncode == 0:
            socketio.emit('log', {'type': 'success', 'message': '✅ Pipeline completado'})
            socketio.emit('log', {'type': 'success', 'message': f'📁 Total: {line_count} líneas'})
            
            if OUTPUT_DIR.exists():
                try:
                    projects = sorted(
                        [p for p in OUTPUT_DIR.iterdir() if p.is_dir() and not p.name.startswith('.')],
                        key=lambda x: x.stat().st_mtime,
                        reverse=True
                    )
                    if projects:
                        latest = projects[0]
                        socketio.emit('log', {'type': 'success', 'message': f'📂 Proyecto: {latest.name}'})
                        
                        file_count = sum(1 for _ in latest.rglob('*') if _.is_file())
                        socketio.emit('log', {'type': 'success', 'message': f'📄 Archivos: {file_count}'})
                except Exception as e:
                    print(f"Error: {e}")
        else:
            socketio.emit('log', {'type': 'error', 'message': f'❌ Error: {process.returncode}'})
        
        socketio.emit('generation_completed', {
            'returncode': process.returncode,
            'lines': line_count
        })
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'❌ Error: {str(e)}'})
        import traceback
        traceback.print_exc()

@socketio.on('connect')
def handle_connect():
    global connected_clients
    connected_clients += 1
    emit('connected', {'status': 'ok'})
    print(f"✅ Cliente conectado. Total: {connected_clients}")

@socketio.on('disconnect')
def handle_disconnect():
    global connected_clients
    connected_clients -= 1
    print(f"❌ Cliente desconectado. Total: {connected_clients}")

@socketio.on('ping')
def handle_ping():
    emit('pong')

if __name__ == '__main__':
    print("=" * 60)
    print("🎬 GUION EXPERTS SUITE V2")
    print("=" * 60)
    print(f"🌐 URL: http://localhost:5001")
    print(f"📁 Base: {BASE_DIR}")
    print(f"📂 Output: {OUTPUT_DIR}")
    print()
    print("⏱️  Timeout: 1 hora por generación")
    print("Presiona Ctrl+C para detener")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
