@echo off
:: 1. Diet chuong trinh ngam (Im lang, khong hien thong bao)
taskkill /F /IM "DLP_Guard.exe" /T >nul 2>&1

:: 2. Cho 1 giay de Windows kip nha file ra (Tranh loi file rac)
timeout /t 1 /nobreak >nul

:: 3. Chay lenh go bo (Lenh nay se kich hoat Popup Da go bo... trong code Python)
"DLP_Guard.exe" --remove