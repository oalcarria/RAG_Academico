const dropzone = document.getElementById("dropzone");
const pdfInput = document.getElementById("pdf-input");
const fileListEl = document.getElementById("file-list");
const uploadBtn = document.getElementById("upload-btn");
const uploadBtnLabel = document.getElementById("upload-btn-label");
const uploadStatus = document.getElementById("upload-status");
const resetBtn = document.getElementById("reset-btn");

const kbPill = document.getElementById("kb-pill");
const kbCount = document.getElementById("kb-count");
const docsLoaded = document.getElementById("docs-loaded");
const loadedList = document.getElementById("loaded-list");

const chatLog = document.getElementById("chat-log");
const emptyState = document.getElementById("empty-state");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const askStatus = document.getElementById("ask-status");
const ttsAudio = document.getElementById("tts-audio");
const toast = document.getElementById("toast");

// Staged files waiting to be uploaded. A plain array because FileList is
// immutable and we let the user drop files in several batches and remove them.
let stagedFiles = [];

const FILE_SVG = `<svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`;

function showToast(message, kind = "") {
  toast.textContent = message;
  toast.className = `toast ${kind}`;
  toast.hidden = false;
  requestAnimationFrame(() => toast.classList.add("show"));
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => (toast.hidden = true), 300);
  }, 3200);
}

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function formatSize(bytes) {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Minimal markdown rendering: the model returns **bold**, *italics* and simple
// bullet/numbered lists, and showing the raw asterisks looks broken to students.
function inlineMarkdown(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*(?!\s)([^*]+?)\*(?=[\s.,;:)!?]|$)/g, "$1<em>$2</em>");
}

function renderAnswer(text) {
  return escapeHtml(text)
    .split(/\n{2,}/)
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (!lines.length) return "";

      const isBulleted = lines.every((l) => /^[-*•]\s+/.test(l));
      if (isBulleted) {
        const items = lines.map((l) => `<li>${inlineMarkdown(l.replace(/^[-*•]\s+/, ""))}</li>`);
        return `<ul>${items.join("")}</ul>`;
      }

      const isNumbered = lines.length > 1 && lines.every((l) => /^\d+[.)]\s+/.test(l));
      if (isNumbered) {
        const items = lines.map((l) => `<li>${inlineMarkdown(l.replace(/^\d+[.)]\s+/, ""))}</li>`);
        return `<ol>${items.join("")}</ol>`;
      }

      return `<p>${inlineMarkdown(lines.join("<br>"))}</p>`;
    })
    .join("");
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    updateKbPill(data.total_chunks);
  } catch {
    // Status is cosmetic; ignore failures so the page still works.
  }
}

function updateKbPill(totalChunks) {
  if (totalChunks > 0) {
    kbCount.textContent = `${totalChunks} fragmento${totalChunks === 1 ? "" : "s"} indexados`;
    kbPill.hidden = false;
  } else {
    kbPill.hidden = true;
  }
}

function addFiles(files) {
  const pdfs = Array.from(files).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
  const skipped = files.length - pdfs.length;

  for (const file of pdfs) {
    if (!stagedFiles.some((f) => f.name === file.name && f.size === file.size)) {
      stagedFiles.push(file);
    }
  }

  if (skipped > 0) showToast("Solo se admiten archivos PDF", "error");
  renderFileList();
}

function renderFileList() {
  fileListEl.innerHTML = "";
  for (const [index, file] of stagedFiles.entries()) {
    const li = document.createElement("li");
    li.className = "file-item";
    li.innerHTML = `
      ${FILE_SVG}
      <span class="file-name">${escapeHtml(file.name)}</span>
      <span class="file-meta">${formatSize(file.size)}</span>
      <button class="remove" type="button" aria-label="Quitar ${escapeHtml(file.name)}">&times;</button>`;
    li.querySelector(".remove").addEventListener("click", () => {
      stagedFiles.splice(index, 1);
      renderFileList();
    });
    fileListEl.appendChild(li);
  }

  uploadBtn.disabled = stagedFiles.length === 0;
  uploadBtnLabel.textContent = stagedFiles.length
    ? `Subir ${stagedFiles.length} documento${stagedFiles.length === 1 ? "" : "s"}`
    : "Subir documentos";
}

pdfInput.addEventListener("change", () => {
  addFiles(pdfInput.files);
  pdfInput.value = "";
});

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);

