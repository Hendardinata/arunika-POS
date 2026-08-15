"""
Uji alur sesi kas bersama (shift) + identitas member berbasis kontak.

    python test_shift_member.py

Selalu memakai database SQLite sementara di folder temp OS, dibuat dari nol lalu
dibuang. Database toko (MSSQL) tidak pernah disentuh -- ada assert eksplisit untuk itu.
"""
import os, sys, tempfile

DB_FILE = os.path.join(tempfile.gettempdir(), 'arunika_shift_member_test.sqlite')
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
os.environ['DATABASE_URL'] = 'sqlite:///' + DB_FILE.replace('\\', '/')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
import bcrypt
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.shift import Shift

app = create_app()
print('DB dipakai:', app.config['SQLALCHEMY_DATABASE_URI'])
assert 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI'], 'HARUS sqlite, batalkan!'

with app.app_context():
    db.create_all()
    for name, role in [('ka', 'CASHIER'), ('kb', 'HEADBAR')]:
        if not User.query.filter_by(username=name).first():
            db.session.add(User(username=name, role=role,
                                password=bcrypt.hashpw(b'pw123456', bcrypt.gensalt()).decode()))
    db.session.commit()

c = app.test_client()
fails = []


def check(label, cond, detail=''):
    print(('  OK  ' if cond else ' FAIL ') + label + (f'   <- {detail}' if not cond and detail else ''))
    if not cond:
        fails.append(label)


def login(u):
    r = c.post('/api/auth/login', json={'username': u, 'password': 'pw123456'})
    assert r.status_code == 200, r.get_json()
    return {'Authorization': 'Bearer ' + r.get_json()['token']}


A, B = login('ka'), login('kb')

r = c.post('/api/shift/open', json={'startingCash': 200000}, headers=A)
check('A buka sesi', r.status_code == 201, r.get_json())
shift = r.get_json()
check('label sesi = SESI 1', shift.get('label') == 'SESI 1', shift.get('label'))
check('sessionNo terisi', shift.get('sessionNo') == 1, shift.get('sessionNo'))

r2 = c.post('/api/shift/open', json={'startingCash': 50000}, headers=B)
check('B tidak bisa buka sesi kedua', r2.status_code == 400, r2.get_json())
check('respons menyertakan sesi yang berjalan', (r2.get_json() or {}).get('shift', {}).get('id') == shift['id'])

cur = c.get('/api/shift/current', headers=B).get_json()['currentShift']
check('B melihat sesi yang sama (sesi milik toko)', cur and cur['id'] == shift['id'])

r = c.post('/api/shift/handover', json={'note': 'A pulang duluan'}, headers=B)
check('handover ke B', r.status_code == 201, r.get_json())
cur = c.get('/api/shift/current', headers=B).get_json()['currentShift']
check('penjaga sekarang B', cur['currentUser']['username'] == 'kb', cur.get('currentUser'))
check('riwayat handover tercatat', len(cur['handovers']) == 1 and cur['handovers'][0]['fromUsername'] == 'ka',
      cur.get('handovers'))
r = c.post('/api/shift/handover', json={}, headers=B)
check('handover ke penjaga yang sama ditolak', r.status_code == 400, r.get_json())

r = c.post('/api/shift/close', json={'endingCash': 250000, 'closingNote': 'uji'}, headers=B)
check('B menutup sesi yang dibuka A', r.status_code == 200, r.get_json())
closed = r.get_json()
check('openedBy=A & closedBy=B',
      closed['openedByUser']['username'] == 'ka' and closed['closedByUser']['username'] == 'kb', closed)
check('ekspektasi kas = modal awal (tanpa transaksi tunai)', closed['expectedEndingCash'] == 200000,
      closed['expectedEndingCash'])
check('catatan penutupan tersimpan', closed['closingNote'] == 'uji')

r = c.post('/api/shift/open', json={'startingCash': 100000}, headers=A)
check('sesi berikutnya = SESI 2', r.get_json().get('label') == 'SESI 2', r.get_json().get('label'))
stale_id = r.get_json()['id']
with app.app_context():
    s = Shift.query.get(stale_id)
    s.startTime = datetime.utcnow() - timedelta(hours=20)
    db.session.commit()
cur = c.get('/api/shift/current', headers=A).get_json()['currentShift']
check('sesi > 18 jam ditandai NEEDS_REVIEW', cur['status'] == 'NEEDS_REVIEW', cur['status'])
r = c.post('/api/shift/close', json={'endingCash': 100000}, headers=A)
check('sesi nyangkut tetap bisa ditutup', r.status_code == 200, r.get_json())

reports = c.get('/api/shift/reports').get_json()
check('laporan sesi terisi', len(reports) == 2, len(reports))

# --- Checkout: atribusi kasir, tanpa auto-create member, Guest tanpa loyalty ---
from app.models.category import Category
from app.models.menu import Menu
from app.models.customer import Customer

with app.app_context():
    cat = Category(name='Kopi')
    db.session.add(cat)
    db.session.flush()
    db.session.add(Menu(name='Kopi Susu', price=20000, hpp=8000, categoryId=cat.id))
    db.session.commit()
    menu_id = Menu.query.first().id

c.post('/api/shift/open', json={'startingCash': 100000}, headers=A)  # sesi 3 dibuka A

m1 = c.post('/api/customers', json={'nickname': 'Budi', 'phone': '+62812-9999-0001'}, headers=B)
check('daftar member (HP saja)', m1.status_code == 201, m1.get_json())
with app.app_context():
    stored = Customer.query.filter_by(nickname='Budi').first()
    check('HP tersimpan ternormalisasi 08xx', stored.phone == '081299990001', stored.phone)
    check('email kosong tetap NULL', stored.email is None)

