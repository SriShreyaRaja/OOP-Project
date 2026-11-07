#!/usr/bin/env bash
# Runs all JUnit tests (Mac/Linux). Downloads the JUnit runner once.
set -e
cd "$(dirname "$0")"
JUNIT=junit-platform-console-standalone-1.10.1.jar
[ -f "$JUNIT" ] || curl -sL -o "$JUNIT" "https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.10.1/$JUNIT"
rm -rf out && mkdir -p out/main out/test
javac --release 17 -d out/main $(find src/main/java -name "*.java")
javac --release 17 -d out/test -cp "out/main:$JUNIT" $(find src/test/java -name "*.java")
java -Dstdout.encoding=UTF-8 -jar "$JUNIT" execute -cp out/main:out/test --scan-classpath --details=tree
