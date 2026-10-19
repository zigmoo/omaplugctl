import json,os,pathlib,random,statistics,subprocess,time,shutil,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=pathlib.Path(sys.argv[1]).resolve();BASE.mkdir(parents=True,exist_ok=True)
if not (pathlib.Path(os.environ.get("XDG_STATE_HOME",str(pathlib.Path.home()/".local/state")))/"omarchy/omaplugctl/marketplace.json").is_file():raise SystemExit("Open Install and Refresh its catalog before measuring cached-catalog reads.")
runtimes={"python":[sys.executable,"-B"],"php":["php","-n"]}
controllers={"python":runtimes["python"]+[str(ROOT/"controller.py")],"php":runtimes["php"]+[str(ROOT/"controller.php")]}
def env_for(label):
 root=BASE/label/"omarchy/omaplugctl";root.mkdir(parents=True,exist_ok=True)
 source=pathlib.Path(os.environ.get("XDG_STATE_HOME",str(pathlib.Path.home()/".local/state")))/"omarchy/omaplugctl"
 for name in ("authors.json","updates.json","marketplace.json"):
  if (source/name).exists():shutil.copyfile(source/name,root/name)
 if (source/"clamav").exists() and not (root/"clamav").is_symlink():(root/"clamav").symlink_to(source/"clamav")
 return dict(os.environ,XDG_STATE_HOME=str(BASE/label))
envs={label:env_for(label) for label in controllers}
randomizer=random.Random(3008)
result={"environment":{},"runs":{},"summaries":{}}
result["environment"]["python"]=subprocess.check_output([sys.executable,"--version"],text=True).strip()
result["environment"]["php"]=subprocess.check_output(["php","-n","-r","echo PHP_VERSION;"],text=True).strip()
for workload,count in (("startup",25),("settings",25),("list",9),("catalog",9)):
 timings={label:[] for label in controllers};outputs={}
 def command(label):
  if workload=="startup":return runtimes[label]+(["-c","import json;print(json.dumps(dict(ok=True)))"] if label=="python" else ["-r",'echo json_encode(["ok"=>true]);'])
  return controllers[label]+[workload]
 for label in controllers:
  warm=subprocess.run(command(label),env=envs[label],capture_output=True,text=True,check=True);outputs[label]=json.loads(warm.stdout)
 if outputs["python"]!=outputs["php"]:
  (BASE/(workload+"-python.json")).write_text(json.dumps(outputs["python"],indent=2));(BASE/(workload+"-php.json")).write_text(json.dumps(outputs["php"],indent=2));raise SystemExit("Parity failed for "+workload)
 for sample in range(count):
  order=list(controllers);randomizer.shuffle(order)
  for label in order:
   start=time.perf_counter_ns();run=subprocess.run(command(label),env=envs[label],capture_output=True,text=True,check=True);elapsed=(time.perf_counter_ns()-start)/1e6
   if run.stderr:raise RuntimeError(run.stderr)
   if json.loads(run.stdout)!=outputs[label]:raise RuntimeError("Output changed for "+workload)
   timings[label].append(elapsed)
 result["runs"][workload]=timings
 result["summaries"][workload]={label:{"median_ms":round(statistics.median(values),2),"min_ms":round(min(values),2),"max_ms":round(max(values),2),"samples":len(values)} for label,values in timings.items()}
 if workload=="list":result["environment"]["bar_plugins"]=len(outputs["php"]["plugins"])
 if workload=="catalog":result["environment"]["catalog_entries"]=len(outputs["php"]["entries"])
 (BASE/"results.json").write_text(json.dumps(result,indent=2));print(workload,result["summaries"][workload],flush=True)
