/**
 * Arunika-POS (BrewPOS) Global JavaScript Helper & Engine
 */

const API_BASE = '/api';
let cachedStoreSettings = null;

// Format Rupiah Helper
function formatRp(amount) {
    if (amount === undefined || amount === null || isNaN(amount)) return 'Rp 0';
    return 'Rp ' + Math.round(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function getToken() {
    return localStorage.getItem('token');
}

// Global API Fetch helper with JWT & Error handling
async function apiFetch(endpoint, options = {}) {
    const token = getToken();

    const headers = {
        'Accept': 'application/json',
        ...(options.headers || {})
    };

    // Identity comes from the JWT payload server-side; no X-User-Id header needed
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    try {
        const url = endpoint.startsWith('/api') ? endpoint : `${API_BASE}${endpoint}`;
        const res = await fetch(url, {
            ...options,
            headers
        });

        // Never bounce from the login page itself, otherwise a 401 here reloads /login forever
        const onLoginPage = window.location.pathname.includes('/login');
        if (res.status === 401 && !endpoint.includes('/auth/login') && !onLoginPage) {
            showToast('Sesi telah berakhir, silakan login kembali.', 'error');
            setTimeout(() => {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }, 1000);
            throw new Error('Unauthorized');
        }

        if (res.status === 204) {
            return null;
        }

        const data = await res.json();
        if (!res.ok) {
            const err = new Error(data.error || data.message || 'Terjadi kesalahan pada server');
            // Body error dibawa serta: 409 duplikat kontak menyertakan member yang bentrok.
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
}

// Store Settings Caching Helper
async function getStoreSettings(forceRefresh = false) {
    if (cachedStoreSettings && !forceRefresh) {
        return cachedStoreSettings;
    }
    try {
        const list = await apiFetch('/settings');
        const map = {
            STORE_NAME: 'Arunika Coffee & Lounge',
            TAGLINE: 'Every Cup Has A Story',
            STORE_ADDRESS: 'Jl. Melati Kopi No. 12, City Center',
            STORE_PHONE: '0812-3456-7890',
            STORE_WEBSITE: 'www.arunikacoffee.com',
            STORE_INSTAGRAM: '@arunika.coffee',
            RECEIPT_FOOTER: 'Terima kasih atas kunjungannya! Wifi: arunika_free | Pass: ngopidulu',
            TAX_PERCENT: '11',
            PARKING_FEE: '2000',
            RECEIPT_PAPER_SIZE: '58mm',
            RECEIPT_PRINT_SCALE: '100'
        };
        list.forEach(s => {
            if (s.key) map[s.key] = s.value;
        });
        if (map.TAX_PERCENT !== undefined && map.TAX_PERCENT !== '') {
            map.TAX_PERCENTAGE = map.TAX_PERCENT;
        } else if (map.TAX_PERCENTAGE !== undefined && map.TAX_PERCENTAGE !== '') {
            map.TAX_PERCENT = map.TAX_PERCENTAGE;
        }
        cachedStoreSettings = map;
        return map;
    } catch (e) {
        return {
            STORE_NAME: 'Arunika Coffee & Lounge',
            TAGLINE: 'Every Cup Has A Story',
            STORE_ADDRESS: 'Jl. Melati Kopi No. 12, City Center',
            STORE_PHONE: '0812-3456-7890',
            STORE_WEBSITE: 'www.arunikacoffee.com',
            STORE_INSTAGRAM: '@arunika.coffee',
            RECEIPT_FOOTER: 'Terima kasih atas kunjungannya!',
            TAX_PERCENT: '11',
            PARKING_FEE: '2000',
            RECEIPT_PAPER_SIZE: '58mm',
            RECEIPT_PRINT_SCALE: '100'
        };
    }
}

// User state helpers
function getUser() {
    try {
        const u = localStorage.getItem('user');
        return u ? JSON.parse(u) : null;
    } catch (e) {
        return null;
    }
}

function setUser(user, token) {
    if (user) localStorage.setItem('user', JSON.stringify(user));
    if (token) localStorage.setItem('token', token);
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
}

// Toast notification
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'exclamation-circle';
    if (type === 'warning') icon = 'triangle-exclamation';

    toast.innerHTML = `<i class="fas fa-${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Modal helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
    }
}

// Global Shift Management
async function updateShiftStatusWidget() {
    const widget = document.getElementById('shift-status-widget');
    if (!widget) return;

    try {
        const data = await apiFetch('/shift/current');
        if (data && data.currentShift) {
            const s = data.currentShift;
            const keeper = s.currentUser ? s.currentUser.username : 'Kasir';
            const stale = s.status === 'NEEDS_REVIEW';
            widget.className = 'shift-status-pill open';
            // Nama penjaga dibungkus .shift-text: di layar sempit bagian itu
            // disembunyikan CSS supaya pill tidak terpotong di tepi layar.
            widget.innerHTML = stale
                ? `<span class="status-dot"></span> ${s.label}<span class="shift-text"> &middot; perlu ditutup</span>`
                : `<span class="status-dot"></span> ${s.label}<span class="shift-text"> &middot; ${keeper}</span>`;
            widget.title = stale
                ? `Sesi ini sudah lebih dari 18 jam terbuka. Modal Awal: ${formatRp(s.startingCash)}`
                : `Modal Awal: ${formatRp(s.startingCash)}`;
        } else {
            widget.className = 'shift-status-pill closed';
            widget.innerHTML = `<span class="status-dot"></span> Tutup<span class="shift-text"> &middot; Sesi Kas</span>`;
            widget.title = `Belum ada sesi kas terbuka`;
        }
    } catch (e) {
        widget.className = 'shift-status-pill closed';
        widget.innerHTML = `<span class="status-dot"></span> Shift Tutup`;
    }
}

async function openShiftModal() {
    openModal('modal-shift');
    const content = document.getElementById('shift-modal-content');
    if (!content) return;

    content.innerHTML = '<p class="text-muted text-center"><i class="fas fa-spinner fa-spin"></i> Memuat status shift...</p>';

    try {
        const data = await apiFetch('/shift/current');
        if (data && data.currentShift) {
            const s = data.currentShift;
            const me = getUser() || {};
            const startTimeStr = new Date(s.startTime).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
            const openedBy = s.openedByUser ? s.openedByUser.username : '-';
            const keeper = s.currentUser ? s.currentUser.username : '-';
            const isMine = s.currentUserId && me.id === s.currentUserId;
            const stale = s.status === 'NEEDS_REVIEW';

            const handoverBtn = isMine ? '' : `
                <button class="btn btn-secondary" style="width: 100%; margin-bottom: 8px;" onclick="submitShiftHandover()">
                    <i class="fas fa-people-arrows"></i> Ganti Penjaga (Saya yang jaga sekarang)
                </button>
            `;
            const staleWarn = stale ? `
                <div style="background: var(--color-danger-bg); border: 1px solid rgba(211, 47, 47, 0.25); padding: 10px 14px; border-radius: var(--radius-sm); margin-bottom: 14px; font-size: 12.5px;">
                    <i class="fas fa-triangle-exclamation text-danger"></i>
                    Sesi ini sudah terbuka lebih dari 18 jam dan ditandai <strong>perlu ditinjau</strong>. Tutup dan cocokkan kasnya.
                </div>
            ` : '';

            content.innerHTML = `
                ${staleWarn}
                <div style="background: var(--color-success-bg); border: 1px solid rgba(46, 125, 50, 0.3); padding: 18px; border-radius: var(--radius-md); margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                        <i class="fas fa-check-circle text-success" style="font-size: 20px;"></i>
                        <h4 style="color: var(--color-success); font-size: 16px; margin: 0;">${s.label} Aktif</h4>
                    </div>
                    <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                        <p><strong>Modal Awal:</strong> ${formatRp(s.startingCash)}</p>
                        <p><strong>Mulai Sejak:</strong> Jam ${startTimeStr} WIB</p>
                        <p><strong>Dibuka oleh:</strong> ${openedBy}</p>
                        <p><strong>Penjaga sekarang:</strong> ${keeper}${isMine ? ' (Anda)' : ''}</p>
                        ${s.handovers && s.handovers.length ? `<p><strong>Pergantian penjaga:</strong> ${s.handovers.length}x</p>` : ''}
                    </div>
                </div>

                ${handoverBtn}

                <div class="form-group">
                    <label class="form-label">Total Uang Tunai di Laci Kasir (Rp)</label>
                    <input type="number" id="shift-ending-cash" class="form-control" placeholder="Contoh: 1250000" required>
                    <small class="text-muted" style="font-size: 11.5px; margin-top: 4px; display: block;">
                        Hitung seluruh uang fisik di laci kasir saat ini untuk rekonsiliasi akhir sesi.
                    </small>
                </div>
                <div class="form-group">
                    <label class="form-label">Catatan Penutupan (Opsional)</label>
                    <input type="text" id="shift-closing-note" class="form-control" placeholder="Contoh: selisih karena kembalian kurang">
                </div>

                <button class="btn btn-danger" style="width: 100%; margin-top: 8px;" onclick="submitCloseShift()">
                    <i class="fas fa-door-closed"></i> Tutup & Rekonsiliasi Sesi Kas
                </button>
            `;
        } else {
            content.innerHTML = `
                <p style="margin-bottom: 18px; font-size: 13px; color: var(--text-secondary);">
                    Belum ada sesi kas yang terbuka. Masukkan modal uang awal di laci kasir untuk mulai transaksi.
                    Sesi ini dipakai bersama semua kasir yang bertugas hari ini.
                </p>
                <div class="form-group">
                    <label class="form-label">Modal Kas Awal di Laci (Rp)</label>
                    <input type="number" id="shift-starting-cash" class="form-control" placeholder="Contoh: 200000" value="200000" required>
                </div>
                <button class="btn btn-primary" style="width: 100%; margin-top: 8px;" onclick="submitOpenShift()">
                    <i class="fas fa-door-open"></i> Buka Sesi Kas Baru
                </button>
            `;
        }
    } catch (err) {
        content.innerHTML = `<p class="text-danger">Gagal memuat data shift: ${err.message}</p>`;
    }
}

async function submitOpenShift() {
    const startingCash = parseInt(document.getElementById('shift-starting-cash').value) || 0;
    try {
        await apiFetch('/shift/open', {
            method: 'POST',
            body: JSON.stringify({ startingCash })
        });
        showToast('Sesi kas berhasil dibuka!', 'success');
        closeModal('modal-shift');
        updateShiftStatusWidget();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function submitShiftHandover() {
    try {
        await apiFetch('/shift/handover', { method: 'POST', body: JSON.stringify({}) });
        showToast('Anda tercatat sebagai penjaga sesi kas sekarang.', 'success');
        openShiftModal();
        updateShiftStatusWidget();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function submitCloseShift() {
    const endingCash = parseInt(document.getElementById('shift-ending-cash').value);
    if (isNaN(endingCash)) {
        showToast('Masukkan jumlah uang kas fisik di laci!', 'warning');
        return;
    }

    try {
        const noteEl = document.getElementById('shift-closing-note');
        const res = await apiFetch('/shift/close', {
            method: 'POST',
            body: JSON.stringify({ endingCash, closingNote: noteEl ? noteEl.value : '' })
        });
        const diff = res.endingCash - res.expectedEndingCash;
        let diffMsg = 'Kas pas!';
        if (diff > 0) diffMsg = `Lebih kas: ${formatRp(diff)}`;
        if (diff < 0) diffMsg = `Kurang kas: ${formatRp(Math.abs(diff))}`;

        showToast(`Sesi kas ditutup. Ekspektasi: ${formatRp(res.expectedEndingCash)} (${diffMsg})`, 'success');
        closeModal('modal-shift');
        updateShiftStatusWidget();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Thermal Receipt Helper with Store Info, Dynamic PPN, and Discounts
function renderThermalReceiptHtml(txData, storeInfo = null) {
    const info = storeInfo || cachedStoreSettings || {
        STORE_NAME: 'ARUNIKA COFFEE',
        TAGLINE: 'Every Cup Has A Story',
        STORE_ADDRESS: 'Jl. Melati Kopi No. 12, City Center',
        STORE_PHONE: '0812-3456-7890',
        STORE_WEBSITE: 'www.arunikacoffee.com',
        STORE_INSTAGRAM: '@arunika.coffee',
        RECEIPT_FOOTER: 'Terima kasih atas kunjungannya! Wifi: arunika_free (Pass: ngopidulu)',
        TAX_PERCENT: '11'
    };

    const user = getUser();
    const cashierName = (user && user.username) ? user.username : 'Kasir';
    
    // Support both raw transaction object or { message, transaction, customer } checkout payload
    const tx = txData.transaction || txData;
    const items = tx.items || txData.items || [];
    const dateStr = new Date(tx.createdAt || txData.createdAt || Date.now()).toLocaleString('id-ID', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });

    const txCode = tx.transactionCode || tx.code || txData.transactionCode || txData.code || ('TR' + new Date().toISOString().slice(0,10).replace(/-/g,'') + '000001');
    const customerObj = tx.customer || txData.customer;
    const custName = customerObj ? customerObj.nickname : (tx.nickname || txData.nickname || 'Guest');
    const custType = customerObj ? (customerObj.customerType || 'REGULAR') : 'REGULAR';
    const typeDisplay = (custType === 'EMPLOYEE' || custType === 'KARYAWAN') ? 'Tipe Karyawan' : 'Tipe Pelanggan';

    let totalItemDiscount = 0;
    const itemsHtml = (items.length > 0) ? items.map(item => {
        const itemName = item.menu ? item.menu.name : (item.name || 'Menu #' + (item.menuId || ''));
        const itemQty = item.quantity || 1;
        const itemPrice = item.price || 0;
        const itemDisc = (item.discountAmount || 0) * itemQty;
        totalItemDiscount += itemDisc;
        const itemGross = itemPrice * itemQty;

        return `
            <div style="margin-bottom: 5px;">
                <div class="receipt-row">
                    <span>${itemQty}x ${itemName}</span>
                    <span>${formatRp(itemGross)}</span>
                </div>
                ${itemDisc > 0 ? `
                <div class="receipt-row" style="font-size: 10.5px; color: #555; padding-left: 10px;">
                    <span>* Potongan / Jatah:</span>
                    <span>-${formatRp(itemDisc)}</span>
                </div>` : ''}
            </div>
        `;
    }).join('') : `
        <div class="receipt-row" style="color: #666; font-style: italic;">
            <span>1x Transaksi Menu</span>
            <span>${formatRp(tx.totalAmount || txData.totalAmount || 0)}</span>
        </div>
    `;

    const totalAmount = (tx.totalAmount !== undefined) ? tx.totalAmount : (txData.totalAmount || 0);
    const orderDiscount = (tx.discountAmount !== undefined) ? tx.discountAmount : (txData.discountAmount || 0);
    const rawTax = (info.TAX_PERCENT !== undefined && info.TAX_PERCENT !== '') 
        ? info.TAX_PERCENT 
        : ((info.TAX_PERCENTAGE !== undefined && info.TAX_PERCENTAGE !== '') ? info.TAX_PERCENTAGE : '11');
    const parsedTax = parseFloat(rawTax);
    const taxPercent = !isNaN(parsedTax) ? parsedTax : 11.0;
    const taxAmount = (tx.taxAmount !== undefined) ? tx.taxAmount : (txData.taxAmount !== undefined ? txData.taxAmount : 0);
    // Menu prices are tax-inclusive, so the honest subtotal is the pre-discount gross.
    // Using the stored DPP made the column fail to add up whenever a discount applied:
    // 45.045 - 10.000 + 4.955 != 50.000.
    const grossBeforeDiscount = totalAmount + orderDiscount + totalItemDiscount;
    const cashTendered = txData.cashReceived || tx.cashReceived || totalAmount;
    const changeAmount = (cashTendered > totalAmount) ? (cashTendered - totalAmount) : 0;
    const pointsEarned = (tx.pointsEarned !== undefined) ? tx.pointsEarned : (txData.pointsEarned || 0);

    return `
        <div class="thermal-receipt-card" id="printable-receipt">
            <div class="receipt-header">
                <div class="receipt-store-title">${info.STORE_NAME || 'ARUNIKA COFFEE'}</div>
                <div style="font-size: 11px; color: #555; font-style: italic; margin-top: 2px;">${info.TAGLINE || 'Every Cup Has A Story'}</div>
                <div class="receipt-meta-info">
                    ${info.STORE_ADDRESS || ''}<br>
                    Telp: ${info.STORE_PHONE || '-'} | IG: ${info.STORE_INSTAGRAM || '-'}
                </div>
            </div>
            
            <div class="receipt-divider double"></div>
            
            <div class="receipt-row">
                <span>Kode Transaksi:</span>
                <span style="font-weight: 800; font-family: monospace; font-size: 12px; color: #000;">${txCode}</span>
            </div>
            <div class="receipt-row">
                <span>Tanggal / Waktu:</span>
                <span>${dateStr} WIB</span>
            </div>
            <div class="receipt-row">
                <span>Kasir:</span>
                <span>${cashierName}</span>
            </div>
            <div class="receipt-row">
                <span>Member:</span>
                <span style="font-weight: 700;">${custName}</span>
            </div>
            <div class="receipt-row">
                <span>Tipe Member:</span>
                <span style="font-weight: 700; color: ${(custType === 'EMPLOYEE') ? '#B78103' : '#2E7D32'};">${typeDisplay}</span>
            </div>
            <div class="receipt-row">
                <span>Metode Bayar:</span>
                <span style="font-weight: 700;">${tx.paymentMethod || txData.paymentMethod || 'CASH'}</span>
            </div>

            <div class="receipt-divider"></div>

            <div style="font-weight: 700; margin-bottom: 6px; font-size: 11px; text-transform: uppercase;">Rincian Pesanan:</div>
            ${itemsHtml}

            <div class="receipt-divider"></div>

            <div class="receipt-row">
                <span>Subtotal Menu</span>
                <span>${formatRp(grossBeforeDiscount)}</span>
            </div>

            ${totalItemDiscount > 0 ? `
            <div class="receipt-row" style="color: #333;">
                <span>Total Diskon Menu / Jatah</span>
                <span>-${formatRp(totalItemDiscount)}</span>
            </div>` : ''}

            ${orderDiscount > 0 ? `
            <div class="receipt-row" style="color: #333;">
                <span>Diskon Voucher</span>
                <span>-${formatRp(orderDiscount)}</span>
            </div>` : ''}

            <div class="receipt-divider double"></div>

            <div class="receipt-row bold" style="font-size: 14.5px;">
                <span>TOTAL AKHIR</span>
                <span>${formatRp(totalAmount)}</span>
            </div>

            ${taxPercent > 0 ? `
            <div class="receipt-row" style="font-size: 9.5px;">
                <span>Termasuk PB1/PPN ${taxPercent}%</span>
                <span>${formatRp(taxAmount)}</span>
            </div>` : ''}

            ${(tx.paymentMethod || txData.paymentMethod) === 'CASH' ? `
            <div class="receipt-row" style="margin-top: 4px;">
                <span>Tunai Diterima</span>
                <span>${formatRp(cashTendered)}</span>
            </div>
            <div class="receipt-row bold">
                <span>Kembalian</span>
                <span>${formatRp(changeAmount)}</span>
            </div>` : ''}

            ${pointsEarned > 0 ? `
            <div class="receipt-divider"></div>
            <div class="receipt-row" style="font-weight: 700; color: #6F4E37;">
                <span>Poin Loyalitas</span>
                <span>+${pointsEarned} Pts</span>
            </div>` : ''}

            <div class="receipt-divider double"></div>
            <div class="receipt-footer">
                <p>${info.RECEIPT_FOOTER || 'Terima kasih atas kunjungan Anda!'}</p>
                <div style="font-size: 10px; color: #444; margin-top: 8px; letter-spacing: 3px; font-family: monospace;">
                    * ${txCode} *
                </div>
            </div>
        </div>
    `;
}

// Mobile Sidebar Toggle Helper
function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar) sidebar.classList.toggle('open');
    if (backdrop) backdrop.classList.toggle('show');
    // Tanpa ini halaman di belakang ikut ter-scroll saat menu dibuka di HP.
    document.body.classList.toggle('scroll-locked', !!(sidebar && sidebar.classList.contains('open')));
}

// Esc menutup panel melayang mana pun yang sedang terbuka
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const sidebar = document.querySelector('.sidebar.open');
    if (sidebar) {
        toggleMobileSidebar();
        return;
    }
    if (typeof toggleMobileCart === 'function' && document.querySelector('.pos-cart-panel.open')) {
        toggleMobileCart();
    }
});

// Sidebar collapse (desktop only; below 1024px the sidebar is an off-canvas drawer)
function toggleSidebarCollapse() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const collapsed = sidebar.classList.toggle('collapsed');
    localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
}

function initSidebarCollapse() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    // Give every nav item a tooltip so the collapsed rail stays readable
    sidebar.querySelectorAll('.nav-item').forEach(item => {
        const label = item.querySelector('span');
        if (label && !item.title) item.title = label.textContent.trim();
    });

    if (document.documentElement.classList.contains('sidebar-collapsed-init')) {
        sidebar.classList.add('no-transition', 'collapsed');
        // Re-enable the transition only after the first frame has painted
        requestAnimationFrame(() => requestAnimationFrame(() => {
            sidebar.classList.remove('no-transition');
            document.documentElement.classList.remove('sidebar-collapsed-init');
        }));
    }
}

// Thermal Receipt Isolated Print Mode (Prints only the receipt slip with auto paper-size detection)
async function printReceipt(containerId = null, forcedPaperSize = null) {
    const targetEl = containerId 
        ? (document.getElementById(containerId) ? document.getElementById(containerId).querySelector('.thermal-receipt-card') || document.getElementById(containerId) : null)
        : (document.getElementById('printable-receipt') || document.querySelector('.thermal-receipt-card'));

    if (!targetEl) {
        window.print();
        return;
    }

    const settings = await getStoreSettings();
    const paperSize = forcedPaperSize || (settings ? settings.RECEIPT_PAPER_SIZE : '58mm') || '58mm';
    const is58mm = (paperSize === '58mm' || paperSize === '58');

    // Create or reuse hidden iframe to print ONLY the receipt without full-page layout
    let iframe = document.getElementById('receipt-print-frame');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.id = 'receipt-print-frame';
        iframe.style.position = 'fixed';
        iframe.style.right = '0';
        iframe.style.bottom = '0';
        iframe.style.width = '0';
        iframe.style.height = '0';
        iframe.style.border = '0';
        document.body.appendChild(iframe);
    }

    // --- Thermal geometry, expressed in millimetres so it does not depend on the
    // browser's 96dpi px assumption ---
    // A cheap 203dpi thermal head prints 384 dots on 58mm paper (48.0mm) and 576 dots
    // on 80mm paper (72.1mm). Those are the real printable widths; the rest of the
    // roll is dead margin. Standard line length is 32 characters on 58mm and 48 on
    // 80mm, and a monospace glyph advances 0.6em, which fixes the body font size:
    //   58mm -> 46.5mm usable / 32 chars / 0.6 = 2.42mm
    //   80mm -> 70.5mm usable / 48 chars / 0.6 = 2.45mm
    // Near enough to share one value. RECEIPT_PRINT_SCALE is the calibration knob for
    // printers whose driver does not hit the nominal size exactly.
    const scalePct = parseFloat(settings && settings.RECEIPT_PRINT_SCALE) || 100;
    const scale = Math.min(200, Math.max(50, scalePct)) / 100;
    const mm = (v) => (v * scale).toFixed(2) + 'mm';

    const pageSizeCss = is58mm ? '58mm auto' : '80mm auto';
    const bodyWidthCss = is58mm ? '48mm' : '72mm';
    const sidePaddingCss = is58mm ? '0.75mm' : '0.75mm';

    const fontSizeCss = mm(2.42);
    const titleSizeCss = mm(3.4);
    const boldSizeCss = mm(2.9);
    const metaSizeCss = mm(2.1);
    const lineHeightCss = '1.3';
    const dividerMargin = mm(1.1) + ' 0';
    const doubleMargin = mm(1.5) + ' 0';

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Struk Transaksi</title>
            <style>
                @page {
                    size: ${pageSizeCss};
                    margin: 0;
                }
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }
                body {
                    background: #FFF;
                    /* Pure black only: thermal heads have no greyscale, and dithered
                       grey comes out as faint speckle on cheap paper. */
                    color: #000;
                    font-family: 'Courier New', Courier, monospace;
                    font-size: ${fontSizeCss};
                    line-height: ${lineHeightCss};
                    width: ${bodyWidthCss};
                    /* Left-aligned, not centred: the printable area starts at the paper
                       edge, so centring inside the sheet pushes content off the head. */
                    margin: 0;
                    padding: 1mm ${sidePaddingCss};
                }
                .thermal-receipt-card {
                    width: 100% !important;
                    max-width: 100% !important;
                    box-shadow: none !important;
                    border: none !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    background: transparent !important;
                    font-size: inherit !important;
                }
                .receipt-header { text-align: center; margin-bottom: ${mm(1.5)}; }
                .receipt-store-title { font-weight: 700; font-size: ${titleSizeCss}; text-transform: uppercase; }
                .receipt-meta-info { font-size: ${metaSizeCss}; color: #000; margin-top: ${mm(0.5)}; line-height: 1.25; }
                .receipt-divider { border-top: 1px dashed #000; margin: ${dividerMargin}; }
                .receipt-divider.double { border-top: 1px solid #000; margin: ${doubleMargin}; }
                .receipt-row { display: flex; justify-content: space-between; gap: ${mm(1)}; margin-bottom: ${mm(0.4)}; font-size: ${fontSizeCss}; }
                .receipt-row.bold { font-weight: 700; font-size: ${boldSizeCss}; }
                .receipt-footer { text-align: center; font-size: ${metaSizeCss}; margin-top: ${mm(2)}; }
                .receipt-logo { display: none !important; }
                /* Long menu names must wrap inside the slip, never widen it */
                * { word-break: break-word; overflow-wrap: anywhere; }
            </style>
        </head>
        <body>
            ${targetEl.outerHTML}
        </body>
        </html>
    `);
    doc.close();

    setTimeout(() => {
        iframe.contentWindow.focus();
        iframe.contentWindow.print();
    }, 200);
}

// Report Print Mode
function printReport() {
    document.body.classList.add('printing-report');
    window.print();
    setTimeout(() => {
        document.body.classList.remove('printing-report');
    }, 500);
}

// RBAC Dynamic Route & Sidebar Navigation Guard
async function initRbacNavigation() {
    const user = getUser();
    if (!user) return;

    try {
        const rbac = await apiFetch('/role-access/allowed-routes');
        if (!rbac || !rbac.allowedPaths) return;

        const currentPath = window.location.pathname;
        const isAllowed = rbac.allowedPaths.some(p => currentPath === p || (p !== '/' && currentPath.startsWith(p)));

        // Filter sidebar navigation items based on permission
        const navLinks = document.querySelectorAll('.sidebar .nav-item[href]');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && href !== '#' && href !== '/login') {
                const canAccess = rbac.allowedPaths.includes(href);
                if (!canAccess) {
                    link.style.display = 'none';
                } else {
                    link.style.display = 'flex';
                }
            }
        });

        // Hide navigation category headers if all children are hidden
        const navSections = document.querySelectorAll('.sidebar .nav-section-title');
        navSections.forEach(title => {
            let nextEl = title.nextElementSibling;
            let hasVisibleChild = false;
            while (nextEl && nextEl.classList.contains('nav-item')) {
                if (nextEl.style.display !== 'none') {
                    hasVisibleChild = true;
                }
                nextEl = nextEl.nextElementSibling;
            }
            if (!hasVisibleChild) {
                title.style.display = 'none';
            }
        });

        // Redirect if user manually accessed an unauthorized URL
        if (!isAllowed && currentPath !== '/login') {
            showToast(`Akses Ditolak: Role [${user.role}] tidak memiliki izin membuka halaman ini.`, 'warning');
            setTimeout(() => {
                window.location.href = rbac.landingPage || '/pos';
            }, 600);
        }
    } catch (e) {
        console.warn('RBAC navigation check warning:', e);
    }
}

