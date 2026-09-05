"""Measured checks and explicit evidence gates; no automatic visual approval."""
from datetime import date
import json
from pathlib import Path

from image_ops import metrics

ROLE_FIELDS=('size','formats','transparent','max_bytes','visual_policy')
ALBUM_FIELDS=('count','static_allowed','text_limits','content_policy','ai_policy')


def rule_value_valid(field,value):
    positive=lambda x: isinstance(x,int) and not isinstance(x,bool) and x>0
    if field=='size':return isinstance(value,list) and len(value)==2 and all(positive(n) for n in value)
    if field=='formats':return isinstance(value,list) and bool(value) and all(f in ('PNG','GIF','JPEG') for f in value)
    if field in ('transparent','static_allowed'):return isinstance(value,bool)
    if field=='max_bytes':return positive(value) or value=='not_specified'
    if field=='count':return isinstance(value,list) and bool(value) and all(positive(n) for n in value)
    if field=='text_limits':return isinstance(value,dict) and all(k in value and (positive(value[k]) or value[k]=='not_specified') for k in ('title','intro','copyright_owner','meaning'))
    return isinstance(value,(str,dict)) and bool(value)


def validate(root):
    from sticker_pipeline import load_project, read, sha, fingerprint, content_fingerprint, ROLES, VISUAL, COMPLIANCE
    p=load_project(root);issues=[];measured=[]

    def issue(status,code,asset,message):
        issues.append({'status':status,'code':code,'asset':asset,'message':message})

    def pending(code,asset,message):issue('pending_rules',code,asset,message)

    if not (root/'manifest.json').exists():
        issue('failed','manifest_missing','project','Build/import the project before checking')
        return {'status':'failed','issues':issues,'files':[]}
    m=read(root/'manifest.json')
    if not m.get('complete'):
        issue('failed','incomplete_build','project',json.dumps(m.get('build_errors',[]),ensure_ascii=False))
    if m.get('config_fingerprint')!=fingerprint(root):
        issue('failed','stale_build','project','Project or profile changed; rebuild all affected derivatives')
    expected={f'{i:02}' for i in range(1,p['count']+1)}
    for role in ('main','thumbnail'):
        entries=[f for f in m['files'] if f['role']==role and f['kind']=='submission']
        if len(entries)!=p['count'] or {f['id'] for f in entries}!=expected:
            issue('failed','numbering',role,'Submission files must match the ordered project ids exactly')
        directory=root/'submission'/('main' if role=='main' else 'thumbnails')
        actual={x.relative_to(root).as_posix() for x in directory.iterdir() if x.is_file()} if directory.exists() else set()
        if actual!={f['path'] for f in entries}:issue('failed','unexpected_or_missing_file',role,'Submission folder contains missing or unlisted files')
    for role in ('cover','banner','chat_icon'):
        if sum(f['role']==role and f['kind']=='submission' for f in m['files'])!=1:
            issue('failed','asset_count',role,'Exactly one submission asset is required')
    listed={f['path'] for f in m['files'] if f['kind']=='submission'}
    actual={f.relative_to(root).as_posix() for f in (root/'submission').rglob('*') if f.is_file()}
    if actual!=listed:issue('failed','submission_inventory','submission','Submission directory must contain only the files mapped by the manifest')
    for source in m.get('sources',[]):
        path=root/source['source']
        if not path.is_file() or sha(path)!=source['sha256']:
            issue('failed','source_changed',source['source'],'Selected source changed; build outputs again')
    seen_main={}
    for f in m['files']:
        path=root/f['path']
        try:
            v=metrics(path);v.update(path=f['path'],role=f['role'],kind=f['kind'],sha256=sha(path));measured.append(v)
        except (OSError,ValueError) as e:
            issue('failed','unreadable_image',f['path'],str(e));continue
        if v['sha256']!=f['sha256']:issue('failed','file_changed',f['path'],'File differs from its build manifest')
        if v['size']!=f['expected_size']:issue('failed','dimensions',f['path'],f"Expected {f['expected_size']}; got {v['size']}")
        if v['format']!=f['expected_format']:issue('failed','format',f['path'],'Image signature does not match intended format')
        if v['frames']!=1:issue('failed','animated_file',f['path'],'This skill builds static files; multiple frames detected')
        if v['visible_pixels']==0:issue('failed','empty_image',f['path'],'Image contains no visible artwork')
        if f['expected_transparent']:
            if not v['has_transparency']:issue('failed','alpha_missing',f['path'],'Opaque background: cannot pass true-alpha checks')
            if v['edge_alpha_max']>0:issue('failed','edge_contact',f['path'],'Visible pixels touch canvas border; review clipping/margins')
        elif v['has_transparency']:issue('failed','unexpected_alpha',f['path'],'Finished banner must be opaque under this production target')
        if f['kind']=='submission':
            budget=p['targets'][f['role']].get('max_bytes_goal')
            if budget and v['bytes']>budget:issue('failed','production_byte_budget',f['path'],f'Exceeds configured working goal {budget} bytes; this is not an official limit claim')
            if f['role']=='main':
                if v['sha256'] in seen_main:issue('pending_visual','duplicate_art',f['path'],f"Identical to {seen_main[v['sha256']]}; confirm distinct intended sticker")
                seen_main[v['sha256']]=f['path']
            if f['role']!='banner' and v['content_extent']<.80:
                issue('pending_visual','excess_margin',f['path'],'Artwork uses <80% of both dimensions; review apparent size')
    # Localized copies must be byte-identical to daily PNGs, not unrelated art.
    for sid in expected:
        d=[f for f in m['files'] if f['id']==sid and f['kind']=='daily' and f['role']=='main']
        c=[f for f in m['files'] if f['id']==sid and f['kind']=='localized']
        if len(d)!=1 or len(c)!=1 or not (root/d[0]['path']).is_file() or not (root/c[0]['path']).is_file() or sha(root/d[0]['path'])!=sha(root/c[0]['path']):
            issue('failed','localized_mismatch',sid,'Chinese-name copy must match the daily PNG')

    profile=read(root/'platform-profile.json');rules=profile.get('rules',[])
    if profile.get('platform')!='wechat' or profile.get('category')!=p['category']:
        pending('profile_scope','profile','Profile must match the selected platform and category')
    if profile.get('checked_for_submission_on')!=date.today().isoformat():
        pending('rules_freshness','profile','Recheck relevant official rules for this submission date; do not merely change the date')
    sources={s['id']:s for s in profile.get('sources',[]) if s.get('id')}
    bykey={}
    for r in rules:bykey.setdefault((r.get('scope'),r.get('field')),[]).append(r)
    required=[('album',k) for k in ALBUM_FIELDS]+[(role,k) for role in ROLES for k in ROLE_FIELDS]
    valid=[]
    for key in required:
        candidates=[r for r in bykey.get(key,[]) if r.get('kind')=='requirement']
        if not candidates:
            pending('rule_missing','/'.join(key),'Required rule is absent; missing entries cannot mean passed');continue
        confirmed=[]
        for rule in candidates:
            evidence=[]
            for sid in rule.get('source_ids',[]):
                src=sources.get(sid,{})
                good=src.get('kind') in ('official_page','official_screenshot') and src.get('locator') and src.get('excerpt')
                try:good=good and date.fromisoformat(src['observed_on'])<=date.today()
                except (KeyError,ValueError,TypeError):good=False
                if src.get('kind')=='official_page':
                    from urllib.parse import urlparse
                    host=urlparse(src.get('locator','')).hostname or ''
                    good=good and (host=='weixin.qq.com' or host.endswith('.weixin.qq.com') or host=='qq.com' or host.endswith('.qq.com'))
                if src.get('kind')=='official_screenshot':good=good and (root/src.get('locator','')).is_file()
                if good:evidence.append(src)
            if rule.get('status')=='verified' and rule_value_valid(rule.get('field'),rule.get('value')) and evidence:confirmed.append(rule)
            else:pending('rule_unverified',rule.get('id','/'.join(key)),'Needs a value and relevant official evidence, or conflict resolution')
        values={json.dumps(r['value'],sort_keys=True,ensure_ascii=False) for r in confirmed}
        if len(values)>1:
            pending('rule_conflict','/'.join(key),'Conflicting verified requirements; resolve by current category-specific evidence')
        elif confirmed:valid.append(confirmed[0])
    submitted=[v for v in measured if v['kind']=='submission']
    for rule in valid:
        scope,field,value=rule['scope'],rule['field'],rule['value']
        if scope=='album':
            if field=='count' and (not isinstance(value,list) or p['count'] not in value):issue('failed','official_count','album','Count not in the verified allowed set')
            if field=='static_allowed' and value is not True:issue('failed','static_not_allowed','album','Verified category does not accept static submission')
            if field=='text_limits' and isinstance(value,dict):
                for name,limit in value.items():
                    if not isinstance(limit,int):continue
                    texts=[s.get('meaning',s['name']) for s in p['stickers']] if name=='meaning' else [p.get(name) or '']
                    if any(len(t)>limit for t in texts):issue('failed','text_length',name,f'Exceeds verified {limit}-character limit; also check platform counter')
            continue
        for v in submitted:
            if v['role']!=scope:continue
            if field=='size' and v['size']!=value:issue('failed','official_size',v['path'],'Does not match verified official dimensions')
            if field=='formats' and v['format'] not in value:issue('failed','official_format',v['path'],'Does not match verified allowed formats')
            if field=='transparent' and isinstance(value,bool) and v['has_transparency']!=value:issue('failed','official_alpha',v['path'],'Does not match verified alpha requirement')
            if field=='max_bytes' and isinstance(value,int) and v['bytes']>value:issue('failed','official_byte_limit',v['path'],f'Exceeds verified hard limit {value} bytes')
    for rule in rules:
        if rule.get('kind')=='auto_compression' and isinstance(rule.get('value'),int):
            for v in submitted:
                if v['role']==rule['scope'] and v['bytes']>rule['value']:
                    issue('warning','compression_threshold',v['path'],'Crosses recorded automatic compression threshold; not a hard rejection limit. Verify current source and resulting quality.')

    visual=read(root/'visual-review.json') if (root/'visual-review.json').exists() else {'files':{}}
    for v in submitted:
        record=visual.get('files',{}).get(v['path'],{})
        fresh=record.get('sha256')==v['sha256'] and record.get('reviewed_at') and record.get('reviewer')
        for key in VISUAL[v['role']]:
            item=record.get('checks',{}).get(key,{})
            if fresh and item.get('status')=='failed':issue('failed','visual_'+key,v['path'],item.get('note','Visual defect'))
            elif not fresh or item.get('status')!='passed' or not item.get('note'):
                issue('pending_visual','visual_'+key,v['path'],'Actual final image needs reviewed result and specific observation; changed hashes invalidate old results')
    cp=read(root/'compliance-review.json') if (root/'compliance-review.json').exists() else {}
    fresh=cp.get('config_fingerprint')==fingerprint(root) and cp.get('content_fingerprint')==content_fingerprint(root) and cp.get('reviewed_at') and cp.get('reviewer')
    for key in COMPLIANCE:
        item=cp.get('checks',{}).get(key,{})
        if fresh and item.get('status')=='failed':issue('failed','compliance_'+key,'album',item.get('evidence','Known compliance issue'))
        elif not fresh or item.get('status')!='passed' or not item.get('evidence'):
            issue('pending_compliance','compliance_'+key,'album','Needs actual content/source review and user-confirmed facts where applicable')
    if not p.get('copyright_owner'):issue('pending_compliance','copyright_owner_missing','album','Use an actual user-confirmed rights-holder name; do not infer it from the character name')
    if not p.get('intro'):issue('pending_compliance','intro_missing','album','Write the album description and review it against current field limits')
    states={i['status'] for i in issues}
    status=next((s for s in ('failed','pending_rules','pending_compliance','pending_visual') if s in states),'passed')
    return {'schema_version':1,'checked_on':date.today().isoformat(),'status':status,'local_check_only':True,
            'summary':{s:sum(i['status']==s for i in issues) for s in ('failed','pending_rules','pending_visual','pending_compliance','warning')},
            'issues':issues,'files':measured,'meaning_of_passed':'Local file/visual/evidence checks completed, not an official approval or guarantee'}
