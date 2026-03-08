import re

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from .batteye_helper import (
    BATTLEYE_SERVER_HOST,
    BATTLEYE_SERVER_PORT,
    BATTLEYE_TIMEOUT_SECONDS,
    check_battleye_by_name,
    check_battleye_by_rid,
    configure_battleye,
)
from .gtaonline_helper import (
    get_hqshi_recent_text,
    get_hqshi_status,
    is_plugin_log_enabled,
    parse_cookie_string,
    set_plugin_log_enabled,
    set_authorization,
    set_refresh_persist_callback,
    set_refresh_cookies,
    update_from_cookie_string,
)

AUTHORIZATION_KV_KEY = "authorization"
REFRESH_COOKIES_KV_KEY = "refresh_cookies"
USER_BINDINGS_KV_KEY = "user_bindings"
REQUIRED_COOKIE_FIELDS = (
    "BearerToken",
    "TS01008f56",
    "TS011be943",
    "TS01347d69",
    "RockStarWebSessionId",
    "prod",
)

class GTAOnlinePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context, config)
        self.config = config

    def _apply_battleye_config(self) -> None:
        cfg = self.config if isinstance(self.config, dict) else {}

        host = str(cfg.get("battleye_server_host") or BATTLEYE_SERVER_HOST).strip()

        raw_port = cfg.get("battleye_server_port", BATTLEYE_SERVER_PORT)
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            port = BATTLEYE_SERVER_PORT

        raw_timeout = cfg.get("battleye_timeout_seconds", BATTLEYE_TIMEOUT_SECONDS)
        try:
            timeout_seconds = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = BATTLEYE_TIMEOUT_SECONDS

        if port <= 0:
            port = BATTLEYE_SERVER_PORT
        if timeout_seconds <= 0:
            timeout_seconds = BATTLEYE_TIMEOUT_SECONDS

        configure_battleye(host=host, port=port, timeout_seconds=timeout_seconds)
        if is_plugin_log_enabled():
            logger.info(
                "[gta_online_helper] BattlEye config applied: host=%s, port=%s, timeout=%ss",
                host,
                port,
                timeout_seconds,
            )

    def _apply_log_config(self) -> None:
        cfg = self.config if isinstance(self.config, dict) else {}
        enabled = bool(cfg.get("plugin_log_enabled", True))
        set_plugin_log_enabled(enabled)

        if is_plugin_log_enabled():
            logger.info("[gta_online_helper] Plugin informational logs enabled.")

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self._apply_log_config()
        self._apply_battleye_config()
        set_refresh_persist_callback(self._persist_auth_state)

        authorization = await self.get_kv_data(AUTHORIZATION_KV_KEY, "")
        if isinstance(authorization, str) and authorization.strip():
            if is_plugin_log_enabled():
                logger.info("[gta_online_helper] Found saved Authorization in plugin storage, loading it: %s", authorization)
            set_authorization(authorization)
            if is_plugin_log_enabled():
                logger.info("[gta_online_helper] Authorization loaded from plugin storage.")

        refresh_cookies = await self.get_kv_data(REFRESH_COOKIES_KV_KEY, {})
        if isinstance(refresh_cookies, dict) and refresh_cookies:
            safe_cookies = {
                str(k): str(v)
                for k, v in refresh_cookies.items()
                if isinstance(k, str) and v is not None and str(v).strip()
            }
            if safe_cookies:
                set_refresh_cookies(safe_cookies)
                if is_plugin_log_enabled():
                    logger.info("[gta_online_helper] Refresh cookies loaded from plugin storage.")

    async def _persist_auth_state(self, authorization: str, refresh_cookies: dict[str, str]) -> None:
        """Persist refreshed authorization and cookies immediately."""
        if authorization and authorization.strip():
            await self.put_kv_data(AUTHORIZATION_KV_KEY, authorization)
        if refresh_cookies:
            await self.put_kv_data(REFRESH_COOKIES_KV_KEY, refresh_cookies)

    async def _load_user_bindings(self) -> dict[str, str]:
        data = await self.get_kv_data(USER_BINDINGS_KV_KEY, {})
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in data.items():
            user_id = str(k).strip()
            nickname = str(v).strip()
            if user_id and nickname:
                out[user_id] = nickname
        return out

    async def _save_user_bindings(self, bindings: dict[str, str]) -> None:
        await self.put_kv_data(USER_BINDINGS_KV_KEY, bindings)

    def _extract_sender_id(self, event: AstrMessageEvent) -> str:
        sender_id = str(event.get_sender_id() or "").strip()
        return sender_id

    @staticmethod
    def _sanitize_message_tail(text: str) -> str:
        return re.sub(
            r"\s*\[(?:MSG[_ ]?ID)\s*:\s*\d+\]\s*$",
            "",
            str(text or "").strip(),
            flags=re.IGNORECASE,
        ).strip()

    async def _get_bound_nickname(self, event: AstrMessageEvent) -> str:
        sender_id = self._extract_sender_id(event)
        if not sender_id:
            return ""
        bindings = await self._load_user_bindings()
        return bindings.get(sender_id, "").strip()

    def _parse_group_third_arg(self, event: AstrMessageEvent) -> str:
        message_str = self._sanitize_message_tail(event.message_str)
        parts = message_str.split(maxsplit=2)
        if len(parts) >= 3:
            return parts[2].strip()
        return ""

    @filter.command_group("gta")
    def gta(self):
        pass

    @gta.command("绑定", alias={"bind"})
    async def gta_bind(self, event: AstrMessageEvent, nickname: str | None = None):
        """绑定 GTA 玩家名称。/gta 绑定 <玩家名称>"""
        sender_id = self._extract_sender_id(event)
        if not sender_id:
            yield event.plain_result("无法识别你的用户标识，暂时不能绑定。")
            return

        target = str(nickname or "").strip()
        if not target:
            target = self._parse_group_third_arg(event)

        if not target:
            yield event.plain_result("用法: /gta 绑定 <玩家名称>")
            return

        bindings = await self._load_user_bindings()
        bindings[sender_id] = target
        await self._save_user_bindings(bindings)
        yield event.plain_result(f"绑定成功，你的 GTA 玩家名称已设置为: {target}")

    @gta.command("我", alias={"me", "my"})
    async def gta_me(self, event: AstrMessageEvent):
        """查询自己已绑定的生涯与战眼信息。/gta me"""
        sender_id = self._extract_sender_id(event)
        if not sender_id:
            yield event.plain_result("无法识别你的用户标识。")
            return

        nickname = await self._get_bound_nickname(event)
        if not nickname:
            yield event.plain_result("你还没有绑定玩家名称。请先使用: /gta 绑定 <玩家名称>")
            return

        lines = [f"已绑定玩家: {nickname}"]

        try:
            career_text = await get_hqshi_recent_text(nickname)
            lines.append("\n生涯信息")
            lines.append(career_text)
        except Exception as e:
            lines.append("\n生涯信息")
            lines.append(f"查询失败: {e}")

        try:
            be_result = await check_battleye_by_name(nickname)
            lines.append("\n战眼信息")
            lines.append(f"RID: {be_result.get('rid', '-')}")
            if be_result.get("is_banned"):
                lines.append("状态: 已封禁")
                lines.append(f"原因: {be_result.get('ban_reason') or '-'}")
            else:
                lines.append("状态: 未封禁")
        except Exception as e:
            lines.append("\n战眼信息")
            lines.append(f"查询失败: {e}")

        yield event.plain_result("\n".join(lines))

    @gta.command("生涯", alias={"career"})
    async def gta_career(self, event: AstrMessageEvent, nickname: str | None = None):
        """查询生涯信息。/gta 生涯 [玩家昵称]"""
        target = str(nickname or "").strip()
        if not target:
            target = self._parse_group_third_arg(event)
        if not target:
            target = await self._get_bound_nickname(event)
        if not target:
            yield event.plain_result("用法: /gta 生涯 <玩家昵称>，或先 /gta 绑定 <玩家名称>")
            return

        try:
            text = await get_hqshi_recent_text(target)
            yield event.plain_result(text)
            return
        except Exception as recent_error:
            logger.warning("[gta_online_helper] HQSHI recent query failed: %s", recent_error)

        try:
            status = await get_hqshi_status(target, limit=3)
        except Exception as status_error:
            yield event.plain_result(
                f"生涯查询失败: {status_error}\nrecent详情: {recent_error}"
            )
            return

        lines = [
            "生涯查询结果(HQSHI)",
            f"昵称: {status.get('名称') or status.get('昵称') or target}",
            f"RID: {status.get('rockstar_id') or '-'}",
            f"最近游玩: {status.get('最近游玩') or '-'}",
            f"状态更新: {status.get('状态更新') or '-'}",
            f"所在地: {status.get('所在地') or '-'}",
        ]
        yield event.plain_result("\n".join(lines))

    @gta.command("战眼", alias={"be", "battleye"})
    async def gta_battleye(self, event: AstrMessageEvent, identifier: str | None = None):
        """查询战眼封禁。/gta 战眼 [RID或玩家名称]"""
        target = str(identifier or "").strip()
        if not target:
            target = self._parse_group_third_arg(event)
        if not target:
            target = await self._get_bound_nickname(event)
        if not target:
            yield event.plain_result("用法: /gta 战眼 <RID或玩家名称>，或先 /gta 绑定 <玩家名称>")
            return

        try:
            if target.isdigit():
                result = await check_battleye_by_rid(int(target))
            else:
                result = await check_battleye_by_name(target)
        except Exception as e:
            yield event.plain_result(f"战眼查询失败: {e}")
            return

        lines = [
            "战眼查询结果",
            f"RID: {result.get('rid', '-')}",
        ]
        if result.get("name"):
            lines.append(f"玩家: {result['name']}")

        if result.get("is_banned"):
            lines.append("状态: 已封禁")
            lines.append(f"原因: {result.get('ban_reason', '') or '-'}")
        else:
            lines.append("状态: 未封禁")

        yield event.plain_result("\n".join(lines))

    @gta.command("帮助", alias={"help", "h"})
    async def gta_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "用法:\n"
            "/gta 绑定 <玩家名称>\n"
            "/gta me\n"
            "/gta 生涯 [玩家昵称]\n"
            "/gta 战眼 [RID或玩家名称]\n"
            "/gta 更新ck <BearerToken 或完整Cookie字符串>"
        )

    @gta.command("更新ck", alias={"更新CK", "setck", "ck"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def gta_set_auth(self, event: AstrMessageEvent):
        """更新 Authorization 或 Cookie。/gta 更新ck <BearerToken 或 Cookie字符串>"""
        message_str = event.message_str.strip()

        payload = ""
        parts = message_str.split(maxsplit=1)
        if len(parts) >= 2:
            payload = parts[1].strip()

        # Strip adapter-appended message markers, e.g. [MSG_ID:1211303900] / [MSGID:1211303900].
        payload = re.sub(r"\s*\[(?:MSG[_ ]?ID)\s*:\s*\d+\]\s*$", "", payload, flags=re.IGNORECASE)
        payload = payload.strip()

        if not payload or not payload.strip():
            yield event.plain_result("用法: /gta 更新ck <BearerToken 或完整Cookie字符串>")
            return

        payload = payload.strip()
        if "=" in payload:
            parsed = parse_cookie_string(payload)
            if not parsed:
                yield event.plain_result("CK 解析失败，请检查格式，例如: key=1;key2=2")
                return

            missing_fields = [field for field in REQUIRED_COOKIE_FIELDS if not parsed.get(field)]
            if missing_fields:
                yield event.plain_result(
                    f"CK 缺少必需字段: {', '.join(missing_fields)}"
                )
                return

            parsed = update_from_cookie_string(payload)

            # Persist all cookie key-values for future refresh requests.
            await self.put_kv_data(REFRESH_COOKIES_KV_KEY, parsed)

            token = parsed.get("BearerToken", "").strip()
            if token:
                set_authorization(token)
                await self.put_kv_data(AUTHORIZATION_KV_KEY, token)
                masked = f"{token[:8]}..." if len(token) > 8 else "***"
                yield event.plain_result(
                    f"Cookie 已更新并缓存，Authorization 已更新: {masked}"
                )
            else:
                yield event.plain_result("Cookie 已缓存（未检测到 BearerToken）。")
            return

        authorization = payload
        set_authorization(authorization)
        await self.put_kv_data(AUTHORIZATION_KV_KEY, authorization)

        # Avoid echoing sensitive tokens in full.
        masked = f"{authorization[:8]}..." if len(authorization) > 8 else "***"
        yield event.plain_result(f"Authorization 已更新并持久化: {masked}")

    @filter.command("查战眼")
    async def gta_battleye_check(self, event: AstrMessageEvent, identifier: str = ""):
        """查询玩家战眼封禁。查战眼 <RID或玩家名称>"""
        if not identifier or not identifier.strip():
            yield event.plain_result("用法: /查战眼 <RID或玩家名称>")
            return

        identifier = identifier.strip()
        try:
            if identifier.isdigit():
                result = await check_battleye_by_rid(int(identifier))
            else:
                result = await check_battleye_by_name(identifier)
        except Exception as e:
            yield event.plain_result(f"战眼查询失败: {e}")
            return

        lines = [
            "战眼查询结果",
            f"RID: {result.get('rid', '-')}",
        ]
        if result.get("name"):
            lines.append(f"玩家: {result['name']}")

        if result.get("is_banned"):
            lines.append("状态: 已封禁")
            lines.append(f"原因: {result.get('ban_reason', '') or '-'}")
        else:
            lines.append("状态: 未封禁")

        yield event.plain_result("\n".join(lines))

    @filter.command("查生涯")
    async def gta_career_query(self, event: AstrMessageEvent, nickname: str = ""):
        """查询 HQSHI 生涯数据。查生涯 <玩家昵称>"""
        if not nickname or not nickname.strip():
            yield event.plain_result("用法: /查生涯 <玩家昵称>")
            return

        target = nickname.strip()
        try:
            text = await get_hqshi_recent_text(target)
            yield event.plain_result(text)
            return
        except Exception as recent_error:
            logger.warning("[gta_online_helper] HQSHI recent query failed: %s", recent_error)

        # Fallback to status data if recent text is unavailable.
        try:
            status = await get_hqshi_status(target, limit=3)
        except Exception as status_error:
            yield event.plain_result(
                f"生涯查询失败: {status_error}\nrecent详情: {recent_error}"
            )
            return

        lines = [
            "生涯查询结果(HQSHI)",
            f"昵称: {status.get('名称') or status.get('昵称') or target}",
            f"RID: {status.get('rockstar_id') or '-'}",
            f"最近游玩: {status.get('最近游玩') or '-'}",
            f"状态更新: {status.get('状态更新') or '-'}",
            f"所在地: {status.get('所在地') or '-'}",
        ]
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