m2 = c.post('/api/customers', json={'nickname': 'Budi', 'email': 'Budi.Dua@Mail.com'}, headers=B)
check('nickname kembar diterima', m2.status_code == 201, m2.get_json())
with app.app_context():
    check('email tersimpan lowercase', Customer.query.get(m2.get_json()['id']).email == 'budi.dua@mail.com')

dup = c.post('/api/customers', json={'nickname': 'Lain', 'phone': '0812 9999 0001'}, headers=B)
check('HP duplikat (format beda) ditolak 409', dup.status_code == 409, dup.get_json())
dup2 = c.post('/api/customers', json={'nickname': 'Lain', 'email': 'BUDI.DUA@mail.com'}, headers=B)
check('email duplikat (beda huruf) ditolak 409', dup2.status_code == 409, dup2.get_json())

r = c.post('/api/checkout', json={'customerId': m1.get_json()['id'], 'paymentMethod': 'CASH',
                                  'items': [{'menuId': menu_id, 'quantity': 2}]}, headers=B)
check('checkout oleh B pada sesi yang dibuka A', r.status_code == 201, r.get_json())
if r.status_code == 201:
    tx = r.get_json()['transaction']
    check('transaksi mencatat kasir B', tx.get('cashierName') == 'kb', tx.get('cashierName'))
    check('transaksi ikut sesi toko', tx.get('shiftId') is not None)
    check('member dapat poin', r.get_json()['customer']['points'] > 0)

r = c.post('/api/checkout', json={'nickname': 'SiapaIni', 'paymentMethod': 'CASH',
                                  'items': [{'menuId': menu_id, 'quantity': 1}]}, headers=B)
check('member tak dikenal ditolak', r.status_code == 404, r.get_json())
with app.app_context():
    check('tidak ada member hantu dibuat', Customer.query.filter_by(nickname='SiapaIni').first() is None)

r = c.post('/api/checkout', json={'nickname': 'Guest', 'paymentMethod': 'CASH',
                                  'items': [{'menuId': menu_id, 'quantity': 1}]}, headers=A)
check('checkout Guest jalan', r.status_code == 201, r.get_json())
if r.status_code == 201:
    g = r.get_json()['customer']
    check('Guest tanpa poin/xp/streak', g['points'] == 0 and g['xp'] == 0 and g['streakCount'] == 0, g)
    check('transaksi Guest atas nama kasir A', r.get_json()['transaction']['cashierName'] == 'ka')

lst = c.get('/api/customers', headers=B).get_json()
check('Guest tidak muncul di daftar member', all(x['nickname'] != 'Guest' for x in lst), [x['nickname'] for x in lst])

ac = c.get('/api/customers/autocomplete?q=Bud', headers=B).get_json()
check('autocomplete menemukan dua Budi', len(ac) == 2, [x['nickname'] for x in ac])
s1 = c.get('/api/customers/search?q=0812-9999-0001', headers=B)
check('cari member via HP berformat', s1.status_code == 200 and s1.get_json()['nickname'] == 'Budi', s1.get_json())

c.post('/api/shift/close', json={'endingCash': 150000}, headers=A)

# --- Pengeluaran tunai dari laci ikut mengurangi ekspektasi kas ---
from app.models.expense import ExpenseCategory

with app.app_context():
    db.session.add(ExpenseCategory(name='Operasional Uji'))
    db.session.commit()
    cat_id = ExpenseCategory.query.filter_by(name='Operasional Uji').first().id

c.post('/api/shift/open', json={'startingCash': 500000}, headers=A)
r = c.post('/api/checkout', json={'nickname': 'Guest', 'paymentMethod': 'CASH',
                                  'items': [{'menuId': menu_id, 'quantity': 1}]}, headers=A)
check('checkout tunai untuk uji kas', r.status_code == 201, r.get_json())
tunai = r.get_json()['transaction']['totalAmount'] if r.status_code == 201 else 0

r = c.post('/api/expenses', json={'categoryId': cat_id, 'amount': 30000,
                                  'notes': 'beli gas', 'paymentSource': 'CASH_DRAWER'}, headers=A)
check('catat pengeluaran dari laci', r.status_code == 201, r.get_json())
check('pengeluaran terikat ke sesi berjalan', r.get_json().get('shiftId') is not None, r.get_json())

r = c.post('/api/expenses', json={'categoryId': cat_id, 'amount': 999000,
                                  'notes': 'transfer sewa', 'paymentSource': 'OTHER'}, headers=A)
check('pengeluaran non-tunai tidak terikat sesi', r.get_json().get('shiftId') is None, r.get_json())

r = c.post('/api/shift/close', json={'endingCash': 500000 + tunai - 30000}, headers=A)
expected = r.get_json().get('expectedEndingCash')
check('ekspektasi kas dikurangi belanja tunai',
      expected == 500000 + tunai - 30000, f'expected={expected}, seharusnya={500000 + tunai - 30000}')
check('kas cocok (tidak ada selisih palsu)',
      r.get_json().get('endingCash') == expected, r.get_json())


with app.app_context():
    db.session.remove()
    db.engine.dispose()
try:
    os.remove(DB_FILE)
except OSError:
    pass

print('\n' + ('SEMUA LULUS' if not fails else f'GAGAL ({len(fails)}): {fails}'))
sys.exit(1 if fails else 0)
