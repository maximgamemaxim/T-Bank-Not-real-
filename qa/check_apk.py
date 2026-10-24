#!/usr/bin/env python3
"""Static release checks. Does not claim to launch Android or validate visuals."""
from pathlib import Path
import re,json,os,subprocess,zipfile,struct,hashlib,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
APK=Path(sys.argv[1]).resolve()if len(sys.argv)>1 else ROOT.parent/'TBank-Native-2.3.apk'
SDK=Path(os.environ.get('ANDROID_SDK_ROOT',str(Path.home()/'.cache/android-sdk')))
TOOLS=SDK/'build-tools/35.0.0'
JAVA=Path(os.environ.get('JAVA_HOME','/usr/lib/jvm/jdk-11'))
ENV={**os.environ,'JAVA_HOME':str(JAVA),'PATH':str(JAVA/'bin')+':'+os.environ.get('PATH','')}
checks=[]
def check(name,ok,detail=''):
    checks.append({'name':name,'passed':bool(ok),'detail':detail});print(('PASS 'if ok else'FAIL ')+name+(' — '+detail if detail else''))
def command(*args):return subprocess.run(list(map(str,args)),text=True,capture_output=True,env=ENV)
def dex_strings(data):
    count,offset=struct.unpack_from('<II',data,56);result=[]
    for i in range(count):
        at=struct.unpack_from('<I',data,offset+4*i)[0]
        while data[at]&128:at+=1
        at+=1;end=data.find(b'\0',at);result.append(data[at:end].decode('utf-8','replace'))
    return result
def dex_types(data,strings):
    count,offset=struct.unpack_from('<II',data,64);return [strings[struct.unpack_from('<I',data,offset+4*i)[0]]for i in range(count)]
def dex_definitions(data,types):
    count,offset=struct.unpack_from('<II',data,96);return [types[struct.unpack_from('<I',data,offset+32*i)[0]]for i in range(count)]
