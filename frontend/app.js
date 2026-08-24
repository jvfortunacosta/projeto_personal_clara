// Sem build step: JS puro, sem dependências externas.

const tabTrack = document.getElementById("tab-track");
const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

tabButtons.forEach((btn, index) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    tabPanels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    tabTrack.dataset.active = String(index);
  });
});

// Controle segmentado (tipo de documento): mantém a mesma API de um
// elemento único com `.dataset.value`, como um <select> teria `.value`.
document.querySelectorAll(".segmented").forEach((group) => {
  const buttons = group.querySelectorAll(".segmented-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-checked", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-checked", "true");
      group.dataset.value = btn.dataset.value;
    });
  });
});

function getBrandName() {
  return document.getElementById("brand-name").value.trim();
}

function setStatus(el, message, state = "idle") {
  el.dataset.state = state;
  el.querySelector(".status-text").textContent = message;
}

async function previewInto(endpoint, text, frame, statusEl, docType) {
  setStatus(statusEl, "Gerando pré-visualização…", "busy");
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, brand_name: getBrandName(), doc_type: docType }),
    });
    if (!res.ok) throw new Error(`Erro ${res.status}`);
    const html = await res.text();
    frame.srcdoc = html;
    setStatus(statusEl, "Pré-visualização atualizada", "ok");
  } catch (err) {
    setStatus(statusEl, `Falha ao pré-visualizar: ${err.message}`, "error");
  }
}

async function downloadPdf(endpoint, text, statusEl, filenameFallback, docType) {
  setStatus(statusEl, "Gerando PDF…", "busy");
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, brand_name: getBrandName(), doc_type: docType }),
    });
    if (!res.ok) throw new Error(`Erro ${res.status}`);
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : filenameFallback;

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setStatus(statusEl, "PDF baixado", "ok");
  } catch (err) {
    setStatus(statusEl, `Falha ao gerar PDF: ${err.message}`, "error");
  }
}

// Plano Alimentar / Treino
const mealPlanText = document.getElementById("meal-plan-text");
const mealPlanFrame = document.getElementById("meal-plan-frame");
const mealPlanStatus = document.getElementById("meal-plan-status");
const mealPlanDocType = document.getElementById("meal-plan-doc-type");

document.getElementById("meal-plan-preview-btn").addEventListener("click", () => {
  previewInto("/api/plan/preview", mealPlanText.value, mealPlanFrame, mealPlanStatus, mealPlanDocType.dataset.value);
});

document.getElementById("meal-plan-pdf-btn").addEventListener("click", () => {
  downloadPdf("/api/plan/pdf", mealPlanText.value, mealPlanStatus, "plano.pdf", mealPlanDocType.dataset.value);
});

// Check-in
const checkinText = document.getElementById("checkin-text");
const checkinFrame = document.getElementById("checkin-frame");
const checkinStatus = document.getElementById("checkin-status");

document.getElementById("checkin-preview-btn").addEventListener("click", () => {
  previewInto("/api/checkin/preview", checkinText.value, checkinFrame, checkinStatus);
});

document.getElementById("checkin-pdf-btn").addEventListener("click", () => {
  downloadPdf("/api/checkin/pdf", checkinText.value, checkinStatus, "checkin.pdf");
});
