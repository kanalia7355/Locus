#Requires -Version 5.1
#Requires -RunAsAdministrator
# Read-only, fixed nonsecret lifecycle records. Never open credential stores/files.
param([string]$Bundle, [string]$ManifestSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-RegularAuditPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($current)) {
        $part = Get-Item -LiteralPath $current -Force
        if ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Reparse diagnostic path refused'
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}
try {
    if ([IntPtr]::Size -ne 8) { throw '64-bit administrator shell required' }
    $root = 'C:\ProgramData\LocusLoopAuditV1'
    Assert-RegularAuditPath $root
    $settingsPath = Join-Path $root 'settings.json'
    Assert-RegularAuditPath $settingsPath
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    if ($settings.protocol -cne 'locus-audit-service-v1' -or $settings.mode -cne 'prepare' -or
        [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne $settings.operator_sid) {
        throw 'Fixed preparation deployment and same owner required'
    }
    $state = Join-Path $root 'state'
    Assert-RegularAuditPath $state
    $records = @()
    foreach ($name in @('home-authentication.json','probe-home-authentication.json',
        'keyring-probe.json','synthetic-model-proof.json')) {
        $path = Join-Path $state $name
        $entry = @{record=$name;present=(Test-Path -LiteralPath $path);phase='absent'}
        if ($entry.present) {
            Assert-RegularAuditPath $path
            $stream = [IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
            try {
                if ($stream.Length -gt 8192) { throw 'Nonsecret record size exceeded' }
                $raw = New-Object byte[] ([int]$stream.Length)
                $offset=0
                while ($offset -lt $raw.Length) {
                    $read=$stream.Read($raw,$offset,$raw.Length-$offset)
                    if ($read -le 0) { throw 'Incomplete lifecycle read' }
                    $offset += $read
                }
            } finally { $stream.Dispose() }
            $record = [Text.Encoding]::UTF8.GetString($raw) | ConvertFrom-Json
            $phase = [string]$record.phase
            if ($phase -cnotin @('pristine','enrolled','probe_ready','probe_cleared','started',
                'complete','active_use','active_enrol','active_probe','active_probe_clear')) {
                $phase = 'unknown'
            }
            $entry.phase = $phase
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $entry.record_sha256 = ([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant() }
            finally { $sha.Dispose() }
        }
        $records += $entry
    }
    $profiles = @()
    foreach ($name in @('home','probe-home')) {
        $homePath = Join-Path $state $name
        Assert-RegularAuditPath $homePath
        $secretsPath = Join-Path $homePath 'secrets'
        Assert-RegularAuditPath $secretsPath
        $entries = @(Get-ChildItem -LiteralPath $secretsPath -Force)
        $profiles += @{profile=$name;plaintext_auth_present=(Test-Path -LiteralPath (Join-Path $homePath 'auth.json'));
            expected_ciphertext_present=(Test-Path -LiteralPath (Join-Path $secretsPath 'codex_auth.age'));
            unexpected_secret_artifact=(@($entries | Where-Object { $_.Name -cne 'codex_auth.age' -or $_.PSIsContainer -or
                ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }).Count -ne 0)}
    }
    @{operation='read_only_audit_state';records=$records;profiles=$profiles;
        credential_values_accessed=$false;provider_request_sent=$false;state_changed=$false;activated=$false} |
        ConvertTo-Json -Depth 5
} catch {
    @{operation='read_only_audit_state';reason='audit_state_inspection_failed';
        error_type=$_.Exception.GetType().Name;hresult=('0x' + $_.Exception.HResult.ToString('x8'));
        state_changed=$false;activated=$false} | ConvertTo-Json -Compress
    exit 2
}
