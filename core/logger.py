"""
[模块] core/logger.py — 全局日志审计（简单 + 详细双通道）
[职责] 简单日志记录流程级审计（任务/Agent/工具调用）；详细日志额外记录与各模型的交互输入输出
[设计思想] 双通道同一套初始化逻辑（_init_logger），按 name 区分、独立文件；
           "详细=简单+LLM交互" 由 llm_config.LoggingLLM 自动写入，本模块不感知 LLM 细节；
           详细日志可用人工全局设置 manual_settings.DETAIL_LOG_ENABLED 关闭（.env 可覆盖）
[关键约定] 日志目录固定在 logs/；同一 logger name 不叠加 handler（防重复写入）；
           所有 handler 均加 StreamHandler，便于命令行/测试直接看到审计输出；
           DETAIL_LOG_ENABLED=false 时详细日志完全静默（不落盘、不打印），简单日志不受影响
[被谁调用] 全项目模块（planner/agent_registry/web_gui 等），通过 get_logger / get_detail_logger
[修改注意] 改日志格式需同步格式常量 _FORMAT；新增日志通道参照 _init_logger；
           详细日志开关值在 manual_settings.py 与 AGENTS.md §6 同步维护
"""
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

import manual_settings

# 先加载 .env（幂等），确保密钥/覆盖值在任意 import 顺序下都可读
load_dotenv()

# logs 目录固定在项目根下
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _init_logger(name: str, filename_prefix: str, persist: bool = True) -> logging.Logger:
    """按 name 初始化一次 handler 的具名 logger（同一 name 不叠加 handler）
    persist=False：NullHandler 静默（不落盘、不打印），供可全局关闭的详细日志使用
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(_FORMAT)

        if not persist:
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
            return logger

        log_file = os.path.join(LOG_DIR, f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        logger.propagate = False
    return logger


def get_logger(name: str = "research_system") -> logging.Logger:
    """
    简单日志：流程级审计（任务开始/结束、Agent 调用、工具调用）
    → logs/run_*.log
    """
    return _init_logger(name, "run")


def get_detail_logger(name: str = "research_system_detail") -> logging.Logger:
    """
    详细日志：流程级审计 + 与各模型的交互输入输出
    → logs/detail_run_*.log
    全局开关：manual_settings.DETAIL_LOG_ENABLED（默认 true；.env 的 DETAIL_LOG_ENABLED=false 可覆盖）
    """
    enabled = os.getenv("DETAIL_LOG_ENABLED", str(manual_settings.DETAIL_LOG_ENABLED)).strip().lower() in ("1", "true", "yes", "on")
    return _init_logger(name, "detail_run", persist=enabled)
