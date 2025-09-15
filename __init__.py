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
            'monitored_groups': '123456789, 987654321'
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
        
        # 检查是否为监控的群聊
        if event.group_id not in plugin_config.monitored_groups:
            return False
        
        # 检查是否为监控机器人接收的事件
        if str(event.self_id) != plugin_config.monitor_bot_id:
            return False
        
        # 检查邀请者是否为管理员
        bot = nonebot.get_bot(str(event.self_id))
        if await is_group_admin(bot, event.group_id, event.user_id):
            logger.info(f"群邀请来自管理员 {event.user_id}，跳过处理")
            return False
        
        return True
    
    return Rule(_rule)

# 创建群邀请事件响应器
group_invite_handler = on_request(rule=create_invite_rule(), priority=5)

@group_invite_handler.handle()
async def handle_group_invite(event: GroupRequestEvent):
    """处理群邀请事件"""
    try:
        group_id = event.group_id
        user_id = event.user_id
        
        logger.info(f"检测到群邀请事件: 群{group_id} 用户{user_id}")
        
        # 获取监控机器人实例
        monitor_bot = nonebot.get_bot(plugin_config.monitor_bot_id)
        if not monitor_bot:
            logger.error(f"无法找到监控机器人: {plugin_config.monitor_bot_id}")
            return
        
        # 获取管理机器人实例
        admin_bot = nonebot.get_bot(plugin_config.admin_bot_id)
        if not admin_bot:
            logger.error(f"无法找到管理机器人: {plugin_config.admin_bot_id}")
            return
        
        # 获取用户信息
        try:
            member_info = await monitor_bot.get_group_member_info(group_id=group_id, user_id=user_id)
            user_card = member_info.get('card', '') or member_info.get('nickname', str(user_id))
            nickname = member_info.get('nickname', str(user_id))
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            user_card = str(user_id)
            nickname = str(user_id)
        
        # 记录违规日志
        await log_violation(user_id, group_id, user_card, nickname)
        
        # 使用管理机器人踢出用户
        try:
            await admin_bot.kick_group_member(group_id=group_id, user_id=user_id)
            logger.info(f"已踢出用户: {user_id} 来自群 {group_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return
        
        # 发送警告消息
        warning_message = (
            f"检测到违规邀请行为！\n"
            f"成员：{user_card} ({user_id})\n"
            f"已被移出本群。请大家注意甄别，不要点击不明群聊邀请，谨防广告与诈骗！"
        )
        
        try:
            await admin_bot.send_group_msg(group_id=group_id, message=warning_message)
            logger.info(f"警告消息已发送到群 {group_id}")
        except Exception as e:
            logger.error(f"发送警告消息失败: {e}")
        
        # 如果配置了拒绝加群申请，则拒绝该邀请
        if plugin_config.reject_add_request:
            try:
                await monitor_bot.set_group_add_request(
                    flag=event.flag,
                    sub_type=event.sub_type,
                    approve=False,
                    reason="检测到可疑邀请行为"
                )
                logger.info(f"已拒绝群邀请申请: {event.flag}")
            except Exception as e:
                logger.error(f"拒绝群邀请申请失败: {e}")
    
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
    
    logger.info(f"插件配置完成:")
    logger.info(f"  监控机器人: {plugin_config.monitor_bot_id}")
    logger.info(f"  管理机器人: {plugin_config.admin_bot_id}")
    logger.info(f"  监控群聊: {plugin_config.monitored_groups}")

@nonebot.get_driver().on_shutdown
async def shutdown():
    """插件关闭时的清理"""
    logger.info("群邀请监控插件已卸载")

# 超级用户命令：重载配置
reload_config = on_request(permission=SUPERUSER, priority=1)

@reload_config.handle()
async def handle_reload_config(event):
    """重载配置文件"""
    global plugin_config
    plugin_config = PluginConfig()
    await reload_config.send("配置文件已重载")
