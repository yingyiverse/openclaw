---
name: podcast-tts
description: 使用火山引擎播客TTS API生成双人播客音频。支持将播客脚本文本通过WebSocket流式生成双人播客音频，需要火山引擎API凭证和Python 3.9+环境。
---

# 播客TTS技能

使用火山引擎播客TTS API生成双人播客音频。

## 环境要求

- Python 3.9+（必须）
- `pip install websocket-client`

## 环境变量

```bash
export VOLCENGINE_APP_ID=your_app_id
export VOLCENGINE_ACCESS_KEY=your_access_key
export VOLCENGINE_SECRET_KEY=your_secret_key
```

## 脚本格式

创建JSON文件，每轮包含speaker和text：

```json
[
  { "speaker": "zh_male_xiaolei_v2_saturn_bigtts", "text": "大家好，今天我们聊..." },
  { "speaker": "zh_male_liufei_v2_saturn_bigtts", "text": "对，我也这么觉得..." }
]
```

## 发音人对应

- 虾播: `zh_male_xiaolei_v2_saturn_bigtts`
- 虾讲: `zh_male_liufei_v2_saturn_bigtts`

## 运行

```bash
python3 scripts/podcast_tts.py --input your_script.json --output output.mp3
```

## 注意事项

1. **必须Python 3.9+**
2. 需要在火山引擎控制台开通播客TTS服务
3. 当前API协议较复杂，建议先在控制台测试
