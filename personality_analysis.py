"""
# 用户性格分析插件 (Personality Analysis)

基于聊天记录分析用户性格特征，生成详细的性格分析报告。

## 主要功能

- **大五人格分析**: 评估开放性、尽责性、外向性、宜人性、神经质五个维度
- **MBTI分析**: 判断用户的MBTI人格类型（16种类型之一）
- **行为模式识别**: 识别社交习惯、时间习惯、语言风格等
- **可视化报告**: 生成Markdown格式的详细分析报告
- **智能缓存**: 避免重复分析，提升效率

## 使用方法

直接向AI请求分析某个用户的性格，AI会自动调用插件进行分析。

## 配置说明

- **分析模型组**: 用于性格分析的LLM模型组
- **分析时间范围**: 默认分析最近30天的聊天记录
- **最大消息数**: 默认分析最近500条消息
- **缓存有效期**: 分析结果缓存7天
"""

import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from nekro_agent.api import core, schemas
from nekro_agent.api.plugin import ConfigBase, NekroPlugin, SandboxMethodType
from nekro_agent.models.db_chat_message import DBChatMessage
from nekro_agent.services.agent.openai import gen_openai_chat_response

plugin = NekroPlugin(
    name="用户性格分析插件",
    module_name="personality_analysis",
    description="基于聊天记录分析用户性格特征，生成大五人格和MBTI分析报告",
    version="0.1.0",
    author="A1A7432",
    url="https://github.com/1A7432/nekro-agent-personality-analysis",
    support_adapter=["onebot_v11", "discord", "telegram", "wechatpad", "wxwork"],
)


@plugin.mount_config()
class PersonalityAnalysisConfig(ConfigBase):
    """性格分析配置"""

    DEFAULT_ANALYSIS_DAYS: int = Field(
        default=30,
        title="默认分析时间范围（天）",
        description="分析最近多少天的聊天记录",
    )
    DEFAULT_MAX_MESSAGES: int = Field(
        default=500,
        title="默认最大分析消息数",
        description="最多分析多少条消息",
    )
    MIN_MESSAGE_THRESHOLD: int = Field(
        default=50,
        title="最小消息样本量阈值",
        description="少于该数量会警告样本量不足",
    )
    CACHE_EXPIRE_DAYS: int = Field(
        default=7,
        title="缓存过期天数",
        description="分析结果缓存的有效期（天）",
    )
    ENABLE_BIG_FIVE: bool = Field(
        default=True,
        title="启用大五人格分析",
        description="是否进行大五人格评估",
    )
    ENABLE_MBTI: bool = Field(
        default=True,
        title="启用MBTI分析",
        description="是否进行MBTI人格类型判断",
    )
    ENABLE_BEHAVIOR_PATTERN: bool = Field(
        default=True,
        title="启用行为模式识别",
        description="是否识别用户的行为模式",
    )
    ANALYSIS_MODEL_GROUP: str = Field(
        default="default",
        title="分析模型组",
        description="用于性格分析的模型组名称",
        json_schema_extra={"ref_model_groups": True, "required": True, "model_type": "chat"},
    )
    MAX_ANALYSIS_TOKENS: int = Field(
        default=2048,
        title="最大分析Token数",
        description="单次分析的最大输出Token数（用于LLM响应）",
    )


# 获取配置和插件存储
config: PersonalityAnalysisConfig = plugin.get_config(PersonalityAnalysisConfig)
store = plugin.store


# region: 数据模型定义


class BigFiveScore(BaseModel):
    """大五人格评分"""

    openness: int = Field(ge=0, le=100, description="开放性")
    conscientiousness: int = Field(ge=0, le=100, description="尽责性")
    extraversion: int = Field(ge=0, le=100, description="外向性")
    agreeableness: int = Field(ge=0, le=100, description="宜人性")
    neuroticism: int = Field(ge=0, le=100, description="神经质")


class MBTIResult(BaseModel):
    """MBTI分析结果"""

    mbti_type: str = Field(description="MBTI类型，如INFP")
    confidence: float = Field(ge=0, le=1, description="置信度")
    dimension_scores: Dict[str, float] = Field(
        description="各维度得分，如{'E-I': 0.6, 'S-N': 0.4, 'T-F': 0.7, 'J-P': 0.3}",
    )


