cd E:\ABU\AL_BURAQ
$ignored = @('build\dist','*.gguf','data\logs','__pycache__')
$total = 0
Get-ChildItem -Recurse -File | Where-Object {
  $_.FullName -notmatch 'build\\dist' -and
  $_.Extension -ne '.gguf' -and
  $_.FullName -notmatch '__pycache__' -and
  $_.FullName -notmatch 'data\\logs'
} | ForEach-Object { $script:total += $_.Length }
"{0:N2} GB would actually be tracked by git" -f ($total/1GB)
