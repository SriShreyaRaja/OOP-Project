@echo off
chcp 65001 >nul
REM Runs the 3 video workflows. Needs Java 17+ (check with: java -version)
cd /d %~dp0
if exist out rmdir /s /q out
mkdir out
dir /s /b src\main\java\*.java > sources.txt
javac --release 17 -d out @sources.txt
if errorlevel 1 ( echo Compile failed & del sources.txt & pause & exit /b 1 )
del sources.txt
java -Dstdout.encoding=UTF-8 -Dfile.encoding=UTF-8 -cp out com.itsm.demo.Demo
pause
