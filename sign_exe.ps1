param (
    [string]$FilePath = "dist\XboxSaveVault.exe",
    [string]$SubjectName = "XboxSaveVault",
    [string]$OrgName = "HectorZL"
)

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "     AUTOFIRMADO DE EJECUTABLE (CODE SIGNING)      " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

if (-not (Test-Path $FilePath)) {
    Write-Host "[!] Error: No se encontró el archivo $FilePath para firmar." -ForegroundColor Red
    exit 1
}

# 1. Buscar si ya existe un certificado de firma de código con ese nombre
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "*CN=$SubjectName*" } | Select-Object -First 1

if (-not $cert) {
    Write-Host "[*] Creando nuevo certificado de firma de código autofirmado..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=$SubjectName, O=$OrgName" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(5) `
        -FriendlyName "$SubjectName Code Signing"

    Write-Host "[+] Certificado creado con éxito en Cert:\CurrentUser\My" -ForegroundColor Green
} else {
    Write-Host "[+] Certificado encontrado: $($cert.Subject) [Vence: $($cert.NotAfter.ToShortDateString())]" -ForegroundColor Green
}

# 2. Firmar el ejecutable
Write-Host "[*] Firmando $FilePath..." -ForegroundColor Cyan

$signed = $null
try {
    # Intentar con servidor de sellado de tiempo (timestamp)
    $signed = Set-AuthenticodeSignature -FilePath $FilePath -Certificate $cert -TimestampServer "http://timestamp.digicert.com" -ErrorAction Stop
} catch {
    Write-Host "[i] Servidor de timestamp no disponible o sin conexión. Firmando localmente..." -ForegroundColor Gray
    $signed = Set-AuthenticodeSignature -FilePath $FilePath -Certificate $cert
}

Write-Host "---------------------------------------------------" -ForegroundColor Gray
$sigStatus = Get-AuthenticodeSignature $FilePath
$color = "Yellow"
if ($sigStatus.Status -eq "Valid") { $color = "Green" }
Write-Host "Estado de Firma: $($sigStatus.Status)" -ForegroundColor $color
Write-Host "Firmado por:     $($sigStatus.SignerCertificate.Subject)" -ForegroundColor White
Write-Host "Huella digital:  $($sigStatus.SignerCertificate.Thumbprint)" -ForegroundColor DarkGray
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "[+] ¡Ejecutable firmado exitosamente!" -ForegroundColor Green
