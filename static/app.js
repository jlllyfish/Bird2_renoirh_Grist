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
const previewSection = document.getElementById("previewSection");
const previewBody    = document.getElementById("previewBody");

let selectedFiles = [];
let previewSeq = 0;      // ignore les réponses d'aperçu périmées
let previewOk = false;   // l'envoi n'est possible que si l'aperçu est valide

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
    resetPreview();
    return;
  }
  fileSection.classList.remove("hidden");
  btnClear.classList.remove("hidden");
  btnSend.disabled = true; // réactivé quand l'aperçu est valide
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
        <div class="file-name">${escHtml(f.name)}</div>
        <div class="file-meta">${f.name.toLowerCase().endsWith(".csv") ? "CSV" : "Excel"} · ${formatDate(f.lastModified)}</div>
      </div>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-remove" onclick="removeFile(${i})" title="Retirer" aria-label="Retirer ${escHtml(f.name)}">✕</button>
    </div>
  `).join("");

  refreshPreview();
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

// ── Aperçu avant envoi ──────────────────────────────────────
function resetPreview() {
  previewSeq++;
  previewOk = false;
  previewSection.classList.add("hidden");
  previewBody.innerHTML = "";
}

async function refreshPreview() {
  const seq = ++previewSeq;
  previewOk = false;
  previewSection.classList.remove("hidden");
  previewBody.innerHTML = `<p class="preview-loading">Analyse des fichiers…</p>`;

  const formData = new FormData();
  for (const f of selectedFiles) formData.append("files", f);

  let data;
  try {
    const resp = await fetch("/api/preview", { method: "POST", body: formData });
    data = await resp.json();
  } catch (e) {
    data = { success: false, error: String(e) };
  }
  if (seq !== previewSeq) return; // une analyse plus récente est en cours
  renderPreview(data);
}

const ICON_WARN = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
const ICON_CHEV = `<svg class="acc-chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;

function plural(n, word) {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${escHtml(text)}</span>`;
}

// items : fragments HTML déjà échappés
function alertBox(kind, items) {
  const li = items.map((t) => `<li>${t}</li>`).join("");
  const role = kind === "err" ? "alert" : "status";
  return `<div class="alert alert-${kind}" role="${role}"><div class="alert-icon">${ICON_WARN}</div><ul class="alert-text">${li}</ul></div>`;
}

function renderPreviewFile(f) {
  const sub = f.kind === "csv"
    ? `CSV · séparateur <code>;</code> · encodage <code>cp1252</code>`
    : `Onglet <code>${escHtml(f.sheet)}</code>`;

  const rows = f.columns.map((c) => `
    <tr>
      <td>${escHtml(c.source)}</td>
      <td class="tbl-val">${c.first ? escHtml(c.first) : `<span class="tbl-empty">—</span>`}</td>
      <td><code>${escHtml(c.grist)}</code>${c.key ? badge("Clé", "badge-key") : ""}</td>
    </tr>`).join("");

  const shown = f.ignored.slice(0, 10).map(escHtml).join(", ");
  const ignored = f.ignored.length
    ? `<p class="acc-ignored">${plural(f.ignored.length, "colonne")} non importée${f.ignored.length > 1 ? "s" : ""} : ${shown}${f.ignored.length > 10 ? ", …" : ""}</p>`
    : "";

  return `
    <details class="acc" open>
      <summary class="acc-head">
        <span class="acc-name">${escHtml(f.name)}</span>
        ${badge(f.role_label, f.role === "principal" ? "badge-main" : "badge-grey")}
        <span class="acc-meta">${plural(f.rows, "ligne")} · ${plural(f.cols_read, "colonne")} lue${f.cols_read > 1 ? "s" : ""} · ${f.columns.length} importée${f.columns.length > 1 ? "s" : ""}</span>
        ${ICON_CHEV}
      </summary>
      <div class="acc-body">
        <p class="acc-sub">${sub}</p>
        <div class="tbl-wrap">
          <table class="tbl">
            <caption class="sr-only">Colonnes lues dans ${escHtml(f.name)}</caption>
            <thead>
              <tr><th scope="col">Colonne du fichier</th><th scope="col">Première valeur</th><th scope="col">Colonne Grist</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        ${ignored}
      </div>
    </details>`;
}

function renderPreview(data) {
  previewOk = false;
  let html = `<h2 class="preview-title">Aperçu avant envoi</h2>`;

  if (!data.success) {
    html += alertBox("err", [escHtml(data.error || "Analyse impossible")]);
  } else if (!data.recognized) {
    const inv = data.files.map((f) =>
      f.error
        ? `<strong>${escHtml(f.name)}</strong> — fichier illisible : ${escHtml(f.error)}`
        : `<strong>${escHtml(f.name)}</strong> — onglets : ${f.sheets.map(escHtml).join(", ") || "aucun"}`
    );
    html += alertBox("err", [
      "Ces fichiers ne correspondent à aucun cas connu (voir mapping.py).",
      ...inv,
    ]);
  } else {
    previewOk = data.total_rows > 0;
    html += `
      <p class="preview-summary">
        ${badge("Cas : " + data.case_label, "badge-ok")}
        <span>${plural(data.files_recognized, "fichier")} reconnu${data.files_recognized > 1 ? "s" : ""} · ${plural(data.total_rows, "ligne")} · mode Upsert sur ${escHtml(data.upsert_keys.join(", "))}</span>
      </p>`;
    if (data.warnings.length) html += alertBox("warn", data.warnings.map(escHtml));
    html += `<div class="acc-group">${data.files.map(renderPreviewFile).join("")}</div>`;
    html += `<p class="preview-note">« — » : cellule vide · ${badge("Clé", "badge-key")} : colonne utilisée pour l'upsert (fichier principal) ou pour la jointure entre fichiers.</p>`;
  }

  previewBody.innerHTML = html;
  btnSend.disabled = !previewOk;
}

