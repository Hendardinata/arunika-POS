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
function gambarPillSesi(shift, aktif) {
    const widget = document.getElementById('shift-status-widget');
    if (!widget) return;

    // Sesi kas dimatikan: sembunyikan pill-nya sekalian. Kalau cuma didiamkan,
    // ia menampilkan "Tutup" selamanya dan terbaca seperti ada yang salah.
    // Penjualan tetap jalan tanpa sesi -- siapa yang melayani tetap tercatat di
    // Transaction.userId, terpisah dari sesi kas.
    if (!aktif) {
        widget.style.display = 'none';
        return;
    }
    widget.style.display = '';

    if (shift) {
        const keeper = shift.currentUser ? shift.currentUser.username : 'Kasir';
        const stale = shift.status === 'NEEDS_REVIEW';
        widget.className = 'shift-status-pill open';
        // Nama penjaga dibungkus .shift-text: di layar sempit bagian itu
        // disembunyikan CSS supaya pill tidak terpotong di tepi layar.
        widget.innerHTML = stale
            ? `<span class="status-dot"></span> ${shift.label}<span class="shift-text"> &middot; perlu ditutup</span>`
            : `<span class="status-dot"></span> ${shift.label}<span class="shift-text"> &middot; ${keeper}</span>`;
        widget.title = stale
            ? `Sesi ini terbuka melewati batas jam. Modal Awal: ${formatRp(shift.startingCash)}`
            : `Modal Awal: ${formatRp(shift.startingCash)}`;
    } else {
        widget.className = 'shift-status-pill closed';
        widget.innerHTML = `<span class="status-dot"></span> Tutup<span class="shift-text"> &middot; Sesi Kas</span>`;
        widget.title = `Belum ada sesi kas terbuka`;
    }
}

/* Ambil ulang status sesi dari server. Dipakai setelah buka/tutup/serah terima,
   di mana data cache pasti sudah basi. */
