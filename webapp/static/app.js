// Configuración
const socket = io();
let currentView = 'generate';
let currentStructure = null;
let currentExpert = null;

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// NAVEGACIÓN
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initAutoDetect();
    initGenerateButton();
    initSocketListeners();
    loadStructures();
    loadExperts();
    loadProjects();
});

function initNavigation() {
    document.querySelectorAll('.nav-icon').forEach(icon => {
        icon.addEventListener('click', () => {
            const view = icon.dataset.view;
            switchView(view);
        });
    });
}

function switchView(view) {
    // Actualizar iconos de navegación
    document.querySelectorAll('.nav-icon').forEach(icon => {
        icon.classList.remove('active');
    });
    document.querySelector(`[data-view="${view}"]`)?.classList.add('active');
    
    // Actualizar vistas
    document.querySelectorAll('.view').forEach(v => {
        v.classList.remove('active');
    });
    
    const viewElement = document.getElementById(`${view}View`);
    if (viewElement) {
        viewElement.classList.add('active');
        currentView = view;
    }
    
    // Actualizar header
    const titles = {
        'generate': '🎬 Guion Experts Suite V2',
        'structures': '📖 Estructuras Narrativas',
        'experts': '🎯 Expertos Individuales',
        'analyze': '📄 Analizar PDF',
        'projects': '📁 Proyectos'
    };
    
    document.getElementById('headerTitle').textContent = titles[view] || titles['generate'];
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// AUTO-DETECCIÓN
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function initAutoDetect() {
    const autoDetect = document.getElementById('autoDetect');
    const manualControls = document.getElementById('manualControls');
    
    autoDetect.addEventListener('change', () => {
        if (autoDetect.checked) {
            manualControls.classList.add('hidden');
        } else {
            manualControls.classList.remove('hidden');
        }
    });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// GENERAR PROYECTO COMPLETO
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function initGenerateButton() {
    document.getElementById('generateBtn').addEventListener('click', generateProject);
}

async function generateProject() {
    const idea = document.getElementById('ideaInput').value.trim();
    
    if (!idea) {
        alert('Por favor ingresa una idea');
        return;
    }
    
    const autoDetect = document.getElementById('autoDetect').checked;
    const formato = document.getElementById('formatoSelect').value;
    const estructura = document.getElementById('estructuraSelect').value;
    
    // Limpiar consola
    document.getElementById('logConsole').innerHTML = '';
    
    // Enviar petición
    const response = await fetch('/api/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            idea: idea,
            auto_detect: autoDetect,
            formato: formato || null,
            estructura: estructura || null
        })
    });
    
    const data = await response.json();
    
    if (data.status === 'started') {
        addLog('info', '🚀 Generación iniciada...');
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ESTRUCTURAS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async function loadStructures() {
    try {
        const response = await fetch('/api/structures/all');
        const data = await response.json();
        
        const grid = document.getElementById('structuresGrid');
        grid.innerHTML = '';
        
        // Iterar por categorías
        for (const [category, structures] of Object.entries(data)) {
            // Header de categoría
            const header = document.createElement('div');
            header.className = 'category-header';
            header.innerHTML = `<h3>${getCategoryIcon(category)} ${getCategoryName(category)}</h3>`;
            grid.appendChild(header);
            
            // Estructuras de esta categoría
            for (const [key, structure] of Object.entries(structures)) {
                const card = createStructureCard(key, structure, category);
                grid.appendChild(card);
            }
        }
    } catch (error) {
        console.error('Error cargando estructuras:', error);
    }
}

function createStructureCard(key, structure, category) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.cursor = 'pointer';
    
    card.innerHTML = `
        <div class="card-icon">${getCategoryIcon(category)}</div>
        <div class="card-title">${structure.name}</div>
        <div class="card-description">${structure.description || ''}</div>
        <div class="card-meta">
            <span class="badge">${structure.beats || '?'} beats</span>
            <span class="badge">${structure.duration || 'Variable'}</span>
            ${structure.best_for ? `<span class="badge">${structure.best_for}</span>` : ''}
        </div>
    `;
    
    card.addEventListener('click', () => openStructureWorkspace(key, structure));
    
    return card;
}

