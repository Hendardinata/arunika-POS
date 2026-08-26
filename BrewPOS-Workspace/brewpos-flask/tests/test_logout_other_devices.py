"""
Pencabutan sesi. Yang diuji: token perangkat lain mati, token yang menekan
tombol tetap hidup, dan akun lain tidak ikut tercabut.
"""
import pytest

from app.services import login_guard


@pytest.fixture(autouse=True)
def clean_guard():
    login_guard.reset_all()
    yield
    login_guard.reset_all()


def _login(client, username='superadmin', password='12qwaszx'):
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200
    return res.get_json()['token']


def _profile(client, token):
    return client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})


def test_perangkat_lain_tercabut_pemanggil_tetap_masuk(client):
    hp = _login(client)
    komputer = _login(client)
    assert _profile(client, hp).status_code == 200

    res = client.post('/api/auth/me/logout-others',
                      headers={'Authorization': f'Bearer {komputer}'})
    assert res.status_code == 200
    token_baru = res.get_json()['token']

    # Sesi HP mati, dan sesi lama komputer ikut mati -- makanya server
    # mengembalikan token pengganti.
    assert _profile(client, hp).status_code == 401
    assert _profile(client, komputer).status_code == 401
    assert _profile(client, token_baru).status_code == 200


def test_akun_lain_tidak_ikut_tercabut(client):
    kasir = _login(client, 'kasir')
    admin = _login(client, 'owner')

    client.post('/api/auth/me/logout-others', headers={'Authorization': f'Bearer {admin}'})

    assert _profile(client, kasir).status_code == 200


def test_login_baru_setelah_pencabutan_tetap_diterima(client):
    lama = _login(client)
    client.post('/api/auth/me/logout-others', headers={'Authorization': f'Bearer {lama}'})

    # Stempel pencabutan tidak boleh mengunci akun: login berikutnya harus jalan.
    assert _profile(client, _login(client)).status_code == 200
