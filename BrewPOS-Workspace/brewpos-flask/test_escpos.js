/*
 * Uji penyusun struk ESC/POS.
 *
 *     node test_escpos.js
 *
 * Memeriksa hal-hal yang benar-benar bikin struk rusak di kertas: baris melebihi
 * lebar kertas, karakter non-ASCII, angka yang terpotong, dan urutan perintah.
 */
const assert = require('assert');
const EscPos = require('./app/static/js/escpos.js');

const COLS = 32;
let pass = 0;
const fails = [];

function check(label, fn) {
    try { fn(); console.log('  OK   ' + label); pass++; }
    catch (e) { console.log(' FAIL  ' + label + '\n         ' + e.message); fails.push(label); }
}

const store = {
    STORE_NAME: 'RuA',
    TAGLINE: 'Rumah Bersua Caffè',
    STORE_ADDRESS: 'Jl. Merpati No 36, Cakranegara Bar., Kec. Cakranegara, Kota Mataram',
    STORE_PHONE: '081997885072',
    STORE_INSTAGRAM: '@RumahBersuacaffe',
    RECEIPT_FOOTER: 'Terima kasih atas kunjungannya!',
    TAX_PERCENT: '11'
};

const tx = {
    transaction: {
        transactionCode: 'TR20260815000001',
        createdAt: '2026-08-15T10:30:00',
        totalAmount: 68000,
        discountAmount: 5000,
        taxAmount: 6739,
        pointsEarned: 68,
        paymentMethod: 'CASH',
        items: [
            { menu: { name: 'Kopi Susu Gula Aren' }, quantity: 2, price: 25000, discountAmount: 0 },
            { menu: { name: 'Butter Croissant Spesial Panjang Sekali Namanya' }, quantity: 1, price: 23000, discountAmount: 2500 }
        ]
    },
    customer: { nickname: 'Budi', customerType: 'REGULAR', points: 168 },
    cashReceived: 100000
};

/*
 * Pisahkan teks dari perintah. Tidak bisa sekadar membuang byte kontrol: parameter
 * perintah ESC/POS sering berupa huruf ASCII biasa (ESC a 1 -> 'a'), sehingga ikut
 * terbaca sebagai teks dan lebar baris jadi salah ukur.
 */
function extractLines(bytes) {
    const PARAM_LEN = { 0x40: 0, 0x74: 1, 0x61: 1, 0x45: 1, 0x64: 1, 0x21: 1 }; // setelah ESC/GS
    const lines = [];
    let cur = '';
    for (let i = 0; i < bytes.length; i++) {
        const b = bytes[i];
        if (b === 0x1B || b === 0x1D) {
            const cmd = bytes[i + 1];
            if (b === 0x1D && cmd === 0x56) { i += 3; continue; }      // GS V m n (potong)
            const n = PARAM_LEN[cmd];
            i += 1 + (n === undefined ? 0 : n);
            continue;
        }
        if (b === 0x0A) { lines.push(cur); cur = ''; continue; }
        cur += String.fromCharCode(b);
    }
    if (cur) lines.push(cur);
    return lines;
}

const bytes = EscPos.buildReceipt(tx, store, { cols: COLS, cut: true, cashierName: 'kasir' });
const text = Buffer.from(bytes).toString('latin1');
const printable = extractLines(bytes);

console.log('--- Pratinjau struk ---');
printable.forEach(l => console.log('|' + l + '|'));
console.log('--- ' + bytes.length + ' byte ---\n');

check('diawali perintah INIT (ESC @)', () => {
    assert.strictEqual(bytes[0], 0x1B);
    assert.strictEqual(bytes[1], 0x40);
});

check('diakhiri perintah potong kertas', () => {
    const tail = Array.from(bytes.slice(-4));
    assert.deepStrictEqual(tail, [0x1D, 0x56, 66, 0x00]);
});

check('tanpa perintah potong bila cutter dimatikan', () => {
    const b = EscPos.buildReceipt(tx, store, { cols: COLS, cut: false });
    const tail = Array.from(b.slice(-4));
    assert.notDeepStrictEqual(tail, [0x1D, 0x56, 66, 0x00]);
});

check('tidak ada baris melebihi lebar kertas', () => {
    const tooLong = printable.filter(l => l.length > COLS);
    assert.strictEqual(tooLong.length, 0, 'baris kepanjangan: ' + JSON.stringify(tooLong));
});

check('semua byte ASCII (aman untuk codepage printer)', () => {
    const bad = Array.from(bytes).filter(b => b > 0x7F);
    assert.strictEqual(bad.length, 0, 'byte non-ASCII: ' + bad);
});

