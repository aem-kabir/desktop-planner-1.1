; installer.iss
; Inno Setup скрипт для DesktopPlanner.
; Собирается локально через build.bat (см. корень проекта) или автоматически
; через GitHub Actions на Windows-раннере.
;
; Требует: Inno Setup 7.x (https://jrsoftware.org/isdl.php#v7)
; Полностью совместим и с Inno Setup 6.x — скрипт использует только
; директивы, работающие одинаково в обеих версиях.
; Ожидает, что PyInstaller уже собрал приложение в dist\DesktopPlanner\DesktopPlanner.exe

#define MyAppName "DesktopPlanner"
#define MyAppDisplayName "Планер задач"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DesktopPlanner"
#define MyAppExeName "DesktopPlanner.exe"
#define MyDistDir "..\dist\DesktopPlanner"

[Setup]
AppId={{7E3F2C6A-2B3E-4E60-9A28-4D5C9C0B7F11}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=DesktopPlanner_Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\app\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppDisplayName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "Создать ярлык в меню Пуск"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppDisplayName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ярлыки удаляются автоматически системой Inno Setup (секция [Icons]).
; Локальные данные пользователя (%LocalAppData%\DesktopPlanner) удаляются
; опционально, с подтверждением, в коде ниже (см. CurUninstallStepChanged).

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LocalDataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    LocalDataDir := ExpandConstant('{localappdata}\DesktopPlanner');
    if DirExists(LocalDataDir) then
    begin
      if MsgBox('Удалить также локальные данные приложения (базу задач, настройки, логи)?' + #13#10 +
                LocalDataDir + #13#10#13#10 +
                'Если вы планируете переустановить приложение позже и сохранить свои задачи ' +
                'и настройки — выберите "Нет".',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(LocalDataDir, True, True, True);
      end;
    end;
  end;
end;