async function updateShiftStatusWidget() {
    if (!document.getElementById('shift-status-widget')) return;
    hapusBootCache();
    try {
        await muatBootstrap({ pakaiCache: false });
    } catch (e) {
        gambarPillSesi(null, true);
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
                    Sesi ini sudah terbuka melewati batas jam dan ditandai <strong>perlu ditinjau</strong>. Tutup dan cocokkan kasnya.
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
                        ${s.handovers && s.handovers.length ? `
                            <p><strong>Pergantian penjaga:</strong> ${s.handovers.length}x</p>
                            ${s.handovers.map(h => {
                                const jam = new Date(h.createdAt).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
                                // Selisih ditampilkan per giliran: inilah gunanya
                                // menghitung laci saat berganti penjaga.
                                if (h.countedCash === null || h.countedCash === undefined) {
                                    return `<p style="margin-left: 10px; font-size: 12px;">${jam} &middot;
                                        ${h.fromUsername || '-'} &rarr; ${h.toUsername}
                                        <span class="text-muted">(kas tidak dihitung)</span></p>`;
                                }
                                const d = h.difference;
                                const label = d === 0 ? 'pas'
                                    : `${d > 0 ? 'lebih' : 'kurang'} ${formatRp(Math.abs(d))}`;
                                return `<p style="margin-left: 10px; font-size: 12px;">${jam} &middot;
                                    ${h.fromUsername || '-'} &rarr; ${h.toUsername} &middot;
                                    <strong class="${d === 0 ? 'text-success' : 'text-danger'}">${label}</strong></p>`;
                            }).join('')}
                        ` : ''}
                    </div>
                </div>

                ${handoverBtn}

                <!-- Uang keluar-masuk laci di luar penjualan & belanja. Tanpa ini
                     laci tidak akan pernah cocok begitu ada yang disetor ke
                     brankas atau receh ditambah. -->
                <div style="border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 12px 14px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <strong style="font-size: 13px;"><i class="fas fa-right-left text-primary"></i> Uang Keluar/Masuk Laci</strong>
                        <button class="btn btn-secondary btn-sm" onclick="bukaFormGerakanKas()">
                            <i class="fas fa-plus"></i> Catat
                        </button>
                    </div>
                    <div id="cash-movement-list" style="font-size: 12px;">Memuat...</div>
                </div>

                <div class="form-group">
                    <label class="form-label">Total Uang Tunai di Laci Kasir (Rp)</label>
                    <input type="number" id="shift-ending-cash" class="form-control" placeholder="Contoh: 1250000" required>
                    <small class="text-muted" style="font-size: 11.5px; margin-top: 4px; display: block;">
                        Hitung uang fisiknya dulu, jangan menebak dari sistem &mdash; kalau angkanya
                        disalin dari perkiraan, selisih kas tidak akan pernah ketahuan.
                    </small>
                    <button type="button" class="btn btn-secondary btn-sm" style="margin-top: 6px;"
                            onclick="togglePenghitungPecahan()">
                        <i class="fas fa-calculator"></i> Bantu hitung per pecahan
                    </button>
                    <div id="denom-counter" style="display: none; margin-top: 8px; background: #FAF8F5; border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px;"></div>
                </div>
                <div class="form-group">
                    <label class="form-label">Catatan Penutupan</label>
                    <input type="text" id="shift-closing-note" class="form-control" placeholder="Wajib diisi bila selisihnya besar">
                </div>

                <button class="btn btn-danger" style="width: 100%; margin-top: 8px;" onclick="submitCloseShift()">
                    <i class="fas fa-door-closed"></i> Tutup & Rekonsiliasi Sesi Kas
                </button>
            `;
            muatGerakanKas();
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

/* ----------------------------------------------------------------------
   Uang keluar-masuk laci

   Setoran ke brankas saat laci penuh, tambah receh, uang diambil pemilik.
   Bukan penjualan dan bukan belanja, jadi sebelumnya tidak terwakili sama
   sekali -- dan sekali terjadi, laci tidak pernah cocok lagi.
   ---------------------------------------------------------------------- */
async function muatGerakanKas() {
    const el = document.getElementById('cash-movement-list');
    if (!el) return;
    try {
        const data = await apiFetch('/shift/cash-movement');
        if (!data.items.length) {
            el.innerHTML = '<span class="text-muted">Belum ada. Catat di sini kalau uang '
                         + 'disetor ke brankas, ditambah receh, atau diambil.</span>';
            return;
        }
        el.innerHTML = data.items.map(m => `
            <div style="display: flex; justify-content: space-between; gap: 8px; padding: 3px 0;">
                <span>${m.type === 'DROP' ? '&minus;' : '+'} ${formatRp(m.amount)}
                    <span class="text-muted">&middot; ${m.reason}</span></span>
                <button class="btn btn-secondary btn-sm" style="padding: 0 6px;"
                        onclick="hapusGerakanKas(${m.id})" title="Hapus">&times;</button>
            </div>`).join('')
            + `<div style="border-top: 1px solid var(--border-light); margin-top: 6px; padding-top: 6px;">
                 <strong>Bersih: ${data.net < 0 ? '&minus;' : '+'} ${formatRp(Math.abs(data.net))}</strong>
               </div>`;
    } catch (e) {
        el.innerHTML = `<span class="text-danger">Gagal memuat: ${e.message}</span>`;
    }
}

async function bukaFormGerakanKas() {
    const arah = prompt('Uang KELUAR atau MASUK laci?\n\nKetik: keluar / masuk');
    if (!arah) return;
    const jenis = arah.trim().toLowerCase().startsWith('k') ? 'DROP' : 'PAID_IN';

    const nominal = parseInt(prompt(jenis === 'DROP'
        ? 'Berapa yang dikeluarkan dari laci? (Rp)'
        : 'Berapa yang dimasukkan ke laci? (Rp)'), 10);
    if (!nominal || nominal <= 0) return;

    const alasan = prompt(jenis === 'DROP'
        ? 'Untuk apa? (mis. setor ke brankas, diambil pemilik)'
        : 'Dari mana? (mis. tambah receh dari brankas)');
    if (!alasan) return;

    try {
        await apiFetch('/shift/cash-movement', {
            method: 'POST',
            body: JSON.stringify({ type: jenis, amount: nominal, reason: alasan })
        });
        showToast('Tercatat', 'success');
        muatGerakanKas();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function hapusGerakanKas(id) {
    if (!confirm('Hapus catatan ini?')) return;
    try {
        await apiFetch(`/shift/cash-movement/${id}`, { method: 'DELETE' });
        muatGerakanKas();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

/* Penghitung pecahan: menghitung uang fisik lebih akurat daripada menjumlah
   di kepala, dan hasilnya mengisi kolom uang laci. */
const PECAHAN = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100];

function togglePenghitungPecahan() {
    const box = document.getElementById('denom-counter');
    if (!box) return;
    if (box.style.display === 'block') { box.style.display = 'none'; return; }

    box.innerHTML = PECAHAN.map(p => `
        <div style="display: grid; grid-template-columns: 90px 1fr 100px; gap: 6px; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 12px;">${formatRp(p)}</span>
            <input type="number" min="0" class="form-control denom-qty" data-nilai="${p}"
                   placeholder="0" oninput="hitungPecahan()" style="padding: 4px 8px; font-size: 12px;">
            <span class="denom-sub text-muted" style="font-size: 12px; text-align: right;">Rp 0</span>
        </div>`).join('')
        + `<div style="border-top: 1px solid var(--border-color); margin-top: 6px; padding-top: 6px; text-align: right;">
             <strong id="denom-total">Rp 0</strong>
           </div>`;
    box.style.display = 'block';
}

function hitungPecahan() {
    let total = 0;
    document.querySelectorAll('.denom-qty').forEach((inp, i) => {
        const nilai = parseInt(inp.dataset.nilai, 10);
        const jml = parseInt(inp.value, 10) || 0;
        const sub = nilai * jml;
        total += sub;
        document.querySelectorAll('.denom-sub')[i].textContent = formatRp(sub);
    });
    document.getElementById('denom-total').textContent = formatRp(total);
    document.getElementById('shift-ending-cash').value = total;
}

async function submitShiftHandover() {
    /*
     * Hitungan laci saat berganti penjaga -- opsional.
     *
     * Kalau diisi, selisih kas bisa dilokalisir ke giliran siapa; tanpa itu
     * selisih hanya diketahui totalnya di akhir sesi 16 jam, dan tidak ada yang
     * bisa dimintai keterangan. Tetap opsional karena pergantian sebentar
     * (ke belakang, salat) tidak perlu dihitung, dan memaksanya justru membuat
     * orang mengarang angka.
     */
    const jawab = prompt(
        'Hitung uang di laci sekarang? Ini mengunci tanggung jawab giliran '
        + 'penjaga sebelumnya.\n\n'
        + 'Isi jumlahnya, atau kosongkan lalu OK untuk lewati.');
    if (jawab === null) return;

    const body = {};
    const dihitung = parseInt(jawab, 10);
    if (jawab.trim() !== '' && !isNaN(dihitung)) body.countedCash = dihitung;

    try {
        const res = await apiFetch('/shift/handover', {
            method: 'POST', body: JSON.stringify(body)
        });
        const h = res.handover || {};
        if (h.countedCash !== null && h.countedCash !== undefined) {
            const d = h.difference;
            showToast(
                d === 0 ? `Kas pas saat serah terima (${formatRp(h.countedCash)}).`
                        : `Giliran sebelumnya ${d > 0 ? 'LEBIH' : 'KURANG'} ${formatRp(Math.abs(d))}.`,
                d === 0 ? 'success' : 'warning');
        }
        showToast('Anda tercatat sebagai penjaga sesi kas sekarang.', 'success');
        openShiftModal();
        updateShiftStatusWidget();
    } catch (err) {
        // Selisih besar ditolak sampai diberi keterangan; minta di sini juga.
        if (err.data && err.data.requiresNote) {
            const alasan = prompt(err.message + '\n\nKeterangannya apa?');
            if (!alasan) return;
            body.note = alasan;
            try {
                await apiFetch('/shift/handover', { method: 'POST', body: JSON.stringify(body) });
                showToast('Serah terima tercatat berikut keterangannya.', 'success');
                openShiftModal();
                updateShiftStatusWidget();
            } catch (e2) {
                showToast(e2.message, 'error');
            }
            return;
        }
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
        const b = res.breakdown || {};
        const diff = res.difference !== undefined ? res.difference
                                                  : res.endingCash - res.expectedEndingCash;
        // Rinciannya ditampilkan setelah tutup, bukan sebelum: kalau angka
        // harapan terlihat lebih dulu, orang tinggal menyalinnya dan selisih
        // kas tidak akan pernah ketahuan.
        showToast(
            `Sesi ditutup. Modal ${formatRp(b.startingCash || 0)}`
            + ` + tunai ${formatRp(b.cashSales || 0)}`
            + ` - belanja ${formatRp(b.cashExpenses || 0)}`
            + ` - keluar ${formatRp(b.cashDrops || 0)}`
            + ` + masuk ${formatRp(b.cashPaidIns || 0)}`
            + ` = ${formatRp(res.expectedEndingCash)}`,
            'info');
        showToast(
            diff === 0 ? 'Kas pas.'
                       : (diff > 0 ? `Kas LEBIH ${formatRp(diff)}` : `Kas KURANG ${formatRp(Math.abs(diff))}`),
            diff === 0 ? 'success' : 'warning');

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

    // Satu panggilan untuk setelan + sesi kas + pemberitahuan, bukan tiga
    // terpisah. Isi cache dipakai lebih dulu supaya kerangka halaman langsung
    // terisi; penyegaran jalan di belakang.
    if (token) {
        try {
            const boot = await muatBootstrap();
            const paperBadge = document.getElementById('topbar-paper-size');
            if (paperBadge && boot.settings) {
                paperBadge.innerHTML = `<i class="fas fa-receipt"></i> ${boot.settings.RECEIPT_PAPER_SIZE || '58mm'}`;
            }
        } catch (e) {
            console.error('Bootstrap gagal:', e);
        }
    }

    hideBrowserPrintHintIfBridged();
});

/* ======================================================================
   Pemberitahuan

   Isinya dihitung server dari keadaan data sekarang, bukan riwayat kejadian.
   Konsekuensinya menyenangkan: peringatan hilang sendiri begitu masalahnya
   beres, dan tidak ada daftar "sudah dibaca" yang harus diurus.
   ====================================================================== */
let notifTimer = null;

function gambarNotifikasi(data) {
    const dot = document.getElementById('notif-dot');
    const body = document.getElementById('notif-body');
    if (!dot || !body) return;

    dot.style.display = data.count > 0 ? 'block' : 'none';
    // Titik merah hanya untuk yang mendesak; kalau semua hal memerahkan
    // lonceng, orang berhenti melihatnya.
    dot.style.background = data.urgent > 0 ? 'var(--color-danger)' : 'var(--color-warning)';

    body.innerHTML = data.items.length
        ? data.items.map(n => `
            <div class="notif-item ${n.level}">
                <i class="fas fa-${n.icon} notif-ico"></i>
                <div>
                    <strong>${n.title}</strong>
                    <span>${n.body}</span>
                    ${n.link ? `<a href="${n.link}">Buka &rarr;</a>` : ''}
                </div>
            </div>`).join('')
        : '<div class="notif-empty">Tidak ada yang perlu ditindaklanjuti.</div>';
}

async function muatNotifikasi() {
    const body = document.getElementById('notif-body');
    if (!body) return;
    try {
        gambarNotifikasi(await apiFetch('/notifications'));
    } catch (e) {
        body.innerHTML = '<div class="notif-empty">Gagal memuat pemberitahuan.</div>';
    }
}

function toggleNotifPanel() {
    const p = document.getElementById('notif-panel');
    if (!p) return;
    const buka = p.style.display === 'none';
    p.style.display = buka ? 'block' : 'none';
    if (buka) muatNotifikasi();
}

// Klik di luar panel menutupnya; tanpa ini panel menggantung dan terasa macet.
document.addEventListener('click', (e) => {
    const wrap = document.querySelector('.notif-wrap');
    const p = document.getElementById('notif-panel');
    if (wrap && p && !wrap.contains(e.target)) p.style.display = 'none';
});

document.addEventListener('DOMContentLoaded', () => {
    if (!document.getElementById('notif-bell')) return;
    // 3 menit: cukup cepat untuk stok habis, cukup jarang untuk tidak
    // membebani sambungan Tailscale yang dipakai kasir.
    notifTimer = setInterval(() => {
        if (document.visibilityState === 'visible') muatNotifikasi();
    }, 180000);
});

/* Rangka pemuatan: menahan tinggi baris supaya isi tidak melompat saat data
   datang. Lompatan itu yang paling terasa sebagai "tidak halus". */
function skeletonRows(kolom, baris = 5) {
    let html = '';
    for (let i = 0; i < baris; i++) {
        html += '<tr>' + `<td><div class="skeleton skeleton-row"></div></td>`.repeat(kolom) + '</tr>';
    }
    return html;
}

/* ======================================================================
   Navigasi terasa cepat

   Aplikasi ini memuat halaman penuh setiap klik menu (Jinja, server-rendered).
   Mengubahnya jadi SPA berisiko: tiap halaman punya <script> inline yang
   mendeklarasikan let/const di lingkup global, jadi menukar isi halaman tanpa
   reload akan menabrakkan deklarasi antar halaman.

   Jadi yang dikerjakan di sini bukan menghapus reload-nya, tapi menghapus
   ongkosnya: aset diunduh sekali (cache immutable + gzip di sisi server),
   setelan disimpan di sessionStorage, tiga panggilan kerangka disatukan jadi
   satu, halaman berikutnya diambil lebih dulu saat kursor menyentuh menunya,
   dan ada bilah progres supaya jeda tidak terasa mati.
   ====================================================================== */

const BOOT_KEY = 'arunika_boot_v1';

/* Setelan hampir tidak pernah berubah dalam satu sesi kerja. Menyimpannya di
   sessionStorage menghapus satu perjalanan bolak-balik dari SETIAP halaman. */
function bacaBootCache() {
    try {
        const j = sessionStorage.getItem(BOOT_KEY);
        return j ? JSON.parse(j) : null;
    } catch (e) { return null; }
}

function simpanBootCache(data) {
    try { sessionStorage.setItem(BOOT_KEY, JSON.stringify(data)); } catch (e) { /* penuh/private mode */ }
}

function hapusBootCache() {
    try { sessionStorage.removeItem(BOOT_KEY); } catch (e) {}
    cachedStoreSettings = null;
}

/*
 * Satu panggilan untuk setelan + sesi kas + pemberitahuan.
 * Isi cache dipakai lebih dulu supaya kerangka halaman langsung terisi, lalu
 * disegarkan di belakang -- pengguna tidak menunggu jaringan untuk melihat
 * nama toko dan status sesi.
 */
async function muatBootstrap({ pakaiCache = true } = {}) {
    if (pakaiCache) {
        const c = bacaBootCache();
        if (c) {
            cachedStoreSettings = c.settings || null;
            terapkanBootstrap(c, { dariCache: true });
            // Segarkan di belakang, jangan ditunggu.
            muatBootstrap({ pakaiCache: false }).catch(() => {});
            return c;
        }
    }
    const data = await apiFetch('/bootstrap');
    if (data.settings) {
        // Selaraskan alias pajak seperti getStoreSettings().
        if (data.settings.TAX_PERCENT) data.settings.TAX_PERCENTAGE = data.settings.TAX_PERCENT;
        else if (data.settings.TAX_PERCENTAGE) data.settings.TAX_PERCENT = data.settings.TAX_PERCENTAGE;
        cachedStoreSettings = data.settings;
    }
    simpanBootCache(data);
    terapkanBootstrap(data, { dariCache: false });
    return data;
}

function terapkanBootstrap(data, { dariCache }) {
    // Pemberitahuan dari cache bisa basi; tampilkan tapi jangan hitung sebagai
    // kebenaran terkini -- penyegaran di belakang akan memperbaikinya.
    if (data.notifications) gambarNotifikasi(data.notifications);
    gambarPillSesi(data.currentShift, data.cashSessionEnabled !== false);
    void dariCache;
}

/* Bilah progres tipis di puncak halaman. Reload halaman penuh tetap ada, tapi
   jeda yang disertai indikator terasa jauh lebih pendek daripada jeda hening. */
function mulaiProgres() {
    let bar = document.getElementById('nav-progress');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'nav-progress';
        document.body.appendChild(bar);
    }
    bar.className = 'nav-progress running';
}

/*
 * Ambil halaman tujuan begitu kursor menyentuh menunya. Saat pengguna benar-
 * benar mengklik, HTML-nya sudah ada di cache browser.
 *
 * Hanya GET, hanya tautan internal, dan sekali per URL. rel=prefetch dipilih
 * karena browser yang memberi prioritas rendah -- tidak mengganggu permintaan
 * yang sedang berjalan.
 */
const sudahDiprefetch = new Set();

function prefetchHalaman(url) {
    if (!url || sudahDiprefetch.has(url)) return;
    sudahDiprefetch.add(url);
    const l = document.createElement('link');
    l.rel = 'prefetch';
    l.href = url;
    document.head.appendChild(l);
}

function pasangNavigasiCepat() {
    const internal = (a) => {
        if (!a || a.target === '_blank' || a.hasAttribute('download')) return null;
        const href = a.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')
            || href.startsWith('mailto:') || href.startsWith('tel:')) return null;
        try {
            const u = new URL(a.href, location.href);
            if (u.origin !== location.origin) return null;
            if (u.pathname === location.pathname) return null;
            return u.href;
        } catch (e) { return null; }
    };

    // Prefetch saat kursor/sentuhan menyentuh tautan.
    ['mouseover', 'touchstart'].forEach(ev => {
        document.addEventListener(ev, (e) => {
            const a = e.target.closest && e.target.closest('a');
            const url = internal(a);
            if (url) prefetchHalaman(url);
        }, { passive: true, capture: true });
    });

    // Bilah progres saat benar-benar berpindah.
    document.addEventListener('click', (e) => {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
        if (internal(e.target.closest && e.target.closest('a'))) mulaiProgres();
    }, { capture: true });

    // Kembali dari cache riwayat: sembunyikan bilahnya lagi.
    window.addEventListener('pageshow', () => {
        const bar = document.getElementById('nav-progress');
        if (bar) bar.className = 'nav-progress';
    });
}

document.addEventListener('DOMContentLoaded', pasangNavigasiCepat);
