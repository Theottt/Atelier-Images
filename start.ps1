param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$log = Join-Path $root 'atelier_images\launcher.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\AtelierImagesLauncher8189')
$ownsMutex = $false

function Get-AtelierStatus {
    try {
        $request = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:8189/api/status')
        $request.Proxy = $null
        $request.Timeout = 3000
        $response = $request.GetResponse()
        try {
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            try { $data = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        } finally { $response.Close() }
        if ($data.app -ne 'atelier-images') { throw 'Unexpected service' }
        return $data
    } catch { return $null }
}

try {
    try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }
    $python = Join-Path $root 'python_embeded\python.exe'
    $server = Join-Path $root 'atelier_images\server.py'
    foreach ($file in @($python, $server, (Join-Path $root 'ComfyUI\main.py'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Fichier introuvable : $file" }
    }
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format o) Demarrage du lanceur."
    $status = Get-AtelierStatus
    $child = $null
    if ($null -eq $status) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            try { $client.Connect('127.0.0.1', 8189) } catch { }
            if ($client.Connected) { throw 'Le port 8189 est occupe, mais Atelier Images ne repond pas. Consulte les journaux avant de relancer.' }
        } finally { $client.Dispose() }
        # server.py starts ComfyUI itself with CREATE_NO_WINDOW and avoids duplicate backends.
        $child = Start-Process -FilePath $python -ArgumentList @('-s', ('"' + $server + '"'), '--no-browser') `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $root 'atelier_images\launcher-server.stdout.log') `
            -RedirectStandardError (Join-Path $root 'atelier_images\launcher-server.stderr.log')
    }
    $deadline = [DateTime]::UtcNow.AddMinutes(6)
    while ($true) {
        $status = Get-AtelierStatus
        if ($null -ne $status -and $status.ready -eq $true) { break }
        if ($null -ne $status -and $status.error) { throw $status.error }
        if ($null -ne $child -and $child.HasExited) { throw 'Le serveur Atelier s''est arrete. Consulte atelier_images\launcher-server.stderr.log.' }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Les serveurs ne sont pas prets apres 6 minutes. Consulte atelier_images\comfyui.log.' }
        Start-Sleep -Seconds 1
    }
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format o) Atelier et ComfyUI prets."
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8189' }
    exit 0
} catch {
    $message = $_.Exception.Message
    try { Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format o) ERREUR : $message" } catch { }
    if (-not $NoBrowser) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'Atelier Images - Demarrage impossible', 'OK', 'Error') | Out-Null
    }
    exit 1
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
