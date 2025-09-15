"""
NoneBot 2 QQ群邀请行为监控插件

用于监控QQ群的邀请行为并自动踢出邀请者，防止广告号/诈骗号拉群成员进入广告群。

作者: AI Assistant
版本: 1.0.0
"""

import os
import asyncio
import configparser
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import nonebot
from nonebot import on_request, get_bots, logger
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot.params import EventType, EventMessage

# 插件元数据
__plugin_meta__ = {
    "name": "群邀请监控",
    "description": "监控QQ群邀请行为并自动踢出邀请者",
    "usage": "自动运行，无需手动操作",
    "type": "application",
    "homepage": "https://github.com/nonebot/nonebot2",
    "supported_adapters": {"nonebot.adapters.onebot.v11"},
}

# 全局配置
config_file_path = Path(__file__).parent / "config.ini"
log_file_path = Path(__file__).parent / "violation_logs.txt"

class PluginConfig:
    """插件配置类"""
    
    def __init__(self):
        self.monitor_bot_id: Optional[str] = None
        self.admin_bot_id: Optional[str] = None
        self.monitored_groups: List[int] = []
        self.communication_group: Optional[int] = None
        self.enabled: bool = True
        self.log_level: str = "INFO"
        self.reject_add_request: bool = False
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if not config_file_path.exists():
                self._create_default_config()
                logger.warning(f"配置文件不存在，已创建默认配置文件: {config_file_path}")
                return
            
            config = configparser.ConfigParser()
            config.read(config_file_path, encoding='utf-8')
            
            # 读取机器人配置
            if 'bots' in config:
                self.monitor_bot_id = config.get('bots', 'monitor_bot_id', fallback=None)
                self.admin_bot_id = config.get('bots', 'admin_bot_id', fallback=None)
            
            # 读取群组配置
            if 'groups' in config:
                groups_str = config.get('groups', 'monitored_groups', fallback='')
                if groups_str.strip():
                    self.monitored_groups = [
                        int(group.strip()) for group in groups_str.split(',') 
                        if group.strip().isdigit()
                    ]
                
                # 读取通讯群配置
                comm_group_str = config.get('groups', 'communication_group', fallback='')
                if comm_group_str.strip().isdigit():
                    self.communication_group = int(comm_group_str.strip())
            
            # 读取设置
            if 'settings' in config:
                self.enabled = config.getboolean('settings', 'enabled', fallback=True)
                self.log_level = config.get('settings', 'log_level', fallback='INFO')
                self.reject_add_request = config.getboolean('settings', 'reject_add_request', fallback=False)
            
            logger.info(f"配置加载成功: 监控{len(self.monitored_groups)}个群聊")
            
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """创建默认配置文件"""
        config = configparser.ConfigParser()
        
        config['bots'] = {
            'monitor_bot_id': '111111111',
            'admin_bot_id': '222222222'
        }
        
        config['groups'] = {
            'monitored_groups': '123456789, 987654321',
            'communication_group': '123456789'
        }
        
        config['settings'] = {
            'enabled': 'true',
            'log_level': 'INFO',
            'reject_add_request': 'false'
        }
        
        with open(config_file_path, 'w', encoding='utf-8') as f:
            config.write(f)

# 创建全局配置实例
plugin_config = PluginConfig()

async def is_group_admin(bot: Bot, group_id: int, user_id: int) -> bool:
    """检查用户是否为群管理员"""
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        role = member_info.get('role', 'member')
        return role in ['admin', 'owner']
    except Exception as e:
        logger.error(f"检查管理员权限失败: {e}")
        return False

async def find_user_in_monitored_groups(bot: Bot, user_id: int) -> Optional[int]:
    """检查用户是否在任何监控群中，返回找到的群号"""
    for group_id in plugin_config.monitored_groups:
        try:
            member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
            if member_info:  # 如果能获取到成员信息，说明用户在该群中
                logger.info(f"用户 {user_id} 在监控群 {group_id} 中")
                return group_id
        except Exception as e:
            # 用户不在该群中或其他错误，继续检查下一个群
            logger.debug(f"用户 {user_id} 不在群 {group_id} 中: {e}")
            continue
    return None

