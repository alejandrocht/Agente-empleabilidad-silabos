param(
    [string]$Runtime = ''
)

$ErrorActionPreference = 'Stop'
$clefListener = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($clefListener) {
    $clefVersion = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 5
    Write-Output "Ollama ya está activo en el puerto 11435 (versión $($clefVersion.version))."
    return
}

if (-not $Runtime) {
    $clefPortable = Join-Path $PSScriptRoot '..\..\outputs\prueba_qwen_clef_20261106\runtime\ollama-0.40.15\ollama.exe'
    if (Test-Path -LiteralPath $clefPortable) {
        $Runtime = $clefPortable
    } else {
        $Runtime = (Get-Command ollama -ErrorAction Stop).Source
    }
}
$clefExecutable = (Resolve-Path -LiteralPath $Runtime).Path
$clefRuntimeDirectory = Split-Path -Parent $clefExecutable
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_CONTEXT_LENGTH = '32768'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$clefProcess = Start-Process -FilePath $clefExecutable -ArgumentList 'serve' `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $clefRuntimeDirectory 'server.out.log') `
    -RedirectStandardError (Join-Path $clefRuntimeDirectory 'server.err.log')
Set-Content -LiteralPath (Join-Path $clefRuntimeDirectory 'server.pid') -Value $clefProcess.Id
Write-Output "Iniciado Ollama local para embeddings y Clef en el puerto 11435 (PID $($clefProcess.Id))."
