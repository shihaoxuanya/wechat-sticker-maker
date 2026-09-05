#!/usr/bin/env python3
"""Portable finishing/checking CLI. Generation is performed by the host's imagegen tool."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageOps

from image_ops import alpha_cutout, encode, fit_transparent, metrics, resize_rgba

SKILL = Path(__file__).resolve().parents[1]
ROLES = ('main','thumbnail','cover','banner','chat_icon')
DEFAULT_NAMES = '亲亲 抱抱 贴贴 想你 爱你 生气 开心 害羞 委屈 哭哭 无语 震惊 拜托 摸摸 收到 早安 晚安 困困 谢谢 加油 偷笑 疑惑 吃饭 拜拜'.split()
TARGETS = {
    'main': {'size':[240,240],'format':'PNG','transparent':True,'margin':3,'max_bytes_goal':512000},
    'thumbnail': {'size':[120,120],'format':'PNG','transparent':True,'margin':2,'max_bytes_goal':51200},
    'cover': {'size':[240,240],'format':'PNG','transparent':True,'margin':3,'max_bytes_goal':512000},
    'banner': {'size':[750,400],'format':'PNG','transparent':False,'margin':0,'max_bytes_goal':512000},
    'chat_icon': {'size':[50,50],'format':'PNG','transparent':True,'margin':1,'max_bytes_goal':102400},
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_name(value):
    out=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(value)).strip(' .')
    return out[:70] or '表情'


def under(root, relative):
    path=(root/relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f'Output must stay inside project: {relative}')
    return path


def load_project(root):
    p=read(root/'project.json')
    if p.get('schema_version')!=1:raise ValueError('Unsupported project schema')
    items=p.get('stickers',[]);count=p.get('count')
    if not isinstance(count,int) or count<1 or count>99 or len(items)!=count:
        raise ValueError('count must match 1..99 ordered sticker entries; this is a tool bound, not a platform allowance')
    if [s.get('id') for s in items] != [f'{i:02}' for i in range(1,count+1)]:
        raise ValueError('Sticker ids must be unique, ordered and contiguous from 01')
    if int(p.get('master_size',0))<1024:raise ValueError('master_size must be at least 1024')
    for role in ROLES:
        t=p['targets'][role]
        if len(t['size'])!=2 or any(not isinstance(v,int) or v<1 for v in t['size']):raise ValueError('Invalid target size')
        if t['format'] not in ('PNG','GIF','JPEG'):raise ValueError('Format must be PNG/GIF/JPEG')
        if t['transparent'] and t['format']=='JPEG':raise ValueError('JPEG cannot preserve transparency')
    return p


def init(root, reference, name, count):
    if (root/'project.json').exists():raise ValueError('Existing project: edit its config instead of reinitializing')
    if not reference.is_file():raise ValueError('Reference file not found')
    with Image.open(reference) as im:im.verify()
    if not 1<=count<=99:raise ValueError('Supported tool count is 1..99; platform allowance must be verified')
    root.mkdir(parents=True,exist_ok=True)
    for folder in ('sources','references','qa','submission','highres','png','thumbnails','中文名称版','assets'):(root/folder).mkdir(exist_ok=True)
    ref_name='reference'+reference.suffix.lower()
    shutil.copy2(reference,root/'references'/ref_name)
    items=[]
    for i in range(count):
        n=DEFAULT_NAMES[i] if i<len(DEFAULT_NAMES) else f'自选{i+1}'
        items.append({'id':f'{i+1:02}','name':n,'text':n,'pose':'','source':f'sources/{i+1:02}.png','background':{'mode':'native'},'prompt':'','variants':[]})
    p={'schema_version':1,'name':name,'title':f'{name}的日常','intro':'','copyright_owner':None,
       'reference':f'references/{ref_name}','category':'static_album','count':count,'language':'zh-CN',
       'identity':{},'style':'preserve reference','master_size':1024,'qa_font':None,'targets':TARGETS,'stickers':items,
       'assets':{r:{'source':f'sources/{r}.png','background':{'mode':'native'},'prompt':''} for r in ('cover','banner','chat_icon')}}
    write(root/'project.json',p)
    shutil.copy2(SKILL/'references'/'platform-baseline.json',root/'platform-profile.json')
    write(root/'revisions.json',[])
    return {'project':str(root),'count':count,'next':'Fill identity/poses/prompts; generate sources with imagegen; verify platform profile; build.'}


def extension(fmt):return {'PNG':'.png','GIF':'.gif','JPEG':'.jpg'}[fmt]


def submission_image(image,target):
    if target['transparent']:return image.convert('RGBA')
    if image.mode=='RGB' or image.convert('RGBA').getchannel('A').getextrema()[0]==255:return image.convert('RGB')
    if not target.get('opaque_color'):raise ValueError('An opaque target needs an explicit opaque_color; do not invent a white background')
    background=Image.new('RGBA',image.size,target['opaque_color']);background.alpha_composite(image.convert('RGBA'))
    return background.convert('RGB')


def fingerprint(root):
    return hashlib.sha256((sha(root/'project.json')+sha(root/'platform-profile.json')).encode()).hexdigest()


def content_fingerprint(root):
    m=read(root/'manifest.json')
    values=[f"{f['path']}:{sha(root/f['path'])}" for f in m['files'] if f['kind']=='submission' and (root/f['path']).is_file()]
    return hashlib.sha256('\n'.join(sorted(values)).encode()).hexdigest()


def build(root):
    p=load_project(root)
    old=read(root/'manifest.json') if (root/'manifest.json').exists() else {'files':[]}
    run=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    # Move only known old packages to a verified project-local history folder.
    package_dir=root/'packages'
    if package_dir.exists():
        for f in package_dir.glob('*.zip'):
            target=under(root,f'history/{run}/{f.name}');target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(f),str(target))
    write(root/'build-state.json',{'complete':False,'started_at':run})
    files=[];errors=[];source_records=[]

    def emit(image, rel, role, kind, size, transparent, fmt='PNG', budget=None, sid=None):
        path=under(root,rel);result=encode(image,path,fmt,budget)
        files.append({'path':rel,'role':role,'kind':kind,'id':sid,'expected_size':list(size),'expected_format':fmt,
                      'expected_transparent':transparent,'sha256':sha(path),**result})

    def source_art(s, role, sid=None):
        path=(root/s['source']).resolve()
        with Image.open(path) as raw:
            raw=ImageOps.exif_transpose(raw);raw.load()
            if role=='banner':
                rgba=raw.convert('RGBA')
                if rgba.getchannel('A').getextrema()[0]<255:
                    raise ValueError('banner has transparent pixels; generate or explicitly compose a finished opaque banner')
                return raw.convert('RGB'),{}
            if min(raw.size)<1024:
                raise ValueError('source_resolution: source must have at least 1024px on each side; regenerate instead of claiming upscaled detail')
            art,info=alpha_cutout(raw,s.get('background',{}),root)
            bbox=art.getchannel('A').getbbox()
            info.update(source_size=list(raw.size),source_bbox=list(bbox),source_edge_touch=bool(bbox[0]==0 or bbox[1]==0 or bbox[2]==raw.width or bbox[3]==raw.height))
        source_records.append({'id':sid,'role':role,'source':s['source'],'sha256':sha(path),'prompt':s.get('prompt',''),'variants':s.get('variants',[]),**info})
        return art,info

    for s in p['stickers']:
        sid=s['id']
        try:
            art,info=source_art(s,'main',sid)
            master=fit_transparent(art,[p['master_size']]*2,max(8,round(p['master_size']*.015)))
            emit(master,f'highres/{sid}.png','main','master',master.size,True,sid=sid)
            t=p['targets']['main'];main=fit_transparent(art,t['size'],t['margin'])
            emit(main,f'png/{sid}.png','main','daily',main.size,True,sid=sid)
            emit(main,f"中文名称版/{sid}-{safe_name(s['name'])}.png",'main','localized',main.size,True,sid=sid)
            emit(submission_image(main,t),f"submission/main/{sid}{extension(t['format'])}",'main','submission',main.size,t['transparent'],t['format'],t.get('max_bytes_goal'),sid)
            t=p['targets']['thumbnail'];thumb=fit_transparent(art,t['size'],t['margin'])
            emit(thumb,f'thumbnails/{sid}.png','thumbnail','daily',thumb.size,True,sid=sid)
            emit(submission_image(thumb,t),f"submission/thumbnails/{sid}{extension(t['format'])}",'thumbnail','submission',thumb.size,t['transparent'],t['format'],t.get('max_bytes_goal'),sid)
        except (OSError,ValueError,KeyError) as e:errors.append({'asset':sid,'error':str(e)})
    for role in ('cover','banner','chat_icon'):
        try:
            s=p['assets'][role];art,info=source_art(s,role);t=p['targets'][role]
            stem=role.replace('_','-')
            if role=='banner':
                ratio=art.width/art.height;target_ratio=t['size'][0]/t['size'][1]
                if abs(ratio/target_ratio-1)>.02:
                    raise ValueError('banner_aspect: source differs from target ratio by >2%; recompose instead of stretching/cropping blindly')
                master=art
                rendered=ImageOps.fit(art,tuple(t['size']),method=Image.Resampling.LANCZOS)
                source_records.append({'id':None,'role':role,'source':s['source'],'sha256':sha(root/s['source']),'prompt':s.get('prompt',''),'variants':s.get('variants',[]),'source_size':list(art.size)})
            else:
                master=fit_transparent(art,[p['master_size']]*2,20)
                rendered=fit_transparent(art,t['size'],t['margin'])
            emit(master,f'assets/{stem}-master.png',role,'master',master.size,role!='banner')
            emit(rendered,f'assets/{stem}.png',role,'daily',rendered.size,role!='banner')
            emit(submission_image(rendered,t),f"submission/assets/{stem}{extension(t['format'])}",role,'submission',rendered.size,t['transparent'],t['format'],t.get('max_bytes_goal'))
        except (OSError,ValueError,KeyError) as e:errors.append({'asset':role,'error':str(e)})
    current={f['path'] for f in files}
    # Archive obsolete managed derivatives, never unrelated files or input sources.
    for item in old.get('files',[]):
        if item['path'] not in current:
            oldpath=under(root,item['path'])
            if oldpath.is_file():
                dst=under(root,f"history/{run}/{item['path']}");dst.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(oldpath),str(dst))
    manifest={'schema_version':1,'built_at':run,'config_fingerprint':fingerprint(root),'complete':not errors,'files':files,'sources':source_records,'build_errors':errors}
    write(root/'manifest.json',manifest);write(root/'build-state.json',{'complete':not errors,'built_at':run})
    write(root/'prompts.json',{'character':p['identity'],'style':p['style'],'items':[{'id':s['id'],'name':s['name'],'text':s['text'],'pose':s['pose'],'prompt':s.get('prompt',''),'variants':s.get('variants',[])} for s in p['stickers']],'assets':{r:{'prompt':a.get('prompt',''),'variants':a.get('variants',[])} for r,a in p['assets'].items()}})
    write(root/'source-info.json',{'generator':p.get('generator','not declared; fill actual tool/source, do not infer provenance from file format'),'sources':source_records,'copyright_owner':p.get('copyright_owner'),'rights_assumed':False})
    with (root/'names.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['编号','名称','画面文字','含义词','主图','缩略图'])
        for s in p['stickers']:writer.writerow([s['id'],s['name'],s['text'],s.get('meaning',s['name']),f"submission/main/{s['id']}{extension(p['targets']['main']['format'])}",f"submission/thumbnails/{s['id']}{extension(p['targets']['thumbnail']['format'])}"])
    from reports import make_previews
    make_previews(root,p,manifest)
    report=check(root)
    return {'complete':not errors,'built_files':len(files),'build_errors':errors,'check_status':report['status']}


VISUAL = {
    'main':['identity','hands_anatomy','text_exact','framing','real_transparency_edges','small_size_readability','emotion_distinct'],
    'thumbnail':['text_exact','framing','real_transparency_edges','small_size_readability','matches_main'],
    'cover':['identity','framing','real_transparency_edges','cover_composition','cover_text_and_decoration_policy'],
    'banner':['identity','text_policy','background_policy','framing_no_stretch'],
    'chat_icon':['identity','front_head_only','no_text','no_extra_decoration','no_outer_white_outline','real_transparency_edges','framing','readable_at_50px','distinct_from_prior_albums']}
COMPLIANCE = ['content_policy','rights_and_portrait','font_and_material_licenses','copyright_owner','ai_policy_and_disclosure','category_eligibility','copy_fields']


def review_template(root):
    p=load_project(root);m=read(root/'manifest.json')
    path=root/'visual-review.json';old=read(path) if path.exists() else {'files':{}}
    entries={}
    for f in m['files']:
        if f['kind']!='submission':continue
        previous=old.get('files',{}).get(f['path'])
        if previous and previous.get('sha256')==sha(root/f['path']):entries[f['path']]=previous
        else:entries[f['path']]={'sha256':sha(root/f['path']),'reviewed_at':None,'reviewer':None,'checks':{key:{'status':'pending_visual','note':''} for key in VISUAL[f['role']]}}
    write(path,{'schema_version':1,'files':entries})
    cp=root/'compliance-review.json'
    if not cp.exists():write(cp,{'schema_version':1,'config_fingerprint':fingerprint(root),'content_fingerprint':content_fingerprint(root),'reviewed_at':None,'reviewer':None,'checks':{k:{'status':'pending_compliance','evidence':''} for k in COMPLIANCE}})
    return {'visual_template':str(path),'compliance_template':str(cp),'note':'No visual or rights checks were marked passed. Review the actual final files and evidence.'}


def check(root):
    from validation import validate
    report=validate(root)
    write(root/'qa'/'report.json',report)
    from reports import upload_guide
    upload_guide(root,load_project(root),report)
    return report


def package(root):
    p=load_project(root);report=check(root);m=read(root/'manifest.json')
    if report['status']=='failed':raise ValueError('Packaging blocked by detected file errors; see qa/report.json')
    draft=report['status']!='passed';stem=safe_name(p['name']);root.joinpath('packages').mkdir(exist_ok=True)
    # An earlier green package must not remain selectable after evidence expires.
    for f in (root/'packages').glob('*.zip'):
        dst=under(root,f"history/{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}/{f.name}");dst.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(f),str(dst))
    common=['names.csv','upload-guide.md','qa/report.json','platform-profile.json']
    full_extra=['preview.html','prompts.json','source-info.json','visual-review.json','compliance-review.json','revisions.json']
    results=[]
    for kind in ('投稿素材','完整包'):
        name=f"{stem}-{kind}{'-草稿' if draft else ''}.zip";path=root/'packages'/name
        files=set(common)
        files.update(f['path'] for f in m['files'] if kind=='完整包' or f['kind']=='submission')
        if kind=='完整包':
            files.update(full_extra)
            files.update(x.relative_to(root).as_posix() for x in (root/'qa').glob('*') if x.is_file())
        with ZipFile(path,'w',ZIP_DEFLATED,compresslevel=9) as z:
            for rel in sorted(files):
                f=under(root,rel)
                if f.is_file():z.write(f,rel)
        with ZipFile(path) as z:
            if z.testzip() is not None:raise ValueError('ZIP integrity check failed')
            entries=len(z.namelist())
        results.append({'file':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':sha(path),'entries':entries,'integrity':'passed','draft':draft})
    write(root/'qa'/'zip-check.json',results)
    return {'status':report['status'],'packages':results}


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','build','review-template','check','package'])
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--reference',type=Path);parser.add_argument('--name',default='我的角色');parser.add_argument('--count',type=int,default=24)
    args=parser.parse_args();root=args.project.resolve()
    try:
        if args.command=='init':
            if not args.reference:parser.error('init requires --reference')
            result=init(root,args.reference.resolve(),args.name,args.count)
        else:result={'build':build,'review-template':review_template,'check':check,'package':package}[args.command](root)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.command=='check':return 0 if result['status']=='passed' else (2 if result['status']=='failed' else 3)
        if args.command=='build' and not result['complete']:return 2
        return 0
    except (OSError,ValueError,KeyError) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(cli())