check('"Caffè" ditransliterasi jadi "Caffe"', () => {
    assert.ok(text.includes('Caffe'), 'tagline hilang/rusak');
    assert.ok(!text.includes('è'));
});

check('nama menu panjang dibungkus, bukan dipotong', () => {
    assert.ok(text.includes('Butter Croissant Spesial'), 'awal nama hilang');
    assert.ok(text.includes('Namanya'), 'akhir nama hilang');
});

check('total tercetak dan rata kanan', () => {
    const l = printable.find(x => x.startsWith('TOTAL'));
    assert.ok(l, 'baris TOTAL tidak ada');
    assert.ok(l.endsWith('68.000'), 'nominal tidak rata kanan: |' + l + '|');
});

check('subtotal = total + semua diskon (kolom nyambung)', () => {
    const l = printable.find(x => x.startsWith('Subtotal'));
    assert.ok(l.endsWith('75.500'), 'subtotal salah: |' + l + '|');  // 68.000 + 5.000 + 2.500
});

check('tunai & kembalian tercetak', () => {
    assert.ok(printable.some(l => l.startsWith('Tunai') && l.endsWith('100.000')));
    assert.ok(printable.some(l => l.startsWith('Kembali') && l.endsWith('32.000')));
});

check('poin tercetak', () => {
    assert.ok(printable.some(l => l.includes('+68')), 'poin transaksi hilang');
    assert.ok(printable.some(l => l.includes('168')), 'total poin hilang');
});

check('non-tunai tidak mencetak baris kembalian', () => {
    const qris = JSON.parse(JSON.stringify(tx));
    qris.transaction.paymentMethod = 'QRIS';
    delete qris.cashReceived;
    const t = Buffer.from(EscPos.buildReceipt(qris, store, { cols: COLS })).toString('latin1');
    assert.ok(!t.includes('Kembali'), 'baris kembalian muncul di transaksi non-tunai');
});

check('transaksi tanpa item tetap tercetak', () => {
    const kosong = { transaction: { totalAmount: 15000, items: [] } };
    const t = Buffer.from(EscPos.buildReceipt(kosong, store, { cols: COLS })).toString('latin1');
    assert.ok(t.includes('15.000'));
});

check('lebar 80mm (48 kolom) juga rapi', () => {
    const lines = extractLines(EscPos.buildReceipt(tx, store, { cols: 48 }));
    assert.strictEqual(lines.filter(l => l.length > 48).length, 0,
        'baris kepanjangan: ' + JSON.stringify(lines.filter(l => l.length > 48)));
    assert.ok(lines.some(l => l.startsWith('TOTAL') && l.endsWith('68.000')));
});

check('label dipotong, nominal tidak pernah hilang', () => {
    const l = EscPos._pair('Label yang sangat panjang sekali melebihi kertas', '999.999', COLS);
    assert.strictEqual(l.length, COLS);
    assert.ok(l.endsWith('999.999'));
});

check('format rupiah', () => {
    assert.strictEqual(EscPos._rupiah(0), '0');
    assert.strictEqual(EscPos._rupiah(1000), '1.000');
    assert.strictEqual(EscPos._rupiah(1234567), '1.234.567');
    assert.strictEqual(EscPos._rupiah(-2500), '-2.500');
});

check('struk tes memuat penggaris kolom yang utuh', () => {
    const lines = extractLines(EscPos.buildTestReceipt(store, { cols: COLS }));
    const ruler = lines.find(l => /^[.\d]{10,}$/.test(l));
    assert.ok(ruler, 'penggaris tidak ada');
    assert.strictEqual(ruler.length, COLS);
    assert.strictEqual(ruler[9], '1', 'penanda kolom 10 salah');
    assert.strictEqual(ruler[29], '3', 'penanda kolom 30 salah');
});

check('base64 bolak-balik utuh', () => {
    const b64 = EscPos.bytesToBase64(bytes);
    assert.strictEqual(Buffer.from(b64, 'base64').length, bytes.length);
    assert.ok(Buffer.from(b64, 'base64').equals(Buffer.from(bytes)));
});

check('tanpa jembatan Android, sendToBridge menolak dengan sopan', () => {
    assert.strictEqual(EscPos.hasBridge(), false);
    assert.strictEqual(EscPos.sendToBridge(bytes), false);
});

console.log('\n' + (fails.length ? `GAGAL (${fails.length}): ${fails.join(', ')}` : `SEMUA LULUS (${pass} pemeriksaan)`));
process.exit(fails.length ? 1 : 0);
