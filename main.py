import re

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from .batteye_helper import check_battleye_by_name, check_battleye_by_rid
from .gtaonline_helper import (
    get_hqshi_recent_text,
    get_hqshi_status,
    parse_cookie_string,
    set_authorization,
    set_refresh_persist_callback,
    set_refresh_cookies,
    update_from_cookie_string,
)

AUTHORIZATION_KV_KEY = "authorization"
REFRESH_COOKIES_KV_KEY = "refresh_cookies"
REQUIRED_COOKIE_FIELDS = (
    "BearerToken",
    "TS01008f56",
    "TS011be943",
    "TS01347d69",
    "RockStarWebSessionId",
    "prod",
)

class GTAOnlinePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        set_refresh_persist_callback(self._persist_auth_state)

        authorization = await self.get_kv_data(AUTHORIZATION_KV_KEY, "")
        if isinstance(authorization, str) and authorization.strip():
            logger.info("[gta_online_helper] Found saved Authorization in plugin storage, loading it: %s", authorization)
            set_authorization(authorization)
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
                logger.info("[gta_online_helper] Refresh cookies loaded from plugin storage.")

    async def _persist_auth_state(self, authorization: str, refresh_cookies: dict[str, str]) -> None:
        """Persist refreshed authorization and cookies immediately."""
        if authorization and authorization.strip():
            await self.put_kv_data(AUTHORIZATION_KV_KEY, authorization)
        if refresh_cookies:
            await self.put_kv_data(REFRESH_COOKIES_KV_KEY, refresh_cookies)

    @filter.command("更新CK")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def gta_set_auth(self, event: AstrMessageEvent):
        """更新 Authorization 或 Cookie。更新CK <BearerToken 或 Cookie字符串>"""
        message_str = event.message_str.strip()

        payload = ""
        parts = message_str.split(maxsplit=1)
        if len(parts) >= 2:
            payload = parts[1].strip()

        # Strip adapter-appended message markers, e.g. [MSG_ID:1211303900] / [MSGID:1211303900].
        payload = re.sub(r"\s*\[(?:MSG[_ ]?ID)\s*:\s*\d+\]\s*$", "", payload, flags=re.IGNORECASE)
        payload = payload.strip()

        if not payload or not payload.strip():
            yield event.plain_result("用法: /更新CK <BearerToken 或完整Cookie字符串>")
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
