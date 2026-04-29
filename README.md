# VideoForge — Editor de Vídeo Intel·ligent

VideoForge és un editor de vídeo d'escriptori per a Windows que combina una interfície visual similar a CapCut amb un pipeline de processament automàtic basat en intel·ligència artificial. Permet editar vídeos, eliminar silencis, transcriure en català i generar subtítols en diversos idiomes.

---

## Característiques principals

- **Eliminació automàtica de silencis** — detecció precisa amb FFmpeg, sense tall de l'àudio
- **Transcripció en català** — via Groq Whisper (gratuït) amb correcció automàtica
- **Generació de subtítols** — CA, ES i EN amb animació configurable (fade, slide)
- **Agente IA per a guions** — Gemini 2.5 amb memòria de projectes anteriors
- **Timeline interactiu** — 6 pistes: vídeo, efectes, música, subtítols CA/ES/EN
- **Exportació per plataforma** — YouTube (16:9, 1920×1080) i Instagram (9:16, 1080×1920)

---

## Requisits

- Windows 10 o superior
- Python 3.11+
- FFmpeg (instal·lat i al PATH)
- Clau API de [Google AI Studio](https://aistudio.google.com) (gratuïta)
- Clau API de [Groq](https://console.groq.com) (gratuïta, per a transcripció)

---

## Instal·lació

**1. Clonar el repositori**
```bash
git clone https://github.com/RogerUbia/VideoEditor.git
cd VideoEditor
```

**2. Instal·lar dependències**
```bash
pip install -r requirements.txt
```

**3. Instal·lar FFmpeg**

Descarregar de [ffmpeg.org](https://ffmpeg.org/download.html) i afegir la carpeta `bin` al PATH del sistema.

**4. Configurar les claus API**

Copiar `.env.example` a `.env` i afegir les claus:
```
GEMINI_API_KEY=la_teva_clau_de_google_ai_studio
GROQ_API_KEY=la_teva_clau_de_groq
```

**5. Executar**
```bash
python main.py
```

La primera vegada demanarà la clau API si no està configurada.

---

## Com funciona

### Interfície

```
┌─────────────────────────────────────────────────────────────────┐
│  [Import] [▶ Run Pipeline] [CC EN ●] [Manual/Auto] [YouTube] [IG]
├──────────────┬──────────────────────┬───────────────────────────┤
│  SCRIPT      │   PREVIEW            │  PROPIETATS               │
│  Taula de    │   Reproducció        │  Segment / Vídeo /        │
│  segments    │   amb àudio          │  Àudio / Export / API     │
│  ──────────  │                      │                           │
│  Chat IA     │                      │                           │
├──────────────┴──────────────────────┴───────────────────────────┤
│  TIMELINE  — VIDEO · FX · MUSIC · CA · ES · EN                  │
├─────────────────────────────────────────────────────────────────┤
│  PROCESS LOG                                         [Resume]   │
└─────────────────────────────────────────────────────────────────┘
```

### Pipeline de 8 passos

| Pas | Nom | Descripció |
|-----|-----|------------|
| 1 | Import | Llegeix metadades del vídeo (resolució, fps, durada) |
| 2 | Remove Silences | Elimina silencios amb FFmpeg. Genera `waveform_analysis.png` per revisar |
| 3 | Transcribe Audio | Groq Whisper transcriu l'àudio en català |
| 4 | Correct Transcription | Gemini corregeix ortografia i gramàtica |
| 5 | Validate vs Script | Compara transcripció real amb el guió escrit |
| 6 | Detect Duplicates | Detecta takes repetits i conserva el millor |
| 7 | Apply Effects | Aplica zoom, transicions, PiP, text i música amb FFmpeg |
| 8 | Export & Subtitles | Genera subtítols CA/ES/EN i exporta el vídeo final |

En **mode Manual**, el pipeline s'atura després del pas 5 per a revisió. Prem **▶▶ Resume** per continuar.

---

## Ús pas a pas

### 1. Crear un projecte
- **File → New Project** (Ctrl+N)
- O arrossega directament un vídeo a la finestra

### 2. Generar el guió amb IA
Escriu al **chat del panell esquerre**:
> *"Vull fer un vídeo de 3 minuts sobre cuina catalana per a Instagram"*

L'agent de IA omplirà automàticament la taula de segments amb temps, contingut i efectes suggerits.

### 3. Ajustar el guió manualment
La taula de segments té les columnes:

| Columna | Descripció |
|---------|------------|
| Start/End | Temps d'inici i fi del segment |
| Contingut | Text parlat en aquest segment |
| Efecto | zoom_in, zoom_out, shake... |
| Zoom | Factor de zoom aplicat |
| Trans. | Transició d'entrada |
| PiP | Vídeo en bombolla actiu |
| Música | Música de fons activa |
| Text | Text sobreimprès actiu |

Fes clic a una fila → el **panell de Propietats** (dreta) permet editar tots els detalls. Prem **✓ Apply** per guardar els canvis.

### 4. Configurar la detecció de silencis
**Propietats → Àudio:**

| Paràmetre | Default | Descripció |
|-----------|---------|------------|
| Threshold | -40 dB | Nivell per sota del qual = silenci |
| Min silence | 500 ms | Durada mínima per tallar |
| Margin | 350 ms | Quant s'endinsa en el silenci per cada costat |
| Min clip | 1000 ms | Clips més curts que això s'eliminen |

Després de cada execució s'obre automàticament el fitxer `waveform_analysis.png`:
- **Vermell** = silenci eliminat
- **Verd** = àudio conservat
- **Groc** = punts de tall exactes

### 5. Executar el pipeline
Prem **▶ Run Pipeline** a la barra d'eines.

En mode **Manual**: el pipeline s'atura al pas 5 mostrant el botó verd **▶▶ Resume**. Revisa la taula i prem Resume per continuar.

En mode **Full Auto**: executa els 8 passos sense pauses.

### 6. Configurar subtítols
**Propietats → Export:**
- **Burn subtitles**: actiu per defecte (subtítols cremats al vídeo)
- **Idioma**: English (EN) per defecte
- **Animació**: Fade in/out, Fade in, Slide up, Static
- **Fade duration**: ajustable en ms

El botó **CC EN ●** a la barra d'eines permet activar/desactivar ràpidament.

### 7. Exportar
- **↑ YouTube** → vídeo 1920×1080 (16:9) + fitxers `.srt` CA/ES/EN separats
- **↑ Instagram** → vídeo 1080×1920 (9:16) amb subtítols EN cremats, verifica <3 min

---

## Agents d'IA

VideoForge utilitza 8 agents especialitzats de Gemini/Groq:

| Agent | Model | Tasca |
|-------|-------|-------|
| ScriptWriter | Gemini 2.5 Flash | Genera guions amb memòria de projectes |
| Transcription | Groq Whisper | Transcripció d'àudio en català |
| TextCorrector | Gemini 2.0 Flash Lite | Correcció ortogràfica ràpida |
| Validator | Gemini 2.5 Flash | Compara transcripció vs guió |
| DuplicateDetector | Gemini 2.0 Flash Lite | Detecta takes repetits |
| EffectsPlanner | Gemini 2.5 Flash | Suggereix efectes visuals |
| SubtitleTranslator | Gemini 2.0 Flash Lite | Tradueix CA → ES i EN |
| QualityControl | Gemini 2.5 Flash | Revisió final de qualitat |

Quan la quota de Gemini s'esgota, el sistema canvia automàticament a **Groq Llama 3.3 70B** per a les tasques de text.

---

## On es guarden els fitxers

```
VideoEditor/
├── data/
│   ├── temp/{projecte}/
│   │   ├── 01_silence_removed.mp4    ← vídeo sense silencis
│   │   ├── waveform_analysis.png     ← anàlisi visual dels talls
│   │   ├── 03_transcript_raw.json    ← transcripció en brut
│   │   └── output/
│   │       ├── projecte_youtube.mp4  ← VÍDEO FINAL YouTube
│   │       ├── projecte_ca.srt       ← subtítols català
│   │       ├── projecte_es.srt       ← subtítols castellà
│   │       ├── projecte_en.srt       ← subtítols anglès
│   │       └── projecte_instagram.mp4 ← VÍDEO FINAL Instagram
│   ├── projects/                     ← projectes guardats (.json)
│   └── scripts/                      ← historial de guions i xat IA
└── .env                              ← claus API (no compartir!)
```

---

## Solució de problemes

**"Quota exceeded" a la IA**
La quota gratuïta de Gemini 2.5 Flash és de 20 peticions/dia. El sistema canvia automàticament a Groq. Si tots dos s'esgoten, espera fins a mitjanit (hora del Pacífic) o crea un nou projecte a [aistudio.google.com](https://aistudio.google.com).

**FFmpeg no trobat**
Obre una nova terminal (per recarregar el PATH) i executa `python main.py`. Si segueix fallant, verifica que FFmpeg estigui al PATH: `ffmpeg -version`.

**El vídeo del preview va lent**
Normal en vídeos d'alta resolució (1080p+). El sistema usa OpenCV per a la previsualització (ràpid) i QMediaPlayer per a l'àudio.

**El pipeline s'atura al pas 5**
És normal en mode Manual. Revisa la taula de segments i prem el botó verd **▶▶ Resume** a la barra de processos.

---

## Llicència

MIT License — Roger Ubia, 2026
