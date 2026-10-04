Invoke-WebRequest -Uri "https://dist.memurai.com/releases/Memurai-Developer/4.1.2/Memurai-Developer-v4.1.2.msi" -OutFile "Memurai.msi"
Start-Process -FilePath "msiexec.exe" -ArgumentList "/i Memurai.msi /quiet /norestart" -Verb RunAs -Wait
