<div align="center">
  <a href="https://nonebot.dev/store"><img src="https://gastigado.cnies.org/d/project_nonebot_plugin_group_welcome/nbp_logo.png?sign=8bUAF9AtoEkfP4bTe2CrYhR0WP4X6ZbGKykZgAeEWL4=:0" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://gastigado.cnies.org/d/project_nonebot_plugin_group_welcome/NoneBotPlugin.svg?sign=ksAOYnkycNpxRKXh2FsfTooiMXafUh2YpuKdAXGZF5M=:0" width="240" alt="NoneBotPluginText"></p>

<h1>NoneBot 2 群邀请监控插件</h1>
</div>

这是一个用于监控QQ群邀请行为并自动踢出邀请者的 NoneBot 2 插件，适用于 `nonebot-adapter-onebot` (OneBot V11) 适配器。

## 功能特点

- 🤖 **双机器人架构**：监控机器人负责监听，管理机器人负责执行操作
- 📋 **配置文件驱动**：通过 `config.ini` 文件灵活配置
- 🎯 **精确识别**：只响应非管理员发出的群邀请事件
- ⚡ **实时处理**：检测到违规行为立即执行踢人操作
- 📝 **详细日志**：记录所有违规行为的详细信息
- 🛡️ **安全防护**：自动发送警告消息，提醒群成员注意安全

## 安装要求

- Python 3.10+
- NoneBot 2
- nonebot-adapter-onebot>=2.0.0

## 安装方法

1. 将插件文件夹放入您的 NoneBot 2 项目的 `plugins` 目录中
2. 确保已安装 `nonebot-adapter-onebot` 适配器
3. 在 NoneBot 2 配置中加载此插件

## 配置说明

### config.ini 配置文件

插件需要一个 `config.ini` 配置文件，包含以下配置项：

```ini
[bots]
# 监控机器人QQ号（非管理员账号，负责监听群邀请事件）
monitor_bot_id = 111111111

# 管理机器人QQ号（管理员账号，负责踢人和发送警告）
admin_bot_id = 222222222

[groups]
# 需要监控的QQ群号列表，用逗号分隔
monitored_groups = 123456789, 987654321

# 通讯群号，用于两个机器人实例之间的通信（可以与监控群相同）
communication_group = 123456789

[settings]
# 插件启用状态
enabled = true

# 日志记录级别
log_level = INFO

# 是否在踢人后拒绝再次加群申请
reject_add_request = false
```

### 配置说明

#### [bots] 节
- `monitor_bot_id`: 监控机器人的QQ号，通常为非管理员账号，负责监听群邀请事件
- `admin_bot_id`: 管理机器人的QQ号，必须为群管理员，负责执行踢人操作

#### [groups] 节
- `monitored_groups`: 需要监控的QQ群号列表，多个群号用逗号分隔
- `communication_group`: 通讯群号，用于两个机器人实例之间的通信（可以与监控群相同）

#### [settings] 节
- `enabled`: 插件是否启用（true/false）
- `log_level`: 日志记录级别（DEBUG/INFO/WARNING/ERROR）
- `reject_add_request`: 是否在踢人后拒绝再次加群申请（true/false）

## 分布式部署模式

当您的监控机器人和管理机器人运行在不同的NoneBot实例上时（例如不同的端口3010、3011），插件会自动启用分布式通信模式：

### 工作原理
1. **监控机器人**：检测到违规邀请后，在通讯群发送特殊格式的检测消息
2. **管理机器人**：监听通讯群中的检测消息，解析后执行踢人操作
3. **通信格式**：使用Unix日志格式的特殊消息进行通信

### 检测消息格式
```
InvalidGroupInvitationDetect | Time: 2024-09-15 14:59:25 | MonitorGroup: 224260653 | User: 2741226099 | Card: 用户昵称 | Nickname: QQ昵称 | TargetGroup: 1046922004 | TargetGroupName: 目标群名
```

### 优势
- ✅ 支持跨实例部署
- ✅ 容错性强，通过QQ群消息保证可靠传输
- ✅ 易于调试，可以在群内直接看到检测消息
- ✅ 支持负载均衡和高可用部署