function openStructureWorkspace(structureId, structure) {
    currentStructure = { id: structureId, ...structure };
    
    // Cambiar a vista de workspace
    switchView('structureWorkspace');
    
    // Actualizar título
    document.getElementById('workspaceStructureName').textContent = structure.name;
    
    // Limpiar input y resultado
    document.getElementById('workspaceInput').value = '';
    document.getElementById('workspaceResult').innerHTML = '<p class="empty">Ingresa tu idea y genera la estructura...</p>';
    document.getElementById('workspaceResult').classList.add('empty');
    document.getElementById('workspaceFlowResult').innerHTML = '<p class="empty">Primero genera la estructura</p>';
    document.getElementById('workspaceFlowResult').classList.add('empty');
    
    // Mostrar metadata
    const metaInfo = document.getElementById('workspaceMetaInfo');
    metaInfo.innerHTML = `
        <h4>${structure.name}</h4>
        <p><strong>Autor:</strong> ${structure.author || 'Clásico'}</p>
        <p><strong>Beats:</strong> ${structure.beats || '?'}</p>
        <p><strong>Duración:</strong> ${structure.duration || 'Variable'}</p>
        <p><strong>Mejor para:</strong> ${structure.best_for || 'General'}</p>
        <p style="color: #666; margin-top: 10px;">${structure.description || ''}</p>
    `;
    
    // Limpiar logs
    document.getElementById('workspaceLog').innerHTML = '';
    
    // Setup botón de generar
    document.getElementById('workspaceGenerateBtn').onclick = () => generateWithStructure();
    document.getElementById('workspaceFlowBtn').onclick = () => generateFlowTable();
}

async function generateWithStructure() {
    const input = document.getElementById('workspaceInput').value.trim();
    
    if (!input) {
        alert('Por favor ingresa una idea');
        return;
    }
    
    addWorkspaceLog('info', `🏗️ Generando con ${currentStructure.name}...`);
    
    // Limpiar resultado
    const resultDiv = document.getElementById('workspaceResult');
    resultDiv.innerHTML = '<p style="color: #999;">Generando...</p>';
    resultDiv.classList.add('empty');
    
    try {
        const response = await fetch('/api/structure/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                structure_id: currentStructure.id,
                input: input
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            addWorkspaceLog('success', '✅ Generación iniciada');
        }
    } catch (error) {
        addWorkspaceLog('error', `❌ Error: ${error.message}`);
    }
}

async function generateFlowTable() {
    const sceneContent = document.getElementById('workspaceResult').textContent;
    
    if (!sceneContent || sceneContent.includes('Esperando')) {
        alert('Primero genera la estructura');
        return;
    }
    
    addWorkspaceLog('info', '🎬 Generando tabla Director Flow...');
    
    const flowResultDiv = document.getElementById('workspaceFlowResult');
    flowResultDiv.innerHTML = '<p style="color: #999;">Generando tabla...</p>';
    flowResultDiv.classList.add('empty');
    
    try {
        const response = await fetch('/api/flow/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                scene_content: sceneContent
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            addWorkspaceLog('success', '✅ Generación Flow iniciada');
        }
    } catch (error) {
        addWorkspaceLog('error', `❌ Error: ${error.message}`);
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// EXPERTOS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async function loadExperts() {
    try {
        const response = await fetch('/api/experts');
        const experts = await response.json();
        
        const grid = document.getElementById('expertsGrid');
        grid.innerHTML = '';
        
        for (const [key, expert] of Object.entries(experts)) {
            const card = createExpertCard(key, expert);
            grid.appendChild(card);
        }
    } catch (error) {
        console.error('Error cargando expertos:', error);
    }
}

function createExpertCard(key, expert) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.cursor = 'pointer';
    
    card.innerHTML = `
        <div class="card-icon">${expert.icon}</div>
        <div class="card-title">${expert.name}</div>
        <div class="card-description">${expert.description}</div>
    `;
    
    card.addEventListener('click', () => openExpertWorkspace(key, expert));
    
    return card;
}

function openExpertWorkspace(expertId, expert) {
    currentExpert = { id: expertId, ...expert };
    
    // Mostrar workspace
    document.getElementById('expertWorkspace').classList.remove('hidden');
    document.getElementById('expertTitle').textContent = `${expert.icon} ${expert.name}`;
    
    // Limpiar
    document.getElementById('expertInput').value = '';
    document.getElementById('expertResult').innerHTML = '<p class="empty">Esperando input...</p>';
    document.getElementById('expertResult').classList.add('empty');
    
    // Scroll al workspace
    document.getElementById('expertWorkspace').scrollIntoView({ behavior: 'smooth' });
}

