#!/usr/bin/env python3
"""Optional maintainer helper. Generated Android vectors are already vendored.
Streams Lucide's MIT-licensed SVG package; writes only selected missing icons.
"""
from pathlib import Path
import urllib.request,tarfile,xml.etree.ElementTree as ET,re,shutil
ROOT=Path(__file__).resolve().parents[1]
WANTED={'star': 'star', 'sliders-horizontal': 'slidershorizontal', 'paint-roller': 'paintroller', 'a-large-small': 'alargesmall', 'image': 'image', 'trash-2': 'trash2', 'arrow-up-right': 'arrowupright', 'heart-pulse': 'heartpulse', 'paintbrush': 'paintbrush', 'rectangle-ellipsis': 'rectangleellipsis', 'shirt': 'shirt', 'clock-3': 'clock3', 'bird': 'bird', 'sprout': 'sprout', 'armchair': 'armchair', 'arrow-up-from-line': 'arrowupfromline', 'book-open': 'bookopen', 'coffee': 'coffee', 'coins': 'coins', 'cpu': 'cpu', 'dumbbell': 'dumbbell', 'gem': 'gem', 'hammer': 'hammer', 'hotel': 'hotel', 'lamp-desk': 'lampdesk', 'minus': 'minus', 'palette': 'palette', 'plane': 'plane', 'puzzle': 'puzzle', 'smile': 'smile', 'washing-machine': 'washingmachine', 'zap': 'zap', 'cloud': 'cloud', 'hash': 'hash', 'vault': 'vault', 'key-round': 'keyround', 'download': 'download', 'upload': 'upload', 'layers': 'layers', 'user-plus': 'userplus', 'bus': 'bus', 'graduation-cap': 'graduationcap', 'history': 'history', 'send': 'send'}
ANDROID='http://schemas.android.com/apk/res/android'
def val(tag,field,default=0):return float(tag.attrib.get(field,default))
def path_data(tag):
    kind=tag.tag.split('}')[-1];a=tag.attrib
    if kind=='path':return a['d']
    if kind=='line':return f'M{val(tag,"x1")} {val(tag,"y1")}L{val(tag,"x2")} {val(tag,"y2")}'
    if kind in ('polyline','polygon'):
        pairs=re.findall(r'[-+]?\d*\.?\d+',a['points']);return 'M'+' '.join(pairs)+('z'if kind=='polygon'else'')
    if kind in ('circle','ellipse'):
        cx,cy=val(tag,'cx'),val(tag,'cy');rx=val(tag,'r')if kind=='circle'else val(tag,'rx');ry=rx if kind=='circle'else val(tag,'ry');return f'M{cx-rx} {cy}a{rx} {ry} 0 1 0 {rx*2} 0a{rx} {ry} 0 1 0 {-rx*2} 0'
    if kind=='rect':
        x,y,w,h=val(tag,'x'),val(tag,'y'),val(tag,'width'),val(tag,'height');r=val(tag,'rx');return f'M{x+r} {y}h{w-2*r}a{r} {r} 0 0 1 {r} {r}v{h-2*r}a{r} {r} 0 0 1 {-r} {r}h{-w+2*r}a{r} {r} 0 0 1 {-r} {-r}v{-h+2*r}a{r} {r} 0 0 1 {r} {-r}z'if r else f'M{x} {y}h{w}v{h}h{-w}z'
    raise ValueError('Unsupported SVG element '+kind)
with urllib.request.urlopen('https://registry.npmjs.org/lucide-static/-/lucide-static-0.468.0.tgz')as response:
    with tarfile.open(fileobj=response,mode='r|gz')as archive:
        remaining=dict(WANTED)
        for entry in archive:
            name=Path(entry.name).stem
            if not entry.name.startswith('package/icons/')or name not in remaining or not entry.name.endswith('.svg'):continue
            target=ROOT/'res/drawable'/('ic_'+remaining.pop(name)+'.xml');source=ET.fromstring(archive.extractfile(entry).read());vector=ET.Element('vector',{'xmlns:android':ANDROID,'android:width':'24dp','android:height':'24dp','android:viewportWidth':'24','android:viewportHeight':'24'})
            for child in source:
                ET.SubElement(vector,'path',{'android:pathData':path_data(child),'android:strokeColor':'#ffffffff','android:fillColor':'@android:color/transparent','android:strokeWidth':'1.9','android:strokeLineCap':'round','android:strokeLineJoin':'round'})
            target.write_text(ET.tostring(vector,encoding='unicode'));print(target.name)
            if not remaining:break
        if remaining:raise SystemExit('Missing upstream icons: '+str(remaining))
shutil.copyfile(ROOT/'res/drawable/ic_ellipsis.xml',ROOT/'res/drawable/ic_morehorizontal.xml')
