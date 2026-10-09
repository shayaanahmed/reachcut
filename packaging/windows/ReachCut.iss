#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef StageDir
  #define StageDir "..\..\build\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\build\installers"
#endif

[Setup]
AppId={{E60CCBB7-0773-4A8F-86C1-B4BEC4446E61}
AppName=ReachCut
AppVersion={#AppVersion}
AppPublisher=ReachCut
DefaultDirName={localappdata}\Programs\ReachCut
DefaultGroupName=ReachCut
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ReachCut-{#AppVersion}-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=ReachCut
VersionInfoCompany=ReachCut
VersionInfoDescription=ReachCut local AI video clipping application

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start ReachCut when I sign in"; GroupDescription: "Background service:"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "launch.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch-background.vbs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ReachCut"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch.vbs"""; WorkingDir: "{app}"
Name: "{autodesktop}\ReachCut"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\ReachCut agent"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch-background.vbs"""; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch.vbs"""; Description: "Open ReachCut"; Flags: nowait postinstall skipifsilent
