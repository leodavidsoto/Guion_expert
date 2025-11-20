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
    ping_timeout=120,
    ping_interval=25,
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
                
                # Intentar leer clasificación
                clasificacion_file = p / "clasificacion" / "result.txt"
                if clasificacion_file.exists():
                    try:
                        content = clasificacion_file.read_text(encoding='utf-8', errors='ignore')
                        for line in content.split('\n'):
                            line = line.strip()
                            
                            # Buscar FORMATO
                            if 'FORMATO' in line.upper() and ':' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    formato = parts[1].strip()
                            
                            # Buscar ESTRUCTURA
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
        
        # Preparar comando
        cmd = [str(BASE_DIR / "ejecutar.sh"), idea]
        
        # Environment variables
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['TERM'] = 'xterm'
        
        if not auto_detect:
            if formato:
                env['FORCE_FORMATO'] = formato
            if estructura:
                env['FORCE_ESTRUCTURA'] = estructura
        
        socketio.emit('log', {'type': 'info', 'message': '⚙️  Ejecutando pipeline...'})
        
        # Ejecutar con mejor buffering
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
            cwd=str(BASE_DIR),
            env=env
        )
        
        # Leer output línea por línea
        line_count = 0
        timeout = 1800  # 30 minutos máximo
        start_time = time.time()
        last_heartbeat = start_time
        
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                process.kill()
                socketio.emit('log', {'type': 'error', 'message': '❌ Timeout: Proceso tomó más de 30 minutos'})
                break
            
            # Heartbeat cada 30 segundos
            if time.time() - last_heartbeat > 30:
                socketio.emit('log', {'type': 'info', 'message': f'💓 Heartbeat: Proceso activo ({int(elapsed)}s)'})
                last_heartbeat = time.time()
            
            line = process.stdout.readline()
            
            if not line:
                # Proceso terminó
                if process.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            
            line = line.rstrip()
            if line:
                line_count += 1
                
                # Determinar tipo de log
                log_type = 'output'
                if '✓' in line or 'OK' in line or 'completado' in line.lower() or 'success' in line.lower():
                    log_type = 'success'
                elif '✗' in line or 'ERROR' in line or 'error' in line.lower() or 'failed' in line.lower():
                    log_type = 'error'
                elif '→' in line or 'INFO' in line or '...' in line:
                    log_type = 'info'
                
                socketio.emit('log', {'type': log_type, 'message': line})
                
                # Progress indicator cada 20 líneas
                if line_count % 20 == 0:
                    socketio.emit('log', {'type': 'info', 'message': f'📊 Progreso: {line_count} líneas procesadas'})
        
        # Esperar a que termine
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            socketio.emit('log', {'type': 'error', 'message': '❌ El proceso no respondió al terminar'})
        
        if process.returncode == 0:
            socketio.emit('log', {'type': 'success', 'message': '✅ Pipeline completado exitosamente'})
            socketio.emit('log', {'type': 'success', 'message': f'📁 Total de líneas: {line_count}'})
            
            # Buscar el proyecto más reciente
            if OUTPUT_DIR.exists():
                try:
                    projects = sorted(
                        [p for p in OUTPUT_DIR.iterdir() if p.is_dir() and not p.name.startswith('.')],
                        key=lambda x: x.stat().st_mtime,
                        reverse=True
                    )
                    if projects:
                        latest = projects[0]
                        socketio.emit('log', {'type': 'success', 'message': f'📂 Proyecto generado: {latest.name}'})
                        
                        # Contar archivos generados
                        file_count = sum(1 for _ in latest.rglob('*') if _.is_file())
                        socketio.emit('log', {'type': 'success', 'message': f'📄 Total de archivos: {file_count}'})
                except Exception as e:
                    print(f"Error contando proyectos: {e}")
        else:
            socketio.emit('log', {'type': 'error', 'message': f'❌ Error: Código de salida {process.returncode}'})
        
        socketio.emit('generation_completed', {
            'returncode': process.returncode,
            'lines': line_count
        })
        
    except subprocess.TimeoutExpired:
        socketio.emit('log', {'type': 'error', 'message': '❌ Timeout: El proceso no respondió'})
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'❌ Error inesperado: {str(e)}'})
        import traceback
        traceback.print_exc()

