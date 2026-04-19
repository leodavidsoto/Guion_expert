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

# --- LLM Provider (Claude Haiku 4.5 / Ollama) --------------------------------
# Adaptador que permite usar Claude o Ollama según .env
import llm_provider  # webapp/llm_provider.py

# --- Logging estructurado (structlog) ----------------------------------------
# Configurar ANTES de crear la app para que todos los logs salgan estructurados.
from observability import configure_logging, get_logger, init_flask_logging
configure_logging()
log = get_logger(__name__)
log.info("app_starting", model=llm_provider.CLAUDE_MODEL, provider=llm_provider.PROVIDER)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'guion-experts-secret'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

# Inyecta trace_id por request + log start/end automático
init_flask_logging(app)

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
    llm_status = llm_provider.provider_status()
    return jsonify({
        'status': 'ok',
        'llm': llm_status,
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
    """
    Corre el pipeline 100% en Python con Claude Haiku 4.5 (sin Ollama ni bash).
    Tras completar, exporta automáticamente el proyecto a OpenMontage.
    """
    try:
        from pipeline_claude import run_full_pipeline  # webapp/pipeline_claude.py

        result = run_full_pipeline(
            idea=idea,
            socketio=socketio,
            formato=formato,
            estructura=estructura,
            auto_detect=auto_detect,
        )

        if result.get("error"):
            socketio.emit('generation_completed', {'returncode': 1, 'error': result["error"]})
            return

        project_dir = result["output_dir"]

        # --- Bridge automático a OpenMontage ---
        om_export = _maybe_export_to_openmontage(
            project_dir=project_dir,
            idea=idea,
            formato=result.get("formato"),
            duration_seconds=(result.get("duracion", 5) * 60) if result.get("duracion") else None,
        )

        socketio.emit('generation_completed', {
            'returncode': 0,
            'project': str(project_dir.name),
            'formato': result.get("formato"),
            'estructura': result.get("estructura"),
            'escenas': result.get("escenas"),
            'openmontage': om_export,
        })

    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'❌ Error: {str(e)}'})
        import traceback
        traceback.print_exc()
        socketio.emit('generation_completed', {'returncode': 1, 'error': str(e)})


