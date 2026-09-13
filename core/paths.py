"""
[模块] core/paths.py — 全局路径与规范常量（唯一事实来源）
[职责] 统一项目根、资料库、输出目录、研究档案目录、主题仓库元数据文件、短文件阈值、
       事实审核有界循环上限等常量；提供"主题域（domain）"路径解析函数
[设计思想] 资料仓库规范（目录/命名/阈值）与流程级常量集中在单文件；
           主题域 = 隔离单元（domains/<名称>/），通用层 = 项目根目录（general，跨域共享）；
           路径按域函数化解析，域从任务状态（state["domain"]）传入，不用全局变量（防多任务串域）；
           域自动注册规则 = "目录即注册"：domains/ 下非 "_" 开头的子目录即为域（配置 _domain.md 可选增强）；
           "_" 开头的目录 = 隐藏（模板域/回收站），不注册不显示
[关键约定] ★ 主题库 = LocalDataBase/ 下含 _repo.md 的子目录；目录名规范"NN-主题短语"（中英文均可）；
           ★ 资料文件规范"NN-主题短语.md"（编号自动补）；_repo.md = 仓库自描述 + 文件摘要索引；
           ★ SHORT_FILE_THRESHOLD：字符数低于该值视为短文件，摘要读取时直接附全文（省会话轮次）；
           ★ ARCHIVE_DIR：研究过程档案目录（独立于资料库，不入 list_topics，避免污染 researcher 读取）；
           ★ 域语义：domain=None/"general" → 通用层（根目录，向后兼容）；具体域 → domains/<域>/；
             local_db_root(domain) 等函数是路径唯一入口，禁止直接拼路径；
           ★ 保留域名：general（通用层）、"_" 开头（隐藏）；建/改名必须经 is_reserved_domain_name 校验
[被谁调用] skills/ 全部资料类 Skill、researcher_agent、archivist_agent、collector_agent、
           document_output、archive_process、fact_check_article 流程、dynamic_planner（循环上限）、
           task_manager / main.py（任务级域传递）、core/domain_config.py（建域/重命名/统计）、
           resource_browser、测试
[修改注意] 改目录/命名规范会影响既有资料布局，需同步迁移
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DB = os.path.join(PROJECT_ROOT, "LocalDataBase")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
# 研究过程档案目录：任务结束后封存"计划+各角色产出+最终文章"（结构化摘要，非日志全文）
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "archives")

# ---- 主题域（domain）----
# 通用层 = 项目根目录（跨域共享，向后兼容）；具体域 = domains/<名称>/
DOMAINS_ROOT = os.path.join(PROJECT_ROOT, "domains")
DEFAULT_DOMAIN = "general"
# 域配置文件名（目录内可选自描述文件，与主题库 _repo.md 同构；无此文件目录仍是域）
DOMAIN_CONFIG_FILE = "_domain.md"
# 新建域时自动生成的子目录骨架（资料/输出/档案，与通用层同名同构）
DOMAIN_LAYOUT_DIRS = ("LocalDataBase", "output", "archives")


def list_domains() -> list:
    """列出已有主题域（domains/ 下非 "_" 开头的子目录，模板/回收站等隐藏）；
    通用层 general 恒有（不算在此列表）"""
    if not os.path.isdir(DOMAINS_ROOT):
        return []
    return sorted(n for n in os.listdir(DOMAINS_ROOT)
                  if os.path.isdir(os.path.join(DOMAINS_ROOT, n)) and not n.startswith("_"))


def is_reserved_domain_name(name) -> bool:
    """域名保留校验：空/通用层（general）/下划线开头（隐藏）不可用作新建或重命名目标"""
    n = (str(name or "").strip().lower())
    return not n or n == DEFAULT_DOMAIN or n.startswith("_")


def ensure_domain_dirs(domain: str) -> str:
    """创建域名目录 + 子目录骨架（资料/输出/档案），返回域名目录路径（幂等）"""
    d = _norm_domain(domain)
    if not d:
        raise ValueError("通用层（general）没有独立域目录，无需创建")
    dpath = os.path.join(DOMAINS_ROOT, d)
    os.makedirs(dpath, exist_ok=True)
    for sub in DOMAIN_LAYOUT_DIRS:
        os.makedirs(os.path.join(dpath, sub), exist_ok=True)
    return dpath


def _norm_domain(domain) -> str:
    """归一化域：None/空/"general" → 通用层（返回 None）；其余返回小写域名"""
    d = (str(domain or "").strip().lower())
    return d if d and d != DEFAULT_DOMAIN else None


def local_db_root(domain=None) -> str:
    """资料库根路径：域私有 = domains/<域>/LocalDataBase；通用层 = 根 LocalDataBase"""
    d = _norm_domain(domain)
    return os.path.join(DOMAINS_ROOT, d, "LocalDataBase") if d else LOCAL_DB


def output_root(domain=None) -> str:
    """输出目录根路径（域私有 / 通用层）"""
    d = _norm_domain(domain)
    return os.path.join(DOMAINS_ROOT, d, "output") if d else OUTPUT_DIR


def archive_root(domain=None) -> str:
    """研究档案根路径（域私有 / 通用层）"""
    d = _norm_domain(domain)
    return os.path.join(DOMAINS_ROOT, d, "archives") if d else ARCHIVE_DIR


# 主题仓库元数据/索引文件名（目录下存在此文件才算主题库，自动注册依据）
REPO_META_FILE = "_repo.md"
# 短文件阈值（字符数）：≤ 此值视为短文件，read_topic_summary 时直接附全文
SHORT_FILE_THRESHOLD = 2000
# 主题库/文件编号前缀格式（NN-）
TOPIC_PREFIX_PATTERN = r"^\d{1,3}-"
# 事实审核有界循环上限：fact_checker 判定不通过时的最大回溯修订次数（防死循环，两引擎共用）
FACT_CHECK_MAX_RETRIES = 2
