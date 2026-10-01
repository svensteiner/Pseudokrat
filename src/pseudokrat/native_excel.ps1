param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
# A kernel-owned job kills only the new Excel instance when this worker exits,
# including when Python terminates this worker after a timeout.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CalcJob {
 [DllImport("kernel32.dll")] public static extern IntPtr CreateJobObject(IntPtr a, string n);
 [DllImport("kernel32.dll")] public static extern bool SetInformationJobObject(IntPtr j, int c, IntPtr p, uint l);
 [DllImport("kernel32.dll")] public static extern bool AssignProcessToJobObject(IntPtr j, IntPtr p);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
'@
$excel = $null
$book = $null
$job = [IntPtr]::Zero
$owned = $false
try {
 $existing = @(Get-Process EXCEL -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
 $excel = New-Object -ComObject Excel.Application
 [uint32]$excelPid = 0
 [void][CalcJob]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$excelPid)
 if ($excelPid -eq 0 -or $existing -contains $excelPid) { throw 'Ownership unavailable' }
 $owned = $true
 $job = [CalcJob]::CreateJobObject([IntPtr]::Zero, $null)
 if ($job -eq [IntPtr]::Zero) { throw 'Job unavailable' }
 # JOBOBJECT_EXTENDED_LIMIT_INFORMATION: limit flags at byte 16 on Win32/64.
 $size = if ([IntPtr]::Size -eq 8) { 144 } else { 112 }
 $limits = [Runtime.InteropServices.Marshal]::AllocHGlobal($size)
 try {
  for ($i=0; $i -lt $size; $i++) { [Runtime.InteropServices.Marshal]::WriteByte($limits,$i,0) }
  [Runtime.InteropServices.Marshal]::WriteInt32($limits,16,0x2000)
  if (-not [CalcJob]::SetInformationJobObject($job,9,$limits,$size)) { throw 'Job setup failed' }
 } finally { [Runtime.InteropServices.Marshal]::FreeHGlobal($limits) }
 $excelProcess = Get-Process -Id $excelPid
 if (-not [CalcJob]::AssignProcessToJobObject($job,$excelProcess.Handle)) { throw 'Job assignment failed' }
 $excel.Visible = $false
 $excel.DisplayAlerts = $false
 $excel.EnableEvents = $false
 $excel.AskToUpdateLinks = $false
 $excel.AutomationSecurity = 3
 $book = $excel.Workbooks.Open((Join-Path $Directory 'input.xlsx'),0,$true)
 $excel.Iteration = $false
 $excel.CalculateFullRebuild()
 if ($excel.CalculationState -ne 0) { throw 'Calculation incomplete' }
 $request = Get-Content -LiteralPath (Join-Path $Directory 'request.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 $cells = @{}
 foreach ($entry in $request.PSObject.Properties) {
  $sheet = $book.Worksheets.Item($entry.Name)
  $sheet.Visible = -1
  $sheet.Activate()
  if ($null -ne $excel.CircularReference) { throw 'Circular reference' }
  $values = @{}
  foreach ($address in $entry.Value) {
   $cell = $sheet.Range($address)
   if ($excel.WorksheetFunction.IsError($cell)) { throw 'Formula error' }
   $value = $cell.Value2
   if ($null -eq $value -or ($value -is [string] -and $value.Length -eq 0)) { throw 'Missing result' }
   $values[$address] = @{ value = $value }
   [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($cell)
  }
  $cells[$entry.Name] = $values
  [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet)
 }
 @{ engine = 'Microsoft Excel'; version = $excel.Version; cells = $cells } |
  ConvertTo-Json -Depth 10 -Compress | Set-Content -LiteralPath (Join-Path $Directory 'result.json') -Encoding UTF8
} catch {
 exit 20
} finally {
 if ($null -ne $book) { try { $book.Close($false) } catch {} }
 if ($owned -and $null -ne $excel) { try { $excel.Quit() } catch {} }
 if ($job -ne [IntPtr]::Zero) { [void][CalcJob]::CloseHandle($job) }
}
