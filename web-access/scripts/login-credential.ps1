<#
.SYNOPSIS
  web-access login credential helper backed by Windows Credential Manager.

.DESCRIPTION
  Stores site login passwords as Generic credentials (persist: this computer,
  current user; not roamed). Key: origin + account.

  User actions (run in your own PowerShell window):
    Add     -Origin https://idp.example.edu -Account <id>  # password typed in a secure prompt
    Check   -Origin <origin> [-Account <id>]               # reports presence only
    List    [-Origin <origin>]                             # masked accounts only
    Remove  -Origin <origin> -Account <id>
    SelfTest                                               # synthetic write/read/delete round trip

  BrokerRead is the internal channel for the web-access Broker: it reads a JSON
  request from stdin and writes one JSON line to stdout. Models and other tools
  must not call it. Passwords never appear in arguments, logs or files.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Add', 'Check', 'List', 'Remove', 'SelfTest', 'BrokerRead')]
  [string]$Action,
  [string]$Origin,
  [string]$Account
)

$ErrorActionPreference = 'Stop'
$TargetPrefix = 'web-access/login|'

if (-not ('WebAccessCredentialStore' -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class WebAccessCredentialStore {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  private struct CREDENTIAL {
    public UInt32 Flags;
    public UInt32 Type;
    public string TargetName;
    public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public UInt32 CredentialBlobSize;
    public IntPtr CredentialBlob;
    public UInt32 Persist;
    public UInt32 AttributeCount;
    public IntPtr Attributes;
    public string TargetAlias;
    public string UserName;
  }

  private const UInt32 CRED_TYPE_GENERIC = 1;
  private const UInt32 CRED_PERSIST_LOCAL_MACHINE = 2;
  private const int ERROR_NOT_FOUND = 1168;

  [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern bool CredWrite(ref CREDENTIAL credential, UInt32 flags);
  [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);
  [DllImport("advapi32.dll", EntryPoint = "CredEnumerateW", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern bool CredEnumerate(string filter, UInt32 flags, out UInt32 count, out IntPtr credentials);
  [DllImport("advapi32.dll", EntryPoint = "CredDeleteW", CharSet = CharSet.Unicode, SetLastError = true)]
  private static extern bool CredDelete(string target, UInt32 type, UInt32 flags);
  [DllImport("advapi32.dll")]
  private static extern void CredFree(IntPtr buffer);

  // secret points to UTF-16 characters (e.g. a BSTR from a SecureString).
  public static void Write(string target, string user, string comment, IntPtr secret, int chars) {
    CREDENTIAL c = new CREDENTIAL();
    c.Type = CRED_TYPE_GENERIC;
    c.TargetName = target;
    c.UserName = user;
    c.Comment = comment;
    c.CredentialBlob = secret;
    c.CredentialBlobSize = (UInt32)(chars * 2);
    c.Persist = CRED_PERSIST_LOCAL_MACHINE;
    if (!CredWrite(ref c, 0)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
  }

  public static string[] ListUsers(string prefix, string comment) {
    UInt32 count; IntPtr list;
    if (!CredEnumerate(prefix + "*", 0, out count, out list)) {
      int error = Marshal.GetLastWin32Error();
      if (error == ERROR_NOT_FOUND) return new string[0];
      throw new System.ComponentModel.Win32Exception(error);
    }
    List<string> users = new List<string>();
    try {
      for (int i = 0; i < count; i++) {
        IntPtr item = Marshal.ReadIntPtr(list, i * IntPtr.Size);
        CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(item, typeof(CREDENTIAL));
        if (c.Type != CRED_TYPE_GENERIC || c.TargetName == null || !c.TargetName.StartsWith(prefix, StringComparison.Ordinal)) continue;
        if (!String.Equals(c.Comment, comment, StringComparison.Ordinal)) continue;
        if (!String.IsNullOrEmpty(c.UserName) && c.TargetName == prefix + c.UserName) users.Add(c.UserName);
      }
    } finally { CredFree(list); }
    users.Sort(StringComparer.Ordinal);
    return users.ToArray();
  }

  public static string[] ListTargets(string prefix) {
    UInt32 count; IntPtr list;
    if (!CredEnumerate(prefix + "*", 0, out count, out list)) {
      int error = Marshal.GetLastWin32Error();
      if (error == ERROR_NOT_FOUND) return new string[0];
      throw new System.ComponentModel.Win32Exception(error);
    }
    List<string> targets = new List<string>();
    try {
      for (int i = 0; i < count; i++) {
        IntPtr item = Marshal.ReadIntPtr(list, i * IntPtr.Size);
        CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(item, typeof(CREDENTIAL));
        if (c.Type == CRED_TYPE_GENERIC && c.TargetName != null && c.TargetName.StartsWith(prefix, StringComparison.Ordinal)) targets.Add(c.TargetName);
      }
    } finally { CredFree(list); }
    targets.Sort(StringComparer.Ordinal);
    return targets.ToArray();
  }

  // Returns UTF-16 bytes, or null when absent. Callers clear the array.
  public static byte[] ReadSecret(string target) {
    IntPtr pointer;
    if (!CredRead(target, CRED_TYPE_GENERIC, 0, out pointer)) {
      int error = Marshal.GetLastWin32Error();
      if (error == ERROR_NOT_FOUND) return null;
      throw new System.ComponentModel.Win32Exception(error);
    }
    try {
      CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(pointer, typeof(CREDENTIAL));
      byte[] bytes = new byte[c.CredentialBlobSize];
      if (c.CredentialBlobSize > 0) Marshal.Copy(c.CredentialBlob, bytes, 0, (int)c.CredentialBlobSize);
      return bytes;
    } finally { CredFree(pointer); }
  }

  public static bool Delete(string target) {
    if (CredDelete(target, CRED_TYPE_GENERIC, 0)) return true;
    int error = Marshal.GetLastWin32Error();
    if (error == ERROR_NOT_FOUND) return false;
    throw new System.ComponentModel.Win32Exception(error);
  }
}
'@
}

function ConvertTo-LoginOrigin([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) { throw 'Origin is required, for example https://idp.example.edu' }
  $uri = $null
  if (-not [Uri]::TryCreate($Value.Trim(), [UriKind]::Absolute, [ref]$uri)) { throw 'Origin is not an absolute URL.' }
  if ($uri.Scheme -ne 'https') { throw 'Only https origins are accepted.' }
  if ($uri.UserInfo) { throw 'Origin must not contain user information.' }
  if (($uri.AbsolutePath -ne '/') -or $uri.Query -or $uri.Fragment) {
    throw 'Pass the origin only (scheme://host[:port]), without path, query or fragment.'
  }
  $origin = 'https://' + $uri.IdnHost.ToLowerInvariant()
  if (-not $uri.IsDefaultPort) { $origin += ':' + $uri.Port }
  return $origin
}

function Get-AccountPrefix([string]$NormalizedOrigin) { return $TargetPrefix + $NormalizedOrigin + '|' }

function Assert-Account([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) { throw 'Account is required.' }
  $trimmed = $Value.Trim()
  if ($trimmed.Length -gt 256 -or $trimmed.Contains('|')) { throw 'Account must be at most 256 characters and must not contain "|".' }
  return $trimmed
}

function Format-MaskedAccount([string]$Value) {
  if ($Value.Length -le 2) { return '*' * $Value.Length }
  if ($Value.Length -le 6) { return $Value.Substring(0, 1) + ('*' * ($Value.Length - 2)) + $Value.Substring($Value.Length - 1) }
  return $Value.Substring(0, 2) + ('*' * ($Value.Length - 4)) + $Value.Substring($Value.Length - 2)
}

function Write-SecureStringCredential([string]$NormalizedOrigin, [string]$User, [Security.SecureString]$Secret) {
  if ($Secret.Length -lt 1) { throw 'Password is empty; nothing was saved.' }
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
  try {
    [WebAccessCredentialStore]::Write((Get-AccountPrefix $NormalizedOrigin) + $User, $User, $NormalizedOrigin, $bstr, $Secret.Length)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

# Selection rule shared by BrokerRead and SelfTest: an explicit account must be
# configured; otherwise exactly one account for the origin is required.
function Get-BrokerCredential([string]$NormalizedOrigin, [string]$Wanted) {
  $users = @([WebAccessCredentialStore]::ListUsers((Get-AccountPrefix $NormalizedOrigin), $NormalizedOrigin))
  if ($Wanted) {
    $Wanted = $Wanted.Trim()
    if ($users -notcontains $Wanted) { return @{ status = 'account_not_configured'; accountCount = $users.Count } }
    $user = $Wanted
  } elseif ($users.Count -eq 0) {
    return @{ status = 'not_configured'; accountCount = 0 }
  } elseif ($users.Count -gt 1) {
    return @{ status = 'account_ambiguous'; accountCount = $users.Count }
  } else {
    $user = $users[0]
  }
  $bytes = [WebAccessCredentialStore]::ReadSecret((Get-AccountPrefix $NormalizedOrigin) + $user)
  if (-not $bytes -or $bytes.Length -lt 2) { return @{ status = 'not_configured'; accountCount = $users.Count } }
  $utf8 = [Text.Encoding]::UTF8.GetBytes([Text.Encoding]::Unicode.GetString($bytes))
  [Array]::Clear($bytes, 0, $bytes.Length)
  $encoded = [Convert]::ToBase64String($utf8)
  [Array]::Clear($utf8, 0, $utf8.Length)
  return @{ status = 'ok'; account = $user; secret = $encoded; accountCount = $users.Count }
}

function Write-BrokerResult($Value) {  [Console]::Out.WriteLine(($Value | ConvertTo-Json -Compress))
}

switch ($Action) {
  'Add' {
    $normalized = ConvertTo-LoginOrigin $Origin
    $user = Assert-Account $Account
    $credential = Get-Credential -UserName $user -Message "web-access: save the login password for $normalized (stored in Windows Credential Manager on this computer only)"
    if (-not $credential) { throw 'Cancelled; nothing was saved.' }
    $enteredUser = ($credential.UserName -replace '^\\', '').Trim()
    if ($enteredUser -ne $user) { throw 'The account in the prompt differs from -Account; nothing was saved.' }
    Write-SecureStringCredential $normalized $user $credential.Password
    $credential = $null
    Write-Output ("Saved: {0} account {1}. The password is not displayed." -f $normalized, (Format-MaskedAccount $user))
  }
  'Check' {
    $normalized = ConvertTo-LoginOrigin $Origin
    $users = [WebAccessCredentialStore]::ListUsers((Get-AccountPrefix $normalized), $normalized)
    if ($Account) {
      $user = Assert-Account $Account
      $present = $users -contains $user
      Write-Output ("{0} account {1}: {2}" -f $normalized, (Format-MaskedAccount $user), $(if ($present) { 'configured' } else { 'not configured' }))
      if (-not $present) { exit 2 }
    } else {
      Write-Output ("{0}: {1} account(s) configured" -f $normalized, $users.Count)
      if ($users.Count -eq 0) { exit 2 }
    }
  }
  'List' {
    if ($Origin) {
      $normalized = ConvertTo-LoginOrigin $Origin
      foreach ($user in [WebAccessCredentialStore]::ListUsers((Get-AccountPrefix $normalized), $normalized)) {
        Write-Output ("{0}  {1}" -f $normalized, (Format-MaskedAccount $user))
      }
    } else {
      foreach ($target in [WebAccessCredentialStore]::ListTargets($TargetPrefix)) {
        $parts = $target.Substring($TargetPrefix.Length).Split('|')
        if ($parts.Count -eq 2) { Write-Output ("{0}  {1}" -f $parts[0], (Format-MaskedAccount $parts[1])) }
      }
    }
  }
  'Remove' {
    $normalized = ConvertTo-LoginOrigin $Origin
    $user = Assert-Account $Account
    $removed = [WebAccessCredentialStore]::Delete((Get-AccountPrefix $normalized) + $user)
    Write-Output ("{0} account {1}: {2}" -f $normalized, (Format-MaskedAccount $user), $(if ($removed) { 'removed' } else { 'was not configured' }))
  }
  'SelfTest' {
    $normalized = 'https://web-access-selftest.invalid'
    $user = 'selftest-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $random = New-Object byte[] 18
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($random)
    $secure = New-Object Security.SecureString
    foreach ($ch in [Convert]::ToBase64String($random).ToCharArray()) { $secure.AppendChar($ch) }
    $expected = [Convert]::ToBase64String($random)
    $ok = $false
    try {
      Write-SecureStringCredential $normalized $user $secure
      $users = [WebAccessCredentialStore]::ListUsers((Get-AccountPrefix $normalized), $normalized)
      $read = Get-BrokerCredential $normalized ''
      $decoded = if ($read.status -eq 'ok') { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($read.secret)) } else { $null }
      $ok = ($users -contains $user) -and ($read.account -eq $user) -and ($decoded -eq $expected)
      $read = $null; $decoded = $null
    } finally {
      [void][WebAccessCredentialStore]::Delete((Get-AccountPrefix $normalized) + $user)
      $secure.Dispose()
    }
    $left = [WebAccessCredentialStore]::ListUsers((Get-AccountPrefix $normalized), $normalized)
    if ($ok -and $left.Count -eq 0) { Write-Output 'SelfTest passed: write, list, read and delete work; the synthetic entry was removed.' }
    else { Write-Output 'SelfTest failed.'; exit 1 }
  }
  'BrokerRead' {
    try {
      $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
      $normalized = ConvertTo-LoginOrigin ([string]$request.origin)
    } catch {
      Write-BrokerResult @{ status = 'invalid_request' }; exit 0
    }
    try {
      Write-BrokerResult (Get-BrokerCredential $normalized ([string]$request.account))
    } catch {
      Write-BrokerResult @{ status = 'store_unavailable' }
    }
  }
}
