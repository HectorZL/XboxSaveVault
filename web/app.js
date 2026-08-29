let allData = {
  xbox: [],
  steam: [],
  epic: [],
  local_saves: []
};
let allGames = [];
let currentGame = null;
let currentSlot = null;
let defaultBackupDir = '';

// DOM Elements
const gamesGrid = document.getElementById('gamesGrid');
const steamGrid = document.getElementById('steamGrid');
const epicGrid = document.getElementById('epicGrid');
const localGrid = document.getElementById('localGrid');

const gameSearch = document.getElementById('gameSearch');
const steamSearch = document.getElementById('steamSearch');
const epicSearch = document.getElementById('epicSearch');
const localSearch = document.getElementById('localSearch');

const statGamesCount = document.getElementById('statGamesCount');
const statSavesCount = document.getElementById('statSavesCount');
const statSlotsCount = document.getElementById('statSlotsCount');
const consoleLogs = document.getElementById('consoleLogs');

const countXbox = document.getElementById('countXbox');
const countSteam = document.getElementById('countSteam');
const countEpic = document.getElementById('countEpic');
const countLocal = document.getElementById('countLocal');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadAllPlatforms();
  setupEventListeners();
  setupTabs();
  setupBridge();
  setupSettings();
});

function setupTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.platform-view').forEach(v => v.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `view${tab.dataset.tab.charAt(0).toUpperCase() + tab.dataset.tab.slice(1)}`;
      const targetView = document.getElementById(targetId);
      if (targetView) targetView.classList.add('active');
    });
  });
}

function setupEventListeners() {
  document.getElementById('btnScan').addEventListener('click', () => {
    logActivity('[SCAN] Re-escaneando el sistema en busca de juegos y partidas...', 'info');
    loadAllPlatforms();
  });

  document.getElementById('btnOpenBackups').addEventListener('click', () => {
    openFolder(defaultBackupDir);
  });

  document.getElementById('btnImportAnyBackup').addEventListener('click', () => {
    openImportModal();
  });

  document.getElementById('btnOpenToolsModal').addEventListener('click', () => {
    openToolsModal();
  });

  // Real-time Search Filters
  if (gameSearch) {
    gameSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = (allData.xbox || []).filter(g => g.name.toLowerCase().includes(q) || (g.publisher && g.publisher.toLowerCase().includes(q)));
      renderGames(filtered);
    });
  }

  if (steamSearch) {
    steamSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = (allData.steam || []).filter(g => g.name.toLowerCase().includes(q) || String(g.appid).includes(q));
      renderSteamGames(filtered);
    });
  }

  if (epicSearch) {
    epicSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = (allData.epic || []).filter(g => g.name.toLowerCase().includes(q));
      renderEpicGames(filtered);
    });
  }

  if (localSearch) {
    localSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = (allData.local_saves || []).filter(g => g.name.toLowerCase().includes(q) || (g.developer && g.developer.toLowerCase().includes(q)));
      renderLocalGames(filtered);
    });
  }

  // Tools Modal File Browsers & Actions
  document.getElementById('btnBrowseInspectFile').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-file-selector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'file', filter: 'Save Files (*.sav;*.dat;*.*)|*.sav;*.dat;*.*' })
      });
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('inspectFilePath').value = data.selected_path;
      }
    } catch (err) {
      showToast('Error abriendo selector de archivos', 'error');
    }
  });

  document.getElementById('btnRunInspect').addEventListener('click', async () => {
    const filePath = document.getElementById('inspectFilePath').value.trim();
    if (!filePath) {
      showToast('Selecciona un archivo para inspeccionar', 'error');
      return;
    }
    const resultBox = document.getElementById('inspectResult');
    resultBox.style.display = 'block';
    resultBox.innerHTML = 'Analizando cabecera...';

    try {
      const res = await fetch('/api/tools/inspect-save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath })
      });
      const data = await res.json();
      if (data.success) {
        const info = data.info;
        resultBox.innerHTML = `
          <strong>Archivo:</strong> ${info.file_name} (${info.size_kb} KB)<br>
          <strong>Formato:</strong> ${info.format}<br>
          ${info.engine_version ? `<strong>Versión de Motor:</strong> ${info.engine_version}<br>` : ''}
          ${info.save_game_version ? `<strong>Versión SaveGame:</strong> ${info.save_game_version}<br>` : ''}
          <strong>IDs Detectados:</strong> ${info.detected_ids.length > 0 ? info.detected_ids.join(', ') : 'Ningún SteamID conocido encontrado en texto plano'}
        `;
        logActivity(`[INSPECT] Archivo ${info.file_name} analizado: ${info.format}`, 'info');
      } else {
        resultBox.innerHTML = `<span style="color: var(--accent-red)">Error: ${data.error}</span>`;
      }
    } catch (err) {
      resultBox.innerHTML = `<span style="color: var(--accent-red)">Error de conexión</span>`;
    }
  });

  document.getElementById('btnBrowsePatchFile').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-file-selector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'file', filter: 'Save Files (*.sav;*.dat;*.*)|*.sav;*.dat;*.*' })
      });
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('patchInputFile').value = data.selected_path;
      }
    } catch (err) {
      showToast('Error abriendo selector de archivos', 'error');
    }
  });

  document.getElementById('btnRunPatchId').addEventListener('click', async () => {
    const file = document.getElementById('patchInputFile').value.trim();
    const oldId = document.getElementById('patchOldId').value.trim();
    const newId = document.getElementById('patchNewId').value.trim();

    if (!file || !oldId || !newId) {
      showToast('Debes indicar el archivo, el ID de origen y el ID de destino', 'error');
      return;
    }

    try {
      const res = await fetch('/api/tools/patch-id', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_file: file, old_id: oldId, new_id: newId })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`¡Parche aplicado! (${data.replacements_count} coincidencias reemplazadas)`, 'success');
        logActivity(`[PATCH] ${data.replacements_count} ocurrencias de ID reemplazadas en ${file}`, 'success');
      } else {
        showToast(`Error: ${data.error}`, 'error');
      }
    } catch (err) {
      showToast('Error aplicando parche', 'error');
    }
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
        loadAllPlatforms();
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
        loadAllPlatforms();
      } else {
        showToast(`Error restaurando: ${data.error}`, 'error');
        logActivity(`[ERROR] Falló la restauración: ${data.error}`, 'error');
      }
    } catch (err) {
      showToast('Error en la restauración', 'error');
    }
  });
}

