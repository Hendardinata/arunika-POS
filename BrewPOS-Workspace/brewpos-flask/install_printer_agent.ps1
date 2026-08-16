<#
.SYNOPSIS
    Pasang jembatan printer supaya jalan sendiri tiap PC kasir dinyalakan.

.DESCRIPTION
    Mendaftarkan printer_agent.py sebagai tugas terjadwal yang jalan saat
    pengguna logon, tanpa jendela, dan hidup lagi sendiri kalau mati.

    Kenapa tugas terjadwal, bukan service (NSSM):
    service jalan di Session 0 yang terpisah dari sesi pengguna. Di sana
    printer bawaan Windows tidak terbaca dan printer yang terpasang sebagai
    koneksi per-pengguna tidak terlihat sama sekali. PC kasir selalu ada yang
    login, jadi jalankan di sesi itu -- lebih sederhana dan bisa dilihat.

.EXAMPLE
    .\install_printer_agent.ps1
    .\install_printer_agent.ps1 -Printer "POS58 Printer"
    .\install_printer_agent.ps1 -Uninstall
#>
param(
    [string]$Printer,
    [int]$Port = 9110,
    [string]$TaskName = 'ArunikaPrinterAgent',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$agent = Join-Path $here 'printer_agent.py'
$logFile = Join-Path $env:LOCALAPPDATA 'Arunika\printer_agent.log'

$startupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'ArunikaPrinterAgent.lnk'

if ($Uninstall) {
    $adaSesuatu = $false

    $ada = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($ada) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tugas terjadwal '$TaskName' dihapus." -ForegroundColor Green
        $adaSesuatu = $true
    }
    if (Test-Path $startupLnk) {
        Remove-Item $startupLnk -Force
        Write-Host "Shortcut Startup dihapus." -ForegroundColor Green
        $adaSesuatu = $true
    }
    if (-not $adaSesuatu) { Write-Host 'Jembatan printer memang belum terpasang.' }

    Get-Process pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.CommandLine -like '*printer_agent.py*' } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    exit 0
}

if (-not (Test-Path $agent)) { throw "printer_agent.py tidak ada di $here" }

# pythonw.exe supaya tidak ada jendela hitam menganggu kasir. Utamakan venv
# proyek kalau ada, karena di situ pywin32 dipasang.
# @( ) membungkus seluruh pipeline, bukan cuma daftarnya: Where-Object yang
# cocok satu mengembalikan string biasa, dan $kandidat[0] pada string berarti
# huruf pertamanya -- "E" dari "E:\...". Tanpa pembungkus ini skrip mencoba
# menjalankan perintah bernama "E".
$kandidat = @(
    @(
        (Join-Path $here 'venv\Scripts\pythonw.exe'),
        (Join-Path $here '.venv\Scripts\pythonw.exe')
    ) | Where-Object { Test-Path $_ }
)

$pythonw = if ($kandidat) { $kandidat[0] } else { (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source }
if (-not $pythonw) { throw 'pythonw.exe tidak ditemukan. Pasang Python lebih dulu.' }

# Gagal cepat di sini jauh lebih baik daripada tugas yang terpasang rapi tapi
# diam-diam tidak pernah bisa mencetak.
$python = $pythonw -replace 'pythonw\.exe$', 'python.exe'

# PowerShell 5.1 membungkus stderr exe native jadi ErrorRecord, dan dengan
# ErrorActionPreference = 'Stop' traceback Python-nya melempar duluan --
# pesan bantuan di bawah tidak akan pernah terlihat. Jadi longgarkan
# sebentar dan nilai lewat kode keluar, bukan lewat $?.
$eapLama = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $python -c "import win32print" *> $null
$adaPywin32 = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $eapLama

if (-not $adaPywin32) {
    throw "pywin32 belum terpasang untuk $python.`nJalankan dulu:  & '$python' -m pip install pywin32"
}

if ($Printer) {
    $daftar = & $python $agent --list
    if ($daftar -notmatch [regex]::Escape($Printer)) {
        Write-Host "Printer terpasang di PC ini:" -ForegroundColor Yellow
        $daftar | Write-Host
        throw "Printer '$Printer' tidak ada dalam daftar di atas."
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

$argumen = "`"$agent`" --port $Port --log `"$logFile`""
if ($Printer) { $argumen += " --printer `"$Printer`"" }

# Tugas terjadwal lebih baik (bisa hidup lagi sendiri kalau mati), tapi
# mendaftarkannya butuh PowerShell elevated. Untuk sekadar jalan saat login itu
# syarat yang tidak sepadan, jadi kalau ditolak turun ke shortcut Startup --
# tanpa admin, hasil akhirnya sama-sama jalan sendiri tiap PC dinyalakan.
$cara = $null
try {
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument $argumen -WorkingDirectory $here
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    # Batas bawaan mematikan tugas setelah 3 hari; kasir jalan terus.
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    $cara = "Tugas terjadwal '$TaskName' (hidup lagi sendiri kalau mati)"
} catch {
    Write-Host "Tugas terjadwal ditolak ($($_.Exception.Message.Trim()))." -ForegroundColor Yellow
    Write-Host "Beralih ke shortcut Startup, tidak butuh hak administrator." -ForegroundColor Yellow

    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($startupLnk)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = $argumen
    $lnk.WorkingDirectory = $here
    $lnk.Description = 'Jembatan printer thermal Arunika POS'
    $lnk.WindowStyle = 7          # minimized; pythonw sendiri sudah tanpa jendela
    $lnk.Save()

    Start-Process -FilePath $pythonw -ArgumentList $argumen -WorkingDirectory $here -WindowStyle Hidden
    $cara = "Shortcut Startup ($startupLnk)"
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Jembatan printer terpasang dan dijalankan." -ForegroundColor Green
Write-Host "  Cara    : $cara"
Write-Host "  Python  : $pythonw"
Write-Host "  Printer : $(if ($Printer) { $Printer } else { 'printer bawaan Windows' })"
Write-Host "  Catatan : $logFile"
Write-Host ""

try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/status" -TimeoutSec 5
    if ($status.siap) {
        Write-Host "Jembatan menjawab. Printer aktif: $($status.printer)" -ForegroundColor Green
        Write-Host "Buka POS -> Pengaturan, harusnya muncul badge hijau 'Jembatan printer aktif'."
    } else {
        Write-Host "Jembatan menjawab tapi belum siap mencetak. Lihat $logFile" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Jembatan belum menjawab di porta $Port." -ForegroundColor Yellow
    Write-Host "Periksa catatannya:  Get-Content '$logFile' -Tail 20"
}

Write-Host ""
Write-Host "Menghapus nanti:  .\install_printer_agent.ps1 -Uninstall"
