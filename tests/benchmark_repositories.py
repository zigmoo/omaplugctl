import json,os,pathlib,random,statistics,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];BASE=pathlib.Path(sys.argv[1]).resolve();BASE.mkdir(parents=True,exist_ok=True)
FIX=BASE/"repositories";FIX.mkdir(exist_ok=True)
def git(*args):return subprocess.check_output(["git",*map(str,args)],stderr=subprocess.DEVNULL,text=True).strip()
remote=FIX/"origin.git";writer=FIX/"writer"
if not remote.exists():
 git("init","--bare","--initial-branch=master",remote);git("init","--initial-branch=master",writer)
 git("-C",writer,"config","user.name","Benchmark Author");git("-C",writer,"config","user.email","benchmark@example.invalid")
 (writer/"manifest.json").write_text('{"id":"benchmark.widget"}');(writer/"Widget.qml").write_text("initial")
 git("-C",writer,"add",".");git("-C",writer,"commit","-m","Initial fixture");git("-C",writer,"remote","add","origin",remote);git("-C",writer,"push","-u","origin","master")
 for i in range(16):git("clone",remote,FIX/("installed-"+str(i)))
 (writer/"Widget.qml").write_text("remote update");git("-C",writer,"add",".");git("-C",writer,"commit","-m","Fixture update");git("-C",writer,"push")
plugins=[{"id":"fixture."+str(i),"firstParty":False,"clonedFrom":""} for i in range(16)]
metadata={p["id"]:{"sourceDir":str(FIX/("installed-"+str(i))),"manifestPath":str(FIX/("installed-"+str(i))/"manifest.json")} for i,p in enumerate(plugins)}
request={"function":"Updates\\check_all","args":[plugins,metadata]};(BASE/"repository-input.json").write_text(json.dumps(request))
python_code="import json,sys;sys.path.insert(0,"+repr(str(ROOT))+");import updates;r=json.load(sys.stdin);print(json.dumps(updates.check_all(*r['args'])))"
commands={"python":[sys.executable,"-B","-c",python_code],"php":["php","-n",str(ROOT/"tests/php_bridge.php")]}
envs={k:dict(os.environ,XDG_STATE_HOME=str(BASE/("repo-state-"+k))) for k in commands}
body=json.dumps(request)
def invoke(label):
 p=subprocess.run(commands[label],input=body,text=True,capture_output=True,env=envs[label],check=True)
 if p.stderr:raise RuntimeError(p.stderr)
 value=json.loads(p.stdout)
 if label=="php":value=value["result"]
 for row in value.values():row.pop("checkedAt",None)
 return value
outputs={k:invoke(k) for k in commands};assert outputs["php"]==outputs["python"]
randomizer=random.Random(3008);times={k:[] for k in commands}
for i in range(9):
 order=list(commands);randomizer.shuffle(order)
 for label in order:
  start=time.perf_counter_ns();value=invoke(label);elapsed=(time.perf_counter_ns()-start)/1e6
  assert value==outputs[label];times[label].append(elapsed)
result={"repos":16,"fetch_concurrency":4,"remote_kind":"local bare Git; no network","samples":times,"summary":{k:{"median_ms":round(statistics.median(v),2),"min_ms":round(min(v),2),"max_ms":round(max(v),2)} for k,v in times.items()}}
(BASE/"repository-results.json").write_text(json.dumps(result,indent=2));print(json.dumps(result["summary"]),flush=True)