// Fetch All Platforms Data
async function loadAllPlatforms() {
  try {
    const res = await fetch('/api/platforms');
    const data = await res.json();
    if (data.success) {
      allData = data.data;
      allGames = allData.xbox;
      defaultBackupDir = data.default_backup_root;

      updateStats();
      renderGames(allData.xbox);
      renderSteamGames(allData.steam);
      renderEpicGames(allData.epic);
      renderLocalGames(allData.local_saves);
      updateBridgeDropdowns();

      logActivity(`[SCAN] Escaneo completo: ${allData.counts.xbox} Xbox, ${allData.counts.steam} Steam, ${allData.counts.epic} Epic, ${allData.counts.local_saves} Locales.`, 'success');
    } else {
      showToast('Error al cargar datos de plataformas', 'error');
    }
  } catch (err) {
    showToast('No se pudo conectar con el backend local', 'error');
  }
}

function updateStats() {
  const totalGames = (allData.xbox ? allData.xbox.length : 0) + 
                     (allData.steam ? allData.steam.length : 0) + 
                     (allData.epic ? allData.epic.length : 0) +
                     (allData.local_saves ? allData.local_saves.length : 0);
  statGamesCount.textContent = totalGames;

  let totalSaves = 0;
  if (allData.xbox) totalSaves += allData.xbox.filter(g => g.has_saves).length;
  if (allData.steam) totalSaves += allData.steam.filter(g => g.has_saves).length;
  if (allData.epic) totalSaves += allData.epic.length;
  if (allData.local_saves) totalSaves += allData.local_saves.length;
  statSavesCount.textContent = totalSaves;

  let totalSlots = 0;
  if (allData.xbox) {
    allData.xbox.forEach(g => {
      if (g.save_details && g.save_details.containers) totalSlots += g.save_details.containers.length;
    });
  }
  statSlotsCount.textContent = totalSlots;

  if (countXbox) countXbox.textContent = allData.xbox ? allData.xbox.length : 0;
  if (countSteam) countSteam.textContent = allData.steam ? allData.steam.length : 0;
  if (countEpic) countEpic.textContent = allData.epic ? allData.epic.length : 0;
  if (countLocal) countLocal.textContent = allData.local_saves ? allData.local_saves.length : 0;
}

// Helper to render Full-Width Hero Cover Banner
function getGameCoverBannerHtml(game, defaultEmoji = '🎮', pillClass = 'local', pillText = 'PC Save') {
  const coverUrl = game.cover_url || (game.appid ? `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.appid}/header.jpg` : null);
  const logoBase64 = game.logo_base64;

  if (coverUrl) {
    return `
      <div class="game-card-banner">
        <img src="${coverUrl}" alt="${game.name}" class="game-cover-img" onerror="this.parentElement.innerHTML='<div class=\\'game-banner-fallback\\'>${defaultEmoji}</div><div class=\\'game-card-banner-overlay\\'></div><span class=\\'platform-pill ${pillClass}\\'>${pillText}</span>'">
        <div class="game-card-banner-overlay"></div>
        <span class="platform-pill ${pillClass}">${pillText}</span>
      </div>
    `;
  }

  if (logoBase64) {
    return `
      <div class="game-card-banner" style="background: #0f172a;">
        <img src="${logoBase64}" alt="${game.name}" class="game-cover-img" style="object-fit: contain; padding: 18px;">
        <div class="game-card-banner-overlay"></div>
        <span class="platform-pill ${pillClass}">${pillText}</span>
      </div>
    `;
  }

  return `
    <div class="game-card-banner" data-cover-pending="${game.name}" data-pill-class="${pillClass}" data-pill-text="${pillText}" data-emoji="${defaultEmoji}">
      <div class="game-banner-fallback">${defaultEmoji}</div>
      <div class="game-card-banner-overlay"></div>
      <span class="platform-pill ${pillClass}">${pillText}</span>
    </div>
  `;
}

// Background cover resolver for items without covers
function resolveMissingCovers() {
  document.querySelectorAll('[data-cover-pending]').forEach(async (el) => {
    const gameName = el.dataset.coverPending;
    if (!gameName) return;
    try {
      const res = await fetch(`/api/game-cover?name=${encodeURIComponent(gameName)}`);
      const data = await res.json();
      if (data.success && data.cover_url) {
        const img = document.createElement('img');
        img.src = data.cover_url;
        img.alt = gameName;
        img.className = 'game-cover-img';
        img.onload = () => {
          el.querySelector('.game-banner-fallback')?.remove();
          el.insertBefore(img, el.firstChild);
        };
        delete el.dataset.coverPending;
      }
    } catch (e) {}
  });
}

