#!/usr/bin/env python3
"""Build a fully native Android APK, with no Gradle, Node, HTML or browser assets.
Requires JDK 11+, Android platform 35 and build-tools 35.0.0.
Usage: ANDROID_SDK_ROOT=/path/to/sdk python3 build_apk.py /path/to/output.apk
"""
from pathlib import Path
import os,sys,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parent
SDK=Path(os.environ.get('ANDROID_SDK_ROOT',str(Path.home()/'.cache/android-sdk')))
PLATFORM=next((p for p in [SDK/'platforms/android-35/android.jar',SDK/'android-35/android.jar']if p.exists()),None)
TOOLS=next((p for p in [SDK/'build-tools/35.0.0',SDK/'android-15']if(p/'aapt2').exists()),None)
if not PLATFORM or not TOOLS:sys.exit('Android platform 35/build-tools 35.0.0 not found; set ANDROID_SDK_ROOT.')
JAVA=Path(os.environ.get('JAVA_HOME','/usr/lib/jvm/jdk-11'))
if not(JAVA/'bin/javac').exists():JAVA=Path(shutil.which('javac')).resolve().parent.parent
ENV={**os.environ,'JAVA_HOME':str(JAVA),'PATH':str(JAVA/'bin')+':'+os.environ.get('PATH','')}
WORK=ROOT/'.cache/apk-build';WORK.mkdir(parents=True,exist_ok=True)
OUTPUT=Path(sys.argv[1]).resolve()if len(sys.argv)>1 else ROOT.parent/'TBank-Native-2.3.apk'
def run(*args):
    print('+',' '.join(map(str,args)),flush=True);subprocess.run(list(map(str,args)),cwd=ROOT,env=ENV,check=True)
classes,dex,generated=[WORK/x for x in ['classes','dex','generated']]
for p in [classes,dex,generated]:
    if p.exists():shutil.rmtree(p)
    p.mkdir()
CORE=ROOT/'lib/zxing-core-3.5.3.jar'
run(TOOLS/'aapt2','compile','--dir',ROOT/'res','-o',WORK/'resources.zip')
run(TOOLS/'aapt2','link','-o',WORK/'resources.apk','-I',PLATFORM,'--manifest',ROOT/'AndroidManifest.xml','--java',generated,'-A',ROOT/'assets',WORK/'resources.zip')
sources=list((ROOT/'src').rglob('*.java'))+list(generated.rglob('*.java'))
run(JAVA/'bin/javac','-encoding','UTF-8','--release','8','-classpath',str(PLATFORM)+os.pathsep+str(CORE),'-d',classes,*sources)
run(TOOLS/'d8','--lib',PLATFORM,'--min-api','26','--output',dex,*classes.rglob('*.class'),CORE)
with zipfile.ZipFile(WORK/'unsigned.apk','w',compression=zipfile.ZIP_DEFLATED)as out:
    with zipfile.ZipFile(WORK/'resources.apk')as base:
        for entry in base.infolist():out.writestr(entry,base.read(entry))
    for f in dex.glob('*.dex'):out.write(f,f.name)
run(TOOLS/'zipalign','-f','-p','4',WORK/'unsigned.apk',WORK/'aligned.apk')
KEY=Path(os.environ.get('BANK_SIGNING_KEY',str(ROOT/'android/.signing/demo-signing.p12')))
if not KEY.exists():sys.exit('Signing key not found. Supply BANK_SIGNING_KEY; do not commit your private key.')
run(TOOLS/'apksigner','sign','--ks',KEY,'--ks-key-alias','demo','--ks-pass','pass:android','--key-pass','pass:android','--v4-signing-enabled','false','--out',OUTPUT,WORK/'aligned.apk')
run(TOOLS/'apksigner','verify','--verbose','--print-certs',OUTPUT)
run(TOOLS/'aapt','dump','badging',OUTPUT)
print('APK ready:',OUTPUT,'('+str(OUTPUT.stat().st_size)+' bytes)')
