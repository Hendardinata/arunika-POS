"""
Rem percobaan login. Yang diuji: tebakan beruntun tertahan, kasir yang akhirnya
ingat passwordnya tidak ikut terkunci, dan penyerang dari satu IP tidak bisa
mengunci akun kasir lain.
"""
import pytest

from app.services import login_guard


@pytest.fixture(autouse=True)
def clean_guard():
    login_guard.reset_all()
    yield
    login_guard.reset_all()


def _login(client, username, password, ip='10.0.0.1'):
    return client.post(
        '/api/auth/login',
        json={'username': username, 'password': password},
        headers={'X-Forwarded-For': ip},
    )


def test_percobaan_beruntun_akhirnya_tertahan(client):
    for _ in range(login_guard.MAX_FAILURES):
        assert _login(client, 'superadmin', 'salah').status_code == 401

    blocked = _login(client, 'superadmin', 'salah')
    assert blocked.status_code == 429
    assert 'Terlalu banyak' in blocked.get_json()['error']

    # Password yang benar pun ikut tertahan selama jendela penguncian -- kalau
    # tidak, penyerang tinggal menyelipkan tebakan benar di antara yang salah.
    assert _login(client, 'superadmin', '12qwaszx').status_code == 429


def test_login_berhasil_menghapus_rem(client):
    for _ in range(login_guard.MAX_FAILURES - 1):
        assert _login(client, 'kasir', 'salah').status_code == 401

    assert _login(client, 'kasir', '12qwaszx').status_code == 200

    # Hitungan sudah bersih: satu kegagalan berikutnya tidak boleh mengunci.
    assert _login(client, 'kasir', 'salah').status_code == 401
    assert _login(client, 'kasir', '12qwaszx').status_code == 200


def test_akun_lain_tidak_ikut_terkunci(client):
    """Mengunci 'owner' dari IP penyerang tidak boleh mematikan login kasir di toko."""
    for _ in range(login_guard.MAX_FAILURES):
        _login(client, 'owner', 'salah', ip='203.0.113.9')

    assert _login(client, 'owner', 'salah', ip='203.0.113.9').status_code == 429
    assert _login(client, 'kasir', '12qwaszx', ip='10.0.0.5').status_code == 200
