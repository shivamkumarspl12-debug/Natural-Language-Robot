param(
    [string]$LanIp,
    [ValidateRange(1, 65535)]
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

if (-not $LanIp) {
    $privateInterfaceIndexes = Get-NetConnectionProfile |
        Where-Object { $_.NetworkCategory -eq "Private" } |
        Select-Object -ExpandProperty InterfaceIndex
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Where-Object { $_.InterfaceIndex -in $privateInterfaceIndexes } |
        Sort-Object RouteMetric, InterfaceMetric |
        Select-Object -First 1
    if (-not $defaultRoute) {
        throw "No default route on a Private network was found. Verify this is the trusted restaurant Wi-Fi and mark that network Private before starting Flask."
    }

    $lanAddress = Get-NetIPAddress `
        -InterfaceIndex $defaultRoute.InterfaceIndex `
        -AddressFamily IPv4 |
        Where-Object {
            $_.AddressState -eq "Preferred" -and
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*"
        } |
        Select-Object -First 1
    if (-not $lanAddress) {
        throw "No preferred LAN IPv4 address was found. Pass -LanIp explicitly."
    }
    $LanIp = $lanAddress.IPAddress
}

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($LanIp, [ref]$parsedIp) -or
    $parsedIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "LanIp must be a valid IPv4 address."
}

$octets = $LanIp.Split(".") | ForEach-Object { [int]$_ }
$isPrivateAddress = (
    $octets[0] -eq 10 -or
    ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
    ($octets[0] -eq 192 -and $octets[1] -eq 168)
)
if (-not $isPrivateAddress) {
    throw "LanIp must be an RFC 1918 private IPv4 address."
}

$assignedAddress = Get-NetIPAddress `
    -AddressFamily IPv4 `
    -IPAddress $LanIp `
    -ErrorAction SilentlyContinue
if (-not $assignedAddress) {
    throw "The LAN IP $LanIp is not assigned to this computer."
}
$networkProfile = Get-NetConnectionProfile `
    -InterfaceIndex $assignedAddress.InterfaceIndex `
    -ErrorAction SilentlyContinue
if (-not $networkProfile -or $networkProfile.NetworkCategory -ne "Private") {
    throw "The interface for $LanIp is not marked Private. Only mark it Private after verifying it is the trusted restaurant network."
}

$mkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
$mkcertPath = if ($mkcertCommand) { $mkcertCommand.Source } else { $null }
if (-not $mkcertPath) {
    $wingetPackageDirectory = Join-Path `
        $env:LOCALAPPDATA `
        "Microsoft\WinGet\Packages\FiloSottile.mkcert_Microsoft.Winget.Source_8wekyb3d8bbwe"
    $installedMkcert = Get-ChildItem `
        -Path $wingetPackageDirectory `
        -Filter "mkcert.exe" `
        -Recurse `
        -File `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($installedMkcert) {
        $mkcertPath = $installedMkcert.FullName
    }
}
if (-not $mkcertPath) {
    throw "mkcert is required. Install it with: winget install --id FiloSottile.mkcert --exact --source winget"
}

$certificateDirectory = Join-Path $env:LOCALAPPDATA "Natural-Language-Robot\certs"
New-Item -ItemType Directory -Force $certificateDirectory | Out-Null
$certificateSuffix = "{0}-{1}" -f `
    ($LanIp -replace "\.", "-"), `
    [guid]::NewGuid().ToString("N")
$certificateFile = Join-Path $certificateDirectory "lan-$certificateSuffix.pem"
$privateKeyFile = Join-Path $certificateDirectory "lan-key-$certificateSuffix.pem"

& $mkcertPath `
    -cert-file $certificateFile `
    -key-file $privateKeyFile `
    $LanIp localhost 127.0.0.1
if ($LASTEXITCODE -ne 0) {
    throw "mkcert could not generate the LAN certificate."
}

$caDirectory = (& $mkcertPath -CAROOT).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "mkcert could not locate its local CA."
}
$rootCaPem = Join-Path $caDirectory "rootCA.pem"
$phoneCaFile = Join-Path $certificateDirectory "mkcert-rootCA.cer"
if (-not (Test-Path $rootCaPem)) {
    throw "mkcert's public root CA certificate was not found."
}
Remove-Item $phoneCaFile -Force -ErrorAction SilentlyContinue
$null = & certutil.exe -decode $rootCaPem $phoneCaFile 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "The public mkcert root CA certificate could not be exported."
}
& certutil.exe -user -addstore Root $phoneCaFile | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The public mkcert root CA could not be added to the current user's trust store."
}

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$application = Join-Path $PSScriptRoot "..\app.py"
if (-not (Test-Path $python)) {
    throw "Project virtual environment not found at $python."
}

$env:FLASK_HOST = $LanIp
$env:PORT = "$Port"
$env:FLASK_TLS_CERT_FILE = $certificateFile
$env:FLASK_TLS_KEY_FILE = $privateKeyFile
$env:CUSTOMER_QR_BASE_URL = "https://${LanIp}:$Port"

Write-Host "Starting Flask over HTTPS bound only to ${LanIp}:$Port"
Write-Host "Certificate and server key are stored outside the repository in $certificateDirectory"
& $python $application
exit $LASTEXITCODE