// Render Steam Games
function renderSteamGames(games) {
  if (!steamGrid) return;
  steamGrid.innerHTML = '';
  if (!games || games.length === 0) {
    steamGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">No se encontraron juegos o partidas de Steam.</div>';
    return;
  }

  games.forEach(g => {
    const card = document.createElement('div');
    card.className = 'game-card';

    const saveDetails = g.save_details;
    const saveCountText = saveDetails ? `${saveDetails.files.length} archivos (${saveDetails.total_size_kb} KB)` : (g.extra_save_files && g.extra_save_files.length > 0 ? `${g.extra_save_files.length} archivos locales` : 'Sin partidas detectadas');
    const filesList = saveDetails ? saveDetails.files : (g.extra_save_files || []);
    const bannerHtml = getGameCoverBannerHtml(g, '🔵', 'steam', '🔵 Steam');

    card.innerHTML = `
      ${bannerHtml}
      <div class="game-card-body">
        <div>
          <div class="game-title" title="${g.name}">${g.name}</div>
          <div class="game-publisher">Steam AppID: <code>${g.appid}</code> &bull; ${g.install_path ? 'Instalado' : 'Partida Cloud'}</div>
        </div>

        <div class="game-save-info">
          <div class="save-info-row">
            <span class="save-info-label">Estado Partidas:</span>
            <span class="save-info-value" style="color: ${g.has_saves ? '#00d2ff' : 'var(--text-muted)'}">${saveCountText}</span>
          </div>
          <div class="save-info-row">
            <span class="save-info-label">Archivos:</span>
            <span class="save-info-value" style="font-size: 0.74rem;">${filesList.map(f => f.name).slice(0, 3).join(', ') || 'Ninguno'}</span>
          </div>
          ${g.remote_save_path ? `
          <div class="save-info-row">
            <span class="save-info-label">Ruta:</span>
            <span class="save-info-value" title="${g.remote_save_path}">${g.remote_save_path}</span>
          </div>` : ''}
        </div>

        <div class="game-actions">
          ${g.has_saves ? `
            <button class="btn btn-action-xbox btn-card-main" onclick="startBridgeTransferFromSteam('${g.appid}')">
              🔄 Pasar Partida a Xbox PC / Game Pass
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openFolder('${(g.remote_save_path || '').replace(/\\/g, '\\\\')}')">
              📁 Abrir Carpeta
            </button>
          ` : `
            <button class="btn btn-secondary btn-sm" style="grid-column: span 2;" disabled>
              Sin partidas activas
            </button>
          `}
        </div>
      </div>
    `;
    steamGrid.appendChild(card);
  });
  resolveMissingCovers();
}

// Render Epic Games Launcher
function renderEpicGames(games) {
  if (!epicGrid) return;
  epicGrid.innerHTML = '';

  if (!games || games.length === 0) {
    epicGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">No se encontraron juegos instalados de Epic Games Launcher.</div>';
    return;
  }

  games.forEach(g => {
    const card = document.createElement('div');
    card.className = 'game-card';

    const bannerHtml = getGameCoverBannerHtml(g, '⚫', 'epic', '⚫ Epic Games');

    card.innerHTML = `
      ${bannerHtml}
      <div class="game-card-body">
        <div>
          <div class="game-title" title="${g.name}">${g.name}</div>
          <div class="game-publisher">Epic Games Launcher &bull; ${g.install_path ? 'Instalado' : 'Biblioteca'}</div>
        </div>

        <div class="game-save-info">
          <div class="save-info-row">
            <span class="save-info-label">Plataforma:</span>
            <span class="save-info-value" style="color: #d8b4fe;">Epic Games Store</span>
          </div>
          ${g.install_path ? `
          <div class="save-info-row">
            <span class="save-info-label">Instalación:</span>
            <span class="save-info-value" title="${g.install_path}">${g.install_path}</span>
          </div>` : ''}
        </div>

        <div class="game-actions">
          ${g.install_path ? `
            <button class="btn btn-secondary btn-sm" style="grid-column: span 2;" onclick="openFolder('${g.install_path.replace(/\\/g, '\\\\')}')">
              📁 Abrir Carpeta de Instalación
            </button>
          ` : `
            <button class="btn btn-secondary btn-sm" style="grid-column: span 2;" disabled>
              Sin ruta de instalación
            </button>
          `}
        </div>
      </div>
    `;
    epicGrid.appendChild(card);
  });
  resolveMissingCovers();
}

