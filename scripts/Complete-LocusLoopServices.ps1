#Requires -Version 5.1
#Requires -RunAsAdministrator
# This template is bundled with the exact committed shared installer definitions.
param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installStage = 'completion_package_validation'
$deploymentRoot = 'C:\ProgramData\LocusLoopServicesV1'
# LOCUS_SHARED_FUNCTIONS
try {
    if ([IntPtr]::Size -ne 8) { throw '64-bit administrator PowerShell required' }
    foreach ($moduleName in @('Microsoft.PowerShell.Management', 'Microsoft.PowerShell.Security',
        'Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.LocalAccounts')) {
        $moduleDirectory = Join-Path $PSHOME ('Modules\' + $moduleName)
        if ($moduleName -eq 'Microsoft.PowerShell.LocalAccounts') { $moduleDirectory = Join-Path $moduleDirectory '1.0.0.0' }
        Import-Module (Join-Path $moduleDirectory ($moduleName + '.psd1'))
    }
    Assert-RegularPath $Bundle
    $manifestPath = Join-Path $Bundle 'manifest.json'
    Assert-RegularPath $manifestPath
    $bytes = [IO.File]::ReadAllBytes($manifestPath)
    if ($bytes.Length -gt 65536) { throw 'Completion manifest too large' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($digest -cne $ManifestSha256) { throw 'Completion manifest changed' }
    $manifest = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
    if ($manifest.protocol -cne 'locus-service-completion-v1' -or $manifest.source_clean -ne $true -or
        $manifest.source_commit -cnotmatch '^[a-f0-9]{40}$' -or
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $manifest.installer_sha256) {
        throw 'Completion helper identity differs'
    }
    $installStage = 'service_completion_preflight'
    $settings = Assert-ServiceCompletion $manifest $deploymentRoot
    # LOCUS_SHARED_NATIVE
    $installStage = 'service_completion_intent'
    [LocusBootstrapNativeV1]::EnableRestore()
    $intent = @{ protocol='locus-service-completion-v1'; helper_manifest_sha256=$ManifestSha256;
        active_manifest_sha256=$manifest.service_completion.active_manifest_sha256;
        review_sid=$manifest.service_completion.review_sid; merge_sid=$manifest.service_completion.merge_sid }
    [LocusBootstrapNativeV1]::WritePrivate((Join-Path $deploymentRoot 'service-completion-intent.json'), ($intent | ConvertTo-Json))
    $credentials = @{}
    foreach ($role in @('review','merge')) {
        $installStage = ($role + '_completion_password_rotation')
        $item = $settings.roles.$role
        $user = Find-LocalUser $item.account
        Assert-UnusedRecoveryAccount $user $item.sid $item.account
        $secure = [LocusBootstrapNativeV1]::NewPassword()
        Set-LocalUser -SID $user.SID -Password $secure -PasswordNeverExpires $true
        $credentials[$role] = [System.Management.Automation.PSCredential]::new(('.\' + $item.account), $secure)
        if ($credentials[$role].UserName -cne ('.\' + $item.account)) { throw 'Completion credential identity differs' }
    }
    foreach ($role in @('review','merge')) {
        $item = $settings.roles.$role
        $installStage = ($role + '_completion_service_creation')
        $binary = '"' + (Join-Path $settings.runtime_root 'python.exe') + '" -I -B "' +
            (Join-Path $settings.runtime_root 'service_bootstrap.py') + '" --role ' + $role +
            ' --manifest-hash ' + $manifest.service_completion.active_manifest_sha256
        New-Service -Name $item.service -DisplayName ('Locus Loop ' + $role + ' preparation') `
            -BinaryPathName $binary -StartupType Manual -Credential $credentials[$role] | Out-Null
        $installStage = ($role + '_completion_service_protection')
        [LocusBootstrapNativeV1]::ProtectService($item.service, $settings.operator_sid)
    }
    foreach ($role in @('review','merge')) {
        $installStage = ($role + '_completion_service_start')
        Start-Service -Name $settings.roles.$role.service
    }
    @{ installed=$true; mode='prepare'; activated=$false;
        manifest_sha256=$manifest.service_completion.active_manifest_sha256;
        completion_manifest_sha256=$ManifestSha256 } | ConvertTo-Json
} catch {
    Write-SafeSetupFailure $installStage $_.Exception
    exit 2
}
