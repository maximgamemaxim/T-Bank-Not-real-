#!/usr/bin/env python3
"""Run the optional Robolectric/native-Skia suite after build_apk.py succeeds.

Requires JDK 11+, Android SDK 35, and Maven 3.8+. Test-only dependencies are
cached outside deliverables. A fresh cache downloads several hundred MB.
No emulator, physical device, Node, WebView or bank network is involved.
"""
import hashlib
import io
import json
import signal
import time
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("NATIVE_TEST_CACHE", ROOT / ".cache" / "ui-native")).resolve()
CLASSES = ROOT / ".cache" / "apk-build" / "classes"
MAVEN = os.environ.get("MAVEN") or shutil.which("mvn")
SDK = Path(os.environ.get("ANDROID_SDK_ROOT", os.environ.get("ANDROID_HOME", "/missing-sdk"))).resolve()
CENTRAL = "https://repo.maven.apache.org/maven2/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def checked_file(path, url, expected, aar=False):
    if path.exists() and sha(path.read_bytes()) == expected:
        return
    print("Test dependency:", url, flush=True)
    data = fetch(url)
    if aar:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = archive.read("classes.jar")
    if sha(data) != expected:
        raise RuntimeError("Dependency checksum mismatch: " + url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    if not MAVEN:
        sys.exit("Install Maven and set MAVEN or add mvn to PATH.")
    if not (SDK / "platforms/android-35/android.jar").exists():
        sys.exit("Set ANDROID_SDK_ROOT to an Android SDK with platform 35.")
    compiled = sorted(CLASSES.rglob("*.class"))
    if len(compiled) < 30 or not (ROOT / ".cache/apk-build/resources.apk").exists():
        sys.exit("First successfully run build_apk.py; compiled app classes/resources are required.")
    newest_source = max(path.stat().st_mtime for path in (ROOT / "src").rglob("*.java"))
    if newest_source > max(path.stat().st_mtime for path in compiled):
        sys.exit("Source changed after compilation. Rebuild the APK before running UI tests.")
    CACHE.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(CACHE / "native-classes.jar", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in compiled:
            archive.write(path, path.relative_to(CLASSES).as_posix())

    framework = "android-all-instrumented-9-robolectric-4913185-2-i4.jar"
    checked_file(
        CACHE / "sdk" / framework,
        CENTRAL + "org/robolectric/android-all-instrumented/9-robolectric-4913185-2-i4/" + framework,
        "50c0a262b8208c282a58053cdd14a77e8aa0aa87eddab2ee4f84673865daf9e3",
    )
    google = "https://dl.google.com/dl/android/maven2/"
    checked_file(
        CACHE / "monitor.jar", google + "androidx/test/monitor/1.6.1/monitor-1.6.1.aar",
        "73ad2cd1a0d51b9caad6b341172c555319f5ae4eb96c7e729329815550e2eb6e", aar=True,
    )
    checked_file(
        CACHE / "espresso.jar",
        google + "androidx/test/espresso/espresso-idling-resource/3.5.1/espresso-idling-resource-3.5.1.aar",
        "fb6f0102c0575efdb73be96970be118aaf6eb8468cd0581d04ee5d81807ab8bc", aar=True,
    )
    source = (ROOT / "src/com/mvt/tbank/NativeScreens.java").read_text()
    dispatch = source.split("Scene render(", 1)[1].split("LinearLayout body()", 1)[0]
    routes = sorted(set(re.findall(r'case "([a-z0-9-]+)"', dispatch)))
    (ROOT / "qa/android-ui/routes.txt").write_text("\n".join(routes) + "\n")
    env = dict(os.environ, BANK_NATIVE_ROOT=str(ROOT), NATIVE_TEST_CACHE=str(CACHE), ANDROID_SDK_ROOT=str(SDK))
    env.setdefault("MAVEN_OPTS", "-Dhttps.protocols=TLSv1.2")
    # Separate small test batches prevent native Skia and JVM heaps from exhausting a 2GB host.
    (CACHE / "runtime-tmp").mkdir(parents=True,exist_ok=True)
    methods=re.findall(r"@Test\s+public void (\w+)\(", (ROOT/"qa/android-ui/src/com/mvt/tbank/NativeLayoutTest.java").read_text())
    selected=os.environ.get("NATIVE_UI_TEST_FILTER","")
    if selected:methods=[m for m in methods if re.search(selected,m)]
    if not methods:sys.exit("No UI test methods selected")
    size=max(1,int(os.environ.get("NATIVE_UI_BATCH_SIZE","8")))
    batches=[];batch=[]
    for method in methods:
        isolated=bool(re.search("^pin|Pin|backgroundLock|warningIsShown|numericIdentity",method))
        if isolated:
            if batch:batches.append(batch);batch=[]
            batches.append([method])
        else:
            batch.append(method)
            if len(batch)>=size:batches.append(batch);batch=[]
    if batch:batches.append(batch)
    cases=[];totals={"tests":0,"failures":0,"errors":0,"skipped":0,"time":0.0}
    checkpoint_path=ROOT/("qa/native-ui-progress-selected.json"if selected else"qa/native-ui-progress.json")
    if os.environ.get("NATIVE_UI_RESUME")=="1"and checkpoint_path.exists():
        old=json.loads(checkpoint_path.read_text())
        if old.get("appClassesSha256")==sha((CACHE/"native-classes.jar").read_bytes())and old.get("resourceApkSha256")==sha((ROOT/".cache/apk-build/resources.apk").read_bytes()):
            totals=old["totals"]
            for case in old["cases"]:cases.append(ET.Element("testcase",{"name":case["name"],"time":str(case["seconds"])}))
            done={c.attrib["name"]for c in cases}
            batches=[[method for method in batch if method not in done]for batch in batches]
            batches=[batch for batch in batches if batch]
            print("Resuming",len(cases),"successful cases from identical classes/resources",flush=True)
    env["MAVEN_OPTS"]=env.get("MAVEN_OPTS","")+" -Xmx192m -Djava.io.tmpdir="+str(CACHE/"runtime-tmp")
    for index,batch in enumerate(batches):
        print("Native batch",index+1,"/",len(batches),":",", ".join(batch),flush=True)
        process=subprocess.Popen([MAVEN,"-B","-f",str(ROOT/"qa/android-ui/pom.xml"),"-Dmaven.repo.local="+str(CACHE/"m2"),"-Dtest=NativeLayoutTest#"+"+".join(batch),"test"],cwd=ROOT,env=env,start_new_session=True)
        began=time.monotonic();guarded=False
        while process.poll()is None:
            available=10**9
            try:available=int(next(line for line in Path("/proc/meminfo").read_text().splitlines()if line.startswith("MemAvailable:")).split()[1])
            except (OSError,StopIteration,ValueError):pass
            if available<180000 or time.monotonic()-began>75:
                print("UI safety guard:",available,"kB available,",round(time.monotonic()-began,1),"seconds",flush=True)
                java=[]
                for entry in Path("/proc").iterdir():
                    if not entry.name.isdigit():continue
                    try:
                        cmd=(entry/"cmdline").read_bytes()
                        if(entry/"comm").read_text().strip()=="java"and(b"surefirebooter"in cmd or b"maven.multiModuleProjectDirectory"in cmd):
                            pid=int(entry.name);java.append(pid);print("Guarded JVM",pid,(entry/"status").read_text().split("VmRSS:",1)[-1].splitlines()[0],flush=True);os.kill(pid,signal.SIGQUIT)
                    except (OSError,ProcessLookupError):pass
                time.sleep(.15)
                for pid in java:
                    try:os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait();guarded=True
                print("UI safety guard stopped batch; no test success claimed",flush=True);break
            time.sleep(.05)
        report=ROOT/"qa/android-ui/target/surefire-reports/TEST-com.mvt.tbank.NativeLayoutTest.xml"
        if guarded or process.returncode:sys.exit(1)
        part=ET.parse(report).getroot()
        for key in totals:totals[key]+=float(part.attrib[key])if key=="time"else int(part.attrib[key])
        cases.extend(part.findall("testcase"))
        checkpoint={"version":"2.3.0","appClassesSha256":sha((CACHE/"native-classes.jar").read_bytes()),"resourceApkSha256":sha((ROOT/".cache/apk-build/resources.apk").read_bytes()),"cases":[{"name":c.attrib["name"],"seconds":float(c.attrib["time"])}for c in cases],"totals":totals,"complete":False}
        checkpoint_path.write_text(json.dumps(checkpoint,indent=2)+"\n")
    xml=ET.Element("testsuite",{k:str(v)for k,v in totals.items()})
    xml.extend(cases)
    summary = {
        "scope": "Robolectric 4.11.1; API 28; actual Android Views + native Skia; not a device/emulator",
        "version": "2.3.0", "appClassesSha256": sha((CACHE / "native-classes.jar").read_bytes()),
        "resourceApkSha256": sha((ROOT / ".cache/apk-build/resources.apk").read_bytes()), "tests": int(xml.attrib["tests"]),
        "failures": int(xml.attrib["failures"]), "errors": int(xml.attrib["errors"]),
        "skipped": int(xml.attrib["skipped"]), "seconds": float(xml.attrib["time"]),
        "renderSizePixels": [720, 1456], "constructedRoutes": routes,
        "cases": [{"name": case.attrib["name"], "seconds": float(case.attrib["time"])}
                  for case in xml.findall("testcase")],
        "limits": ["No physical camera, sensors or Android system-integration checks",
                   "Native render snapshots are not phone screenshots",
                   "Render/geometry checks do not prove pixel-identical appearance on every Android"],
    }
    if selected:
        output=ROOT/"qa/native-ui-selected.json"
    else:
        output=ROOT/"qa/native-ui-tests.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("Native UI tests:", summary["tests"], "passed; routes:", len(routes))


if __name__ == "__main__":
    main()
