@echo off
"C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" "Falcor.sln" /p:Configuration=ReleaseD3D12 /m:24 /v:m
Bin\x64\Release\Mogwai.exe --script=main.py
