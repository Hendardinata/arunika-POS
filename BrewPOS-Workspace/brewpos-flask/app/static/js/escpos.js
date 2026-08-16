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

    /* Selalu dengan awalan "Rp" -- di kertas, angka tanpa satuan bikin ragu. */
    function rupiah(n) {
        var v = Math.round(Number(n) || 0);
        var sign = v < 0 ? '-' : '';
        return sign + 'Rp ' + Math.abs(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
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
     * Susun struk sebagai daftar baris.
     *
     * Ini satu-satunya tempat tata letak struk ditentukan. Byte printer dan
     * pratinjau HTML sama-sama dibuat dari daftar ini, supaya keduanya tidak
     * pernah lagi berbeda bentuk.
     *
     * Tiap baris: { t: teks, a: 'l'|'c', s: 'n'|'d'|'t', b: tebal }
     * Baris khusus: { feed: n } dan { cut: true }
     */
    function buildReceiptLines(txData, info, opts) {
        info = info || {};
        opts = opts || {};
        var cols = opts.cols || 32;
        var out = [];
        var add = function (t, a, s, bold) { out.push({ t: t, a: a || 'l', s: s || 'n', b: !!bold }); };

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

        // --- Kepala ---
        add(info.STORE_NAME || 'ARUNIKA COFFEE', 'c', 'd', true);
        if (info.TAGLINE) add(info.TAGLINE, 'c');
        if (info.STORE_ADDRESS) {
            wrap(info.STORE_ADDRESS, cols).forEach(function (l) { add(l, 'c'); });
        }
        if (info.STORE_PHONE) add('Telp: ' + info.STORE_PHONE, 'c');
        if (info.STORE_INSTAGRAM) add('IG: ' + info.STORE_INSTAGRAM, 'c');

        add(line('=', cols));

        // --- Identitas transaksi ---
        add(pair('No', txCode, cols));
        add(pair('Waktu', dateStr, cols));
        add(pair('Kasir', opts.cashierName || 'Kasir', cols));
        add(pair('Member', custName, cols));
        if (custType === 'EMPLOYEE') add(pair('Tipe', 'KARYAWAN', cols));
        add(pair('Bayar', tx.paymentMethod || txData.paymentMethod || 'CASH', cols));
        add(line('-', cols));

        // --- Item ---
        var totalItemDiscount = 0;
        if (items.length) {
            items.forEach(function (item) {
                var name = item.menu ? item.menu.name : (item.name || 'Menu #' + (item.menuId || ''));
                var qty = item.quantity || 1;
                var price = item.price || 0;
                var disc = (item.discountAmount || 0) * qty;
                totalItemDiscount += disc;

                wrap(name, cols).forEach(function (l) { add(l); });
                add(pair('  ' + qty + ' x ' + rupiah(price), rupiah(price * qty), cols));
                if (disc > 0) add(pair('  Potongan', rupiah(-disc), cols));
            });
        } else {
            add(pair('1 x Transaksi Menu', rupiah(tx.totalAmount || 0), cols));
        }

        add(line('-', cols));

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

        add(pair('Subtotal', rupiah(grossBeforeDiscount), cols));
        if (totalItemDiscount > 0) add(pair('Diskon Item', rupiah(-totalItemDiscount), cols));
        if (orderDiscount > 0) add(pair('Diskon Order', rupiah(-orderDiscount), cols));
        if (taxAmount > 0) add(pair('Termasuk PPN', rupiah(taxAmount), cols));

        add(line('=', cols));
        add(pair('TOTAL', rupiah(totalAmount), cols), 'l', 't', true);

        if (cashTendered >= totalAmount && (tx.paymentMethod || 'CASH') === 'CASH') {
            add(pair('Tunai', rupiah(cashTendered), cols));
            add(pair('Kembali', rupiah(changeAmount), cols));
        }
        if (pointsEarned > 0) {
            add(line('-', cols));
            add(pair('Poin didapat', '+' + pointsEarned, cols));
            if (customerObj && customerObj.points !== undefined) {
                add(pair('Total poin', String(customerObj.points), cols));
            }
        }

        // --- Kaki ---
        out.push({ feed: 1 });
        if (info.RECEIPT_FOOTER) {
            wrap(info.RECEIPT_FOOTER, cols).forEach(function (l) { add(l, 'c'); });
        }
        add('Simpan struk ini', 'c');
        add('sebagai bukti pembayaran', 'c');

        // Ruang sobek: printer tanpa cutter butuh kertas maju agar teks terakhir
        // lolos dari kepala cetak.
        out.push({ feed: 4 });
        if (opts.cut) out.push({ cut: true });

        return out;
    }

    /** Daftar baris -> byte ESC/POS. */
    function linesToBytes(lines) {
        var b = new Builder();
        var align = 'l', size = 'n', bold = false;
        b.raw(CMD.INIT).raw(CMD.CODEPAGE_437);

        // Kembalikan mode ke normal; dipanggil sebelum memotong kertas dan di akhir
        // supaya perintah potong benar-benar jadi byte terakhir.
        var resetState = function () {
            if (align !== 'l') { b.raw(CMD.ALIGN_LEFT); align = 'l'; }
            if (size !== 'n') { b.raw(CMD.SIZE_NORMAL); size = 'n'; }
            if (bold) { b.raw(CMD.BOLD_OFF); bold = false; }
        };

        lines.forEach(function (l) {
            if (l.feed) { b.feed(l.feed); return; }
            if (l.cut) { resetState(); b.raw(CMD.CUT_PARTIAL); return; }

            if (l.a !== align) {
                b.raw(l.a === 'c' ? CMD.ALIGN_CENTER : CMD.ALIGN_LEFT);
                align = l.a;
            }
            if (l.s !== size) {
                b.raw(l.s === 'd' ? CMD.SIZE_DOUBLE : (l.s === 't' ? CMD.SIZE_TALL : CMD.SIZE_NORMAL));
                size = l.s;
            }
            if (l.b !== bold) {
                b.raw(l.b ? CMD.BOLD_ON : CMD.BOLD_OFF);
                bold = l.b;
            }
            b.ln(l.t);
        });

        resetState();
        return new Uint8Array(b.bytes);
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /**
     * Daftar baris -> HTML monospace. Bentuknya sengaja dibuat sama persis dengan
     * yang keluar di kertas, jadi pratinjau di layar = hasil cetak.
     */
    function linesToHtml(lines) {
        var html = lines.map(function (l) {
            if (l.cut) return '';
            if (l.feed) return new Array(l.feed + 1).join('<div>&nbsp;</div>');
            var style = 'white-space: pre; font-family: inherit;';
            if (l.a === 'c') style += ' text-align: center;';
            if (l.s === 'd') style += ' font-size: 1.55em; font-weight: 800; line-height: 1.25;';
            else if (l.s === 't') style += ' font-size: 1.15em; line-height: 1.3;';
            if (l.b && l.s !== 'd') style += ' font-weight: 700;';
            return '<div style="' + style + '">' + (escapeHtml(l.t) || '&nbsp;') + '</div>';
        }).join('');
        return '<div class="thermal-receipt-card" id="printable-receipt">' + html + '</div>';
    }

    /** Struk siap kirim ke printer. */
    function buildReceipt(txData, info, opts) {
        return linesToBytes(buildReceiptLines(txData, info, opts));
    }

    /** Struk yang sama, tapi sebagai HTML untuk pratinjau & dialog cetak browser. */
    function buildReceiptHtml(txData, info, opts) {
        return linesToHtml(buildReceiptLines(txData, info, opts));
    }

    /** Struk uji singkat untuk memastikan printer & sambungan bekerja. */
    function buildTestReceiptLines(info, opts) {
        opts = opts || {};
        var cols = opts.cols || 32;
        var out = [];
        var add = function (t, a, s, b) { out.push({ t: t, a: a || 'l', s: s || 'n', b: !!b }); };

        add('TES CETAK', 'c', 'd', true);
        add((info && info.STORE_NAME) || 'ARUNIKA POS', 'c');
        add(line('=', cols));
        add(pair('Lebar kertas', cols + ' kolom', cols));
        add(pair('Waktu', new Date().toLocaleString('id-ID'), cols));
        add(line('-', cols));
        // Penggaris kolom: kalau angka terakhir terpotong, berarti kolomnya kebanyakan.
        var ruler = '';
        for (var i = 1; i <= cols; i++) ruler += (i % 10 === 0) ? String(i / 10) : '.';
        add(ruler);
        add('Kalau baris di atas utuh,');
        add('lebar kertas sudah pas.');
        add(pair('Contoh nominal', rupiah(1250000), cols));
        out.push({ feed: 4 });
        if (opts.cut) out.push({ cut: true });
        return out;
    }

    function buildTestReceipt(info, opts) {
        return linesToBytes(buildTestReceiptLines(info, opts));
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
        buildReceiptHtml: buildReceiptHtml,
        buildReceiptLines: buildReceiptLines,
        buildTestReceipt: buildTestReceipt,
        bytesToBase64: bytesToBase64,
        hasBridge: hasBridge,
        sendToBridge: sendToBridge,
        // diekspor untuk pengujian
        _toAscii: toAscii, _pair: pair, _wrap: wrap, _rupiah: rupiah
    };

    global.EscPos = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
