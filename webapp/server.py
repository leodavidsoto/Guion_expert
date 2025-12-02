#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import subprocess
from pathlib import Path
import threading
import time
import os
import json
import sys
import platform
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'guion-experts-secret'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=180,
    ping_interval=30,
    async_mode='threading'
)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_DIR = BASE_DIR / "config"
connected_clients = 0

def load_config():
    """Load configuration from config/models.conf"""
    config = {}
    config_file = CONFIG_DIR / "models.conf"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")
        except Exception as e:
            print(f"Error loading config: {e}")
    return config

# Load config on startup
APP_CONFIG = load_config()

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
        structures_file = CONFIG_DIR / "structures.json"
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
                
                # Contar archivos
                file_count = sum(1 for _ in p.rglob('*') if _.is_file())
                
                projects.append({
                    'id': p.name,
                    'formato': formato,
                    'estructura': estructura,
                    'created': p.stat().st_mtime,
                    'file_count': file_count,
                    'path': str(p.absolute())
                })
    
    return jsonify(projects[:30])

@app.route('/api/project/<project_id>/open', methods=['POST'])
def open_project_folder(project_id):
    """Abre la carpeta del proyecto en Finder/Explorer"""
    try:
        project_path = OUTPUT_DIR / project_id
        
        if not project_path.exists():
            return jsonify({'error': 'Proyecto no encontrado'}), 404
        
        # Detectar sistema operativo y abrir carpeta
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            subprocess.run(['open', str(project_path)])
        elif system == 'Windows':
            subprocess.run(['explorer', str(project_path)])
        elif system == 'Linux':
            subprocess.run(['xdg-open', str(project_path)])
        else:
            return jsonify({'error': f'Sistema operativo no soportado: {system}'}), 400
        
        return jsonify({'success': True, 'path': str(project_path)})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/project/<project_id>/files')
