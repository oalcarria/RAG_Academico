# Asistente RAG para visitas de institutos

Aplicación para las visitas de institutos y colegios: los alumnos suben sus
apuntes en PDF (todos a la vez, en una sesión compartida tipo kiosko) y pueden
preguntar lo que quieran sobre ellos, por texto o por voz, recibiendo la
respuesta tanto en texto como habladas.

Este documento explica también, de forma sencilla, **qué es un RAG y cómo
funciona por dentro**, pensado para alguien que no haya trabajado antes con
este tipo de sistemas.

## ¿Qué es un RAG?

Un modelo de lenguaje (el "cerebro" que genera las respuestas, en este
proyecto un modelo alojado en Groq) solo sabe lo que aprendió durante su
entrenamiento. No ha leído los apuntes de un alumno concreto, así que si le
preguntas directamente sobre ellos, no podrá responder o se lo inventará.

**RAG** son las siglas de *Retrieval-Augmented Generation* (generación
aumentada con recuperación de información). La idea es sencilla:

1. Antes de preguntar, **buscamos** en los documentos del usuario los trozos
   de texto que probablemente contienen la respuesta (esto es la parte de
   *Retrieval*, "recuperación").
2. Le pasamos esos trozos al modelo de lenguaje junto con la pregunta,
   pidiéndole que responda basándose en ellos (esto es la parte de
   *Generation*, "generación").

De esta forma el modelo puede responder sobre documentos que nunca ha visto
antes, sin necesidad de volver a entrenarlo, y citando de dónde ha sacado la
información. Es el mismo principio que usan herramientas como ChatGPT cuando
"leen" un PDF que le adjuntas.

## ¿Cómo funciona este proyecto paso a paso?

Hay dos flujos independientes: **subir documentos** (una vez, al principio) y
**preguntar** (muchas veces, por cada alumno).

### 1. Subir documentos (indexación)

```
PDF subido
   │
   ▼
Extraer el texto de cada página        (backend/rag.py → extract_pages)
   │
   ▼
Trocear el texto en fragmentos         (backend/rag.py → chunk_text)
   pequeños y solapados (~800 palabras)
   │
   ▼
Convertir cada fragmento en un         (sentence-transformers)
"embedding" (un vector de números)
   │
   ▼
Guardar el vector + el texto en el     (backend/rag.py → VectorStore)
almacén local (data/vector_store/)
```

Un **embedding** es, simplificando, una lista de unos cientos de números que
representa el *significado* de un texto: dos fragmentos con significados
parecidos generan vectores parecidos, aunque usen palabras distintas. Esto es
lo que nos permite buscar por significado y no solo por coincidencia exacta
de palabras.

Los documentos se trocean (*chunking*) porque un PDF entero es demasiado
largo para compararlo de una vez; es mejor tener muchos fragmentos pequeños y
quedarnos solo con los más relevantes para cada pregunta.

### 2. Preguntar (recuperación + generación)

```
Pregunta del alumno (texto o voz)
   │
   ├─ Si es voz → transcribir con Whisper local   (backend/stt.py)
   │
   ▼
Convertir la pregunta en un embedding          (mismo modelo que al indexar)
   │
   ▼
Comparar ese embedding con todos los           (backend/rag.py → search)
guardados y quedarnos con los más
parecidos (similitud de coseno)
   │
   ▼
Construir un mensaje con:                      (backend/llm.py → build_context)
  - los fragmentos de texto más relevantes
  - la pregunta del alumno
   │
   ▼
Enviarlo al modelo de lenguaje (Groq)          (backend/llm.py → ask)
para que redacte la respuesta
   │
   ▼
Mostrar la respuesta en texto y locutarla      (backend/tts.py, Piper)
en voz con TTS local
```

La calidad de la respuesta depende sobre todo de que se recuperen los
fragmentos correctos en el paso de comparación: si la pregunta no encuentra
buenos fragmentos, el modelo lo dirá honestamente en vez de inventarse una
respuesta (así se lo pedimos en las instrucciones que le damos, ver
`SYSTEM_PROMPT` en [backend/llm.py](backend/llm.py)).

## Glosario rápido

| Término | Qué significa aquí |
|---|---|
| **LLM** (*Large Language Model*) | El modelo de lenguaje que redacta las respuestas finales (en este proyecto, un modelo servido por Groq). |
| **Embedding** | Representación numérica del significado de un texto, usada para comparar qué tan parecidos son dos fragmentos. |
| **Chunk / chunking** | Fragmento en el que se divide un documento largo, y el proceso de dividirlo. |
| **Vector store / base vectorial** | El lugar donde se guardan los embeddings de todos los fragmentos, preparado para buscar rápidamente los más parecidos a una pregunta. |
| **Similitud de coseno** | La forma matemática de medir "cuánto se parecen" dos embeddings (dos vectores). |
| **STT** (*Speech-to-Text*) | Convertir voz grabada en texto (aquí, con Whisper, en local). |
| **TTS** (*Text-to-Speech*) | Convertir texto en audio hablado (aquí, con Piper, en local). |
| **Prompt / system prompt** | Las instrucciones que le damos al LLM antes de la pregunta del usuario, para decirle cómo debe comportarse. |

## Arquitectura y por qué se eligió cada pieza

- **LLM (generación de respuestas)**: [Groq](https://console.groq.com) (API
  compatible con OpenAI, muy rápida). Es la única parte que necesita
  internet durante el evento.
- **Embeddings**: locales, con `sentence-transformers` (modelo multilingüe,
  funciona bien en español), para no depender de una API externa de pago
  solo para indexar los PDFs.
