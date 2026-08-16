"""
Jembatan printer di PC kasir (printer_agent.py).

Diuji lewat HTTP sungguhan ke server yang benar-benar berjalan, dengan bagian
win32print diganti tiruan -- mesin uji tidak punya printer, tapi protokolnya
harus tetap benar: CORS, base64, batas ukuran, dan pesan galat yang terbaca.
"""
import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

import printer_agent


@pytest.fixture
def agen(monkeypatch):
    """Server sungguhan di porta bebas, dengan pencetakan dialihkan ke daftar."""
    tercetak = []

    def cetak_palsu(nama, data):
        if nama == 'PRINTER RUSAK':
            raise RuntimeError('Printer sedang offline')
        tercetak.append((nama, data))
        return nama or 'Printer Bawaan'

    monkeypatch.setattr(printer_agent, 'cetak_raw', cetak_palsu)
    monkeypatch.setattr(printer_agent, 'win32print', object())  # anggap pywin32 ada
    printer_agent.Handler.printer = 'POS58 Uji'

    server = HTTPServer(('127.0.0.1', 0), printer_agent.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    alamat = f'http://127.0.0.1:{server.server_port}'
    yield alamat, tercetak
    server.shutdown()


def _kirim(alamat, jalur, muatan=None, method=None):
    data = json.dumps(muatan).encode() if muatan is not None else None
    req = urllib.request.Request(alamat + jalur, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b'{}'), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}'), dict(e.headers)


def test_status_menjawab_siap(agen):
    alamat, _ = agen
    kode, isi, _ = _kirim(alamat, '/status')
    assert kode == 200
    assert isi['ok'] is True and isi['siap'] is True
    assert isi['printer'] == 'POS58 Uji'


def test_status_membawa_header_cors(agen):
    """Halaman POS datang dari origin lain; tanpa CORS browser membuang balasannya."""
    alamat, _ = agen
    _, _, headers = _kirim(alamat, '/status')
    assert headers.get('Access-Control-Allow-Origin') == '*'


def test_preflight_dijawab(agen):
    # Browser mengirim OPTIONS lebih dulu untuk POST ber-Content-Type JSON.
    alamat, _ = agen
    req = urllib.request.Request(alamat + '/print', method='OPTIONS')
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 204
        assert r.headers.get('Access-Control-Allow-Origin') == '*'
        assert 'POST' in r.headers.get('Access-Control-Allow-Methods', '')


def test_byte_struk_sampai_utuh_ke_printer(agen):
    alamat, tercetak = agen
    asli = bytes([0x1B, 0x40]) + 'Arunika Coffee\n'.encode('ascii') + bytes([0x1D, 0x56, 66, 0])

    kode, isi, _ = _kirim(alamat, '/print', {'data': base64.b64encode(asli).decode()})
    assert kode == 200, isi
    assert isi['ok'] is True and isi['bytes'] == len(asli)
    # Byte harus sampai apa adanya -- satu byte meleset, struknya kacau.
    assert tercetak == [('POS58 Uji', asli)]


def test_bisa_menunjuk_printer_lain_per_permintaan(agen):
    alamat, tercetak = agen
    _kirim(alamat, '/print', {'data': base64.b64encode(b'x').decode(), 'printer': 'Printer Dapur'})
    assert tercetak[0][0] == 'Printer Dapur'


def test_base64_rusak_ditolak_dengan_pesan_jelas(agen):
    alamat, tercetak = agen
    kode, isi, _ = _kirim(alamat, '/print', {'data': 'bukan base64!!!'})
    assert kode == 400
    assert 'tidak terbaca' in isi['error']
    assert tercetak == []


def test_data_kosong_ditolak(agen):
    alamat, tercetak = agen
    kode, isi, _ = _kirim(alamat, '/print', {'data': ''})
    assert kode == 400
    assert tercetak == []


def test_kiriman_kelewat_besar_ditolak(agen):
    """Struk terpanjang pun jauh di bawah batas; sisanya sampah atau salah alamat."""
    alamat, tercetak = agen
    besar = base64.b64encode(b'A' * (printer_agent.MAX_BYTES + 1000)).decode()
    kode, isi, _ = _kirim(alamat, '/print', {'data': besar})
    assert kode == 400
    assert 'tidak wajar' in isi['error']
    assert tercetak == []


def test_galat_printer_diteruskan_apa_adanya(agen):
    """Pesan 'Printer sedang offline' harus sampai ke kasir, bukan ditelan."""
    alamat, _ = agen
    kode, isi, _ = _kirim(alamat, '/print',
                          {'data': base64.b64encode(b'x').decode(), 'printer': 'PRINTER RUSAK'})
    assert kode == 500
    assert isi['error'] == 'Printer sedang offline'


def test_jalur_tak_dikenal_menjawab_404(agen):
    alamat, _ = agen
    assert _kirim(alamat, '/apa-saja')[0] == 404
    assert _kirim(alamat, '/kirim', {'data': 'eA=='})[0] == 404


def test_hanya_mendengar_di_localhost():
    """
    Jembatan ini menerima perintah cetak tanpa autentikasi. Selama hanya terikat
    ke 127.0.0.1, hanya halaman di PC itu sendiri yang bisa menjangkaunya.
    """
    import inspect
    sumber = inspect.getsource(printer_agent.main)
    assert "'127.0.0.1'" in sumber, 'jembatan printer tidak boleh terbuka ke jaringan'
