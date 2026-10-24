#!/usr/bin/env python3
"""Optional, local-only 2.2 -> com.mvt.tbank transfer helper. Never changes the old app's data.
Requires the previously delivered frozen 2.2 source ZIP and the same signing key.
"""
from pathlib import Path
import os,sys,zipfile,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path(sys.argv[1]).resolve()if len(sys.argv)>1 else ROOT.parent/'TBank-Native-2.2-source.zip'
OUTPUT=Path(sys.argv[2]).resolve()if len(sys.argv)>2 else ROOT.parent/'TBank-2.2-export.apk'
WORK=ROOT/'.cache/legacy-export'
if not ARCHIVE.exists():raise SystemExit('Supply the frozen TBank-Native-2.2-source.zip')
if WORK.exists():shutil.rmtree(WORK)
WORK.mkdir(parents=True)
with zipfile.ZipFile(ARCHIVE)as z:
 for entry in z.infolist():
  rel=Path(entry.filename)
  if rel.is_absolute()or'..'in rel.parts:raise ValueError('Unsafe source archive')
 z.extractall(WORK)
project=WORK/'t-bank-native';src=project/'src/ai/arena/bankdemo'
p=project/'AndroidManifest.xml';s=p.read_text().replace('versionCode="5"','versionCode="6"').replace('versionName="2.2.0"','versionName="2.2.1"').replace('android:label="Т-Банк"','android:label="Т-Банк · перенос"');p.write_text(s)
p=src/'NativeScreens.java';s=p.read_text();start=s.index('  Scene dataAccess(');at=s.index('    LinearLayout b = body();',start)+len('    LinearLayout b = body();');s=s[:at]+'''
    b.addView(u.button("Экспорт для переноса в новое приложение",false,this::exportLegacyProfile));
    gap(b,20);
'''+s[at:]
start=s.index('  Scene settings(');at=s.index('    LinearLayout b = body();',start)+len('    LinearLayout b = body();');s=s[:at]+'\n    b.addView(u.button("Экспорт для переноса в новое приложение",false,this::exportLegacyProfile));\n    gap(b,20);\n'+s[at:]
at=s.index('  Scene help(');s=s[:at]+'''
  String backupDigest(String value)throws Exception{byte[] bytes=java.security.MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format(java.util.Locale.US,"%02x",b&255));return out.toString();}
  void exportLegacyProfile(){try{JSONObject data=BankEngine.object(a.store.state.toString());data.remove("locked");data.remove("pendingResult");String raw=data.toString();JSONObject backup=obj("schema",1,"revision",0,"stateJson",raw,"sha256",backupDigest(raw),"sourcePackage","ai.arena.bankdemo");java.io.File avatar=new java.io.File(a.getFilesDir(),"profile-avatar.webp");if(avatar.exists()){String image=java.util.Base64.getEncoder().encodeToString(java.nio.file.Files.readAllBytes(avatar.toPath()));put(backup,"avatar",obj("mime","image/webp","base64",image,"sha256",backupDigest(image)));}a.download("tbank-legacy-profile.json",backup.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8),"application/json");}catch(Exception e){a.toast("Не удалось подготовить копию");}}

'''+s[at:];p.write_text(s)
p=src/'MainActivity.java';p.write_text(p.read_text().replace('2.2.0','2.2.1'))
env={**os.environ,'BANK_SIGNING_KEY':str(ROOT/'android/.signing/demo-signing.p12')}
subprocess.run([sys.executable,str(project/'build_apk.py'),str(OUTPUT)],cwd=project,env=env,check=True)
print('Optional legacy export helper:',OUTPUT)
