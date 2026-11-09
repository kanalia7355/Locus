#Requires -Version 5.1
#Requires -RunAsAdministrator
param([string]$Bundle,[string]$ManifestSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stage='completion_preflight'
__READONLY_HELPERS__
function Assert-SealedMetadata([string]$Path,[string]$Hash,[string[]]$Readers) {
    Assert-RegularPath $Path
    if((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Hash){throw 'Metadata hash changed'}
    $acl=Get-Acl -LiteralPath $Path
    if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18' -or
        -not $acl.AreAccessRulesProtected){throw 'Sealed metadata required'}
    $wanted=@{'S-1-5-18'=2032127;'S-1-5-32-544'=2032127}
    foreach($reader in $Readers){$wanted[$reader]=1179817}
    $rules=@($acl.Access)
    if($rules.Count -ne $wanted.Count){throw 'Metadata ACL differs'}
    foreach($rule in $rules) {
        $sid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if(-not $wanted.ContainsKey($sid) -or $rule.IsInherited -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            [int]$rule.FileSystemRights -ne $wanted[$sid]){throw 'Metadata access differs'}
        $wanted.Remove($sid)
    }
}
try {
    if([IntPtr]::Size -ne 8){throw '64-bit administrator shell required'}
    foreach($module in @('Microsoft.PowerShell.Management','Microsoft.PowerShell.Security','Microsoft.PowerShell.Utility')) {
        Import-Module (Join-Path $PSHOME ('Modules\'+$module+'\'+$module+'.psd1'))
    }
    Assert-RegularPath $Bundle
    $manifestPath=Join-Path $Bundle 'manifest.json'
    Assert-RegularPath $manifestPath
    if((Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ManifestSha256){throw 'Completion manifest changed'}
    $plan=Get-Content $manifestPath -Raw | ConvertFrom-Json
    if($plan.protocol -cne 'locus-audit-upgrade-completion-v1' -or $plan.source_clean -ne $true){throw 'Closed completion scope required'}
    foreach($name in @('active_manifest','next_manifest','old_settings','new_settings','permit_hash','upgrade_helper')) {
        if($plan.$name -cnotmatch '^[a-f0-9]{64}$'){throw 'Invalid completion binding'}
    }
    $root='C:\ProgramData\LocusLoopAuditV1'
    Assert-RegularPath $root
    $settings=Join-Path $root 'settings.json'
    $staged=Join-Path $root 'settings.upgrade.json'
    $old=Get-Content -LiteralPath $settings -Raw | ConvertFrom-Json
    $readers=@($old.operator_sid,$old.review_sid,$old.audit_sid)
    if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne $old.operator_sid -or
        $old.protocol -cne 'locus-audit-service-v1' -or $old.mode -cne 'prepare' -or
        (Split-Path $old.runtime_root -Leaf) -cne $plan.active_manifest){throw 'Existing deployment differs'}
    $account=Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True AND Name='locus_loop_audit'"
    if($null -eq $account -or $account.SID -cne $old.audit_sid -or $account.Disabled){throw 'Existing audit identity changed'}
    Assert-SealedMetadata $settings $plan.old_settings $readers
    Assert-SealedMetadata $staged $plan.new_settings $readers
    $backup=Join-Path $root ('settings.before-'+$plan.next_manifest+'.json')
    Assert-SealedMetadata $backup $plan.old_settings $readers
    $permitPath=Join-Path $root 'reconciliation-permit.json'
    Assert-SealedMetadata $permitPath $plan.permit_hash @($old.audit_sid,$old.operator_sid)
    $permit=Get-Content $permitPath -Raw | ConvertFrom-Json
    if($permit.identity -cne $plan.next_manifest -or $permit.previous_identity -cne $plan.active_manifest){throw 'Existing permit differs'}
    $intentPath=Join-Path $root 'audit-runtime-upgrade-intent.json'
    Assert-RegularPath $intentPath
    $intent=Get-Content $intentPath -Raw | ConvertFrom-Json
    if($intent.helper -cne $plan.upgrade_helper -or $intent.previous -cne $plan.active_manifest -or
        $intent.next -cne $plan.next_manifest -or $intent.automatic_replay -ne $false){throw 'Original upgrade intent differs'}
    $new=Get-Content -LiteralPath $staged -Raw | ConvertFrom-Json
    if($new.runtime_root -cne (Join-Path (Join-Path $root 'runtimes') $plan.next_manifest) -or
        $new.profile_runtime -cne $old.runtime_root -or $new.state_identity -cne $plan.active_manifest){throw 'Staged migration differs'}
    foreach($name in @('protocol','mode','project_root','operator_sid','review_sid','merge_sid','audit_sid','app_manifest','model','reasoning_effort')) {
        if($new.$name -cne $old.$name){throw 'Existing identity/model scope cannot change'}
    }
    $runtime=$new.runtime_root
    $runtimeManifest=Join-Path (Split-Path $runtime -Parent) ($plan.next_manifest+'.manifest.json')
    Assert-SealedMetadata $runtimeManifest $plan.next_manifest $readers
    $artifact=Get-Content $runtimeManifest -Raw | ConvertFrom-Json
    $files=@($artifact.files.PSObject.Properties)
    if($files.Count -lt 10 -or $files.Count -gt 5000 -or
        @(Get-ChildItem $runtime -Force -Recurse -File).Count -ne $files.Count){throw 'Installed runtime inventory differs'}
    foreach($item in @(Get-ChildItem $runtime -Force -Recurse)){Assert-RegularPath $item.FullName}
    foreach($file in $files){Assert-SealedMetadata (Resolve-Child $runtime $file.Name) $file.Value $readers}
    $service=Get-CimInstance Win32_Service -Filter "Name='LocusLoopAuditV1'"
    $oldBinary='"'+(Join-Path $old.runtime_root 'python.exe')+'" -I -B "'+
        (Join-Path $old.runtime_root 'service_bootstrap.py')+'" --role audit --manifest-hash '+$plan.active_manifest
    if($service.PathName -cne $oldBinary -or $service.StartMode -cne 'Manual' -or
        $service.State -cnotin @('Running','Stopped') -or
        $service.StartName -cnotin @('.\locus_loop_audit',([Environment]::MachineName+'\locus_loop_audit'))){throw 'Original audit service differs'}
    $startName=$service.StartName
    $appBefore=@{}
    foreach($role in @('review','merge')) {
        $item=Get-CimInstance Win32_Service -Filter ("Name='LocusLoop"+$role+"V1'")
        if($null -eq $item -or $item.State -cne 'Running'){throw 'App service not running'}
        $appBefore[$role]=$item.PathName+'|'+$item.StartName+'|'+$item.StartMode
    }
    if('LocusAuditUpgradeCompletionNativeV1' -as [type]){throw 'Fresh administrator shell required'}
    Add-Type -TypeDefinition @'
__NATIVE_HELPER__
'@
    [LocusAuditUpgradeCompletionNativeV1]::EnableRestore()
    $stage='completion_intent'
    [LocusAuditUpgradeCompletionNativeV1]::WritePrivate((Join-Path $root 'audit-upgrade-completion-intent.json'),
        (@{helper=$ManifestSha256;previous=$plan.active_manifest;next=$plan.next_manifest;automatic_replay=$false}|ConvertTo-Json))
    $stage='audit_stop'
    if($service.State -eq 'Running'){Stop-Service LocusLoopAuditV1 -ErrorAction Stop}
    (Get-Service LocusLoopAuditV1).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30))
    $stage='settings_replace'
    Assert-SealedMetadata $settings $plan.old_settings $readers
    Assert-SealedMetadata $staged $plan.new_settings $readers
    [IO.File]::Replace($staged,$settings,[System.Management.Automation.Language.NullString]::Value)
    $stage='binary_switch'
    $binary='"'+(Join-Path $runtime 'python.exe')+'" -I -B "'+
        (Join-Path $runtime 'service_bootstrap.py')+'" --role audit --manifest-hash '+$plan.next_manifest
    [LocusAuditUpgradeCompletionNativeV1]::UpdateAuditBinary($binary)
    $stage='audit_start'
    Start-Service LocusLoopAuditV1
    (Get-Service LocusLoopAuditV1).WaitForStatus('Running',[TimeSpan]::FromSeconds(30))
    $service=Get-CimInstance Win32_Service -Filter "Name='LocusLoopAuditV1'"
    if($service.PathName -cne $binary -or $service.StartName -cne $startName -or $service.StartMode -cne 'Manual'){throw 'Audit registration differs'}
    foreach($role in @('review','merge')) {
        $item=Get-CimInstance Win32_Service -Filter ("Name='LocusLoop"+$role+"V1'")
        if($item.State -cne 'Running' -or ($item.PathName+'|'+$item.StartName+'|'+$item.StartMode) -cne $appBefore[$role]){throw 'App service changed'}
    }
    @{installed=$true;activated=$false;manifest_sha256=$plan.next_manifest;
        credentials_preserved=$true;original_trial_preserved=$true}|ConvertTo-Json -Compress
} catch {
    $chain=@();$cursor=$_.Exception
    for($i=0;$i -lt 8 -and $null -ne $cursor;$i++) {
        $chain+=@{error_type=$cursor.GetType().Name;hresult=('0x'+$cursor.HResult.ToString('x8'))}
        $cursor=$cursor.InnerException
    }
    @{installed=$false;activated=$false;stage=$stage;reason='upgrade_completion_failed_preserve_state';
        error_chain=$chain}|ConvertTo-Json -Compress -Depth 5
    exit 2
}