// Render PC Local Saves (AppData LocalLow / Saved Games)
function renderLocalGames(games) {
  if (!localGrid) return;
  localGrid.innerHTML = '';

  if (!games || games.length === 0) {
    localGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-secondary);">No se encontraron partidas locales en AppData o Saved Games.</div>';
    return;
  }

  games.forEach(g => {
    const card = document.createElement('div');
    card.className = 'game-card';

    const fileCount = g.file_count || (g.files ? g.files.length : 0);
    const sizeText = g.total_size_kb ? `${g.total_size_kb} KB` : '';
    const filesList = g.files ? g.files.map(f => f.name).slice(0, 3).join(', ') : 'N/A';
    const isLocalLow = g.platform === 'AppData LocalLow';
    const pillText = isLocalLow ? '📁 LocalLow' : '💾 Saved Games';
    const badgeEmoji = isLocalLow ? '📁' : '💾';
    const bannerHtml = getGameCoverBannerHtml(g, badgeEmoji, 'local', pillText);

    card.innerHTML = `
      ${bannerHtml}
      <div class="game-card-body">
        <div>
          <div class="game-title" title="${g.name}">${g.name}</div>
          <div class="game-publisher">${g.developer || g.platform}</div>
        </div>

        <div class="game-save-info">
          <div class="save-info-row">
            <span class="save-info-label">Partidas:</span>
            <span class="save-info-value" style="color: #cbd5e1;">${fileCount} archivos (${sizeText})</span>
          </div>
          <div class="save-info-row">
            <span class="save-info-label">Archivos:</span>
            <span class="save-info-value" style="font-size: 0.74rem;">${filesList}</span>
          </div>
          ${g.save_path ? `
          <div class="save-info-row">
            <span class="save-info-label">Ruta:</span>
            <span class="save-info-value" title="${g.save_path}">${g.save_path}</span>
          </div>` : ''}
        </div>

        <div class="game-actions">
          ${fileCount > 0 ? `
            <button class="btn btn-action-xbox btn-card-main" onclick="startBridgeTransferFromLocal('${g.id}')">
              🔄 Pasar Partida a Xbox PC / Game Pass
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openFolder('${(g.save_path || '').replace(/\\/g, '\\\\')}')">
              📁 Abrir Carpeta
            </button>
          ` : `
            <button class="btn btn-secondary btn-sm" style="grid-column: span 2;" disabled>
              Sin partidas activas
            </button>
          `}
        </div>
      </div>
    `;
    localGrid.appendChild(card);
  });
  resolveMissingCovers();
}

// Cross-Save Bridge Setup
function setupBridge() {
  const srcPlatform = document.getElementById('bridgeSourcePlatform');
  const tgtPlatform = document.getElementById('bridgeTargetPlatform');
  const srcGame = document.getElementById('bridgeSourceGame');
  const srcFile = document.getElementById('bridgeSourceFile');
  const tgtGame = document.getElementById('bridgeTargetGame');
  const btnTransfer = document.getElementById('btnExecuteBridgeTransfer');

  if (!srcPlatform) return;

  srcPlatform.addEventListener('change', () => {
    updateBridgeSourceGames();
  });

  tgtPlatform.addEventListener('change', () => {
    updateBridgeTargetGames();
  });

  srcGame.addEventListener('change', () => {
    updateBridgeSourceFiles();
  });

  srcFile.addEventListener('change', () => {
    checkBridgeCompatibility();
  });

  btnTransfer.addEventListener('click', () => {
    executeBridgeTransfer();
  });

  // Search filters
  if (steamSearch) {
    steamSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = (allData.steam || []).filter(g => g.name.toLowerCase().includes(q) || (g.appid && g.appid.includes(q)));
      renderSteamGames(filtered);
    });
  }

  if (epicSearch) {
    epicSearch.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filteredLocal = (allData.local_saves || []).filter(g => g.name.toLowerCase().includes(q));
      const filteredEpic = (allData.epic || []).filter(g => g.name.toLowerCase().includes(q));
      renderEpicGames(filteredEpic, filteredLocal);
    });
  }
}

function updateBridgeDropdowns() {
  updateBridgeSourceGames();
  updateBridgeTargetGames();
}

function updateBridgeSourceGames() {
  const platform = document.getElementById('bridgeSourcePlatform').value;
  const select = document.getElementById('bridgeSourceGame');
  select.innerHTML = '';

  let list = [];
  if (platform === 'steam') list = (allData.steam || []).filter(g => g.has_saves);
  else if (platform === 'xbox') list = (allData.xbox || []).filter(g => g.has_saves);
  else if (platform === 'epic') list = [...(allData.local_saves || []), ...(allData.epic || [])];

  list.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.id;
    opt.textContent = `${item.name} (${item.platform || 'Juego'})`;
    select.appendChild(opt);
  });

  updateBridgeSourceFiles();
}

function normalizeGameName(str) {
  if (!str) return '';
  return str.toLowerCase()
    .replace(/[™®©:_\-\.\,\'\(\)]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function updateBridgeSourceFiles() {
  const platform = document.getElementById('bridgeSourcePlatform').value;
  const gameId = document.getElementById('bridgeSourceGame').value;
  const fileSelect = document.getElementById('bridgeSourceFile');
  fileSelect.innerHTML = '';

  let files = [];
  if (platform === 'steam') {
    const game = (allData.steam || []).find(g => g.id === gameId);
    if (game && game.save_details) files = game.save_details.files || [];
    else if (game && game.extra_save_files) files = game.extra_save_files || [];
  } else if (platform === 'xbox') {
    const game = (allData.xbox || []).find(g => g.id === gameId);
    if (game && game.save_details && game.save_details.containers) {
      files = game.save_details.containers.map(c => ({
        name: `${c.name} (${(c.size/1024).toFixed(1)} KB)`,
        path: c.files && c.files[0] ? c.files[0].blob_path : c.dir_path,
        raw_name: c.name
      }));
    }
  } else if (platform === 'epic') {
    const game = [...(allData.local_saves || []), ...(allData.epic || [])].find(g => g.id === gameId);
    if (game && game.files) files = game.files || [];
  }

  // Sort files so main save files (.dat, .sav, .sl2, .bin) are listed before auxiliary .vdf/.xml
  files.sort((a, b) => {
    const aExt = (a.name || '').split('.').pop().toLowerCase();
    const bExt = (b.name || '').split('.').pop().toLowerCase();
    const isASave = ['dat', 'sav', 'sl2', 'bin'].includes(aExt);
    const isBSave = ['dat', 'sav', 'sl2', 'bin'].includes(bExt);
    if (isASave && !isBSave) return -1;
    if (!isASave && isBSave) return 1;
    return 0;
  });

  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.path;
    opt.textContent = f.name;
    fileSelect.appendChild(opt);
  });

  // Auto-fill target slot name
  const tgtSlotInput = document.getElementById('bridgeTargetSlotName');
  if (files.length > 0) {
    const selectedFile = files[0];
    tgtSlotInput.value = selectedFile.raw_name || selectedFile.name;
  }
}

