"""
Mattermost Windows Toast Notifier
=================================

Mattermost(Free Edition 포함) 의 WebSocket API 로부터 실시간 이벤트를 수신하여
Windows 10/11 의 네이티브 토스트(Action Center) 알림을 띄우는 프로그램.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote, urlparse

import requests
import websocket  # websocket-client
import yaml
from windows_toasts import (
    Toast,
    ToastDuration,
    WindowsToaster,
)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

CONFIG_FILE_CANDIDATES = ["config.yaml", "config.yml"]
APP_AUMID = "MattermostWindowsToast"
APP_DISPLAY_NAME = "Mattermost Toast"  # Action Center 토스트 헤더에 표시될 이름


def register_aumid(aumid: str, display_name: str, logger: logging.Logger | None = None) -> bool:
    """Windows AUMID 에 DisplayName 을 등록한다.

    이 작업을 하지 않으면 Action Center 토스트 헤더에 부모 프로세스의 AUMID
    (예: 'PythonSoftwareFoundation.Python.3.13_...')가 그대로 노출된다.

    HKEY_CURRENT_USER 에 쓰므로 관리자 권한이나 외부 라이브러리 없이
    표준 라이브러리 winreg 만으로 동작한다.
    """
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        if logger:
            logger.debug("winreg unavailable - non-Windows, skip AUMID 등록")
        return False

    key_path = r"SOFTWARE\Classes\AppUserModelId\{}".format(aumid)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
            winreg.SetValueEx(key, "ShowInActionCenter", 0, winreg.REG_DWORD, 1)
        if logger:
            logger.info("AUMID 등록 완료: %s -> '%s'", aumid, display_name)
        return True
    except OSError as e:
        if logger:
            logger.warning("AUMID 등록 실패 (%s): %s", aumid, e)
        return False


@dataclass
class Config:
    server_url: str
    token: str
    verify_ssl: bool = True

    websocket_origin: str | None = None

    notify_dm: bool = True
    notify_mention: bool = True
    notify_all_channels: bool = True
    keywords: list[str] = field(default_factory=list)
    ignore_own_messages: bool = True
    body_max_length: int = 200
    ignore_system_messages: bool = True

    click_mode: str = "open_app"

    log_level: str = "INFO"
    log_file: str = "mattermost_toast.log"

    @classmethod
    def load(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        srv = raw.get("server", {})
        notif = raw.get("notifications", {})
        click = raw.get("click_action", {})
        log = raw.get("logging", {})

        url = (srv.get("url") or "").rstrip("/")
        if not url:
            raise ValueError("config.yaml: server.url 이 비어 있습니다.")
        token = srv.get("token") or ""
        if not token or "여기에" in token:
            raise ValueError("config.yaml: server.token (PAT) 이 설정되지 않았습니다.")

        ws_origin_raw = srv.get("websocket_origin", None)
        if ws_origin_raw in ("auto", ""):
            ws_origin = url
        else:
            ws_origin = ws_origin_raw

        return cls(
            server_url=url,
            token=token,
            verify_ssl=bool(srv.get("verify_ssl", True)),
            websocket_origin=ws_origin,
            notify_dm=bool(notif.get("dm", True)),
            notify_mention=bool(notif.get("mention", True)),
            notify_all_channels=bool(notif.get("all_channel_messages", True)),
            keywords=[str(k) for k in (notif.get("keywords") or [])],
            ignore_own_messages=bool(notif.get("ignore_own_messages", True)),
            body_max_length=int(notif.get("body_max_length", 200)),
            ignore_system_messages=bool(notif.get("ignore_system_messages", True)),
            click_mode=str(click.get("mode", "open_app")),
            log_level=str(log.get("level", "INFO")).upper(),
            log_file=str(log.get("file", "mattermost_toast.log")),
        )


def find_config_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in CONFIG_FILE_CANDIDATES:
        p = os.path.join(here, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "config.yaml 을 찾을 수 없습니다. config.example.yaml 을 복사해서 만들어주세요."
    )


def setup_logging(level: str, log_file: str) -> logging.Logger:
    logger = logging.getLogger("mm-toast")
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass

    return logger


# ---------------------------------------------------------------------------
# Mattermost REST 클라이언트
# ---------------------------------------------------------------------------

class MattermostREST:
    def __init__(self, base_url: str, token: str, verify_ssl: bool, logger: logging.Logger):
        self.base = base_url.rstrip("/") + "/api/v4"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
            }
        )
        self.session.verify = verify_ssl
        self.logger = logger

        self._user_cache: dict[str, dict] = {}
        self._channel_cache: dict[str, dict] = {}
        self._team_cache: dict[str, dict] = {}

    def me(self) -> dict:
        r = self.session.get(self.base + "/users/me", timeout=10)
        r.raise_for_status()
        return r.json()

    def my_teams(self) -> list[dict]:
        try:
            r = self.session.get(self.base + "/users/me/teams", timeout=10)
            r.raise_for_status()
            return r.json() or []
        except Exception as e:
            self.logger.warning("내 팀 조회 실패: %s", e)
            return []

    def user(self, user_id: str) -> dict:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            r = self.session.get(self.base + "/users/" + user_id, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.logger.warning("사용자 조회 실패 (%s): %s", user_id, e)
            data = {"id": user_id, "username": "unknown"}
        self._user_cache[user_id] = data
        return data

    def channel(self, channel_id: str) -> dict:
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]
        try:
            r = self.session.get(self.base + "/channels/" + channel_id, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.logger.warning("채널 조회 실패 (%s): %s", channel_id, e)
            data = {"id": channel_id, "name": "", "display_name": "", "type": "O", "team_id": ""}
        self._channel_cache[channel_id] = data
        return data

    def team(self, team_id: str) -> dict:
        if not team_id:
            return {"id": "", "name": "", "display_name": ""}
        if team_id in self._team_cache:
            return self._team_cache[team_id]
        try:
            r = self.session.get(self.base + "/teams/" + team_id, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.logger.warning("팀 조회 실패 (%s): %s", team_id, e)
            data = {"id": team_id, "name": "", "display_name": ""}
        self._team_cache[team_id] = data
        return data


# ---------------------------------------------------------------------------
# 토스트 알림
# ---------------------------------------------------------------------------

class Notifier:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.toaster = WindowsToaster(APP_AUMID)
        self._refs: list[Toast] = []

    def show(self, title: str, body: str, on_click: Callable[[], None] | None = None) -> None:
        toast = Toast()
        toast.text_fields = [title, body]
        toast.duration = ToastDuration.Short

        if on_click is not None:
            def _activated(_event_args, _cb=on_click):
                try:
                    _cb()
                except Exception as e:
                    self.logger.warning("토스트 클릭 처리 실패: %s", e)

            toast.on_activated = _activated

        try:
            self.toaster.show_toast(toast)
            self._refs.append(toast)
            if len(self._refs) > 50:
                self._refs.pop(0)
        except Exception as e:
            self.logger.error("토스트 표시 실패: %s", e)


def open_deeplink(url: str, mode: str, logger: logging.Logger) -> None:
    if mode == "none" or not url:
        return
    try:
        if mode == "open_app":
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            webbrowser.open(url)
    except Exception as e:
        logger.warning("링크 열기 실패 (%s): %s", url, e)


# ---------------------------------------------------------------------------
# Deeplink 빌더
# ---------------------------------------------------------------------------

CHANNEL_TYPE_DM = "D"
CHANNEL_TYPE_GROUP = "G"


def _host(server_url: str) -> str:
    u = urlparse(server_url)
    return u.netloc or u.path


def build_link(
    server_url: str,
    scheme: str,
    team_name: str,
    channel: dict,
    sender_username: str,
    post_id: str | None = None,
) -> str:
    host = _host(server_url)
    team = team_name or "team"
    ch_type = channel.get("type", "O")
    ch_name = channel.get("name", "")

    if scheme == "mattermost":
        prefix = "mattermost://" + host + "/" + team
    else:
        prefix = server_url.rstrip("/") + "/" + team

    if ch_type == CHANNEL_TYPE_DM:
        return prefix + "/messages/@" + sender_username
    if ch_type == CHANNEL_TYPE_GROUP:
        return prefix + "/messages/" + quote(ch_name)

    if post_id:
        return prefix + "/pl/" + post_id
    return prefix + "/channels/" + quote(ch_name or "town-square")


# ---------------------------------------------------------------------------
# 이벤트 처리
# ---------------------------------------------------------------------------

@dataclass
class MeContext:
    user_id: str
    username: str
    default_team_name: str = ""


class EventHandler:
    def __init__(self, cfg: Config, rest: MattermostREST, notifier: Notifier, me: MeContext, logger: logging.Logger):
        self.cfg = cfg
        self.rest = rest
        self.notifier = notifier
        self.me = me
        self.logger = logger

        if cfg.keywords:
            pattern = "|".join(re.escape(k) for k in cfg.keywords)
            self.kw_re: re.Pattern[str] | None = re.compile(pattern, re.IGNORECASE)
        else:
            self.kw_re = None

    def _classify(self, post: dict, channel: dict, mentions: list[str]) -> tuple[bool, str]:
        ch_type = channel.get("type", "O")

        if self.cfg.ignore_own_messages and post.get("user_id") == self.me.user_id:
            return False, ""

        if self.cfg.ignore_system_messages and post.get("type"):
            return False, ""

        if ch_type == CHANNEL_TYPE_DM:
            if self.cfg.notify_dm:
                return True, "DM"
            return False, ""

        if ch_type == CHANNEL_TYPE_GROUP:
            if self.cfg.notify_dm:
                return True, "Group"
            if self.cfg.notify_mention and self.me.user_id in mentions:
                return True, "Mention"
            return False, ""

        if self.cfg.notify_mention and self.me.user_id in mentions:
            return True, "Mention"

        msg = post.get("message", "") or ""
        if self.kw_re is not None and self.kw_re.search(msg):
            return True, "Keyword"

        if self.cfg.notify_all_channels:
            return True, "Channel"

        return False, ""

    def _format(self, post: dict, channel: dict, sender_username: str, label: str) -> tuple[str, str]:
        ch_type = channel.get("type", "O")
        ch_display = channel.get("display_name") or channel.get("name") or ""

        if ch_type == CHANNEL_TYPE_DM:
            title = "@" + sender_username
        elif ch_type == CHANNEL_TYPE_GROUP:
            title = "@" + sender_username + " · 그룹"
        else:
            tag = "@멘션" if label == "Mention" else ("[키워드]" if label == "Keyword" else "")
            prefix = (tag + " ") if tag else ""
            title = (prefix + ch_display + " · @" + sender_username).strip()

        body = (post.get("message") or "").strip()
        if not body:
            if post.get("file_ids"):
                body = "(파일 첨부)"
            else:
                body = "(빈 메시지)"

        if len(body) > self.cfg.body_max_length:
            body = body[: self.cfg.body_max_length].rstrip() + "..."

        return title, body

    def handle_posted(self, data: dict) -> None:
        try:
            post_raw = data.get("post")
            if not post_raw:
                return
            post = json.loads(post_raw) if isinstance(post_raw, str) else post_raw

            mentions_raw = data.get("mentions") or "[]"
            try:
                mentions = json.loads(mentions_raw) if isinstance(mentions_raw, str) else (mentions_raw or [])
            except json.JSONDecodeError:
                mentions = []

            channel_id = post.get("channel_id") or ""
            channel = self.rest.channel(channel_id) if channel_id else {}
            if not channel.get("display_name") and data.get("channel_display_name"):
                channel["display_name"] = data["channel_display_name"]
            if not channel.get("name") and data.get("channel_name"):
                channel["name"] = data["channel_name"]
            if not channel.get("type") and data.get("channel_type"):
                channel["type"] = data["channel_type"]

            should, label = self._classify(post, channel, mentions)
            if not should:
                self.logger.debug("skip post id=%s ch=%s type=%s", post.get("id"), channel.get("name"), channel.get("type"))
                return

            sender_user = self.rest.user(post.get("user_id", ""))
            sender_username = sender_user.get("username") or "unknown"

            title, body = self._format(post, channel, sender_username, label)

            ch_type = channel.get("type", "O")
            team_id = channel.get("team_id") or data.get("team_id") or ""

            if ch_type in (CHANNEL_TYPE_DM, CHANNEL_TYPE_GROUP):
                team_name = self.me.default_team_name or ""
            else:
                team = self.rest.team(team_id)
                team_name = team.get("name") or self.me.default_team_name or ""

            if self.cfg.click_mode == "open_browser":
                url = build_link(self.cfg.server_url, "https", team_name, channel, sender_username, post.get("id"))
            elif self.cfg.click_mode == "open_app":
                url = build_link(self.cfg.server_url, "mattermost", team_name, channel, sender_username, post.get("id"))
            else:
                url = ""

            cb_mode = self.cfg.click_mode
            cb_logger = self.logger

            def _on_click(_url=url, _mode=cb_mode, _log=cb_logger):
                open_deeplink(_url, _mode, _log)

            self.notifier.show(title, body, _on_click if url else None)
            self.logger.info("notify [%s] %s :: %s -> %s", label, title, body[:60], url)

        except Exception as e:
            self.logger.exception("posted 이벤트 처리 중 오류: %s", e)


# ---------------------------------------------------------------------------
# WebSocket 루프
# ---------------------------------------------------------------------------

class WebSocketLoop:
    def __init__(self, cfg: Config, handler: EventHandler, logger: logging.Logger):
        self.cfg = cfg
        self.handler = handler
        self.logger = logger
        self._stop = threading.Event()
        self._seq = 1
        self._ws: websocket.WebSocketApp | None = None

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass

    def _ws_url(self) -> str:
        u = urlparse(self.cfg.server_url)
        scheme = "wss" if u.scheme == "https" else "ws"
        host = u.netloc or u.path
        return scheme + "://" + host + "/api/v4/websocket"

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        self.logger.info("WebSocket 연결됨, 인증 challenge 전송")
        self._seq = 1
        challenge = {
            "seq": self._seq,
            "action": "authentication_challenge",
            "data": {"token": self.cfg.token},
        }
        self._seq += 1
        ws.send(json.dumps(challenge))

    def _on_message(self, _ws: websocket.WebSocketApp, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warning("WS: JSON 파싱 실패: %s", raw[:200])
            return

        event = msg.get("event")
        if event == "posted":
            self.handler.handle_posted(msg.get("data") or {})
        elif event == "hello":
            self.logger.info("hello: server=%s", (msg.get("data") or {}).get("server_version"))
        elif "status" in msg and msg.get("status") == "OK" and msg.get("seq_reply") == 1:
            self.logger.info("인증 OK")
        elif msg.get("status") == "FAIL":
            self.logger.error("WS 응답 실패: %s", msg)

    def _on_error(self, _ws: websocket.WebSocketApp, error: Any) -> None:
        self.logger.warning("WebSocket 오류: %s", error)

    def _on_close(self, _ws: websocket.WebSocketApp, code: Any, reason: Any) -> None:
        self.logger.info("WebSocket 연결 종료 code=%s reason=%s", code, reason)

    def run_forever(self) -> None:
        backoff = 1
        url = self._ws_url()
        origin = self.cfg.websocket_origin
        if origin is None:
            self.logger.info("WebSocket 대상: %s (Origin 헤더 미전송)", url)
        else:
            self.logger.info("WebSocket 대상: %s (Origin=%s)", url, origin)

        sslopt = None if self.cfg.verify_ssl else {"cert_reqs": 0}

        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                run_kwargs: dict[str, Any] = {
                    "ping_interval": 30,
                    "ping_timeout": 10,
                    "sslopt": sslopt,
                }
                if origin is None:
                    run_kwargs["suppress_origin"] = True
                else:
                    run_kwargs["origin"] = origin
                self._ws.run_forever(**run_kwargs)
            except Exception as e:
                self.logger.warning("WS 루프 예외: %s", e)

            if self._stop.is_set():
                break

            self.logger.info("재연결 대기 %d 초...", backoff)
            for _ in range(backoff):
                if self._stop.is_set():
                    break
                time.sleep(1)
            backoff = min(backoff * 2, 60)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        cfg_path = find_config_path()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        cfg = Config.load(cfg_path)
    except Exception as e:
        print("설정 파일 로드 실패: " + str(e), file=sys.stderr)
        return 2

    logger = setup_logging(cfg.log_level, cfg.log_file)
    logger.info("=" * 60)
    logger.info("Mattermost Windows Toast 시작")
    logger.info("server=%s click=%s", cfg.server_url, cfg.click_mode)

    # AUMID DisplayName 등록 (실패해도 동작에는 지장 없음, 헤더 라벨만 못 바뀜)
    register_aumid(APP_AUMID, APP_DISPLAY_NAME, logger)

    rest = MattermostREST(cfg.server_url, cfg.token, cfg.verify_ssl, logger)

    try:
        me_data = rest.me()
    except requests.HTTPError as e:
        logger.error("인증 실패 (HTTP %s). PAT 가 유효한지 확인하세요.",
                     e.response.status_code if e.response else "?")
        return 3
    except Exception as e:
        logger.error("서버 접속 실패: %s", e)
        return 3

    teams = rest.my_teams()
    default_team_name = ""
    if teams:
        default_team_name = teams[0].get("name", "")
        logger.info("기본 팀(DM URL 용): %s", default_team_name)

    me = MeContext(
        user_id=me_data["id"],
        username=me_data.get("username", ""),
        default_team_name=default_team_name,
    )
    logger.info("로그인: @%s (id=%s)", me.username, me.user_id)

    notifier = Notifier(logger)
    handler = EventHandler(cfg, rest, notifier, me, logger)
    loop = WebSocketLoop(cfg, handler, logger)

    notifier.show("Mattermost Toast", "@" + me.username + " 으로 알림 수신을 시작합니다.")

    def _sigint(_signum, _frame):
        logger.info("종료 신호 수신, 정리 중...")
        loop.stop()

    try:
        signal.signal(signal.SIGINT, _sigint)
        signal.signal(signal.SIGTERM, _sigint)
    except (ValueError, AttributeError):
        pass

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.stop()

    logger.info("종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
