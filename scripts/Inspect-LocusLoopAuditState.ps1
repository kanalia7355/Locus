#Requires -Version 5.1
#Requires -RunAsAdministrator
# Read-only, fixed nonsecret lifecycle records. Never open credential stores/files.
param([string]$Bundle, [string]$ManifestSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$diagnosticStage = 'path_validation'
$diagnosticRecord = $null
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
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;
public static class LocusAuditRecordReaderV1 {
    [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
    [StructLayout(LayoutKind.Sequential)] struct Privileges {
        public uint Count; public Luid Id; public uint Flags;
    }
    [StructLayout(LayoutKind.Sequential)] struct Tag { public uint Attributes, Value; }
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(
        IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern bool LookupPrivilegeValue(string system,string name,out Luid value);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool AdjustTokenPrivileges(
        IntPtr token,bool disable,ref Privileges state,uint length,out Privileges previous,out uint required);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr value);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern SafeFileHandle CreateFile(string path,uint access,uint share,IntPtr security,
        uint disposition,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandleEx(
        SafeFileHandle handle,int kind,out Tag info,uint size);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern uint GetFinalPathNameByHandle(SafeFileHandle handle,StringBuilder path,uint size,uint flags);
    static SafeFileHandle Open(string path) {
        var handle=CreateFile(path,0x80000000,1,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
        if(!handle.IsInvalid) return handle;
        int error=Marshal.GetLastWin32Error();handle.Dispose();
        if(error!=5) throw new Win32Exception(error);
        using(var identity=WindowsIdentity.GetCurrent()) {
            if(!new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator))
                throw new Win32Exception(5);
        }
        IntPtr token;
        if(!OpenProcessToken(GetCurrentProcess(),0x28,out token))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        var previous=new Privileges();bool changed=false;
        try {
            Luid id;
            if(!LookupPrivilegeValue(null,"SeBackupPrivilege",out id))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            var state=new Privileges { Count=1,Id=id,Flags=2 };uint required;
            if(!AdjustTokenPrivileges(token,false,ref state,(uint)Marshal.SizeOf(typeof(Privileges)),
                out previous,out required) || Marshal.GetLastWin32Error()!=0)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            changed=true;
            handle=CreateFile(path,0x80000000,1,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
            if(handle.IsInvalid) { error=Marshal.GetLastWin32Error();handle.Dispose();throw new Win32Exception(error); }
            return handle;
        } finally {
            if(changed) {
                Privileges ignored;uint required;
                if(!AdjustTokenPrivileges(token,false,ref previous,(uint)Marshal.SizeOf(typeof(Privileges)),
                    out ignored,out required) || Marshal.GetLastWin32Error()!=0) {
                    if(handle!=null) handle.Dispose();
                    CloseHandle(token);
                    throw new InvalidOperationException("Privilege restoration failed");
                }
            }
            CloseHandle(token);
        }
    }
    public static byte[] Read(string name) {
        if(name!="home-authentication.json" && name!="probe-home-authentication.json" &&
            name!="keyring-probe.json" && name!="synthetic-model-proof.json")
            throw new InvalidOperationException("Fixed nonsecret record required");
        string path=Path.Combine(@"C:\ProgramData\LocusLoopAuditV1\state",name);
        using(var handle=Open(path)) {
            Tag info;
            if(!GetFileInformationByHandleEx(handle,9,out info,8) || (info.Attributes&0x410)!=0)
                throw new InvalidOperationException("Regular record required");
            var final=new StringBuilder(32768);
            uint count=GetFinalPathNameByHandle(handle,final,32768,0);
            if(count==0 || count>=32768 || !String.Equals(final.ToString(),@"\\?\"+path,
                StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Record identity changed");
            using(var stream=new FileStream(handle,FileAccess.Read)) {
                if(stream.Length<=0 || stream.Length>8192) throw new InvalidOperationException("Record limit");
                var data=new byte[(int)stream.Length];int offset=0;
                while(offset<data.Length) {
                    int read=stream.Read(data,offset,data.Length-offset);
                    if(read<=0) throw new InvalidOperationException("Incomplete record");
                    offset+=read;
                }
                return data;
            }
        }
    }
}
'@
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
        $diagnosticStage = 'nonsecret_record_read'
        $diagnosticRecord = $name
        $path = Join-Path $state $name
        $entry = @{record=$name;present=(Test-Path -LiteralPath $path);phase='absent'}
        if ($entry.present) {
            Assert-RegularAuditPath $path
            $raw = [LocusAuditRecordReaderV1]::Read($name)
            $diagnosticStage = 'nonsecret_record_parse'
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
    $diagnosticStage = 'profile_metadata'
    $diagnosticRecord = $null
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
    $chain = @()
    $cursor = $_.Exception
    for ($index=0; $index -lt 8 -and $null -ne $cursor; $index++) {
        $chain += @{error_type=$cursor.GetType().Name;hresult=('0x' + $cursor.HResult.ToString('x8'))}
        $cursor = $cursor.InnerException
    }
    @{operation='read_only_audit_state';reason='audit_state_inspection_failed';
        error_type=$_.Exception.GetType().Name;hresult=('0x' + $_.Exception.HResult.ToString('x8'));
        stage=$diagnosticStage;record=$diagnosticRecord;error_chain=$chain;
        state_changed=$false;activated=$false} | ConvertTo-Json -Compress -Depth 5
    exit 2
}
