@echo off
set ANDROID_HOME=C:\Android\Sdk
set JAVA_HOME=C:\Program Files\ojdkbuild\java-17-openjdk-17.0.3.0.6-1

REM Accept all licenses first
echo Accepting licenses...
( echo y
  echo y
  echo y
  echo y
  echo y
  echo y
  echo y
  echo y
) | "C:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat" --sdk_root="C:\Android\Sdk" --licenses

REM Install required packages
echo Installing SDK packages...
( echo y
  echo y
) | "C:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat" --sdk_root="C:\Android\Sdk" "platform-tools" "platforms;android-34" "build-tools;34.0.0"

echo DONE
