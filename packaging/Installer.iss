; Inno Setup script for IPVidex (Windows x64 installer).
;
; Requires Inno Setup 6: https://jrsoftware.org/isdl.php
;
; Build steps:
;   1) Produce the portable folder payload first:
;        .\packaging\Build.ps1 -Mode onedir
;   2) Compile this installer:
;        & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\Installer.iss
;   3) Result: dist\IPVidex-Setup.exe

#define AppName "IPVidex"
#define AppExe "IPVidex.exe"
#define AppVersion "1.0.1"
#define AppPublisher "Vivoo"

[Setup]
; Fixed identity so later versions upgrade this installation. Never change it.
AppId={{9D168724-0502-4BA7-9CCE-18F71AD15EDA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\IPVidex
DefaultGroupName=IPVidex
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\IPVidex.ico
OutputDir=..\dist
OutputBaseFilename=IPVidex-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Installing into Program Files needs admin; use lowest + {localappdata} if you
; want a per-user install with no UAC prompt.
PrivilegesRequired=admin

[Files]
; The entire onedir payload produced by Build.ps1 -Mode onedir.
Source: "..\dist\IPVidex\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\IPVidex"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall IPVidex"; Filename: "{uninstallexe}"
Name: "{autodesktop}\IPVidex"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch IPVidex now"; Flags: nowait postinstall skipifsilent
