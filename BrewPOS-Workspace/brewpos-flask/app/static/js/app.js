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
    // Simpan data mentahnya; tombol cetak thermal menyusun ESC/POS dari sini.
    lastReceiptData = txData;

    const info = storeInfo || cachedStoreSettings || {
        STORE_NAME: 'ARUNIKA COFFEE',
        TAGLINE: 'Every Cup Has A Story',
        RECEIPT_FOOTER: 'Terima kasih atas kunjungannya!',
        TAX_PERCENT: '11'
    };

    const user = getUser();
    // Struk layar dan struk kertas dibangun dari model baris yang sama, jadi
    // bentuknya tidak bisa lagi berbeda. Dulu keduanya ditulis terpisah dan
    // versi HTML jauh lebih bertele-tele daripada yang keluar di printer.
    return EscPos.buildReceiptHtml(txData, info, {
        cols: receiptColumns(info),
        cashierName: (user && user.username) ? user.username : 'Kasir'
    });
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
/*
 * Cetak struk lewat printer thermal Bluetooth bila aplikasi Android terpasang.
 * Kalau tidak ada jembatannya (dibuka dari browser biasa/desktop), pemanggil
 * jatuh kembali ke printReceipt() berbasis HTML.
 *
 * lastReceiptData diisi saat struk ditampilkan, supaya tombol cetak punya data
 * mentahnya -- bukan hasil render HTML.
 */
let lastReceiptData = null;

function receiptColumns(settings) {
    const paper = ((settings && settings.RECEIPT_PAPER_SIZE) || '58mm').toString();
    return paper.startsWith('80') ? 48 : 32;
}

/* Petunjuk "Margins: None, Scale: 100" hanya berlaku untuk dialog cetak browser.
   Di dalam aplikasi kasir, struk keluar langsung ke printer thermal. */
function hideBrowserPrintHintIfBridged() {
    if (typeof EscPos === 'undefined' || !EscPos.hasBridge()) return;
    document.querySelectorAll('.browser-print-hint').forEach(el => { el.style.display = 'none'; });
}

async function printReceiptThermal(txData = null) {
    if (typeof EscPos === 'undefined' || !EscPos.hasBridge()) return false;

    const data = txData || lastReceiptData;
    if (!data) return false;

    try {
        const settings = await getStoreSettings();
        const user = getUser();
        const bytes = EscPos.buildReceipt(data, settings, {
            cols: receiptColumns(settings),
            cut: (settings && settings.RECEIPT_AUTO_CUT) !== '0',
            cashierName: (user && user.username) ? user.username : 'Kasir'
        });
        EscPos.sendToBridge(bytes);
        return true;
    } catch (e) {
        console.error('Gagal menyusun struk ESC/POS:', e);
        return false;
    }
}

/*
 * Struk lewat printer USB di PC. Dipisah dari printReceiptThermal karena
 * jembatannya beda: Android pakai Bluetooth, PC pakai WebUSB. Bytenya sama.
 *
 * Mengembalikan false kalau printer USB belum dipilih atau browsernya tidak
 * mendukung -- pemanggil lalu jatuh ke dialog cetak.
 */
/* Byte struk untuk transaksi ini. Dipakai semua jalur printer, supaya hasil di
   Bluetooth, USB, dan jembatan lokal tidak mungkin berbeda bentuk. */
async function byteStruk(txData = null) {
    const data = txData || lastReceiptData;
    if (!data) return null;
    const settings = await getStoreSettings();
    const user = getUser();
    return EscPos.buildReceipt(data, settings, {
        cols: receiptColumns(settings),
        cut: (settings && settings.RECEIPT_AUTO_CUT) !== '0',
        cashierName: (user && user.username) ? user.username : 'Kasir'
    });
}

/*
 * Jembatan printer lokal di PC kasir (printer_agent.py). Jalur ini yang dipakai
 * kalau printer tercolok di PC kasir sementara servernya di mesin lain: driver
 * Windows resmi tetap terpakai, dan bytenya sama persis dengan Android.
 */
async function printReceiptAgent(txData = null) {
    if (typeof EscPos === 'undefined') return false;
    if (!(await EscPos.agentAvailable())) return false;

    const bytes = await byteStruk(txData);
    if (!bytes) return false;
    await EscPos.sendToAgent(bytes);
    return true;
}

async function printReceiptUsb(txData = null) {
    if (typeof EscPos === 'undefined' || !EscPos.usbSupported()) return false;

    const device = await EscPos.getUsbPrinter();
    if (!device) return false;   // belum pernah diizinkan; jangan paksa dialog di sini

    const bytes = await byteStruk(txData);
    if (!bytes) return false;
    await EscPos.sendToUsb(bytes, device);
    return true;
}

/*
 * Kenapa struk tidak keluar lewat printer USB. Dialog cetak browser selalu
 * bisa dipakai, tapi hasilnya buram: teks digambar dengan antialiasing lalu
 * dipaksa jadi hitam-putih oleh kepala thermal, hurufnya keluar putus-putus.
 * Jatuh ke sana tanpa memberi tahu membuat pengguna mengira sudah mentok,
 * padahal jalur yang tajam cuma butuh satu langkah lagi.
 */
