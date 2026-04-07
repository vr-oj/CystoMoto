; SPDX-License-Identifier: GPL-3.0-only
; CystoMoto Inno Setup Script
; Requires Inno Setup 6.x — https://jrsoftware.org/isinfo.php
;
; Build command (from repo root, after running PyInstaller):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows\CystoMoto.iss
;
; This script expects PyInstaller to have produced dist\CystoMoto\ first.

#define MyAppName        "CystoMoto"
#define MyAppPublisher   "CystoMoto"
#define MyAppExeName     "CystoMoto.exe"
#define MyAppDescription "Live Pressure Data Logger for Cystometry"

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#ifndef MyAppURL
  #define MyAppURL "https://github.com/valdovegarodr/CystoMoto"
#endif

; Relative path from installer\windows\ to the PyInstaller one-dir output
#define DistPath "..\..\dist\CystoMoto"

[Setup]
; ── Identification ────────────────────────────────────────────────────────────
; IMPORTANT: Never change this AppId once the installer has been published.
; Windows uses it to link installations to the uninstaller entry.
AppId={{B2D5E3A1-4C7F-4B9E-AE23-2E7F6D8C9B4A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; ── Install location ──────────────────────────────────────────────────────────
; {autopf} = "C:\Program Files" on 64-bit Windows
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
PrivilegesRequired=admin

; ── Start Menu ────────────────────────────────────────────────────────────────
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no

; ── Output ────────────────────────────────────────────────────────────────────
; Puts the finished installer in installer_output\ at the repo root
OutputDir=..\..\installer_output
OutputBaseFilename=CystoMoto_Setup_v{#MyAppVersion}
SetupIconFile=..\..\cysto_app\ui\icons\CystoMoto.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; ── Architecture ─────────────────────────────────────────────────────────────
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; ── Appearance ────────────────────────────────────────────────────────────────
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; ── Misc ──────────────────────────────────────────────────────────────────────
LicenseFile=..\..\LICENSE
MinVersion=6.1.7600

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut (recommended)"; \
    GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
; Entire PyInstaller one-dir output (CystoMoto.exe + all DLLs + Qt plugins + data)
Source: "{#DistPath}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    Comment: "{#MyAppDescription}"
Name: "{group}\Uninstall {#MyAppName}"; \
    Filename: "{uninstallexe}"

; Desktop shortcut (only if user checked the task)
Name: "{autodesktop}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    Comment: "{#MyAppDescription}"; \
    Tasks: desktopicon

[Run]
; Offer to launch the app after the installer finishes
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the install directory entirely on uninstall (catches runtime-created files)
Type: filesandordirs; Name: "{app}"