badging=command(TOOLS/'aapt','dump','badging',APK);check('aapt parses APK',badging.returncode==0)
check('Native version 2.3.0, code 6',"versionCode='6'"in badging.stdout and"versionName='2.3.0'"in badging.stdout)
check('Install package preserved',"name='com.mvt.tbank'"in badging.stdout)
check('Android 8+, target API 34',"sdkVersion:'26'"in badging.stdout and"targetSdkVersion:'34'"in badging.stdout)
permissions=re.findall(r"uses-permission: name='([^']+)'",badging.stdout)
check('Only required camera, vibration and cloud network permissions',set(permissions)=={'android.permission.CAMERA','android.permission.VIBRATE','android.permission.INTERNET','android.permission.ACCESS_NETWORK_STATE'},', '.join(permissions))
check('Camera hardware optional',"uses-feature-not-required: name='android.hardware.camera'"in badging.stdout)
check('Launcher is real native Activity',"launchable-activity: name='com.mvt.tbank.MainActivity'"in badging.stdout)
sig=command(TOOLS/'apksigner','verify','--verbose','--print-certs',APK)
check('APK signature verification',sig.returncode==0)
certificate='8c266aa51593f9af658e5f8d42485151e49469a9614d634c590c32bbf9680e44'
check('Same update signing certificate',certificate in sig.stdout)
check('v2 APK signature present','Verified using v2 scheme (APK Signature Scheme v2): true'in sig.stdout)
align=command(TOOLS/'zipalign','-c','-p','4',APK);check('4-byte ZIP alignment',align.returncode==0)
manifest=command(TOOLS/'aapt','dump','xmltree',APK,'AndroidManifest.xml').stdout
check('Release build is not debuggable','android:debuggable'in manifest and re.search(r'android:debuggable[^\n]*0x0\b',manifest)is not None)
check('Android backup disabled','android:allowBackup'in manifest and re.search(r'android:allowBackup[^\n]*0x0\b',manifest)is not None)
with zipfile.ZipFile(APK)as archive:
    files=archive.namelist();data=archive.read('classes.dex');strings=dex_strings(data);types=dex_types(data,strings);definitions=dex_definitions(data,types)
    check('No browser assets',not any(n.lower().endswith(('.html','.htm','.js','.css','.woff','.woff2','.webmanifest'))for n in files))
    check('No WebView or browser type references',not any(t.startswith(('Landroid/webkit/','Lorg/chromium/','Lcom/getcapacitor/','Lorg/apache/cordova/'))for t in types))
    check('Native View widgets are referenced',all('Landroid/widget/'+n+';'in types for n in ['TextView','EditText','Button','LinearLayout','FrameLayout','ScrollView']))
    check('Native Canvas and PdfDocument referenced',all(t in types for t in ['Landroid/graphics/Canvas;','Landroid/graphics/pdf/PdfDocument;']))
    check('Native animation and camera referenced',all(t in types for t in ['Landroid/animation/ValueAnimator;','Landroid/hardware/Camera;','Landroid/view/SurfaceView;']))
    check('Native implementation class included','Lcom/mvt/tbank/MainActivity;'in definitions and'Lcom/mvt/tbank/NativeScreens;'in definitions)
    check('ZXing core included','Lcom/google/zxing/MultiFormatReader;'in definitions)
    check('JVM org.json not bundled',not any(t.startswith('Lorg/json/')for t in definitions))
    check('Signing private keys not bundled',not any(n.lower().endswith(('.p12','.jks','.keystore'))for n in files))
    check('No reference videos or screenshots bundled',not any(n.lower().endswith(('.mp4','.mov','.mkv','.webm'))or'reference-video'in n or'screenshot'in n.lower()for n in files))
    current=ROOT/'.cache/apk-build/dex/classes.dex';check('APK contains latest compiled DEX',current.exists()and data==current.read_bytes())
    seed=json.loads(archive.read('assets/seed.json'))
    check('Fictional contact phone set',all('(000)'in c['phone']for c in seed['contacts']))
    check('Only approved art, seed, fonts, locales and client Firebase config in assets',all(n in {'assets/seed.json','assets/firebase-config.json'}or n.startswith(('assets/art/','assets/licenses/','assets/fonts/','assets/locales/'))for n in files if n.startswith('assets/')))
    check('Eleven native Roboto weights included',all('assets/fonts/roboto-'+str(w)+'.ttf'in files for w in [300,350,400,450,500,600,650,680,700,750,800]))
    check('Roboto open font license included','assets/licenses/ROBOTO-OFL.txt'in files)
    check('Restored legacy native screens compiled','Lcom/mvt/tbank/LegacyScreens;'in definitions)

