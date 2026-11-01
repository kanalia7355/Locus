# Read-only guard for the one exact pre-authentication audit-account failure.
function Assert-UnusedAuditAccount($User, [string]$ExpectedSid) {
    $script:installStage = 'completion_account_unused'
    if ($null -eq $User -or $User.Name -cne 'locus_loop_audit' -or
        $User.SID.Value -cne $ExpectedSid -or -not $User.Enabled -or $null -ne $User.LastLogon) {
        throw 'Audit account changed or used; preserve state'
    }
    $profileRegistry = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
    $profileRoot = [Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileRegistry).ProfilesDirectory)
    if ((Test-Path -LiteralPath (Join-Path $profileRoot 'locus_loop_audit')) -or
        (Test-Path -LiteralPath ($profileRegistry + '\' + $ExpectedSid))) {
        throw 'Audit profile exists; no automatic password reset'
    }
    $names = @('locus_loop_audit','.\locus_loop_audit',([Environment]::MachineName + '\locus_loop_audit'))
    if (@(Get-CimInstance Win32_Service | Where-Object { $_.StartName -in $names }).Count -ne 0) {
        throw 'Audit identity already used by a service'
    }
    foreach ($group in @(Get-LocalGroup)) {
        $script:installStage = 'completion_account_groups'
        if (@(Get-LocalGroupMember -Group $group | Where-Object { $_.SID.Value -eq $ExpectedSid }).Count -ne 0) {
            throw 'Grouped audit identity preserved'
        }
    }
}

function Assert-PrivateAuditPath([string]$Path) {
    Assert-RegularPath $Path
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne 'S-1-5-18' -or
        -not $acl.AreAccessRulesProtected -or @($acl.Access).Count -ne 2) { throw 'Private partial deployment changed' }
    $seen = @()
    foreach ($rule in @($acl.Access)) {
        $identity = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($identity -cnotin @('S-1-5-18','S-1-5-32-544') -or $identity -in $seen -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.IsInherited -or [int]$rule.FileSystemRights -ne 2032127) { throw 'Partial deployment grants changed' }
        $seen += $identity
    }
}

function Assert-AuditPartial([string]$Root, $Manifest, [string]$Hash, [string]$ExpectedSid) {
    $script:installStage = 'completion_private_root'
    Assert-PrivateAuditPath $Root
    $expected = @('installation-intent.json','runtimes','state')
    $script:installStage = 'completion_partial_namespace'
    if (@(Get-ChildItem -LiteralPath $Root -Force).Count -ne $expected.Count) { throw 'Partial namespace differs' }
    foreach ($item in @(Get-ChildItem -LiteralPath $Root -Force)) {
        Assert-RegularPath $item.FullName
        if ($item.Name -cnotin $expected) { throw 'Unexpected partial deployment artifact' }
    }
    $intentPath = Join-Path $Root 'installation-intent.json'
    Assert-PrivateAuditPath $intentPath
    $intent = Get-Content -LiteralPath $intentPath -Raw | ConvertFrom-Json
    if ($intent.protocol -cne 'locus-audit-install-v1' -or $intent.manifest_sha256 -cne $Hash -or
        $intent.automatic_replay -ne $false) { throw 'Partial installation intent changed' }
    $state = Join-Path $Root 'state'
    $script:installStage = 'completion_empty_state'
    Assert-RegularPath $state
    $entries = @(Get-ChildItem -LiteralPath $state -Force)
    if ($entries.Count -ne 1 -or $entries[0].Name -cne 'empty' -or -not $entries[0].PSIsContainer) {
        throw 'Authentication/state already exists; preserve without reset'
    }
    Assert-RegularPath $entries[0].FullName
    if (@(Get-ChildItem -LiteralPath $entries[0].FullName -Force).Count -ne 0) { throw 'Workspace not empty' }
    $runtimeParent = Join-Path $Root 'runtimes'
    $script:installStage = 'completion_runtime_inventory'
    Assert-PrivateAuditPath $runtimeParent
    $runtime = Join-Path $runtimeParent $Hash
    $installedManifest = Join-Path $runtimeParent ($Hash + '.manifest.json')
    if (@(Get-ChildItem -LiteralPath $runtimeParent -Force).Count -ne 2) { throw 'Partial runtimes differ' }
    Assert-PrivateAuditPath $runtime
    Assert-PrivateAuditPath $installedManifest
    if ((Get-FileHash -LiteralPath $installedManifest -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Hash) {
        throw 'Installed manifest changed'
    }
    $inventory = @($Manifest.files.PSObject.Properties)
    $actualFiles = @(Get-ChildItem -LiteralPath $runtime -Force -Recurse -File)
    if ($actualFiles.Count -ne $inventory.Count) { throw 'Installed inventory differs' }
    foreach ($item in @(Get-ChildItem -LiteralPath $runtime -Force -Recurse)) { Assert-PrivateAuditPath $item.FullName }
    foreach ($file in $inventory) {
        $path = Resolve-Child $runtime $file.Name
        Assert-RegularPath $path
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value) {
            throw 'Installed artifact changed'
        }
    }
    $blockedLogs = Join-Path $runtime 'blocked-logs'
    Assert-RegularPath $blockedLogs
    if (@(Get-ChildItem -LiteralPath $blockedLogs -Force).Count -ne 0) { throw 'Unexpected audit logs' }
    Assert-UnusedAuditAccount (Find-LocalUser 'locus_loop_audit') $ExpectedSid
}