async function alasanPrinterUsbTidakDipakai() {
    if (typeof EscPos === 'undefined') return 'Modul struk gagal dimuat.';

    if (!EscPos.usbSupported()) {
        if (typeof window !== 'undefined' && window.isSecureContext === false) {
            return `Printer USB dimatikan browser karena halaman dibuka lewat ` +
                   `${window.location.protocol}//${window.location.host}. ` +
                   `WebUSB hanya jalan di HTTPS atau localhost.`;
        }
        return 'Browser ini tidak mendukung WebUSB. Pakai Chrome atau Edge versi baru.';
    }
    if (!(await EscPos.getUsbPrinter())) {
        return 'Printer USB belum dipilih. Buka Pengaturan → Hubungkan Printer USB (cukup sekali).';
    }
    return null;
}

/* Dipanggil tombol "Cetak Struk": printer Bluetooth (Android), lalu printer USB
   (PC), baru dialog cetak browser sebagai jalan terakhir. */
async function printReceiptSmart(containerId = null, txData = null) {
    if (await printReceiptThermal(txData)) {
        showToast('Struk dikirim ke printer', 'success');
        return;
    }
    try {
        // Jembatan lokal lebih dulu: jalan di http biasa dan tetap memakai
        // driver resmi printer, jadi tidak menuntut apa-apa dari pengguna
        // selain menjalankan programnya.
        if (await printReceiptAgent(txData)) {
            showToast('Struk dikirim ke printer', 'success');
            return;
        }
        if (await printReceiptUsb(txData)) {
            showToast('Struk dikirim ke printer USB', 'success');
            return;
        }
        // Bukan galat, tapi pengguna tetap harus tahu kenapa hasilnya buram.
        const alasan = await alasanPrinterUsbTidakDipakai();
        if (alasan) showToast(alasan, 'warning');
    } catch (e) {
        // Printer USB sudah dipilih tapi gagal dipakai: beri tahu, jangan
        // diam-diam jatuh ke dialog cetak yang hasilnya buram.
        console.error('Gagal mengirim ke printer USB:', e);
        showToast('Printer USB gagal: ' + e.message + '. Memakai dialog cetak.', 'warning');
    }
    printReceipt(containerId);
}

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
    // roll is dead margin. Standard line length is 32 characters on 58mm, 48 on 80mm,
    // and a monospace glyph advances 0.6em -- which is what fixes the body font size.
    //
    // The figures below are deliberately ~1mm narrower than the true printable width.
    // Filling it exactly leaves zero tolerance: the browser rounds mm to device dots,
    // and one dot of rounding pushes the last character of every right-aligned line
    // off the paper. RECEIPT_PRINT_SCALE is the calibration knob for drivers that do
    // not hit the nominal size.
    const scalePct = parseFloat(settings && settings.RECEIPT_PRINT_SCALE) || 100;
    const scale = Math.min(200, Math.max(50, scalePct)) / 100;
    const mm = (v) => (v * scale).toFixed(3) + 'mm';

    const cols = is58mm ? 32 : 48;
    const contentMm = is58mm ? 45.5 : 69.5;   // ruang teks, sudah termasuk kelonggaran
    const sidePadMm = 0.75;

    const pageSizeCss = is58mm ? '58mm auto' : '80mm auto';
    const bodyWidthCss = mm(contentMm + sidePadMm * 2);
    const sidePaddingCss = mm(sidePadMm);

    // Satu sumber angka: lebar isi / jumlah kolom / lebar maju glyph monospace.
    const fontSizeCss = mm(contentMm / cols / 0.6);
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
                /* Kelas-kelas ini dipancarkan linesToHtml() di escpos.js -- kalau di sana
                   berubah, aturan di bawah wajib ikut (dijaga oleh test_escpos.js). */

                /* white-space: pre wajib. Perataan kanan di jalur HTML sepenuhnya
                   bergantung pada spasi padding buatan pair(); tanpa pre, browser
                   meringkasnya jadi satu spasi dan semua nilai jadi rata kiri. */
                .receipt-line { white-space: pre; line-height: ${lineHeightCss}; }
                .receipt-line.center { text-align: center; }
                .receipt-line.bold { font-weight: 700; }
                /* Nama toko: em, bukan mm, supaya ikut skala kalibrasi. pre-wrap
                   bukan pre -- nama panjang harus membungkus, bukan menjulur. */
                .receipt-line.title { font-size: 1.4em; font-weight: 700; white-space: pre-wrap; line-height: 1.25; }
                /* TOTAL: HANYA lebih tebal & lebih tinggi, JANGAN diperbesar lebarnya.
                   Barisnya sudah dipadding tepat ${cols} karakter oleh pair(), jadi font
                   yang lebih lebar pasti menjulur keluar kertas. Printer pun cuma
                   menggandakan tinggi (SIZE_TALL), bukan lebar. */
                .receipt-line.total { font-weight: 700; line-height: 1.7; padding: 0.4mm 0; }
                .receipt-rule { border-top: 1px dashed #000; margin: ${dividerMargin}; }
                .receipt-rule.strong { border-top: 1px solid #000; margin: ${doubleMargin}; }
                /* .receipt-gap tingginya inline dari escpos.js, tidak perlu aturan di sini. */
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
    hideBrowserPrintHintIfBridged();
});