@app.route('/api/expert/run', methods=['POST'])
def run_expert():
    data = request.json
    expert = data.get('expert')
    input_text = data.get('input')
    
    if not expert or not input_text:
        return jsonify({'error': 'Missing parameters'}), 400
    
    thread = threading.Thread(target=run_expert_thread, args=(expert, input_text))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_expert_thread(expert, input_text):
    try:
        socketio.emit('log', {'type': 'info', 'message': f'🎯 Ejecutando {expert}...'})
        
        expert_map = {
            'clasificador': ('llama3.2:3b', 'prompts/00_clasificador_completo.txt'),
            'concepto': ('qwen2.5:7b', 'prompts/01_concepto.txt'),
            'arquitecto': ('qwen2.5:14b', 'prompts/02_arquitecto.txt'),
            'escaletista': ('qwen2.5:7b', 'prompts/03_escaletista.txt'),
            'dialoguista': ('qwen2.5:14b', 'prompts/04_dialoguista.txt'),
            'localizador': ('qwen2.5:7b', 'prompts/10_localizador_chile.txt')
        }
        
        if expert not in expert_map:
            socketio.emit('log', {'type': 'error', 'message': f'Experto desconocido: {expert}'})
            return
        
        model, prompt_file = expert_map[expert]
        prompt_path = BASE_DIR / prompt_file
        
        if not prompt_path.exists():
            socketio.emit('log', {'type': 'error', 'message': 'Prompt no encontrado'})
            return
        
        prompt_content = prompt_path.read_text()
        full_input = f"{prompt_content}\n\nINPUT:\n{input_text}"
        
        cmd = ['ollama', 'run', model, full_input]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        result = ""
        for line in iter(process.stdout.readline, ''):
            if line:
                result += line
                socketio.emit('expert_update', {'expert': expert, 'content': result})
        
        process.wait()
        
        socketio.emit('log', {'type': 'success', 'message': f'✅ {expert} completado'})
        socketio.emit('expert_completed', {'expert': expert, 'content': result})
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/structure/generate', methods=['POST'])
def generate_with_structure():
    data = request.json
    structure_id = data.get('structure_id')
    input_text = data.get('input')
    
    if not structure_id or not input_text:
        return jsonify({'error': 'Missing parameters'}), 400
    
    thread = threading.Thread(target=run_structure_thread, args=(structure_id, input_text))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_structure_thread(structure_id, input_text):
    try:
        socketio.emit('log', {'type': 'info', 'message': f'🏗️ Generando con {structure_id}...'})
        
        structure_prompts = {
            'SAVE_THE_CAT': 'prompts/02_save_the_cat.txt',
            'THREE_ACT': 'prompts/02_arquitecto.txt',
            'HERO_JOURNEY': 'prompts/02_hero_journey.txt',
            'STORY_CIRCLE': 'prompts/02_story_circle.txt',
            'FIVE_ACT': 'prompts/02_five_act.txt',
            'IN_MEDIA_RES': 'prompts/02_in_media_res.txt',
            'SIMPLE': 'prompts/02_simple.txt'
        }
        
        prompt_file = BASE_DIR / structure_prompts.get(structure_id, 'prompts/02_arquitecto.txt')
        
        if not prompt_file.exists():
            socketio.emit('log', {'type': 'error', 'message': 'Prompt no encontrado'})
            return
        
        prompt_content = prompt_file.read_text()
        model = 'qwen2.5:14b'
        
        full_input = f"{prompt_content}\n\nESTRUCTURA: {structure_id}\n\nIDEA:\n{input_text}"
        
        cmd = ['ollama', 'run', model, full_input]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        result = ""
        for line in iter(process.stdout.readline, ''):
            if line:
                result += line
        
        process.wait()
        
        if process.returncode == 0:
            socketio.emit('log', {'type': 'success', 'message': f'✅ {structure_id} generada'})
            socketio.emit('structure_result', {'structure_id': structure_id, 'content': result})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Error'})
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/flow/generate', methods=['POST'])
def generate_flow():
    data = request.json
    scene_content = data.get('scene_content')
    
    if not scene_content:
        return jsonify({'error': 'Scene content required'}), 400
    
    thread = threading.Thread(target=run_flow_thread, args=(scene_content,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_flow_thread(scene_content):
    try:
        socketio.emit('log', {'type': 'info', 'message': '🎬 Director Flow analizando...'})
        
        prompt_file = BASE_DIR / 'prompts' / '11_director_flow.txt'
        
        if not prompt_file.exists():
            socketio.emit('log', {'type': 'error', 'message': 'Prompt Flow no encontrado'})
            return
        
        prompt_content = prompt_file.read_text()
        model = 'qwen2.5:14b'
        
        full_input = f"{prompt_content}\n\nESCENA:\n{scene_content}"
        
        cmd = ['ollama', 'run', model, full_input]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        result = ""
        for line in iter(process.stdout.readline, ''):
            if line:
                result += line
        
        process.wait()
        
        if process.returncode == 0:
            socketio.emit('log', {'type': 'success', 'message': '✅ Tabla Flow generada'})
            socketio.emit('flow_completed', {'tabla': result})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Error'})
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)
    
    return jsonify({'success': True, 'filename': filename, 'filepath': str(filepath)})

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    filepath = data.get('filepath')
    
    if not filepath:
        return jsonify({'error': 'Filepath required'}), 400
    
    thread = threading.Thread(target=run_analyze_thread, args=(filepath,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_analyze_thread(filepath):
    try:
        socketio.emit('log', {'type': 'info', 'message': '📊 Analizando...'})
        socketio.emit('analysis_update', {'content': 'Análisis en progreso...'})
        time.sleep(2)
        socketio.emit('analysis_update', {'content': 'Análisis completado (placeholder)'})
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

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
    print("Presiona Ctrl+C para detener")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
