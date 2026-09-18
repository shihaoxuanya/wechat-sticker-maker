# 一张图做微信表情包

`wechat-sticker-maker` 是一个 Codex Skill：给它一张人物、宠物或角色参考图，它会协助生成一整套微信静态表情，并整理封面、横幅、聊天图标、预览、检查报告和上传清单。

## 它能做什么

- 默认制作 24 款静态表情，也支持自定义数量、名称、画风和文字。
- 从单张参考图提取角色特征，尽量保持整套形象一致。
- 生成透明高清母图、主图、缩略图、中文名称版和配套素材。
- 检查尺寸、体积、透明通道、编号、缺失文件和 ZIP 完整性。
- 根据微信表情开放平台的驳回截图定位问题并修正相关素材。
- 单独检查聊天页图标，避免文字、装饰、白边和主体过小等常见问题。

## 安装

### 下载 ZIP

下载 [`dist/wechat-sticker-maker.zip`](dist/wechat-sticker-maker.zip)，解压后把整个 `wechat-sticker-maker` 文件夹放入 Codex 的 skills 目录：

- Windows：`%USERPROFILE%\.codex\skills\`
- macOS / Linux：`~/.codex/skills/`
- 自定义 `CODEX_HOME`：放入其中的 `skills` 目录

最终应存在：

```text
skills/wechat-sticker-maker/SKILL.md
```

也可以直接复制仓库中的 [`wechat-sticker-maker`](wechat-sticker-maker) 文件夹。完整说明见 [安装与使用.md](安装与使用.md)。

## 使用示例

上传一张参考图，在 Codex 中输入：

```text
请使用 $wechat-sticker-maker，根据这张图做24款微信静态表情。
保持角色一致，突出头脸，适合的图片配自然手写字。
同时制作封面、横幅和独立聊天图标，检查素材并给我上传清单。
```

检查已有素材：

```text
请使用 $wechat-sticker-maker 检查这个表情包目录，先告诉我哪些文件不符合当前投稿要求。
```

处理驳回：

```text
这是平台驳回截图，请使用 $wechat-sticker-maker 修正涉及的图片，更新预览和压缩包，并指出需要重新上传哪些文件。
```

## 处理工具

配套脚本需要 Python 3.10+、Pillow 和 NumPy：

```bash
python -m pip install -r wechat-sticker-maker/scripts/requirements.txt
python wechat-sticker-maker/scripts/sticker_pipeline.py init --project <项目目录> --reference <参考图> --name <角色名> --count 24
python wechat-sticker-maker/scripts/sticker_pipeline.py build --project <项目目录>
python wechat-sticker-maker/scripts/sticker_pipeline.py review-template --project <项目目录>
python wechat-sticker-maker/scripts/sticker_pipeline.py check --project <项目目录>
python wechat-sticker-maker/scripts/sticker_pipeline.py package --project <项目目录>
```

这些脚本负责确定性的排版、尺寸导出、检查和打包，不调用收费图像 API。插画生成需要 Codex 环境提供图像生成能力。

## 投稿与合规说明

仓库内的尺寸和体积配置是制作基线，不代表微信当前规则已经永久不变。准备投稿时，Skill 会优先核对微信表情开放平台的官方说明、当前表单提示或使用者提供的官方截图；无法核实时会把项目标记为“待核实”，不会宣称已经通过平台审核。

使用者需要确认参考图、人物肖像、字体、角色设计和其他素材的权利，并按照平台当期要求填写 AI 素材相关信息。该 Skill 能减少常见制作和上传错误，但不能承诺审核必过。

## 隐私

生成项目默认保存在使用者指定的本地目录中。

## 测试

```bash
python -m unittest discover -s wechat-sticker-maker/tests -v
```

当前版本包含 21 个行为测试，覆盖中文及含空格路径、透明图片、尺寸与体积错误、编号错配、损坏文件、假透明、文字审核状态和 ZIP 完整性等情况。

## 许可证

[MIT License](LICENSE)
## 贡献者
感谢 [rosyrongrong](https://github.com/rosyrongrong) 参与项目共创。
