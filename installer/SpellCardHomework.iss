; 符卡作业簿 · Inno Setup 7 安装包脚本（英文产物名）
; 先构建 PyInstaller 产物：dist\SpellCardHomework\
; 运行：ISCC.exe installer\SpellCardHomework.iss

#define MyAppName "SpellCardHomework"
#define MyAppDisplayName "符卡作业簿"
#define MyAppVersion "1.1.7"
#define MyAppFileVersion "1.1.7.0"
#define MyAppPublisher "Shinichi, Fastrof & 会哈气の祥"
#define MyAppExeName "SpellCardHomework.exe"
#define MyAppURL "https://github.com/Jerry9335/SpellCardHomework"

[Setup]
AppId={{8F3A9C21-5B7D-4E6A-9C2F-1D4B7E8A6C10}
AppMutex=Local\SpellCardHomework.SingleInstance
CloseApplications=yes
CloseApplicationsFilter=SpellCardHomework.exe
RestartApplications=no
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
Source: "使用说明-1.1.7.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "符卡作业簿"
Name: "{group}\使用说明"; Filename: "{app}\使用说明-1.1.7.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; AppUserModelID: "符卡作业簿"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppDisplayName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载即清除本机配置、API Key、账本、日志和试用痕迹。
; 这些数据都在应用专属目录内，不影响用户其他文件。
Type: filesandordirs; Name: "{userappdata}\SpellCardHomework"
Type: filesandordirs; Name: "{localappdata}\SpellCardHomework"

[Code]
var
  PreviousExeExists: Boolean;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { 必须在文件复制前判断：旧目录里已有 exe = 覆盖升级，不能重置引导。 }
  PreviousExeExists := FileExists(ExpandConstant('{app}\{#MyAppExeName}'));
  Result := '';
end;

procedure WriteOnboardingRequest;
var
  DirName, FileName: String;
begin
  DirName := ExpandConstant('{userappdata}\SpellCardHomework');
  ForceDirectories(DirName);
  FileName := DirName + '\onboarding_request.json';
  SaveStringToFile(FileName, '{"reason":"fresh_or_reinstall"}', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { 旧 exe 不存在才是新装/卸载重装；覆盖升级绝不写这个标记。 }
    if not PreviousExeExists then
      WriteOnboardingRequest();

    if WizardIsTaskSelected('resetlicense') then
    begin
      DeleteFile(ExpandConstant('{userappdata}\SpellCardHomework\license.json'));
      DeleteFile(ExpandConstant('{userappdata}\SpellCardHomework\trial.json'));
      DeleteFile(ExpandConstant('{localappdata}\SpellCardHomework\.spellcard_trial'));
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Shinichi\SpellCardHomework');
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Shinichi\SpellCardHomework');
  end;
end;
