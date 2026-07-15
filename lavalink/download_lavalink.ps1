$ErrorActionPreference = "Stop"
$Url = "https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar"
Invoke-WebRequest -Uri $Url -OutFile (Join-Path $PSScriptRoot "Lavalink.jar")
Write-Host "Lavalink downloaded. The YouTube plugin downloads automatically at startup."
