"""
Kompresi, cache aset, dan panggilan bootstrap.

Ini yang menentukan seberapa cepat halaman terasa lewat Tailscale: aset 131 KB
yang diminta ulang tiap navigasi vs 35 KB yang diunduh sekali. Diuji karena
mudah rusak tanpa terlihat -- satu header keliru dan browser diam-diam kembali
mengunduh semuanya.
"""
import gzip

from app.extensions import db
from app.models.inventory import InventoryItem
from app.models.system_settings import SystemSettings

GZIP = {'Accept-Encoding': 'gzip'}


# --- Kompresi ---------------------------------------------------------------

def test_aset_statis_dikompresi(client):
    r = client.get('/static/js/app.js?v=1', headers=GZIP)
    assert r.status_code == 200
    assert r.headers.get('Content-Encoding') == 'gzip'
    assert 'Accept-Encoding' in (r.headers.get('Vary') or '')


def test_isi_tetap_utuh_setelah_dikompresi(client):
    """Kompresi yang merusak isi jauh lebih buruk daripada tanpa kompresi."""
    asli = client.get('/static/js/app.js?v=1').data
    dikompres = client.get('/static/js/app.js?v=1', headers=GZIP).data
    assert gzip.decompress(dikompres) == asli


def test_kompresi_benar_benar_memangkas(client):
    asli = len(client.get('/static/css/style.css?v=1').data)
    kecil = len(client.get('/static/css/style.css?v=1', headers=GZIP).data)
    assert kecil < asli * 0.5, f'hanya hemat {100 - kecil * 100 // asli}%'


def test_klien_tanpa_gzip_tetap_dilayani(client):
    """Jangan pernah mengirim gzip ke klien yang tidak memintanya."""
    r = client.get('/static/js/app.js?v=1')
    assert r.headers.get('Content-Encoding') is None
    assert b'function' in r.data


def test_json_api_ikut_dikompresi(client, admin_headers):
    h = dict(admin_headers)
    h.update(GZIP)
    r = client.get('/api/menus', headers=h)
    assert r.status_code == 200
    # Balasan kecil tidak dikompresi; yang penting tidak rusak.
    isi = gzip.decompress(r.data) if r.headers.get('Content-Encoding') == 'gzip' else r.data
    assert isi.strip().startswith(b'[') or isi.strip().startswith(b'{')


def test_respons_kecil_tidak_dikompresi(client, admin_headers):
    """Di bawah 1 KB, ongkos header gzip lebih besar dari hematnya."""
    h = dict(admin_headers)
    h.update(GZIP)
    r = client.get('/api/shift/current', headers=h)
    if len(r.data) < 1024:
        assert r.headers.get('Content-Encoding') is None


# --- Cache aset -------------------------------------------------------------

def test_aset_berversi_disimpan_lama(client):
    """
    URL-nya sudah memuat mtime, jadi isinya tidak mungkin berubah tanpa URL
    berubah. Tanpa header ini browser bertanya ulang tiap navigasi.
    """
    cc = client.get('/static/js/app.js?v=1', headers=GZIP).headers.get('Cache-Control')
    assert 'immutable' in cc
    assert 'max-age=31536000' in cc


def test_aset_tanpa_versi_tidak_disimpan_lama(client):
    """Tanpa ?v tidak ada jaminan; menyimpannya setahun akan menyajikan yang basi."""
    cc = client.get('/static/js/app.js').headers.get('Cache-Control')
    assert 'immutable' not in cc
    assert 'max-age=300' in cc


def test_url_aset_membawa_penanda_versi(app):
    """Cache immutable hanya aman kalau URL-nya benar-benar berversi."""
    from flask import url_for
    with app.test_request_context():
        assert 'v=' in url_for('static', filename='js/app.js')


# --- Bootstrap --------------------------------------------------------------

def test_bootstrap_mengembalikan_semua_yang_dibutuhkan_kerangka(client, admin_headers):
    isi = client.get('/api/bootstrap', headers=admin_headers).get_json()
    for kunci in ('settings', 'currentShift', 'notifications', 'cashSessionEnabled'):
        assert kunci in isi, f'{kunci} hilang dari bootstrap'
    assert isinstance(isi['settings'], dict)
    assert 'items' in isi['notifications']


def test_bootstrap_isinya_sama_dengan_endpoint_terpisah(client, app, bean, admin_headers):
    """Menyatukan panggilan tidak boleh mengubah datanya."""
    bean.stock = 0
    db.session.commit()

    boot = client.get('/api/bootstrap', headers=admin_headers).get_json()
    notif = client.get('/api/notifications', headers=admin_headers).get_json()
    shift = client.get('/api/shift/current', headers=admin_headers).get_json()

    assert boot['notifications']['count'] == notif['count']
    assert [n['id'] for n in boot['notifications']['items']] == [n['id'] for n in notif['items']]
    assert boot['currentShift'] == shift['currentShift']


def test_bootstrap_membawa_setelan_yang_dipakai_kerangka(client, app, admin_headers):
    db.session.add(SystemSettings(key='RECEIPT_PAPER_SIZE', value='80mm'))
    db.session.commit()

    isi = client.get('/api/bootstrap', headers=admin_headers).get_json()
    assert isi['settings']['RECEIPT_PAPER_SIZE'] == '80mm'


def test_bootstrap_satu_bagian_gagal_tidak_menjatuhkan_sisanya(client, app, admin_headers, monkeypatch):
    """
    Kerangka halaman tidak boleh kosong hanya karena satu bagian bermasalah --
    itu membuat seluruh aplikasi terlihat rusak padahal cuma lonceng yang gagal.
    """
    def meledak():
        raise RuntimeError('sengaja')

    monkeypatch.setattr('app.routes.notifications._kumpulkan', meledak)
    isi = client.get('/api/bootstrap', headers=admin_headers).get_json()

    assert isi['notifications']['items'] == []
    assert isinstance(isi['settings'], dict) and isi['settings']    # bagian lain tetap terisi


def test_bootstrap_menghormati_sesi_kas_dimatikan(client, app, admin_headers):
    db.session.add(SystemSettings(key='CASH_SESSION_ENABLED', value='0'))
    db.session.commit()

    isi = client.get('/api/bootstrap', headers=admin_headers).get_json()
    assert isi['cashSessionEnabled'] is False
    assert isi['currentShift'] is None


def test_bootstrap_wajib_login(client):
    assert client.get('/api/bootstrap').status_code == 401
