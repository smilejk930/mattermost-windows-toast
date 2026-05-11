# Mattermost Windows Toast Notifier

Mattermost(Free Edition 포함) 의 **WebSocket API** 를 통해 실시간 메시지 이벤트를 수신하고,
Windows 10/11 의 **네이티브 토스트(Action Center)** 알림으로 띄우는 가벼운 Python 프로그램입니다.

시스템 트레이 아이콘이 아니라 카카오톡처럼 OS 가 직접 그리는 알림이므로
포커스가 다른 창에 있어도 우측 하단에 자연스럽게 떠오르고, 알림 센터에 누적됩니다.

## 주요 기능

- DM(1:1) / 그룹 DM
- @mention, @channel, @here, @all
- 내가 속한 모든 채널의 새 메시지 (선택)
- 사용자 지정 키워드 알림 (예: "긴급", "urgent")
- 토스트 클릭 시 Mattermost **데스크톱 앱**으로 해당 메시지 바로가기 (`mattermost://...`)
- 자동 재연결(지수 백오프), 본인 메시지/시스템 메시지 필터링

## 동작 원리

1. REST `GET /api/v4/users/me` 로 PAT 검증 후 본인 user id 획득
2. `wss://<server>/api/v4/websocket` 에 접속, `authentication_challenge` 전송
3. `posted` 이벤트가 오면 채널/사용자 메타데이터를 캐시 조회 후 분류
4. 조건에 맞으면 `windows-toasts` 라이브러리(WinRT `ToastNotification` API)로 알림 표시
5. 사용자가 토스트를 클릭하면 `mattermost://server/team/pl/<post_id>` 딥링크 실행

## 설치

Python 3.10 이상이 필요합니다.

```powershell
cd D:\develop\workspace\mattermost-windows-toast

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

## 설정

1. `config.example.yaml` 을 `config.yaml` 로 복사합니다.
2. Mattermost 에서 **개인 액세스 토큰(PAT)** 을 발급합니다.
   - 우측 상단 프로필 사진 → **계정 설정** → **보안** → **개인 액세스 토큰**
   - 화면이 보이지 않으면 워크스페이스 관리자에게 *"Enable Personal Access Tokens"* 활성화를 요청하세요.
3. `config.yaml` 의 `server.url` 과 `server.token` 을 채웁니다.
4. (선택) `notifications` 섹션에서 어떤 이벤트에 알림을 띄울지 조정합니다.

```yaml
server:
  url: "https://mattermost.example.com"
  token: "xxxxxxxxxxxxxxxxxxxxxxxxxx"

notifications:
  dm: true
  mention: true
  all_channel_messages: true
  keywords: ["긴급", "urgent"]

click_action:
  mode: "open_app"   # open_app | open_browser | none
```

## 실행

```powershell
.venv\Scripts\python mattermost_toast.py
```

또는 `run.bat` 더블클릭.

콘솔 창 없이 백그라운드 실행하고 싶다면 `run.bat` 의 `python` 을 `pythonw` 로 바꾸면 됩니다.

## Windows 시작 시 자동 실행

`Win + R` → `shell:startup` → 열린 폴더에 `run.bat` 의 바로가기를 넣어두면 로그인 시 자동 시작됩니다.

> 알림이 보이지 않는다면 **설정 → 시스템 → 알림** 에서 알림이 켜져 있는지,
> **집중 모드(Focus Assist)** 가 꺼져 있는지 확인하세요.

## 단일 실행 파일 만들기 (선택)

```powershell
.venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --onefile --noconsole mattermost_toast.py
```

`dist\mattermost_toast.exe` 가 생성됩니다. `config.yaml` 은 같은 폴더에 두고 사용하세요.

## 트러블슈팅

| 증상 | 원인/대응 |
| --- | --- |
| `인증 실패 (HTTP 401)` | PAT 가 만료됐거나 오타. `config.yaml` 의 token 재확인 |
| `서버 접속 실패` | URL 오타 또는 사내망 인증서 문제. `verify_ssl: false` 로 우회 가능 |
| 토스트는 뜨는데 클릭해도 앱이 안 열림 | Mattermost 데스크톱 앱이 설치되어 있어야 `mattermost://` 가 동작. 미설치 시 `click_action.mode: "open_browser"` 로 변경 |
| 알림이 너무 많이 옴 | `notifications.all_channel_messages: false` 로 끄고 멘션/키워드만 켜기 |
| Action Center 에 알림이 누적되지 않음 | 알림 설정에서 `MattermostWindowsToast` 앱의 알림이 켜져 있는지 확인 |

## 프로젝트 구조

```
mattermost-windows-toast/
├── mattermost_toast.py      # 메인 스크립트
├── requirements.txt
├── config.example.yaml      # 설정 템플릿
├── config.yaml              # 실제 설정 (git ignored)
├── run.bat                  # 실행 스크립트
├── .gitignore
└── README.md
```

## 라이선스

본 저장소는 LICENSE 파일을 따릅니다.
