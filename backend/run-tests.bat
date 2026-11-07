@echo off
chcp 65001 >nul
REM Runs all JUnit tests. Downloads the JUnit runner once (needs internet the first time).
cd /d %~dp0
set JUNIT=junit-platform-console-standalone-1.10.1.jar
if not exist %JUNIT% curl -L -o %JUNIT% https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.10.1/%JUNIT%
if exist out rmdir /s /q out
mkdir out\main out\test
dir /s /b src\main\java\*.java > sources.txt
javac --release 17 -d out\main @sources.txt
dir /s /b src\test\java\*.java > tests.txt
javac --release 17 -d out\test -cp out\main;%JUNIT% @tests.txt
del sources.txt tests.txt
java -Dstdout.encoding=UTF-8 -jar %JUNIT% execute -cp out\main;out\test --scan-classpath --details=tree
pause
