package com.arunika.pos

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.OutputStream
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
 * "paired" saja, dan koneksinya dibuka oleh aplikasi saat mau mencetak.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        // Diisi saat build dari app/build.gradle.kts (-PposUrl=...)
        private val POS_URL = BuildConfig.POS_URL
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        private const val PREFS = "arunika_printer"
        private const val KEY_MAC = "printer_mac"
        private const val REQ_BT = 1001
    }

    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // localStorage dipakai untuk token login
            databaseEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
        }
        webView.webViewClient = WebViewClient()
        webView.webChromeClient = WebChromeClient()
        webView.addJavascriptInterface(PrinterBridge(), "AndroidPrinter")
        webView.loadUrl(POS_URL)

        requestBluetoothPermission()
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    private fun requestBluetoothPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.BLUETOOTH_CONNECT), REQ_BT
                )
            }
        }
    }

    private fun hasBtPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
                PackageManager.PERMISSION_GRANTED
    }

    private fun toast(msg: String) = runOnUiThread {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    inner class PrinterBridge {
        /** Dipanggil dari JavaScript: AndroidPrinter.print(base64EscPos) */
        @JavascriptInterface
        fun print(base64: String) {
            val data = try {
                Base64.decode(base64, Base64.DEFAULT)
            } catch (e: Exception) {
                toast("Data struk tidak valid"); return
            }
            thread { sendToPrinter(data) }
        }

        /** Buka pemilih printer dari halaman web (mis. tombol di Pengaturan). */
        @JavascriptInterface
        fun choosePrinter() = runOnUiThread { showPrinterPicker(null) }

        @JavascriptInterface
        fun isReady(): Boolean = hasBtPermission() && BluetoothAdapter.getDefaultAdapter() != null
    }

    @SuppressLint("MissingPermission")
    private fun bondedDevices(): List<BluetoothDevice> {
        val adapter = BluetoothAdapter.getDefaultAdapter() ?: return emptyList()
        if (!hasBtPermission()) return emptyList()
        // Ambil dari daftar paired -- tidak perlu discovery, jadi tidak perlu izin lokasi.
        return adapter.bondedDevices?.toList() ?: emptyList()
    }

    @SuppressLint("MissingPermission")
    private fun showPrinterPicker(pending: ByteArray?) {
        val devices = bondedDevices()
        if (devices.isEmpty()) {
            toast("Belum ada perangkat Bluetooth yang di-pair. Pair printer dulu di Pengaturan Android.")
            return
        }
        val names = devices.map { "${it.name ?: "(tanpa nama)"}\n${it.address}" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Pilih Printer")
            .setItems(names) { _, which ->
                val dev = devices[which]
                getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString(KEY_MAC, dev.address).apply()
                toast("Printer disimpan: ${dev.name}")
                if (pending != null) thread { sendToPrinter(pending) }
            }
            .show()
    }

    @SuppressLint("MissingPermission")
    private fun sendToPrinter(data: ByteArray) {
        if (!hasBtPermission()) {
            toast("Izin Bluetooth belum diberikan")
            runOnUiThread { requestBluetoothPermission() }
            return
        }
        val adapter = BluetoothAdapter.getDefaultAdapter()
        if (adapter == null) { toast("Perangkat tidak punya Bluetooth"); return }
        if (!adapter.isEnabled) { toast("Nyalakan Bluetooth dulu"); return }

        val mac = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_MAC, null)
        if (mac == null) {
            // Belum pernah pilih printer: minta pilih, lalu cetak setelahnya.
            runOnUiThread { showPrinterPicker(data) }
            return
        }

        val device = try { adapter.getRemoteDevice(mac) } catch (e: Exception) {
            toast("Printer tersimpan tidak dikenali, pilih ulang")
            runOnUiThread { showPrinterPicker(data) }; return
        }

        // Discovery yang masih jalan sering bikin connect() gagal.
        if (adapter.isDiscovering) adapter.cancelDiscovery()

        var socket: BluetoothSocket? = null
        try {
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
            socket.connect()
        } catch (first: Exception) {
            // Sebagian printer murah menolak cara standar; jalur cadangan lewat
            // RFCOMM channel 1 secara refleksi.
            try {
                socket?.close()
                val m = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                socket = m.invoke(device, 1) as BluetoothSocket
                socket.connect()
            } catch (second: Exception) {
                toast("Gagal terhubung ke printer. Pastikan printer menyala dan dekat.")
                try { socket?.close() } catch (_: Exception) {}
                return
            }
        }

        try {
            val out: OutputStream = socket!!.outputStream
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
        } catch (e: Exception) {
            toast("Gagal mengirim data ke printer: ${e.message}")
        } finally {
            try { socket?.close() } catch (_: Exception) {}
        }
    }
}
