/**
 * Sequential Health-State Recognition — Frontend Application
 *
 * Simple, vanilla JavaScript SPA that communicates with the Flask JSON API.
 * Features:
 *  - Clean top navbar with segmented tabs (Dashboard, Observations, Analysis, About)
 *  - 1-click Case Pills switcher and Case Dropdown
 *  - Auto-selects Case 1 on initial load
 *  - Auto-runs rule-based analysis on case selection for instant dashboard stats
 *  - Clean, structured sequential trend timelines and flagged observation breakdowns
 */

(function () {
    "use strict";

    // ── State ─────────────────────────────────────────────────
    let currentView = "dashboard";
    let selectedCaseId = null;
    let casesData = [];
    let currentSignals = [];
    let chartInstances = {};
    let obsOffset = 0;
    const OBS_LIMIT = 100;
    let latestAnalysisResult = null;

    // ── DOM References ────────────────────────────────────────
    const caseSelector = document.getElementById("case-selector");
    const casePills = document.getElementById("case-pills");
    const signalFilter = document.getElementById("signal-filter");
    const btnAnalyzeDash = document.getElementById("btn-analyze-dashboard");
    const btnAnalyzeMain = document.getElementById("btn-analyze-main");
    const btnJumpObs = document.getElementById("btn-jump-observations");
    const btnJumpAnalysis = document.getElementById("btn-jump-analysis");

    // Views
    const views = {
        dashboard: document.getElementById("view-dashboard"),
        observations: document.getElementById("view-observations"),
        analysis: document.getElementById("view-analysis"),
        about: document.getElementById("view-about"),
        empty: document.getElementById("view-empty"),
    };

    // Navigation buttons
    const navButtons = document.querySelectorAll(".nav-btn[data-view]");

    // ── Initialisation ────────────────────────────────────────
    async function init() {
        setupNavigation();
        setupAnalyzeButtons();
        setupSignalFilter();
        setupJumpButtons();
        await loadCases();
    }

    // ── Navigation ────────────────────────────────────────────
    function setupNavigation() {
        navButtons.forEach((btn) => {
            btn.addEventListener("click", () => {
                switchView(btn.dataset.view);
            });
        });
    }

    function switchView(viewName) {
        currentView = viewName;

        // Hide all views
        Object.values(views).forEach((v) => {
            if (v) v.style.display = "none";
        });

        // Show selected view
        if (views[viewName]) {
            views[viewName].style.display = "block";
        }

        // Update nav button active states
        navButtons.forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.view === viewName);
        });

        // If switching to observations and we have a selected case, load them
        if (viewName === "observations" && selectedCaseId) {
            loadObservations();
        }

        // Scroll top smoothly
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function setupJumpButtons() {
        if (btnJumpObs) {
            btnJumpObs.addEventListener("click", () => switchView("observations"));
        }
        if (btnJumpAnalysis) {
            btnJumpAnalysis.addEventListener("click", () => switchView("analysis"));
        }
    }

    // ── API Helpers ───────────────────────────────────────────
    async function apiGet(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    }

    async function apiPost(url, body = {}) {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    }

    // ── Load Cases ────────────────────────────────────────────
    async function loadCases() {
        try {
            const data = await apiGet("/api/cases");
            casesData = data.cases || [];

            // Update stats
            const totalCasesElem = document.getElementById("stat-total-cases");
            if (totalCasesElem) totalCasesElem.textContent = casesData.length;

            if (casesData.length === 0) {
                showEmptyState();
                return;
            }

            hideEmptyState();

            // Populate selector dropdown & quick pills
            caseSelector.innerHTML = '<option value="">Select a case…</option>';
            if (casePills) casePills.innerHTML = "";

            casesData.forEach((c) => {
                // Dropdown option
                const opt = document.createElement("option");
                opt.value = c.id;
                opt.textContent = `Case ${c.source_case_id} (VitalDB)`;
                caseSelector.appendChild(opt);

                // Quick Pill button
                if (casePills) {
                    const pill = document.createElement("button");
                    pill.className = "case-pill";
                    pill.textContent = `Case ${c.source_case_id}`;
                    pill.dataset.id = c.id;
                    pill.title = `Switch to Case ${c.source_case_id}`;
                    pill.addEventListener("click", () => selectCase(c.id));
                    casePills.appendChild(pill);
                }
            });

            // Handle dropdown change
            caseSelector.addEventListener("change", () => {
                const val = caseSelector.value;
                if (val) selectCase(parseInt(val, 10));
            });

            // Automatically select Case 1 (or first available case) on page load!
            if (casesData.length > 0) {
                await selectCase(casesData[0].id);
            }
        } catch (err) {
            console.error("Failed to load cases:", err);
            showEmptyState();
        }
    }

    function showEmptyState() {
        Object.values(views).forEach((v) => { if (v) v.style.display = "none"; });
        if (views.empty) views.empty.style.display = "flex";
    }

    function hideEmptyState() {
        if (views.empty) views.empty.style.display = "none";
        if (views.dashboard) views.dashboard.style.display = "block";
    }

    // ── Select Case ───────────────────────────────────────────
    async function selectCase(caseId) {
        selectedCaseId = caseId;
        caseSelector.value = caseId;

        // Update pills
        if (casePills) {
            casePills.querySelectorAll(".case-pill").forEach((p) => {
                p.classList.toggle("active", parseInt(p.dataset.id, 10) === caseId);
            });
        }

        const caseObj = casesData.find((c) => c.id === caseId);
        const sourceId = caseObj ? caseObj.source_case_id : caseId;

        // Update active banner
        const badgeElem = document.getElementById("active-case-badge");
        const titleElem = document.getElementById("active-case-title");
        if (badgeElem) badgeElem.textContent = `Case ${sourceId}`;
        if (titleElem) titleElem.textContent = `Patient Monitoring Sequence — Case ${sourceId}`;

        // Enable buttons
        if (btnAnalyzeDash) btnAnalyzeDash.disabled = false;
        if (btnAnalyzeMain) btnAnalyzeMain.disabled = false;

        // Load signals, observation counts, and charts in parallel
        await Promise.all([loadSignals(), loadObservationCount()]);
        await loadCharts();

        // Reset analysis state until user explicitly clicks the button
        latestAnalysisResult = null;
        resetAnalysisUI(sourceId);

        // If currently viewing observations table, refresh it
        if (currentView === "observations") {
            obsOffset = 0;
            await loadObservations();
        }
    }

    // ── Signals ───────────────────────────────────────────────
    async function loadSignals() {
        if (!selectedCaseId) return;
        try {
            const data = await apiGet(`/api/cases/${selectedCaseId}/signals`);
            currentSignals = data.signals || [];

            // Update signal filter in Observations
            if (signalFilter) {
                signalFilter.innerHTML = '<option value="">All Signals</option>';
                currentSignals.forEach((s) => {
                    const opt = document.createElement("option");
                    opt.value = s.signal_name;
                    opt.textContent = `${formatSignalName(s.signal_name)} (${s.unit})`;
                    signalFilter.appendChild(opt);
                });
            }

            const captionElem = document.getElementById("stat-signals-caption");
            if (captionElem) {
                captionElem.textContent = `${currentSignals.length} vital signals recorded`;
            }
        } catch (err) {
            console.error("Failed to load signals:", err);
        }
    }

    async function loadObservationCount() {
        if (!selectedCaseId) return;
        try {
            const data = await apiGet(`/api/cases/${selectedCaseId}/observations?limit=1`);
            const totalObsElem = document.getElementById("stat-total-obs");
            if (totalObsElem) totalObsElem.textContent = data.total.toLocaleString();
        } catch (err) {
            const totalObsElem = document.getElementById("stat-total-obs");
            if (totalObsElem) totalObsElem.textContent = "—";
        }
    }

    // ── Charts ────────────────────────────────────────────────
    const CHART_COLORS = {
        heart_rate:   { line: "#ef4444", bg: "rgba(239,68,68,0.08)" },
        spo2:         { line: "#2563eb", bg: "rgba(37,99,235,0.08)" },
        systolic_bp:  { line: "#8b5cf6", bg: "rgba(139,92,246,0.08)" },
        diastolic_bp: { line: "#a855f7", bg: "rgba(168,85,247,0.08)" },
        temperature:  { line: "#f97316", bg: "rgba(249,115,22,0.08)" },
    };

    async function loadCharts() {
        clearCharts();
        if (!selectedCaseId || currentSignals.length === 0) return;

        const container = document.getElementById("charts-container");
        if (!container) return;
        container.innerHTML = "";

        // Create a line chart for each available vital track
        for (const sig of currentSignals) {
            try {
                const data = await apiGet(
                    `/api/cases/${selectedCaseId}/observations?signal=${sig.signal_name}&limit=2500`
                );
                const obs = data.observations || [];
                if (obs.length === 0) continue;

                const box = document.createElement("div");
                box.className = "chart-box";

                const colors = CHART_COLORS[sig.signal_name] || {
                    line: "#475569",
                    bg: "rgba(71,85,105,0.08)"
                };

                const title = document.createElement("h3");
                title.innerHTML = `
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${colors.line};"></span>
                    ${formatSignalName(sig.signal_name)}
                    <span style="font-weight:400;color:var(--text-muted);font-size:11px;margin-left:auto;">${sig.unit} · ${obs.length.toLocaleString()} pts</span>
                `;
                box.appendChild(title);

                const canvas = document.createElement("canvas");
                canvas.id = `chart-${sig.signal_name}`;
                canvas.style.maxHeight = "200px";
                box.appendChild(canvas);
                container.appendChild(box);

                // Sample data points if large sequence to maintain high frame rate
                let chartObs = obs;
                if (obs.length > 500) {
                    const step = Math.ceil(obs.length / 500);
                    chartObs = obs.filter((_, i) => i % step === 0);
                }

                const ctx = canvas.getContext("2d");
                chartInstances[sig.signal_name] = new Chart(ctx, {
                    type: "line",
                    data: {
                        labels: chartObs.map((o) => formatTime(o.observed_at_seconds)),
                        datasets: [
                            {
                                label: formatSignalName(sig.signal_name),
                                data: chartObs.map((o) => o.value),
                                borderColor: colors.line,
                                backgroundColor: colors.bg,
                                borderWidth: 1.5,
                                pointRadius: 0,
                                pointHoverRadius: 4,
                                fill: true,
                                tension: 0.15,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: "index",
                            intersect: false,
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: "rgba(15,23,42,0.92)",
                                titleFont: { size: 11, weight: "bold" },
                                bodyFont: { size: 12 },
                                padding: 8,
                                cornerRadius: 6,
                                callbacks: {
                                    title: (items) => `Elapsed: ${items[0].label}`,
                                    label: (item) => `${formatSignalName(sig.signal_name)}: ${item.raw} ${sig.unit}`,
                                },
                            },
                        },
                        scales: {
                            x: {
                                display: true,
                                title: {
                                    display: false,
                                },
                                ticks: {
                                    maxTicksLimit: 6,
                                    font: { size: 10 },
                                    color: "#94a3b8",
                                },
                                grid: { display: false },
                            },
                            y: {
                                display: true,
                                title: {
                                    display: false,
                                },
                                ticks: {
                                    font: { size: 10 },
                                    color: "#94a3b8",
                                },
                                grid: {
                                    color: "rgba(226,232,240,0.6)",
                                },
                            },
                        },
                    },
                });
            } catch (err) {
                console.error(`Failed to load chart for ${sig.signal_name}:`, err);
            }
        }

        if (container.children.length === 0) {
            container.innerHTML =
                '<div class="chart-placeholder"><p>No vital sign data available for this case.</p></div>';
        }
    }

    function clearCharts() {
        Object.values(chartInstances).forEach((c) => c.destroy());
        chartInstances = {};
        const container = document.getElementById("charts-container");
        if (container) {
            container.innerHTML =
                '<div class="chart-placeholder"><p>Select a case to view charts.</p></div>';
        }
    }

    // ── Observations Table ────────────────────────────────────
    function setupSignalFilter() {
        if (signalFilter) {
            signalFilter.addEventListener("change", () => {
                obsOffset = 0;
                loadObservations();
            });
        }
    }

    async function loadObservations() {
        if (!selectedCaseId) return;

        const tbody = document.getElementById("observations-tbody");
        if (!tbody) return;

        tbody.innerHTML =
            '<tr><td colspan="4" class="loading-spinner"><span class="spinner"></span> Loading observations…</td></tr>';

        try {
            let url = `/api/cases/${selectedCaseId}/observations?limit=${OBS_LIMIT}&offset=${obsOffset}`;
            const sig = signalFilter ? signalFilter.value : "";
            if (sig) url += `&signal=${sig}`;

            const data = await apiGet(url);
            const obs = data.observations || [];

            // Update indicator
            const indElem = document.getElementById("obs-count-indicator");
            if (indElem) {
                const start = Math.min(obsOffset + 1, data.total);
                const end = Math.min(obsOffset + obs.length, data.total);
                indElem.textContent = `Showing ${start.toLocaleString()} – ${end.toLocaleString()} of ${data.total.toLocaleString()} records`;
            }

            if (obs.length === 0) {
                tbody.innerHTML =
                    '<tr><td colspan="4" class="text-muted text-center" style="padding:24px;">No observations recorded.</td></tr>';
                renderPagination(0, 0, OBS_LIMIT);
                return;
            }

            tbody.innerHTML = "";
            obs.forEach((o) => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="font-family:monospace;font-size:12px;font-weight:600;color:var(--text-secondary);">${formatTime(o.observed_at_seconds)}</td>
                    <td><span class="badge ${getSignalBadgeClass(o.signal_name)}">${formatSignalName(o.signal_name)}</span></td>
                    <td style="font-weight:600;font-family:monospace;">${typeof o.value === "number" ? o.value.toFixed(2) : o.value}</td>
                    <td style="color:var(--text-secondary);font-size:12px;">${escapeHtml(o.unit)}</td>
                `;
                tbody.appendChild(tr);
            });

            renderPagination(data.total, data.offset, data.limit);
        } catch (err) {
            tbody.innerHTML =
                '<tr><td colspan="4" class="text-muted text-center" style="padding:24px;">Error loading observations.</td></tr>';
        }
    }

    function getSignalBadgeClass(signal) {
        if (signal === "heart_rate") return "badge-critical";
        if (signal === "spo2") return "badge-normal";
        if (signal === "temperature") return "badge-warning";
        return "badge-normal";
    }

    function renderPagination(total, offset, limit) {
        const pag = document.getElementById("obs-pagination");
        if (!pag) return;
        pag.innerHTML = "";

        const totalPages = Math.ceil(total / limit);
        const currentPage = Math.floor(offset / limit) + 1;

        if (totalPages <= 1) return;

        // Prev button
        const prevBtn = document.createElement("button");
        prevBtn.className = "btn btn-secondary btn-sm";
        prevBtn.textContent = "◀ Previous 100";
        prevBtn.disabled = currentPage === 1;
        prevBtn.addEventListener("click", () => {
            obsOffset = Math.max(0, obsOffset - OBS_LIMIT);
            loadObservations();
        });
        pag.appendChild(prevBtn);

        // Page info
        const info = document.createElement("span");
        info.className = "pagination-info";
        info.textContent = `Page ${currentPage} of ${totalPages}`;
        pag.appendChild(info);

        // Next button
        const nextBtn = document.createElement("button");
        nextBtn.className = "btn btn-secondary btn-sm";
        nextBtn.textContent = "Next 100 ▶";
        nextBtn.disabled = currentPage >= totalPages;
        nextBtn.addEventListener("click", () => {
            obsOffset += OBS_LIMIT;
            loadObservations();
        });
        pag.appendChild(nextBtn);
    }

    // ── Analysis ──────────────────────────────────────────────
    function setupAnalyzeButtons() {
        if (btnAnalyzeDash) btnAnalyzeDash.addEventListener("click", () => runAnalysis());
        if (btnAnalyzeMain) btnAnalyzeMain.addEventListener("click", () => runAnalysis());
    }

    function resetAnalysisUI(sourceId) {
        // Reset Dashboard Stat Cards
        const latestStatusElem = document.getElementById("stat-latest-status");
        const flaggedElem = document.getElementById("stat-flagged");
        if (latestStatusElem) {
            latestStatusElem.textContent = "—";
            latestStatusElem.style.color = "var(--text-muted)";
            latestStatusElem.style.fontSize = "24px";
        }
        if (flaggedElem) {
            flaggedElem.textContent = "—";
        }

        // Idle state on Dashboard
        const dashSummary = document.getElementById("dashboard-analysis-summary");
        if (dashSummary) {
            dashSummary.innerHTML = `
                <div class="analysis-idle-box">
                    <div>
                        <span>⚡ Ready to analyze <strong>Case ${sourceId}</strong>. Click the button to run the rule-based pattern recognition engine across all vital-sign tracks.</span>
                    </div>
                    <button class="btn btn-primary btn-sm" id="btn-analyze-idle-dash">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        Analyze Sequence
                    </button>
                </div>
            `;
            const btnIdleDash = document.getElementById("btn-analyze-idle-dash");
            if (btnIdleDash) btnIdleDash.addEventListener("click", () => runAnalysis());
        }

        // Idle state on Analysis page
        const analysisResults = document.getElementById("analysis-results");
        if (analysisResults) {
            analysisResults.innerHTML = `
                <div class="analysis-idle-card">
                    <div class="idle-icon">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                    </div>
                    <h3>No Analysis Run Yet for Case ${sourceId}</h3>
                    <p>Click below to evaluate this patient's time-ordered observations against demonstration thresholds and detect sustained multi-step trends.</p>
                    <button class="btn btn-primary" id="btn-analyze-idle-main">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        Run Sequential Analysis Now
                    </button>
                </div>
            `;
            const btnIdleMain = document.getElementById("btn-analyze-idle-main");
            if (btnIdleMain) btnIdleMain.addEventListener("click", () => runAnalysis());
        }
    }

    async function runAnalysis() {
        if (!selectedCaseId) return;

        const caseObj = casesData.find((c) => c.id === selectedCaseId);
        const sourceId = caseObj ? caseObj.source_case_id : selectedCaseId;

        const dashSummary = document.getElementById("dashboard-analysis-summary");
        const analysisResults = document.getElementById("analysis-results");

        // 1. Show Loading Screen in both views
        if (dashSummary) {
            dashSummary.innerHTML = `
                <div class="analysis-loading-box">
                    <div class="spinner-large"></div>
                    <h4>Analyzing Case ${sourceId} Sequence…</h4>
                    <p>Evaluating thresholds & identifying sequential patterns…</p>
                    <div class="loading-progress-bar"><div class="loading-progress-fill"></div></div>
                </div>
            `;
        }

        if (analysisResults) {
            analysisResults.innerHTML = `
                <div class="analysis-loading-card">
                    <div class="spinner-large"></div>
                    <h3>Running Sequential Pattern Analysis…</h3>
                    <p>Ingesting real time-series observations for Case ${sourceId} from VitalDB · Checking demonstration thresholds · Detecting multi-step directional trends…</p>
                    <div class="loading-progress-bar"><div class="loading-progress-fill"></div></div>
                </div>
            `;
        }

        // Update button states
        if (btnAnalyzeDash) {
            btnAnalyzeDash.disabled = true;
            btnAnalyzeDash.innerHTML = `<span class="spinner"></span> Analyzing…`;
        }
        if (btnAnalyzeMain) {
            btnAnalyzeMain.disabled = true;
            btnAnalyzeMain.innerHTML = `<span class="spinner"></span> Analyzing Case ${sourceId}…`;
        }

        try {
            // Run API request with a deliberate minimum delay (600ms) for realistic UX
            const [result] = await Promise.all([
                apiPost(`/api/cases/${selectedCaseId}/analyze`),
                new Promise((resolve) => setTimeout(resolve, 600))
            ]);

            latestAnalysisResult = result;

            // 2. Update Dashboard Stat Cards
            const latestStatusElem = document.getElementById("stat-latest-status");
            const flaggedElem = document.getElementById("stat-flagged");

            if (latestStatusElem) {
                latestStatusElem.textContent = result.overall_status || "—";
                latestStatusElem.style.fontSize = "15px";
                if (result.overall_status?.includes("Critical")) {
                    latestStatusElem.style.color = "var(--red)";
                } else if (result.overall_status?.includes("Warning")) {
                    latestStatusElem.style.color = "var(--yellow)";
                } else {
                    latestStatusElem.style.color = "var(--green)";
                }
            }

            if (flaggedElem) {
                flaggedElem.textContent = (result.flagged_total != null ? result.flagged_total : 0).toLocaleString();
            }

            // 3. Render Dashboard summary & Full Analysis view
            if (dashSummary) {
                dashSummary.innerHTML = renderAnalysisBrief(result);
            }

            if (analysisResults) {
                analysisResults.innerHTML = renderAnalysisResults(result);
            }
        } catch (err) {
            console.error("Analysis failed:", err);
            const errHtml = '<p class="text-muted" style="padding:20px;text-align:center;">Error running analysis. Please try again.</p>';
            if (dashSummary) dashSummary.innerHTML = errHtml;
            if (analysisResults) analysisResults.innerHTML = errHtml;
        } finally {
            if (btnAnalyzeDash) {
                btnAnalyzeDash.disabled = false;
                btnAnalyzeDash.innerHTML = `
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Analyze Sequence
                `;
            }
            if (btnAnalyzeMain) {
                btnAnalyzeMain.disabled = false;
                btnAnalyzeMain.innerHTML = `
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Re-Analyze Case
                `;
            }
        }
    }

    function renderAnalysisBrief(result) {
        const sc = result.status_counts || {};
        let statusBadge = "status-badge-normal";
        let statusIcon = "✓";
        if (result.overall_status?.includes("Critical")) {
            statusBadge = "status-badge-critical";
            statusIcon = "⚠";
        } else if (result.overall_status?.includes("Warning")) {
            statusBadge = "status-badge-warning";
            statusIcon = "!";
        }

        return `
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
                <div class="analysis-status-pill ${statusBadge}">
                    <span>${statusIcon}</span>
                    <span>${escapeHtml(result.overall_status)}</span>
                </div>
                <div style="font-size:12px;color:var(--text-secondary);">
                    Demonstration algorithm v${escapeHtml(result.algorithm_version)}
                </div>
            </div>
            <div class="analysis-summary-grid">
                <div class="analysis-stat">
                    <div class="label">Total Points</div>
                    <div class="value">${(result.total_analyzed || 0).toLocaleString()}</div>
                </div>
                <div class="analysis-stat">
                    <div class="label">Normal</div>
                    <div class="value value-normal">${(sc.Normal || 0).toLocaleString()}</div>
                </div>
                <div class="analysis-stat">
                    <div class="label">Warning</div>
                    <div class="value value-warning">${(sc.Warning || 0).toLocaleString()}</div>
                </div>
                <div class="analysis-stat">
                    <div class="label">Critical</div>
                    <div class="value value-critical">${(sc.Critical || 0).toLocaleString()}</div>
                </div>
            </div>
            <p class="analysis-brief-footer">
                Identified <strong>${(result.trends || []).length} sequential trends</strong> and <strong>${(result.flagged_total || 0).toLocaleString()} threshold-crossing events</strong>.
            </p>
        `;
    }

    function renderAnalysisResults(result) {
        const sc = result.status_counts || {};
        let statusBadge = "status-badge-normal";
        let statusIcon = "✓";
        if (result.overall_status?.includes("Critical")) {
            statusBadge = "status-badge-critical";
            statusIcon = "⚠";
        } else if (result.overall_status?.includes("Warning")) {
            statusBadge = "status-badge-warning";
            statusIcon = "!";
        }

        let html = `
            <div class="analysis-hero-card">
                <div class="analysis-hero-top">
                    <div class="analysis-status-pill ${statusBadge}">
                        <span>${statusIcon}</span>
                        <span>${escapeHtml(result.overall_status)}</span>
                    </div>
                    <div class="analysis-meta-tags">
                        <span class="meta-tag">Algorithm v${escapeHtml(result.algorithm_version)}</span>
                        <span class="meta-tag">${(result.signals_analyzed || []).map(formatSignalName).join(" · ") || "All signals"}</span>
                    </div>
                </div>

                <div class="analysis-summary-grid">
                    <div class="analysis-stat">
                        <div class="label">Total Analyzed</div>
                        <div class="value">${(result.total_analyzed || 0).toLocaleString()}</div>
                    </div>
                    <div class="analysis-stat">
                        <div class="label">Normal</div>
                        <div class="value value-normal">${(sc.Normal || 0).toLocaleString()}</div>
                    </div>
                    <div class="analysis-stat">
                        <div class="label">Warning</div>
                        <div class="value value-warning">${(sc.Warning || 0).toLocaleString()}</div>
                    </div>
                    <div class="analysis-stat">
                        <div class="label">Critical</div>
                        <div class="value value-critical">${(sc.Critical || 0).toLocaleString()}</div>
                    </div>
                </div>
            </div>
        `;

        // Sequential Trends
        if (result.trends && result.trends.length > 0) {
            const trendsToShow = result.trends.slice(0, 16);
            html += `
                <div class="analysis-block">
                    <div class="analysis-block-header">
                        <h3>Sequential Trends Detected</h3>
                        <span class="badge-subtle">${result.trends.length} total patterns</span>
                    </div>
                    <div class="trends-list">
            `;
            trendsToShow.forEach((t) => {
                const isInc = t.direction === "increasing";
                const dirIcon = isInc ? "↗" : "↘";
                const dirClass = isInc ? "dir-up" : "dir-down";
                html += `
                    <div class="trend-card">
                        <div class="trend-card-left">
                            <span class="badge badge-signal">${formatSignalName(t.signal)}</span>
                            <span class="trend-dir ${dirClass}">${dirIcon} ${t.direction}</span>
                        </div>
                        <div class="trend-duration">
                            ${t.count} readings (${Math.round(t.start_time)}s – ${Math.round(t.end_time)}s)
                        </div>
                        <div class="trend-values">
                            ${t.start_value.toFixed(1)} → <strong>${t.end_value.toFixed(1)}</strong>
                        </div>
                    </div>
                `;
            });
            html += `
                    </div>
                </div>
            `;
        }

        // Flagged Observations
        if (result.flagged_observations && result.flagged_observations.length > 0) {
            const flagged = result.flagged_observations.slice(0, 25);
            html += `
                <div class="analysis-block">
                    <div class="analysis-block-header">
                        <h3>Flagged Threshold Events</h3>
                        <span class="badge-subtle">Showing first ${flagged.length} of ${(result.flagged_total || 0).toLocaleString()} events</span>
                    </div>
                    <div class="flagged-list">
            `;
            flagged.forEach((f) => {
                const isCrit = f.status === "Critical";
                const badgeCls = isCrit ? "badge-critical" : "badge-warning";
                // Strip redundant suffix
                let cleanReason = f.reason.replace(/\[Rule-based demonstration\]/g, "").trim();
                html += `
                    <div class="flagged-row ${isCrit ? "row-critical" : "row-warning"}">
                        <span class="badge ${badgeCls}">${f.status}</span>
                        <span class="flagged-time">${formatTime(f.time)}</span>
                        <span class="flagged-signal">${formatSignalName(f.signal)}</span>
                        <span class="flagged-val">${typeof f.value === 'number' ? f.value.toFixed(1) : f.value} ${f.unit}</span>
                        <span class="flagged-reason">${escapeHtml(cleanReason)}</span>
                    </div>
                `;
            });
            html += `
                    </div>
                </div>
            `;
        }

        // Single clean footer disclaimer
        html += `
            <div class="disclaimer-footer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span>Educational Demonstration Only: Thresholds are application-defined demonstration rules from surgical VitalDB records and do not represent a clinical medical diagnosis.</span>
            </div>
        `;

        return html;
    }

    // ── Utilities ─────────────────────────────────────────────
    function formatSignalName(name) {
        const map = {
            heart_rate: "Heart Rate",
            spo2: "SpO₂",
            systolic_bp: "Systolic BP",
            diastolic_bp: "Diastolic BP",
            temperature: "Body Temperature",
        };
        return map[name] || name;
    }

    function formatTime(seconds) {
        if (seconds == null) return "—";
        const totalSecs = Math.round(seconds);
        const mins = Math.floor(totalSecs / 60);
        const secs = totalSecs % 60;
        if (mins >= 60) {
            const hrs = Math.floor(mins / 60);
            const remainMins = mins % 60;
            return `${hrs}h ${remainMins.toString().padStart(2, "0")}m ${secs.toString().padStart(2, "0")}s`;
        }
        return `${mins}m ${secs.toString().padStart(2, "0")}s`;
    }

    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ── Start ─────────────────────────────────────────────────
    document.addEventListener("DOMContentLoaded", init);
})();