function updateBridgeTargetGames() {
  const platform = document.getElementById('bridgeTargetPlatform').value;
  const select = document.getElementById('bridgeTargetGame');
  select.innerHTML = '';

  let list = [];
  if (platform === 'xbox') list = allData.xbox || [];
  else if (platform === 'steam') list = allData.steam || [];
  else if (platform === 'epic') list = [...(allData.local_saves || []), ...(allData.epic || [])];

  list.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.id;
    opt.textContent = `${item.name} (${item.platform || 'Xbox'})`;
    select.appendChild(opt);
  });
}

function autoMatchTargetGame(srcPlatform, srcGameName, tgtPlatform) {
  const targetSelect = document.getElementById('bridgeTargetGame');
  if (!targetSelect || !srcGameName) return;

  let targetList = [];
  if (tgtPlatform === 'xbox') targetList = allData.xbox || [];
  else if (tgtPlatform === 'steam') targetList = allData.steam || [];
  else if (tgtPlatform === 'epic') targetList = [...(allData.local_saves || []), ...(allData.epic || [])];

  const normSrc = normalizeGameName(srcGameName);
  const match = targetList.find(tg => {
    const normTgt = normalizeGameName(tg.name || tg.display_name || '');
    return normTgt === normSrc || normTgt.includes(normSrc) || normSrc.includes(normTgt);
  });

  if (match) {
    targetSelect.value = match.id;
  }
}

// Quick transfer triggers
function startBridgeTransferFromSteam(appId) {
  const bridgeTab = document.querySelector('.tab-btn[data-tab="bridge"]');
  if (bridgeTab) bridgeTab.click();

  document.getElementById('bridgeSourcePlatform').value = 'steam';
  updateBridgeSourceGames();
  document.getElementById('bridgeSourceGame').value = `steam_${appId}`;
  updateBridgeSourceFiles();

  document.getElementById('bridgeTargetPlatform').value = 'xbox';
  updateBridgeTargetGames();

  const steamGame = (allData.steam || []).find(g => g.appid === appId || g.id === `steam_${appId}`);
  if (steamGame) {
    autoMatchTargetGame('steam', steamGame.name, 'xbox');
  }
}

function startBridgeTransferFromLocal(localId) {
  const bridgeTab = document.querySelector('.tab-btn[data-tab="bridge"]');
  if (bridgeTab) bridgeTab.click();

  document.getElementById('bridgeSourcePlatform').value = 'epic';
  updateBridgeSourceGames();
  document.getElementById('bridgeSourceGame').value = localId;
  updateBridgeSourceFiles();

  document.getElementById('bridgeTargetPlatform').value = 'xbox';
  updateBridgeTargetGames();

  const localGame = [...(allData.local_saves || []), ...(allData.epic || [])].find(g => g.id === localId);
  if (localGame) {
    autoMatchTargetGame('epic', localGame.name, 'xbox');
  }
}

function closeCompatibilityModal() {
  const modal = document.getElementById('compatibilityWarningModal');
  if (modal) modal.classList.remove('active');
}

function showCompatibilityModal(info) {
  const modal = document.getElementById('compatibilityWarningModal');
  if (!modal) return;

  document.getElementById('modalSrcPlatform').textContent = `Plataforma de Origen (${info.source_platform})`;
  document.getElementById('modalSrcVer').textContent = info.source_version;
  document.getElementById('modalTgtPlatform').textContent = `Plataforma de Destino (${info.target_platform})`;
  document.getElementById('modalTgtVer').textContent = info.target_version;

  document.getElementById('modalWarningText').textContent = info.message;
  document.getElementById('modalRecommendationText').innerHTML = `<strong>💡 Recomendación:</strong> ${info.recommendation}`;

  document.getElementById('btnProceedDespiteWarning').onclick = () => {
    closeCompatibilityModal();
    doExecuteTransfer();
  };

  modal.classList.add('active');
}