class PersonalityAnalysisResult(BaseModel):
    """性格分析结果"""

    target_userid: str
    target_username: str
    analysis_timestamp: int
    message_sample_size: int
    time_range_start: int
    time_range_end: int
    big_five_scores: Optional[BigFiveScore] = None
    mbti_result: Optional[MBTIResult] = None
    personality_summary: str
    behavior_patterns: List[str]
    communication_style: str
    emotional_tendency: str
    report_markdown: str


class MessageStatistics(BaseModel):
    """消息统计信息"""

    total_count: int
    avg_length: float
    time_distribution: Dict[str, int]
    emoji_count: int
    mention_count: int
    question_count: int
    positive_count: int
    negative_count: int


# endregion: 数据模型定义


# region: 数据采集模块


async def query_user_messages(
    chat_key: str,
    target_userid: str,
    days: int,
    max_messages: int,
) -> List[DBChatMessage]:
    """查询用户历史消息"""
    end_time = int(time.time())
    start_time = end_time - (days * 24 * 60 * 60)

    messages = (
        await DBChatMessage.filter(
            chat_key=chat_key,
            platform_userid=target_userid,
            send_timestamp__gte=start_time,
            send_timestamp__lte=end_time,
            is_recalled=False,
        )
        .order_by("-send_timestamp")
        .limit(max_messages)
    )

    filtered_messages = []
    for msg in messages:
        if msg.is_system:
            continue
        if len(msg.content_text.strip()) < 2:
            continue
        filtered_messages.append(msg)

    return filtered_messages


