# 孔明审片 · Kongming Video Review

中文实拍短视频的编导返修助手 · A director's review skill for Chinese short-form videos.

给短视频编导、剪辑和运营团队使用。根据视频画面与带时间点的口播，给出一份可直接复制的中文修改意见，1000字以内，有几条说几条。

内部检查开头吸引力与精彩片段前置、剪辑方式、广告与平台风险、下次拍摄。根据素材写真正值得修改的部分，不强凑四栏。

值得换开头时，可把推荐的具体区间导出为可播放候选，供编导核对。已有开头成立就保留。当前版本1.1.0。

## 安装和使用

已使用支持 Skills CLI 的环境时，可从公开仓库安装：

```bash
npx skills add chunyoukong-beep/kongming-review
```

也可以在仓库的 Releases 下载 Skill ZIP。

压缩包中 `kongming-review` 是完整 Skill 文件夹。放入支持 Agent Skills 的宿主的技能目录，或请该宿主安装这个文件夹。例如 Codex 可放入 `~/.codex/skills/kongming-review`，重新打开会话后使用。

对 AI 说：

> 使用 $kongming-review 审这条视频，1000字以内，有几条说几条。重点意见给出原片时间点。

提供可访问的视频文件。支持 Agent Skills 格式不代表每个宿主都能读取本机视频；完整视频审片需要图像理解及本地取材/音频能力。仅有文字时只能给相应的文案意见。

本地取材需要 Python 3.10+、FFmpeg 或 imageio-ffmpeg、Pillow。语音转写可用已有字幕，或 pywhispercpp 配合自己下载的本地 Whisper 模型。详细步骤在 [本地工具说明](kongming-review/references/local-tools.md)。不随包分发视频、模型和 FFmpeg 二进制。

## 先体验工具链

进入 `kongming-review` 文件夹，在独立 Python 环境中执行：

```bash
python -m pip install -r requirements.txt
python scripts/doctor.py
python scripts/demo.py --out demo-output
```

打开 `demo-output/source.mp4` 与 `demo-output/opening-candidate.mp4`，可核对原片3至6秒如何被导出。图卡上持续标注 SYNTHETIC DEMO；无原声，配套字幕是示例文字。

这一步验证安装、抽帧、字幕导入和片段导出，不调用云端AI，不代表真实客户案例、AI审片质量或播放效果。真实审片请提供已获授权的素材，由宿主按 Skill 生成意见。

公开仓库附有 [演示原片](examples/demo-source.mp4) 与 [三秒候选](examples/opening-candidate.mp4)，均由上述脚本生成。

## 能力与费用

Skill 是供 AI 宿主调用的审片说明与工具，沿用孔明传媒桌面审片台的编导标准；桌面窗口、播放器和一键按钮由桌面程序提供。Skill 通过宿主交互，生成一份连续报告。

抽帧包括开头密集取样、全片场景变化信号和间隔抽样。它不代表每一帧都做了语义审核，也不代表所有画面文字都被检查。脚本会如实标明转写来源与覆盖限制，AI应以实际看到、听到的素材判断。

本地取材脚本不联网、不上传视频、不读取账号密钥。AI 宿主可能把提交的画面、文字及音频发到其云端处理，并使用其账户额度或付费接口。费用由所选宿主和处理量决定。该项目不包含云算力、付费平台会员和收费系统。

广告与平台风险为辅助审查，提供原句、位置、判断依据和改法；规则按适用范围核实。不保证爆款、法律结论或平台审核通过。

## 发布范围

当前为公开分享版，发布目录包含 Skill、本地工具、说明、测试及明确标注的合成演示。原桌面 App、私有素材、审片历史、账号信息和模型文件保持在使用者自己的环境。

## 验证

在安装了基础依赖的 Python 环境中运行 `python -m unittest discover -s tests -v`。测试使用临时生成的视频，不需要客户素材。语音转写另需本地模型。

已在 macOS Apple Silicon、Python 3.12 的独立环境验证16项测试。其他操作系统尚未实测。