- **Base de datos vectorial**: almacén propio muy simple (numpy + JSON),
  persistente en `data/vector_store`. Se descartó Chroma porque su
  dependencia `chroma-hnswlib` no tiene wheel para Windows + Python 3.13 y
  exige compilador de C++; para el volumen de una demo con alumnos, una
  búsqueda por similitud de coseno con numpy es más que suficiente y evita
  esa complicación de instalación.
- **Voz → texto**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  local, sin depender de una API externa.
- **Texto → voz**: [Piper](https://github.com/rhasspy/piper), local, con
  voces en español.
- **Backend**: FastAPI (Python), expone la API y sirve también el frontend.
- **Frontend**: página HTML/JS/CSS sencilla, sin frameworks, servida por el
  propio backend.

Solo las llamadas al LLM (Groq) necesitan internet; todo lo demás
(embeddings, base vectorial, voz) funciona en local, para que el evento no
dependa de una conexión perfecta.

## Estructura del proyecto

```
backend/
  config.py   → carga la configuración desde .env
  rag.py      → extracción/troceado de PDFs, embeddings y base vectorial
  llm.py      → construye el prompt y llama a Groq
  stt.py      → transcribe audio a texto con faster-whisper
  tts.py      → convierte texto en audio con Piper
  main.py     → API FastAPI que conecta todo lo anterior con el frontend

frontend/
  index.html  → estructura de la página (subida de PDFs + chat)
  style.css   → estilos visuales
  app.js      → lógica de la interfaz (subir, preguntar, grabar voz, reproducir audio)

data/
  uploads/       → PDFs subidos (se generan en tiempo de ejecución)
  vector_store/  → embeddings + metadatos indexados (se generan en tiempo de ejecución)

models/       → aquí van los ficheros de voz de Piper (no se suben a git)
```

## Instalación

### 1. Entorno de Python

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Variable de entorno con la API key de Groq

Copia `.env.example` a `.env` y añade tu clave de Groq (sacada en
https://console.groq.com/keys):

```bash
copy .env.example .env
```

Edita `.env` y rellena `GROQ_API_KEY`. Revisa también `GROQ_MODEL`: Groq
depreca o renombra modelos con cierta frecuencia, así que si al preguntar
sale un error `model_not_found`, entra en
[console.groq.com/docs/models](https://console.groq.com/docs/models) y pon
ahí el nombre de un modelo vigente.

### 3. Descargar la voz de Piper (texto → voz en español)

Piper necesita un modelo de voz `.onnx` descargado localmente. Por ejemplo,
para la voz `es_ES-davefx-medium`:

1. Crea una carpeta `models/` en la raíz del proyecto (si no existe ya).
2. Descarga los dos ficheros de la voz desde
   [rhasspy/piper-voices en Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium):
   - `es_ES-davefx-medium.onnx`
   - `es_ES-davefx-medium.onnx.json`
3. Colócalos ambos dentro de `models/`.

Si prefieres otra voz en español, cambia `PIPER_MODEL_PATH` en `.env` (y
descarga el `.onnx` + `.onnx.json` correspondientes).

### 4. Modelo de Whisper (voz → texto)

No hay que descargar nada a mano: `faster-whisper` descarga el modelo
automáticamente la primera vez que se usa (necesita internet esa primera
vez) y luego lo deja cacheado para funcionar sin conexión.

## Arrancar la aplicación

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000` en el navegador (Chrome recomendado, para que
el micrófono funcione bien). Si vais a proyectar la pantalla en el evento,
esta misma máquina hace de servidor y de "kiosko" a la vez.

## Uso durante la visita

1. Los alumnos suben todos sus PDFs de golpe desde la sección "Tus
   documentos" (se pueden arrastrar o seleccionar varios ficheros a la vez).
2. Preguntan escribiendo o pulsando el botón del micrófono 🎤 para hablar.
3. La respuesta aparece en texto (con las páginas de origen citadas) y se
   reproduce automáticamente en voz.
4. Entre grupos de alumnos, pulsa "Empezar de cero" para borrar los PDFs y
   el historial y dejarlo listo para el siguiente grupo.

## Personalización rápida

Todo esto se ajusta en `.env` (ver `.env.example` para la lista completa):

- `TOP_K`: cuántos fragmentos de contexto se recuperan por pregunta (por
  defecto 4). Subirlo da más contexto al modelo pero hace las respuestas más
  lentas y caras.
- `WHISPER_MODEL_SIZE`: tamaño del modelo de voz→texto (`tiny`, `base`,
  `small`, `medium`). Más grande = más preciso pero más lento.
- `EMBEDDING_MODEL` / `GROQ_MODEL` / `PIPER_MODEL_PATH`: para cambiar el
  modelo de embeddings, el modelo de Groq o la voz de Piper.

El tamaño y solapamiento de los fragmentos (`chunk_size`, `overlap`) están en
[backend/rag.py](backend/rag.py), en la función `chunk_text`.

## Notas y problemas conocidos

- El primer arranque tarda algo más porque se descargan los modelos de
  embeddings y de Whisper.
- Si en el evento falla la conexión a internet, las respuestas del LLM
  (Groq) dejarán de funcionar aunque la voz y la búsqueda en los PDFs sigan
  funcionando en local; conviene comprobar la conexión del sitio con
  antelación.
- En Windows, algunos paquetes con extensiones compiladas en C++
  (`chroma-hnswlib`, versiones antiguas de `piper-tts`) no tienen wheel
  precompilado para Python 3.13 y fallan al instalar pidiendo "Microsoft
  Visual C++ Build Tools". Por eso este proyecto evita esas dependencias
  (ver la sección de arquitectura); si en el futuro añades una librería
  nueva y te encuentras el mismo error, prueba primero a buscar una
  alternativa sin extensión compilada antes de instalar el compilador.
