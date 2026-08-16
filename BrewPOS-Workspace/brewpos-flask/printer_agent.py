"""
Jembatan printer thermal untuk PC kasir.

    python printer_agent.py                    # pakai printer bawaan Windows
    python printer_agent.py --list             # lihat daftar nama printer
    python printer_agent.py --printer "POS58"  # pilih printer tertentu

Kenapa ini ada
--------------
Halaman POS jalan di server lain, sementara printernya tercolok di PC kasir.
Browser tidak bisa mengirim byte ESC/POS ke driver Windows, dan satu-satunya
jalur langsung (WebUSB) menuntut driver resmi printer ditukar ke WinUSB lewat
Zadig -- driver resminya jadi tidak terpakai lagi.

Program ini menerima byte struk dari halaman POS lalu menyodorkannya ke driver
resmi dalam mode RAW. Printer memakai font bawaannya sendiri, jadi hasilnya
tajam dan sama persis dengan struk yang keluar dari aplikasi Android. Tidak ada
teks yang digambar browser, tidak ada abu-abu antialiasing yang jadi bintik.

Keamanan
--------
Hanya mendengar di 127.0.0.1, jadi tidak bisa dijangkau dari jaringan -- hanya
halaman yang dibuka di PC ini sendiri. Konsekuensinya: situs lain yang dibuka
di PC ini juga bisa menyuruhnya mencetak. Kerugian terburuknya kertas terbuang,
dan itu sebabnya panjang data dibatasi.

Butuh pywin32:  pip install pywin32
"""
import argparse
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9110
MAX_BYTES = 200_000     # struk terpanjang pun jauh di bawah ini; sisanya sampah

try:
    import win32print
except ImportError:                                  # pragma: no cover - khusus Windows
    win32print = None

# Diisi --log. Saat dijalankan Task Scheduler tanpa jendela (pythonw), stdout
# tidak ke mana-mana; tanpa berkas catatan tidak ada cara melihat kenapa struk
# tidak keluar.
_berkas_log = None


def catat(pesan):
    baris = f"[{__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S}] {pesan}"
    print(baris)
    if _berkas_log:
        try:
            with open(_berkas_log, 'a', encoding='utf-8') as f:
                f.write(baris + '\n')
        except OSError:
            pass    # catatan gagal ditulis tidak boleh menghentikan pencetakan


def daftar_printer():
    if not win32print:
        return []
    tingkat = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(tingkat)]


def cetak_raw(nama_printer, data):
    """Kirim byte apa adanya ke printer. Mode RAW = driver tidak ikut menggambar."""
    if not win32print:
        raise RuntimeError('pywin32 belum terpasang. Jalankan: pip install pywin32')

    nama = nama_printer or win32print.GetDefaultPrinter()
    handle = win32print.OpenPrinter(nama)
    try:
        win32print.StartDocPrinter(handle, 1, ('Struk POS', None, 'RAW'))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
    return nama


class Handler(BaseHTTPRequestHandler):
    printer = None

    def _cors(self):
        # Halaman POS datang dari origin lain (server Flask di mesin lain), jadi
        # tanpa header ini browser menolak balasannya.
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')

    def _balas(self, kode, isi):
        badan = json.dumps(isi).encode('utf-8')
        self.send_response(kode)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(badan)))
        self._cors()
        self.end_headers()
        self.wfile.write(badan)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip('/') != '/status':
            return self._balas(404, {'error': 'Tidak ada'})
        self._balas(200, {
            'ok': True,
            'agent': 'arunika-printer-agent',
            'printer': self.printer or (win32print.GetDefaultPrinter() if win32print else None),
            'siap': win32print is not None,
        })

    def do_POST(self):
        if self.path.rstrip('/') != '/print':
            return self._balas(404, {'error': 'Tidak ada'})

        panjang = int(self.headers.get('Content-Length') or 0)
        if panjang <= 0 or panjang > MAX_BYTES:
            return self._balas(400, {'error': f'Ukuran data tidak wajar ({panjang} byte)'})

        try:
            muatan = json.loads(self.rfile.read(panjang) or b'{}')
            data = base64.b64decode(muatan.get('data') or '', validate=True)
        except Exception as e:
            return self._balas(400, {'error': f'Data struk tidak terbaca: {e}'})

        if not data:
            return self._balas(400, {'error': 'Data struk kosong'})

        try:
            dipakai = cetak_raw(muatan.get('printer') or self.printer, data)
        except Exception as e:
            return self._balas(500, {'error': str(e)})

        self._balas(200, {'ok': True, 'printer': dipakai, 'bytes': len(data)})

    def log_message(self, fmt, *args):
        # Satu baris ringkas per permintaan; format bawaan terlalu berisik.
        catat(f"  {self.command} {self.path} -> {fmt % args}")


def main():
    p = argparse.ArgumentParser(description='Jembatan printer thermal untuk PC kasir.')
    p.add_argument('--printer', help='nama printer Windows (default: printer bawaan)')
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--list', action='store_true', help='tampilkan daftar printer lalu keluar')
    p.add_argument('--log', help='catat ke berkas (wajib kalau dijalankan tanpa jendela)')
    a = p.parse_args()

    global _berkas_log
    _berkas_log = a.log

    if a.list:
        nama = daftar_printer()
        if not nama:
            print('Tidak ada printer terdeteksi (atau pywin32 belum terpasang).')
            return 1
        bawaan = win32print.GetDefaultPrinter()
        for n in nama:
            print(f"  {'*' if n == bawaan else ' '} {n}")
        print("\n(* = printer bawaan Windows)")
        return 0

    if not win32print:
        print('pywin32 belum terpasang. Jalankan:  pip install pywin32')
        return 1

    if a.printer and a.printer not in daftar_printer():
        print(f'Printer "{a.printer}" tidak ditemukan. Lihat daftarnya dengan --list')
        return 1

    Handler.printer = a.printer
    catat(f"Jembatan printer siap di http://127.0.0.1:{a.port}")
    catat(f"Printer  : {a.printer or win32print.GetDefaultPrinter()}")
    if not a.log:
        print("Biarkan jendela ini terbuka selama kasir dipakai. Tekan Ctrl+C untuk berhenti.\n")

    try:
        server = HTTPServer(('127.0.0.1', a.port), Handler)
    except OSError as e:
        # Paling sering: agen lain sudah jalan. Kalau ini ditelan, Task Scheduler
        # akan mencoba lagi terus tanpa jejak.
        catat(f"GAGAL mengikat porta {a.port}: {e}")
        return 1

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        catat('Jembatan printer dihentikan.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
