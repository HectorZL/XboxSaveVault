let allGames = [];
let currentGame = null;
let currentSlot = null;
let defaultBackupDir = '';

// DOM Elements
const gamesGrid = document.getElementById('gamesGrid');
const gameSearch = document.getElementById('gameSearch');
const statGamesCount = document.getElementById('statGamesCount');
const statSavesCount = document.getElementById('statSavesCount');
const statSlotsCount = document.getElementById('statSlotsCount');
const consoleLogs = document.getElementById('consoleLogs');

// Modals
const slotsModal = document.getElementById('slotsModal');
const injectModal = document.getElementById('injectModal');
const importBackupModal = document.getElementById('importBackupModal');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadGames();
  setupEventListeners();
});

function setupEventListeners() {
  document.getElementById('btnScan').addEventListener('click', () => {
    logActivity('[SCAN] Re-escaneando el sistema en busca de juegos y partidas...', 'info');
    loadGames();
  });

  document.getElementById('btnOpenBackups').addEventListener('click', () => {
    openFolder(defaultBackupDir);
  });

  document.getElementById('btnImportAnyBackup').addEventListener('click', () => {
    openImportModal();
  });

  document.getElementById('btnClearLogs').addEventListener('click', () => {
    consoleLogs.innerHTML = '';
  });

  gameSearch.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = allGames.filter(g => 
      g.name.toLowerCase().includes(q) || 
      (g.publisher && g.publisher.toLowerCase().includes(q)) ||
      (g.package_id && g.package_id.toLowerCase().includes(q))
    );
    renderGames(filtered);
  });

  // Modal actions
  document.getElementById('btnModalExportRaw').addEventListener('click', () => {
    if (currentGame) exportGameRaw(currentGame);
  });

  document.getElementById('btnModalExportBackup').addEventListener('click', () => {
    if (currentGame) exportGameBackup(currentGame);
  });

  document.getElementById('btnModalOpenFolder').addEventListener('click', () => {
    if (currentGame && currentGame.wgs_user_dirs && currentGame.wgs_user_dirs.length > 0) {
      openFolder(currentGame.wgs_user_dirs[0].path);
    } else if (currentGame && currentGame.wgs_root) {
      openFolder(currentGame.wgs_root);
    }
  });

  // Inject Slot
  document.getElementById('btnBrowseInjectFile').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-file-selector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'file', filter: 'Save Files (*.sav;*.dat;*.*)|*.sav;*.dat;*.*' })
      });
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('injectFilePath').value = data.selected_path;
      }
    } catch (err) {
      showToast('Error abriendo selector de archivos', 'error');
    }
  });

  document.getElementById('btnConfirmInject').addEventListener('click', async () => {
    const filePath = document.getElementById('injectFilePath').value.trim();
    if (!filePath) {
      showToast('Por favor selecciona un archivo de partida para inyectar', 'error');
      return;
    }
    if (!currentGame || !currentSlot) return;

    const userWgsDir = currentGame.wgs_user_dirs[0].path;
    logActivity(`[INJECT] Inyectando partida en ranura ${currentSlot.name}...`, 'info');

    try {
      const res = await fetch('/api/import/slot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_wgs_dir: userWgsDir,
          container_name: currentSlot.name,
          raw_file_path: filePath
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`¡Partida inyectada con éxito en ${currentSlot.name}!`, 'success');
        logActivity(`[SUCCESS] Ranura ${currentSlot.name} actualizada con nuevo blob (${data.new_size} bytes).`, 'success');
        closeModal('injectModal');
        closeModal('slotsModal');
        loadGames();
      } else {
        showToast(`Error: ${data.error}`, 'error');
        logActivity(`[ERROR] Falló la inyección: ${data.error}`, 'error');
      }
    } catch (err) {
      showToast('Error de conexión', 'error');
    }
  });

  // Restore Backup
  document.getElementById('btnBrowseBackupZip').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-file-selector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'file', filter: 'ZIP Backups (*.zip)|*.zip' })
      });
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('importZipPath').value = data.selected_path;
      }
    } catch (err) {
      showToast('Error abriendo selector de archivos', 'error');
    }
  });

  document.getElementById('btnConfirmRestore').addEventListener('click', async () => {
    const zipPath = document.getElementById('importZipPath').value.trim();
    const gameId = document.getElementById('importTargetGameSelect').value;
    if (!zipPath) {
      showToast('Selecciona un archivo .zip de backup', 'error');
      return;
    }
    const targetGame = allGames.find(g => g.id === gameId);
    if (!targetGame || !targetGame.wgs_user_dirs || targetGame.wgs_user_dirs.length === 0) {
      showToast('El juego seleccionado no tiene una estructura de guardado válida', 'error');
      return;
    }

    const targetWgsDir = targetGame.wgs_user_dirs[0].path;
    logActivity(`[RESTORE] Restaurando backup para ${targetGame.name}...`, 'info');

    try {
      const res = await fetch('/api/import/backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          backup_zip_path: zipPath,
          target_wgs_dir: targetWgsDir
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`¡Backup restaurado exitosamente en ${targetGame.name}!`, 'success');
        logActivity(`[SUCCESS] Partida restaurada en ${targetWgsDir}. Pre-backup creado en ${data.safety_backup || 'N/A'}`, 'success');
        closeModal('importBackupModal');
        loadGames();
      } else {
        showToast(`Error restaurando: ${data.error}`, 'error');
        logActivity(`[ERROR] Falló la restauración: ${data.error}`, 'error');
      }
    } catch (err) {
      showToast('Error en la restauración', 'error');
    }
  });
}

