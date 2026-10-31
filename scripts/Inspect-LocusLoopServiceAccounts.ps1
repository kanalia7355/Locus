#Requires -Version 5.1
# Read-only: fixed account metadata and LSA rights. No password/key access.
param([string]$Bundle, [string]$ManifestSha256)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    if ([IntPtr]::Size -ne 8) { throw '64-bit PowerShell required' }
    $modulePath = Join-Path $PSHOME 'Modules\Microsoft.PowerShell.LocalAccounts\1.0.0.0\Microsoft.PowerShell.LocalAccounts.psd1'
    Import-Module $modulePath
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class LocusAccountInspectionV1 {
    [StructLayout(LayoutKind.Sequential)] struct Attributes {
        public uint Length; public IntPtr Root, Name; public uint Flags;
        public IntPtr Security, Quality;
    }
    [StructLayout(LayoutKind.Sequential)] struct Text {
        public ushort Length, Maximum; public IntPtr Buffer;
    }
    [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(
        IntPtr system, ref Attributes attributes, uint rights, out IntPtr policy);
    [DllImport("advapi32.dll")] static extern uint LsaEnumerateAccountRights(
        IntPtr policy, byte[] sid, out IntPtr rights, out uint count);
    [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr value);
    [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr value);
    static string Code(uint status) { return "0x" + status.ToString("x8"); }
    public static Dictionary<string, object> Read(string sidText) {
        var result = new Dictionary<string, object>();
        var sid = new SecurityIdentifier(sidText);
        var binary = new byte[sid.BinaryLength]; sid.GetBinaryForm(binary, 0);
        var attributes = new Attributes { Length=(uint)Marshal.SizeOf(typeof(Attributes)) };
        IntPtr policy;
        // Access check matching installer; no mutating entry point is present.
        uint status=LsaOpenPolicy(IntPtr.Zero, ref attributes, 0x810, out policy);
        result["installer_policy_access_status"]=Code(status);
        if (status==0) LsaClose(policy);
        status=LsaOpenPolicy(IntPtr.Zero, ref attributes, 0x800, out policy);
        result["read_policy_status"]=Code(status);
        if (status!=0) return result;
        IntPtr values=IntPtr.Zero;
        try {
            uint count;
            status=LsaEnumerateAccountRights(policy, binary, out values, out count);
            result["read_rights_status"]=Code(status);
            if (status!=0) return result;
            if (count>256) throw new InvalidOperationException();
            var names=new HashSet<string>(StringComparer.Ordinal);
            for (int i=0; i<(int)count; i++) {
                var text=(Text)Marshal.PtrToStructure(IntPtr.Add(values,i*Marshal.SizeOf(typeof(Text))),typeof(Text));
                if (text.Length>512 || text.Length%2!=0) throw new InvalidOperationException();
                names.Add(Marshal.PtrToStringUni(text.Buffer,text.Length/2));
            }
            result["service_logon"]=names.Contains("SeServiceLogonRight");
            result["deny_interactive"]=names.Contains("SeDenyInteractiveLogonRight");
            result["deny_remote_interactive"]=names.Contains("SeDenyRemoteInteractiveLogonRight");
            return result;
        } finally { if(values!=IntPtr.Zero)LsaFreeMemory(values); LsaClose(policy); }
    }
}
'@
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        $administrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } finally { $identity.Dispose() }
    $result = @{ operation = 'read_only_account_diagnostics'; activated = $false;
        administrator = $administrator; accounts = @() }
    foreach ($role in @('review', 'merge')) {
        $name = 'locus_loop_' + $role
        $user = Get-LocalUser -Name $name -ErrorAction SilentlyContinue
        $entry = @{ role = $role; present = ($null -ne $user) }
        if ($null -ne $user) {
            $entry.sid = $user.SID.Value
            $entry.enabled = $user.Enabled
            $entry.profile_registered = Test-Path -LiteralPath (
                'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $user.SID.Value)
            $entry.rights = [LocusAccountInspectionV1]::Read($user.SID.Value)
        }
        $result.accounts += $entry
    }
    $result | ConvertTo-Json -Depth 6
} catch {
    [Console]::Error.WriteLine('{"operation":"read_only_account_diagnostics","reason":"inspection_failed","activated":false}')
    exit 2
}
