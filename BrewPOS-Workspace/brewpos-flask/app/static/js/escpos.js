/*
 * Penyusun struk ESC/POS untuk printer thermal Bluetooth.
 *
 * Dipakai lewat jembatan aplikasi Android (window.AndroidPrinter). Kalau jembatan
 * tidak ada, pemanggil harus jatuh kembali ke printReceipt() berbasis HTML.
 *
 * Acuan: printer 58mm = 384 dot = 32 karakter per baris pada Font A. Jumlah kolom
 * dan perintah potong kertas dibuat bisa diatur karena tidak semua printer 58mm
 * punya auto-cutter, dan sebagian model memakai lebar kolom berbeda.
 */
(function (global) {
    'use strict';

    var ESC = 0x1B, GS = 0x1D;

    var CMD = {
        INIT: [ESC, 0x40],
        ALIGN_LEFT: [ESC, 0x61, 0],
        ALIGN_CENTER: [ESC, 0x61, 1],
        ALIGN_RIGHT: [ESC, 0x61, 2],
        BOLD_ON: [ESC, 0x45, 1],
        BOLD_OFF: [ESC, 0x45, 0],
        SIZE_NORMAL: [GS, 0x21, 0x00],
        SIZE_DOUBLE: [GS, 0x21, 0x11],   // lebar & tinggi 2x
        SIZE_TALL: [GS, 0x21, 0x01],     // tinggi 2x saja
        // Codepage 437; struk kita sengaja ASCII saja jadi ini cuma penyeragam.
        CODEPAGE_437: [ESC, 0x74, 0x00],
        CUT_PARTIAL: [GS, 0x56, 66, 0x00]
    };

    // Printer 58mm umumnya hanya mengenal ASCII. Tanpa transliterasi, "Caffè"
    // keluar sebagai karakter sampah di kertas.
    var TRANSLIT = {
        'à':'a','á':'a','â':'a','ã':'a','ä':'a','å':'a','è':'e','é':'e','ê':'e','ë':'e',
        'ì':'i','í':'i','î':'i','ï':'i','ò':'o','ó':'o','ô':'o','õ':'o','ö':'o',
        'ù':'u','ú':'u','û':'u','ü':'u','ñ':'n','ç':'c','ý':'y','ÿ':'y',
        '“':'"','”':'"','‘':"'",'’':"'",'–':'-','—':'-','…':'...','×':'x','·':'-',
        '€':'EUR','£':'GBP','°':' der','™':'(TM)','©':'(C)','®':'(R)','•':'*','₹':'Rs'
    };

    function toAscii(text) {
        if (text === null || text === undefined) return '';
        var s = String(text);
        var out = '';
        for (var i = 0; i < s.length; i++) {
            var ch = s[i];
            var lower = ch.toLowerCase();
            if (TRANSLIT[ch] !== undefined) {
                out += TRANSLIT[ch];
            } else if (TRANSLIT[lower] !== undefined) {
                var rep = TRANSLIT[lower];
                out += (ch === lower) ? rep : rep.toUpperCase();
            } else if (ch.charCodeAt(0) < 128) {
                out += ch;
            } else {
                out += '?';
            }
        }
        return out;
    }

    function rupiah(n) {
        var v = Math.round(Number(n) || 0);
        var sign = v < 0 ? '-' : '';
        return sign + Math.abs(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    /* Bungkus teks pada batas kolom, memotong kata hanya kalau katanya memang
       lebih panjang dari satu baris. */
    function wrap(text, cols) {
        var words = toAscii(text).split(/\s+/).filter(Boolean);
        var lines = [], line = '';
        words.forEach(function (w) {
            while (w.length > cols) {
                if (line) { lines.push(line); line = ''; }
                lines.push(w.slice(0, cols));
                w = w.slice(cols);
            }
            if (!line) line = w;
            else if ((line + ' ' + w).length <= cols) line += ' ' + w;
            else { lines.push(line); line = w; }
        });
        if (line) lines.push(line);
        return lines.length ? lines : [''];
    }

    /* Kiri-kanan dalam satu baris. Kalau tidak muat, label dipotong lebih dulu
       supaya angkanya tidak pernah hilang. */
    function pair(left, right, cols) {
        var l = toAscii(left), r = toAscii(right);
        var space = cols - r.length - 1;
        if (space < 1) return r.slice(-cols);
        if (l.length > space) l = l.slice(0, space);
        return l + new Array(cols - l.length - r.length + 1).join(' ') + r;
    }

    function center(text, cols) {
        var t = toAscii(text);
        if (t.length >= cols) return t.slice(0, cols);
        var pad = Math.floor((cols - t.length) / 2);
        return new Array(pad + 1).join(' ') + t;
    }

    function line(ch, cols) {
        return new Array(cols + 1).join(ch);
    }

    function Builder(cols) {
        this.cols = cols;
        this.bytes = [];
    }
    Builder.prototype.raw = function (arr) {
        for (var i = 0; i < arr.length; i++) this.bytes.push(arr[i]);
        return this;
    };
    Builder.prototype.text = function (str) {
        var s = toAscii(str);
        for (var i = 0; i < s.length; i++) this.bytes.push(s.charCodeAt(i) & 0xFF);
        return this;
    };
    Builder.prototype.ln = function (str) {
        if (str !== undefined) this.text(str);
        this.bytes.push(0x0A);
        return this;
    };
    Builder.prototype.feed = function (n) {
        for (var i = 0; i < (n || 1); i++) this.bytes.push(0x0A);
        return this;
    };

    /**
     * Susun struk lengkap.
     * @param txData payload checkout ({transaction, customer, cashReceived}) atau objek transaksi
     * @param info   pengaturan toko (STORE_NAME, TAGLINE, ...)
     * @param opts   { cols, cut, cashierName }
     * @returns {Uint8Array}
     */
    function buildReceipt(txData, info, opts) {
        info = info || {};
        opts = opts || {};
        var cols = opts.cols || 32;
        var b = new Builder(cols);

        var tx = txData.transaction || txData;
        var items = tx.items || txData.items || [];
        var d = new Date(tx.createdAt || txData.createdAt || Date.now());
        var pad2 = function (n) { return (n < 10 ? '0' : '') + n; };
        var dateStr = pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear() +
                      ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());

        var txCode = tx.transactionCode || tx.code || txData.transactionCode || txData.code || '-';
        var customerObj = tx.customer || txData.customer;
        var custName = customerObj ? customerObj.nickname : (tx.nickname || txData.nickname || 'Guest');
        var custType = customerObj ? (customerObj.customerType || 'REGULAR') : 'REGULAR';

        b.raw(CMD.INIT).raw(CMD.CODEPAGE_437);

        // --- Kepala ---
        b.raw(CMD.ALIGN_CENTER).raw(CMD.SIZE_DOUBLE).raw(CMD.BOLD_ON);
        b.ln(info.STORE_NAME || 'ARUNIKA COFFEE');
        b.raw(CMD.BOLD_OFF).raw(CMD.SIZE_NORMAL);
        if (info.TAGLINE) b.ln(center(info.TAGLINE, cols));
        if (info.STORE_ADDRESS) {
            wrap(info.STORE_ADDRESS, cols).forEach(function (l) { b.ln(center(l, cols)); });
        }
        if (info.STORE_PHONE) b.ln(center('Telp: ' + info.STORE_PHONE, cols));
        if (info.STORE_INSTAGRAM) b.ln(center('IG: ' + info.STORE_INSTAGRAM, cols));

        b.raw(CMD.ALIGN_LEFT);
        b.ln(line('=', cols));

        // --- Identitas transaksi ---
        b.ln(pair('No', txCode, cols));
        b.ln(pair('Waktu', dateStr, cols));
        b.ln(pair('Kasir', opts.cashierName || 'Kasir', cols));
        b.ln(pair('Member', custName, cols));
        if (custType === 'EMPLOYEE') b.ln(pair('Tipe', 'KARYAWAN', cols));
        b.ln(pair('Bayar', tx.paymentMethod || txData.paymentMethod || 'CASH', cols));
        b.ln(line('-', cols));

        // --- Item ---
        var totalItemDiscount = 0;
        if (items.length) {
            items.forEach(function (item) {
                var name = item.menu ? item.menu.name : (item.name || 'Menu #' + (item.menuId || ''));
                var qty = item.quantity || 1;
                var price = item.price || 0;
                var disc = (item.discountAmount || 0) * qty;
                totalItemDiscount += disc;

                wrap(name, cols).forEach(function (l) { b.ln(l); });
                b.ln(pair('  ' + qty + ' x ' + rupiah(price), rupiah(price * qty), cols));
                if (disc > 0) b.ln(pair('  Potongan', '-' + rupiah(disc), cols));
            });
        } else {
            b.ln(pair('1 x Transaksi Menu', rupiah(tx.totalAmount || 0), cols));
        }

        b.ln(line('-', cols));

        // --- Ringkasan uang ---
        var totalAmount = (tx.totalAmount !== undefined) ? tx.totalAmount : (txData.totalAmount || 0);
        var orderDiscount = (tx.discountAmount !== undefined) ? tx.discountAmount : (txData.discountAmount || 0);
        var taxAmount = (tx.taxAmount !== undefined) ? tx.taxAmount : (txData.taxAmount || 0);
        // Harga menu sudah termasuk pajak, jadi subtotal yang jujur adalah bruto
        // sebelum diskon -- sama dengan perhitungan di struk HTML.
        var grossBeforeDiscount = totalAmount + orderDiscount + totalItemDiscount;
        var cashTendered = txData.cashReceived || tx.cashReceived || totalAmount;
        var changeAmount = (cashTendered > totalAmount) ? (cashTendered - totalAmount) : 0;
        var pointsEarned = (tx.pointsEarned !== undefined) ? tx.pointsEarned : (txData.pointsEarned || 0);

        b.ln(pair('Subtotal', rupiah(grossBeforeDiscount), cols));
        if (totalItemDiscount > 0) b.ln(pair('Diskon Item', '-' + rupiah(totalItemDiscount), cols));
        if (orderDiscount > 0) b.ln(pair('Diskon Order', '-' + rupiah(orderDiscount), cols));
        if (taxAmount > 0) b.ln(pair('Termasuk PPN', rupiah(taxAmount), cols));

        b.ln(line('=', cols));
        b.raw(CMD.SIZE_TALL).raw(CMD.BOLD_ON);
        b.ln(pair('TOTAL', rupiah(totalAmount), cols));
        b.raw(CMD.BOLD_OFF).raw(CMD.SIZE_NORMAL);

        if (cashTendered >= totalAmount && (tx.paymentMethod || 'CASH') === 'CASH') {
            b.ln(pair('Tunai', rupiah(cashTendered), cols));
            b.ln(pair('Kembali', rupiah(changeAmount), cols));
        }
        if (pointsEarned > 0) {
            b.ln(line('-', cols));
            b.ln(pair('Poin didapat', '+' + pointsEarned, cols));
            if (customerObj && customerObj.points !== undefined) {
                b.ln(pair('Total poin', String(customerObj.points), cols));
            }
        }

        // --- Kaki ---
        b.feed(1).raw(CMD.ALIGN_CENTER);
        if (info.RECEIPT_FOOTER) {
            wrap(info.RECEIPT_FOOTER, cols).forEach(function (l) { b.ln(l); });
        }
        b.ln('Simpan struk ini');
        b.ln('sebagai bukti pembayaran');
        b.raw(CMD.ALIGN_LEFT);

        // Ruang sobek: printer tanpa cutter butuh kertas maju agar teks terakhir
        // lolos dari kepala cetak.
        b.feed(4);
        if (opts.cut) b.raw(CMD.CUT_PARTIAL);

        return new Uint8Array(b.bytes);
    }

    /** Struk uji singkat untuk memastikan printer & sambungan bekerja. */
    function buildTestReceipt(info, opts) {
        opts = opts || {};
        var cols = opts.cols || 32;
        var b = new Builder(cols);
        b.raw(CMD.INIT).raw(CMD.CODEPAGE_437);
        b.raw(CMD.ALIGN_CENTER).raw(CMD.SIZE_DOUBLE).raw(CMD.BOLD_ON);
        b.ln('TES CETAK');
        b.raw(CMD.BOLD_OFF).raw(CMD.SIZE_NORMAL);
        b.ln(center((info && info.STORE_NAME) || 'ARUNIKA POS', cols));
        b.raw(CMD.ALIGN_LEFT);
        b.ln(line('=', cols));
        b.ln(pair('Lebar kertas', cols + ' kolom', cols));
        b.ln(pair('Waktu', new Date().toLocaleString('id-ID'), cols));
        b.ln(line('-', cols));
        // Penggaris kolom: kalau angka terakhir terpotong, berarti kolomnya kebanyakan.
        var ruler = '';
        for (var i = 1; i <= cols; i++) ruler += (i % 10 === 0) ? String(i / 10) : '.';
        b.ln(ruler);
        b.ln('Kalau baris di atas utuh,');
        b.ln('lebar kertas sudah pas.');
        b.feed(4);
        if (opts.cut) b.raw(CMD.CUT_PARTIAL);
        return new Uint8Array(b.bytes);
    }

    function bytesToBase64(bytes) {
        var bin = '';
        for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        if (typeof btoa === 'function') return btoa(bin);
        return Buffer.from(bin, 'binary').toString('base64'); // node (uji otomatis)
    }

    /** Jembatan aplikasi Android tersedia? */
    function hasBridge() {
        return typeof global.AndroidPrinter !== 'undefined' &&
               global.AndroidPrinter !== null &&
               typeof global.AndroidPrinter.print === 'function';
    }

    /** Kirim ke printer lewat jembatan. Returns true kalau terkirim. */
    function sendToBridge(bytes) {
        if (!hasBridge()) return false;
        global.AndroidPrinter.print(bytesToBase64(bytes));
        return true;
    }

    var api = {
        buildReceipt: buildReceipt,
        buildTestReceipt: buildTestReceipt,
        bytesToBase64: bytesToBase64,
        hasBridge: hasBridge,
        sendToBridge: sendToBridge,
        // diekspor untuk pengujian
        _toAscii: toAscii, _pair: pair, _wrap: wrap, _center: center, _rupiah: rupiah
    };

    global.EscPos = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
