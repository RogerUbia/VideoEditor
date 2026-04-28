# VideoForge — Manual de Usuario

## ¿Qué es VideoForge?

VideoForge es un editor de video de escritorio con IA integrada. Combina una interfaz visual similar a CapCut con un pipeline de procesamiento automático basado en 8 agentes de IA especializados (Gemini 2.5).

---

## Interfaz

```
┌─────────────────────────────────────────────────────────────────┐
│  [Import Video] [▶ Run Pipeline] [⏹ Stop] [▶▶ Resume] [Manual/Auto] [↑ YouTube] [↑ Instagram]
├──────────────────┬───────────────────────┬──────────────────────┤
│  PANEL GUION     │   PREVIEW DE VIDEO    │  PROPIEDADES         │
│                  │                       │                      │
│  Tabla de        │   Vista previa del    │  Tabs:               │
│  segmentos       │   video con controles │  · Segment           │
│  (Excel-like)    │   de reproducción     │  · Video             │
│                  │                       │  · Audio             │
│  ──────────────  │                       │  · Export            │
│  CHAT con IA     │                       │  · API               │
│  (agente guion)  │                       │                      │
├──────────────────┴───────────────────────┴──────────────────────┤
│  TIMELINE  (clips de video, audio, texto)                       │
├─────────────────────────────────────────────────────────────────┤
│  PROCESS LOG  (progreso del pipeline en tiempo real)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Inicio rápido

### 1. Crear un proyecto
- **File → New Project** (Ctrl+N) o arrastra un video directamente a la ventana
- Introduce el nombre del proyecto

### 2. Importar el video base
- **File → Import Video…** (Ctrl+Shift+O)
- O arrastra un archivo MP4/MOV/AVI/MKV a la ventana
- El video aparece en el preview central

### 3. Crear el guion con IA
- En el **panel izquierdo (chat)**, escribe lo que quieres:
  - _"Crea un guion de 3 minutos sobre cocina catalana para Instagram"_
  - _"Añade un segmento al final explicando los ingredientes"_
  - _"Cambia el tono a más informal"_
- La IA rellena automáticamente la **tabla de segmentos** (parte superior izquierda)
- Puedes editar la tabla directamente: doble clic en cualquier celda

### 4. Ajustar efectos y transiciones (tabla de guion)

| Columna | Qué controla |
|---|---|
| Start / End | Tiempo de inicio y fin del segmento |
| Dur. | Duración calculada automáticamente |
| Content | Texto hablado en ese segmento |
| Message | Nota interna del editor (no se renderiza) |
| Effect | Efecto de video: none, zoom_in, zoom_out, shake, blur |
| Zoom | Activar zoom progresivo (factor configurable en Propiedades) |
| Trans. | Transición de entrada: none, fade, dissolve, slide_up |
| PiP | Video en burbuja (picture-in-picture) |
| Music | Música de fondo en ese segmento |
| Text | Texto sobreimpreso en el video |
| Notes | Notas personales (no afectan al render) |
| ✓ | Estado de validación (verde = correcto, naranja = duplicado) |

**Clic derecho** sobre la tabla → menú contextual: Insertar fila, Duplicar, Eliminar.

### 5. Configurar propiedades del segmento
- Haz clic en una fila de la tabla → el **panel derecho** (Propiedades) muestra todos los detalles
- Configura: efecto, zoom, transición, PiP, música, texto overlay

---

## Modos de ejecución

### Modo Manual (por defecto)
El pipeline se **pausa después del Paso 5 (Validación)** para que puedas revisar.

**Pasos:**
1. Importa el video
2. Crea o edita el guion en la tabla
3. Pulsa **▶ Run Pipeline**
4. El pipeline ejecuta los pasos 1–5 automáticamente:
   - Paso 1: Importar y leer metadatos del video
   - Paso 2: Eliminar silencios (ajustable en Propiedades → Audio)
   - Paso 3: Transcribir audio en catalán (IA)
   - Paso 4: Corregir ortografía/gramática de la transcripción (IA)
   - Paso 5: Validar que la transcripción coincide con el guion (IA)
5. **⏸ El pipeline se pausa** — aparece el botón **▶▶ Resume** en la barra
6. Revisa la tabla: el agente marcará en rojo los segmentos que no coinciden
7. Corrige lo que necesites (edita la tabla o el guion en el chat)
8. Pulsa **▶▶ Resume** para continuar:
   - Paso 6: Detectar y eliminar takes duplicados (IA)
   - Paso 7: Aplicar efectos del guion (zoom, PiP, texto, transiciones) con FFmpeg
   - Paso 8: Generar subtítulos CA/ES/EN + exportar
9. El video final aparece en el preview

### Modo Full Auto
El pipeline ejecuta los 8 pasos sin pausar.

**Cómo activarlo:** Pulsa el botón **Manual** en la barra → cambia a **Full Auto**

Útil cuando el guion ya está revisado y confías en la validación automática.

---

## Exportación

### YouTube
- Genera: `proyecto_youtube.mp4` + `proyecto_ca.srt` + `proyecto_es.srt` + `proyecto_en.srt`
- Los archivos .srt los subes manualmente al subir el video en YouTube (Subtítulos → Añadir)
- Codec: H.264, CRF 18, AAC 192k

### Instagram
- Genera: `proyecto_instagram.mp4` con subtítulos en **inglés sobreimpresos**
- Verifica automáticamente que la duración sea < 3 minutos (avisa si se supera)
- Codec: H.264 perfil High, optimizado para streaming móvil (faststart)
- La fuente de subtítulos es configurable en Propiedades → Export

**Cómo exportar:**
- Barra de herramientas: **↑ YouTube** o **↑ Instagram**
- O menú: **Export → Export for YouTube…** / **Export for Instagram…**
- Selecciona la carpeta de destino

---

## Donde se guardan los archivos

```
Video_autoeditor/
├── data/
│   ├── projects/        ← Archivos de proyecto (.json) — File → Save Project
│   ├── scripts/         ← Historial de guiones + memoria del agente IA
│   │   └── {proyecto}/
│   │       ├── script_v001.json   ← Versiones del guion
│   │       └── session_log.json   ← Historial del chat con la IA
│   └── temp/            ← Archivos intermedios del pipeline
│       └── {proyecto}/
│           ├── 01_silence_removed.mp4
│           ├── 02_audio.wav
│           ├── 03_transcript_raw.json
│           ├── 04_transcript_corrected.json
│           ├── 05_validation_report.json
│           ├── 06_segments_final.json
│           ├── 07_effects_applied.mp4
│           └── output/
│               ├── proyecto_youtube.mp4
│               ├── proyecto_ca.srt
│               ├── proyecto_es.srt
│               └── proyecto_en.srt
└── .env                 ← API key de Gemini (nunca compartir)
```

---

## Ajustes de silencios (Propiedades → Audio)

| Parámetro | Por defecto | Descripción |
|---|---|---|
| Threshold | -40 dB | Nivel de audio considerado silencio. Más bajo = detecta silencios más profundos |
| Min duration | 500 ms | Duración mínima para cortar. Más alto = solo corta pausas largas |
| Margin | 100 ms | Margen que se deja antes/después del corte para no cortar respiraciones |

---

## Agentes de IA (Gemini 2.5)

| Agente | Modelo | Tarea |
|---|---|---|
| ScriptWriter | gemini-2.5-flash | Genera y modifica guiones, tiene memoria de proyectos anteriores |
| Transcription | gemini-2.5-flash | Transcribe el audio del video en catalán |
| TextCorrector | gemini-2.0-flash-lite | Corrige ortografía y gramática de la transcripción |
| Validator | gemini-2.5-flash | Compara transcripción real vs guion escrito |
| DuplicateDetector | gemini-2.0-flash-lite | Detecta takes repetidos, marca el mejor |
| EffectsPlanner | gemini-2.5-flash | Sugiere efectos visuales adecuados para cada segmento |
| SubtitleTranslator | gemini-2.0-flash-lite | Traduce subtítulos CA → ES y CA → EN en paralelo |
| QualityControl | gemini-2.5-flash | Revisión final de calidad del video exportado |

---

## Funcionalidades actuales ✅

- [x] Interfaz oscura tipo CapCut con timeline, preview y propiedades
- [x] Agente IA para crear/modificar guiones estructurados con tabla visual
- [x] Memoria de guiones anteriores (el agente recuerda proyectos pasados)
- [x] Importar video con drag & drop
- [x] Preview de video con controles de reproducción
- [x] Detección y eliminación automática de silencios (umbral configurable)
- [x] Transcripción de audio en catalán (Gemini)
- [x] Corrección ortográfica de la transcripción
- [x] Validación guion vs transcripción real
- [x] Detección de takes duplicados
- [x] Planificación de efectos con IA
- [x] Zoom progresivo (Ken Burns effect)
- [x] Picture-in-Picture (video en burbuja)
- [x] Texto overlay con animaciones
- [x] Transiciones: fade, dissolve, slide
- [x] Música de fondo por segmento
- [x] Subtítulos CA + traducción a ES y EN (automática)
- [x] Export YouTube (.mp4 + .srt separados)
- [x] Export Instagram (.mp4 con subtítulos EN sobreimpresos, check <3min)
- [x] Modo Manual (pausa en paso 5 para revisión)
- [x] Modo Full Auto (sin pausas)
- [x] Fallback automático entre modelos Gemini si hay error de quota
- [x] Gestión de proyectos (nuevo, abrir, guardar)

---

## Funcionalidades previstas / en desarrollo ⚙️

- [ ] **Timeline interactivo** — arrastrar clips, reordenar segmentos visualmente *(el timeline se muestra pero el drag no actualiza el pipeline todavía)*
- [ ] **Waveform de audio** en el timeline
- [ ] **Preview en tiempo real** de efectos antes de renderizar
- [ ] **Shake / blur** — efectos implementados en código pero pendientes de prueba end-to-end
- [ ] **Pipeline standalone** — ejecutar solo silences o solo transcripción sin el pipeline completo
- [ ] **Múltiples videos** en el timeline (B-roll, clips de corte)
- [ ] **Color grading** básico (brillo, contraste, saturación)
- [ ] **Subtítulos animados** tipo Instagram (pop-up por palabra)
- [ ] **Detección automática de idioma** del audio
- [ ] **Exportar solo subtítulos** sin reencoding del video

---

## Solución de problemas

**"Quota exceeded" en el log**
→ La API key de Gemini ha agotado su límite diario gratuito.
Solución: esperar hasta mañana, o crear un nuevo proyecto en aistudio.google.com con una API key nueva.

**"FFmpeg not found"**
→ FFmpeg no está en el PATH. Abre una nueva terminal (para recargar el PATH) y relanza la app.

**El pipeline se para en "Awaiting approval"**
→ Normal en modo Manual. Revisa la tabla de segmentos y pulsa el botón **▶▶ Resume** que aparece en la barra de herramientas.

**La validación da 0% de coincidencia**
→ El guion y el video no corresponden. Asegúrate de que el guion que tienes en la tabla describe el contenido del video importado. En modo Manual puedes continuar igualmente pulsando Resume.