## 工作原理

1. **事件监听**：监控机器人监听所有群邀请事件（不限制群号）
2. **成员检查**：检查被邀请的用户是否为监控群的成员
3. **权限检查**：自动检查邀请者在监控群中是否为群管理员
4. **执行操作**：如果邀请者是监控群的非管理员成员，立即在监控群中执行以下操作：
   - 踢出发送邀请的用户
   - 在监控群内发送警告消息
   - 记录违规行为到日志文件
5. **日志记录**：所有操作都会记录到 `violation_logs.txt` 文件中

### 场景说明
- **群A**（监控群）：需要保护的群聊，配置在 `monitored_groups` 中
- **群B**（目标群）：广告/诈骗群，邀请者试图拉群A成员加入的群
- **工作流程**：当群A的成员被邀请到群B时，插件会在群A中踢出发送邀请的成员

## 警告消息格式

当检测到违规邀请行为时，插件会自动发送以下格式的警告消息：

```
检测到违规邀请行为！
成员：[被踢成员的群名片] ([被踢成员的QQ号])
试图邀请群成员加入外部群聊 ([目标群号])
已被移出本群。请大家注意甄别，不要点击不明群聊邀请，谨防广告与诈骗！
```

## 日志格式

违规行为日志保存在 `violation_logs.txt` 文件中，格式如下：

```
2024-09-15 14:17:48 | Group: 1046922004 | User: 2741226099 | Card: 用户昵称 | Nickname: QQ昵称 | Action: KICKED_FOR_INVITE
```

## 注意事项

1. **权限要求**：管理机器人必须拥有群管理员权限才能执行踢人操作
2. **机器人配置**：确保两个机器人都已正确连接到 NoneBot 2
3. **群聊权限**：监控机器人需要能够接收群消息
4. **事件类型**：插件监听的是群邀请 request 事件，不是新成员入群事件

## 调试命令

插件提供了一些调试命令来帮助诊断问题（需要超级用户权限）：

### /test_invite_bots
检查机器人连接状态，显示：
- 当前连接的所有机器人
- 监控机器人和管理机器人的连接状态
- 监控群聊配置
- 插件启用状态

### /reload_invite_config
重新加载配置文件，无需重启NoneBot即可应用新配置。

## 故障排除

### 1. 机器人连接问题
如果出现 `无法找到管理机器人` 错误：
1. 检查两个机器人是否都已连接到NoneBot
2. 使用 `/test_invite_bots` 命令查看连接状态
3. 确认配置文件中的机器人ID与实际连接的ID一致
4. 检查NoneBot日志中的机器人连接信息

### 2. 权限问题
如果踢人操作失败：
1. 确认管理机器人在监控群中拥有管理员权限
2. 检查被踢用户是否为群主或管理员
3. 查看详细的错误日志

### 3. API调用问题
如果API调用失败，日志会显示：
- 调用的具体API名称和参数
- 错误详情
- 机器人类型信息

## 常见问题

### Q: 为什么需要两个机器人？
A: 分离监控和管理功能可以提高安全性，避免管理机器人账号因频繁操作被风控。

### Q: 监控机器人需要管理员权限吗？
A: 不需要，监控机器人只需要能够接收群消息即可。

### Q: 插件如何区分管理员和普通成员？
A: 插件会自动调用群成员信息接口检查用户的群内角色。

### Q: 可以自定义警告消息吗？
A: 当前版本不支持自定义消息，但可以通过修改代码中的 `warning_message` 变量来实现。

### Q: 为什么插件检测到事件但没有执行操作？
A: 可能的原因：
- 管理机器人未连接或权限不足
- 被检测用户在监控群中是管理员
- API调用格式错误
使用调试命令和日志来诊断具体问题。

## 技术支持

如果您在使用过程中遇到问题，请检查：

1. 配置文件是否正确
2. 机器人是否正常连接
3. 管理机器人是否有足够权限
4. 日志文件中是否有错误信息

## 版本信息

- 版本：1.0.0
- 适配器：nonebot-adapter-onebot (OneBot V11)
- Python版本：3.10+
