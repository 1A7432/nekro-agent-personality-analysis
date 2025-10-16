# Nekro Agent 用户性格分析插件

[![GitHub](https://img.shields.io/github/license/1A7432/nekro-agent-personality-analysis)](https://github.com/1A7432/nekro-agent-personality-analysis/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Nekro Agent](https://img.shields.io/badge/Nekro_Agent-Plugin-green.svg)](https://github.com/KroMiose/nekro-agent)

基于聊天记录分析用户性格特征的 Nekro Agent 第三方插件，采用大五人格模型和MBTI理论，生成详细的性格分析报告。

## ✨ 主要功能

- 🎯 **大五人格分析**：评估开放性、尽责性、外向性、宜人性、神经质五个维度
- 🧩 **MBTI类型判断**：识别16种MBTI人格类型
- 🔍 **行为模式识别**：分析用户的时间习惯、互动风格、表达方式
- 📊 **可视化报告**：生成Markdown格式的详细分析报告
- 💾 **智能缓存**：7天缓存机制，提升响应速度

## 📦 安装方法

### 方式一：克隆仓库（推荐）

```bash
cd /path/to/nekro-agent/plugins/workdir
git clone https://github.com/1A7432/nekro-agent-personality-analysis.git personality_analysis
```

### 方式二：手动下载

1. 下载本仓库的代码
2. 解压到 `nekro-agent/plugins/workdir/personality_analysis` 目录

### 安装后

重启 Nekro Agent 或在管理界面重新加载插件即可。

## 🚀 使用方法

### 基本使用

直接向AI发起请求：

```
分析一下张三的性格
```

AI会自动调用插件进行分析，并返回详细的性格分析报告。

### 通过代码调用

```python
# 在沙盒环境中调用
/exec analyze_user_personality(chat_key, "user_12345", 30, 500, False)
```

### 参数说明

- `chat_key`: 聊天频道标识（自动获取）
- `target_userid`: 目标用户的平台ID
- `days`: 分析时间范围（天），默认30天
- `max_messages`: 最大分析消息数，默认500条
- `force_refresh`: 是否强制刷新缓存，默认False

## 📊 分析报告示例

报告包含以下内容：

### 🎯 大五人格评估

```
开放性 (Openness)
████████░░ 82/100
对新体验的接受程度、创造性、好奇心

外向性 (Extraversion)
███████████ 95/100
社交性、活力、主动性
```

### 🧩 MBTI人格类型

```
类型: ENFP - 竞选者型 - 热情、有创造力的社交者
置信度: 78.5%

各维度倾向:
- 能量来源: 外向(E) (85%)
- 信息处理: 直觉(N) (72%)
```

### 🔍 行为模式洞察

- 傍晚时段活跃
- 高频互动者（喜欢@他人）
- emoji爱好者（频繁使用表情符号）

## ⚙️ 配置说明

在插件管理界面可以调整以下配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| DEFAULT_ANALYSIS_DAYS | 30 | 默认分析时间范围（天） |
| DEFAULT_MAX_MESSAGES | 500 | 默认最大分析消息数 |
| MIN_MESSAGE_THRESHOLD | 50 | 最小消息样本量阈值 |
| CACHE_EXPIRE_DAYS | 7 | 缓存过期天数 |
| ENABLE_BIG_FIVE | True | 是否启用大五人格分析 |
| ENABLE_MBTI | True | 是否启用MBTI分析 |
| ENABLE_BEHAVIOR_PATTERN | True | 是否启用行为模式识别 |
| ANALYSIS_MODEL_GROUP | default | 用于性格分析的模型组 |
| MAX_ANALYSIS_TOKENS | 4000 | 单次分析的最大Token数 |

## 🔧 技术架构

### 核心模块

1. **数据采集模块**
   - 查询历史消息
   - 文本清洗和脱敏
   - 统计分析

2. **分析引擎模块**
   - 大五人格分析
   - MBTI类型判断
   - 行为模式识别

3. **报告生成模块**
   - Markdown格式化
   - 文本可视化
   - 类型描述

4. **缓存管理模块**
   - 结果缓存
   - 过期管理
   - 手动清除

## 🔒 隐私与安全

- ✅ 仅分析当前聊天频道内的消息
- ✅ 自动脱敏敏感信息（手机号、身份证等）
- ✅ 本地存储，不外传数据
- ✅ 缓存自动过期删除

## ⚠️ 注意事项

1. **样本量要求**：建议至少有50条消息才能获得较准确的分析
2. **分析准确性**：基于AI文本分析，仅供娱乐参考，不构成专业心理评估
3. **性能考虑**：单次分析耗时约10-30秒，建议使用缓存机制
4. **模型要求**：需要配置支持JSON格式输出的LLM模型

## 🐛 故障排除

**问题1：提示"未找到该用户的聊天记录"**

解决方案：
- 确认用户ID正确
- 检查时间范围是否合理
- 确认该用户有足够的聊天记录

**问题2：提示"消息样本量不足"**

解决方案：
- 增加时间范围（如从30天增加到60天）
- 等待用户产生更多聊天记录

**问题3：分析失败**

解决方案：
- 检查模型组配置是否正确
- 确认LLM模型可用
- 查看日志获取详细错误信息

## 📝 更新日志

### v0.1.0 (2025-10-16)

- ✨ 初始版本发布
- ✅ 实现大五人格分析
- ✅ 实现MBTI分析
- ✅ 实现行为模式识别
- ✅ 实现Markdown报告生成
- ✅ 实现缓存管理

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

## 👥 作者

- GitHub: [@A1A7432](https://github.com/1A7432)

## 🙏 致谢

感谢 [Nekro Agent](https://github.com/KroMiose/nekro-agent) 框架提供的强大插件系统支持！

## 📮 联系方式

如有问题或建议，请通过以下方式联系：

- GitHub Issues: [提交Issue](https://github.com/1A7432/nekro-agent-personality-analysis/issues)
- GitHub Discussions: [参与讨论](https://github.com/1A7432/nekro-agent-personality-analysis/discussions)

---

**⚠️ 免责声明**：本插件生成的性格分析报告仅供娱乐参考，不构成专业心理评估或诊断。