// Fetch Games
async function loadGames() {
  try {
    const res = await fetch('/api/games');
    const data = await res.json();
    if (data.success) {
      allGames = data.games;
      defaultBackupDir = data.default_backup_root;
      updateStats();
      renderGames(allGames);
      logActivity(`[SCAN] ${allGames.length} juegos procesados. Partidas listas.`, 'success');
    } else {
      showToast('Error al cargar juegos', 'error');
    }
  } catch (err) {
    showToast('No se pudo conectar con el backend local', 'error');
  }
}

function updateStats() {
  statGamesCount.textContent = allGames.length;
  const savesCount = allGames.filter(g => g.has_saves).length;
  statSavesCount.textContent = savesCount;
  
  let totalSlots = 0;
  allGames.forEach(g => {
    if (g.save_details && g.save_details.containers) {
      totalSlots += g.save_details.containers.length;
    }
  });
  statSlotsCount.textContent = totalSlots;
}

// Render Games Grid
function renderGames(games) {
  gamesGrid.innerHTML = '';
  if (games.length === 0) {
    gamesGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">
        No se encontraron juegos con los criterios de búsqueda.
      </div>
    `;
    return;
  }

  games.forEach(g => {
    const card = document.createElement('div');
    card.className = 'game-card';

    const logoHtml = g.logo_base64 
      ? `<img src="${g.logo_base64}" alt="${g.name}" class="game-logo">`
      : `<div class="game-logo-placeholder">🎮</div>`;

    const saveDetails = g.save_details;
    const saveCountText = saveDetails ? `${saveDetails.container_count} Ranuras (${saveDetails.total_size_kb} KB)` : 'Sin partidas detectadas';
    const lastSavedText = saveDetails ? saveDetails.last_saved : 'N/A';

    card.innerHTML = `
      <div class="game-card-header">
        ${logoHtml}
        <div class="game-meta">
          <div class="game-title" title="${g.name}">${g.name}</div>
          <div class="game-publisher">${g.publisher} &bull; v${g.version}</div>
          <div class="game-tags">
            <span class="tag ${g.is_installed ? 'tag-active' : ''}">${g.is_installed ? 'Instalado' : 'Solo Guardado'}</span>
            ${g.title_id ? `<span class="tag">TitleID: ${g.title_id}</span>` : ''}
            ${g.has_saves ? `<span class="tag tag-active">💾 Partidas WGS</span>` : ''}
          </div>
        </div>
      </div>

      <div class="game-save-info">
        <div class="save-info-row">
          <span class="save-info-label">Estado Partidas:</span>
          <span class="save-info-value" style="color: ${g.has_saves ? 'var(--xbox-neon)' : 'var(--text-muted)'}">${saveCountText}</span>
        </div>
        <div class="save-info-row">
          <span class="save-info-label">Último Guardado:</span>
          <span class="save-info-value">${lastSavedText}</span>
        </div>
        ${g.install_path ? `
        <div class="save-info-row">
          <span class="save-info-label">Instalación:</span>
          <span class="save-info-value" title="${g.install_path}">${g.install_path}</span>
        </div>` : ''}
      </div>

      <div class="game-actions">
        ${g.has_saves ? `
          <button class="btn btn-card-main" onclick="openSlotsModal('${g.id}')">
            🔍 Inspeccionar y Gestionar Ranuras (${saveDetails ? saveDetails.container_count : 0})
          </button>
          <button class="btn btn-secondary btn-sm" onclick="exportGameRawById('${g.id}')" title="Exportar partidas a archivos .sav legibles">
            📂 Exportar .SAV
          </button>
          <button class="btn btn-secondary btn-sm" onclick="exportGameBackupById('${g.id}')" title="Crear backup completo en ZIP">
            📦 Backup .ZIP
          </button>
        ` : `
          <button class="btn btn-secondary btn-sm" style="grid-column: span 2;" disabled>
            Sin partidas activas para exportar
          </button>
        `}
      </div>
    `;

    gamesGrid.appendChild(card);
  });
}

// Open Slots Modal
function openSlotsModal(gameId) {
  const game = allGames.find(g => g.id === gameId);
  if (!game) return;
  currentGame = game;

  document.getElementById('modalGameTitle').textContent = game.name;
  
  const metaHtml = `
    <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">
      <strong>Paquete:</strong> <code>${game.package_id || 'N/A'}</code><br>
      <strong>Directorio WGS:</strong> <code>${game.wgs_user_dirs && game.wgs_user_dirs[0] ? game.wgs_user_dirs[0].path : 'N/A'}</code>
    </div>
  `;
  document.getElementById('modalGameMeta').innerHTML = metaHtml;

  const slotsContainer = document.getElementById('slotsList');
  slotsContainer.innerHTML = '';

  const containers = game.save_details ? game.save_details.containers : [];
  if (containers.length === 0) {
    slotsContainer.innerHTML = '<div style="color: var(--text-muted);">No se encontraron contenedores de guardado.</div>';
  } else {
    containers.forEach(c => {
      const slotEl = document.createElement('div');
      slotEl.className = 'slot-item';

      const fileInfo = c.files && c.files[0] ? `${c.files[0].filename} (${(c.size / 1024).toFixed(1)} KB)` : `${(c.size / 1024).toFixed(1)} KB`;

      slotEl.innerHTML = `
        <div>
          <div class="slot-name">
            <span>💾 ${c.name}</span>
            <span class="tag">Seq ${c.seq}</span>
          </div>
          <div class="slot-sub">
            GUID: ${c.guid} &bull; ${fileInfo} &bull; Modificado: ${c.modified}
          </div>
        </div>
        <div class="slot-actions">
          <button class="btn btn-secondary btn-sm" onclick="openInjectModal('${c.name}')">
            🔄 Reemplazar / Inyectar
          </button>
        </div>
      `;
      slotsContainer.appendChild(slotEl);
    });
  }

  slotsModal.classList.add('active');
}

// Open Inject Modal
function openInjectModal(slotName) {
  if (!currentGame || !currentGame.save_details) return;
  const slot = currentGame.save_details.containers.find(c => c.name === slotName);
  if (!slot) return;
  currentSlot = slot;

  document.getElementById('injectSlotTitle').textContent = `Reemplazar Ranura: ${slot.name}`;
  document.getElementById('injectFilePath').value = '';
  injectModal.classList.add('active');
}

// Open Import Modal
function openImportModal() {
  const select = document.getElementById('importTargetGameSelect');
  select.innerHTML = '';

  const eligibleGames = allGames.filter(g => g.wgs_user_dirs && g.wgs_user_dirs.length > 0);
  if (eligibleGames.length === 0) {
    showToast('No hay juegos con WGS configurado en el sistema', 'error');
    return;
  }

  eligibleGames.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g.id;
    opt.textContent = `${g.name} (${g.package_id})`;
    select.appendChild(opt);
  });

  document.getElementById('importZipPath').value = '';
  importBackupModal.classList.add('active');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
}

// Export actions
async function exportGameRawById(gameId) {
  const game = allGames.find(g => g.id === gameId);
  if (game) exportGameRaw(game);
}

async function exportGameBackupById(gameId) {
  const game = allGames.find(g => g.id === gameId);
  if (game) exportGameBackup(game);
}

async function exportGameRaw(game) {
  if (!game.wgs_user_dirs || game.wgs_user_dirs.length === 0) {
    showToast('No se encontró directorio de guardado', 'error');
    return;
  }

  const userWgsDir = game.wgs_user_dirs[0].path;
  logActivity(`[EXPORT] Exportando archivos .SAV limpios para ${game.name}...`, 'info');

  try {
    const res = await fetch('/api/export/raw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_wgs_dir: userWgsDir,
        game_name: game.name
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`¡${data.file_count} partidas exportadas exitosamente!`, 'success');
      logActivity(`[SUCCESS] Exportadas ${data.file_count} partidas a ${data.export_dir}`, 'success');
      openFolder(data.export_dir);
    } else {
      showToast(`Error al exportar: ${data.error}`, 'error');
      logActivity(`[ERROR] ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Error de conexión con el servidor', 'error');
  }
}