def clean_message_text(text: str) -> str:
    """清洗消息文本"""
    text = re.sub(r"\[CQ:.*?\]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"1[3-9]\d{9}", "[手机号]", text)
    text = re.sub(r"\d{17}[\dXx]", "[身份证]", text)
    return text.strip()


def analyze_message_statistics(messages: List[DBChatMessage]) -> MessageStatistics:
    """分析消息统计信息"""
    if not messages:
        return MessageStatistics(
            total_count=0,
            avg_length=0,
            time_distribution={"morning": 0, "afternoon": 0, "evening": 0, "night": 0},
            emoji_count=0,
            mention_count=0,
            question_count=0,
            positive_count=0,
            negative_count=0,
        )

    total_length = 0
    time_dist = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
    emoji_count = 0
    mention_count = 0
    question_count = 0

    for msg in messages:
        total_length += len(msg.content_text)

        hour = datetime.fromtimestamp(msg.send_timestamp).hour
        if 6 <= hour < 12:
            time_dist["morning"] += 1
        elif 12 <= hour < 18:
            time_dist["afternoon"] += 1
        elif 18 <= hour < 23:
            time_dist["evening"] += 1
        else:
            time_dist["night"] += 1

        emoji_pattern = r"[\U0001F300-\U0001F9FF]|[\U0001F600-\U0001F64F]|[\U0001F680-\U0001F6FF]"
        emoji_count += len(re.findall(emoji_pattern, msg.content_text))

        if "[@" in msg.content_text or "@" in msg.content_text:
            mention_count += 1

        if "?" in msg.content_text or "？" in msg.content_text:
            question_count += 1

    avg_length = total_length / len(messages) if messages else 0

    return MessageStatistics(
        total_count=len(messages),
        avg_length=avg_length,
        time_distribution=time_dist,
        emoji_count=emoji_count,
        mention_count=mention_count,
        question_count=question_count,
        positive_count=0,
        negative_count=0,
    )


def prepare_analysis_input(messages: List[DBChatMessage], stats: MessageStatistics) -> str:
    """准备分析输入数据"""
    sample_messages = messages[:100] if len(messages) > 100 else messages

    message_texts = []
    for msg in sample_messages:
        cleaned_text = clean_message_text(msg.content_text)
        if cleaned_text:
            timestamp = datetime.fromtimestamp(msg.send_timestamp).strftime("%H:%M")
            message_texts.append(f"[{timestamp}] {cleaned_text}")

    input_text = "消息样本：\n" + "\n".join(message_texts)
    input_text += f"\n\n统计信息：\n"
    input_text += f"- 总消息数：{stats.total_count}\n"
    input_text += f"- 平均消息长度：{stats.avg_length:.1f}字\n"
    input_text += f"- 时间分布：早晨{stats.time_distribution['morning']}条，下午{stats.time_distribution['afternoon']}条，傍晚{stats.time_distribution['evening']}条，夜晚{stats.time_distribution['night']}条\n"
    input_text += f"- 表情符号使用：{stats.emoji_count}次\n"
    input_text += f"- @他人频率：{stats.mention_count}次\n"
    input_text += f"- 提问频率：{stats.question_count}次\n"

    return input_text


# endregion: 数据采集模块


# region: 性格分析引擎


async def analyze_big_five_personality(input_data: str) -> BigFiveScore:
    """大五人格分析"""
    prompt = f"""你是一位经验丰富的心理学专家，专精于基于文本行为分析进行大五人格评估。

请基于以下聊天消息样本和统计信息，分析用户在大五人格各维度的得分（0-100分）：

1. 开放性（Openness）：对新体验的接受程度，创造性，好奇心
2. 尽责性（Conscientiousness）：组织性，可靠性，自律性
3. 外向性（Extraversion）：社交性，活力，主动性
4. 宜人性（Agreeableness）：合作性，同理心，友善性
5. 神经质（Neuroticism）：情绪稳定性（分数越高越不稳定）

{input_data}

请严格按照以下JSON格式输出（仅输出JSON，不要任何其他内容）：
{{
    "openness": 整数（0-100）,
    "conscientiousness": 整数（0-100）,
    "extraversion": 整数（0-100）,
    "agreeableness": 整数（0-100）,
    "neuroticism": 整数（0-100）,
    "reasoning": "简要说明评分理由"
}}"""

    try:
        model_group = core.config.get_model_group_info(config.ANALYSIS_MODEL_GROUP)
        response = await gen_openai_chat_response(
            model=model_group.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            base_url=model_group.BASE_URL,
            api_key=model_group.API_KEY,
            temperature=0.3,
            max_tokens=1024,
        )

        content = response.response_content.strip()
        if not content:
            core.logger.warning("大五人格分析返回内容为空，使用默认值")
            return BigFiveScore(
                openness=50,
                conscientiousness=50,
                extraversion=50,
                agreeableness=50,
                neuroticism=50,
            )

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group()

        result = json.loads(content)
        return BigFiveScore(
            openness=result["openness"],
            conscientiousness=result["conscientiousness"],
            extraversion=result["extraversion"],
            agreeableness=result["agreeableness"],
            neuroticism=result["neuroticism"],
        )
    except Exception as e:
        core.logger.error(f"大五人格分析失败: {e}")
        return BigFiveScore(
            openness=50,
            conscientiousness=50,
            extraversion=50,
            agreeableness=50,
            neuroticism=50,
        )


async def analyze_mbti_type(input_data: str) -> MBTIResult:
    """MBTI分析"""
    prompt = f"""你是一位MBTI认证分析师，擅长从行为模式识别人格类型。

请根据用户的聊天行为和语言风格，判断其在MBTI四个维度上的倾向：

1. E（外向）vs I（内向）：能量来源
2. S（感觉）vs N（直觉）：信息处理
3. T（思考）vs F（情感）：决策方式
4. J（判断）vs P（知觉）：生活态度

{input_data}

请严格按照以下JSON格式输出（仅输出JSON，不要任何其他内容）：
{{
    "mbti_type": "四个字母的MBTI类型（如INFP）",
    "confidence": 0.0到1.0之间的小数,
    "dimension_scores": {{
        "E-I": 0.0到1.0（越接近0越I，越接近1越E）,
        "S-N": 0.0到1.0（越接近0越S，越接近1越N）,
        "T-F": 0.0到1.0（越接近0越T，越接近1越F）,
        "J-P": 0.0到1.0（越接近0越J，越接近1越P）
    }},
    "reasoning": "简要说明判断理由"
}}"""

    try:
        model_group = core.config.get_model_group_info(config.ANALYSIS_MODEL_GROUP)
        response = await gen_openai_chat_response(
            model=model_group.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            base_url=model_group.BASE_URL,
            api_key=model_group.API_KEY,
            temperature=0.3,
            max_tokens=1024,
        )

        content = response.response_content.strip()
        if not content:
            core.logger.warning("MBTI分析返回内容为空，使用默认值")
            return MBTIResult(
                mbti_type="XXXX",
                confidence=0.5,
                dimension_scores={"E-I": 0.5, "S-N": 0.5, "T-F": 0.5, "J-P": 0.5},
            )

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group()

        result = json.loads(content)
        return MBTIResult(
            mbti_type=result["mbti_type"],
            confidence=result["confidence"],
            dimension_scores=result["dimension_scores"],
        )
    except Exception as e:
        core.logger.error(f"MBTI分析失败: {e}")
        return MBTIResult(
            mbti_type="XXXX",
            confidence=0.5,
            dimension_scores={"E-I": 0.5, "S-N": 0.5, "T-F": 0.5, "J-P": 0.5},
        )


async def identify_behavior_patterns(input_data: str, stats: MessageStatistics) -> List[str]:
    """识别行为模式"""
    patterns = []

    max_time = max(stats.time_distribution, key=stats.time_distribution.get)
    time_patterns = {
        "morning": "早起鸟（经常在早晨活跃）",
        "afternoon": "午间活跃者（下午时段最为活跃）",
        "evening": "傍晚时段活跃",
        "night": "夜猫子（深夜时段活跃）",
    }
    patterns.append(time_patterns.get(max_time, "时间习惯不明显"))

    if stats.mention_count > stats.total_count * 0.3:
        patterns.append("高频互动者（喜欢@他人）")
    elif stats.mention_count < stats.total_count * 0.1:
        patterns.append("独立表达者（较少@他人）")

    if stats.emoji_count > stats.total_count * 0.5:
        patterns.append("emoji爱好者（频繁使用表情符号）")
    elif stats.emoji_count < stats.total_count * 0.1:
        patterns.append("纯文本派（很少使用表情）")

    if stats.avg_length > 50:
        patterns.append("详细表达者（消息通常较长）")
    elif stats.avg_length < 15:
        patterns.append("简洁派（消息简短精炼）")

    if stats.question_count > stats.total_count * 0.3:
        patterns.append("好奇提问者（经常提出问题）")

    return patterns


# endregion: 性格分析引擎


# region: 报告生成模块


def generate_progress_bar(score: int, max_length: int = 10) -> str:
    """生成文本进度条"""
    filled = int(score / 10)
    bar = "█" * filled + "░" * (max_length - filled)
    return f"{bar} {score}/100"


def get_mbti_description(mbti_type: str) -> str:
    """获取MBTI类型描述"""
    descriptions = {
        "INTJ": "建筑师型 - 富有想象力和战略性的思想家",
        "INTP": "逻辑学家型 - 具有创新精神的发明家",
        "ENTJ": "指挥官型 - 大胆、富有想象力的强大领导者",
        "ENTP": "辩论家型 - 聪明好奇的思想家",
        "INFJ": "提倡者型 - 安静而神秘的理想主义者",
        "INFP": "调停者型 - 诗意、善良的利他主义者",
        "ENFJ": "主人公型 - 富有魅力、鼓舞人心的领导者",
        "ENFP": "竞选者型 - 热情、有创造力的社交者",
        "ISTJ": "物流师型 - 实用、注重事实的可靠者",
        "ISFJ": "守卫者型 - 非常专注、温暖的保护者",
        "ESTJ": "总经理型 - 出色的管理者",
        "ESFJ": "执政官型 - 极有同情心、受欢迎的人",
        "ISTP": "鉴赏家型 - 大胆而实际的实验者",
        "ISFP": "探险家型 - 灵活、有魅力的艺术家",
        "ESTP": "企业家型 - 精明、善于感知的实干者",
        "ESFP": "表演者型 - 自发的、充满活力的表演者",
    }
    return descriptions.get(mbti_type, "未知类型")


def generate_markdown_report(result: PersonalityAnalysisResult) -> str:
    """生成Markdown格式报告"""
    lines = []

    lines.append(f"# 📊 用户性格分析报告")
    lines.append("")
    lines.append(f"**分析对象**: {result.target_username}")
    lines.append(f"**分析时间**: {datetime.fromtimestamp(result.analysis_timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(
        f"**数据范围**: {datetime.fromtimestamp(result.time_range_start).strftime('%Y-%m-%d')} 至 {datetime.fromtimestamp(result.time_range_end).strftime('%Y-%m-%d')}",
    )
    lines.append(f"**样本量**: {result.message_sample_size} 条消息")
    lines.append("")
    lines.append("---")
    lines.append("")

    if result.big_five_scores:
        lines.append("## 🎯 大五人格评估")
        lines.append("")
        scores = result.big_five_scores
        lines.append(f"**开放性 (Openness)**")
        lines.append(f"{generate_progress_bar(scores.openness)}")
        lines.append(f"对新体验的接受程度、创造性、好奇心")
        lines.append("")

        lines.append(f"**尽责性 (Conscientiousness)**")
        lines.append(f"{generate_progress_bar(scores.conscientiousness)}")
        lines.append(f"组织性、可靠性、自律性")
        lines.append("")

        lines.append(f"**外向性 (Extraversion)**")
        lines.append(f"{generate_progress_bar(scores.extraversion)}")
        lines.append(f"社交性、活力、主动性")
        lines.append("")

        lines.append(f"**宜人性 (Agreeableness)**")
        lines.append(f"{generate_progress_bar(scores.agreeableness)}")
        lines.append(f"合作性、同理心、友善性")
        lines.append("")

        lines.append(f"**神经质 (Neuroticism)**")
        lines.append(f"{generate_progress_bar(scores.neuroticism)}")
        lines.append(f"情绪稳定性（分数越低越稳定）")
        lines.append("")
        lines.append("---")
        lines.append("")

    if result.mbti_result and result.mbti_result.mbti_type != "XXXX":
        lines.append("## 🧩 MBTI人格类型")
        lines.append("")
        mbti = result.mbti_result
        lines.append(f"**类型**: **{mbti.mbti_type}** - {get_mbti_description(mbti.mbti_type)}")
        lines.append(f"**置信度**: {mbti.confidence * 100:.1f}%")
        lines.append("")

        lines.append("**各维度倾向**:")
        dims = mbti.dimension_scores
        ei_label = "外向(E)" if dims.get("E-I", 0.5) > 0.5 else "内向(I)"
        sn_label = "直觉(N)" if dims.get("S-N", 0.5) > 0.5 else "感觉(S)"
        tf_label = "情感(F)" if dims.get("T-F", 0.5) > 0.5 else "思考(T)"
        jp_label = "知觉(P)" if dims.get("J-P", 0.5) > 0.5 else "判断(J)"

        lines.append(f"- 能量来源: {ei_label} ({dims.get('E-I', 0.5) * 100:.0f}%)")
        lines.append(f"- 信息处理: {sn_label} ({dims.get('S-N', 0.5) * 100:.0f}%)")
        lines.append(f"- 决策方式: {tf_label} ({dims.get('T-F', 0.5) * 100:.0f}%)")
        lines.append(f"- 生活态度: {jp_label} ({dims.get('J-P', 0.5) * 100:.0f}%)")
        lines.append("")
        lines.append("---")
        lines.append("")

    if result.behavior_patterns:
        lines.append("## 🔍 行为模式洞察")
        lines.append("")
        for pattern in result.behavior_patterns:
            lines.append(f"- {pattern}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## 💬 沟通风格")
    lines.append("")
    lines.append(result.communication_style)
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 😊 情感倾向")
    lines.append("")
    lines.append(result.emotional_tendency)
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 🎨 综合性格画像")
    lines.append("")
    lines.append(result.personality_summary)
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ **免责声明**: 本报告基于聊天记录的AI分析生成，仅供娱乐参考，不构成专业心理评估。")

    return "\n".join(lines)


# endregion: 报告生成模块


# region: 缓存管理模块


async def get_cached_result(chat_key: str, target_userid: str) -> Optional[PersonalityAnalysisResult]:
    """获取缓存的分析结果"""
    cache_key = f"analysis_{target_userid}_{chat_key}"
    cached_data = await store.get(store_key=cache_key)

    if not cached_data:
        return None

    try:
        result = PersonalityAnalysisResult.model_validate_json(cached_data)
        cache_expire_seconds = config.CACHE_EXPIRE_DAYS * 24 * 60 * 60
        if time.time() - result.analysis_timestamp > cache_expire_seconds:
            core.logger.info(f"缓存已过期: {cache_key}")
            return None
        return result
    except Exception as e:
        core.logger.error(f"解析缓存数据失败: {e}")
        return None


async def save_result_to_cache(chat_key: str, target_userid: str, result: PersonalityAnalysisResult):
    """保存分析结果到缓存"""
    cache_key = f"analysis_{target_userid}_{chat_key}"
    await store.set(store_key=cache_key, value=result.model_dump_json())
    core.logger.info(f"已缓存分析结果: {cache_key}")


async def clear_cache(chat_key: str, target_userid: str):
    """清除缓存"""
    cache_key = f"analysis_{target_userid}_{chat_key}"
    await store.delete(store_key=cache_key)
    core.logger.info(f"已清除缓存: {cache_key}")


# endregion: 缓存管理模块


# region: 沙盒方法


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="分析用户性格",
    description="分析指定用户的性格特征并生成详细报告",
)
async def analyze_user_personality(
    _ctx: schemas.AgentCtx,
    chat_key: str,
    target_userid: str,
    days: int,
    max_messages: int,
    force_refresh: bool,
) -> str:
    """Analyze User Personality (分析用户性格)

    Analyze a user's personality based on their chat history and generate a detailed report.

    Args:
        chat_key (str): Chat channel identifier (use _ck in sandbox)
        target_userid (str): Target user's platform ID
        days (int): Analysis time range in days (e.g., 30 for last 30 days)
        max_messages (int): Maximum number of messages to analyze (e.g., 500)
        force_refresh (bool): Whether to force refresh cache and reanalyze

    Returns:
        str: Markdown formatted personality analysis report

    Example:
        analyze_user_personality(_ck, "user_12345", 30, 500, False)
    """
    if not target_userid:
        raise ValueError("Error: Target user ID cannot be empty!")

    if days < 1 or days > 365:
        raise ValueError("Error: Days must be between 1 and 365!")

    if max_messages < config.MIN_MESSAGE_THRESHOLD or max_messages > 5000:
        raise ValueError(f"Error: Max messages must be between {config.MIN_MESSAGE_THRESHOLD} and 5000!")

    if not force_refresh:
        cached_result = await get_cached_result(chat_key, target_userid)
        if cached_result:
            core.logger.info(f"使用缓存的分析结果: {target_userid}")
            return cached_result.report_markdown

    core.logger.info(f"开始分析用户性格: {target_userid}, 时间范围: {days}天, 最大消息数: {max_messages}")
    messages = await query_user_messages(chat_key, target_userid, days, max_messages)

    if not messages:
        raise ValueError(f"Error: No chat messages found for user {target_userid} in the last {days} days!")

    if len(messages) < config.MIN_MESSAGE_THRESHOLD:
        core.logger.warning(f"消息样本量不足: {len(messages)} < {config.MIN_MESSAGE_THRESHOLD}")

    stats = analyze_message_statistics(messages)
    input_data = prepare_analysis_input(messages, stats)

    big_five_scores = None
    mbti_result = None

    if config.ENABLE_BIG_FIVE:
        core.logger.info("执行大五人格分析...")
        big_five_scores = await analyze_big_five_personality(input_data)

    if config.ENABLE_MBTI:
        core.logger.info("执行MBTI分析...")
        mbti_result = await analyze_mbti_type(input_data)

    behavior_patterns = []
    if config.ENABLE_BEHAVIOR_PATTERN:
        core.logger.info("识别行为模式...")
        behavior_patterns = await identify_behavior_patterns(input_data, stats)

    username = messages[0].sender_nickname if messages else "未知用户"

    communication_style = "该用户的沟通风格表现为："
    if stats.avg_length > 50:
        communication_style += "喜欢详细表达，消息内容丰富；"
    else:
        communication_style += "倾向简洁沟通，言简意赅；"

    if stats.emoji_count > stats.total_count * 0.3:
        communication_style += "频繁使用表情符号增强表达；"

    if stats.mention_count > stats.total_count * 0.2:
        communication_style += "主动与他人互动，喜欢@提及他人。"

    emotional_tendency = "从情感表达来看，"
    if big_five_scores and big_five_scores.neuroticism < 40:
        emotional_tendency += "该用户情绪较为稳定，表现出良好的心理韧性。"
    elif big_five_scores and big_five_scores.neuroticism > 60:
        emotional_tendency += "该用户情感表达较为丰富，有时会表现出情绪波动。"
    else:
        emotional_tendency += "该用户的情感表达处于正常范围。"

    personality_summary = f"综合来看，{username}是一个"
    if big_five_scores:
        if big_five_scores.extraversion > 60:
            personality_summary += "外向活跃、"
        elif big_five_scores.extraversion < 40:
            personality_summary += "内敛深思、"

        if big_five_scores.openness > 60:
            personality_summary += "富有创造力、"

        if big_five_scores.conscientiousness > 60:
            personality_summary += "做事认真、"

        if big_five_scores.agreeableness > 60:
            personality_summary += "友善合作的人。"
        else:
            personality_summary += "独立自主的人。"
    else:
        personality_summary += "有独特个性的人。"

    result = PersonalityAnalysisResult(
        target_userid=target_userid,
        target_username=username,
        analysis_timestamp=int(time.time()),
        message_sample_size=len(messages),
        time_range_start=int(time.time()) - (days * 24 * 60 * 60),
        time_range_end=int(time.time()),
        big_five_scores=big_five_scores,
        mbti_result=mbti_result,
        personality_summary=personality_summary,
        behavior_patterns=behavior_patterns,
        communication_style=communication_style,
        emotional_tendency=emotional_tendency,
        report_markdown="",
    )

    result.report_markdown = generate_markdown_report(result)

    await save_result_to_cache(chat_key, target_userid, result)

    core.logger.info(f"性格分析完成: {target_userid}")
    return result.report_markdown


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="获取性格分析报告",
    description="获取已生成的用户性格分析报告",
)
async def get_personality_report(_ctx: schemas.AgentCtx, chat_key: str, target_userid: str) -> str:
    """Get Personality Report (获取性格分析报告)

    Get a previously generated personality analysis report from cache.

    Args:
        chat_key (str): Chat channel identifier (use _ck in sandbox)
        target_userid (str): Target user's platform ID

    Returns:
        str: Markdown formatted report or error message

    Example:
        get_personality_report(_ck, "user_12345")
    """
    cached_result = await get_cached_result(chat_key, target_userid)
    if not cached_result:
        raise ValueError(f"Error: No cached personality analysis found for user {target_userid}. Please run analysis first.")

    return cached_result.report_markdown


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="清除性格分析缓存",
    description="清除指定用户的性格分析缓存",
)
async def clear_personality_cache(_ctx: schemas.AgentCtx, chat_key: str, target_userid: str) -> str:
    """Clear Personality Cache (清除性格分析缓存)

    Clear the cached personality analysis for a specific user.

    Args:
        chat_key (str): Chat channel identifier (use _ck in sandbox)
        target_userid (str): Target user's platform ID

    Returns:
        str: Success message

    Example:
        clear_personality_cache(_ck, "user_12345")
    """
    await clear_cache(chat_key, target_userid)
    return f"Successfully cleared personality analysis cache for user {target_userid}"


# endregion: 沙盒方法


# region: 提示注入


@plugin.mount_prompt_inject_method(name="personality_analysis_prompt_inject")
async def personality_analysis_prompt_inject(_ctx: schemas.AgentCtx) -> str:
    """性格分析提示注入"""
    return """Personality Analysis Plugin Available:
- You can analyze user personality by calling analyze_user_personality tool
- User can request: "分析XXX的性格" or "给我看看XXX的性格报告"
- The analysis is based on chat history and includes Big Five and MBTI assessment"""


# endregion: 提示注入


# region: 清理方法


@plugin.mount_cleanup_method()
async def clean_up():
    """清理插件资源"""
    core.logger.info("性格分析插件清理完成")


# endregion: 清理方法
