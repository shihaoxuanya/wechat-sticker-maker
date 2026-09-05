# 工具与项目配置

## 运行环境

Python 3.10+，依赖 `Pillow>=10`、`numpy>=1.24`。优先用宿主已有运行时；否则在使用者允许的项目环境创建venv，再 `python -m pip install -r <skill>/scripts/requirements.txt`。不要把作者本机解释器地址写入项目或分享包。脚本路径以安装位置为准。

初始化示例：

```text
python <skill>/scripts/sticker_pipeline.py init --project "我的表情 项目" --reference "参考图.png" --name "小团子" --count 24
```

初始化只复制参考图并生成配置，不生成插画，不声称参考图已授权。脚本支持1至99条配置，这只是工具边界，不是微信支持的投稿数量。

## project.json

- `name/title/intro/copyright_owner`：角色名、专辑名、介绍、使用者确认的权利人。未知署名保持null。
- `reference`、`identity`、`style`、`language`：参考位置、观察到的身份特征、画风和语言。`generator`可补充实际生成工具或已有素材来源；脚本不从文件格式推断生成来源。
- `category`：必须与当前核对的platform-profile类别相同。
- `master_size`：默认1024，可增加；不会把低分辨率来源伪装成高清细节。
- `qa_font`：可选本地字体路径，仅用于总览标签；无可用中文字体时总览使用数字和英文，网页仍显示中文。不把未经授权的字体随分享包打包。
- `targets`：main/thumbnail/cover/banner/chat_icon各自的size、format（PNG/GIF/JPEG）、transparent、margin、max_bytes_goal。目标体积是制作约束，**不是官方规格证据**。PNG优先全色，超目标时选择最高通过的减色候选；JPEG质量不低于60；达不到时失败并要求调整画面/目标，不降像素偷过检查。
- 若已核实的规则需要不透明副本，设置transparent=false并提供明确的opaque_color；工具不擅自补白底。横幅使用已完成的不透明原图；高清透明母图和日常PNG仍保留。
- `stickers`：连续01起的id、name、text（无字用空字符串）、meaning（可选含义词，默认name）、pose、source、background、prompt、variants。用户自选名称直接改这里；count必须同步。
- `assets`：cover/banner/chat_icon分别配置source、background、prompt、variants。图标与封面必须是分别设计的源图，不只是两种尺寸。

源文件名可配置，默认 `sources/01.png` 等；原图最低短边1024（横幅例外，按目标尺寸检查）。原生透明图片的background为 `{"mode":"native"}`。RGB、全不透明RGBA、假棋盘格不得因为扩展名是PNG就跳过背景修复。

纯色底备用例子：

```json
{
  "mode": "chroma",
  "screen_confirmed": true,
  "key_rgb": [0, 240, 240],
  "tolerance": 28,
  "protect_mask": "sources/01-protect.png",
  "remove_mask": "sources/01-remove.png"
}
```

只有实际看过源图才设置screen_confirmed。mask为与源图相同尺寸的灰度PNG，白色代表保留或去除；可省略未使用的mask，二者不得重叠。底色必须与目标图适配，不固定使用青色。封闭底色孔洞默认保留并提示看图，可用明确移除蒙版处理。源图触边会写入来源记录，结合framing检查区分有意半身构图与意外裁断。

## 生成、查看、复核

完成imagegen生成并填写真实prompt后：

```text
python <skill>/scripts/sticker_pipeline.py build --project "我的表情 项目"
python <skill>/scripts/sticker_pipeline.py review-template --project "我的表情 项目"
python <skill>/scripts/sticker_pipeline.py check --project "我的表情 项目"
python <skill>/scripts/sticker_pipeline.py package --project "我的表情 项目"
```

build输出highres、png、中文名称版、thumbnails、assets，单独将适合上传的副本放在submission；尺寸和体积优化只作用于相应副本。某张失败会记录具体原因，完整性状态为失败。以前由工具管理且已过时的派生文件和ZIP移动到项目history，既不递归删除源图，也不让旧成功包继续冒充新结果。

`review-template`只创建/保留与当前哈希对应的视觉待办，不做自动批准。查看 `qa/overview-*.png`、`qa/chat-icon-check.png`、`preview.html`，需要时打开单张母图。给 `visual-review.json` 每个submission文件写实际reviewer、reviewed_at；每项checks写passed/failed及具体note。不能只写一个总passed或无事实的“已通过”。图标内容检查必须看实际图。

`compliance-review.json`记录内容、权利与肖像、字体/素材许可、版权署名、AI政策、类别资质、文案字段的复核，每项有具体evidence。不适用的授权项可在确认原因后记passed并说明不适用依据。复核配置与成图对应时，将config_fingerprint和content_fingerprint更新为当前值（脚本的同名函数可读取）；不要仅更新哈希而跳过实质复核。内容修改会让旧合规确认失效。

平台证据按 [规范文档](platform.md) 填写。verified的max_bytes可填正整数硬上限；官方完整页面确实未规定硬上限时可用字符串`not_specified`并提供对应页面核对证据，不能用它绕过未知规则。文本字段限制对象可包含title、intro、copyright_owner、meaning。

## 检查状态与交付

check退出码：0是本地检查通过，2是已发现错误，3是尚待规则/视觉/合规核实。report.json保留每个issue而非只有汇总状态；像素机检不会填“无文字/无装饰/不侵权”。压缩阈值以warning单独报告，不当成拒收上限。

package先重新check。已发现错误时拒绝打包；仅缺复核时可生成清楚标为“草稿”的包。每个ZIP重新读回做CRC检查并记录SHA256；上传清单与包内文件一一对应。完整包含母图和预览、来源及提示记录，但不包含私人原始参考图；原图仍保留在项目sources中以便继续编辑。

这些工具不会自动生成图像、浏览官方页面、证明版权或代替人看图。宿主agent负责上述步骤，并如实填入它实际观察到的结果。没有imagegen或无法核实规则时仍可整理已有素材和准确列出缺项。
