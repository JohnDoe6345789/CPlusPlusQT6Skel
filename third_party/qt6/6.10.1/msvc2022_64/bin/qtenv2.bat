@echo off
echo Setting up environment for Qt usage...
set PATH=third_party\qt6\6.10.1\msvc2022_64\bin;%PATH%
cd /D third_party\qt6\6.10.1\msvc2022_64
echo Remember to call vcvarsall.bat to complete environment setup!