def get_project_files(project_id):
    """Lista todos los archivos del proyecto"""
    try:
        project_path = OUTPUT_DIR / project_id
        
        if not project_path.exists():
            return jsonify({'error': 'Proyecto no encontrado'}), 404
        
        files = []
        
        for file_path in project_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(project_path)
                file_size = file_path.stat().st_size
                
                files.append({
                    'name': file_path.name,
                    'path': str(relative_path),
                    'size': file_size,
                    'size_human': format_size(file_size),
                    'folder': str(relative_path.parent),
                    'extension': file_path.suffix
                })
        
        # Organizar por carpeta
        folders = {}
        for f in files:
            folder = f['folder']
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(f)
        
        return jsonify({
            'project_id': project_id,
            'total_files': len(files),
            'folders': folders
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/project/<project_id>/download/<path:filename>')
def download_project_file(project_id, filename):
    """Descarga un archivo específico del proyecto"""
    try:
        project_path = OUTPUT_DIR / project_id
        file_path = project_path / filename
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({'error': 'Archivo no encontrado'}), 404
        
        # Verificar que el archivo está dentro del proyecto (seguridad)
        if not str(file_path.resolve()).startswith(str(project_path.resolve())):
            return jsonify({'error': 'Acceso denegado'}), 403
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/project/<project_id>/view/<path:filename>')
def view_project_file(project_id, filename):
    """Ve el contenido de un archivo de texto"""
    try:
        project_path = OUTPUT_DIR / project_id
        file_path = project_path / filename
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({'error': 'Archivo no encontrado'}), 404
        
        # Verificar seguridad
        if not str(file_path.resolve()).startswith(str(project_path.resolve())):
            return jsonify({'error': 'Acceso denegado'}), 403
        
        # Solo archivos de texto
        if file_path.suffix not in ['.txt', '.md', '.json', '.py', '.sh', '.html']:
            return jsonify({'error': 'Solo archivos de texto son visibles'}), 400
        
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        return jsonify({
            'filename': file_path.name,
            'content': content,
            'lines': len(content.split('\n')),
            'size': file_path.stat().st_size
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def format_size(size):
    """Formatea tamaño de archivo en formato legible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

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
        # env['TERM'] = 'xterm' # Removed to avoid interactive output issues
        
        if not auto_detect:
            if formato:
                env['FORCE_FORMATO'] = formato
            if estructura:
                env['FORCE_ESTRUCTURA'] = estructura
        
        socketio.emit('log', {'type': 'info', 'message': '⚙️  Ejecutando pipeline...'})
        
        try:
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
        except Exception as e:
            socketio.emit('log', {'type': 'error', 'message': f'❌ Error iniciando proceso: {e}'})
            return
        
        line_count = 0
        timeout = 3600
        start_time = time.time()
        last_heartbeat = start_time
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                process.kill()
                socketio.emit('log', {'type': 'error', 'message': '❌ Timeout: Proceso tomó más de 1 hora'})
                break
            
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
        
        # Use config or defaults
        expert_map = {
            'clasificador': (APP_CONFIG.get('MODEL_CLASIFICADOR', 'llama3.2:3b'), 'prompts/00_clasificador_completo.txt'),
            'concepto': (APP_CONFIG.get('MODEL_CONCEPTO', 'qwen2.5:7b'), 'prompts/01_concepto.txt'),
            'arquitecto': (APP_CONFIG.get('MODEL_ARQUITECTO', 'qwen2.5:14b'), 'prompts/02_arquitecto.txt'),
            'escaletista': (APP_CONFIG.get('MODEL_ESCALETISTA', 'qwen2.5:7b'), 'prompts/03_escaletista.txt'),
            'dialoguista': (APP_CONFIG.get('MODEL_DIALOGUISTA', 'qwen2.5:14b'), 'prompts/04_dialoguista.txt'),
            'localizador': (APP_CONFIG.get('MODEL_LOCALIZADOR', 'qwen2.5:7b'), 'prompts/10_localizador_chile.txt')
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
        model = APP_CONFIG.get('MODEL_ARQUITECTO', 'qwen2.5:14b')
        
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
    output_format = data.get('format', 'text')  # 'text' or 'json'
    
    if not scene_content:
        return jsonify({'error': 'Scene content required'}), 400
    
    thread = threading.Thread(target=run_flow_thread, args=(scene_content, output_format))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

def run_flow_thread(scene_content, output_format='text'):
    try:
        socketio.emit('log', {'type': 'info', 'message': '🎬 Director Flow analizando...'})
        
        prompt_filename = '12_director_flow_json.txt' if output_format == 'json' else '11_director_flow.txt'
        prompt_file = BASE_DIR / 'prompts' / prompt_filename
        
        if not prompt_file.exists():
            socketio.emit('log', {'type': 'error', 'message': f'Prompt {prompt_filename} no encontrado'})
            return
        
        prompt_content = prompt_file.read_text()
        model = APP_CONFIG.get('MODEL_DIRECTOR_FLOW', 'qwen2.5:14b')
        
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
                # Emitir chunk si es texto plano, si es JSON esperamos al final para validar
                if output_format == 'text':
                    socketio.emit('flow_chunk', {'content': line})
        
        process.wait()
        
        if process.returncode == 0:
            final_result = result
            if output_format == 'json':
                # Limpiar markdown si existe
                final_result = result.replace('```json', '').replace('```', '').strip()
                try:
                    # Validar JSON
                    json.loads(final_result)
                except json.JSONDecodeError:
                    socketio.emit('log', {'type': 'warning', 'message': '⚠️ El modelo no generó JSON válido, enviando texto crudo'})
            
            socketio.emit('log', {'type': 'success', 'message': '✅ Tabla Flow generada'})
            socketio.emit('flow_completed', {'tabla': final_result, 'format': output_format})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Error'})
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})
        
        process.wait()
        
        if process.returncode == 0:
            socketio.emit('log', {'type': 'success', 'message': '✅ Tabla Flow generada'})
            socketio.emit('flow_completed', {'tabla': result})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Error'})
        
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/analyze/upload', methods=['POST'])
def analyze_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file:
        filename = secure_filename(file.filename)
        upload_folder = app.config.get('UPLOAD_FOLDER')
        if not upload_folder:
            # Fallback
            upload_folder = BASE_DIR / "webapp/uploads"
        
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        filepath = Path(upload_folder) / filename
        file.save(filepath)
        
        thread = threading.Thread(target=run_analysis_thread, args=(str(filepath),))
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'started', 'filename': filename})

def run_analysis_thread(filepath):
    try:
        filename = os.path.basename(filepath)
        socketio.emit('log', {'type': 'info', 'message': f'📄 Analizando {filename}...'})
        
        script_path = BASE_DIR / "scripts/analizar_archivo.sh"
        if not script_path.exists():
            socketio.emit('log', {'type': 'error', 'message': 'Script de análisis no encontrado'})
            return

        cmd = [str(script_path), filepath]
        
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),  # Ensure correct working directory
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        result_output = ""
        for line in iter(process.stdout.readline, ''):
            if line:
                line = line.strip()
                result_output += line + "\n"
                
                log_type = 'info'
                if '✓' in line: log_type = 'success'
                elif '✗' in line or 'Error' in line: log_type = 'error'
                
                socketio.emit('log', {'type': log_type, 'message': line})
        
        process.wait()
        
        if process.returncode == 0:
            # Leer el reporte generado
            try:
                # Buscar el directorio de análisis más reciente
                analyzer_dir = BASE_DIR / "analyzer"
                if analyzer_dir.exists():
                    latest_analysis = sorted(
                        [d for d in analyzer_dir.iterdir() if d.is_dir() and d.name.startswith('analysis_')],
                        key=lambda x: x.stat().st_mtime,
                        reverse=True
                    )[0]
                    
                    report_file = latest_analysis / "ANALYSIS_REPORT.md"
                    if report_file.exists():
                        report_content = report_file.read_text()
                        socketio.emit('analysis_completed', {
                            'success': True,
                            'report': report_content,
                            'path': str(latest_analysis)
                        })
                        socketio.emit('log', {'type': 'success', 'message': '✅ Análisis finalizado'})
                    else:
                        socketio.emit('log', {'type': 'error', 'message': '❌ Reporte no encontrado'})
            except Exception as e:
                socketio.emit('log', {'type': 'error', 'message': f'Error leyendo reporte: {e}'})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Error en el análisis'})
            socketio.emit('analysis_completed', {'success': False})
            
    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/config/models')
def get_model_config():
    """Return current model configuration"""
    return jsonify(APP_CONFIG)

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
