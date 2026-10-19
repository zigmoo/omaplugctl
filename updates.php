<?php
declare(strict_types=1);
namespace OmaPlugCtl\Updates;
use function OmaPlugCtl\{state_root,json_file,save_json,raw_run,run,locked,relative_path,now,process_result,ensure_directory};

function git(string $directory,array $args,int $timeout=10,?string $body=null,bool $raw=false): string {
    $env=[...getenv(),'GIT_TERMINAL_PROMPT'=>'0','GIT_SSH_COMMAND'=>'ssh -oBatchMode=yes -oConnectTimeout=7'];
    try { $value=raw_run(['git','-C',$directory,...$args],$timeout,$body,$env,67108864);return $raw?$value:trim($value); }
    catch (\Throwable $error) { throw new \RuntimeException('Could not read or contact the source repository.',0,$error); }
}
function cache_path(): string { return state_root().'/updates.json'; }
function load_cache(): array { $value=json_file(cache_path());return is_array($value)?$value:[]; }
function save_cache(array $value,?string $path=null): void { save_json($value,$path??cache_path()); }
function operations(): array {
    $result=[];
    foreach(glob(state_root().'/operations/*.json')?:[] as $file) { $value=json_file($file,null,8192);if(is_array($value)&&is_string($value['plugin']??null))$result[$value['plugin']]=$value; }
    return $result;
}
function save_operation(string $id,array $fields): void { save_json([...$fields,'plugin'=>$id,'changedAt'=>now()],state_root().'/operations/'.hash('sha256',$id).'.json'); }
function source(array $plugin,array $metadata): ?array {
    $directory=$metadata['sourceDir']??'';
    if (!is_string($directory)||!is_dir($directory)) return null;
    $first=!empty($plugin['firstParty'])&&empty($plugin['clonedFrom']);
    if (!$first&&!file_exists($directory.'/.git')) return null;
    try {
        $root=realpath(git($directory,['rev-parse','--show-toplevel']));
        if (!$root || (!$first&&$root!==realpath($directory))) return null;
        $remote=git($root,['remote','get-url','origin']);$head=git($root,['rev-parse','HEAD']);$branch=git($root,['branch','--show-current']);
        $target='HEAD';$tracking=false;
        try { $target=git($root,['config','--get','branch.'.$branch.'.merge']);$tracking=$branch!==''&&git($root,['config','--get','branch.'.$branch.'.remote'])==='origin'&&str_starts_with($target,'refs/heads/'); } catch(\Throwable) {}
        if(!$tracking)$target='HEAD';
        return ['root'=>$root,'head'=>$head,'target'=>$target,'identity'=>hash('sha256',$root."\n".$remote."\n".$target."\n".$branch),'branch'=>$branch,'tracking'=>$tracking,'kind'=>$first?'omarchy':'plugin','dirty'=>git($root,['status','--porcelain','--untracked-files=normal'])!==''];
    } catch(\Throwable) { return null; }
}
function cached_status(array $plugin,array $metadata,array $cache): array {
    $info=source($plugin,$metadata);
    if($info===null)return ['status'=>!empty($plugin['firstParty'])?'system':'local','canUpdate'=>false];
    $value=$cache[$plugin['id']]??[];
    if(!is_array($value)||($value['identity']??'')!==$info['identity']||($value['head']??'')!==$info['head'])return ['status'=>'unchecked','kind'=>$info['kind'],'canUpdate'=>false];
    if(($value['status']??'')==='current') {
        $stamp=is_string($value['checkedAt']??null)?strtotime($value['checkedAt']):false;
        if($stamp===false||time()-$stamp>86400)return ['status'=>'unchecked','kind'=>$info['kind'],'canUpdate'=>false];
    }
    $value['dirty']=$info['dirty'];$value['canUpdate']=in_array($value['status']??'',['available','rewritten'],true)&&!$info['dirty']&&$info['tracking']&&$info['kind']==='plugin';
    if(in_array($value['status']??'',['available','rewritten','diverged'],true)&&!empty($value['remoteHead'])&&empty($value['latestDate']))try{$value=[...$value,...update_details($info,$value['remoteHead'],$metadata)];}catch(\Throwable){}
    return $value;
}
function plugin_paths(array $metadata,string $root): array {
    $manifest=$metadata['manifestPath'];$directory=dirname($manifest);
    if(basename($manifest)==='manifest.json')$paths=[$directory];
    else {
        $document=json_file($manifest);$paths=[$manifest];
        foreach(($document['entryPoints']??[]) as $entry)if(is_string($entry))$paths[]=$directory.'/'.$entry;
        foreach(($document['omarchy']['clonePaths']??[]) as $entry)if(is_array($entry)&&is_string($entry['source']??null))$paths[]=$directory.'/'.$entry['source'];
    }
    return array_map(fn($path)=>relative_path($path,$root),$paths);
}
function fetch_source(array $info): string { git($info['root'],['fetch','--quiet','--no-tags','origin',$info['target']],12);return git($info['root'],['rev-parse','FETCH_HEAD']); }
function update_details(array $info,string $remote,array $metadata): array {
    $args=['log','--max-count=3','--format=%cs%x1f%s',$info['head'].'..'.$remote];
    if($info['kind']==='omarchy')$args=[...$args,'--',...plugin_paths($metadata,$info['root'])];
    $notes=[];$date='';
    foreach(explode("\n",git($info['root'],$args))as$row) { $parts=explode("\x1f",$row,2);if(count($parts)===2){$date=$date?:$parts[0];$notes[]=\OmaPlugCtl\shorten($parts[1],240);} }
    return ['latestDate'=>$date,'notes'=>$notes];
}
function equivalent_history(array $info,string $remote): bool {
    $root=$info['root'];$head=$info['head'];$local=array_filter(explode("\n",git($root,['rev-list',$head,'--not',$remote])));
    if(!$local||git($root,['rev-list','--merges',$head,'--not',$remote])!=='')return false;
    $patches=function($tip,$exclude)use($root) {
        $text=git($root,['log','--no-merges','--pretty=medium','--patch','--binary','--full-index','--no-ext-diff','--no-textconv','--no-renames',$tip,'--not',$exclude],30,null,true);
        $result=[];foreach(explode("\n",git($root,['patch-id','--verbatim'],30,$text))as$row) { $parts=preg_split('/\s+/',trim($row));if(count($parts)===2)$result[$parts[1]]=$parts[0]; }return $result;
    };
    $installed=$patches($head,$remote);$ids=array_keys($installed);sort($ids);sort($local);if($ids!==$local)return false;
    $upstream=array_count_values(array_values($patches($remote,$head)));
    foreach(array_count_values(array_values($installed))as$patch=>$count)if(($upstream[$patch]??0)<$count)return false;
    return true;
}
function compare_source(array $info,string $remote,array $metadata): array {
    [$ahead,$behind]=array_map('intval',preg_split('/\s+/',git($info['root'],['rev-list','--left-right','--count',$info['head'].'...'.$remote])));
    $status=$ahead&&$behind?'diverged':($ahead?'ahead':($behind?'available':'current'));
    if($status==='diverged'&&$info['kind']==='plugin'&&equivalent_history($info,$remote))$status='rewritten';
    if($status==='available'&&$info['kind']==='omarchy'&&git($info['root'],['diff','--name-only',$info['head'],$remote,'--',...plugin_paths($metadata,$info['root'])])==='')$status='current';
    $details=in_array($status,['available','rewritten','diverged'],true)?update_details($info,$remote,$metadata):[];
    return [...$info,...$details,'status'=>$status,'remoteHead'=>$remote,'checkedAt'=>now(),'canUpdate'=>in_array($status,['available','rewritten'],true)&&!$info['dirty']&&$info['tracking']&&$info['kind']==='plugin'];
}
function unchanged(?array $current,array $before): bool { return $current!==null&&$current['identity']===$before['identity']&&$current['head']===$before['head']&&!$current['dirty']; }
function apply_update(array $plugin,array $metadata,bool $scan=true): array {
    $initial=source($plugin,$metadata);
    if(!$initial||$initial['kind']!=='plugin')throw new \RuntimeException('This plugin is updated with Omarchy, not an independent plugin Git checkout.');
    return locked(state_root().'/update-'.hash('sha256',$initial['root']).'.lock',function()use($initial,$plugin,$metadata,$scan){
        $before=source($plugin,$metadata);
        if(!$before||$before['identity']!==$initial['identity'])throw new \RuntimeException('The running plugin source changed. Refresh before updating.');
        if($before['dirty'])throw new \RuntimeException('Local changes block this update; your files were preserved.');
        if(!$before['tracking'])throw new \RuntimeException('Choose an attached branch tracking origin before updating this plugin.');
        $remote=fetch_source($before);
        if(!unchanged(source($plugin,$metadata),$before))throw new \RuntimeException('The plugin checkout changed during the source check. No update applied.');
        $status=compare_source($before,$remote,$metadata);$backup='';$scanResult=['status'=>'disabled'];
        if($status['status']==='diverged')throw new \RuntimeException('History diverged; installed commits are not all reproduced upstream. No files were changed.');
        if($status['status']==='ahead')throw new \RuntimeException('This checkout has local commits ahead of upstream. No files were changed.');
        if($scan&&in_array($status['status'],['available','rewritten'],true)) {
            save_operation($plugin['id'],['status'=>'working','message'=>'Scanning update with ClamAV…']);
            $scanResult=\OmaPlugCtl\Malware\scan_commit($before['root'],$remote);
            if(!unchanged(source($plugin,$metadata),$before))throw new \RuntimeException('The plugin changed during malware scanning. No update applied.');
        }
        if(!unchanged(source($plugin,$metadata),$before))throw new \RuntimeException('The plugin changed during history verification. No update applied.');
        if($status['status']==='available')git($before['root'],['-c','core.hooksPath=/dev/null','merge','--ff-only','--no-edit','--no-overwrite-ignore',$remote],30);
        elseif($status['status']==='rewritten') {
            $backup='backup/omaplugctl/'.gmdate('Ymd\THis').bin2hex(random_bytes(4)).'Z-'.substr($before['head'],0,12);
            git($before['root'],['branch','--no-track',$backup,$before['head']]);
            if(git($before['root'],['rev-parse','refs/heads/'.$backup])!==$before['head'])throw new \RuntimeException('Could not verify the backup branch; update stopped.');
            try{git($before['root'],['-c','core.hooksPath=/dev/null','checkout','--no-track','--no-overwrite-ignore','-B',$before['branch'],$remote],30);}
            catch(\Throwable $error){throw new \RuntimeException('History reconciliation stopped; previous version is preserved at '.$backup.'.',0,$error);}
        }
        $after=source($plugin,$metadata);
        if(!$after||$after['head']!==$remote||$after['dirty']||$after['identity']!==$before['identity'])throw new \RuntimeException('Could not confirm the updated checkout. Refresh its status.');
        $cache=load_cache();$cache[$plugin['id']]=[...compare_source($after,$remote,$metadata),'scan'=>$scanResult];save_cache($cache);
        return ['head'=>$after['head'],'changed'=>$after['head']!==$before['head'],'backup'=>$backup,'scan'=>$scanResult];
    });
}
/** Four concurrent Git fetches, once per source identity, without PHP modules. */
function fetch_groups(array $groups): array {
    $pending=$groups;$active=[];$result=[];
    $environment=[...getenv(),'GIT_TERMINAL_PROMPT'=>'0','GIT_SSH_COMMAND'=>'ssh -oBatchMode=yes -oConnectTimeout=7'];
    try {
        while($pending||$active) {
            while($pending&&count($active)<4) {
                $key=array_key_first($pending);$info=$pending[$key];unset($pending[$key]);$pipes=[];
                $process=proc_open(['git','-C',$info['root'],'fetch','--quiet','--no-tags','origin',$info['target']],[0=>['file','/dev/null','r'],1=>['file','/dev/null','w'],2=>['file','/dev/null','w']],$pipes,null,$environment);
                if(!is_resource($process)){$result[$key]=null;continue;}
                $active[$key]=['process'=>$process,'info'=>$info,'deadline'=>microtime(true)+12];
            }
            foreach($active as$key=>$job) {
                $status=proc_get_status($job['process']);
                if($status['running']&&microtime(true)<$job['deadline'])continue;
                if($status['running'])proc_terminate($job['process'],9);
                proc_close($job['process']);unset($active[$key]);$result[$key]=null;
                if(!$status['running']&&$status['exitcode']===0)try{$result[$key]=git($job['info']['root'],['rev-parse','FETCH_HEAD']);}catch(\Throwable){}
            }
            if($active)usleep(10000);
        }
    } finally {foreach($active as$job){proc_terminate($job['process'],9);proc_close($job['process']);}}
    return $result;
}
function check_all(array $plugins,array $metadata): array {
    $cache=load_cache();$sources=[];$groups=[];
    foreach($plugins as$plugin){$info=source($plugin,$metadata[$plugin['id']]??[]);if($info){$sources[$plugin['id']]=$info;$groups[$info['identity']]=$info;}}
    $fetched=fetch_groups($groups);
    foreach($sources as$id=>$info)try { $remote=$fetched[$info['identity']];if($remote===null)throw new \RuntimeException('Source check failed.');$cache[$id]=compare_source($info,$remote,$metadata[$id]); }
    catch(\Throwable){$cache[$id]=[...$info,'status'=>'error','canUpdate'=>false];}
    save_cache($cache);return $cache;
}