def _maybe_export_to_openmontage(project_dir, idea, formato=None, duration_seconds=None):
    """
    Intenta exportar automáticamente a OpenMontage si el repo está junto a Guion_expert.
    Devuelve dict con los paths o None si no hay OpenMontage disponible.
    """
    try:
        # Busca OpenMontage junto al repo (sibling) o dentro de ESCRIBE
        candidates = [
            BASE_DIR.parent / "OpenMontage",
            BASE_DIR.parent / "OpenMontage" / "OpenMontage",  # tolerar clon anidado
        ]
        openmontage_root = next((p for p in candidates if (p / "schemas" / "artifacts").exists()), None)
        if openmontage_root is None:
            socketio.emit('log', {'type': 'info', 'message': 'ℹ️  OpenMontage no encontrado — export omitido.'})
            return None

        socketio.emit('log', {'type': 'info', 'message': f'🎬 Exportando a OpenMontage ({openmontage_root.name})…'})

        # Import tardío para no fallar si falta el paquete
        sys.path.insert(0, str(BASE_DIR))
        from bridge.openmontage_export import export_project_to_openmontage

        brief_hint = {"idea": idea, "formato": formato}
        if duration_seconds:
            brief_hint["duration_seconds"] = duration_seconds

        result = export_project_to_openmontage(
            project_dir=project_dir,
            openmontage_root=openmontage_root,
            idea=idea,
            brief_hint=brief_hint,
        )

        socketio.emit('log', {'type': 'success', 'message': f'✅ OpenMontage export: {result["project_root"].name}'})
        socketio.emit('log', {'type': 'success', 'message': f'   📋 brief.json, script.json, scene_plan.json'})
        socketio.emit('log', {'type': 'success', 'message': f'   🎞️  remotion-cuts.json (render sin API keys)'})

        # Devolver rutas como strings para JSON
        return {k: str(v) for k, v in result.items() if isinstance(v, Path)}

    except Exception as e:
        socketio.emit('log', {'type': 'error', 'message': f'⚠️  Export a OpenMontage falló: {e}'})
        import traceback
        traceback.print_exc()
        return None

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

        # LLM call vía adaptador (Claude Haiku 4.5 o Ollama según .env)
        result = ""
        for chunk in llm_provider.generate(model=model, prompt=full_input, stream=True):
            if chunk:
                result += chunk
                socketio.emit('expert_update', {'expert': expert, 'content': result})

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

        # LLM call vía adaptador
        result = ""
        for chunk in llm_provider.generate(model=model, prompt=full_input, stream=True):
            if chunk:
                result += chunk

        if result.strip():
            socketio.emit('log', {'type': 'success', 'message': f'✅ {structure_id} generada'})
            socketio.emit('structure_result', {'structure_id': structure_id, 'content': result})
        else:
            socketio.emit('log', {'type': 'error', 'message': '❌ Respuesta vac\u00eda del modelo'})
        
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

        # LLM call vía adaptador
        result = ""
        for chunk in llm_provider.generate(model=model, prompt=full_input, stream=True):
            if chunk:
                result += chunk
                if output_format == 'text':
                    socketio.emit('flow_chunk', {'content': chunk})

        if result.strip():
            final_result = result
            if output_format == 'json':
                final_result = result.replace('```json', '').replace('```', '').strip()
                try:
                    json.loads(final_result)
                except json.JSONDecodeError:
                    socketio.emit('log', {'type': 'warning', 'message': '\u26a0\ufe0f El modelo no gener\u00f3 JSON v\u00e1lido, enviando texto crudo'})

            socketio.emit('log', {'type': 'success', 'message': '\u2705 Tabla Flow generada'})
            socketio.emit('flow_completed', {'tabla': final_result, 'format': output_format})
        else:
            socketio.emit('log', {'type': 'error', 'message': '\u274c Respuesta vac\u00eda del modelo'})

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

@app.route('/api/openmontage/export/<project_id>', methods=['POST'])
def export_to_openmontage(project_id):
    """
    Exporta manualmente un proyecto existente de Guion_expert a OpenMontage.
    """
    try:
        project_dir = OUTPUT_DIR / project_id
        if not project_dir.exists() or not project_dir.is_dir():
            return jsonify({'error': f'Proyecto {project_id} no existe'}), 404

        # Localizar OpenMontage como sibling
        candidates = [
            BASE_DIR.parent / "OpenMontage",
            BASE_DIR.parent / "OpenMontage" / "OpenMontage",
        ]
        openmontage_root = next((p for p in candidates if (p / "schemas" / "artifacts").exists()), None)
        if openmontage_root is None:
            return jsonify({'error': 'OpenMontage no está clonado junto al proyecto'}), 400

        sys.path.insert(0, str(BASE_DIR))
        from bridge.openmontage_export import export_project_to_openmontage

        # Best-effort: leer idea del concepto
        concepto = project_dir / "concepto" / "result.txt"
        idea = concepto.read_text(encoding='utf-8').splitlines()[0] if concepto.exists() else project_id

        result = export_project_to_openmontage(
            project_dir=project_dir,
            openmontage_root=openmontage_root,
            idea=idea,
        )
        return jsonify({
            'status': 'ok',
            'project_root': str(result['project_root']),
            'artifacts': {k: str(v) for k, v in result.items() if isinstance(v, Path)},
            'title': result.get('title'),
            'num_scenes': result.get('num_scenes'),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/openmontage/status')
def openmontage_status():
    """Indica si OpenMontage está disponible como sibling."""
    candidates = [
        BASE_DIR.parent / "OpenMontage",
        BASE_DIR.parent / "OpenMontage" / "OpenMontage",
    ]
    found = next((p for p in candidates if (p / "schemas" / "artifacts").exists()), None)
    return jsonify({
        'available': found is not None,
        'path': str(found) if found else None,
    })

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