// Global Initialization
document.addEventListener('DOMContentLoaded', async () => {
    const isLoginPage = window.location.pathname.includes('/login');
    const user = getUser();
    const token = localStorage.getItem('token');

    if (!isLoginPage && (!token || !user)) {
        window.location.href = '/login';
        return;
    }

    if (isLoginPage && token && user) {
        window.location.href = '/dashboard';
        return;
    }

    // Populate user profile info in navbar/sidebar
    if (user) {
        document.querySelectorAll('.user-name').forEach(el => el.textContent = user.username);
        document.querySelectorAll('.user-role').forEach(el => el.textContent = user.role || 'CASHIER');
        document.querySelectorAll('.user-avatar').forEach(el => el.textContent = (user.username || 'U').charAt(0).toUpperCase());
    }

    // Initialize RBAC navigation filtering & route protection
    if (!isLoginPage) {
        initSidebarCollapse();
        initRbacNavigation();
    }

    // Fetch store settings in background (needs a token: /api/settings is auth-guarded)
    if (token) {
        const settings = await getStoreSettings();
        const paperBadge = document.getElementById('topbar-paper-size');
        if (paperBadge && settings) {
            paperBadge.innerHTML = `<i class="fas fa-receipt"></i> ${settings.RECEIPT_PAPER_SIZE || '58mm'}`;
        }
    }

    // Initialize shift status widget if present
    updateShiftStatusWidget();
});