document.getElementById('runExpertBtn')?.addEventListener('click', async () => {
    const input = document.getElementById('expertInput').value.trim();
    
    if (!input) {
        alert('Por favor ingresa un input');
        return;
    }
    
    const resultDiv = document.getElementById('expertResult');
    resultDiv.innerHTML = '<p style="color: #999;">Procesando...</p>';
    resultDiv.classList.add('empty');
    
    try {
        const response = await fetch('/api/expert/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                expert: currentExpert.id,
                input: input
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            addLog('success', `✅ Ejecutando ${currentExpert.name}`);
        }
    } catch (error) {
        resultDiv.innerHTML = `<p style="color: var(--error);">Error: ${error.message}</p>`;
    }
});

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// PROYECTOS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const projects = await response.json();
        
        const grid = document.getElementById('projectsGrid');
        grid.innerHTML = '';
        
        if (projects.length === 0) {
            grid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #999;">No hay proyectos aún</p>';
            return;
        }
        
        projects.forEach(project => {
            const card = createProjectCard(project);
            grid.appendChild(card);
        });
    } catch (error) {
        console.error('Error cargando proyectos:', error);
    }
}

function createProjectCard(project) {
    const card = document.createElement('div');
    card.className = 'card';
    
    const date = new Date(project.created * 1000);
    
    card.innerHTML = `
        <div class="card-icon">📂</div>
        <div class="card-title">${project.id}</div>
        <div class="card-meta">
            <span class="badge">📺 ${project.formato}</span>
            <span class="badge">📖 ${project.estructura}</span>
            <span class="badge">📅 ${date.toLocaleDateString()}</span>
        </div>
    `;
    
    return card;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// TABS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        
        // Actualizar botones
        btn.parentElement.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Actualizar contenido
        btn.closest('.form-section').querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`${tab}TabContent`).classList.add('active');
    });
});

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// WEBSOCKETS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function initSocketListeners() {
    socket.on('connect', () => {
        console.log('Conectado al servidor');
        document.getElementById('statusBadge').textContent = '● Conectado';
        document.getElementById('statusBadge').style.background = 'var(--success)';
    });
    
    socket.on('disconnect', () => {
        console.log('Desconectado');
        document.getElementById('statusBadge').textContent = '● Desconectado';
        document.getElementById('statusBadge').style.background = 'var(--error)';
    });
    
    socket.on('log', (data) => {
        addLog(data.type, data.message);
    });
    
    socket.on('structure_result', (data) => {
        const resultDiv = document.getElementById('workspaceResult');
        resultDiv.textContent = data.content;
        resultDiv.classList.remove('empty');
        addWorkspaceLog('success', '✅ Estructura generada');
    });
    
    socket.on('flow_completed', (data) => {
        const flowDiv = document.getElementById('workspaceFlowResult');
        flowDiv.textContent = data.tabla;
        flowDiv.classList.remove('empty');
        addWorkspaceLog('success', '✅ Tabla Flow completada');
    });
    
    socket.on('expert_update', (data) => {
        const resultDiv = document.getElementById('expertResult');
        resultDiv.textContent = data.content;
        resultDiv.classList.remove('empty');
    });
    
    socket.on('expert_completed', (data) => {
        addLog('success', `✅ ${currentExpert?.name || 'Experto'} completado`);
    });
    
    socket.on('generation_completed', (data) => {
        if (data.returncode === 0) {
            addLog('success', '✅ Generación completada exitosamente');
            loadProjects(); // Recargar lista de proyectos
        } else {
            addLog('error', '❌ Error en la generación');
        }
    });
}

function addLog(type, message) {
    const console = document.getElementById('logConsole');
    const line = document.createElement('div');
    line.className = `log-line log-${type}`;
    line.textContent = message;
    console.appendChild(line);
    console.scrollTop = console.scrollHeight;
}

function addWorkspaceLog(type, message) {
    const console = document.getElementById('workspaceLog');
    const line = document.createElement('div');
    line.className = `log-line log-${type}`;
    line.textContent = message;
    console.appendChild(line);
    console.scrollTop = console.scrollHeight;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// UTILIDADES
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function getCategoryIcon(category) {
    const icons = {
        'hollywood': '🎬',
        'mythic': '🗿',
        'tv': '📺',
        'nonlinear': '🔀',
        'international': '🌏',
        'experimental': '🧪',
        'short': '⚡',
        'documentary': '🎥',
        'theater': '🎭'
    };
    return icons[category] || '📖';
}

function getCategoryName(category) {
    const names = {
        'hollywood': 'Hollywood Clásico',
        'mythic': 'Viaje Mítico',
        'tv': 'TV y Series',
        'nonlinear': 'No Lineal',
        'international': 'Internacional',
        'experimental': 'Experimental',
        'short': 'Formato Corto',
        'documentary': 'Documental',
        'theater': 'Teatro'
    };
    return names[category] || category;
}

// Heartbeat
setInterval(() => {
    socket.emit('ping');
}, 25000);