all_java='\n'.join(p.read_text()for p in(ROOT/'src').rglob('*.java'))
refs=set(re.findall(r'"([\w-]+\.webp)"',all_java));refs.update('bonus-partner-'+str(i)+'.webp'for i in range(1,4));refs.discard('profile-avatar.webp')
missing=[n for n in refs if not(ROOT/'assets/art'/n).exists()];check('All native artwork resources exist',not missing,', '.join(missing))
candidates={n for n in re.findall(r'"([A-Z][A-Za-z0-9]{2,40})"','\n'.join(p.read_text()for p in(ROOT/'src').rglob('*.java')if p.name!='NativeWords.java'))if not n.isupper()};non_icons={'Android','AvatarImport','BEAUTY17','BONUS500','Black','Chat','City','English','Explore','Home','JUNIOR','PAY','PRO','Payments','WELCOME10','BALN','NORD','AndroidKeyStore','PBKDF2WithHmacSHA256','SHA256','ETag','Kaspersky'}
known={p.stem[3:]for p in(ROOT/'res/drawable').glob('ic_*.xml')};missing=sorted(n for n in candidates-non_icons if n.lower()not in known);check('No missing icon fallback candidates',not missing,', '.join(missing))
screens=(ROOT/'src/com/mvt/tbank/NativeScreens.java').read_text();dispatch=screens[screens.index('public Scene render('):screens.index('Scene account(')];routes=set(re.findall(r'case "([\w-]+)"',dispatch))
known_routes=routes|{'card-details','card-transfer','contract-transfer'}
navigated=set(re.findall(r'\b(?:nav|tab)\s*\(\s*"([\w-]+)"\s*[,)]',all_java));navigated.update(n['route']for n in seed['state']['notifications']);unknown=sorted(navigated-known_routes);check('Literal and seeded routes resolve',not unknown,', '.join(unknown))
check('No transfer review or confirmation route',not(routes&{'transfer-review','transfer-confirm','transfer-confirmation','review-transfer','confirm-transfer'}))
check('Direct form execution is wired','a.execute(request,submit,error)'in re.sub(r'\s+','',screens))
main=(ROOT/'src/com/mvt/tbank/MainActivity.java').read_text();check('Busy guard and durable local operation','if(busy||gateOpen)return;'in re.sub(r'\s+','',main) and'saveNow()'in main and'pendingResult'in main)
check('Startup acknowledgement gate implemented','private View disclaimer()'in main and'gateOpen=false'in re.sub(r'\s+','',main))
check('Logout clears navigation root','public void logout()'in main and'stack.clear();stack.add(newRoute("login",null))'in re.sub(r'\s+','',main))
check('Exported PDFs retain invalid-sample mark','Образец, недействительно'in(ROOT/'src/com/mvt/tbank/NativeDocuments.java').read_text())
check('Deleted private reference cache absent',not(ROOT.parent/'.cache/reference-video-v3').exists())
ui=(ROOT/'src/com/mvt/tbank/NativeUi.java').read_text();store=(ROOT/'src/com/mvt/tbank/NativeStore.java').read_text();legacy=(ROOT/'src/com/mvt/tbank/LegacyScreens.java').read_text()
check('Roboto is loaded from native assets','Typeface.createFromAsset'in ui and'fonts/roboto-'in ui)
check('Intrinsic native label bounds are explicit','t.setLayoutParams(new LinearLayout.LayoutParams(-2, -2))'in ui)
check('Native preference file preserved','local-bank-native-v2'in store)
check('Account balance is the restored compact native summary','legacy-account-balance'in legacy and re.search(r'24,\s*u\.text,\s*650',legacy)is not None)
check('Card settings is a real native navigation route','case "card-details"'in dispatch and'"card-details".equals(name)) {\n      screens.cardDetails'not in main)
check('Private screenshot originals removed',not list((ROOT.parent/'uploads').glob('Screenshot_20261022-*.png')))

check('New native menu, panel and portfolio classes compiled',all('Lcom/mvt/tbank/'+n+';'in definitions for n in ['ReferenceMenus','NativePanel','PortfolioEngine']))
check('All additional native menu routes are dispatched',len(routes)>=96 and {'cashback-month','cashback-limits','cashback-offers','shopping','shopping-catalog','shopping-product','shopping-address','investments','referral-product','monthly-statement'}.issubset(routes))
panel=(ROOT/'src/com/mvt/tbank/NativePanel.java').read_text()
check('Native card gestures wait for measured geometry','NativeUi.afterLayout'in panel and'onInterceptTouchEvent'in panel and'setOffset(downOffset + dy)'in panel)
portfolio=(ROOT/'src/com/mvt/tbank/PortfolioEngine.java').read_text()
check('Portfolio arithmetic is integer-only and duplicate guarded','Math.multiplyExact'in portfolio and'BankEngine.transaction(source, id)'in portfolio and re.search(r'\b(?:double|float)\b',portfolio)is None)
category_ids=['clothes','beauty','jewels','electronics','auto','children','hobby','home','sport','repair','furniture','appliances','cleaning']
new_art=['category-'+n+'.webp'for n in category_ids]+['market-'+n+'.webp'for n in ['dryer','pillow','ssd','pillow-soft']]+['referral-'+n+'.webp'for n in ['black','platinum','mobile','business']]
check('Additional dynamic artwork sets are complete',all((ROOT/'assets/art'/n).exists()for n in new_art))
check('Second private recording and frame cache removed',not(ROOT.parent/'.cache/reference-motion-next').exists())

