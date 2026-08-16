"""
Penjaga db_migrator.

Tabel baru lahir di dua tempat: model SQLAlchemy (dipakai tes & seed lewat
db.create_all) dan DDL manual di db_migrator (satu-satunya yang jalan di MSSQL
produksi). Keduanya pernah berpisah jalan -- RecipeIngredient hanya ada di model,
jadi database yang tidak pernah di-seed tidak punya tabelnya sama sekali dan
seluruh fitur resep diam-diam mati: stok tidak terpotong, HPP tidak terhitung.

Tes ini tidak menjalankan SQL-nya (sintaksnya khusus MSSQL, sementara tes memakai
SQLite). Yang diperiksa: setiap CREATE TABLE di migrator punya kolom yang sama
persis dengan modelnya.
"""
import pathlib
import re

from app.extensions import db

MIGRATOR = pathlib.Path(__file__).resolve().parent.parent / 'app' / 'services' / 'db_migrator.py'


def _ddl_columns():
    """{nama tabel: {kolom}} dari setiap CREATE TABLE di db_migrator."""
    source = MIGRATOR.read_text(encoding='utf-8')
    hasil = {}
    for nama, badan in re.findall(r'CREATE TABLE \[(\w+)\]\s*\((.*?)\n\s*\)', source, re.S):
        kolom = set()
        for baris in badan.splitlines():
            baris = baris.strip()
            if not baris or baris.upper().startswith('CONSTRAINT'):
                continue
            m = re.match(r'\[(\w+)\]', baris)
            if m:
                kolom.add(m.group(1))
        hasil[nama] = kolom
    return hasil


def test_ddl_migrator_cocok_dengan_model(app):
    ddl = _ddl_columns()
    assert ddl, 'tidak ada CREATE TABLE yang terbaca di db_migrator.py'

    for nama, kolom_ddl in ddl.items():
        tabel = db.metadata.tables.get(nama)
        assert tabel is not None, f'{nama} dibuat di migrator tapi tidak punya model'

        kolom_model = {c.name for c in tabel.columns}
        assert kolom_ddl == kolom_model, (
            f'{nama} berbeda antara model dan DDL migrator.\n'
            f'  hanya di model   : {sorted(kolom_model - kolom_ddl)}\n'
            f'  hanya di migrator: {sorted(kolom_ddl - kolom_model)}'
        )


def _ddl_indexes():
    """[(nama, tabel, [kolom])] dari setiap CREATE INDEX di db_migrator."""
    source = MIGRATOR.read_text(encoding='utf-8')
    hasil = []
    for nama, tabel, kolom in re.findall(
            r"\('(IX_\w+)',\s*'(\w+)',\s*'([^']+)'\)", source):
        hasil.append((nama, tabel, [k.strip(' []') for k in kolom.split(',')]))
    return hasil


def test_indeks_menunjuk_tabel_dan_kolom_yang_benar_benar_ada(app):
    """
    Salah ketik nama kolom di sini tidak akan pernah terlihat: pembuatan indeks
    dibungkus try/except dan hanya mencetak catatan, jadi query tetap jalan --
    cuma tanpa indeks yang dikira sudah ada.
    """
    indeks = _ddl_indexes()
    assert len(indeks) >= 15, f'indeks terbaca terlalu sedikit: {len(indeks)}'

    for nama, tabel, kolom in indeks:
        t = db.metadata.tables.get(tabel)
        assert t is not None, f'{nama} menunjuk tabel {tabel} yang tidak punya model'
        ada = {c.name for c in t.columns}
        for k in kolom:
            assert k in ada, f'{nama}: kolom {tabel}.{k} tidak ada (yang ada: {sorted(ada)})'


def test_nama_indeks_tidak_kembar(app):
    nama = [n for n, _, _ in _ddl_indexes()]
    assert len(nama) == len(set(nama)), 'ada nama indeks yang kembar'


def test_recipeingredient_punya_ddl(app):
    """Tabel inti fitur resep -- pernah hilang sama sekali dari migrator."""
    assert 'RecipeIngredient' in _ddl_columns()
