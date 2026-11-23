; 符卡作业簿 · Inno Setup 7 安装包脚本（英文产物名）
; 先构建 PyInstaller 产物：dist\SpellCardHomework\
; 运行：ISCC.exe installer\SpellCardHomework.iss

#define MyAppName "SpellCardHomework"
#define MyAppDisplayName "符卡作业簿"
#define MyAppVersion "1.0.6-rc.03"
#define MyAppFileVersion "1.0.6.3"
#define MyAppPublisher "Shinichi, Fastrof & 会哈气の祥"
#define MyAppExeName "SpellCardHomework.exe"
#define MyAppURL "https://github.com/Jerry9335/SpellCardHomework"

[Setup]
AppId={{8F3A9C21-5B7D-4E6A-9C2F-1D4B7E8A6C10}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} {#MyAppVersion}
VersionInfoVersion={#MyAppFileVersion}
VersionInfoProductVersion={#MyAppFileVersion}
VersionInfoProductName={#MyAppDisplayName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDisplayName} 安装程序
VersionInfoCopyright=Copyright (C) 2025 Shinichi, Fastrof, 会哈气の祥
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\SpellCardHomework
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SpellCardHomework-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
LicenseFile=EULA.txt
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "resetlicense"; Description: "清除本机授权与试用记录（重新激活）"; GroupDescription: "其他任务"; Flags: unchecked

[Files]
Source: "..\dist\SpellCardHomework\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "使用说明-1.0.6-rc.03.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "符卡作业簿"
Name: "{group}\使用说明"; Filename: "{app}\使用说明-1.0.6-rc.03.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; AppUserModelID: "符卡作业簿"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppDisplayName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userappdata}\SpellCardHomework\license.json"
Type: files; Name: "{userappdata}\SpellCardHomework\trial.json"
Type: files; Name: "{localappdata}\SpellCardHomework\.spellcard_trial"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('resetlicense') then
  begin
    DeleteFile(ExpandConstant('{userappdata}\SpellCardHomework\license.json'));
    DeleteFile(ExpandConstant('{userappdata}\SpellCardHomework\trial.json'));
    DeleteFile(ExpandConstant('{localappdata}\SpellCardHomework\.spellcard_trial'));
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Shinichi\SpellCardHomework');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Shinichi\SpellCardHomework');
  end;
end;