check('Package matches supplied Firebase Android client','package="com.mvt.tbank"'in(ROOT/'AndroidManifest.xml').read_text()and json.loads((ROOT/'assets/firebase-config.json').read_text())['packageName']=='com.mvt.tbank')
check('Real native access and cloud classes compiled',all('Lcom/mvt/tbank/'+n+';'in definitions for n in ['NativeAccess','PinCrypto','NativeIdentity','NativeFirebase','FirebaseRest','NativeVault','CloudSnapshot','AccountTools','CurrencyEngine','DepositEngine','NativeNextMenus']))
access=(ROOT/'src/com/mvt/tbank/NativeAccess.java').read_text();identity=(ROOT/'src/com/mvt/tbank/NativeIdentity.java').read_text();wire=(ROOT/'src/com/mvt/tbank/FirebaseRest.java').read_text();vault=(ROOT/'src/com/mvt/tbank/NativeVault.java').read_text();snapshot=(ROOT/'src/com/mvt/tbank/CloudSnapshot.java').read_text()
check('Launch notice is installation-scoped','identity.accepted()'in main and'noticeAccepted'in identity)
check('Old accept-any-code entry removed','Для входа подойдёт любой четырёхзначный код'not in screens and'Войти без кода'not in screens and'PinCrypto.verify'in access)
check('PIN verification salted and constant-time','PBKDF2WithHmacSHA256'in(ROOT/'src/com/mvt/tbank/PinCrypto.java').read_text()and'MessageDigest.isEqual'in(ROOT/'src/com/mvt/tbank/PinCrypto.java').read_text())
check('Permanent numeric profile ID is persisted','number'in identity and'SecureRandom'in identity and'900000000000L'in identity)
check('Refresh session uses Android Keystore AES-GCM','AndroidKeyStore'in vault and'AES/GCM/NoPadding'in vault and'GCMParameterSpec'in vault)
check('Backup strips secrets and preserves exact JSON',all(k in snapshot for k in ['scrub','stateJson','pinhash','refreshtoken']))
check('Public RTDB access is detected before a state write','assertPrivate'in wire and'PUBLIC_DATABASE_RULES'in wire and'If-Match'in wire)
check('Closed per-user RTDB rules supplied','auth.uid === $uid'in(ROOT/'firebase/database.rules.json').read_text()and'".read": false'in(ROOT/'firebase/database.rules.json').read_text())
check('Native press animations installed','StateListAnimator'in ui and'pressMotion(b)'in ui and'scaleX'in ui)
check('Adaptive and monochrome launcher resources supplied',(ROOT/'res/mipmap-anydpi-v26/ic_launcher.xml').exists()and(ROOT/'res/mipmap-anydpi-v33/ic_launcher.xml').exists())
check('English UI resource catalog supplied',len(json.loads((ROOT/'assets/locales/en.json').read_text()))>=450 and'NativeWords.text'in ui)
check('Third-reference private recording and screenshots removed',not(ROOT.parent/'.cache/reference-2.3').exists()and not list((ROOT.parent/'uploads').glob('Screenshot_20261023-05*.png')))

metadata=[]
for image in(ROOT/'assets/art').iterdir():
    with Image.open(image)as im:
        if im.info.get('exif')or im.info.get('xmp'):metadata.append(image.name)
check('Artwork contains no EXIF/XMP blocks',not metadata,', '.join(metadata))
report={'apk':APK.name,'version':'2.3.0','versionCode':6,'checkedOn':'2026-10-23','sizeBytes':APK.stat().st_size,'sha256':hashlib.sha256(APK.read_bytes()).hexdigest(),'certificateSha256':certificate,'routeCount':len(routes),'nativeClassCount':sum(t.startswith('Lcom/mvt/tbank/')for t in definitions),'checks':checks,'passed':sum(x['passed']for x in checks),'total':len(checks),'limitations':['Static APK/source checks, not Android runtime tests.','Headless API-28 native graphics UI suite is recorded separately; not a device/emulator.','Camera hardware, OEM/system appearance, sensors and exported PDF files still require device checks.']}
(ROOT/'qa/apk-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(ROOT/'qa/apk-checks.txt').write_text('\n'.join(('PASS 'if c['passed']else'FAIL ')+c['name']for c in checks)+'\n')
print('TOTAL',report['passed'],'/',report['total'],'static checks; native routes:',len(routes))
raise SystemExit(0 if report['passed']==report['total']else 1)
