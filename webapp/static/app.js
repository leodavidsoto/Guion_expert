// WebSocket Connection
const socket = io({
    transports: ['websocket', 'polling'],
    pingTimeout: 120000,
    pingInterval: 25000
});

let selectedExpert = null;
let selectedStructure = null;
let currentWorkspaceContent = null;

// Elements
const views = document.querySelectorAll('.view');
const navIcons = document.querySelectorAll('.nav-icon');
const headerTitle = document.getElementById('headerTitle');
const headerSubtitle = document.getElementById('headerSubtitle');
const statusBadge = document.getElementById('statusBadge');
const logConsole = document.getElementById('logConsole');
const workspaceLog = document.getElementById('workspaceLog');
const autoDetect = document.getElementById('autoDetect');
const manualControls = document.getElementById('manualControls');
const estructuraSelect = document.getElementById('estructuraSelect');
const estructuraInfo = document.getElementById('estructuraInfo');

// Toggle manual controls
autoDetect.addEventListener('change', () => {
    manualControls.classList.toggle('hidden', autoDetect.checked);
});

// Show estructura info
estructuraSelect.addEventListener('change', () => {
    const value = estructuraSelect.value;
    if (!value) {
        estructuraInfo.classList.add('hidden');
        return;
    }
    
    const selectedOption = estructuraSelect.options[estructuraSelect.selectedIndex];
    document.getElementById('estructuraInfoTitle').textContent = selectedOption.text;
    document.getElementById('estructuraInfoDesc').textContent = 'Estructura narrativa seleccionada';
    estructuraInfo.classList.remove('hidden');
});

// Navigation
navIcons.forEach(icon => {
    icon.addEventListener('click', () => {
        const viewName = icon.dataset.view;
        switchView(viewName);
    });
});

function switchView(viewName) {
    navIcons.forEach(i => i.classList.remove('active'));
    views.forEach(v => v.classList.remove('active'));
    
    const targetNav = document.querySelector(`[data-view="${viewName}"]`);
    const targetView = document.getElementById(viewName + 'View');
    
    if (targetNav) targetNav.classList.add('active');
    if (targetView) targetView.classList.add('active');
    
    const titles = {
        'generate': ['🎬 Generar Guion', '53 Estructuras • 70+ Formatos • 8 Expertos • Director Flow'],
        'structures': ['📖 Estructuras Narrativas', '53 estructuras de todo el mundo'],
        'experts': ['🎯 Expertos Individuales', '8 expertos especializados'],
        'analyze': ['📄 Analizar PDF', 'Sube y analiza guiones'],
        'projects': ['📁 Proyectos', 'Historial de generaciones']
    };
    
    if (titles[viewName]) {
        headerTitle.textContent = titles[viewName][0];
        headerSubtitle.textContent = titles[viewName][1];
    }
    
    if (viewName === 'experts') loadExperts();
    if (viewName === 'structures') loadStructures();
    if (viewName === 'projects') loadProjects();
}

// Socket events
socket.on('connected', (data) => {
    statusBadge.textContent = '● Conectado';
    statusBadge.style.background = 'var(--success)';
    addLog('✅ Sistema conectado', 'success');
});

socket.on('disconnect', () => {
    statusBadge.textContent = '● Desconectado';
    statusBadge.style.background = 'var(--error)';
});

socket.on('log', (data) => {
    addLog(data.message, data.type);
    addWorkspaceLog(data.message, data.type);
});

socket.on('expert_update', (data) => {
    document.getElementById('expertResult').textContent = data.content;
    document.getElementById('expertResult').classList.remove('empty');
});

socket.on('expert_completed', (data) => {
    document.getElementById('runExpertBtn').disabled = false;
    addLog('✅ Experto completado', 'success');
});

socket.on('structure_result', (data) => {
    currentWorkspaceContent = data.content;
    document.getElementById('workspaceResult').textContent = data.content;
    document.getElementById('workspaceResult').classList.remove('empty');
    document.getElementById('workspaceGenerateBtn').disabled = false;
    document.getElementById('workspaceGenerateBtn').textContent = '▶️ Generar con esta Estructura';
});

socket.on('flow_completed', (data) => {
    document.getElementById('workspaceFlowResult').textContent = data.tabla;
    document.getElementById('workspaceFlowResult').classList.remove('empty');
    document.getElementById('workspaceFlowBtn').disabled = false;
    document.getElementById('workspaceFlowBtn').textContent = '🎥 Generar Tabla Flow';
    addWorkspaceLog('✅ Tabla Flow generada', 'success');
});

