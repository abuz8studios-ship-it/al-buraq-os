$ErrorActionPreference = 'Stop'
cd E:\ABU\AL_BURAQ

Write-Host '=== SIZE AUDIT — top 20 largest files ==='
Get-ChildItem -Recurse -File | Sort-Object Length -Descending | Select-Object -First 20 | ForEach-Object {
  "{0,10:N1} MB   {1}" -f ($_.Length/1MB), $_.FullName.Replace('E:\ABU\AL_BURAQ\','')
}

Write-Host ''
Write-Host '=== TOTAL SIZE ==='
$total = (Get-ChildItem -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
"{0:N2} GB" -f $total

Write-Host ''
Write-Host '=== SECRET SCAN — grep for common key patterns in text files ==='
$patterns = 'sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}|xox[baprs]-[0-9a-zA-Z\-]+|-----BEGIN.*PRIVATE KEY-----|BOT_TOKEN|API_KEY.*=.*[a-zA-Z0-9]{20,}|Bearer [a-zA-Z0-9]{20,}'
$textExt = @('.py','.js','.json','.md','.txt','.cmd','.ps1','.yaml','.yml','.env','.cfg','.ini')
Get-ChildItem -Recurse -File | Where-Object { $textExt -contains $_.Extension } | ForEach-Object {
  $hits = Select-String -Path $_.FullName -Pattern $patterns -ErrorAction SilentlyContinue
  if ($hits) {
    foreach ($h in $hits) {
      Write-Host "HIT: $($_.FullName.Replace('E:\ABU\AL_BURAQ\','')):$($h.LineNumber)"
    }
  }
}

Write-Host ''
Write-Host '=== .env / secret-named files ==='
Get-ChildItem -Recurse -File | Where-Object { $_.Name -match '\.env$|secret|credential|\.pem$|\.key$' } | ForEach-Object {
  $_.FullName.Replace('E:\ABU\AL_BURAQ\','')
}

Write-Host ''
Write-Host '=== SCAN COMPLETE ==='
