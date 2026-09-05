"""Behavioral tests with synthetic art and mocked official evidence ONLY.

No real assets receive approval here. All simulated review decisions stay in
temporary projects created by this test suite.
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import sticker_pipeline as pipe
from image_ops import alpha_cutout, encode, metrics


def synthetic_art(index=0):
    im=Image.new('RGBA',(1024,1024));d=ImageDraw.Draw(im)
    color=[(235,153,72,255),(81,181,209,255),(201,151,211,255)][index%3]
    d.ellipse((120,100,900,920),fill=color,outline='#553322',width=16)
    d.ellipse((270,400,360,500),fill='white');d.ellipse((650,400,740,500),fill='white')
    d.arc((350,520,670,730),0,180,fill='#553322',width=12+index)
    return im


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='sticker-skill-test-')
        cls.base=Path(cls.temp.name)/'基础 项目'
        ref=Path(cls.temp.name)/'参考.png';synthetic_art().save(ref)
        pipe.init(cls.base,ref,'测试角色',3)
        p=pipe.read(cls.base/'project.json');p['intro']='测试场景';p['copyright_owner']='测试权利人'
        p['identity']={'type':'synthetic fixture, not an actual character'}
        for i,s in enumerate(p['stickers']):
            synthetic_art(i).save(cls.base/s['source']);s['pose']='Synthetic test fixture';s['prompt']='TEST ONLY, no imagegen invoked'
        for role in ('cover','chat_icon'):synthetic_art().save(cls.base/p['assets'][role]['source'])
        banner=Image.new('RGB',(1500,800),'#f4cfa0');ImageDraw.Draw(banner).ellipse((700,50,1350,730),fill='#e7a163');banner.save(cls.base/p['assets']['banner']['source'])
        pipe.write(cls.base/'project.json',p)
        result=pipe.build(cls.base)
        assert result['complete'],result

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.case=Path(self.temp.name)/self._testMethodName
        shutil.copytree(self.base,self.case)

    def report(self):return pipe.check(self.case)

    def has(self,report,code):return any(x['code']==code for x in report['issues'])

    def simulate_verified_profile(self):
        """Mock evidence for testing the gate, never a real official-rule claim."""
        profile=pipe.read(self.case/'platform-profile.json')
        profile['checked_for_submission_on']=date.today().isoformat()
        profile['sources']=[{'id':'test-evidence','kind':'official_page','locator':'https://sticker.weixin.qq.com/','observed_on':date.today().isoformat(),'excerpt':'SYNTHETIC TEST FIXTURE; not actual platform evidence'}]
        p=pipe.read(self.case/'project.json')
        for r in profile['rules']:
            r['status']='verified';r['source_ids']=['test-evidence']
            if r['field']=='count':r['value']=[1,3,24]
            elif r['field']=='static_allowed':r['value']=True
            elif r['field']=='text_limits':r['value']={'title':50,'intro':80,'copyright_owner':10,'meaning':20}
            elif r['field'] in ('content_policy','ai_policy','visual_policy'):r['value']='SYNTHETIC TEST POLICY'
            elif r['field']=='max_bytes':r['value']=512000
        pipe.write(self.case/'platform-profile.json',profile)
        result=pipe.build(self.case);self.assertTrue(result['complete'])

    def simulate_reviews(self):
        """Mock reviewer results, restricted to this generated test project."""
        pipe.review_template(self.case)
        v=pipe.read(self.case/'visual-review.json')
        for entry in v['files'].values():
            entry.update(reviewed_at='TEST-SIMULATION',reviewer='synthetic-test')
            for check in entry['checks'].values():check.update(status='passed',note='SIMULATED fixture observation for gating test, not real visual approval')
        pipe.write(self.case/'visual-review.json',v)
        cp=pipe.read(self.case/'compliance-review.json');cp.update(reviewed_at='TEST-SIMULATION',reviewer='synthetic-test',config_fingerprint=pipe.fingerprint(self.case),content_fingerprint=pipe.content_fingerprint(self.case))
        for c in cp['checks'].values():c.update(status='passed',evidence='SYNTHETIC fixture facts for gating test')
        pipe.write(self.case/'compliance-review.json',cp)

    def test_default_cannot_claim_compliance(self):
        r=self.report();self.assertEqual(r['status'],'pending_rules');self.assertGreater(r['summary']['pending_visual'],0)
        self.assertTrue(self.has(r,'rule_unverified'));self.assertTrue(self.has(r,'compliance_ai_policy_and_disclosure'))

    def test_rule_metadata_does_not_replace_visual_review(self):
        self.simulate_verified_profile();r=self.report()
        self.assertEqual(r['summary']['pending_rules'],0);self.assertGreater(r['summary']['pending_visual'],0)

    def test_complete_mocked_gate_then_changed_source_invalidates(self):
        self.simulate_verified_profile();self.simulate_reviews();self.assertEqual(self.report()['status'],'passed')
        art=synthetic_art(2);ImageDraw.Draw(art).ellipse((420,230,600,340),fill='#e22141');art.save(self.case/'sources'/'01.png')
        self.assertTrue(self.has(self.report(),'source_changed'))
        pipe.build(self.case);r=self.report()
        self.assertGreater(r['summary']['pending_visual'],0);self.assertGreater(r['summary']['pending_compliance'],0)

    def test_dimensions_and_signature(self):
        f=self.case/'submission'/'main'/'01.png';Image.open(f).resize((239,240)).save(f)
        self.assertTrue(self.has(self.report(),'dimensions'))
        Image.new('RGB',(240,240),'white').save(f,'JPEG')
        self.assertTrue(self.has(self.report(),'format'))

    def test_missing_corrupt_and_unlisted(self):
        f=self.case/'submission'/'main'/'01.png';f.write_bytes(b'broken PNG')
        self.assertTrue(self.has(self.report(),'unreadable_image'))
        f.unlink();self.assertTrue(self.has(self.report(),'unexpected_or_missing_file'))
        (self.case/'submission'/'notes.txt').write_text('not an upload file')
        self.assertTrue(self.has(self.report(),'submission_inventory'))

    def test_number_and_localized_copy_mismatch(self):
        p=pipe.read(self.case/'project.json');p['stickers'][1]['id']='01';pipe.write(self.case/'project.json',p)
        with self.assertRaises(ValueError):pipe.load_project(self.case)
        p['stickers'][1]['id']='02';pipe.write(self.case/'project.json',p)
        m=pipe.read(self.case/'manifest.json');f=next(x for x in m['files'] if x['kind']=='localized')
        synthetic_art(2).save(self.case/f['path'])
        self.assertTrue(self.has(self.report(),'localized_mismatch'))

    def test_opaque_fake_transparency_and_clipping(self):
        opaque=Image.new('RGBA',(1024,1024),'white')
        d=ImageDraw.Draw(opaque)
        for y in range(0,1024,32):
            for x in range(0,1024,32):
                if (x+y)//32%2:d.rectangle((x,y,x+31,y+31),fill='#ddd')
        with self.assertRaisesRegex(ValueError,'alpha_missing'):alpha_cutout(opaque,{'mode':'native'},self.case)
        f=self.case/'submission'/'main'/'01.png';im=Image.open(f).convert('RGBA');im.putpixel((0,50),(30,20,10,255));im.save(f)
        self.assertTrue(self.has(self.report(),'edge_contact'))

    def test_chroma_preserves_enclosed_key_color(self):
        im=Image.new('RGB',(100,100),(0,240,240));d=ImageDraw.Draw(im)
        d.rectangle((20,20,80,80),fill=(130,60,30));d.rectangle((40,40,60,60),fill=(0,240,240))
        cut,info=alpha_cutout(im,{'mode':'chroma','key_rgb':[0,240,240],'screen_confirmed':True},self.case)
        self.assertEqual(cut.getpixel((0,0))[3],0)
        self.assertEqual(cut.getpixel((50,50)),(0,240,240,255))
        self.assertGreater(info['enclosed_key_pixels_retained'],0)

    def test_chroma_protection_and_explicit_hole_removal(self):
        im=Image.new('RGB',(100,100),(0,240,240));d=ImageDraw.Draw(im);d.rectangle((20,20,80,80),fill='#a05020')
        d.rectangle((40,40,60,60),fill=(0,240,240))
        mask=Image.new('L',(100,100));ImageDraw.Draw(mask).rectangle((40,40,60,60),fill=255);mask.save(self.case/'remove.png')
        bg={'mode':'chroma','key_rgb':[0,240,240],'screen_confirmed':True,'remove_mask':'remove.png'}
        cut,_=alpha_cutout(im,bg,self.case);self.assertEqual(cut.getpixel((50,50))[3],0)
        bg['protect_mask']='remove.png'
        with self.assertRaisesRegex(ValueError,'overlap'):alpha_cutout(im,bg,self.case)
        del bg['remove_mask'];cut,_=alpha_cutout(im,bg,self.case);self.assertEqual(cut.getpixel((50,50)),(0,240,240,255))

    def test_chroma_requires_visual_confirmation(self):
        with self.assertRaisesRegex(ValueError,'screen_confirmed'):
            alpha_cutout(Image.new('RGB',(100,100),(0,240,240)),{'mode':'chroma','key_rgb':[0,240,240]},self.case)

    def test_protected_partial_alpha_is_not_squared(self):
        im=Image.new('RGBA',(100,100),(0,240,240,255));ImageDraw.Draw(im).rectangle((20,20,80,80),fill=(140,70,30,255))
        im.putpixel((50,50),(70,140,170,128))
        mask=Image.new('L',(100,100));mask.putpixel((50,50),255);mask.save(self.case/'protect.png')
        out,_=alpha_cutout(im,{'mode':'chroma','key_rgb':[0,240,240],'screen_confirmed':True,'protect_mask':'protect.png'},self.case)
        self.assertEqual(out.getpixel((50,50)),(70,140,170,128))

    def test_opaque_export_requires_explicit_color(self):
        im=synthetic_art();target={'transparent':False}
        with self.assertRaisesRegex(ValueError,'opaque_color'):pipe.submission_image(im,target)
        target['opaque_color']='#edc899';out=pipe.submission_image(im,target)
        self.assertEqual(out.mode,'RGB');self.assertEqual(out.getpixel((0,0)),(237,200,153))

    def test_photo_pet_character_config_is_not_hardcoded(self):
        for kind,mode,ext in [('photo','RGB','.jpg'),('pet','RGBA','.png'),('character','P','.png')]:
            reference=self.case/f'{kind}{ext}';synthetic_art().convert(mode).save(reference)
            dest=self.case/f'{kind} 独立项目'
            pipe.init(dest,reference,kind,1)
            project=pipe.read(dest/'project.json');project['identity']={'type':kind,'feature':'cyan fur' if kind=='pet' else 'user-defined'}
            pipe.write(dest/'project.json',project)
            self.assertEqual(pipe.load_project(dest)['identity']['type'],kind)
            self.assertTrue((dest/project['reference']).exists())

    def test_compression_threshold_not_hard_limit(self):
        profile=pipe.read(self.case/'platform-profile.json')
        next(r for r in profile['rules'] if r['id']=='icon-compression')['value']=1
        pipe.write(self.case/'platform-profile.json',profile);pipe.build(self.case)
        r=self.report();self.assertTrue(self.has(r,'compression_threshold'))
        self.assertFalse(self.has(r,'official_byte_limit'));self.assertEqual(r['summary']['failed'],0)

    def test_verified_hard_limit_and_conflict(self):
        self.simulate_verified_profile();profile=pipe.read(self.case/'platform-profile.json')
        rule=next(x for x in profile['rules'] if x['id']=='main-max_bytes');rule['value']=1
        pipe.write(self.case/'platform-profile.json',profile);pipe.build(self.case)
        self.assertTrue(self.has(self.report(),'official_byte_limit'))
        conflict=copy.deepcopy(rule);conflict['id']='conflicting-limit';conflict['value']=999999;profile['rules'].append(conflict)
        pipe.write(self.case/'platform-profile.json',profile);pipe.build(self.case)
        self.assertTrue(self.has(self.report(),'rule_conflict'))

    def test_missing_empty_and_malformed_rules_cannot_pass(self):
        self.simulate_verified_profile();self.simulate_reviews();profile=pipe.read(self.case/'platform-profile.json')
        next(r for r in profile['rules'] if r['id']=='main-transparent')['value']='probably'
        pipe.write(self.case/'platform-profile.json',profile);pipe.build(self.case)
        self.assertTrue(self.has(self.report(),'rule_unverified'))
        profile['rules']=[];pipe.write(self.case/'platform-profile.json',profile);pipe.build(self.case)
        self.assertTrue(self.has(self.report(),'rule_missing'))

    def test_visual_text_and_icon_defect_fail(self):
        pipe.review_template(self.case);v=pipe.read(self.case/'visual-review.json')
        for path,record in v['files'].items():
            record.update(reviewed_at='TEST',reviewer='test')
            if path.endswith('chat-icon.png'):record['checks']['no_extra_decoration']={'status':'failed','note':'Test observation: a star is present'}
            if path.endswith('main/01.png'):record['checks']['text_exact']={'status':'failed','note':'Test observation: lettering differs from requested text'}
        pipe.write(self.case/'visual-review.json',v);r=self.report()
        self.assertTrue(self.has(r,'visual_no_extra_decoration'));self.assertTrue(self.has(r,'visual_text_exact'))

    def test_lowres_input_not_claimed_highres(self):
        synthetic_art().resize((128,128)).save(self.case/'sources'/'01.png')
        result=pipe.build(self.case);self.assertFalse(result['complete'])
        self.assertIn('source_resolution',str(result['build_errors']))

    def test_static_gif_and_quality_floor(self):
        im=synthetic_art().resize((240,240));path=self.case/'static.gif'
        encode(im,path,'GIF');v=metrics(path)
        self.assertEqual(v['frames'],1);self.assertTrue(v['has_transparency'])
        with self.assertRaisesRegex(ValueError,'byte_budget'):encode(im,self.case/'too-small.png','PNG',10)

    def test_draft_pack_integrity_and_preview_links(self):
        pipe.review_template(self.case);result=pipe.package(self.case)
        self.assertTrue(all(x['draft'] for x in result['packages']))
        for item in result['packages']:
            with ZipFile(self.case/item['file']) as z:
                self.assertIsNone(z.testzip());self.assertIn('upload-guide.md',z.namelist())
                self.assertFalse(any(s.startswith('references/') for s in z.namelist()))
        from html.parser import HTMLParser
        links=[]
        class Parser(HTMLParser):
            def handle_starttag(self,tag,attrs):links.extend(v for k,v in attrs if k in ('href','src'))
        Parser().feed((self.case/'preview.html').read_text(encoding='utf-8'))
        self.assertTrue(all((self.case/link).exists() for link in links))

    def test_count_change_archives_only_obsolete_generated_files(self):
        pipe.package(self.case);p=pipe.read(self.case/'project.json');p['count']=1;p['stickers']=p['stickers'][:1]
        pipe.write(self.case/'project.json',p);(self.case/'sources'/'keep.txt').write_text('user data')
        result=pipe.build(self.case);self.assertTrue(result['complete'])
        self.assertFalse((self.case/'submission'/'main'/'03.png').exists())
        self.assertTrue((self.case/'sources'/'03.png').exists());self.assertTrue((self.case/'sources'/'keep.txt').exists())
        self.assertFalse(list((self.case/'packages').glob('*.zip')))
        self.assertEqual(self.report()['summary']['failed'],0)


if __name__=='__main__':unittest.main(verbosity=2)
