package com.arunika.pos

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.OutputStream
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Cangkang WebView untuk ARUNIKA POS + jembatan cetak Bluetooth.
 *
 * UI tetap dilayani server, jadi APK ini nyaris tidak pernah perlu dibangun ulang.
 * Halaman web memanggil AndroidPrinter.print(base64) berisi byte ESC/POS.
 *
 * Printer thermal 58mm memakai Bluetooth Classic (SPP). Tidak ada koneksi tingkat
 * sistem untuk perangkat semacam ini -- statusnya di Pengaturan Android memang
 * "paired" saja, dan koneksinya dibuka aplikasi saat mau mencetak.
 *
 * PENTING soal penanganan galat: versi pertama aplikasi ini tertutup sendiri saat
 * mencetak tanpa pesan apa pun. Sekarang setiap jalur dibungkus penangkap galat,
 * ada penangkap crash global, dan galat terakhir disimpan supaya bisa dibaca lewat
 * menu Diagnostik -- tanpa perlu kabel USB atau logcat.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ArunikaPOS"
        private val POS_URL = BuildConfig.POS_URL
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        private const val PREFS = "arunika_printer"
        private const val KEY_MAC = "printer_mac"
        private const val KEY_LAST_ERROR = "last_error"
        private const val KEY_CRASH = "last_crash"
        private const val KEY_PAGE_ERROR = "last_page_error"
        private const val REQ_BT = 1001
    }

    private lateinit var webView: WebView

    /* Kotak <input type="file"> di halaman web. WebView tidak punya pemilih
       berkas bawaan: tanpa onShowFileChooser di bawah, mengetuk "Pilih File"
       untuk foto nota TIDAK melakukan apa pun -- diam, tanpa galat. Di browser
       mana pun kotak itu bekerja, jadi di aplikasi pun harus. */
    private var callbackBerkas: ValueCallback<Array<Uri>>? = null
    private lateinit var pilihBerkas: ActivityResultLauncher<String>

    private fun prefs() = getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Simpan crash apa pun supaya bisa dibaca setelah aplikasi dibuka lagi.
        // Tanpa ini, aplikasi hanya "hilang" dan tidak ada jejak sama sekali.
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                prefs().edit().putString(KEY_CRASH, stamp() + "\n" + stackOf(e)).apply()
            } catch (_: Throwable) {
            }
            previous?.uncaughtException(t, e)
        }

        // Harus terdaftar sebelum activity mencapai STARTED.
        pilihBerkas = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            // Wajib dijawab walau dibatalkan. Kalau callback-nya dibiarkan
            // menggantung, kotak berkas BERIKUTNYA tidak akan pernah terbuka.
            callbackBerkas?.onReceiveValue(if (uri == null) null else arrayOf(uri))
            callbackBerkas = null
        }

        webView = WebView(this)
        setContentView(webView)

        // Halaman bisa diperiksa dari chrome://inspect lewat kabel USB. Ini APK
        // debug yang dipakai internal, dan tanpa ini satu-satunya cara menelusuri
        // masalah tampilan adalah menebak dari tangkapan layar.
        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // localStorage dipakai untuk token login
            databaseEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            // Matikan pembesaran huruf otomatis. Bawaan WebView adalah
            // TEXT_AUTOSIZING: kalau meta viewport gagal dikenali karena alasan
            // apa pun, halaman dianggap situs desktop lalu setiap huruf
            // dibesarkan supaya "terbaca" -- satu kotak isian bisa memenuhi
            // layar dan POS jadi tidak bisa dipakai sama sekali. POS ini sudah
            // dirancang untuk layar HP, jadi tebakan itu tidak pernah membantu.
            layoutAlgorithm = WebSettings.LayoutAlgorithm.NORMAL

            // Ukuran huruf mengikuti halaman, bukan setelan "Ukuran font"
            // Android. Inilah beda paling terasa antara Chrome dan WebView:
            // Chrome punya penskalaan teksnya sendiri (bawaannya 100%),
            // sedangkan WebView mengalikan seluruh teks dengan skala font
            // sistem. Di HP Samsung yang fontnya disetel besar, halaman yang
            // rapi di Chrome bisa meluber di aplikasi -- padahal mesinnya sama.
            //
            // Tata letak POS ini dirancang per ukuran layar (lihat @media di
            // style.css), jadi pilihan font sistem tidak lagi dihormati di
            // sini. Kalau kasir butuh huruf lebih besar, itu harus dilakukan
            // lewat penyesuaian tata letak, bukan lewat pengali yang membuat
            // tombol Bayar terdorong keluar layar.
            textZoom = 100
        }
        webView.webViewClient = object : WebViewClient() {
            /*
             * Tanpa ini, server yang tidak terjangkau (Tailscale putus, WiFi
             * pindah) menampilkan halaman galat bawaan WebView: teks
             * "net::ERR_..." tanpa tombol apa pun. Kasir hanya bisa menutup
             * paksa aplikasi. Browser selalu memberi tombol muat ulang.
             */
            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                // Gambar atau ikon yang gagal bukan alasan mengganti halaman.
                if (!request.isForMainFrame) return
                val sebab = try { error.description?.toString() } catch (_: Throwable) { null }
                tampilkanHalamanGagal(view, sebab ?: "tidak diketahui")
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?
            ): Boolean {
                callbackBerkas?.onReceiveValue(null)
                callbackBerkas = filePathCallback
                val jenis = params?.acceptTypes
                    ?.firstOrNull { !it.isNullOrBlank() }
                    ?: "*/*"
                return try {
                    pilihBerkas.launch(jenis)
                    true
                } catch (e: Throwable) {
                    callbackBerkas = null
                    recordError("Gagal membuka pemilih berkas", e)
                    false
                }
            }

            /* Galat JavaScript disimpan supaya bisa dibaca lewat Diagnostik.
               Di HP kasir tidak ada konsol pengembang untuk dibuka. */
            override fun onConsoleMessage(pesan: ConsoleMessage?): Boolean {
                if (pesan != null && pesan.messageLevel() == ConsoleMessage.MessageLevel.ERROR) {
                    try {
                        prefs().edit().putString(
                            KEY_PAGE_ERROR,
                            stamp() + "
" + pesan.message() +
                                " (" + pesan.sourceId() + ":" + pesan.lineNumber() + ")"
                        ).apply()
                    } catch (_: Throwable) {
                    }
                }
                return super.onConsoleMessage(pesan)
            }
        }
        webView.addJavascriptInterface(PrinterBridge(), "AndroidPrinter")
        webView.loadUrl(POS_URL)

        requestBluetoothPermission()
        showPendingCrashIfAny()
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    // ------------------------------------------------------------------
    // Utilitas galat
    // ------------------------------------------------------------------

    /**
     * Halaman galat sendiri, menggantikan "net::ERR_..." bawaan WebView.
     *
     * Base URL-nya sengaja POS_URL supaya tombolnya cukup menavigasi ke "/"
     * dan halaman aslinya dimuat ulang -- tanpa perlu jembatan JavaScript,
     * yang membuat halaman ini tetap bekerja walau apa pun gagal.
     */
    private fun tampilkanHalamanGagal(view: WebView, sebab: String) {
        // "&" lebih dulu: kalau "<" diganti duluan, "&lt;" hasilnya ikut
        // terkena putaran kedua dan berubah jadi "&amp;lt;".
        val aman = sebab.replace("&", "&amp;").replace("<", "&lt;")
        val html = """
            <!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
            <div style="font-family:system-ui,-apple-system,sans-serif;padding:32px 24px;
                        text-align:center;color:#3D2617;">
              <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="#C0894A"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                   style="margin-bottom:14px;">
                <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>
                <path d="M12 9v4"/><path d="M12 17h.01"/>
              </svg>
              <h2 style="margin:0 0 8px;font-size:19px;">Server POS tidak terjangkau</h2>
              <p style="margin:0 0 4px;font-size:14px;color:#7A6A5D;">
                Periksa WiFi atau sambungan Tailscale ke server kasir.</p>
              <p style="margin:0 0 22px;font-size:12px;color:#A0928A;">$aman</p>
              <a href="$POS_URL" style="display:inline-block;background:#6F4E37;color:#FFF;
                 text-decoration:none;padding:13px 30px;border-radius:10px;font-size:15px;
                 font-weight:600;">Coba Lagi</a>
            </div>
        """.trimIndent()
        try {
            view.loadDataWithBaseURL(POS_URL, html, "text/html", "utf-8", null)
        } catch (e: Throwable) {
            recordError("Gagal menampilkan halaman galat", e)
        }
    }

    /** Paket dan versi Chromium yang menggambar halaman. */
    private fun webViewInfo(): String = try {
        val pkg = WebView.getCurrentWebViewPackage()
        if (pkg == null) "tidak diketahui" else "${pkg.packageName} ${pkg.versionName}"
    } catch (e: Throwable) {
        "gagal dibaca"
    }

    private fun stamp(): String =
        SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale.getDefault()).format(Date())

    private fun stackOf(e: Throwable): String {
        val sw = StringWriter()
        e.printStackTrace(PrintWriter(sw))
        return sw.toString().take(4000)
    }

    private fun recordError(context: String, e: Throwable) {
        Log.e(TAG, context, e)
        val msg = "$context\n${e.javaClass.simpleName}: ${e.message}"
        try {
            prefs().edit().putString(KEY_LAST_ERROR, stamp() + "\n" + msg + "\n\n" + stackOf(e)).apply()
        } catch (_: Throwable) {
        }
        toast(msg)
    }

    private fun showPendingCrashIfAny() {
        val crash = prefs().getString(KEY_CRASH, null) ?: return
        prefs().edit().remove(KEY_CRASH).apply()
        safeDialog("Aplikasi sempat tertutup", crash)
    }

    private fun toast(msg: String) = runOnUiThread {
        if (!isFinishing) Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    /** Dialog yang tidak pernah bisa menjatuhkan aplikasi. */
    private fun safeDialog(title: String, message: String) = runOnUiThread {
        if (isFinishing || isDestroyed) return@runOnUiThread
        try {
            AlertDialog.Builder(this)
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton("Tutup", null)
                .show()
        } catch (e: Throwable) {
            Log.e(TAG, "Gagal menampilkan dialog", e)
        }
    }

    // ------------------------------------------------------------------
    // Jembatan JavaScript
    // ------------------------------------------------------------------

    inner class PrinterBridge {

        /** Dipanggil dari JavaScript: AndroidPrinter.print(base64EscPos) */
        @JavascriptInterface
        fun print(base64: String) {
            try {
                val data = Base64.decode(base64, Base64.DEFAULT)
                if (data.isEmpty()) { toast("Data struk kosong"); return }
                thread {
                    // Pembungkus terakhir: apa pun yang lolos di dalam sini tidak
                    // boleh sampai mematikan aplikasi.
                    try { sendToPrinter(data) } catch (e: Throwable) { recordError("Gagal mencetak", e) }
                }
            } catch (e: Throwable) {
                recordError("Data struk tidak bisa dibaca", e)
            }
        }

        /** Buka pemilih printer dari halaman web. */
        @JavascriptInterface
        fun choosePrinter() {
            try { runOnUiThread { showPrinterPicker(null) } }
            catch (e: Throwable) { recordError("Gagal membuka daftar printer", e) }
        }

        @JavascriptInterface
        fun isReady(): Boolean = try {
            hasBtPermission() && BluetoothAdapter.getDefaultAdapter() != null
        } catch (e: Throwable) {
            recordError("Gagal memeriksa Bluetooth", e); false
        }

        /** Galat terakhir, supaya halaman web bisa menampilkannya. */
        @JavascriptInterface
        fun lastError(): String = try {
            prefs().getString(KEY_LAST_ERROR, "") ?: ""
        } catch (e: Throwable) { "" }

        /** Ringkasan kondisi perangkat untuk menelusuri masalah cetak. */
        @JavascriptInterface
        fun showDiagnostics() {
            try {
                val adapter = try { BluetoothAdapter.getDefaultAdapter() } catch (e: Throwable) { null }
                val mac = prefs().getString(KEY_MAC, null)
                val bonded = try { bondedDevices().size } catch (e: Throwable) { -1 }
                val info = buildString {
                    appendLine("Alamat server : $POS_URL")
                    appendLine("Android SDK   : ${Build.VERSION.SDK_INT}")
                    appendLine("Perangkat     : ${Build.MANUFACTURER} ${Build.MODEL}")
                    // Mesin render halaman. WebView memakai Chromium yang sama
                    // dengan Chrome, tapi paketnya diperbarui terpisah: kalau
                    // versinya jauh tertinggal dari Chrome di HP yang sama,
                    // tampilan yang berbeda memang wajar.
                    appendLine("Mesin WebView : ${webViewInfo()}")
                    appendLine("Skala font    : ${resources.configuration.fontScale}")
                    appendLine("Izin Bluetooth: ${if (hasBtPermission()) "diberikan" else "BELUM"}")
                    appendLine("Bluetooth     : ${if (adapter == null) "tidak ada" else if (adapter.isEnabled) "aktif" else "mati"}")
                    appendLine("Perangkat pair: $bonded")
                    appendLine("Printer dipilih: ${mac ?: "belum ada"}")
                    appendLine()
                    appendLine("Galat terakhir:")
                    appendLine(prefs().getString(KEY_LAST_ERROR, "(belum ada)"))
                    appendLine()
                    appendLine("Galat halaman terakhir:")
                    append(prefs().getString(KEY_PAGE_ERROR, "(belum ada)"))
                }
                safeDialog("Diagnostik Printer", info)
            } catch (e: Throwable) {
                recordError("Gagal membuka diagnostik", e)
            }
        }

        /** Lupakan printer tersimpan supaya bisa memilih ulang. */
        @JavascriptInterface
        fun forgetPrinter() {
            try {
                prefs().edit().remove(KEY_MAC).apply()
                toast("Pilihan printer dihapus")
            } catch (e: Throwable) { recordError("Gagal menghapus pilihan printer", e) }
        }
    }

    // ------------------------------------------------------------------
    // Bluetooth
    // ------------------------------------------------------------------

    private fun requestBluetoothPermission() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.BLUETOOTH_CONNECT), REQ_BT
                )
            }
        } catch (e: Throwable) {
            recordError("Gagal meminta izin Bluetooth", e)
        }
    }

    private fun hasBtPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
                PackageManager.PERMISSION_GRANTED
    }

    @SuppressLint("MissingPermission")
    private fun bondedDevices(): List<BluetoothDevice> {
        if (!hasBtPermission()) return emptyList()
        val adapter = BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        return try {
            adapter.bondedDevices?.toList() ?: emptyList()
        } catch (e: Throwable) {
            recordError("Gagal membaca daftar perangkat", e); emptyList()
        }
    }

    /** Nama perangkat butuh izin di Android 12+; jangan sampai jadi sumber crash. */
    @SuppressLint("MissingPermission")
    private fun safeName(d: BluetoothDevice): String = try {
        d.name ?: "(tanpa nama)"
    } catch (e: Throwable) {
        "(tanpa nama)"
    }

    private fun showPrinterPicker(pending: ByteArray?) {
        if (isFinishing || isDestroyed) return
        try {
            val devices = bondedDevices()
            if (devices.isEmpty()) {
                safeDialog(
                    "Belum ada printer",
                    "Tidak ada perangkat Bluetooth yang sudah di-pair, atau izin Bluetooth belum " +
                    "diberikan.\n\nPair printer lewat Pengaturan Bluetooth Android, lalu coba lagi."
                )
                return
            }
            val names = devices.map { "${safeName(it)}\n${it.address}" }.toTypedArray()
            AlertDialog.Builder(this)
                .setTitle("Pilih Printer")
                .setItems(names) { _, which ->
                    // Blok ini dulu tidak punya penangkap galat sama sekali -- galat
                    // di sini langsung menutup aplikasi tepat setelah printer diklik.
                    try {
                        val dev = devices[which]
                        prefs().edit().putString(KEY_MAC, dev.address).apply()
                        toast("Printer disimpan: ${safeName(dev)}")
                        if (pending != null) {
                            thread {
                                try { sendToPrinter(pending) }
                                catch (e: Throwable) { recordError("Gagal mencetak", e) }
                            }
                        }
                    } catch (e: Throwable) {
                        recordError("Gagal menyimpan pilihan printer", e)
                    }
                }
                .setNegativeButton("Batal", null)
                .show()
        } catch (e: Throwable) {
            recordError("Gagal menampilkan daftar printer", e)
        }
    }

    @SuppressLint("MissingPermission")
    private fun sendToPrinter(data: ByteArray) {
        if (!hasBtPermission()) {
            toast("Izin Bluetooth belum diberikan")
            runOnUiThread { requestBluetoothPermission() }
            return
        }

        val adapter = BluetoothAdapter.getDefaultAdapter()
        if (adapter == null) { toast("Perangkat ini tidak punya Bluetooth"); return }
        if (!adapter.isEnabled) { toast("Nyalakan Bluetooth dulu"); return }

        val mac = prefs().getString(KEY_MAC, null)
        if (mac == null) {
            runOnUiThread { showPrinterPicker(data) }
            return
        }

        val device = try {
            adapter.getRemoteDevice(mac)
        } catch (e: Throwable) {
            recordError("Printer tersimpan tidak dikenali", e)
            prefs().edit().remove(KEY_MAC).apply()
            runOnUiThread { showPrinterPicker(data) }
            return
        }

        try { if (adapter.isDiscovering) adapter.cancelDiscovery() } catch (_: Throwable) {}

        var socket: BluetoothSocket? = null
        var connected = false

        // Cara standar
        try {
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
            socket.connect()
            connected = true
        } catch (first: Throwable) {
            Log.w(TAG, "Sambungan SPP standar gagal, coba jalur cadangan", first)
            try { socket?.close() } catch (_: Throwable) {}
            socket = null
        }

        // Jalur cadangan: RFCOMM channel 1 lewat refleksi
        if (!connected) {
            try {
                val m = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                socket = m.invoke(device, 1) as BluetoothSocket
                socket.connect()
                connected = true
            } catch (second: Throwable) {
                try { socket?.close() } catch (_: Throwable) {}
                recordError(
                    "Tidak bisa terhubung ke printer.\nPastikan printer menyala, dekat, " +
                    "dan tidak sedang dipakai aplikasi lain.", second
                )
                return
            }
        }

        val live = socket
        if (live == null) {
            toast("Sambungan printer tidak terbentuk")
            return
        }

        try {
            val out: OutputStream = live.outputStream
            // Kirim bertahap: buffer sebagian printer kecil dan mudah kebanjiran.
            var offset = 0
            val chunk = 256
            while (offset < data.size) {
                val len = minOf(chunk, data.size - offset)
                out.write(data, offset, len)
                out.flush()
                offset += len
                Thread.sleep(20)
            }
            // Jeda sebelum tutup: tanpa ini baris terakhir sering terpotong.
            Thread.sleep(400)
            toast("Struk tercetak")
        } catch (e: Throwable) {
            recordError("Gagal mengirim data ke printer", e)
        } finally {
            try { live.close() } catch (_: Throwable) {}
        }
    }
}
