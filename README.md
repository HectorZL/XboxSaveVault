# Xbox Save Vault 🎮💾

**Xbox Save Vault** es una herramienta para **escanear, exportar, importar, respaldar y convertir partidas guardadas** de juegos de la aplicación Xbox para PC y Xbox Game Pass (incluyendo juegos GDK y UWP).

---

## 🌟 Características Principales

- 🔍 **Auto-Detección Total:** Escanea automáticamente `C:\XboxGames`, unidades secundarias y `%LOCALAPPDATA%\Packages` para detectar todos tus juegos instalados y sus partidas de Windows Gaming Services (WGS).
- 📂 **Exportación Limpia (.SAV):** Decodifica los contenedores binarios de Xbox y extrae archivos `.sav` legibles con sus nombres originales (ej. `borSaveDataNormal_0.sav`), compatibles con Steam u otras plataformas.
- 📦 **Backup Completo Xbox (.ZIP):** Empaqueta toda la estructura de contenedores, firmas de tiempo, índices y configuraciones locales (`LocalCache`) para copias de seguridad de restauración perfecta.
- 🔄 **Restauración Inteligente con Seguridad:** Restaura backups completos con creación automática de copia de seguridad previa de seguridad.
- 💉 **Inyección de Partidas por Ranura:** Permite reemplazar una ranura específica (ej. Ranura Manual 0, Autoguardado) con cualquier archivo de partida `.sav`, reconstruyendo automáticamente los metadatos de Xbox.
- 📁 **Acceso Directo:** Abre instantáneamente la carpeta real de guardado en el Explorador de Windows.
- 🖥️ **Interfaz Visual Moderna + CLI:** Interfaz gráfica web con estética gamer oscura (Xbox Emerald & Carbon) y CLI rápido.

---

## 🚀 Inicio Rápido

### Opción 1: Ejecutable Autónomo (.EXE)
Puedes usar directamente el ejecutable compilado:
```
dist\XboxSaveVault.exe
```
O compilarlo y autofirmarlo tú mismo con 1 clic en:
```
build_exe.bat
```

### Opción 2: Desde Python / Bat
Haz doble clic en:
```
Launch_XboxSaveManager.bat
```
O desde la terminal:
```bash
python xbox_save_manager.py
```
Se abrirá automáticamente en tu navegador en `http://127.0.0.1:8899`.

---

## 💻 Uso desde Línea de Comandos (CLI)

### 1. Listar todos los juegos y partidas detectadas
```bash
python xbox_save_manager.py --list
```

### 2. Exportar partidas legibles (.SAV para Steam/PC)
```bash
python xbox_save_manager.py --export-raw "Beast of Reincarnation"
```

### 3. Crear un backup completo de Xbox (.ZIP)
```bash
python xbox_save_manager.py --backup "Beast of Reincarnation"
```

### 4. Restaurar un backup
```bash
python xbox_save_manager.py --restore "C:\ruta\al\backup.zip" --target "Beast of Reincarnation"
```

---

## 🔍 ¿Dónde guarda Xbox las partidas en PC?

A diferencia de Steam (que suele guardar en `Documents` o `AppData\Roaming`), la aplicación de Xbox y los juegos de Windows Store / Game Pass guardan las partidas en contenedores sincronizados con la nube en:
```
%LOCALAPPDATA%\Packages\<NombreDelPaquete>\SystemAppData\wgs\<ID_Usuario_Xbox>_<TitleID>\
```

Dentro de este directorio:
- `containers.index`: Archivo binario con la lista de ranuras, hashes y marcas de tiempo.
- Carpetas con identificadores GUID: Cada una contiene un archivo `container.X` y un archivo blob binario con la partida real.
- Carpetas `LocalCache\Local`: Almacenan configuraciones locales (`.sav`).

**Xbox Save Vault se encarga de decodificar y recodificar toda esta estructura automáticamente.**
