// Configuración
const hasSocketIO = typeof window.io === 'function';
const socket = hasSocketIO ? window.io() : {
    on: () => {},
    emit: () => {}
};
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
    initAnalysis();
});

function initNavigation() {
    document.querySelectorAll('.nav-icon').forEach(icon => {
        icon.addEventListener('click', () => {
            const view = icon.dataset.view;
            if (view) {
                switchView(view);
            }
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

    if (!autoDetect || !manualControls) return;

    const syncManualControls = () => {
        manualControls.classList.toggle('hidden', autoDetect.checked);
    };

    autoDetect.addEventListener('change', syncManualControls);
    syncManualControls();
    autoDetect.dataset.bound = '1';
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// GENERAR PROYECTO COMPLETO
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function initGenerateButton() {
    const generateBtn = document.getElementById('generateBtn');
    if (!generateBtn) return;
    if (generateBtn.dataset.bound === '1') return;
    generateBtn.addEventListener('click', generateProject);
    generateBtn.dataset.bound = '1';
}

async function generateProject() {
    const ideaInput = document.getElementById('ideaInput');
    const generateBtn = document.getElementById('generateBtn');
    const logConsole = document.getElementById('logConsole');
    const autoDetectInput = document.getElementById('autoDetect');
    const formatoSelect = document.getElementById('formatoSelect');
    const estructuraSelect = document.getElementById('estructuraSelect');

    if (!ideaInput || !generateBtn || !logConsole || !autoDetectInput || !formatoSelect || !estructuraSelect) {
        alert('Falta configuración de interfaz. Recarga la página.');
        return;
    }

    const idea = ideaInput.value.trim();

    if (!idea) {
        alert('Por favor ingresa una idea');
        return;
    }

    const autoDetect = autoDetectInput.checked;
    const formato = formatoSelect.value;
    const estructura = estructuraSelect.value;

    // Limpiar consola
    logConsole.innerHTML = '';

    generateBtn.disabled = true;
    generateBtn.textContent = '⏳ Iniciando...';
    addLog('info', '⏳ Enviando solicitud de generación...');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                idea: idea,
                auto_detect: autoDetect,
                formato: formato || null,
                estructura: estructura || null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            addLog('error', `❌ Error ${response.status}: ${data.error || 'No se pudo iniciar la generación'}`);
            return;
        }

        if (data.status === 'started') {
            addLog('success', '🚀 Generación iniciada...');
        } else {
            addLog('error', `❌ Respuesta inesperada: ${JSON.stringify(data)}`);
        }
    } catch (error) {
        addLog('error', `❌ Fallo de conexión al generar: ${error.message}`);
    } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = '🚀 Generar Proyecto';
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
            headers: { 'Content-Type': 'application/json' },
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scene_content: sceneContent,
                format: 'json' // Default to JSON for Auto Flow
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
            headers: { 'Content-Type': 'application/json' },
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
    if (!hasSocketIO) {
        console.warn('Socket.IO no cargado. UI en modo sin tiempo real.');
        const statusBadge = document.getElementById('statusBadge');
        if (statusBadge) {
            statusBadge.textContent = '● Sin Socket';
            statusBadge.style.background = 'var(--error)';
        }
        return;
    }

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

        if (data.format === 'json') {
            try {
                const shots = JSON.parse(data.tabla);
                let html = '<div style="margin-bottom: 10px;"><button class="btn btn-primary" onclick="downloadFlowJson()">⬇️ Descargar JSON (Auto Flow)</button></div>';
                html += '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;">';
                html += '<thead><tr style="background: #f5f5f5; text-align: left;">';
                html += '<th style="padding: 8px; border: 1px solid #ddd;">#</th>';
                html += '<th style="padding: 8px; border: 1px solid #ddd;">Prompt</th>';
                html += '<th style="padding: 8px; border: 1px solid #ddd;">Control</th>';
                html += '<th style="padding: 8px; border: 1px solid #ddd;">Modo</th>';
                html += '</tr></thead><tbody>';

                shots.forEach(shot => {
                    html += '<tr>';
                    html += `<td style="padding: 8px; border: 1px solid #ddd;">${shot.shot_number}</td>`;
                    html += `<td style="padding: 8px; border: 1px solid #ddd; font-size: 0.9em;">${shot.prompt}</td>`;
                    html += `<td style="padding: 8px; border: 1px solid #ddd;">${shot.camera_control}</td>`;
                    html += `<td style="padding: 8px; border: 1px solid #ddd;">${shot.mode}</td>`;
                    html += '</tr>';
                });

                html += '</tbody></table>';

                // Guardar JSON globalmente para descarga
                window.lastFlowJson = JSON.stringify(shots, null, 2);
                flowDiv.innerHTML = html;

            } catch (e) {
                console.error("Error parsing JSON", e);
                flowDiv.textContent = data.tabla; // Fallback
            }
        } else {
            flowDiv.textContent = data.tabla;
        }

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

            // Si el export a OpenMontage se realizó, mostrar botones de acción
            if (data.openmontage && data.openmontage.project_root) {
                renderOpenMontageActions(data.openmontage);
            } else if (data.project) {
                // Sin OpenMontage auto-export: ofrecer export manual
                renderOpenMontageExportButton(data.project);
            }
        } else {
            addLog('error', `❌ Error en la generación: ${data.error || 'desconocido'}`);
        }
    });

    socket.on('analysis_completed', (data) => {
        const resultDiv = document.getElementById('analysisResult');
        if (data.success) {
            resultDiv.innerHTML = `<pre style="white-space: pre-wrap; font-family: sans-serif;">${data.report}</pre>`;
            resultDiv.classList.remove('empty');

            const btn = document.createElement('button');
            btn.className = 'btn btn-primary';
            btn.textContent = '📂 Abrir Carpeta de Análisis';
            btn.style.marginTop = '20px';
            btn.onclick = () => {
                fetch(`/api/project/${data.path.split('/').pop()}/open`, { method: 'POST' });
            };
            resultDiv.appendChild(btn);

        } else {
            resultDiv.innerHTML = '<p style="color: var(--error);">❌ Error en el análisis</p>';
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
        'classic_hollywood': '🎬',
        'mythic_journey': '🗿',
        'episodic_tv': '📺',
        'non_linear': '🔀',
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
        'classic_hollywood': 'Hollywood Clásico',
        'mythic_journey': 'Viaje Mítico',
        'episodic_tv': 'TV y Series',
        'non_linear': 'No Lineal',
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

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// PROYECTOS - MEJORADO
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const projects = await response.json();

        const grid = document.getElementById('projectsGrid');
        grid.innerHTML = '';

        if (projects.length === 0) {
            grid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #999;">No hay proyectos aún. ¡Genera tu primer guion!</p>';
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
    card.style.cursor = 'pointer';

    const date = new Date(project.created * 1000);

    card.innerHTML = `
        <div class="card-icon">📂</div>
        <div class="card-title">${project.id}</div>
        <div class="card-meta">
            <span class="badge">📺 ${project.formato}</span>
            <span class="badge">📖 ${project.estructura}</span>
            <span class="badge">📄 ${project.file_count} archivos</span>
            <span class="badge">📅 ${date.toLocaleDateString()}</span>
        </div>
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button class="btn btn-secondary" style="flex: 1; padding: 8px;" onclick="openProjectFolder('${project.id}', event)">
                📁 Abrir Carpeta
            </button>
            <button class="btn btn-primary" style="flex: 1; padding: 8px;" onclick="viewProjectFiles('${project.id}', event)">
                👁️ Ver Archivos
            </button>
        </div>
    `;

    return card;
}

async function openProjectFolder(projectId, event) {
    event.stopPropagation();

    try {
        const response = await fetch(`/api/project/${projectId}/open`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            addLog('success', `✅ Carpeta abierta: ${projectId}`);
        } else {
            addLog('error', `❌ Error: ${data.error}`);
        }
    } catch (error) {
        addLog('error', `❌ Error abriendo carpeta: ${error.message}`);
    }
}

async function viewProjectFiles(projectId, event) {
    event.stopPropagation();

    try {
        const response = await fetch(`/api/project/${projectId}/files`);
        const data = await response.json();

        if (data.error) {
            alert(`Error: ${data.error}`);
            return;
        }

        showProjectFilesModal(projectId, data);
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

function showProjectFilesModal(projectId, data) {
    // Crear modal
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 20px;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
        background: white;
        border-radius: 12px;
        max-width: 800px;
        width: 100%;
        max-height: 80vh;
        overflow-y: auto;
        padding: 30px;
    `;

    let filesHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="margin: 0;">📂 ${projectId}</h2>
            <button onclick="this.closest('[style*=fixed]').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">✕</button>
        </div>
        <p style="color: #666; margin-bottom: 20px;">Total: ${data.total_files} archivos</p>
    `;

    // Organizar por carpeta
    for (const [folder, files] of Object.entries(data.folders)) {
        filesHTML += `
            <div style="margin-bottom: 20px;">
                <h3 style="background: var(--primary); color: white; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
                    📁 ${folder}
                </h3>
                <div style="display: grid; gap: 10px;">
        `;

        files.forEach(file => {
            const icon = getFileIcon(file.extension);
            filesHTML += `
                <div style="background: #f8f9fa; padding: 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1;">
                        <strong>${icon} ${file.name}</strong>
                        <div style="color: #666; font-size: 0.85em;">${file.size_human}</div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        ${file.extension === '.txt' || file.extension === '.md' ?
                    `<button onclick="viewFile('${projectId}', '${file.path}')" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.85em;">👁️ Ver</button>` : ''}
                        <button onclick="downloadFile('${projectId}', '${file.path}')" class="btn btn-primary" style="padding: 6px 12px; font-size: 0.85em;">⬇️ Descargar</button>
                    </div>
                </div>
            `;
        });

        filesHTML += `
                </div>
            </div>
        `;
    }

    modalContent.innerHTML = filesHTML;
    modal.appendChild(modalContent);
    document.body.appendChild(modal);

    // Cerrar al hacer click fuera
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

async function viewFile(projectId, filePath) {
    try {
        const response = await fetch(`/api/project/${projectId}/view/${filePath}`);
        const data = await response.json();

        if (data.error) {
            alert(`Error: ${data.error}`);
            return;
        }

        showFileContentModal(data);
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

function showFileContentModal(data) {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10001;
        padding: 20px;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText = `
        background: white;
        border-radius: 12px;
        max-width: 900px;
        width: 100%;
        max-height: 80vh;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    `;

    modalContent.innerHTML = `
        <div style="padding: 20px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h3 style="margin: 0;">📄 ${data.filename}</h3>
                <p style="margin: 5px 0 0 0; color: #666; font-size: 0.9em;">${data.lines} líneas • ${data.size} bytes</p>
            </div>
            <button onclick="this.closest('[style*=fixed]').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">✕</button>
        </div>
        <div style="flex: 1; overflow-y: auto; padding: 20px;">
            <pre style="margin: 0; white-space: pre-wrap; font-family: 'Courier New', monospace; font-size: 0.9em; line-height: 1.6;">${escapeHtml(data.content)}</pre>
        </div>
    `;

    modal.appendChild(modalContent);
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

function downloadFile(projectId, filePath) {
    window.open(`/api/project/${projectId}/download/${filePath}`, '_blank');
}

function getFileIcon(extension) {
    const icons = {
        '.txt': '📄',
        '.md': '📝',
        '.json': '📋',
        '.py': '🐍',
        '.sh': '⚙️',
        '.html': '🌐',
        '.jpg': '🖼️',
        '.png': '🖼️',
        '.pdf': '📕'
    };
    return icons[extension] || '📄';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ANÁLISIS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function initAnalysis() {
    const dropZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');

    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--primary)';
        dropZone.style.background = 'rgba(102, 126, 234, 0.1)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#e0e0e0';
        dropZone.style.background = 'transparent';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#e0e0e0';
        dropZone.style.background = 'transparent';

        if (e.dataTransfer.files.length) {
            uploadFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            uploadFile(fileInput.files[0]);
        }
    });
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    document.getElementById('analysisArea').classList.remove('hidden');
    const resultDiv = document.getElementById('analysisResult');
    resultDiv.innerHTML = '<p style="color: #999;">Subiendo y analizando...</p>';
    resultDiv.classList.add('empty');

    try {
        const response = await fetch('/api/analyze/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'started') {
            addLog('info', `📄 Subido: ${data.filename}`);
        } else {
            resultDiv.innerHTML = `<p style="color: var(--error);">Error: ${data.error}</p>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<p style="color: var(--error);">Error: ${error.message}</p>`;
    }
}

function downloadFlowJson() {
    if (!window.lastFlowJson) return;
    const blob = new Blob([window.lastFlowJson], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'auto_flow_sequence.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// --- OpenMontage bridge UI ------------------------------------------------

function renderOpenMontageActions(om) {
    const consoleEl = document.getElementById('logConsole');
    if (!consoleEl) return;

    const box = document.createElement('div');
    box.className = 'log-line log-success';
    box.style.cssText = 'margin-top:12px; padding:12px; border:1px solid #22D3EE; border-radius:8px; background:rgba(34,211,238,0.06);';
    box.innerHTML = `
        <div style="font-weight:600; margin-bottom:6px;">🎬 OpenMontage — listo</div>
        <div style="font-size:12px; opacity:0.85; margin-bottom:8px;">
            Proyecto: <code>${om.project_root.split('/').pop()}</code><br>
            Brief + Script + Scene Plan generados (schemas oficiales)
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="copyToClipboard('${(om.cuts || '').replace(/'/g, "\\'")}')">
                📋 Copiar ruta cuts.json
            </button>
            <button class="btn btn-secondary" onclick="openOpenMontageInstructions('${om.project_root.replace(/'/g, "\\'")}')">
                📖 Cómo renderizar
            </button>
        </div>
    `;
    consoleEl.appendChild(box);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

function renderOpenMontageExportButton(projectId) {
    const consoleEl = document.getElementById('logConsole');
    if (!consoleEl || !projectId) return;
    const box = document.createElement('div');
    box.className = 'log-line log-info';
    box.style.cssText = 'margin-top:8px;';
    box.innerHTML = `
        <button class="btn btn-secondary" onclick="manualExportOpenMontage('${projectId}')">
            🎬 Exportar a OpenMontage
        </button>
    `;
    consoleEl.appendChild(box);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

async function manualExportOpenMontage(projectId) {
    addLog('info', `🎬 Exportando ${projectId} a OpenMontage…`);
    try {
        const response = await fetch(`/api/openmontage/export/${projectId}`, { method: 'POST' });
        const data = await response.json();
        if (data.status === 'ok') {
            addLog('success', `✅ Exportado: ${data.project_root.split('/').pop()}`);
            renderOpenMontageActions({
                project_root: data.project_root,
                cuts: data.artifacts && data.artifacts.cuts,
            });
        } else {
            addLog('error', `❌ ${data.error || 'export falló'}`);
        }
    } catch (e) {
        addLog('error', `❌ ${e.message}`);
    }
}

function copyToClipboard(text) {
    if (!text) return;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text);
        addLog('success', `📋 Copiado: ${text}`);
    } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        addLog('success', `📋 Copiado`);
    }
}

function openOpenMontageInstructions(projectRoot) {
    const cmd = `cd "${projectRoot.replace('/projects/', '/').replace(/\/[^/]+$/, '')}" && python render_demo.py --props "${projectRoot}/remotion-cuts.json"`;
    const msg = `Para renderizar con Remotion (zero-key):\n\n${cmd}\n\nO abrí OpenMontage en Claude Code / Cursor y pedile continuar el pipeline desde el 'stages/' del proyecto.`;
    alert(msg);
}
