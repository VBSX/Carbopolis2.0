(() => {
  const reportUrl = "/api/lab/public_reports";
  const reportList = document.getElementById("public-report-list");
  const toast = document.getElementById("public-report-toast");
  const toastClose = document.getElementById("public-report-toast-close");

  function readLastReportId() {
    try {
      return localStorage.getItem("last_report_id");
    } catch (error) {
      console.error("Não foi possível acessar o armazenamento local de notificações.", error);
      return null;
    }
  }

  function storeLastReportId(id) {
    try {
      localStorage.setItem("last_report_id", String(id));
    } catch (error) {
      console.error("Não foi possível salvar o último laudo visto.", error);
    }
  }

  const savedLastReportId = readLastReportId();
  let lastReportId = Number(savedLastReportId || 0);
  let hasBaseline = savedLastReportId !== null;
  let isChecking = false;

  function addReportCard(report) {
    if (!reportList || reportList.querySelector(`[data-report-id="${report.id}"]`)) {
      return;
    }

    const card = document.createElement("article");
    card.className = "public-report-card rounded-xl border border-cyan-800 bg-[#0a1728] p-3";
    card.dataset.reportId = report.id;

    const headingRow = document.createElement("div");
    headingRow.className = "flex justify-between items-start gap-2";
    const title = document.createElement("h3");
    title.className = "font-bold text-cyan-100";
    title.textContent = report.title;
    const timestamp = document.createElement("span");
    timestamp.className = "text-xs text-slate-400 whitespace-nowrap";
    timestamp.textContent = report.timestamp;
    headingRow.append(title, timestamp);

    const el = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const body = [];
    const origin = el("p", "report-origin mt-2");
    origin.append(el("b", "", "Origem dos dados:"), ...(report.origin.length ? report.origin : ["Instituto de Pesquisas (projeção do EIA)"]).map(o => el("span", "block", `• ${o}`)));
    body.push(origin);
    for (const group of report.groups) {
      body.push(el("h4", "report-group", group.name === "Água" ? "💧 Análise da água" : "🌫️ Análise do ar"));
      const list = el("ul", "report-items");
      for (const item of group.items) {
        const row = el("li");
        row.append(
          el("span", "", item.label),
          el("b", "", item.value),
          el("em", item.alert ? "alert" : "ok", item.alert ? "⚠️ Acima" : "✓ Ok"),
          el("small", "", `Ref.: ${item.reference}`)
        );
        list.append(row);
      }
      body.push(list);
    }
    if (report.notes) {
      const notes = el("p", "report-notes");
      notes.append(el("b", "", "Observações: "), report.notes);
      body.push(notes);
    }
    const author = document.createElement("p");
    author.className = "text-xs text-amber-200 mt-2";
    author.textContent = `Publicado por: ${report.author}`;
    card.append(headingRow, ...body, author);

    const emptyMessage = document.getElementById("public-report-empty");
    if (emptyMessage) {
      emptyMessage.remove();
    }
    reportList.prepend(card);
  }

  function showToast() {
    if (!toast) {
      return;
    }
    toast.classList.remove("hidden");
    toast.classList.add("animate-pulse");
  }

  async function checkForReports() {
    if (isChecking) {
      return;
    }
    isChecking = true;
    try {
      const response = await fetch(reportUrl, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`Consulta de laudos falhou: HTTP ${response.status}`);
      }
      const reports = await response.json();
      const latestId = reports.reduce((latest, report) => Math.max(latest, report.id), 0);

      if (!hasBaseline) {
        lastReportId = latestId;
        hasBaseline = true;
        storeLastReportId(lastReportId);
      } else if (latestId > lastReportId) {
        reports
          .filter((report) => report.id > lastReportId)
          .sort((a, b) => a.id - b.id)
          .forEach(addReportCard);
        lastReportId = latestId;
        storeLastReportId(lastReportId);
        showToast();
      }
    } catch (error) {
      console.error("Não foi possível atualizar os laudos públicos.", error);
    } finally {
      isChecking = false;
    }
  }

  if (toastClose) {
    toastClose.addEventListener("click", () => {
      toast.classList.add("hidden");
      toast.classList.remove("animate-pulse");
    });
  }

  checkForReports();
  window.setInterval(checkForReports, 15000);
})();
