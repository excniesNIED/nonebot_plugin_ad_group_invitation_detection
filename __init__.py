"""
NoneBot 2 QQ群邀请行为监控插件

用于监控QQ群的邀请行为并自动踢出违规邀请者的插件
支持双机器人模式：监控机器人+管理机器人

Author: AI Assistant
Version: 1.0.0
"""

import os
import time
import configparser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from nonebot import get_bots, get_driver, logger
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.adapters.lagrange import Adapter, Bot
from nonebot.adapters.lagrange.event import (
    GroupEvent,
    NoticeEvent,
    GroupInviteNoticeEvent
)
from nonebot.adapters.lagrange.permission import GROUP
from nonebot import on_notice

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="群邀请监控",
    description="监控QQ群的邀请行为并自动踢出违规邀请者",
    usage="配置config.ini文件后自动运行",
    homepage="https://github.com/example/nonebot_plugin_ad_group_invitation_detection",
    type="application",
    supported_adapters={"~lagrange"}
)

# 配置文件路径 - 可根据需要修改
CONFIG_PATH = Path(__file__).parent / "config.ini"
LOG_PATH = Path(__file__).parent / "invitation_logs.txt"

# 全局配置存储
config_data = {
    "monitored_groups": [],
    "monitor_bot_id": "",
    "admin_bot_id": "",
    "enabled": False
}


def load_config() -> bool:
    """加载配置文件"""
    global config_data
    
    if not CONFIG_PATH.exists():
        logger.warning(f"配置文件不存在: {CONFIG_PATH}")
        return False
    
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding='utf-8')
        
        # 读取基本配置
        config_data["monitor_bot_id"] = config.get("bots", "monitor_bot_id", fallback="")
        config_data["admin_bot_id"] = config.get("bots", "admin_bot_id", fallback="")
        
        # 读取监控群组列表
        groups_str = config.get("groups", "monitored_groups", fallback="")
        if groups_str:
            # 支持逗号分隔的群号列表
            groups = [int(g.strip()) for g in groups_str.split(",") if g.strip().isdigit()]
            config_data["monitored_groups"] = groups
        
        # 检查配置完整性
        if not config_data["monitor_bot_id"] or not config_data["admin_bot_id"]:
            logger.error("机器人ID配置不完整")
            return False
        
        if not config_data["monitored_groups"]:
            logger.error("监控群组列表为空")
            return False
        
        config_data["enabled"] = True
        logger.info(f"配置加载成功: 监控机器人={config_data['monitor_bot_id']}, "
                   f"管理机器人={config_data['admin_bot_id']}, "
                   f"监控群组={config_data['monitored_groups']}")
        return True
        
    except Exception as e:
        logger.error(f"配置文件加载失败: {e}")
        return False


def save_log(user_id: int, user_card: str, user_name: str, group_id: int, invited_group: str = "未知") -> None:
    """保存违规邀请日志"""
    try:
        timestamp = int(time.time())
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = (f"{timestamp}\t{date_str}\t{user_id}\t{user_card}\t{user_name}\t"
                    f"{group_id}\t{invited_group}\n")
        
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        logger.info(f"日志已保存: {user_id} 在群 {group_id} 发送违规邀请")
    except Exception as e:
        logger.error(f"保存日志失败: {e}")


async def get_admin_bot() -> Optional[Bot]:
    """获取管理机器人实例"""
    bots = get_bots()
    admin_bot_id = config_data.get("admin_bot_id")
    
    if admin_bot_id in bots:
        return bots[admin_bot_id]
    
    logger.error(f"未找到管理机器人: {admin_bot_id}")
    return None


async def check_user_is_admin(bot: Bot, group_id: int, user_id: int) -> bool:
    """检查用户是否为群管理员"""
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        role = member_info.get("role", "member")
        return role in ["admin", "owner"]
    except Exception as e:
        logger.error(f"检查用户权限失败: {e}")
        return False


def invitation_rule() -> Rule:
    """群邀请事件规则"""
    async def _rule(event: NoticeEvent) -> bool:
        # 检查配置是否启用
        if not config_data.get("enabled", False):
            return False
        
        # 检查是否为群邀请事件
        if not isinstance(event, GroupInviteNoticeEvent):
            return False
        
        # 检查是否为监控群组
        if event.group_id not in config_data["monitored_groups"]:
            return False
        
        # 检查是否由监控机器人接收
        # 注意：这里可能需要根据实际事件结构调整
        return True
    
    return Rule(_rule)


# 注册事件响应器
invitation_handler = on_notice(
    rule=invitation_rule(),
    permission=GROUP,
    priority=1,
    block=True
)


@invitation_handler.handle()
async def handle_group_invitation(event: GroupInviteNoticeEvent):
    """处理群邀请事件"""
    try:
        # 获取事件信息
        group_id = event.group_id
        inviter_id = event.user_id
        
        logger.info(f"检测到群邀请事件: 群={group_id}, 邀请者={inviter_id}")
        
        # 获取当前机器人和管理机器人
        current_bot = get_bots().get(str(event.self_id))
        admin_bot = await get_admin_bot()
        
        if not admin_bot:
            logger.error("无法获取管理机器人，停止处理")
            return
        
        # 检查邀请者是否为管理员
        if await check_user_is_admin(admin_bot, group_id, inviter_id):
            logger.info(f"邀请者 {inviter_id} 是管理员，跳过处理")
            return
        
        # 获取邀请者信息
        try:
            member_info = await admin_bot.get_group_member_info(
                group_id=group_id, 
                user_id=inviter_id
            )
            user_card = member_info.get("card", "")
            user_name = member_info.get("nickname", "")
            if not user_card:
                user_card = user_name
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            user_card = "未知用户"
            user_name = "未知"
        
        # 保存日志
        invited_group_info = getattr(event, 'invited_group', '未知')
        save_log(inviter_id, user_card, user_name, group_id, str(invited_group_info))
        
        # 踢出违规用户
        try:
            await admin_bot.set_group_kick(
                group_id=group_id,
                user_id=inviter_id,
                reject_add_request=False
            )
            logger.info(f"已踢出用户: {inviter_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return
        
        # 发送警告消息
        warning_message = (
            f"检测到违规邀请行为！\n"
            f"成员：{user_card} ({inviter_id})\n"
            f"已被移出本群。请大家注意甄别，不要点击不明群聊邀请，谨防广告与诈骗！"
        )
        
        try:
            await admin_bot.send_group_msg(
                group_id=group_id,
                message=warning_message
            )
            logger.info(f"警告消息已发送到群 {group_id}")
        except Exception as e:
            logger.error(f"发送警告消息失败: {e}")
        
    except Exception as e:
        logger.error(f"处理群邀请事件时发生错误: {e}")


# 在插件加载时读取配置
driver = get_driver()

@driver.on_startup
async def _():
    """插件启动时加载配置"""
    if load_config():
        logger.info("群邀请监控插件已启动")
    else:
        logger.warning("群邀请监控插件配置加载失败，插件将不会工作")


@driver.on_shutdown
async def _():
    """插件关闭时的清理工作"""
    logger.info("群邀请监控插件已关闭")
