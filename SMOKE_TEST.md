# Smoke Test

本文件用于验证项目是否能按目标运行。

## 1. Without API Key

这些命令不需要 NVIDIA API key：

```bash
python -m agent3gpp fetch-spec --spec 38.331
python -m agent3gpp parse
python -m agent3gpp search RRCSetup --limit 3
```

预期：

- `data/incoming/` 出现官方 ZIP。
- `data/processed/` 出现转换文本。
- `data/index/metadata.csv` 和 `data/index/research.db` 被生成。
- search 返回包含 official_url 的证据片段。

## 2. With API Key

先设置：

```bash
set NVIDIA_API_KEY=your-key
```

或使用本地 `.env`。

运行：

```bash
python -m agent3gpp "请分析 RRCSetup 在 RRC re-establishment fallback 场景中的作用"
```

或显式使用 `research` 子命令：

```bash
python -m agent3gpp plan "请分析 RRCSetup 在 RRC re-establishment fallback 场景中的作用"
python -m agent3gpp research "请分析 RRCSetup 在 RRC re-establishment fallback 场景中的作用" --spec 38.331
```

预期：

- 自动下载 / 解析 / 建库。
- 调用 NVIDIA NIM。
- 输出中文报告。
- 使用 `--save` 时写入 `runs/`。