async function executeBridgeTransfer() {
  const srcPlatform = document.getElementById('bridgeSourcePlatform').value;
  const tgtPlatform = document.getElementById('bridgeTargetPlatform').value;
  const srcFilePath = document.getElementById('bridgeSourceFile').value;
  const srcGameId = document.getElementById('bridgeSourceGame').value;
  const tgtGameId = document.getElementById('bridgeTargetGame').value;

  if (!srcFilePath) {
    showToast('Selecciona un archivo de partida de origen', 'error');
    return;
  }
  if (!tgtGameId) {
    showToast('Selecciona un juego de destino válido', 'error');
    return;
  }

  let srcMeta = {};
  if (srcPlatform === 'steam') srcMeta = (allData.steam || []).find(g => g.id === srcGameId) || {};
  else if (srcPlatform === 'xbox') srcMeta = (allData.xbox || []).find(g => g.id === srcGameId) || {};
  else if (srcPlatform === 'epic') srcMeta = [...(allData.local_saves || []), ...(allData.epic || [])].find(g => g.id === srcGameId) || {};

  let tgtMeta = {};
  if (tgtPlatform === 'xbox') tgtMeta = (allData.xbox || []).find(g => g.id === tgtGameId) || {};
  else if (tgtPlatform === 'steam') tgtMeta = (allData.steam || []).find(g => g.id === tgtGameId) || {};
  else if (tgtPlatform === 'epic') tgtMeta = [...(allData.local_saves || []), ...(allData.epic || [])].find(g => g.id === tgtGameId) || {};

  // Check version compatibility on click
  try {
    const res = await fetch('/api/bridge/verify-compatibility', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_platform: srcPlatform,
        target_platform: tgtPlatform,
        source_file: srcFilePath,
        source_meta: srcMeta,
        target_meta: tgtMeta
      })
    });
    const data = await res.json();
    if (data.success && data.data && data.data.has_mismatch) {
      // ⚠️ Versions are different -> show warning modal to user
      showCompatibilityModal(data.data);
      return;
    }
  } catch (e) {
    console.error('Error verificando versiones:', e);
  }

  // ✅ Versions match or compatible -> Transfer directly
  doExecuteTransfer();
}