// Keep alive
setInterval(() => {
    socket.emit('ping');
}, 20000);

// Generate
document.getElementById('generateBtn')?.addEventListener('click', async () => {
    const idea = document.getElementById('ideaInput').value.trim();
    if (!idea) {
        alert('Ingresa una idea');
        return;
    }
    
    const auto = autoDetect.checked;
    const formato = auto ? null : document.getElementById('formatoSelect').value;
    const estructura = auto ? null : estructuraSelect.value;
    
    document.getElementById('generateBtn').disabled = true;
    document.getElementById('generateBtn').textContent = '⏳ Generando...';
    logConsole.innerHTML = '';
    
    await fetch('/api/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ 
            idea, 
            formato,
            estructura,
            auto_detect: auto 
        })
    });
});

// Load structures
async function loadStructures() {
    try {
        const response = await fetch('/api/structures/all');
        const allStructures = await response.json();
        const grid = document.getElementById('structuresGrid');
        
        let html = '';
        
        const categoryNames = {
            'classic_hollywood': '🎬 Hollywood Clásico',
            'mythic_journey': '🗿 Viaje Mítico',
            'episodic_tv': '📺 TV y Series',
            'non_linear': '🔀 No Lineal',
            'international': '🌏 Internacional',
            'experimental': '🧪 Experimental',
            'short_form': '⚡ Formato Corto',
            'documentary': '🎥 Documental',
            'theatre_performance': '🎭 Teatro'
        };
        
        for (let category in allStructures) {
            html += `<div class="category-header"><h3>${categoryNames[category] || category}</h3></div>`;
            
            for (let id in allStructures[category]) {
                const s = allStructures[category][id];
                html += `
                    <div class="card" onclick="openStructureWorkspace('${id}', \`${s.name}\`, \`${s.description}\`, '${s.beats}', '${s.duration}', '${s.best_for}', '${s.author || ''}')">
                        <div class="card-icon">📖</div>
                        <div class="card-title">${s.name}</div>
                        <div class="card-description">${s.description}</div>
                        <div class="card-meta">
                            <span class="badge">${s.beats} beats</span>
                            <span class="badge">${s.duration}</span>
                            <span class="badge">${s.best_for}</span>
                        </div>
                    </div>
                `;
            }
        }
        
        grid.innerHTML = html;
    } catch (error) {
        document.getElementById('structuresGrid').innerHTML = '<p style="color: red;">Error cargando estructuras</p>';
    }
}

function openStructureWorkspace(id, name, description, beats, duration, bestFor, author) {
    selectedStructure = id;
    
    document.getElementById('workspaceStructureName').textContent = name;
    document.getElementById('workspaceStructureDesc').textContent = description;
    
    document.getElementById('workspaceMetaInfo').innerHTML = `
        <p><strong>📊 Beats:</strong> ${beats}</p>
        <p><strong>⏱️ Duración:</strong> ${duration}</p>
        <p><strong>🎯 Mejor para:</strong> ${bestFor}</p>
        ${author ? `<p><strong>✍️ Autor:</strong> ${author}</p>` : ''}
    `;
    
    document.getElementById('workspaceInput').value = '';
    document.getElementById('workspaceResult').textContent = 'Esperando generación...';
    document.getElementById('workspaceResult').classList.add('empty');
    document.getElementById('workspaceFlowResult').textContent = 'Presiona el botón para generar tabla de rodaje';
    document.getElementById('workspaceFlowResult').classList.add('empty');
    
    workspaceLog.innerHTML = '<div class="log-line log-info">Listo para generar</div>';
    
    switchView('structureWorkspace');
}

document.getElementById('workspaceGenerateBtn')?.addEventListener('click', async () => {
    const input = document.getElementById('workspaceInput').value.trim();
    if (!input) {
        alert('Ingresa tu idea');
        return;
    }
    
    if (!selectedStructure) {
        alert('Error: No hay estructura seleccionada');
        return;
    }
    
    document.getElementById('workspaceGenerateBtn').disabled = true;
    document.getElementById('workspaceGenerateBtn').textContent = '⏳ Generando...';
    document.getElementById('workspaceResult').textContent = 'Generando...';
    document.getElementById('workspaceResult').classList.remove('empty');
    workspaceLog.innerHTML = '';
    
    try {
        const response = await fetch('/api/structure/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                structure_id: selectedStructure,
                input: input
            })
        });
        
        if (response.ok) {
            addWorkspaceLog(`Generando con ${selectedStructure}...`, 'info');
        } else {
            throw new Error('Error al iniciar');
        }
    } catch (error) {
        addWorkspaceLog(`Error: ${error.message}`, 'error');
        document.getElementById('workspaceGenerateBtn').disabled = false;
        document.getElementById('workspaceGenerateBtn').textContent = '▶️ Generar con esta Estructura';
    }
});

