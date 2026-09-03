; Inno Setup script for Deadlock Draft Viewer.
;
; Prerequisite: run `python build.py` from the project root first, so
; dist\DeadlockDraftViewer\ exists (the exe, its bundled runtime, and a
; plain "assets" folder copied there by build.py -- see that script and
; hero.py's resource_path() for why assets are shipped as loose files
; rather than bundled into the exe).
;
; Compile with Inno Setup 6 (https://jrsoftware.org/isinfo.php) on Windows:
;     ISCC.exe installer\installer.iss
; or open this file in the Inno Setup Compiler GUI and press Build.
;
; Output: dist\installer\DeadlockDraftViewer-Setup-<version>.exe

#define MyAppName "Deadlock Draft Viewer"
#define MyAppVersion "0.0.2"
#define MyAppPublisher "Deadlock Draft Viewer"
#define MyAppExeName "DeadlockDraftViewer.exe"
#define ProjectRoot "..\"
#define BuildDir ProjectRoot + "dist\DeadlockDraftViewer"

[Setup]
AppId={{6C8B0F0B-6E5C-4C7B-9C2E-6E9E9B7B6B39}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Installed per-user, no admin rights required. This keeps the shipped
; "assets" folder freely writable by the user (a Program Files install
; would need elevation to edit hero images/voice lines there).
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#ProjectRoot}dist\installer
OutputBaseFilename=DeadlockDraftViewer-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#ProjectRoot}assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Pulls in the exe, PyInstaller's bundled runtime, AND the plain "assets"
; folder that build.py copies there -- all shipped as loose, editable files.
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