async function doExecuteTransfer() {
  const srcPlatform = document.getElementById('bridgeSourcePlatform').value;
  const tgtPlatform = document.getElementById('bridgeTargetPlatform').value;
  const srcFilePath = document.getElementById('bridgeSourceFile').value;
  const tgtGameId = document.getElementById('bridgeTargetGame').value;
  const tgtSlotName = document.getElementById('bridgeTargetSlotName').value.trim();

  let tgtMeta = {};
  if (tgtPlatform === 'xbox') {
    const game = (allData.xbox || []).find(g => g.id === tgtGameId);
    if (!game) {
      showToast('Selecciona un juego de Xbox válido', 'error');
      return;
    }
    tgtMeta = {
      package_id: game.package_id,
      wgs_user_dir: game.wgs_user_dirs && game.wgs_user_dirs[0] ? game.wgs_user_dirs[0].path : null
    };
  } else if (tgtPlatform === 'steam') {
    const game = (allData.steam || []).find(g => g.id === tgtGameId);
    tgtMeta = {
      appid: game ? game.appid : null,
      remote_save_path: game ? game.remote_save_path : null,
      install_path: game ? game.install_path : null
    };
  } else if (tgtPlatform === 'epic') {
    const game = [...(allData.local_saves || []), ...(allData.epic || [])].find(g => g.id === tgtGameId);
    tgtMeta = {
      save_path: game ? game.save_path : null,
      install_path: game ? game.install_path : null
    };
  }

  logActivity(`[BRIDGE] Iniciando transferencia: ${srcPlatform} ➔ ${tgtPlatform} para ranura '${tgtSlotName}'...`, 'info');

  try {
    const res = await fetch('/api/bridge/transfer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_platform: srcPlatform,
        target_platform: tgtPlatform,
        source_file: srcFilePath,
        target_meta: tgtMeta,
        target_slot: tgtSlotName
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      logActivity(`[SUCCESS] ${data.message}`, 'success');
      if (data.auto_patches && data.auto_patches.length > 0) {
        data.auto_patches.forEach(p => {
          logActivity(`[AUTO-PATCH] ⚡ ${p}`, 'success');
        });
      }
      loadAllPlatforms();
    } else {
      showToast(`Error: ${data.error}`, 'error');
      logActivity(`[ERROR] ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Error ejecutando transferencia Cross-Save', 'error');
  }
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

    const saveDetails = g.save_details;
    const saveCountText = saveDetails ? `${saveDetails.container_count} Ranuras (${saveDetails.total_size_kb} KB)` : 'Sin partidas detectadas';
    const lastSavedText = saveDetails ? saveDetails.last_saved : 'N/A';
    const bannerHtml = getGameCoverBannerHtml(g, '🎮', 'xbox', '🟢 Xbox PC');

    card.innerHTML = `
      ${bannerHtml}
      <div class="game-card-body">
        <div>
          <div class="game-title" title="${g.name}">${g.name}</div>
          <div class="game-publisher">${g.publisher} &bull; v${g.version} ${g.is_installed ? '(Instalado)' : ''}</div>
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
              🔍 Inspeccionar Ranuras (${saveDetails ? saveDetails.container_count : 0})
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
      </div>
    `;

    gamesGrid.appendChild(card);
  });
  resolveMissingCovers();
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
          <button class="btn btn-action-accent btn-sm" onclick="exportSlotRawFromModal('${c.name}')" title="Exportar este slot individual a archivo .SAV">
            📥 Exportar .SAV
          </button>
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

// Open Advanced Tools Modal
async function openToolsModal() {
  const container = document.getElementById('detectedAccounts');
  container.innerHTML = '<span>Detectando IDs en el sistema...</span>';
  document.getElementById('toolsModal').classList.add('active');

  try {
    const res = await fetch('/api/tools/user-ids');
    const data = await res.json();
    if (data.success) {
      container.innerHTML = '';
      const { xbox_xuids, steam_ids } = data.data;

      if (xbox_xuids.length === 0 && steam_ids.length === 0) {
        container.innerHTML = '<span style="color: var(--text-muted)">No se detectaron IDs en las rutas estándar.</span>';
        return;
      }

      xbox_xuids.forEach(x => {
        const badge = document.createElement('div');
        badge.className = 'id-badge';
        badge.title = 'Clic para usar como ID Destino';
        badge.innerHTML = `🟢 Xbox XUID (Hex): <strong>${x.hex}</strong>`;
        badge.onclick = () => {
          document.getElementById('patchNewId').value = x.hex;
          showToast(`Copiado ${x.hex} a ID Destino`);
        };
        container.appendChild(badge);
      });

      steam_ids.forEach(s => {
        const badge = document.createElement('div');
        badge.className = 'id-badge';
        badge.title = 'Clic para usar como ID Origen';
        badge.innerHTML = `🔵 SteamID64: <strong>${s.steam64}</strong>`;
        badge.onclick = () => {
          document.getElementById('patchOldId').value = s.steam64;
          showToast(`Copiado ${s.steam64} a ID Origen`);
        };
        container.appendChild(badge);
      });
    }
  } catch (err) {
    container.innerHTML = '<span style="color: var(--accent-red)">Error al consultar IDs.</span>';
  }
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
    <span>${type === 'success' ? '✅' : (type === 'info' ? 'ℹ️' : '⚠️')}</span>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4500);
}

// ----------------------------------------------------
// Settings & Windows Task Scheduler (Silent Cron) Setup
// ----------------------------------------------------
async function setupSettings() {
  await loadSettings();

  document.getElementById('btnBrowseBackupDir')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-file-selector', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'folder' })
      });
      const data = await res.json();
      if (data.selected_path) {
        document.getElementById('cfgBackupRootDir').value = data.selected_path;
      }
    } catch (e) {
      showToast('Error al seleccionar carpeta', 'error');
    }
  });

  document.getElementById('btnOpenCurrentBackupDir')?.addEventListener('click', () => {
    const p = document.getElementById('cfgBackupRootDir').value.trim() || defaultBackupDir;
    openFolder(p);
  });

  document.getElementById('btnSaveStorageSettings')?.addEventListener('click', async () => {
    const backupDir = document.getElementById('cfgBackupRootDir').value.trim();
    const maxHist = parseInt(document.getElementById('cfgMaxHistory').value, 10);
    const syncInterval = parseInt(document.getElementById('cfgSyncInterval')?.value, 10) || 60;
    const autoSyncOn = document.getElementById('cfgAutoSyncEnabled')?.checked;

    if (!backupDir) {
      showToast('Por favor especifica un directorio de respaldo válido', 'error');
      return;
    }
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          backup_root_dir: backupDir,
          max_backup_history: maxHist,
          auto_sync_interval_mins: syncInterval,
          auto_sync_enabled: autoSyncOn
        })
      });
      const data = await res.json();
      if (data.success) {
        defaultBackupDir = data.config.backup_root_dir;
        if (data.scheduler_refreshed) {
          showToast('¡Configuración guardada y Tarea de Windows (Cron) actualizada!', 'success');
          logActivity(`[CONFIG] Ruta: ${defaultBackupDir} | Tarea silenciosa de Windows actualizada (cada ${syncInterval}m)`, 'success');
        } else {
          showToast('¡Configuración de almacenamiento guardada exitosamente!', 'success');
          logActivity(`[CONFIG] Ruta de respaldos actualizada a: ${defaultBackupDir}`, 'success');
        }
        await loadSettings();
      }
    } catch (e) {
      showToast('Error guardando configuración', 'error');
    }
  });

  document.getElementById('cfgAutoSyncEnabled')?.addEventListener('change', async (e) => {
    const enabled = e.target.checked;
    await updateConfigKey('auto_sync_enabled', enabled);
    showToast(enabled ? 'Auto-Sync periódico habilitado' : 'Auto-Sync pausado', 'info');
    logActivity(`[AUTO-SYNC] Modo periódico en app: ${enabled ? 'Activado' : 'Desactivado'}`, 'info');
    await loadSettings();
  });

  document.getElementById('cfgSyncInterval')?.addEventListener('change', async (e) => {
    const mins = parseInt(e.target.value, 10);
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_sync_interval_mins: mins })
    });
    const data = await res.json();
    if (data.scheduler_refreshed) {
      showToast(`Intervalo actualizado a ${mins} min y Tarea de Windows sincronizada`, 'success');
      logActivity(`[SCHEDULER] Tarea de Windows reconfigurada para ejecutarse cada ${mins} minutos.`, 'success');
    } else {
      showToast(`Intervalo actualizado a ${mins} minutos`, 'info');
    }
    await loadSettings();
  });

  document.getElementById('btnSyncNow')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnSyncNow');
    btn.disabled = true;
    btn.textContent = '⏳ Sincronizando...';
    logActivity('[SYNC] Iniciando sincronización manual de todas las partidas...', 'info');

    try {
      const res = await fetch('/api/sync/run-now', { method: 'POST' });
      const data = await res.json();
      if (data.success && data.results) {
        const r = data.results;
        showToast(`¡Sincronización completada! ${r.total_games} juegos respaldados`, 'success');
        logActivity(`[SYNC SUCCESS] Se respaldaron ${r.total_games} juegos y ${r.total_saves} partidas directamente en: ${defaultBackupDir}`, 'success');
        await loadSettings();
      } else {
        showToast('Error durante la sincronización', 'error');
      }
    } catch (e) {
      showToast('Error de conexión con el servidor', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '⚡ Sincronizar Todo Ahora';
    }
  });

  document.getElementById('btnInstallScheduler')?.addEventListener('click', async () => {
    const interval = parseInt(document.getElementById('cfgSyncInterval').value, 10) || 60;
    try {
      const res = await fetch('/api/sync/scheduler/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_mins: interval })
      });
      const data = await res.json();
      if (data.success) {
        showToast('¡Tarea silenciosa de Windows instalada con éxito!', 'success');
        logActivity(`[SCHEDULER] ${data.message}`, 'success');
        await loadSettings();
      } else {
        showToast(`Error: ${data.error}`, 'error');
      }
    } catch (e) {
      showToast('Error al instalar la tarea programada', 'error');
    }
  });

  document.getElementById('btnUninstallScheduler')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/sync/scheduler/uninstall', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showToast('Tarea programada desinstalada', 'info');
        logActivity('[SCHEDULER] Tarea de Windows eliminada.', 'info');
        await loadSettings();
      } else {
        showToast(`Error: ${data.error}`, 'error');
      }
    } catch (e) {
      showToast('Error al desinstalar la tarea', 'error');
    }
  });
}

async function loadSettings() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    if (data.success) {
      const cfg = data.config;
      const sched = data.scheduler;

      if (document.getElementById('cfgBackupRootDir')) document.getElementById('cfgBackupRootDir').value = cfg.backup_root_dir || defaultBackupDir;
      if (document.getElementById('cfgMaxHistory')) document.getElementById('cfgMaxHistory').value = String(cfg.max_backup_history ?? 10);
      if (document.getElementById('cfgAutoSyncEnabled')) document.getElementById('cfgAutoSyncEnabled').checked = Boolean(cfg.auto_sync_enabled);
      if (document.getElementById('cfgSyncInterval')) document.getElementById('cfgSyncInterval').value = String(cfg.auto_sync_interval_mins ?? 60);

      // Sync status banner
      const descEl = document.getElementById('syncStatusDesc');
      if (descEl) {
        const lastTime = cfg.last_sync_time || 'Nunca';
        const lastStatus = cfg.last_sync_status || 'Sin ejecuciones previas';
        descEl.textContent = `Última sincronización: ${lastTime} • ${lastStatus}`;
      }

      // Scheduler status badge & buttons
      const badge = document.getElementById('schedulerBadge');
      const btnInstall = document.getElementById('btnInstallScheduler');
      const btnUninstall = document.getElementById('btnUninstallScheduler');
      const nextRunEl = document.getElementById('schedulerNextRun');

      if (sched && sched.installed) {
        if (badge) {
          badge.textContent = `Activa (${sched.status || 'Programada'})`;
          badge.className = 'badge-task badge-task-on';
        }
        if (btnInstall) btnInstall.textContent = '🔄 Reconfigurar Frecuencia de Tarea';
        if (btnUninstall) btnUninstall.style.display = 'inline-block';
        if (nextRunEl && sched.next_run) nextRunEl.textContent = `Próxima ejecución: ${sched.next_run}`;
      } else {
        if (badge) {
          badge.textContent = 'No Instalada';
          badge.className = 'badge-task badge-task-off';
        }
        if (btnInstall) btnInstall.textContent = '⚙️ Instalar Tarea Programada Silenciosa';
        if (btnUninstall) btnUninstall.style.display = 'none';
        if (nextRunEl) nextRunEl.textContent = '';
      }
    }
  } catch (e) {
    console.error('Error cargando configuración:', e);
  }
}

async function updateConfigKey(key, value) {
  try {
    const payload = {};
    payload[key] = value;
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (e) {}
}

async function exportSlotRawFromModal(slotName) {
  if (!currentGame) return;
  const userWgsDir = currentGame.wgs_user_dirs && currentGame.wgs_user_dirs[0] ? currentGame.wgs_user_dirs[0].path : null;
  if (!userWgsDir) {
    showToast('No se encontró directorio WGS para este juego', 'error');
    return;
  }

  // Ask where to save via Windows Native Save File Dialog
  let targetPath = null;
  try {
    const selectorRes = await fetch('/api/open-file-selector', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'save_file',
        filter: 'Save File (*.sav)|*.sav|All Files (*.*)|*.*',
        default_name: `${slotName}.sav`
      })
    });
    const sData = await selectorRes.json();
    if (sData.selected_path) {
      targetPath = sData.selected_path;
    }
  } catch (e) {}

  logActivity(`[EXPORT SLOT] Exportando ranura '${slotName}' para ${currentGame.name}...`, 'info');

  try {
    const res = await fetch('/api/export/slot-raw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_wgs_dir: userWgsDir,
        container_name: slotName,
        game_name: currentGame.name,
        dest_path: targetPath
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`¡Ranura exportada: ${data.filename}!`, 'success');
      logActivity(`[SUCCESS] Ranura '${slotName}' exportada como .SAV en: ${data.exported_file} (${data.size_kb} KB)`, 'success');
      openFolder(data.exported_file.substring(0, data.exported_file.lastIndexOf('\\')));
    } else {
      showToast(`Error: ${data.error}`, 'error');
      logActivity(`[ERROR] ${data.error}`, 'error');
    }
  } catch (e) {
    showToast('Error exportando ranura', 'error');
  }
}