// ── Import ──────────────────────────────────────────────────
async function doImport() {
  if (!selectedFiles.length || !previewOk) return;

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
    btnSend.disabled = !previewOk;
  }
}

function showResult(data) {
  resultEmpty.classList.add("hidden");
  resultCard.classList.remove("hidden");

  if (data.success) {
    const total = data.rows_processed || 0;
    const added = data.inserted || 0;
    const files = data.files_processed || 0;
    const detailed = data.modified !== null && data.modified !== undefined;
    const table = data.table ? `Table « ${escHtml(data.table)} »` : "Table Grist";

    // Cercle SVG (circonférence ≈ 163.4 pour r=26)
    const circ = 163.4;
    const statRow = (label, sub, value, ratio, color) => `
        <div class="stat-row">
          <div><div class="stat-label">${label}</div><div class="stat-sub">${sub}</div></div>
          <div class="stat-circle">
            <svg width="48" height="48" viewBox="0 0 60 60">
              <circle cx="30" cy="30" r="26" fill="none" stroke="#FFF6D8" stroke-width="6"/>
              <circle cx="30" cy="30" r="26" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${Math.min(ratio, 1) * circ} ${circ}" transform="rotate(-90 30 30)"/>
            </svg>
            <div class="stat-circle-val">${value}</div>
          </div>
        </div>`;
    const part = (n) => (total > 0 ? n / total : 0);

    const rowsHtml = detailed
      ? statRow("Lignes ajoutées", "nouvelles dans Grist", added, part(added), "#F7C600") +
        statRow("Lignes modifiées", "valeurs mises à jour", data.modified, part(data.modified), "#171717") +
        statRow("Lignes inchangées", "déjà à jour", data.unchanged, part(data.unchanged), "#B89400")
      : statRow("Lignes ajoutées", "sur ce lot", added, part(added), "#F7C600") +
        statRow("Lignes traitées", "au total", total, total > 0 ? 1 : 0, "#171717") +
        statRow("Fichiers traités", "ce lot", files, Math.min(files / 5, 1), "#B89400");

    const keysHtml = data.upsert && data.upsert_keys?.length
      ? `<div class="keys-block">
          <span class="keys-label-text">Clés d'upsert</span>
          <div class="keys-tags">${data.upsert_keys.map(k => `<span class="key-tag">${escHtml(k)}</span>`).join("")}</div>
         </div>`
      : "";

    let title;
    let sub;
    if (data.up_to_date) {
      title = `${table} déjà à jour`;
      sub = `Aucune ligne ajoutée ni modifiée · ${plural(total, "ligne")} vérifiée${total > 1 ? "s" : ""}`;
    } else if (detailed) {
      title = "Synchronisation réussie";
      sub = `${table} : ${added} ajoutée${added > 1 ? "s" : ""} · ${data.modified} modifiée${data.modified > 1 ? "s" : ""} · ${data.unchanged} inchangée${data.unchanged > 1 ? "s" : ""}`;
    } else {
      title = "Synchronisation réussie";
      sub = `${table} · ${plural(total, "ligne")} traitée${total > 1 ? "s" : ""}`;
    }

    resultContent.innerHTML = `
      <div class="stat-block">${rowsHtml}
      </div>
      ${keysHtml}
      <div class="result-ok-banner">
        <div class="ok-check">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div class="result-ok-text">
          <strong>${title}</strong>
          <span>${sub}</span>
        </div>
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
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function quitApp() {
  if (!confirm("Quitter Bird ?")) return;
  await fetch("/api/quit", { method: "POST" });
  window.close();
}

setInterval(() => {
  fetch("/api/ping", { method: "POST" }).catch(() => {});
}, 5000);
