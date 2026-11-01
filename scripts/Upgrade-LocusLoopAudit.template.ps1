#Requires -Version 5.1
#Requires -RunAsAdministrator
param([string]$Bundle,[string]$ManifestSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stage='upgrade_preflight'
__READONLY_HELPERS__
try {
    if([IntPtr]::Size -ne 8){throw '64-bit administrator required'}
    foreach($module in @('Microsoft.PowerShell.Management','Microsoft.PowerShell.Security',
        'Microsoft.PowerShell.Utility','Microsoft.PowerShell.LocalAccounts')) {
        $path=Join-Path $PSHOME ('Modules\'+$module)
        if($module -eq 'Microsoft.PowerShell.LocalAccounts'){$path=Join-Path $path '1.0.0.0'}
        Import-Module (Join-Path $path ($module+'.psd1'))
    }
    Assert-RegularPath $Bundle
    $manifestPath=Join-Path $Bundle 'manifest.json'
    Assert-RegularPath $manifestPath
    if((Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ManifestSha256){throw 'Upgrade manifest changed'}
    $plan=Get-Content $manifestPath -Raw | ConvertFrom-Json
    if($plan.protocol -cne 'locus-audit-runtime-upgrade-v1' -or $plan.source_clean -ne $true -or
        $plan.active_manifest -cnotmatch '^[a-f0-9]{64}$' -or $plan.payload_manifest -cnotmatch '^[a-f0-9]{64}$' -or
        $plan.authentication -cnotmatch '^[a-f0-9]{64}$' -or $plan.trial -cnotmatch '^[a-f0-9]{64}$') {throw 'Closed upgrade scope differs'}
    $root='C:\ProgramData\LocusLoopAuditV1'
    $settingsPath=Join-Path $root 'settings.json'
    Assert-RegularPath $root
    Assert-RegularPath $settingsPath
    if((Get-FileHash $settingsPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $plan.settings_sha256){throw 'Existing settings changed'}
    $old=Get-Content $settingsPath -Raw | ConvertFrom-Json
    if($old.protocol -cne 'locus-audit-service-v1' -or $old.mode -cne 'prepare' -or
        (Split-Path $old.runtime_root -Leaf) -cne $plan.active_manifest -or
        [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne $old.operator_sid){throw 'Existing owner/deployment differs'}
    $account=Find-LocalUser 'locus_loop_audit'
    if($null -eq $account -or $account.SID.Value -cne $old.audit_sid -or -not $account.Enabled){throw 'Existing audit account changed'}
    foreach($path in @($root,$settingsPath)) {
        $acl=Get-Acl -LiteralPath $path
        if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18' -or
            -not $acl.AreAccessRulesProtected){throw 'System-owned upgrade target required'}
        foreach($ace in @($acl.Access)) {
            $sid=$ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            if($ace.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or $ace.IsInherited -or
                ($sid -cnotin @('S-1-5-18','S-1-5-32-544') -and [int]$ace.FileSystemRights -ne 1179817)) {
                throw 'Existing metadata writable outside system/admin'
            }
        }
    }
    foreach($name in @('audit-runtime-upgrade-intent.json','reconciliation-permit.json')) {
        if(Test-Path -LiteralPath (Join-Path $root $name)){throw 'Existing upgrade preserved; no replay'}
    }
    $service=Get-CimInstance Win32_Service -Filter "Name='LocusLoopAuditV1'"
    $oldBinary='"'+(Join-Path $old.runtime_root 'python.exe')+'" -I -B "'+
        (Join-Path $old.runtime_root 'service_bootstrap.py')+'" --role audit --manifest-hash '+$plan.active_manifest
    if($null -eq $service -or $service.State -cne 'Running' -or $service.StartMode -cne 'Manual' -or
        $service.PathName -cne $oldBinary -or $service.StartName -cnotin @('.\locus_loop_audit',
        ([Environment]::MachineName+'\locus_loop_audit'))){throw 'Existing audit service differs'}
    $startName=$service.StartName
    $appBefore=@{}
    foreach($role in @('review','merge')) {
        $item=Get-CimInstance Win32_Service -Filter ("Name='LocusLoop"+$role+"V1'")
        if($null -eq $item -or $item.State -cne 'Running'){throw 'App service not running'}
        $appBefore[$role]=$item.PathName+'|'+$item.StartName+'|'+$item.StartMode
    }
    $payload=Join-Path $Bundle 'payload'
    $payloadManifestPath=Join-Path $payload 'manifest.json'
    Assert-RegularPath $payloadManifestPath
    if((Get-FileHash $payloadManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $plan.payload_manifest){throw 'Payload manifest changed'}
    $manifest=Get-Content $payloadManifestPath -Raw | ConvertFrom-Json
    if($manifest.protocol -cne 'locus-audit-bundle-v1' -or $manifest.source_clean -ne $true -or
        $manifest.operator_sid -cne $old.operator_sid -or $manifest.review_sid -cne $old.review_sid -or
        $manifest.merge_sid -cne $old.merge_sid -or $manifest.app_manifest -cne $old.app_manifest -or
        $manifest.model -cne $old.model -or $manifest.reasoning_effort -cne $old.reasoning_effort){throw 'Payload identity/model policy differs'}
    $files=@($manifest.files.PSObject.Properties)
    if($files.Count -lt 10 -or $files.Count -gt 5000){throw 'Payload inventory incomplete'}
    $parent=Join-Path $root 'runtimes'
    $target=Join-Path $parent $plan.payload_manifest
    if(Test-Path -LiteralPath $target){throw 'Existing upgrade runtime preserved'}
    foreach($file in $files) {
        if($file.Value -cnotmatch '^[a-f0-9]{64}$'){throw 'Invalid payload hash'}
        Assert-RegularPath (Resolve-Child (Join-Path $payload 'runtime') $file.Name)
    }
    if('LocusAuditUpgradeNativeV1' -as [type]){throw 'Fresh administrator shell required'}
    Add-Type -TypeDefinition @'
__NATIVE_HELPER__
'@
    [LocusAuditUpgradeNativeV1]::EnableRestore()
    $stage='upgrade_intent'
    [LocusAuditUpgradeNativeV1]::WritePrivate((Join-Path $root 'audit-runtime-upgrade-intent.json'),
        (@{helper=$ManifestSha256;previous=$plan.active_manifest;next=$plan.payload_manifest;automatic_replay=$false}|ConvertTo-Json))
    $stage='new_runtime'
    [LocusAuditUpgradeNativeV1]::MakeTree($root,$target)
    foreach($file in $files) {
        $destination=Resolve-Child $target $file.Name
        [LocusAuditUpgradeNativeV1]::MakeTree($root,(Split-Path $destination -Parent))
        [LocusAuditUpgradeNativeV1]::CopyPinned((Resolve-Child (Join-Path $payload 'runtime') $file.Name),$destination,$file.Value)
    }
    $readers=@($old.operator_sid,$old.review_sid,$old.audit_sid)
    foreach($item in @(Get-ChildItem $target -Force -Recurse)){Set-SealedAcl $item.FullName $readers}
    Set-SealedAcl $target $readers
    $installedManifest=Join-Path $parent ($plan.payload_manifest+'.manifest.json')
    [LocusAuditUpgradeNativeV1]::CopyPinned($payloadManifestPath,$installedManifest,$plan.payload_manifest)
    Set-SealedAcl $installedManifest $readers
    $backup=Join-Path $root ('settings.before-'+$plan.payload_manifest+'.json')
    [LocusAuditUpgradeNativeV1]::CopyPinned($settingsPath,$backup,$plan.settings_sha256)
    Set-SealedAcl $backup $readers
    $permit=@{protocol='locus-audit-reconciliation-v1';identity=$plan.payload_manifest;
        previous_identity=$plan.active_manifest;authentication=$plan.authentication;trial=$plan.trial;
        diagnostic_inference=$true}
    $permitPath=Join-Path $root 'reconciliation-permit.json'
    [LocusAuditUpgradeNativeV1]::WritePrivate($permitPath,($permit|ConvertTo-Json))
    Set-SealedAcl $permitPath @($old.audit_sid,$old.operator_sid)
    $new=$old | Select-Object *
    $new.runtime_root=$target
    $new | Add-Member -NotePropertyName profile_runtime -NotePropertyValue $old.runtime_root
    $new | Add-Member -NotePropertyName state_identity -NotePropertyValue $plan.active_manifest
    $staged=Join-Path $root 'settings.upgrade.json'
    [LocusAuditUpgradeNativeV1]::WritePrivate($staged,($new|ConvertTo-Json -Depth 6))
    Set-SealedAcl $staged $readers
    $stage='audit_stop'
    Stop-Service LocusLoopAuditV1 -ErrorAction Stop
    (Get-Service LocusLoopAuditV1).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))
    $stage='settings_and_binary'
    if((Get-FileHash $settingsPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $plan.settings_sha256){throw 'Settings changed before switch'}
    $stage='settings_replace'
    [IO.File]::Replace($staged,$settingsPath,[System.Management.Automation.Language.NullString]::Value)
    $stage='binary_switch'
    $binary='"'+(Join-Path $target 'python.exe')+'" -I -B "'+
        (Join-Path $target 'service_bootstrap.py')+'" --role audit --manifest-hash '+$plan.payload_manifest
    [LocusAuditUpgradeNativeV1]::UpdateAuditBinary($binary)
    $stage='audit_start'
    Start-Service LocusLoopAuditV1
    (Get-Service LocusLoopAuditV1).WaitForStatus('Running',[TimeSpan]::FromSeconds(30))
    $service=Get-CimInstance Win32_Service -Filter "Name='LocusLoopAuditV1'"
    if($service.PathName -cne $binary -or $service.StartName -cne $startName -or $service.StartMode -cne 'Manual'){throw 'Audit registration changed unexpectedly'}
    foreach($role in @('review','merge')) {
        $item=Get-CimInstance Win32_Service -Filter ("Name='LocusLoop"+$role+"V1'")
        if($item.State -cne 'Running' -or ($item.PathName+'|'+$item.StartName+'|'+$item.StartMode) -cne $appBefore[$role]){throw 'App service changed'}
    }
    @{installed=$true;activated=$false;manifest_sha256=$plan.payload_manifest;
        credentials_preserved=$true;original_trial_preserved=$true}|ConvertTo-Json -Compress
} catch {
    @{installed=$false;activated=$false;stage=$stage;reason='audit_upgrade_failed_preserve_state';
        error_type=$_.Exception.GetType().Name;hresult=('0x'+$_.Exception.HResult.ToString('x8'))}|ConvertTo-Json -Compress
    exit 2
}
