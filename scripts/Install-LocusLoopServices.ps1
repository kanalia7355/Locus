#Requires -Version 5.1
#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installStage = 'package_validation'
$deploymentRoot = 'C:\ProgramData\LocusLoopServicesV1'

function Assert-RegularPath([string]$Value) {
    $item = Get-Item -LiteralPath $Value -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Reparse path rejected'
        }
        if ($item -is [IO.FileInfo]) { $item = $item.Directory } else { $item = $item.Parent }
    }
}

function Resolve-Child([string]$Parent, [string]$Relative) {
    if ($Relative -notmatch '^[A-Za-z0-9_./-]+$' -or $Relative.Contains('..')) {
        throw 'Invalid artifact path'
    }
    $parentPath = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $candidate = [IO.Path]::GetFullPath((Join-Path $Parent $Relative))
    if (-not $candidate.StartsWith($parentPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Artifact path escaped its package'
    }
    return $candidate
}

function Set-SealedAcl([string]$Path, [string[]]$Readers, [string]$Writer = '') {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer) {
        $acl = New-Object Security.AccessControl.DirectorySecurity
    } else {
        $acl = New-Object Security.AccessControl.FileSecurity
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))
    foreach ($identity in @('S-1-5-18', 'S-1-5-32-544')) {
        $principal = New-Object Security.Principal.SecurityIdentifier($identity)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $principal, [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    foreach ($identity in ($Readers | Select-Object -Unique)) {
        if ($identity -eq $Writer) { continue }
        $principal = New-Object Security.Principal.SecurityIdentifier($identity)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $principal, [Security.AccessControl.FileSystemRights]::ReadAndExecute,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    if ($Writer) {
        $principal = New-Object Security.Principal.SecurityIdentifier($Writer)
        $inheritance = if ($item.PSIsContainer) {
            [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
        } else { [Security.AccessControl.InheritanceFlags]::None }
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $principal, [Security.AccessControl.FileSystemRights]::Modify, $inheritance,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Find-LocalUser([string]$Name) {
    try { return Get-LocalUser -Name $Name -ErrorAction Stop }
    catch { if ($_.FullyQualifiedErrorId -notlike 'UserNotFound,*') { throw }; return $null }
}

function Assert-PrivateAcl([string]$Path) {
    Assert-RegularPath $Path
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne 'S-1-5-18' -or
        -not $acl.AreAccessRulesProtected) { throw 'Private SYSTEM ownership required' }
    $rules = @($acl.Access)
    if ($rules.Count -ne 2) { throw 'Unexpected private ACL' }
    $seen = @()
    foreach ($rule in $rules) {
        $identity = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($identity -notin @('S-1-5-18', 'S-1-5-32-544') -or $identity -in $seen -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.IsInherited -or [int]$rule.FileSystemRights -ne 2032127) {
            throw 'Unexpected private ACL grant'
        }
        $seen += $identity
    }
}

function Assert-RecoveryAccount($User, [string]$ExpectedSid, [bool]$ProfilePresent, [bool]$InUse) {
    if ($null -eq $User -or $User.Name -ne 'locus_loop_review' -or
        $User.SID.Value -cne $ExpectedSid -or -not $User.Enabled -or
        $null -ne $User.LastLogon -or $ProfilePresent -or $InUse) {
        throw 'Partial Review identity differs or has been used; preserve for explicit recovery'
    }
}

function Assert-UnusedRecoveryAccount($User, [string]$ExpectedSid) {
    $profileRegistry = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList'
    $profileRoot = [Environment]::ExpandEnvironmentVariables((Get-ItemProperty -LiteralPath $profileRegistry).ProfilesDirectory)
    $profile = (Test-Path -LiteralPath (Join-Path $profileRoot 'locus_loop_review')) -or
        (Test-Path -LiteralPath ($profileRegistry + '\' + $ExpectedSid))
    $accountNames = @('locus_loop_review', '.\locus_loop_review', ([Environment]::MachineName + '\locus_loop_review'))
    $inUse = @(Get-CimInstance -ClassName Win32_Service | Where-Object { $_.StartName -in $accountNames }).Count -ne 0
    Assert-RecoveryAccount $User $ExpectedSid $profile $inUse
    foreach ($group in @(Get-LocalGroup)) {
        if (@(Get-LocalGroupMember -Group $group | Where-Object { $_.SID.Value -eq $ExpectedSid }).Count -ne 0) {
            throw 'Grouped Review account preserved'
        }
    }
}

function Assert-PartialRecovery($Recovery, $NewManifest, [string]$Root) {
    if ($null -eq $Recovery -or
        @($Recovery.PSObject.Properties.Name).Count -ne 2 -or
        $Recovery.previous_manifest_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        $Recovery.review_sid -cnotmatch '^S-1-5-21(-[0-9]{1,10}){4}$' -or
        $Recovery.review_sid -eq $NewManifest.operator_sid) { throw 'Exact recovery pins required' }
    $expectedSid = New-Object Security.Principal.SecurityIdentifier($Recovery.review_sid)
    if ($expectedSid.Value -cne $Recovery.review_sid) { throw 'Canonical Review SID required' }
    Assert-PrivateAcl $Root
    $rootItems = @(Get-ChildItem -LiteralPath $Root -Force)
    if ($rootItems.Count -ne 1 -or $rootItems[0].Name -cne 'runtimes' -or
        -not $rootItems[0].PSIsContainer) { throw 'Unknown partial deployment contents preserved' }
    $runtimes = Join-Path $Root 'runtimes'
    Assert-PrivateAcl $runtimes
    $oldHash = $Recovery.previous_manifest_sha256
    $expectedNames = @($oldHash, ($oldHash + '.manifest.json'))
    $actualNames = @((Get-ChildItem -LiteralPath $runtimes -Force).Name)
    if (@(Compare-Object $expectedNames $actualNames -CaseSensitive).Count -ne 0) {
        throw 'Unknown runtime or prior recovery preserved'
    }
    $oldManifestPath = Join-Path $runtimes ($oldHash + '.manifest.json')
    Assert-PrivateAcl $oldManifestPath
    if ((Get-FileHash -LiteralPath $oldManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $oldHash) {
        throw 'Previous installed manifest changed'
    }
    $oldManifest = Get-Content -LiteralPath $oldManifestPath -Raw | ConvertFrom-Json
    if ($oldManifest.protocol -ne 'locus-service-bundle-v1' -or
        $oldManifest.source_clean -ne $true -or
        $oldManifest.operator_sid -cne $NewManifest.operator_sid -or
        $oldManifest.project_root -ne $NewManifest.project_root) { throw 'Previous deployment identity differs' }
    $oldRuntime = Join-Path $runtimes $oldHash
    Assert-PrivateAcl $oldRuntime
    $oldFiles = @($oldManifest.files.PSObject.Properties.Name)
    if ($oldFiles.Count -lt 1 -or $oldFiles.Count -gt 5000 -or
        @(Get-ChildItem -LiteralPath $oldRuntime -File -Recurse -Force).Count -ne $oldFiles.Count) {
        throw 'Previous inventory differs'
    }
    $expectedDirectories = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $oldFiles) {
        $parent = [IO.Path]::GetDirectoryName((Resolve-Child $oldRuntime $name))
        while ($parent -ne $oldRuntime) {
            [void]$expectedDirectories.Add($parent)
            $parent = [IO.Path]::GetDirectoryName($parent)
        }
    }
    $actualDirectories = @(Get-ChildItem -LiteralPath $oldRuntime -Directory -Recurse -Force)
    if ($actualDirectories.Count -ne $expectedDirectories.Count) { throw 'Previous directory inventory differs' }
    foreach ($directory in $actualDirectories) {
        if (-not $expectedDirectories.Contains($directory.FullName)) { throw 'Unknown previous directory preserved' }
    }
    foreach ($item in @(Get-ChildItem -LiteralPath $oldRuntime -Recurse -Force)) {
        Assert-PrivateAcl $item.FullName
    }
    foreach ($name in $oldFiles) {
        $path = Resolve-Child $oldRuntime $name
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $oldManifest.files.$name) {
            throw 'Previous runtime changed'
        }
    }
    if ($null -ne (Find-LocalUser 'locus_loop_merge')) { throw 'Existing Merge account preserved' }
    $review = Find-LocalUser 'locus_loop_review'
    Assert-UnusedRecoveryAccount $review $Recovery.review_sid
    return $review
}

try {
    if ([IntPtr]::Size -ne 8) { throw '64-bit administrator PowerShell required' }
    foreach ($moduleName in @('Microsoft.PowerShell.Management', 'Microsoft.PowerShell.Security',
        'Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.LocalAccounts')) {
        $moduleDirectory = Join-Path $PSHOME ('Modules\' + $moduleName)
        if ($moduleName -eq 'Microsoft.PowerShell.LocalAccounts') {
            $moduleDirectory = Join-Path $moduleDirectory '1.0.0.0'
        }
        Import-Module (Join-Path $moduleDirectory ($moduleName + '.psd1'))
    }
    $bundleRoot = (Get-Item -LiteralPath $Bundle -Force).FullName
    Assert-RegularPath $bundleRoot
    $manifestPath = Join-Path $bundleRoot 'manifest.json'
    Assert-RegularPath $manifestPath
    $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    if ($manifestBytes.Length -gt 4000000) { throw 'Manifest size exceeded' }
    $manifestHasher = [Security.Cryptography.SHA256]::Create()
    try {
        $observedHash = ([BitConverter]::ToString($manifestHasher.ComputeHash($manifestBytes))).Replace('-', '').ToLowerInvariant()
    } finally { $manifestHasher.Dispose() }
    if ($observedHash -ne $ManifestSha256) { throw 'Manifest identity changed' }
    $manifest = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
    if ($manifest.protocol -ne 'locus-service-bundle-v1' -or $manifest.source_clean -ne $true -or
        $manifest.python_version -ne '3.14.10' -or $manifest.operator_sid -notmatch '^S-1-') {
        throw 'Unsupported package'
    }
    if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.installer_sha256) {
        throw 'Installer identity changed'
    }
    $sourceRuntime = Join-Path $bundleRoot 'runtime'
    $fileNames = @($manifest.files.PSObject.Properties.Name)
    if ($fileNames.Count -eq 0 -or $fileNames.Count -gt 5000) { throw 'Invalid inventory' }
    $actualFiles = @(Get-ChildItem -LiteralPath $sourceRuntime -File -Recurse -Force)
    if ($actualFiles.Count -ne $fileNames.Count) { throw 'Artifact inventory changed' }
    foreach ($name in $fileNames) {
        $source = Resolve-Child $sourceRuntime $name
        Assert-RegularPath $source
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.$name) {
            throw 'Artifact digest changed'
        }
    }
    $roleDefinitions = @{
        review = @{ service = 'LocusLoopReviewV1'; account = 'locus_loop_review'; app_id = 5555922; installation_id = 177234377 }
        merge = @{ service = 'LocusLoopMergeV1'; account = 'locus_loop_merge'; app_id = 5556060; installation_id = 177236244 }
    }
    $recovery = $null
    $recoveryUser = $null
    if ($manifest.PSObject.Properties.Name -contains 'partial_recovery') {
        $recovery = $manifest.partial_recovery
        if ($null -eq $recovery) { throw 'Invalid recovery metadata' }
    }
    foreach ($role in @('review', 'merge')) {
        if (Get-Service -Name $roleDefinitions[$role].service -ErrorAction SilentlyContinue) { throw 'Existing service preserved' }
    }
    if ($null -ne $recovery) {
        $installStage = 'recovery_preflight'
        $recoveryUser = Assert-PartialRecovery $recovery $manifest $deploymentRoot
    } else {
        if (Test-Path -LiteralPath $deploymentRoot) { throw 'Existing deployment requires explicit recovery/upgrade' }
        foreach ($role in @('review', 'merge')) {
            if ($null -ne (Find-LocalUser $roleDefinitions[$role].account)) { throw 'Existing account preserved' }
        }
    }
    if (-not ('LocusBootstrapNativeV1' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class LocusBootstrapNativeV1 {
    [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
    [StructLayout(LayoutKind.Sequential)] struct Privileges { public uint Count; public Luid Id; public uint Flags; }
    [StructLayout(LayoutKind.Sequential)] struct Attributes { public uint Length; public IntPtr Root, Name; public uint Flags; public IntPtr Security, Quality; }
    [StructLayout(LayoutKind.Sequential)] struct Text { public ushort Length, Maximum; public IntPtr Buffer; }
    [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes { public uint Length; public IntPtr Descriptor; public int Inherit; }
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr value);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr value);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateDirectory(string path, ref SecurityAttributes attributes);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFile(string path, uint access, uint share, ref SecurityAttributes attributes, uint mode, uint flags, IntPtr template);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string sddl, uint revision, out IntPtr result, IntPtr size);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr process, uint rights, out IntPtr token);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool LookupPrivilegeValue(string system, string name, out Luid value);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr token, bool disable, ref Privileges state, uint size, IntPtr previous, IntPtr needed);
    [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr system, ref Attributes attributes, uint rights, out IntPtr policy);
    [DllImport("advapi32.dll")] static extern uint LsaAddAccountRights(IntPtr policy, byte[] sid, Text[] rights, uint count);
    [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr policy);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr OpenSCManager(string machine, string database, uint rights);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr OpenService(IntPtr manager, string name, uint rights);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool SetServiceObjectSecurity(IntPtr service, uint information, IntPtr descriptor);
    [DllImport("advapi32.dll")] static extern bool CloseServiceHandle(IntPtr value);
    public static void EnableRestore() {
        IntPtr token;
        if (!OpenProcessToken(GetCurrentProcess(), 0x28, out token)) throw new InvalidOperationException();
        try {
            Luid value;
            if (!LookupPrivilegeValue(null, "SeRestorePrivilege", out value)) throw new InvalidOperationException();
            var state = new Privileges { Count=1, Id=value, Flags=2 };
            if (!AdjustTokenPrivileges(token, false, ref state, 0, IntPtr.Zero, IntPtr.Zero) || Marshal.GetLastWin32Error()!=0) throw new InvalidOperationException();
        } finally { CloseHandle(token); }
    }
    public static System.Security.SecureString NewPassword() {
        byte[] data=new byte[48];
        using(var random=System.Security.Cryptography.RandomNumberGenerator.Create()) random.GetBytes(data);
        string value=Convert.ToBase64String(data)+"!Aa1";
        var result=new System.Security.SecureString();
        foreach(char item in value) result.AppendChar(item);
        result.MakeReadOnly(); Array.Clear(data,0,data.Length);
        return result;
    }
    static IntPtr Descriptor(bool directory) {
        IntPtr result;
        string inheritance = directory ? "OICI" : "";
        if (!ConvertStringSecurityDescriptorToSecurityDescriptor("O:SYD:P(A;"+inheritance+";FA;;;SY)(A;"+inheritance+";FA;;;BA)", 1, out result, IntPtr.Zero)) throw new InvalidOperationException();
        return result;
    }
    public static void MakeDirectory(string path) {
        IntPtr descriptor = Descriptor(true);
        try {
            var attributes = new SecurityAttributes { Length=(uint)Marshal.SizeOf(typeof(SecurityAttributes)), Descriptor=descriptor, Inherit=0 };
            if (!CreateDirectory(path, ref attributes)) throw new InvalidOperationException();
        } finally { LocalFree(descriptor); }
    }
    public static void MakeTree(string root, string path) {
        string prefix = System.IO.Path.GetFullPath(root).TrimEnd('\\')+"\\";
        string full = System.IO.Path.GetFullPath(path);
        if (String.Equals(full, prefix.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) return;
        if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException();
        string current = prefix.TrimEnd('\\');
        foreach (string part in full.Substring(prefix.Length).Split('\\')) {
            current = System.IO.Path.Combine(current, part);
            if (!System.IO.Directory.Exists(current)) MakeDirectory(current);
        }
    }
    static System.IO.FileStream NewPrivateFile(string path) {
        IntPtr descriptor = Descriptor(false);
        try {
            var attributes = new SecurityAttributes { Length=(uint)Marshal.SizeOf(typeof(SecurityAttributes)), Descriptor=descriptor, Inherit=0 };
            IntPtr handle = CreateFile(path, 0x40000000, 0, ref attributes, 1, 0x80, IntPtr.Zero);
            if (handle==new IntPtr(-1)) throw new InvalidOperationException();
            return new System.IO.FileStream(new Microsoft.Win32.SafeHandles.SafeFileHandle(handle,true), System.IO.FileAccess.Write);
        } finally { LocalFree(descriptor); }
    }
    public static void CopyPinned(string source, string target, string digest) {
        using (var input = new System.IO.FileStream(source, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.Read)) {
            if (input.Length>64000000) throw new InvalidOperationException();
            using (var sha = System.Security.Cryptography.SHA256.Create()) {
                string actual = BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
                if (!String.Equals(actual,digest,StringComparison.Ordinal)) throw new InvalidOperationException();
            }
            input.Position=0;
            using (var output = NewPrivateFile(target)) { input.CopyTo(output); output.Flush(true); }
        }
    }
    public static void WritePrivate(string path, string value) {
        using (var output = NewPrivateFile(path)) {
            byte[] data = new System.Text.UTF8Encoding(false).GetBytes(value);
            output.Write(data,0,data.Length); output.Flush(true);
        }
    }
    public static void ProtectService(string name, string operatorSid) {
        IntPtr manager=OpenSCManager(null,null,1);
        if(manager==IntPtr.Zero) throw new InvalidOperationException();
        IntPtr service=IntPtr.Zero, descriptor=IntPtr.Zero;
        try {
            service=OpenService(manager,name,0xf01ff);
            if(service==IntPtr.Zero) throw new InvalidOperationException();
            string sddl="O:SYD:P(A;;0xf01ff;;;SY)(A;;0xf01ff;;;BA)(A;;0x200b5;;;"+operatorSid+")";
            if(!ConvertStringSecurityDescriptorToSecurityDescriptor(sddl,1,out descriptor,IntPtr.Zero) || !SetServiceObjectSecurity(service,5,descriptor)) throw new InvalidOperationException();
        } finally { if(descriptor!=IntPtr.Zero) LocalFree(descriptor); if(service!=IntPtr.Zero) CloseServiceHandle(service); CloseServiceHandle(manager); }
    }
    public static void PrepareIdentity(byte[] sid) {
        var attributes = new Attributes { Length=(uint)Marshal.SizeOf(typeof(Attributes)) };
        IntPtr policy;
        if (LsaOpenPolicy(IntPtr.Zero, ref attributes, 0x810, out policy)!=0) throw new InvalidOperationException();
        string[] names = { "SeServiceLogonRight", "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight" };
        var values = new Text[names.Length];
        try {
            for (int index=0; index<names.Length; index++) values[index]=new Text { Length=(ushort)(names[index].Length*2), Maximum=(ushort)((names[index].Length+1)*2), Buffer=Marshal.StringToHGlobalUni(names[index]) };
            if (LsaAddAccountRights(policy, sid, values, (uint)values.Length)!=0) throw new InvalidOperationException();
        } finally { foreach (var item in values) if (item.Buffer!=IntPtr.Zero) Marshal.FreeHGlobal(item.Buffer); LsaClose(policy); }
        // SCM loads the service account profile at logon. No manual CreateProfile.
    }
}
'@
    }
    $installStage = 'privilege_setup'
    [LocusBootstrapNativeV1]::EnableRestore()
    if ($null -ne $recovery) {
        $intent = @{ protocol = 'locus-partial-recovery-v1'; manifest_sha256 = $ManifestSha256;
            previous_manifest_sha256 = $recovery.previous_manifest_sha256; review_sid = $recovery.review_sid }
        [LocusBootstrapNativeV1]::WritePrivate((Join-Path $deploymentRoot 'partial-recovery-intent.json'), ($intent | ConvertTo-Json))
    } else {
        [LocusBootstrapNativeV1]::MakeDirectory($deploymentRoot)
    }
    $installStage = 'runtime_copy'
    $runtimeParent = Join-Path $deploymentRoot 'runtimes'
    $targetRuntime = Join-Path $runtimeParent $ManifestSha256
    [LocusBootstrapNativeV1]::MakeTree($deploymentRoot, $targetRuntime)
    foreach ($name in $fileNames) {
        $target = Resolve-Child $targetRuntime $name
        [LocusBootstrapNativeV1]::MakeTree($deploymentRoot, [IO.Path]::GetDirectoryName($target))
        [LocusBootstrapNativeV1]::CopyPinned((Resolve-Child $sourceRuntime $name), $target, $manifest.files.$name)
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.$name) {
            throw 'Copied runtime digest changed'
        }
    }
    $installedManifest = Join-Path $runtimeParent ($ManifestSha256 + '.manifest.json')
    [LocusBootstrapNativeV1]::CopyPinned($manifestPath, $installedManifest, $ManifestSha256)
    $installStage = 'accounts'
    $credentials = @{}
    foreach ($role in @('review', 'merge')) {
        # No plaintext password is bound to a cmdlet parameter or emitted to logs.
        $secure = [LocusBootstrapNativeV1]::NewPassword()
        $account = $roleDefinitions[$role].account
        if ($role -eq 'review' -and $null -ne $recoveryUser) {
            $installStage = 'review_password_rotation'
            $user = Find-LocalUser $account
            Assert-UnusedRecoveryAccount $user $recovery.review_sid
            Set-LocalUser -SID $user.SID -Password $secure -PasswordNeverExpires $true
        } else {
            $installStage = ($role + '_account_creation')
            $user = New-LocalUser -Name $account -Password $secure -AccountNeverExpires -PasswordNeverExpires
        }
        $roleDefinitions[$role].sid = $user.SID.Value
        $sidBytes = New-Object byte[] $user.SID.BinaryLength
        $user.SID.GetBinaryForm($sidBytes, 0)
        $installStage = ($role + '_logon_rights')
        [LocusBootstrapNativeV1]::PrepareIdentity($sidBytes)
        $credentials[$role] = New-Object Management.Automation.PSCredential('.\' + $account, $secure)
    }
    $installStage = 'permissions'
    $readers = @($manifest.operator_sid, $roleDefinitions.review.sid, $roleDefinitions.merge.sid)
    $settings = @{ protocol = 'locus-services-v1'; mode = 'prepare'; project_root = $manifest.project_root;
        runtime_root = $targetRuntime; operator_sid = $manifest.operator_sid; roles = $roleDefinitions }
    $settingsPath = Join-Path $deploymentRoot 'settings.json'
    [LocusBootstrapNativeV1]::WritePrivate($settingsPath, ($settings | ConvertTo-Json -Depth 8))
    # Every runtime/config entry is independently protected and owned by SYSTEM.
    foreach ($item in @(Get-ChildItem -LiteralPath $targetRuntime -Recurse -Force)) {
        Set-SealedAcl $item.FullName $readers
    }
    foreach ($path in @($targetRuntime, $runtimeParent, $installedManifest, $settingsPath)) { Set-SealedAcl $path $readers }
    Set-SealedAcl $deploymentRoot $readers
    $stateParent = Join-Path $deploymentRoot 'state'
    [LocusBootstrapNativeV1]::MakeTree($deploymentRoot, $stateParent)
    Set-SealedAcl $stateParent $readers
    foreach ($role in @('review', 'merge')) {
        $statePath = Join-Path $stateParent $role
        [LocusBootstrapNativeV1]::MakeTree($deploymentRoot, $statePath)
        Set-SealedAcl $statePath @($manifest.operator_sid) $roleDefinitions[$role].sid
        $canary = Join-Path $statePath 'isolation-canary.txt'
        [LocusBootstrapNativeV1]::WritePrivate($canary, 'synthetic role isolation canary')
        Set-SealedAcl $canary @($manifest.operator_sid) $roleDefinitions[$role].sid
    }
    $installStage = 'services'
    foreach ($role in @('review', 'merge')) {
        $binary = '"' + (Join-Path $targetRuntime 'python.exe') + '" -I -B "' +
            (Join-Path $targetRuntime 'service_bootstrap.py') + '" --role ' + $role +
            ' --manifest-hash ' + $ManifestSha256
        New-Service -Name $roleDefinitions[$role].service -DisplayName ('Locus Loop ' + $role + ' preparation') `
            -BinaryPathName $binary -StartupType Manual -Credential $credentials[$role] | Out-Null
        [LocusBootstrapNativeV1]::ProtectService($roleDefinitions[$role].service, $manifest.operator_sid)
    }
    foreach ($role in @('review', 'merge')) { Start-Service -Name $roleDefinitions[$role].service }
    @{ installed = $true; mode = 'prepare'; activated = $false; manifest_sha256 = $ManifestSha256;
       review_sid = $roleDefinitions.review.sid; merge_sid = $roleDefinitions.merge.sid } | ConvertTo-Json
} catch {
    [Console]::Error.WriteLine(('{"installed":false,"activated":false,"stage":"' + $installStage +
        '","reason":"setup_failed_preserve_partial_state"}'))
    exit 2
}