async function exportGameBackup(game) {
  if (!game.wgs_user_dirs || game.wgs_user_dirs.length === 0) {
    showToast('No se encontró directorio de guardado', 'error');
    return;
  }

  const userWgsDir = game.wgs_user_dirs[0].path;
  logActivity(`[BACKUP] Generando backup .ZIP completo para ${game.name}...`, 'info');

  try {
    const res = await fetch('/api/export/backup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_wgs_dir: userWgsDir,
        game_name: game.name,
        game_meta: {
          name: game.name,
          package_id: game.package_id,
          title_id: game.title_id
        }
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast('¡Backup .ZIP creado con éxito!', 'success');
      logActivity(`[SUCCESS] Backup creado en: ${data.backup_path} (${(data.size / 1024).toFixed(1)} KB)`, 'success');
      openFolder(data.backup_path.substring(0, data.backup_path.lastIndexOf('\\')));
    } else {
      showToast(`Error: ${data.error}`, 'error');
      logActivity(`[ERROR] ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Error creando backup', 'error');
  }
}

async function openFolder(folderPath) {
  if (!folderPath) return;
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: folderPath })
    });
    const data = await res.json();
    if (data.success) {
      logActivity(`[EXPLORER] Carpeta abierta: ${folderPath}`, 'info');
    } else {
      showToast('No se pudo abrir la carpeta', 'error');
    }
  } catch (err) {
    showToast('Error abriendo carpeta', 'error');
  }
}

function logActivity(text, type = 'info') {
  const entry = document.createElement('div');
  entry.className = `log-entry log-${type}`;
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${text}`;
  consoleLogs.appendChild(entry);
  consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✅' : '⚠️'}</span>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4500);
}
