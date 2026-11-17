<# User-invoked foreground capture. Does not launch, debug-attach, stop, or focus the target.
   -SelfTest only compiles the interop declarations and checks pure path comparisons.
#>
param(
    [string]$ExpectedExecutable,
    [string]$OutputDirectory,
    [ValidateRange(3,60)][int]$ForegroundSeconds = 8,
    [ValidateRange(1,30)][int]$IntervalSeconds = 5,
    [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class RecordedHangCapture {
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool QueryFullProcessImageName(IntPtr handle, uint flags, StringBuilder path, ref uint size);
    [DllImport("user32.dll")]
    static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("dbghelp.dll", SetLastError=true)]
    static extern bool MiniDumpWriteDump(IntPtr process, uint id, IntPtr file, uint type,
                                        IntPtr exception, IntPtr stream, IntPtr callback);
    public static bool SamePath(string left, string right) {
        return String.Equals(Path.GetFullPath(left), Path.GetFullPath(right), StringComparison.OrdinalIgnoreCase);
    }
    public static uint ForegroundProcessId() {
        uint id; GetWindowThreadProcessId(GetForegroundWindow(), out id); return id;
    }
    public static void Write(uint id, string expected, string path) {
        // PROCESS_QUERY_INFORMATION | PROCESS_VM_READ; no debug API or memory writes.
        IntPtr process = OpenProcess(0x410, false, id);
        if (process == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        try {
            uint capacity = 32768; var image = new StringBuilder((int)capacity);
            if (!QueryFullProcessImageName(process, 0, image, ref capacity))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            if (!SamePath(image.ToString(), expected)) throw new InvalidOperationException("Executable identity changed");
            if (ForegroundProcessId() != id) throw new InvalidOperationException("Target is no longer foreground");
            using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None)) {
                // FullMemory | FullMemoryInfo | ThreadInfo. No handle/token stream requested.
                if (!MiniDumpWriteDump(process, id, output.SafeFileHandle.DangerousGetHandle(), 0x1802,
                                       IntPtr.Zero, IntPtr.Zero, IntPtr.Zero))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        } finally { CloseHandle(process); }
    }
}
'@

if ($SelfTest) {
    if (-not [RecordedHangCapture]::SamePath('C:\fixture\game.exe', 'c:\fixture\game.exe')) { throw 'Case-insensitive identity test failed' }
    if ([RecordedHangCapture]::SamePath('C:\fixture\game.exe', 'C:\other\game.exe')) { throw 'Different-directory identity test failed' }
    'CAPTURE SELFTEST PASS: interop compiled; path guards passed; no process access'
    exit 0
}
if (-not $ExpectedExecutable -or -not $OutputDirectory) { throw 'ExpectedExecutable and OutputDirectory are required' }
$expected = (Resolve-Path -LiteralPath $ExpectedExecutable).Path
$candidates = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($expected)) -ErrorAction SilentlyContinue | Where-Object {
    try { [RecordedHangCapture]::SamePath($_.MainModule.FileName, $expected) } catch { $false }
})
if ($candidates.Count -ne 1) { throw 'Exactly one already-running process with the expected executable path is required' }
$target = $candidates[0]
$identityTime = $target.StartTime.ToUniversalTime().ToString('o')
$directory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $directory) { throw 'OutputDirectory already exists; existing dumps are never overwritten' }
[IO.Directory]::CreateDirectory($directory) | Out-Null
$events = [Collections.Generic.List[object]]::new()
$result = [ordered]@{ executable=$expected; process_id=$target.Id; start_utc=$identityTime; status='waiting'; captures=@(); events=$events }

function Wait-TargetForeground([int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    $since = $null
    $previous = -1L
    while ([DateTime]::UtcNow -lt $deadline) {
        $target.Refresh()
        if ($target.HasExited -or $target.StartTime.ToUniversalTime().ToString('o') -ne $identityTime) { throw 'Selected process exited or changed' }
        $front = [RecordedHangCapture]::ForegroundProcessId()
        if ($front -ne $previous) {
            $events.Add([ordered]@{ utc=[DateTime]::UtcNow.ToString('o'); target_foreground=($front -eq $target.Id) })
            $previous = $front
        }
        if ($front -eq $target.Id) {
            if ($null -eq $since) { $since = [DateTime]::UtcNow }
            if (([DateTime]::UtcNow - $since).TotalSeconds -ge $Seconds) { return }
        } else { $since = $null }
        Start-Sleep -Milliseconds 200
    }
    throw 'Foreground wait timed out; no window activation was attempted'
}

Write-Host "Switch back to the already-running game and keep it foreground. Capture begins after $ForegroundSeconds seconds."
Write-Host 'Two local snapshots will be written. Capture may briefly pause the process. No game launch or exit is performed.'
try {
    for ($index=1; $index -le 2; $index++) {
        $delay = if ($index -eq 1) { $ForegroundSeconds } else { $IntervalSeconds }
        Wait-TargetForeground $delay
        $path = Join-Path $directory ("foreground-{0}.dmp" -f $index)
        $before = [RecordedHangCapture]::ForegroundProcessId() -eq $target.Id
        $started = [DateTime]::UtcNow.ToString('o')
        [RecordedHangCapture]::Write([uint32]$target.Id, $expected, "$path.partial")
        $after = [RecordedHangCapture]::ForegroundProcessId() -eq $target.Id
        [IO.File]::Move("$path.partial", $path)
        $result.captures += [ordered]@{ path=$path; start_utc=$started; end_utc=[DateTime]::UtcNow.ToString('o');
            foreground_before=$before; foreground_after=$after; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    $result.status = 'captured'
    Write-Host "CAPTURE COMPLETE: $directory"
} catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    throw
} finally {
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $directory 'capture.json') -Encoding UTF8
}