document.getElementById('workspaceFlowBtn')?.addEventListener('click', async () => {
    if (!currentWorkspaceContent) {
        alert('Genera primero la estructura');
        return;
    }
    
    document.getElementById('workspaceFlowBtn').disabled = true;
    document.getElementById('workspaceFlowBtn').textContent = '⏳ Generando...';
    document.getElementById('workspaceFlowResult').textContent = 'Generando tabla de rodaje...';
    document.getElementById('workspaceFlowResult').classList.remove('empty');
    
    await fetch('/api/flow/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            scene_content: currentWorkspaceContent
        })
    });
});

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;
        
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        document.getElementById(tabName + 'TabContent').classList.add('active');
    });
});

// Load experts
async function loadExperts() {
    const response = await fetch('/api/experts');
    const experts = await response.json();
    const grid = document.getElementById('expertsGrid');
    
    grid.innerHTML = Object.entries(experts).map(([id, expert]) => `
        <div class="card" onclick="selectExpert('${id}', '${expert.name}')">
            <div class="card-icon">${expert.icon}</div>
            <div class="card-title">${expert.name}</div>
            <div class="card-description">${expert.description}</div>
        </div>
    `).join('');
}

function selectExpert(id, name) {
    selectedExpert = id;
    document.getElementById('expertWorkspace').classList.remove('hidden');
    document.getElementById('expertTitle').textContent = name;
    document.getElementById('expertResult').textContent = 'Esperando ejecución...';
    document.getElementById('expertResult').classList.add('empty');
}

document.getElementById('runExpertBtn')?.addEventListener('click', async () => {
    if (!selectedExpert) return;
    
    const input = document.getElementById('expertInput').value;
    if (!input.trim()) {
        alert('Ingresa un input');
        return;
    }
    
    document.getElementById('runExpertBtn').disabled = true;
    document.getElementById('expertResult').textContent = 'Procesando...';
    document.getElementById('expertResult').classList.remove('empty');
    
    await fetch('/api/expert/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ expert: selectedExpert, input })
    });
});

// Load projects
async function loadProjects() {
    const response = await fetch('/api/projects');
    const projects = await response.json();
    const grid = document.getElementById('projectsGrid');
    
    if (projects.length === 0) {
        grid.innerHTML = '<p style="color: #999;">No hay proyectos aún</p>';
        return;
    }
    
    grid.innerHTML = projects.map(p => `
        <div class="card" style="background: white; color: var(--dark); border: 2px solid #e0e0e0;">
            <div class="card-title">${p.id}</div>
            <div class="card-meta" style="color: #666;">
                ${p.formato} • ${p.estructura}<br>
                ${new Date(p.created * 1000).toLocaleString('es-CL')}
            </div>
        </div>
    `).join('');
}

// File upload
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

uploadZone?.addEventListener('click', () => fileInput.click());

fileInput?.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (file) {
        const formData = new FormData();
        formData.append('file', file);
        
        addLog(`📤 Subiendo: ${file.name}`, 'info');
        
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            addLog('✅ Archivo subido', 'success');
            document.getElementById('analysisArea').classList.remove('hidden');
            
            await fetch('/api/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ filepath: data.filepath, analysis_type: 'full' })
            });
        }
    }
});

socket.on('analysis_update', (data) => {
    document.getElementById('analysisResult').textContent = data.content;
    document.getElementById('analysisResult').classList.remove('empty');
});

function addLog(message, type = 'output') {
    const line = document.createElement('div');
    line.className = `log-line log-${type}`;
    line.textContent = message;
    logConsole.appendChild(line);
    logConsole.scrollTop = logConsole.scrollHeight;
}

function addWorkspaceLog(message, type = 'output') {
    const line = document.createElement('div');
    line.className = `log-line log-${type}`;
    line.textContent = message;
    workspaceLog.appendChild(line);
    workspaceLog.scrollTop = workspaceLog.scrollHeight;
}

// Init
loadStructures();
loadExperts();
loadProjects();
