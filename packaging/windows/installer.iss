; Inno Setup script. Build: ISCC.exe /DAppVersion=1.1.0 packaging\windows\installer.iss
; Installs for the current user by default (no administrator rights), so the in-app
; updater can upgrade silently; "Install for all users" is offered on the first page.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Solution Preparation Calculator"
#define AppExe "SolutionCalculator.exe"
#define Root SourcePath + "..\.."

[Setup]
AppId={{6F1E3C2A-7A55-4F0B-9D3E-5C2B8A41D7E1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Jongsu Lim
AppPublisherURL=https://github.com/jongsu-king/perovskite-opv-solution-calculator
AppSupportURL=https://github.com/jongsu-king/perovskite-opv-solution-calculator/issues
AppUpdatesURL=https://github.com/jongsu-king/perovskite-opv-solution-calculator/releases
DefaultDirName={autopf}\Solution Calculator
DefaultGroupName=Solution Calculator
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Root}\dist
OutputBaseFilename=Solution-Calculator-{#AppVersion}-windows-x64-setup
SetupIconFile={#Root}\packaging\icons\app.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile={#Root}\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Root}\dist\SolutionCalculator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
