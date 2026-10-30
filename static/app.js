const fileInput   = document.getElementById("fileInput");
const dropZone    = document.getElementById("dropZone");
const fileList    = document.getElementById("fileList");
const fileSection = document.getElementById("fileSection");
const fileCount   = document.getElementById("fileCount");
const btnSend     = document.getElementById("btnSend");
const btnClear    = document.getElementById("btnClear");
const resultCard  = document.getElementById("resultCard");
const resultContent = document.getElementById("resultContent");
const resultEmpty = document.getElementById("resultEmpty");
const overlay     = document.getElementById("progressOverlay");

let selectedFiles = [];

// ── File input ──────────────────────────────────────────────
fileInput.addEventListener("change", () => addFiles(fileInput.files));

// ── Drag & drop ─────────────────────────────────────────────
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  addFiles(e.dataTransfer.files);
});
dropZone.addEventListener("click", (e) => {
  if (e.target.closest("label")) return;
  fileInput.click();
});

function addFiles(fileListObj) {
  const allowed = [".xlsx", ".xls", ".xlsm", ".csv"];
  for (const f of fileListObj) {
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) continue;
    if (selectedFiles.find((s) => s.name === f.name && s.size === f.size)) continue;
    selectedFiles.push(f);
  }
  renderFileList();
}

function renderFileList() {
  if (selectedFiles.length === 0) {
    fileSection.classList.add("hidden");
    btnClear.classList.add("hidden");
    btnSend.disabled = true;
    return;
  }
  fileSection.classList.remove("hidden");
  btnClear.classList.remove("hidden");
  btnSend.disabled = false;
  fileCount.textContent = `${selectedFiles.length} fichier${selectedFiles.length > 1 ? "s" : ""}`;

  fileList.innerHTML = selectedFiles.map((f, i) => `
    <div class="file-item">
      <div class="file-item-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
      </div>
      <div class="file-info">
        <div class="file-name">${f.name}</div>
        <div class="file-meta">Excel · ${formatDate(f.lastModified)}</div>
      </div>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-remove" onclick="removeFile(${i})" title="Retirer">✕</button>
    </div>
  `).join("");
}

function removeFile(idx) {
  selectedFiles.splice(idx, 1);
  renderFileList();
}

function clearFiles() {
  selectedFiles = [];
  fileInput.value = "";
  renderFileList();
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " o";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " Ko";
  return (bytes / (1024 * 1024)).toFixed(1) + " Mo";
}

function formatDate(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// ── Import ──────────────────────────────────────────────────
async function doImport() {
  if (!selectedFiles.length) return;

  overlay.classList.remove("hidden");
  btnSend.disabled = true;

  const formData = new FormData();
  for (const f of selectedFiles) formData.append("files", f);

  try {
    const resp = await fetch("/api/import", { method: "POST", body: formData });
    const data = await resp.json();
    showResult(data);
  } catch (e) {
    showResult({ success: false, error: String(e) });
  } finally {
    overlay.classList.add("hidden");
    btnSend.disabled = false;
  }
}

function showResult(data) {
  resultEmpty.classList.add("hidden");
  resultCard.classList.remove("hidden");

  if (data.success) {
    const total = data.rows_processed || 0;
    const added = data.inserted || 0;
    const files = data.files_processed || 0;

    // Calcul des arcs SVG (circonférence ≈ 163.4 pour r=26)
    const circ = 163.4;
    const arcAdded = Math.min((added / Math.max(total, 1)) * circ, circ);
    const arcTotal = Math.min((total / Math.max(total + 10, 1)) * circ, circ);
    const arcFiles = Math.min((files / 5) * circ, circ);

    const keysHtml = data.upsert && data.upsert_keys?.length
      ? `<div class="keys-block">
          <span class="keys-label-text">Clés d'upsert</span>
          <div class="keys-tags">${data.upsert_keys.map(k => `<span class="key-tag">${k}</span>`).join("")}</div>
         </div>`
      : "";

    resultContent.innerHTML = `
      <div class="stat-block">
        <div class="stat-row">
          <div><div class="stat-label">Lignes ajoutées</div><div class="stat-sub">sur ce lot</div></div>
          <div class="stat-circle">
            <svg width="48" height="48" viewBox="0 0 60 60">
              <circle cx="30" cy="30" r="26" fill="none" stroke="#F1EFFC" stroke-width="6"/>
              <circle cx="30" cy="30" r="26" fill="none" stroke="#5B4FE8" stroke-width="6" stroke-linecap="round" stroke-dasharray="${arcAdded} ${circ}" transform="rotate(-90 30 30)"/>
            </svg>
            <div class="stat-circle-val">${added}</div>
          </div>
        </div>
        <div class="stat-row">
          <div><div class="stat-label">Lignes traitées</div><div class="stat-sub">au total</div></div>
          <div class="stat-circle">
            <svg width="48" height="48" viewBox="0 0 60 60">
              <circle cx="30" cy="30" r="26" fill="none" stroke="#F1EFFC" stroke-width="6"/>
              <circle cx="30" cy="30" r="26" fill="none" stroke="#8B7FF0" stroke-width="6" stroke-linecap="round" stroke-dasharray="${arcTotal} ${circ}" transform="rotate(-90 30 30)"/>
            </svg>
            <div class="stat-circle-val">${total}</div>
          </div>
        </div>
        <div class="stat-row">
          <div><div class="stat-label">Fichiers traités</div><div class="stat-sub">ce lot</div></div>
          <div class="stat-circle">
            <svg width="48" height="48" viewBox="0 0 60 60">
              <circle cx="30" cy="30" r="26" fill="none" stroke="#F1EFFC" stroke-width="6"/>
              <circle cx="30" cy="30" r="26" fill="none" stroke="#C4BDF7" stroke-width="6" stroke-linecap="round" stroke-dasharray="${arcFiles} ${circ}" transform="rotate(-90 30 30)"/>
            </svg>
            <div class="stat-circle-val">${files}</div>
          </div>
        </div>
      </div>
      ${keysHtml}
      <div class="result-ok-banner">
        <div class="ok-check">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <span>Synchronisation réussie</span>
      </div>`;
  } else {
    resultContent.innerHTML = `
      <div class="result-err-banner">
        <h3>✕ Erreur</h3>
        <pre>${escHtml(data.error || "Erreur inconnue")}</pre>
      </div>`;
  }
}

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function quitApp() {
  if (!confirm("Quitter Bird ?")) return;
  await fetch("/api/quit", { method: "POST" });
  window.close();
}

setInterval(() => {
  fetch("/api/ping", { method: "POST" }).catch(() => {});
}, 5000);
