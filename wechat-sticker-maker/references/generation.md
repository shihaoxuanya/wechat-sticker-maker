# 单图生成与质量修正

## 从参考图建立身份

记录可观察的脸型、眼睛、眉毛、嘴鼻、发型/毛色、服装与重要配饰、轮廓和材质。人物、宠物、卡通角色均可；不要把某位用户的角色名、帽子或眼镜写成通用要求。区分角色自带图案和后加特效。参考图不是版权授权证明，第三方水印也不能以“抠干净”为由消除来源问题。

默认24个选题池：亲亲、抱抱、贴贴、想你、爱你、生气、开心、害羞、委屈、哭哭、无语、震惊、拜托、摸摸、收到、早安、晚安、困困、谢谢、加油、偷笑、疑惑、吃饭、拜拜。用户已有选题优先；不足时补齐、超出时保留用户数量并核实平台允许数量。

## 内置 imagegen 调用

每款单独调用内置图像生成工具，参考同一张身份图及已选定样片。参考多个图时明确“身份”“风格”“文字笔触”的角色。编辑本地原图前先查看它。按工具要求返回生成图片，将选用原图复制到当前项目；不硬编码工具缓存目录。内置工具不可用时说明需要图像生成能力；未经用户选择不切换到收费API/CLI。

提示模板（用实际项目内容替换花括号，不直接提交花括号）：

```text
Use case: illustration-story.
Asset: one square static chat sticker, independently usable at small size.
Reference roles: image 1 defines the exact character identity.
Identity: {observed_identity}. Preserve these visible distinguishing features.
Expression and pose: {emotion_and_specific_pose}; distinguish from {similar_emotion}.
Framing: {close_face_or_necessary_full_body}. Large readable face and essential hands;
use most of the frame, with complete ears/hair/fingers/text inside safe margins.
Style: {reference_style}; consistent contours, palette, glasses/accessories if present.
Text verbatim: "{exact_text}". {language_and_handwriting_or_no_text}.
Keep lettering readable on light and dark chat backgrounds without covering the face.
Background: genuinely transparent alpha, no painted checkerboard, white rectangle,
or artificial transparency pattern. No watermark or unexpected text/extra characters.
Render a high-resolution source with at least 1024 pixels on each side.
```

单一参考角色默认不添加第二人；“抱抱”等可朝观看者伸手，用户明确需要双人互动时不强加单人限制。先选三张具有不同脸部/手势复杂度的图做内部样片检查；只有身份或风格存在高影响歧义才请求用户选择。

## 中文文字可靠性

- 把最终文案作为准确的Unicode字符串保存在项目配置中，逐字检查简繁体、标点和语气词；相似字形、AI生成字形和OCR结果都不能替代原字符串。
- 默认让 imagegen 生成角色和预留排字空间，中文用已确认可用的本地标准字体确定性渲染。需要手写感时选择楷体、圆体等合法字体并调整字号、角度、描边和排版，不把字形本身改造成难辨认的装饰。
- 若成图已经包含生成式手写字，必须同时在高清图、投稿尺寸和缩略图下逐字看图。任何一字无法确认时，只重绘文字区域并保留角色画面；不要以删除用户要求的文字作为默认修正。
- 记录最终文本、Unicode码点、字体路径或字体来源、许可状态和修改区域。只输出栅格字形，不把未经授权的字体文件放入分享包。
- 平台以“错别字或异形字”驳回时，优先换成标准字形而非再次让 imagegen 猜字；修复后更新名称表、提示词、来源、修订记录、预览、检查报告和压缩包。

## 独立配套素材

- 聊天图标：正面头部、紧凑单一轮廓，压简发丝细节，五官在50px仍易辨认。无文字、外置星星/心形/光点、手、身体、外圈白色描边、底板或方框。角色白毛/白帽本身不等于白描边；不得一律删白。已有专辑应使用不同图标。
- 封面：单独创作简洁、有辨识度的代表姿势，默认正面半身；透明、无额外文字，最终依当前封面规则核对。
- 横幅：独立横向设计，不把正方图拉伸成750×400。默认不透明、无字、与微信底色有区分，角色与专辑一致；采用带颜色的明亮背景而非接近纯白。比例不同用合理裁切或重新生成，不压扁角色。

## 真透明与色彩

先要求原生alpha。出现实心棋盘格必须重新生成/编辑背景，不能把灰白格当透明。纯色底仅在实际输出失败后作为确定性提取的备选；选择与角色/道具不冲突的颜色，明确这只是制作中间态。

工具的 chroma 模式只移除与外部相连的底色，并处理邻近边缘；不会猜测封闭的相同颜色区域是眼睛还是背景。角色本身有底色时提供保护蒙版（白色保留），封闭孔洞确认为背景时可用移除蒙版。两种蒙版冲突须纠正。不能借全局删除青色来“通过检查”。颜色冲突、细发丝、透明纱等复杂边缘优先让 imagegen 修复真实alpha；无法可靠修复则报告具体问题。

高清母图始终保留全色，压缩只影响投稿副本。PNG先尝试无损优化，必要时有界减色；JPEG在规定体积内选择最高通过质量。减色结果要复看眼睛、渐变、文字和透明边缘。若平台要求GIF，导出单帧静态GIF且保留高清PNG；不要用伪动画冒充动态专辑。

## 单张修正与重试

围绕一个明确缺陷编辑，提示中锁定其它视觉特征。记录原因、旧变体、新变体和最终来源；同一缺陷连续两次修正仍不改善时换构图或更适合的修复方法，三次仍未解决就展示问题并列为待处理，不无限消耗生成次数。更新配置的source后重建；恢复草稿和续做时先检查现有来源，不从头生成已合格图片。
