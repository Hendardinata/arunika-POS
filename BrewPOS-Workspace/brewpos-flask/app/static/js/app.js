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
    const user = getUser();
    
    const headers = {
        'Accept': 'application/json',
        ...(options.headers || {})
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    if (user && user.id) {
        headers['X-User-Id'] = user.id.toString();
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

        if (res.status === 401 && !endpoint.includes('/auth/login')) {
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
            throw new Error(data.error || data.message || 'Terjadi kesalahan pada server');
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
            PARKING_FEE: '2000'
        };
        list.forEach(s => {
            if (s.key) map[s.key] = s.value;
        });
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
            PARKING_FEE: '2000'
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
            widget.className = 'shift-status-pill open';
            widget.innerHTML = `<span class="status-dot"></span> Shift ${s.type} (Kasir Aktif)`;
            widget.title = `Modal Awal: ${formatRp(s.startingCash)}`;
        } else {
            widget.className = 'shift-status-pill closed';
            widget.innerHTML = `<span class="status-dot"></span> Shift Tutup`;
            widget.title = `Belum ada shift terbuka`;
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
            const startTimeStr = new Date(s.startTime).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
            content.innerHTML = `
                <div style="background: var(--color-success-bg); border: 1px solid rgba(46, 125, 50, 0.3); padding: 18px; border-radius: var(--radius-md); margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                        <i class="fas fa-check-circle text-success" style="font-size: 20px;"></i>
                        <h4 style="color: var(--color-success); font-size: 16px; margin: 0;">Shift ${s.type} Aktif</h4>
                    </div>
                    <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                        <p><strong>Modal Awal:</strong> ${formatRp(s.startingCash)}</p>
                        <p><strong>Mulai Sejak:</strong> Jam ${startTimeStr} WIB</p>
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Total Uang Tunai di Laci Kasir (Rp)</label>
                    <input type="number" id="shift-ending-cash" class="form-control" placeholder="Contoh: 1250000" required>
                    <small class="text-muted" style="font-size: 11.5px; margin-top: 4px; display: block;">
                        Hitung seluruh uang fisik di laci kasir saat ini untuk rekonsiliasi akhir shift.
                    </small>
                </div>

                <button class="btn btn-danger" style="width: 100%; margin-top: 8px;" onclick="submitCloseShift()">
                    <i class="fas fa-door-closed"></i> Tutup & Rekonsiliasi Shift
                </button>
            `;
        } else {
            const user = getUser();
            const defaultShift = (user && user.assignedShift) ? user.assignedShift : 'MORNING';
            content.innerHTML = `
                <p style="margin-bottom: 18px; font-size: 13px; color: var(--text-secondary);">
                    Tidak ada shift kasir yang aktif saat ini. Masukkan modal uang awal di laci kasir untuk mulai transaksi.
                </p>
                <div class="form-group">
                    <label class="form-label">Pilih Sesi Shift</label>
                    <select id="shift-type-select" class="form-control">
                        <option value="MORNING" ${defaultShift === 'MORNING' ? 'selected' : ''}>Shift Pagi (Morning)</option>
                        <option value="NIGHT" ${defaultShift === 'NIGHT' ? 'selected' : ''}>Shift Malam (Night)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Modal Kas Awal di Laci (Rp)</label>
                    <input type="number" id="shift-starting-cash" class="form-control" placeholder="Contoh: 200000" value="200000" required>
                </div>
                <button class="btn btn-primary" style="width: 100%; margin-top: 8px;" onclick="submitOpenShift()">
                    <i class="fas fa-door-open"></i> Buka Shift Kasir Baru
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
        showToast('Shift kasir berhasil dibuka!', 'success');
        closeModal('modal-shift');
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
        const res = await apiFetch('/shift/close', {
            method: 'POST',
            body: JSON.stringify({ endingCash })
        });
        const diff = res.endingCash - res.expectedEndingCash;
        let diffMsg = 'Kas pas!';
        if (diff > 0) diffMsg = `Lebih kas: ${formatRp(diff)}`;
        if (diff < 0) diffMsg = `Kurang kas: ${formatRp(Math.abs(diff))}`;

        showToast(`Shift ditutup. Ekspektasi: ${formatRp(res.expectedEndingCash)} (${diffMsg})`, 'success');
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
    const taxPercent = parseFloat(info.TAX_PERCENT || '11');
    const taxAmount = (tx.taxAmount !== undefined) ? tx.taxAmount : (txData.taxAmount || 0);
    const subTotal = (tx.subTotal !== undefined && tx.subTotal > 0) ? tx.subTotal : Math.round(totalAmount / (1 + (taxPercent / 100)));
    const cashTendered = txData.cashReceived || tx.cashReceived || totalAmount;
    const changeAmount = (cashTendered > totalAmount) ? (cashTendered - totalAmount) : 0;
    const pointsEarned = (tx.pointsEarned !== undefined) ? tx.pointsEarned : (txData.pointsEarned || 0);

    return `
        <div class="thermal-receipt-card" id="printable-receipt">
            <div class="receipt-header">
                <div class="receipt-logo">☕</div>
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
                <span>${formatRp(subTotal)}</span>
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

            <div class="receipt-row">
                <span>PB1 / PPN (${taxPercent}% inc.)</span>
                <span>${formatRp(taxAmount)}</span>
            </div>

            <div class="receipt-divider double"></div>

            <div class="receipt-row bold" style="font-size: 14.5px;">
                <span>TOTAL AKHIR</span>
                <span>${formatRp(totalAmount)}</span>
            </div>

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
                <span>⭐ Poin Loyalitas</span>
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
}

// Thermal Receipt Print Mode
function printReceipt() {
    document.body.classList.add('printing-receipt');
    window.print();
    setTimeout(() => {
        document.body.classList.remove('printing-receipt');
    }, 500);
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
        initRbacNavigation();
    }

    // Fetch store settings in background
    await getStoreSettings();

    // Initialize shift status widget if present
    updateShiftStatusWidget();
});
