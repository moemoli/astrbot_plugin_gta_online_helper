# GTA Online Helper

一个 AstrBot 插件，当前提供以下能力：

- 管理员更新并持久化 Rockstar 相关 CK / BearerToken
- 按 RID 或玩家名查询 BattlEye 封禁状态
- 通过 HQSHI 开放接口查询玩家生涯信息

## 功能与命令

## 插件配置

可在插件配置面板中设置以下字段：

- `plugin_log_enabled`：是否启用插件 info 日志，默认 `true`
- `battleye_server_host`：战眼查询服务器地址，默认 `51.89.97.102`
- `battleye_server_port`：战眼查询服务器端口，默认 `61455`
- `battleye_timeout_seconds`：战眼查询超时秒数，默认 `5`

修改配置后重载插件即可生效。

### 1) 更新 CK（仅管理员）

命令：

```text
/gta 更新ck <BearerToken 或完整 Cookie 字符串>
```

说明：

- 该命令仅 AstrBot 管理员可用。
- 推荐传入完整 Cookie 字符串（`k1=v1;k2=v2;...`），插件会自动解析并持久化。
- 支持直接传入 BearerToken，但仅传 Token 时刷新能力会受限。

完整 Cookie 模式下必需字段：

- `BearerToken`
- `TS01008f56`
- `TS011be943`
- `TS01347d69`
- `RockStarWebSessionId`
- `prod`

### 2) 查战眼封禁

命令：

```text
/查战眼 <RID或玩家名称>
```

### 3) 查生涯（HQSHI API）

命令：

```text
/查生涯 <玩家昵称>
```

### 4) 绑定与我的查询

命令：

```text
/gta 绑定 <玩家名称>
/gta me
/gta 生涯 [玩家昵称]
/gta 战眼 [RID或玩家名称]
/gta 更新ck <BearerToken 或完整 Cookie 字符串>
/gta 帮助
```

说明：

- 采用 `gta` 指令组风格（参考 steam 插件）。
- `/gta 绑定 <玩家名称>`：将当前发送者账号与 GTA 玩家昵称绑定。
- `/gta me`：读取绑定昵称并返回“生涯信息 + 战眼封禁结果”。
- `/gta 生涯 [玩家昵称]`：查询生涯信息；不填参数时默认使用绑定昵称。
- `/gta 战眼 [RID或玩家名称]`：查询战眼封禁；不填参数时默认使用绑定昵称。
- `/gta 更新ck <BearerToken 或完整 Cookie 字符串>`：管理员更新授权信息。
- `/gta 帮助`：查看指令组帮助。

## 如何获取 CK（教程）

以下步骤以 Chromium 内核浏览器（Chrome / Edge）为例。

1. 按 `F12` 打开开发者工具。
2. 切到 `Network`（网络）面板。
3. 打开 `https://socialclub.rockstargames.com/members/qwq`。
4. 选中第一个请求

[](doc/1.png)
[](doc/2.png)


5. 发送给机器人更新: /gta 更新ck <上面复制的完整Cookie字符串>

### 1) 提示“CK 缺少必需字段”

- 说明复制的 Cookie 不完整。
- 回到 `Network` 重新复制请求头中的整段 Cookie。
- 避免从浏览器插件或精简视图复制，容易缺字段。

### 2) 提示刷新失败或 401

- 账号会话可能过期，重新登录 Social Club 后重新抓取 CK。
- 同一账号频繁请求可能触发风控，建议间隔一段时间后再试。

### 3) 查生涯没有数据

- HQSHI 在有效期内可能没有该玩家可用记录。
- 可稍后重试，或确认昵称拼写是否正确。

## 安全建议

- `BearerToken` 和完整 Cookie 都是敏感凭据，请勿在群聊公开发送。
- 建议仅在私聊中使用 `/gta 更新ck`。
- 如怀疑泄露，请立即退出 Rockstar 账号并重新登录以更新会话。