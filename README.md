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

## 사용 (배포본)

배포본은 파일 두 개 — `mattermost_toast.exe` 와 `config.yaml` — 만으로 동작합니다.
Python 설치나 의존성 설치는 필요 없습니다 (모두 exe 안에 포함).

1. `mattermost_toast.exe` 와 `config.yaml` 을 같은 폴더에 둡니다.
2. Mattermost 에서 **개인 액세스 토큰(PAT)** 을 발급합니다.
   - 우측 상단 프로필 사진 → **계정 설정** → **보안** → **개인 액세스 토큰**
   - 메뉴가 안 보이면 워크스페이스 관리자에게 *"Enable Personal Access Tokens"* 활성화를 요청하세요.
3. `config.yaml` 의 `server.url` 과 `server.token` 을 채웁니다.

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

4. `mattermost_toast.exe` 더블클릭. 백그라운드(콘솔창 없이)로 동작합니다.

오류가 발생하면 화면에 메시지 박스가 뜨고, 상세 내용은 exe 옆에 생성되는
`mattermost_toast_error.log` (치명적 오류) / `mattermost_toast.log` (실행 로그) 에 기록됩니다.

### 통합 관리 도구 (mattermost_init.bat)

`mattermost_init.bat` 을 `mattermost_toast.exe` 와 같은 폴더에 두고 더블클릭하면
콘솔 메뉴로 다음 작업을 할 수 있습니다.

1. 프로그램 시작
2. 프로그램 종료 (`taskkill` 로 강제 종료)
3. 프로그램 재시작
4. **Windows 시작 시 자동 실행 등록** (현재 사용자의 `HKCU\...\Run` 레지스트리)
5. 자동 실행 등록 해제

> `mattermost_init.bat` 은 cmd 기본 코드페이지(한국어 Windows 의 949)에 맞춰
> **ANSI(CP949)** 로 저장되어 있습니다. 메모장에서 수정해 다시 저장할 때는
> 인코딩을 반드시 **ANSI** 로 두세요. UTF-8 로 저장하면 메뉴 한글이 깨집니다.

자동 실행만 따로 걸고 싶다면 `Win + R` → `shell:startup` 폴더에
`mattermost_toast.exe` 의 바로가기를 넣어두어도 됩니다.

> 알림이 보이지 않는다면 **설정 → 시스템 → 알림** 에서 알림이 켜져 있는지,
> **집중 모드(Focus Assist)** 가 꺼져 있는지 확인하세요.

## 동작 원리

1. REST `GET /api/v4/users/me` 로 PAT 검증 후 본인 user id 획득
2. `wss://<server>/api/v4/websocket` 에 접속, `authentication_challenge` 전송
3. `posted` 이벤트가 오면 채널/사용자 메타데이터를 캐시 조회 후 분류
4. 조건에 맞으면 `windows-toasts` 라이브러리(WinRT `ToastNotification` API)로 알림 표시
5. 사용자가 토스트를 클릭하면 `mattermost://server/team/pl/<post_id>` 딥링크 실행

## 트러블슈팅

| 증상 | 원인/대응 |
| --- | --- |
| 더블클릭해도 아무 일도 안 일어남 | exe 옆에 `config.yaml` 이 있는지 확인. 없으면 메시지 박스로 안내됨 |
| `인증 실패 (HTTP 401)` 메시지 박스 | PAT 가 만료됐거나 오타. `config.yaml` 의 `server.token` 재확인 |
| `서버 접속 실패` 메시지 박스 | URL 오타 또는 사내망 인증서 문제. `verify_ssl: false` 로 우회 가능 |
| 토스트는 뜨는데 클릭해도 앱이 안 열림 | Mattermost 데스크톱 앱이 설치되어 있어야 `mattermost://` 가 동작. 미설치 시 `click_action.mode: "open_browser"` 로 변경 |
| 알림이 너무 많이 옴 | `notifications.all_channel_messages: false` 로 끄고 멘션/키워드만 켜기 |
| Action Center 에 알림이 누적되지 않음 | 알림 설정에서 `MattermostWindowsToast` 앱의 알림이 켜져 있는지 확인 |

---

## 개발자 가이드

> 일반 사용자는 위쪽 "사용 (배포본)" 섹션만 보면 됩니다. 아래는 소스에서 실행하거나
> exe 를 새로 빌드하는 사람용입니다.

### exe 빌드

`build.bat` 더블클릭 한 번이면 끝입니다. 내부적으로:

1. `.venv` 가 없으면 자동 생성
2. `requirements.txt` + `pyinstaller` 설치
3. `pyinstaller --onefile --noconsole` 로 단일 실행 파일 빌드

```powershell
build.bat
```

성공하면 `dist\mattermost_toast.exe` 가 생성됩니다.
배포할 때는 이 exe 와 (사용자가 채울 템플릿) `config.example.yaml` 을 함께 주면 됩니다.

### 소스에서 직접 실행

Python 3.10 이상.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python mattermost_toast.py
```

`.venv` 가 이미 있다면 `run.bat` 더블클릭만으로 같은 동작.

## 프로젝트 구조

```
mattermost-windows-toast/
├── mattermost_toast.py      # 메인 스크립트
├── requirements.txt
├── config.example.yaml      # 설정 템플릿
├── config.yaml              # 실제 설정 (git ignored)
├── build.bat                # exe 빌드 스크립트 (개발자용)
├── run.bat                  # 소스에서 실행 (개발자용)
├── mattermost_init.bat      # exe 시작/종료/자동 실행 등록 통합 관리 도구
├── .gitignore
└── README.md
```

## 라이선스

본 저장소는 LICENSE 파일을 따릅니다.
