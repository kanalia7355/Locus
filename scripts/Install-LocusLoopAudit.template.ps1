#Requires -Version 5.1
#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installStage = 'package_validation'
$deploymentRoot = 'C:\ProgramData\LocusLoopAuditV1'

__READONLY_HELPERS__

function Set-LockAcl([string]$Path, [string]$Writer) {
    Set-SealedAcl $Path @($Writer)
    $acl = Get-Acl -LiteralPath $Path
    $principal = New-Object Security.Principal.SecurityIdentifier($Writer)
    $acl.RemoveAccessRuleAll((New-Object Security.AccessControl.FileSystemAccessRule(
        $principal, [Security.AccessControl.FileSystemRights]::ReadAndExecute,
        [Security.AccessControl.AccessControlType]::Allow)))
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $principal, [Security.AccessControl.FileSystemRights]'Read,Write,Synchronize',
        [Security.AccessControl.AccessControlType]::Allow)
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

try {
    if ([IntPtr]::Size -ne 8) { throw '64-bit administrator shell required' }
    foreach ($moduleName in @('Microsoft.PowerShell.Management','Microsoft.PowerShell.Security',
        'Microsoft.PowerShell.Utility','Microsoft.PowerShell.LocalAccounts')) {
        $modulePath = Join-Path $PSHOME ('Modules\' + $moduleName)
        if ($moduleName -eq 'Microsoft.PowerShell.LocalAccounts') {
            $modulePath = Join-Path $modulePath '1.0.0.0'
        }
        Import-Module (Join-Path $modulePath ($moduleName + '.psd1'))
    }
    $bundleRoot = (Get-Item -LiteralPath $Bundle -Force).FullName
    Assert-RegularPath $bundleRoot
    $manifestPath = Join-Path $bundleRoot 'manifest.json'
    Assert-RegularPath $manifestPath
    $raw = [IO.File]::ReadAllBytes($manifestPath)
    if ($raw.Length -gt 4000000) { throw 'Manifest size exceeded' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $observed = ([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($observed -cne $ManifestSha256) { throw 'Manifest changed' }
    $manifest = [Text.Encoding]::UTF8.GetString($raw) | ConvertFrom-Json
    if ($manifest.protocol -cne 'locus-audit-bundle-v1' -or $manifest.source_clean -ne $true -or
        $manifest.python_version -cne '3.14.10' -or $manifest.source_commit -cnotmatch '^[a-f0-9]{40}$' -or
        $manifest.app_manifest -cnotmatch '^[a-f0-9]{64}$' -or $manifest.model -cnotmatch '^[a-z0-9][a-z0-9.-]{0,79}$' -or
        $manifest.operator_sid -cnotmatch '^S-1-5-21(?:-[0-9]+){4}$' -or
        $manifest.review_sid -cnotmatch '^S-1-5-21(?:-[0-9]+){4}$' -or
        $manifest.merge_sid -cnotmatch '^S-1-5-21(?:-[0-9]+){4}$') { throw 'Fixed audit scope differs' }
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($currentSid -cne $manifest.operator_sid) { throw 'Same owner elevated console required' }
    if (Test-Path -LiteralPath $deploymentRoot) { throw 'Existing or partial audit deployment preserved' }
    if ($null -ne (Find-LocalUser 'locus_loop_audit')) { throw 'Existing audit account preserved' }
    if ($null -ne (Get-Service -Name LocusLoopAuditV1 -ErrorAction SilentlyContinue)) {
        throw 'Existing audit service preserved'
    }
    $appSettingsPath = 'C:\ProgramData\LocusLoopServicesV1\settings.json'
    Assert-RegularPath $appSettingsPath
    $appAcl = Get-Acl -LiteralPath $appSettingsPath
    if ($appAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18' -or
        -not $appAcl.AreAccessRulesProtected) { throw 'Existing App settings not sealed' }
    $apps = Get-Content -LiteralPath $appSettingsPath -Raw | ConvertFrom-Json
    if ($apps.protocol -cne 'locus-services-v1' -or $apps.mode -cne 'prepare' -or
        (Split-Path $apps.runtime_root -Leaf) -cne $manifest.app_manifest -or
        $apps.operator_sid -cne $manifest.operator_sid -or $apps.project_root -cne $manifest.project_root -or
        $apps.roles.review.sid -cne $manifest.review_sid -or $apps.roles.merge.sid -cne $manifest.merge_sid) {
        throw 'Existing App deployment changed'
    }
    $appBefore = @{}
    foreach ($role in @('review','merge')) {
        $account = Find-LocalUser ('locus_loop_' + $role)
        if ($null -eq $account -or $account.SID.Value -cne $apps.roles.$role.sid) {
            throw 'Existing App account changed'
        }
        $appService = Get-CimInstance Win32_Service -Filter ("Name='" + $apps.roles.$role.service + "'")
        if ($null -eq $appService -or $appService.State -cne 'Running') { throw 'Existing App service not running' }
        $appBefore[$role] = $appService.PathName + '|' + $appService.StartName + '|' + $appService.StartMode
    }
    $files = @($manifest.files.PSObject.Properties)
    foreach ($feature in $manifest.disabled_features) {
        if ($feature -cnotmatch '^[a-z_][a-z0-9_]*$') { throw 'Invalid fixed capability name' }
    }
    if ($files.Count -lt 10 -or $files.Count -gt 5000) { throw 'Complete audit inventory required' }
    $sourceRuntime = Join-Path $bundleRoot 'runtime'
    Assert-RegularPath $sourceRuntime
    $names = @{}
    foreach ($file in $files) {
        $name = [string]$file.Name
        if ($names.ContainsKey($name.ToLowerInvariant()) -or $file.Value -cnotmatch '^[a-f0-9]{64}$') {
            throw 'Duplicate or invalid audit inventory'
        }
        $names[$name.ToLowerInvariant()] = $true
        $source = Resolve-Child $sourceRuntime $name
        Assert-RegularPath $source
        if ((Get-Item -LiteralPath $source).PSIsContainer) { throw 'Regular audit artifact required' }
    }
    if ($manifest.codex_sha256 -cne $manifest.files.'codex.exe' -or
        # pragma: allowlist nextline secret
        $manifest.codex_sha256 -cne '9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42') {
        throw 'Approved CLI identity differs'
    }
    if ('LocusAuditBootstrapNativeV1' -as [type]) { throw 'Fresh administrator shell required' }
    Add-Type -TypeDefinition @'
__NATIVE_HELPER__
'@
    [LocusAuditBootstrapNativeV1]::EnableRestore()
    $installStage = 'private_deployment'
    [LocusAuditBootstrapNativeV1]::MakeDirectory($deploymentRoot)
    [LocusAuditBootstrapNativeV1]::WritePrivate((Join-Path $deploymentRoot 'installation-intent.json'),
        (@{ protocol='locus-audit-install-v1'; manifest_sha256=$ManifestSha256; automatic_replay=$false } | ConvertTo-Json))
    $runtimeParent = Join-Path $deploymentRoot 'runtimes'
    $targetRuntime = Join-Path $runtimeParent $ManifestSha256
    [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot, $targetRuntime)
    foreach ($file in $files) {
        $source = Resolve-Child $sourceRuntime $file.Name
        $target = Resolve-Child $targetRuntime $file.Name
        [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot, (Split-Path $target -Parent))
        [LocusAuditBootstrapNativeV1]::CopyPinned($source, $target, $file.Value)
    }
    $installedManifest = Join-Path $runtimeParent ($ManifestSha256 + '.manifest.json')
    [LocusAuditBootstrapNativeV1]::CopyPinned($manifestPath, $installedManifest, $ManifestSha256)
    [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot, (Join-Path $targetRuntime 'blocked-logs'))
    $installStage = 'audit_account'
    $secure = [LocusAuditBootstrapNativeV1]::NewPassword()
    try {
        $user = New-LocalUser -Name 'locus_loop_audit' -Password $secure -AccountNeverExpires -PasswordNeverExpires
        $auditSid = $user.SID.Value
        if (@($auditSid,$manifest.operator_sid,$manifest.review_sid,$manifest.merge_sid | Select-Object -Unique).Count -ne 4) {
            throw 'All service identities must differ'
        }
        $sidBytes = New-Object byte[] ($user.SID.BinaryLength)
        $user.SID.GetBinaryForm($sidBytes,0)
        [LocusAuditBootstrapNativeV1]::PrepareIdentity($sidBytes)
        $readers = @($manifest.operator_sid,$manifest.review_sid,$auditSid)
        $installStage = 'audit_state'
        $state = Join-Path $deploymentRoot 'state'
        [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot,$state)
        Set-SealedAcl $state @() $auditSid
        [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot,(Join-Path $state 'empty'))
        Set-SealedAcl (Join-Path $state 'empty') @($auditSid)
        $profileLines = @('cli_auth_credentials_store="keyring"',
            ('model=' + ($manifest.model | ConvertTo-Json -Compress)))
        if ($null -ne $manifest.reasoning_effort) {
            if ($manifest.reasoning_effort -cnotin @('none','minimal','low','medium','high','xhigh','max')) {
                throw 'Unknown approved reasoning policy'
            }
            $profileLines += ('model_reasoning_effort=' + ($manifest.reasoning_effort | ConvertTo-Json -Compress))
        }
        $profileLines += @(
            ('model_catalog_json=' + ((Join-Path $targetRuntime 'models.json') | ConvertTo-Json -Compress)),
            ('log_dir=' + ((Join-Path $targetRuntime 'blocked-logs') | ConvertTo-Json -Compress)),
            'skills.bundled.enabled=false','skills.include_instructions=false',
            'analytics.enabled=false','feedback.enabled=false',
            'otel.exporter="none"','otel.trace_exporter="none"','otel.metrics_exporter="none"',
            'otel.log_user_prompt=false','otel.log_agent_responses=false','otel.log_guardian_assessments=false',
            'hide_agent_reasoning=true','show_raw_agent_reasoning=false','mcp_servers={}',
            '[history]','persistence="none"','[features]','secret_auth_storage=true')
        $installStage = 'audit_profile_policy'
        foreach ($feature in $manifest.disabled_features) {
            if ($feature -cnotmatch '^[a-z_][a-z0-9_]*$') { throw 'Invalid fixed capability name' }
            $profileLines += ($feature + '=false')
        }
        foreach ($profileName in @('home','probe-home')) {
            $installStage = ('audit_profile_' + $profileName)
            $homePath = Join-Path $state $profileName
            [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot,$homePath)
            [LocusAuditBootstrapNativeV1]::WritePrivate((Join-Path $homePath 'config.toml'), (($profileLines -join "`n") + "`n"))
            [LocusAuditBootstrapNativeV1]::WritePrivate((Join-Path $homePath 'auth.lock'),'')
            [LocusAuditBootstrapNativeV1]::WritePrivate((Join-Path $homePath 'installation_id'),[Guid]::NewGuid().ToString('D'))
            $secretsPath = Join-Path $homePath 'secrets'
            [LocusAuditBootstrapNativeV1]::MakeTree($deploymentRoot,$secretsPath)
            Set-SealedAcl $secretsPath @() $auditSid
            [LocusAuditBootstrapNativeV1]::WritePrivate((Join-Path $state ($profileName + '-authentication.json')), '{"key_metadata":null,"phase":"pristine"}')
            Set-SealedAcl (Join-Path $state ($profileName + '-authentication.json')) @() $auditSid
            Set-SealedAcl (Join-Path $homePath 'config.toml') @($auditSid)
            Set-LockAcl (Join-Path $homePath 'auth.lock') $auditSid
            Set-LockAcl (Join-Path $homePath 'installation_id') $auditSid
            Set-SealedAcl $homePath @($auditSid)
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $targetRuntime -Recurse -Force)) {
            $installStage = 'audit_runtime_acl'
            Set-SealedAcl $item.FullName $readers
        }
        foreach ($path in @($targetRuntime,$runtimeParent,$installedManifest)) { Set-SealedAcl $path $readers }
        $settings = @{ protocol='locus-audit-service-v1';mode='prepare';project_root=$manifest.project_root;
            runtime_root=$targetRuntime;operator_sid=$manifest.operator_sid;review_sid=$manifest.review_sid;
            merge_sid=$manifest.merge_sid;audit_sid=$auditSid;app_manifest=$manifest.app_manifest;
            model=$manifest.model;reasoning_effort=$manifest.reasoning_effort }
        $settingsPath = Join-Path $deploymentRoot 'settings.json'
        $installStage = 'audit_settings'
        [LocusAuditBootstrapNativeV1]::WritePrivate($settingsPath,($settings | ConvertTo-Json -Depth 5))
        Set-SealedAcl $settingsPath $readers
        Set-SealedAcl $deploymentRoot $readers
        $installStage = 'audit_service'
        $credential = [Management.Automation.PSCredential]::new('.\locus_loop_audit',$secure)
        if ($credential.UserName -cne '.\locus_loop_audit') { throw 'Service credential identity differs' }
        $binary = '"' + (Join-Path $targetRuntime 'python.exe') + '" -I -B "' +
            (Join-Path $targetRuntime 'service_bootstrap.py') + '" --role audit --manifest-hash ' + $ManifestSha256
        New-Service -Name LocusLoopAuditV1 -DisplayName 'Locus isolated audit preparation' `
            -BinaryPathName $binary -StartupType Manual -Credential $credential | Out-Null
        [LocusAuditBootstrapNativeV1]::ProtectService('LocusLoopAuditV1',$manifest.operator_sid,$manifest.review_sid)
    } finally { if ($null -ne $secure) { $secure.Dispose() } }
    $installStage = 'audit_start'
    Start-Service -Name LocusLoopAuditV1
    (Get-Service -Name LocusLoopAuditV1).WaitForStatus('Running',[TimeSpan]::FromSeconds(30))
    foreach ($role in @('review','merge')) {
        $appService = Get-CimInstance Win32_Service -Filter ("Name='" + $apps.roles.$role.service + "'")
        if (($appService.PathName + '|' + $appService.StartName + '|' + $appService.StartMode) -cne $appBefore[$role] -or
            $appService.State -cne 'Running') { throw 'Existing App service changed; preserve and reconcile' }
    }
    @{ installed=$true; activated=$false; app_services_preserved=$true; manifest_sha256=$ManifestSha256 } |
        ConvertTo-Json -Compress
} catch {
    @{ installed=$false; activated=$false; stage=$installStage;
        reason='audit_setup_failed_preserve_partial_state'; error_type=$_.Exception.GetType().Name;
        hresult=('0x' + $_.Exception.HResult.ToString('x8')) } |
        ConvertTo-Json -Compress
    exit 1
}
