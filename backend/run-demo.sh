#!/usr/bin/env bash
# Runs the 3 video workflows (Mac/Linux). Needs Java 17+.
set -e
cd "$(dirname "$0")"
rm -rf out && mkdir out
javac --release 17 -d out $(find src/main/java -name "*.java")
java -Dstdout.encoding=UTF-8 -cp out com.itsm.demo.Demo