["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);

dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

uploadBtn.addEventListener("click", async () => {
  if (!stagedFiles.length) return;

  const formData = new FormData();
  stagedFiles.forEach((file) => formData.append("files", file));

  uploadBtn.disabled = true;
  uploadBtnLabel.textContent = "Procesando...";
  setStatus(uploadStatus, "Leyendo e indexando los PDFs, esto puede tardar unos segundos...");

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error al subir los documentos");

    for (const doc of data.processed) {
      const li = document.createElement("li");
      li.className = "file-item";
      li.innerHTML = `
        ${FILE_SVG}
        <span class="file-name">${escapeHtml(doc.filename)}</span>
        <span class="file-meta">${doc.chunks} frag.</span>`;
      loadedList.appendChild(li);
    }
    docsLoaded.hidden = false;

    stagedFiles = [];
    renderFileList();
    updateKbPill(data.total_chunks);
    setStatus(uploadStatus, "");
    showToast(`${data.processed.length} documento(s) listos para consultar`, "success");
    questionInput.focus();
  } catch (err) {
    setStatus(uploadStatus, err.message, true);
    showToast(err.message, "error");
  } finally {
    uploadBtn.disabled = stagedFiles.length === 0;
    renderFileList();
  }
});

resetBtn.addEventListener("click", async () => {
  if (!confirm("¿Borrar todos los documentos subidos y el historial para empezar de cero?")) return;

  await fetch("/api/reset", { method: "POST" });

  stagedFiles = [];
  renderFileList();
  loadedList.innerHTML = "";
  docsLoaded.hidden = true;
  chatLog.innerHTML = "";
  chatLog.appendChild(emptyState);
  emptyState.hidden = false;
  updateKbPill(0);
  setStatus(uploadStatus, "");
  showToast("Base de conocimiento reiniciada", "success");
});

function addMessage(role, text, sources) {
  emptyState.hidden = true;

  const msg = document.createElement("div");
  msg.className = `msg ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "bot" ? "🤖" : "🙋";
  avatar.setAttribute("aria-hidden", "true");

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (role === "bot") {
    bubble.innerHTML = renderAnswer(text);

    if (sources && sources.length) {
      const seen = new Set();
      const wrap = document.createElement("div");
      wrap.className = "sources";
      for (const s of sources) {
        const key = `${s.source}#${s.page}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const tag = document.createElement("span");
        tag.className = "source-tag";
        tag.textContent = `📄 ${s.source} · p. ${s.page}`;
        wrap.appendChild(tag);
      }
      bubble.appendChild(wrap);
    }

    const replay = document.createElement("button");
    replay.className = "replay";
    replay.type = "button";
    replay.innerHTML = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg> Escuchar de nuevo`;
    replay.addEventListener("click", () => playAnswer(text));
    bubble.appendChild(replay);
  } else {
    bubble.textContent = text;
  }

  msg.append(avatar, bubble);
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function showTyping() {
  emptyState.hidden = true;
  const msg = document.createElement("div");
  msg.className = "msg bot";
  msg.id = "typing-msg";
  msg.innerHTML = `
    <div class="avatar" aria-hidden="true">🤖</div>
    <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
  chatLog.appendChild(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function hideTyping() {
  document.getElementById("typing-msg")?.remove();
}

async function askQuestion(question) {
  if (!question) return;

  addMessage("user", question);
  questionInput.value = "";
  sendBtn.disabled = true;
  showTyping();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    hideTyping();
    if (!res.ok) throw new Error(data.detail || "Error al procesar la pregunta");

    addMessage("bot", data.answer, data.sources);
    setStatus(askStatus, "");
    playAnswer(data.answer);
  } catch (err) {
    hideTyping();
    setStatus(askStatus, err.message, true);
    showToast(err.message, "error");
  } finally {
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

async function playAnswer(text) {
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    ttsAudio.src = URL.createObjectURL(blob);
    await ttsAudio.play();
  } catch {
    // Voice playback is best-effort; the text answer is already on screen.
  }
}

sendBtn.addEventListener("click", () => askQuestion(questionInput.value.trim()));
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion(questionInput.value.trim());
});

document.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => askQuestion(chip.dataset.q))
);

let mediaRecorder = null;
let recordedChunks = [];

async function toggleRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    showToast("No se pudo acceder al micrófono", "error");
    return;
  }

  mediaRecorder = new MediaRecorder(stream);
  recordedChunks = [];

  mediaRecorder.ondataavailable = (e) => recordedChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((track) => track.stop());
    micBtn.classList.remove("recording");
    setStatus(askStatus, "Transcribiendo tu pregunta...");

    const formData = new FormData();
    formData.append("audio", new Blob(recordedChunks, { type: "audio/webm" }), "question.webm");

    try {
      const res = await fetch("/api/stt", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error al transcribir el audio");
      setStatus(askStatus, "");
      if (data.text) {
        askQuestion(data.text);
      } else {
        showToast("No se ha entendido nada, inténtalo otra vez", "error");
      }
    } catch (err) {
      setStatus(askStatus, err.message, true);
      showToast(err.message, "error");
    }
  };

  mediaRecorder.start();
  micBtn.classList.add("recording");
  setStatus(askStatus, "Grabando... pulsa el micrófono otra vez para enviar");
}

micBtn.addEventListener("click", toggleRecording);

refreshStatus();
renderFileList();