async def log_violation(user_id: int, group_id: int, user_card: str, nickname: str):
    """记录违规行为到日志文件"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | Group: {group_id} | User: {user_id} | Card: {user_card} | Nickname: {nickname} | Action: KICKED_FOR_INVITE\n"
        
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
        logger.info(f"违规记录已保存: {user_id} in {group_id}")
    except Exception as e:
        logger.error(f"保存违规日志失败: {e}")

def create_invite_rule() -> Rule:
    """创建群邀请事件规则"""
    async def _rule(event: GroupRequestEvent) -> bool:
        # 检查插件是否启用
        if not plugin_config.enabled:
            return False
        
        # 检查是否为群邀请事件
        if event.request_type != "group" or event.sub_type != "invite":
            return False
        
        # 检查是否为监控机器人接收的事件
        if str(event.self_id) != plugin_config.monitor_bot_id:
            return False
        
        # 检查邀请者是否在任何监控群中
        try:
            bot = nonebot.get_bot(str(event.self_id))
        except Exception as e:
            logger.error(f"无法获取监控机器人实例 {event.self_id}: {e}")
            return False
            
        monitored_group_id = await find_user_in_monitored_groups(bot, event.user_id)
        if not monitored_group_id:
            logger.debug(f"邀请者 {event.user_id} 不在任何监控群中，跳过处理")
            return False
        
        # 检查邀请者是否为监控群的管理员
        if await is_group_admin(bot, monitored_group_id, event.user_id):
            logger.info(f"邀请者 {event.user_id} 是监控群 {monitored_group_id} 的管理员，跳过处理")
            return False
        
        return True
    
    return Rule(_rule)

# 创建群邀请事件响应器
group_invite_handler = on_request(rule=create_invite_rule(), priority=5)

@group_invite_handler.handle()
async def handle_group_invite(event: GroupRequestEvent):
    """处理群邀请事件 - 监控机器人发送检测消息"""
    try:
        target_group_id = event.group_id  # 被邀请的目标群
        user_id = event.user_id
        
        logger.info(f"检测到群邀请事件: 用户{user_id}被邀请到群{target_group_id}")
        
        # 获取监控机器人实例
        try:
            monitor_bot = nonebot.get_bot(plugin_config.monitor_bot_id)
        except Exception as e:
            logger.error(f"无法找到监控机器人 {plugin_config.monitor_bot_id}: {e}")
            # 尝试从所有连接的机器人中查找
            bots = nonebot.get_bots()
            monitor_bot = bots.get(plugin_config.monitor_bot_id)
            if not monitor_bot:
                logger.error(f"监控机器人 {plugin_config.monitor_bot_id} 未连接")
                return
        
        # 找到邀请者所在的监控群
        monitored_group_id = await find_user_in_monitored_groups(monitor_bot, user_id)
        if not monitored_group_id:
            logger.error(f"无法找到邀请者 {user_id} 所在的监控群")
            return
        
        logger.info(f"邀请者 {user_id} 在监控群 {monitored_group_id} 中，将发送检测消息")
        
        # 获取用户在监控群中的信息
        try:
            member_info = await monitor_bot.get_group_member_info(group_id=monitored_group_id, user_id=user_id)
            user_card = member_info.get('card', '') or member_info.get('nickname', str(user_id))
            nickname = member_info.get('nickname', str(user_id))
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            user_card = str(user_id)
            nickname = str(user_id)
        
        # 获取目标群信息
        target_group_name = "未知群聊"
        try:
            target_group_info = await monitor_bot.get_group_info(group_id=target_group_id)
            target_group_name = target_group_info.get('group_name', f"群{target_group_id}")
        except Exception as e:
            logger.debug(f"无法获取目标群信息: {e}")
        
        # 记录违规日志（记录监控群信息）
        await log_violation(user_id, monitored_group_id, user_card, nickname)
        
        # 检查是否配置了通讯群
        if not plugin_config.communication_group:
            logger.error("未配置通讯群，无法发送检测消息")
            return
        
        # 构造检测消息 (Unix日志格式)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        detection_message = (
            f"InvalidGroupInvitationDetect | "
            f"Time: {timestamp} | "
            f"MonitorGroup: {monitored_group_id} | "
            f"User: {user_id} | "
            f"Card: {user_card} | "
            f"Nickname: {nickname} | "
            f"TargetGroup: {target_group_id} | "
            f"TargetGroupName: {target_group_name}"
        )
        
        # 在通讯群发送检测消息
        try:
            await monitor_bot.send_group_msg(group_id=plugin_config.communication_group, message=detection_message)
            logger.info(f"检测消息已发送到通讯群 {plugin_config.communication_group}")
        except Exception as e:
            logger.error(f"发送检测消息失败: {e}")
        
        # 如果配置了拒绝加群申请，则拒绝该邀请
        if plugin_config.reject_add_request:
            try:
                await monitor_bot.set_group_add_request(
                    flag=event.flag,
                    approve=False,
                    reason="检测到可疑邀请行为"
                )
                logger.info(f"已拒绝群邀请申请: {event.flag}")
            except Exception as e:
                logger.error(f"拒绝群邀请申请失败: {e}")
                logger.error(f"尝试调用的API: set_group_add_request(flag={event.flag}, approve=False)")
    
    except Exception as e:
        logger.error(f"处理群邀请事件时发生错误: {e}")

# 插件加载时的初始化
@nonebot.get_driver().on_startup
async def startup():
    """插件启动时的初始化"""
    logger.info("群邀请监控插件已加载")
    
    if not plugin_config.enabled:
        logger.warning("插件已禁用，请在配置文件中启用")
        return
    
    if not plugin_config.monitor_bot_id or not plugin_config.admin_bot_id:
        logger.error("机器人ID配置不完整，请检查配置文件")
        return
    
    if not plugin_config.monitored_groups:
        logger.warning("未配置监控群聊，插件将不会工作")
        return
    
    if not plugin_config.communication_group:
        logger.warning("未配置通讯群，分布式模式将无法正常工作")
    
    logger.info(f"插件配置完成:")
    logger.info(f"  监控机器人: {plugin_config.monitor_bot_id}")
    logger.info(f"  管理机器人: {plugin_config.admin_bot_id}")
    logger.info(f"  监控群聊: {plugin_config.monitored_groups}")
    logger.info(f"  通讯群聊: {plugin_config.communication_group}")
    
    # 分布式部署模式下，机器人连接状态将在连接时实时显示

@nonebot.get_driver().on_bot_connect
async def check_bot_connection(bot: Bot):
    """机器人连接时检查"""
    # 检查是否为配置的机器人
    if str(bot.self_id) == plugin_config.monitor_bot_id:
        logger.info(f"✓ 监控机器人 {bot.self_id} 已连接")
    elif str(bot.self_id) == plugin_config.admin_bot_id:
        logger.info(f"✓ 管理机器人 {bot.self_id} 已连接")
    else:
        logger.debug(f"机器人已连接: {bot.self_id} (非插件配置机器人)")

@nonebot.get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    """机器人断开连接时记录"""
    if str(bot.self_id) == plugin_config.monitor_bot_id:
        logger.warning(f"✗ 监控机器人 {bot.self_id} 已断开连接！")
    elif str(bot.self_id) == plugin_config.admin_bot_id:
        logger.warning(f"✗ 管理机器人 {bot.self_id} 已断开连接！")
    else:
        logger.debug(f"机器人已断开: {bot.self_id} (非插件配置机器人)")

@nonebot.get_driver().on_shutdown
async def shutdown():
    """插件关闭时的清理"""
    logger.info("群邀请监控插件已卸载")

# 超级用户命令：重载配置
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent

reload_config_cmd = on_command("reload_invite_config", permission=SUPERUSER, priority=1)

@reload_config_cmd.handle()
async def handle_reload_config():
    """重载配置文件"""
    global plugin_config
    plugin_config = PluginConfig()
    await reload_config_cmd.send("群邀请监控插件配置文件已重载")

# 测试命令：检查机器人状态
test_bots_cmd = on_command("test_invite_bots", permission=SUPERUSER, priority=1)

@test_bots_cmd.handle()
async def handle_test_bots():
    """测试机器人连接状态"""
    bots = nonebot.get_bots()
    
    status_msg = f"机器人连接状态检查：\n\n"
    status_msg += f"当前连接的机器人: {list(bots.keys())}\n\n"
    
    # 检查监控机器人
    if plugin_config.monitor_bot_id in bots:
        status_msg += f"✓ 监控机器人 {plugin_config.monitor_bot_id} 已连接\n"
    else:
        status_msg += f"✗ 监控机器人 {plugin_config.monitor_bot_id} 未连接\n"
    
    # 检查管理机器人
    if plugin_config.admin_bot_id in bots:
        status_msg += f"✓ 管理机器人 {plugin_config.admin_bot_id} 已连接\n"
    else:
        status_msg += f"✗ 管理机器人 {plugin_config.admin_bot_id} 未连接\n"
    
    status_msg += f"\n监控群聊: {plugin_config.monitored_groups}"
    status_msg += f"\n通讯群聊: {plugin_config.communication_group}"
    status_msg += f"\n插件状态: {'启用' if plugin_config.enabled else '禁用'}"
    
    await test_bots_cmd.send(status_msg)

# 管理机器人的消息监听器 - 监听检测消息并执行操作
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

def create_detection_message_rule() -> Rule:
    """创建检测消息规则"""
    async def _rule(event: GroupMessageEvent) -> bool:
        # 检查插件是否启用
        if not plugin_config.enabled:
            return False
        
        # 检查是否为通讯群的消息
        if not plugin_config.communication_group or event.group_id != plugin_config.communication_group:
            return False
        
        # 检查是否为管理机器人接收的消息
        if str(event.self_id) != plugin_config.admin_bot_id:
            return False
        
        # 检查消息是否以特定标识开头
        message_text = str(event.message).strip()
        if not message_text.startswith("InvalidGroupInvitationDetect"):
            return False
        
        return True
    
    return Rule(_rule)

# 创建检测消息响应器
detection_message_handler = on_message(rule=create_detection_message_rule(), priority=5)

@detection_message_handler.handle()
async def handle_detection_message(event: GroupMessageEvent):
    """处理检测消息 - 管理机器人执行踢人操作"""
    try:
        message_text = str(event.message).strip()
        logger.info(f"管理机器人收到检测消息: {message_text}")
        
        # 解析消息内容
        detection_data = parse_detection_message(message_text)
        if not detection_data:
            logger.error(f"无法解析检测消息: {message_text}")
            return
        
        monitor_group_id = detection_data['monitor_group']
        user_id = detection_data['user_id']
        user_card = detection_data['user_card']
        nickname = detection_data['nickname']
        target_group_id = detection_data['target_group']
        target_group_name = detection_data['target_group_name']
        
        logger.info(f"解析成功 - 监控群: {monitor_group_id}, 用户: {user_id}, 目标群: {target_group_id}")
        
        # 获取管理机器人实例
        try:
            admin_bot = nonebot.get_bot(plugin_config.admin_bot_id)
        except Exception as e:
            logger.error(f"无法找到管理机器人 {plugin_config.admin_bot_id}: {e}")
            bots = nonebot.get_bots()
            admin_bot = bots.get(plugin_config.admin_bot_id)
            if not admin_bot:
                logger.error(f"管理机器人 {plugin_config.admin_bot_id} 未连接")
                return
        
        # 执行踢人操作
        try:
            await admin_bot.set_group_kick(group_id=monitor_group_id, user_id=user_id)
            logger.info(f"已踢出用户: {user_id} 来自监控群 {monitor_group_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            logger.error(f"尝试调用的API: set_group_kick(group_id={monitor_group_id}, user_id={user_id})")
            return
        
        # 在监控群中发送警告消息
        warning_message = (
            f"检测到违规邀请行为！\n"
            f"成员：{user_card} ({user_id})\n"
            f"试图邀请群成员加入外部群聊：{target_group_name} ({target_group_id})\n"
            f"已被移出本群。请大家注意甄别，不要点击不明群聊邀请，谨防广告与诈骗！"
        )
        
        try:
            await admin_bot.send_group_msg(group_id=monitor_group_id, message=warning_message)
            logger.info(f"警告消息已发送到监控群 {monitor_group_id}")
        except Exception as e:
            logger.error(f"发送警告消息失败: {e}")
            logger.error(f"尝试调用的API: send_group_msg(group_id={monitor_group_id}, message=...)")
    
    except Exception as e:
        logger.error(f"处理检测消息时发生错误: {e}")

def parse_detection_message(message: str) -> Optional[Dict]:
    """解析检测消息"""
    try:
        # 消息格式：InvalidGroupInvitationDetect | Time: ... | MonitorGroup: ... | User: ... | ...
        parts = message.split(" | ")
        if len(parts) < 7:
            return None
        
        data = {}
        for part in parts[1:]:  # 跳过第一个标识符
            if ": " in part:
                key, value = part.split(": ", 1)
                data[key.strip()] = value.strip()
        
        # 检查必需的字段
        required_fields = ['MonitorGroup', 'User', 'Card', 'Nickname', 'TargetGroup', 'TargetGroupName']
        for field in required_fields:
            if field not in data:
                logger.error(f"检测消息缺少必需字段: {field}")
                return None
        
        return {
            'monitor_group': int(data['MonitorGroup']),
            'user_id': int(data['User']),
            'user_card': data['Card'],
            'nickname': data['Nickname'],
            'target_group': int(data['TargetGroup']),
            'target_group_name': data['TargetGroupName']
        }
    
    except Exception as e:
        logger.error(f"解析检测消息失败: {e}")
        return None
