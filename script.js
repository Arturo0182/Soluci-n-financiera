/**
 * Antigravity — Gestor de Cartera
 * Dynamia Soluciones Financieras
 * script.js — v2.0
 *
 * Architecture:
 *  - State:    clients[] fetched from REST API (localhost:8000)
 *  - Render:   renderTable() → DOM injection via classList only (no inline style)
 *  - Finance:  calculateFinancials() — daily-exact interest (simple & compound)
 *  - Export:   CSV with BOM + semicolons for native Excel compatibility
 *  - Accordion: per-row toggle shows cedula, phone, notes, payment history (desc)
 */

document.addEventListener('DOMContentLoaded', () => {

    /* ── DOM References ──────────────────────────────────── */
    const tableBody     = document.getElementById('table-body');
    const searchInput   = document.getElementById('search-input');
    const emptyState    = document.getElementById('empty-state');
    const mainTable     = document.getElementById('main-table');
    const btnNewClient  = document.getElementById('btn-new-client');
    const btnExport     = document.getElementById('btn-export');
    const btnBackupExp  = document.getElementById('btn-backup-export');
    const btnBackupImp  = document.getElementById('btn-backup-import');
    const importFile    = document.getElementById('import-file');
    const clientForm    = document.getElementById('client-form');
    const paymentForm   = document.getElementById('payment-form');

    // KPI summary elements
    const summaryClients   = document.getElementById('summary-clients');
    const summaryDebt      = document.getElementById('summary-debt');
    const summaryInterests = document.getElementById('summary-interests');

    /* ── API Configuration ───────────────────────────────── */
    // Backend en :8000. Si FastAPI sirve el frontend, usar el mismo origen.
    const API_URL = (window.location.port === '8000')
        ? `${window.location.origin}/api`
        : `${window.location.protocol}//${window.location.hostname}:8000/api`;

    /* ── Application State ───────────────────────────────── */
    let clients = [];
    // Track which rows are expanded: Set of client IDs
    const expandedRows = new Set();

    /* ─────────────────────────────────────────────────────── *
     *  UTILITIES
     * ─────────────────────────────────────────────────────── */

    /**
     * Format a number as COP currency string.
     * Uses period as thousands separator, comma for decimals (CO locale).
     */
    function formatMoney(amount) {
        const num = parseFloat(amount) || 0;
        const hasDecimals = num % 1 !== 0;
        let parts = num.toFixed(hasDecimals ? 2 : 0).split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return '$' + parts.join(',');
    }

    /**
     * Format a date string (YYYY-MM-DD or ISO) → DD/MM/YYYY.
     */
    function formatDate(dateString) {
        if (!dateString) return '—';
        const d = new Date(dateString);
        if (isNaN(d.getTime())) return dateString;
        const day   = String(d.getUTCDate()).padStart(2, '0');
        const month = String(d.getUTCMonth() + 1).padStart(2, '0');
        const year  = d.getUTCFullYear();
        return `${day}/${month}/${year}`;
    }

    /**
     * Format a full ISO timestamp → DD/MM/YYYY (local time).
     */
    function formatTimestamp(isoString) {
        if (!isoString) return '—';
        const d = new Date(isoString);
        if (isNaN(d.getTime())) return isoString;
        const day   = String(d.getDate()).padStart(2, '0');
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const year  = d.getFullYear();
        return `${day}/${month}/${year}`;
    }

    /**
     * Escape a string for safe CSV output.
     */
    function csvEscape(val) {
        const str = String(val ?? '').replace(/"/g, '""');
        return `"${str}"`;
    }

    /**
     * Parse FastAPI error response body into a human-readable message.
     */
    function parseApiError(body) {
        if (!body || body.detail == null) return 'Error al procesar la solicitud.';
        if (typeof body.detail === 'string') return body.detail;
        if (Array.isArray(body.detail)) {
            return body.detail.map(e => e.msg || String(e)).join(', ');
        }
        return String(body.detail);
    }

    /* ─────────────────────────────────────────────────────── *
     *  FINANCIAL ENGINE
     * ─────────────────────────────────────────────────────── */

    /**
     * Calculate financials for a single client using exact daily interest.
     *
     * Daily rate derivation:
     *   Simple   → rDaily = (monthlyRate / 100) / 30
     *   Compound → rDaily = (1 + monthlyRate/100)^(1/30) - 1
     *
     * Accumulated interest:
     *   Simple   → interest = P * rDaily * daysPassed
     *   Compound → interest = P * ((1 + rDaily)^daysPassed - 1)
     *
     * @param {Object} client
     * @returns {{ accumulatedInterest, totalPayments, totalToPay, status }}
     */
    function calculateFinancials(client) {
        const startDate = new Date(client.startDate);
        startDate.setHours(0, 0, 0, 0);
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const msPerDay   = 1000 * 60 * 60 * 24;
        const daysPassed = Math.max(0, Math.floor((today - startDate) / msPerDay));

        const P         = parseFloat(client.initialDebt) || 0;
        const monthly   = parseFloat(client.interestRate) || 0;
        let interest    = 0;

        if (client.interestType === 'simple') {
            const rDaily = (monthly / 100) / 30;
            interest     = P * rDaily * daysPassed;
        } else { // compuesto
            const rDaily = Math.pow(1 + monthly / 100, 1 / 30) - 1;
            interest     = P * (Math.pow(1 + rDaily, daysPassed) - 1);
        }

        const totalPayments = (client.payments || []).reduce(
            (sum, p) => sum + (parseFloat(p.amount) || 0), 0
        );
        const totalToPay = Math.max(0, P + interest - totalPayments);

        let status = 'pendiente';
        if (totalToPay <= 0)    status = 'saldado';
        else if (totalPayments > 0) status = 'parcial';

        return { accumulatedInterest: interest, totalPayments, totalToPay, status };
    }

    /* ─────────────────────────────────────────────────────── *
     *  DATA FETCHING (REST API)
     * ─────────────────────────────────────────────────────── */

    async function fetchClients() {
        try {
            const response = await fetch(`${API_URL}/clientes`);
            if (!response.ok) throw new Error('Error al obtener clientes');
            clients = await response.json();
        } catch (err) {
            console.error('fetchClients:', err);
            clients = [];
            if (err.message === 'Failed to fetch') {
                alert('No se pudo conectar con el servidor.\n\nAsegúrate de ejecutar el backend:\n  .\\.venv\\Scripts\\Activate.ps1\n  python main.py\n\nLuego recarga esta página (Ctrl+Shift+R).');
            }
        }
        renderTable(searchInput.value);
    }

    /* ─────────────────────────────────────────────────────── *
     *  RENDERING
     * ─────────────────────────────────────────────────────── */

    function renderTable(filterText = '') {
        tableBody.innerHTML = '';

        let filtered = clients;
        if (filterText) {
            const q = filterText.toLowerCase();
            filtered = clients.filter(c =>
                c.name.toLowerCase().includes(q) ||
                (c.cedula && c.cedula.includes(q)) ||
                (c.phone  && c.phone.toLowerCase().includes(q))
            );
        }

        if (filtered.length === 0) {
            emptyState.classList.remove('hidden');
            mainTable.classList.add('hidden');
        } else {
            emptyState.classList.add('hidden');
            mainTable.classList.remove('hidden');
        }

        let totalDebt     = 0;
        let totalInterest = 0;

        filtered.forEach(client => {
            const fin = calculateFinancials(client);
            totalDebt     += fin.totalToPay;
            totalInterest += fin.accumulatedInterest;

            /* -- Status badge HTML -- */
            const badgeClass = `status-${fin.status}`;
            const badgeLabel = fin.status === 'pendiente' ? 'Pendiente'
                             : fin.status === 'parcial'   ? 'Parcial'
                             :                              'Saldado';
            const statusHtml = `<span class="status-badge ${badgeClass}">
                <div class="status-indicator"></div>${badgeLabel}
            </span>`;

            /* -- Is this row expanded? -- */
            const isOpen = expandedRows.has(client.id);

            /* -- Data row -- */
            const tr = document.createElement('tr');
            tr.className = 'data-row';
            tr.dataset.id = client.id;

            tr.innerHTML = `
                <td>
                    <button class="btn-icon action-toggle${isOpen ? ' is-open' : ''}"
                            data-id="${client.id}" title="Mostrar / Ocultar detalles"
                            aria-expanded="${isOpen}">
                        <i class="fa-solid fa-chevron-down"></i>
                    </button>
                </td>
                <td class="fw-600">${escapeHtml(client.name)}</td>
                <td>${formatDate(client.startDate)}</td>
                <td class="td-money">${formatMoney(client.initialDebt)}</td>
                <td class="td-rate">
                    ${client.interestRate}%
                    <span class="td-type">(${client.interestType === 'simple' ? 'S' : 'C'})</span>
                </td>
                <td class="td-money interest">+${formatMoney(fin.accumulatedInterest)}</td>
                <td class="td-money payments">−${formatMoney(fin.totalPayments)}</td>
                <td class="td-money total-due">${formatMoney(fin.totalToPay)}</td>
                <td>${statusHtml}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-icon action-pay"    data-id="${client.id}" title="Registrar Abono">
                            <i class="fa-solid fa-hand-holding-dollar"></i>
                        </button>
                        <button class="btn-icon action-edit"   data-id="${client.id}" title="Editar Cliente">
                            <i class="fa-solid fa-pen"></i>
                        </button>
                        <button class="btn-icon action-delete" data-id="${client.id}" title="Eliminar Cliente">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </td>`;

            tableBody.appendChild(tr);

            /* -- Details accordion row -- */
            const detailsTr = document.createElement('tr');
            detailsTr.className = 'details-row';
            detailsTr.dataset.detailsFor = client.id;
            if (!isOpen) detailsTr.classList.add('hidden');

            // Payment history: sort newest first
            const sortedPayments = [...(client.payments || [])].sort(
                (a, b) => new Date(b.date) - new Date(a.date)
            );

            const payHistoryHtml = sortedPayments.length > 0
                ? sortedPayments.map(p => `
                    <div class="payment-item">
                        <span class="pay-date">${formatTimestamp(p.date)}</span>
                        <span class="pay-amount">${formatMoney(p.amount)}</span>
                    </div>`).join('')
                : '<p class="no-payments">Sin abonos registrados.</p>';

            detailsTr.innerHTML = `
                <td colspan="10">
                    <div class="details-inner">
                        <!-- Left: hidden fields -->
                        <div>
                            <p class="details-section-title">Información del Cliente</p>
                            <div class="details-client-info">
                                <div class="details-info-item">
                                    <span class="label">Cédula</span>
                                    <span class="value">${escapeHtml(client.cedula || '—')}</span>
                                </div>
                                <div class="details-info-item">
                                    <span class="label">Contacto</span>
                                    <span class="value">${escapeHtml(client.phone || '—')}</span>
                                </div>
                                <div class="details-info-item">
                                    <span class="label">Notas</span>
                                    <span class="value">${escapeHtml(client.notes || '—')}</span>
                                </div>
                            </div>
                        </div>
                        <!-- Right: payment history -->
                        <div class="details-payments">
                            <p class="details-section-title">Historial de Abonos</p>
                            <div class="payment-history-list">
                                ${payHistoryHtml}
                            </div>
                        </div>
                    </div>
                </td>`;

            tableBody.appendChild(detailsTr);
        });

        // Update KPI cards
        summaryClients.textContent   = clients.length;
        summaryDebt.textContent      = formatMoney(totalDebt);
        summaryInterests.textContent = formatMoney(totalInterest);
    }

    /**
     * Minimal HTML escape to prevent XSS from client data.
     */
    function escapeHtml(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /* ─────────────────────────────────────────────────────── *
     *  TABLE EVENT DELEGATION
     * ─────────────────────────────────────────────────────── */

    tableBody.addEventListener('click', e => {
        const toggleBtn = e.target.closest('.action-toggle');
        const payBtn    = e.target.closest('.action-pay');
        const editBtn   = e.target.closest('.action-edit');
        const deleteBtn = e.target.closest('.action-delete');

        if (toggleBtn) {
            const id      = toggleBtn.dataset.id;
            const details = tableBody.querySelector(`[data-details-for="${id}"]`);
            if (!details) return;

            if (expandedRows.has(id)) {
                expandedRows.delete(id);
                toggleBtn.classList.remove('is-open');
                toggleBtn.setAttribute('aria-expanded', 'false');
                details.classList.add('hidden');
            } else {
                expandedRows.add(id);
                toggleBtn.classList.add('is-open');
                toggleBtn.setAttribute('aria-expanded', 'true');
                details.classList.remove('hidden');
            }
        }
        if (payBtn)    openPaymentModal(payBtn.dataset.id);
        if (editBtn)   openEditModal(editBtn.dataset.id);
        if (deleteBtn) deleteClient(deleteBtn.dataset.id);
    });

    /* ─────────────────────────────────────────────────────── *
     *  MODALS
     * ─────────────────────────────────────────────────────── */

    window.openModal  = id => document.getElementById(id).classList.remove('hidden');
    window.closeModal = id => {
        document.getElementById(id).classList.add('hidden');
        if (id === 'client-modal')  clientForm.reset();
        if (id === 'payment-modal') paymentForm.reset();
    };

    // Close modals on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', e => {
            if (e.target === modal) closeModal(modal.id);
        });
    });

    // "Nuevo Cliente" button
    btnNewClient.addEventListener('click', () => {
        document.getElementById('form-id').value = '';
        document.getElementById('modal-title').textContent = 'Agregar Nuevo Cliente';
        document.getElementById('form-date').value = new Date().toISOString().split('T')[0];
        openModal('client-modal');
    });

    /* ─────────────────────────────────────────────────────── *
     *  CLIENT CRUD
     * ─────────────────────────────────────────────────────── */

    clientForm.addEventListener('submit', async e => {
        e.preventDefault();
        const id = document.getElementById('form-id').value;
        const payload = {
            cedula:       document.getElementById('form-cedula').value.trim(),
            name:         document.getElementById('form-name').value.trim(),
            phone:        document.getElementById('form-phone').value.trim(),
            initialDebt:  parseFloat(document.getElementById('form-amount').value),
            startDate:    document.getElementById('form-date').value,
            interestRate: parseFloat(document.getElementById('form-rate').value),
            interestType: document.getElementById('form-type').value,
            notes:        document.getElementById('form-notes').value.trim(),
        };

        try {
            const url    = id ? `${API_URL}/clientes/${id}` : `${API_URL}/clientes`;
            const method = id ? 'PUT' : 'POST';
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(parseApiError(err));
            }
            await fetchClients();
            closeModal('client-modal');
        } catch (err) {
            alert(err.message);
        }
    });

    window.openEditModal = id => {
        const c = clients.find(c => c.id === id);
        if (!c) return;
        document.getElementById('form-id').value          = c.id;
        document.getElementById('form-cedula').value      = c.cedula || '';
        document.getElementById('form-name').value        = c.name;
        document.getElementById('form-phone').value       = c.phone || '';
        document.getElementById('form-amount').value      = c.initialDebt;
        document.getElementById('form-date').value        = c.startDate;
        document.getElementById('form-rate').value        = c.interestRate;
        document.getElementById('form-type').value        = c.interestType;
        document.getElementById('form-notes').value       = c.notes || '';
        document.getElementById('modal-title').textContent = 'Editar Datos de Cliente';
        openModal('client-modal');
    };

    window.deleteClient = async id => {
        if (!confirm('¿Eliminar permanentemente este cliente, su deuda e historial de abonos?')) return;
        try {
            const res = await fetch(`${API_URL}/clientes/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Error al eliminar');
            expandedRows.delete(id);
            await fetchClients();
        } catch (err) {
            alert(err.message);
        }
    };

    /* ─────────────────────────────────────────────────────── *
     *  PAYMENTS
     * ─────────────────────────────────────────────────────── */

    window.openPaymentModal = id => {
        const c = clients.find(c => c.id === id);
        if (!c) return;
        const fin = calculateFinancials(c);
        if (fin.status === 'saldado') {
            alert('Este cliente ya tiene su deuda saldada.');
            return;
        }
        document.getElementById('payment-client-id').value     = id;
        document.getElementById('payment-client-name').textContent = c.name;
        document.getElementById('payment-current-debt').textContent = formatMoney(fin.totalToPay);
        const amtInput = document.getElementById('payment-amount');
        amtInput.max   = fin.totalToPay;
        amtInput.value = '';
        openModal('payment-modal');
    };

    paymentForm.addEventListener('submit', async e => {
        e.preventDefault();
        const id     = document.getElementById('payment-client-id').value;
        const amount = parseFloat(document.getElementById('payment-amount').value);
        if (!amount || amount <= 0) return;

        try {
            const res = await fetch(`${API_URL}/clientes/${id}/payments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    amount,
                    date: new Date().toISOString(), // ISO timestamp for sorting
                }),
            });
            if (!res.ok) throw new Error('Error al registrar abono');
            await fetchClients();
            closeModal('payment-modal');
        } catch (err) {
            alert(err.message);
        }
    });

    /* ─────────────────────────────────────────────────────── *
     *  SEARCH
     * ─────────────────────────────────────────────────────── */

    searchInput.addEventListener('input', e => renderTable(e.target.value));

    /* ─────────────────────────────────────────────────────── *
     *  EXPORT — CSV with BOM + semicolons for native Excel
     * ─────────────────────────────────────────────────────── */

    btnExport.addEventListener('click', () => {
        if (clients.length === 0) { alert('No hay datos para exportar.'); return; }

        const SEP = ';';
        const headers = [
            'Estado', 'Nombre', 'Cédula', 'Contacto',
            'Fecha Inicio', 'Monto Inicial (COP)', 'Tasa (%)', 'Tipo Interés',
            'Días Transcurridos', 'Interés Acum. (COP)', 'Abonos (COP)', 'Total a Pagar (COP)',
            'Notas',
        ];

        const rows = clients.map(c => {
            const fin = calculateFinancials(c);
            const startDate = new Date(c.startDate);
            startDate.setHours(0, 0, 0, 0);
            const today = new Date(); today.setHours(0, 0, 0, 0);
            const days  = Math.max(0, Math.floor((today - startDate) / 86400000));

            return [
                csvEscape(fin.status.toUpperCase()),
                csvEscape(c.name),
                csvEscape(c.cedula || ''),
                csvEscape(c.phone || ''),
                csvEscape(formatDate(c.startDate)),
                String(c.initialDebt).replace('.', ','),
                String(c.interestRate).replace('.', ','),
                csvEscape(c.interestType),
                days,
                String(fin.accumulatedInterest.toFixed(2)).replace('.', ','),
                String(fin.totalPayments.toFixed(2)).replace('.', ','),
                String(fin.totalToPay.toFixed(2)).replace('.', ','),
                csvEscape(c.notes || ''),
            ].join(SEP);
        });

        // BOM (\uFEFF) ensures Excel opens as UTF-8 automatically
        const csv     = '\uFEFF' + [headers.join(SEP), ...rows].join('\n');
        const blob    = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url     = URL.createObjectURL(blob);
        const link    = document.createElement('a');
        link.href     = url;
        link.download = `Cartera_${new Date().toISOString().split('T')[0]}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    });

    /* ─────────────────────────────────────────────────────── *
     *  BACKUP — JSON Export / Import
     * ─────────────────────────────────────────────────────── */

    btnBackupExp.addEventListener('click', () => {
        if (clients.length === 0) { alert('No hay datos para respaldar.'); return; }
        const blob  = new Blob([JSON.stringify(clients, null, 2)], { type: 'application/json' });
        const url   = URL.createObjectURL(blob);
        const link  = document.createElement('a');
        link.href   = url;
        link.download = `Backup_Cartera_${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        URL.revokeObjectURL(url);
    });

    btnBackupImp.addEventListener('click', () => importFile.click());

    importFile.addEventListener('change', e => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async event => {
            try {
                const data = JSON.parse(event.target.result);
                if (!Array.isArray(data)) throw new Error('Formato no válido');
                if (!confirm(`Importar ${data.length} cliente(s) al servidor. ¿Proceder?`)) return;

                let imported = 0;
                let skipped  = 0;

                for (const c of data) {
                    const res = await fetch(`${API_URL}/clientes`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            cedula:       c.cedula,
                            name:         c.name,
                            phone:        c.phone,
                            initialDebt:  c.initialDebt,
                            startDate:    c.startDate,
                            interestRate: c.interestRate,
                            interestType: c.interestType,
                            notes:        c.notes,
                        }),
                    });

                    if (!res.ok) {
                        skipped++;
                        continue;
                    }

                    const created = await res.json();
                    imported++;

                    for (const p of (c.payments || [])) {
                        await fetch(`${API_URL}/clientes/${created.id}/payments`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                amount: p.amount,
                                date:   p.date || new Date().toISOString(),
                            }),
                        });
                    }
                }
                await fetchClients();
                const msg = skipped > 0
                    ? `Importación completada: ${imported} cliente(s) importado(s), ${skipped} omitido(s) (cédula duplicada).`
                    : `Importación completada: ${imported} cliente(s) importado(s).`;
                alert(msg);
            } catch (err) {
                alert('Error al importar: ' + err.message);
            }
            importFile.value = '';
        };
        reader.readAsText(file);
    });

    /* ─────────────────────────────────────────────────────── *
     *  BOOT
     * ─────────────────────────────────────────────────────── */

    fetchClients();
});
