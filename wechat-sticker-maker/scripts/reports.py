"""Offline galleries, contact sheets and an asset-to-field upload map."""
import html
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from image_ops import resize_rgba, png_bytes


def font_path(project):
    if project.get('qa_font'):
        path=Path(project['qa_font'])
        if not path.is_file():raise ValueError('Configured QA font not found')
        return path
    candidates=[Path('C:/Windows/Fonts/msyh.ttc'),Path('/System/Library/Fonts/PingFang.ttc'),Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    return next((p for p in candidates if p.is_file()),None)


def checker(size,cell=12):
    image=Image.new('RGBA',size,'#fafafa');draw=ImageDraw.Draw(image)
    for y in range(0,size[1],cell):
        for x in range(0,size[0],cell):
            if (x//cell+y//cell)%2:draw.rectangle((x,y,x+cell-1,y+cell-1),fill='#e1e3e6')
    return image


def save(im,path):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(png_bytes(im))


def make_previews(root,p,m):
    fontfile=font_path(p)
    font=lambda n: ImageFont.truetype(str(fontfile),n) if fontfile else ImageFont.load_default(size=n)
    lookup={f['id']:f for f in m['files'] if f['role']=='main' and f['kind']=='submission'}
    cols=min(6,p['count']);rows=math.ceil(p['count']/cols)
    for size,bg in [(240,'light'),(240,'dark'),(240,'checker'),(120,'light'),(120,'dark')]:
        gap,label_h,top=16,32,70
        sheet=Image.new('RGBA',(cols*(size+gap)+gap,rows*(size+label_h+gap)+top),'#26282e' if bg=='dark' else '#f7f4f0')
        d=ImageDraw.Draw(sheet);color='#eddfd4' if bg=='dark' else '#584338'
        title=f"{p['name']} · {p['count']}款 · {size}px" if fontfile else f"{p['count']} stickers / {size}px / {bg}"
        d.text((gap,18),title,font=font(24),fill=color)
        for i,s in enumerate(p['stickers']):
            x=gap+(i%cols)*(size+gap);y=top+(i//cols)*(size+label_h+gap)
            tile=checker((size,size)) if bg=='checker' else Image.new('RGBA',(size,size),'#26282e' if bg=='dark' else '#fff')
            if s['id'] in lookup:
                with Image.open(root/lookup[s['id']]['path']) as im:
                    factor=min(size/im.width,size/im.height)
                    art=resize_rgba(im.convert('RGBA'),(max(1,round(im.width*factor)),max(1,round(im.height*factor))))
                    tile.alpha_composite(art,((size-art.width)//2,(size-art.height)//2))
            else:ImageDraw.Draw(tile).text((12,12),'MISSING',font=font(18),fill='#be3131')
            sheet.alpha_composite(tile,(x,y));label=f"{s['id']} {s['name']}" if fontfile else s['id']
            d.text((x,y+size+3),label,font=font(16 if size==240 else 12),fill=color)
        save(sheet.convert('RGB'),root/'qa'/f'overview-{bg}-{size}.png')
    icon=next((f for f in m['files'] if f['role']=='chat_icon' and f['kind']=='submission'),None)
    if icon:
        with Image.open(root/icon['path']) as im:art=im.convert('RGBA')
        sheet=Image.new('RGB',(900,430),'#f7f4f0');d=ImageDraw.Draw(sheet)
        title='聊天图标：上方原尺寸，下方放大检查（不是上传文件）' if fontfile else 'Chat icon: actual size above; magnified review below (not upload asset)'
        d.text((18,12),title,font=font(20),fill='#584338')
        for i,bg in enumerate(('#fff','#26282e','#ededed')):
            tile=Image.new('RGBA',art.size,bg);tile.alpha_composite(art)
            sheet.paste(tile.convert('RGB'),(20+i*295,65))
            large=tile.resize((250,250),Image.Resampling.NEAREST)
            sheet.paste(large.convert('RGB'),(20+i*295,150))
        save(sheet,root/'qa'/'chat-icon-check.png')
    cards=[]
    for s in p['stickers']:
        src=html.escape(lookup.get(s['id'],{}).get('path',''),quote=True)
        name=html.escape(s['name']);sid=s['id']
        cards.append(f'<article><a class="tile" href="highres/{sid}.png" target="_blank"><img src="{src}" alt="{name}"></a><div>{sid} · {name}<a href="{src}" download>下载</a></div></article>')
    doc=(SKIN.replace('TITLE',html.escape(p['name'])).replace('COUNT',str(p['count'])).replace('CARDS',''.join(cards)))
    (root/'preview.html').write_text(doc,encoding='utf-8')


SKIN='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TITLE · 表情预览</title><style>
*{box-sizing:border-box}body{margin:0;background:#f7f4ef;color:#583e32;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1200px;margin:auto;padding:24px}h1{font-size:30px}.controls{display:flex;gap:10px;flex-wrap:wrap;position:sticky;top:0;padding:14px 0;background:#f7f4eff2}button,.controls a{background:white;color:#583e32;border:1px solid #dbcabc;border-radius:30px;padding:8px 14px;font:inherit;text-decoration:none;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(252px,1fr));gap:16px}article{background:white;border-radius:16px;overflow:hidden;border:1px solid #eadfd6}.tile{height:260px;display:flex;align-items:center;justify-content:center;background:var(--tile,#fff)}img{width:var(--size,240px);height:var(--size,240px);object-fit:contain}article>div{padding:10px 16px;display:flex;justify-content:space-between}a{color:#a45440}.dark{--tile:#25282e}.checker{--tile:repeating-conic-gradient(#e1e3e6 0% 25%,#fff 0% 50%) 50% / 20px 20px}@media(max-width:560px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.tile{height:180px}img{max-width:100%;max-height:170px}article>div{display:block;font-size:13px}}
</style><main><h1>TITLE · COUNT款表情</h1><p>点击图片查看高清母图。切换背景和显示大小，看看聊天时的效果。</p><nav class="controls"><button onclick="mode('')">浅色</button><button onclick="mode('dark')">深色</button><button onclick="mode('checker')">透明检查</button><button onclick="size(120)">120px</button><button onclick="size(240)">240px</button><a href="upload-guide.md">上传清单与检查结果</a><a href="qa/chat-icon-check.png" target="_blank">聊天图标</a></nav><section class="grid">CARDS</section></main><script>function mode(m){document.body.className=m}function size(n){document.documentElement.style.setProperty('--size',n+'px')}</script></html>'''


def upload_guide(root,p,report):
    from sticker_pipeline import read
    m=read(root/'manifest.json') if (root/'manifest.json').exists() else {'files':[]}
    submitted=[f for f in m['files'] if f['kind']=='submission']
    statuses={'passed':'已完成本地投稿前检查（不代表官方审核通过）','failed':'存在已发现的错误，请修正后再上传','pending_rules':'草稿：当前平台规则尚未核实完整','pending_visual':'草稿：尚有成品未完成视觉检查','pending_compliance':'草稿：内容或权利信息尚未确认'}
    lines=['# 上传清单', '', statuses[report['status']], '', '## 文案字段', '', '| 页面字段 | 内容 |','| --- | --- |',
           f"| 专辑名称 | {p['title'].replace('|','／')} |",f"| 介绍 | {(p.get('intro') or '待撰写').replace('|','／')} |",f"| 版权 | {(p.get('copyright_owner') or '待使用者确认实际权利人；不要自动使用角色名').replace('|','／')} |",'',
           '介绍和名称等限制以当前表单为准；上传时检查页面字符计数。AI素材声明按实际平台要求填写，来源说明见 source-info.json。', '',
           '## 选择对应文件', '', '| 上传位置 | 文件 | 制作规格 |','| --- | --- |']
    labels={'main':'主图','thumbnail':'缩略图','cover':'封面','banner':'横幅','chat_icon':'聊天页图标'}
    for role in ('main','thumbnail','cover','banner','chat_icon'):
        fs=[f for f in submitted if f['role']==role];t=p['targets'][role]
        paths='、'.join(f"`{f['path']}`" for f in fs) if len(fs)<=1 else f"`{fs[0]['path']}` 至 `{fs[-1]['path']}`（{len(fs)}张）"
        lines.append(f"| {labels[role]} | {paths or '缺失'} | {t['size'][0]}×{t['size'][1]} {t['format']} |")
    lines += ['', '**图标一定选择独立的聊天页图标文件**，不要上传封面、带字主图、母图或放大检查图。','',
              '## 上传步骤', '', '1. 解压素材包后进入对应投稿类别；先核对当前页面规则与本包检查报告。ZIP通常是交付容器，不默认可以直接上传。',
              '2. 按01开始的顺序选择主图和对应缩略图，核对数量、编号和含义词；含义词见 names.csv。',
              '3. 分别选择横幅、封面和独立聊天图标，填入已确认文案和真实权利人。',
              '4. 检查平台最新预览中的顺序、文字、透明底、裁切及实际小图标；平台若压缩图片，再看显示质量。',
              '5. 使用者自行确认相关声明并提交。保存草稿、提交成功和审核通过是不同状态，以平台显示结果为准。','',
              '## 尚需处理', '']
    blocking=[x for x in report['issues'] if x['status']!='warning']
    if not blocking:lines.append('本地检查没有待办；提交后仍以平台审核结果为准。')
    else:
        for status in ('failed','pending_rules','pending_visual','pending_compliance'):
            group=[x for x in blocking if x['status']==status]
            if group:lines.append(f"- {status}：{len(group)}项，详见 `qa/report.json` 中的具体文件、原因和状态。")
    lines += ['', '驳回后保存平台原文，定位对应素材，修正后重新生成预览、检查报告与ZIP；不要只替换旧包里的一张图而保留旧检查结论。', '']
    (root/'upload-guide.md').write_text('\n'.join(lines),encoding='utf-8')
