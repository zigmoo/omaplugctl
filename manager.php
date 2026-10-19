<?php
declare(strict_types=1);
namespace OmaPlugCtl;
use OmaPlugCtl\Updates as Updates;
use OmaPlugCtl\Malware as Malware;
use OmaPlugCtl\Marketplace as Marketplace;

function self_settings(): array {
    foreach((config()['bar']['layout']??[])as$entries)if(is_array($entries))foreach($entries as$entry)if(is_array($entry)&&($entry['id']??'')===SELF)return $entry;
    return [];
}
function configured_bar_icon_scale(): int {$value=self_settings()['barIconScale']??100;return is_int($value)&&$value>=50&&$value<=200?$value:100;}
function scan_before_update(): bool {return (self_settings()['scanBeforeUpdate']??true)!==false;}
function configured_sort(): string {$value=self_settings()['sortOrder']??'screen';return in_array($value,SORT_ORDERS,true)?$value:'screen';}
function workspace_settings(): ?array {
    $layout=config()['bar']['layout']??[];$candidates=[];
    foreach(catalog()as$plugin){
        $manifest=json_file($plugin['manifestPath']??'',null);if(!is_array($manifest))continue;
        $provenance=$manifest['omarchy']??[];
        if(($manifest['id']??'')!=='omarchy.workspaces'&&(!is_array($provenance)||($provenance['clonedFrom']??'')!=='omarchy.workspaces'))continue;
        $widget=$manifest['barWidget']??[];if(!is_array($widget))continue;$schema=$widget['schema']??[];$supported=false;
        if(is_array($schema))foreach($schema as$field)if(is_array($field)&&($field['key']??'')==='pinnedCount'&&($field['type']??'')==='integer')$supported=true;
        if(!$supported)continue;$defaults=is_array($widget['defaults']??null)?$widget['defaults']:[];
        foreach($layout as$entries)if(is_array($entries))foreach($entries as$entry){
            if(is_string($entry))$entry=['id'=>$entry];if(!is_array($entry)||($entry['id']??'')!==($plugin['id']??null))continue;
            $value=$entry['pinnedCount']??$defaults['pinnedCount']??5;
            if(!is_int($value)||$value<0||$value>10)return null;$candidates[]=['id'=>$plugin['id'],'count'=>$value];
        }
    }
    return count($candidates)===1?$candidates[0]:null;
}
function set_bar_icon_scale(?string $value): array {
    if($value===null||!preg_match('/\A\d{2,3}\z/D',$value)||(int)$value<50||(int)$value>200)throw new \InvalidArgumentException('Choose a bar icon size between 50% and 200%.');
    run(['omarchy','bar','set',SELF,'barIconScale',(string)(int)$value,'--json']);
    if(configured_bar_icon_scale()!==(int)$value)throw new \RuntimeException('The bar icon size was not saved. Refresh and try again.');
    return ['plugins'=>inventory(),'message'=>'Bar icon size saved.'];
}
function set_workspace_count(?string $value): array {
    if($value===null||!preg_match('/\A(?:[0-9]|10)\z/D',$value))throw new \InvalidArgumentException('Choose between 0 and 10 always-visible workspaces.');
    $current=workspace_settings();if($current===null)throw new \RuntimeException('The active workspace widget does not expose a single configurable count.');
    run(['omarchy','bar','set',$current['id'],'pinnedCount',$value,'--json']);
    if(workspace_settings()!==['id'=>$current['id'],'count'=>(int)$value])throw new \RuntimeException('The workspace count was not saved. Refresh and try again.');
    return ['plugins'=>inventory(),'message'=>'Workspace count saved.'];
}
function set_scan_before_update(?string $value): array {
    if(!in_array($value,['true','false'],true))throw new \InvalidArgumentException('Choose whether to scan updates before installation.');
    run(['omarchy','bar','set',SELF,'scanBeforeUpdate',$value,'--json']);
    if(scan_before_update()!==($value==='true'))throw new \RuntimeException('The malware scan preference was not confirmed.');
    return ['plugins'=>inventory(),'message'=>'Malware scan preference saved.'];
}
function set_sort(?string $value): array {
    if(!in_array($value,SORT_ORDERS,true))throw new \InvalidArgumentException('Choose name, screen, or updates.');
    run(['omarchy','bar','set',SELF,'sortOrder',$value]);if(configured_sort()!==$value)throw new \RuntimeException('The selected sort order was not confirmed.');
    return ['plugins'=>inventory(),'message'=>''];
}
function bar_position(): string {
    try {$value=run(['omarchy','bar','position']);}
    catch (\RuntimeException $error) {
        // Omarchy 4.0.5 supports writes only; read the same persisted setting.
        if (trim($error->getMessage())!=='omarchy-bar: position is required') throw $error;
        $value=config()['bar']['position']??null;
    }
    if(!is_string($value)||!in_array($value,EDGES,true))throw new \RuntimeException('Could not read the current bar position.');
    return $value;
}
function set_bar_position(?string $edge): array {
    if(!in_array($edge,EDGES,true))throw new \InvalidArgumentException('Choose top, bottom, left, or right.');
    run(['omarchy','bar','position',$edge]);$position=bar_position();if($position!==$edge)throw new \RuntimeException('New bar position was not confirmed. Try Refresh.');
    return ['plugins'=>inventory(),'barPosition'=>$position,'message'=>'Bar position confirmed.'];
}
function sort_plugins(array $plugins,string $order): array {
    $key=function($p)use($order){
        $name=fold((string)($p['name']??$p['id']));
        if($order==='screen'){$positions=[];foreach($p['instances']??[]as$instance){$section=array_search($instance['section'],SECTIONS,true);if($section!==false)$positions[]=[$section,$instance['index']];}sort($positions);return [...($positions[0]??[count(SECTIONS),0]),$name];}
        if($order==='updates'){$update=$p['update']??[];$date=$update['latestDate']??'';$stamp=is_string($date)&&preg_match('/\A\d{4}-\d{2}-\d{2}\z/D',$date)?strtotime($date.'T00:00:00+00:00'):false;return [!in_array($update['status']??'',['available','rewritten','diverged'],true),-($stamp?:0),$name];}
        return [$name];
    };
    usort($plugins,fn($a,$b)=>$key($a)<=>$key($b));return $plugins;
}
function inventory(): array {
    $plugins=json_decode(run(['omarchy-shell','shell','listPlugins']),true,512,JSON_THROW_ON_ERROR);
    if(!is_array($plugins)||!array_is_list($plugins)||count($plugins)>10000)throw new \RuntimeException('Could not read the running plugins.');
    $metadata=metadata_map();$updateCache=Updates\load_cache();$operations=Updates\operations();$history=author_cache();$previous=$history;$layout=config()['bar']['layout']??[];$result=[];
    foreach($plugins as$p){
        if(!is_array($p)||!in_array('bar-widget',$p['kinds']??[],true))continue;$id=$p['id'];$instances=[];
        foreach(SECTIONS as$section)foreach($layout[$section]??[]as$index=>$entry){$eid=is_string($entry)?$entry:($entry['id']??'');if($eid===$id)$instances[]=['section'=>$section,'index'=>$index];}
        $p['instances']=$instances;$p['description']=plugin_description($metadata[$id]??[]);$p=[...$p,...plugin_details($metadata[$id]??[],$history)];
        $p['isSelf']=$id===SELF;$p['canDisable']=!$p['isSelf']&&($p['canDisable']??true);$p['canRemove']=!$p['isSelf']&&empty($p['firstParty'])&&file_exists(home().'/.config/omarchy/plugins/'.$id);
        $p['update']=Updates\cached_status($p,$metadata[$id]??[],$updateCache);$p['operation']=$operations[$id]??(object)[];$result[]=$p;
    }
    if($history!==$previous)Updates\save_cache($history,state_root().'/authors.json');return $result;
}
function check_updates(): array {
    Updates\check_all(inventory(),metadata_map());$plugins=inventory();$available=0;$failed=0;
    foreach($plugins as$p){if(in_array($p['update']['status'],['available','rewritten','diverged'],true))$available++;if($p['update']['status']==='error')$failed++;}
    return ['plugins'=>$plugins,'message'=>$available.' updates available. '.$failed.' source checks failed.'];
}
function update_target(?string $id): array {
    validate_id($id);$plugin=null;foreach(inventory()as$p)if($p['id']===$id){$plugin=$p;break;}
    if($plugin===null)throw new \InvalidArgumentException('Unknown bar plugin.');
    $source=Updates\source($plugin,metadata_map()[$id]??[]);
    if($source===null){if(!empty($plugin['firstParty'])&&empty($plugin['clonedFrom']))return [$plugin,null];throw new \RuntimeException('No independent Git update repository is configured for this plugin.');}
    if($source['dirty'])throw new \RuntimeException('This source has local changes. Review them before updating; no files were changed.');
    return [$plugin,$source];
}
function launch_update(?string $id): array {
    [$plugin,$source]=update_target($id);
    if($source===null||$source['kind']!=='plugin')throw new \RuntimeException('Built-in plugins are updated with Omarchy.');
    if(!$source['tracking'])throw new \RuntimeException('Choose a branch tracking origin before updating this plugin.');
    return locked(state_root().'/operations/launcher.lock',function()use($id){
        $previous=Updates\operations()[$id]??[];$stamp=is_string($previous['changedAt']??null)?strtotime($previous['changedAt']):false;
        if(($previous['status']??'')==='working'&&$stamp!==false&&time()-$stamp<120)return ['plugins'=>inventory(),'message'=>'This plugin is already updating.'];
        Updates\save_operation($id,['status'=>'working','message'=>'Updating plugin…']);
        try{$result=process_result(['setsid','--fork',PHP_BINARY,'-n',__DIR__.'/controller.php','finish-update',$id],5);if($result['code']!==0)throw new \RuntimeException('Could not start the background update.');}
        catch(\Throwable $error){Updates\save_operation($id,['status'=>'error','message'=>shorten($error->getMessage(),1200)]);throw $error;}
        return ['plugins'=>inventory(),'message'=>'Updating plugin…'];
    },true);
}
function apply_update(?string $id): array {
    [$plugin]=update_target($id);$metadata=metadata_map();$result=Updates\apply_update($plugin,$metadata[$id],scan_before_update());
    $message=$result['changed']?'Updated to '.substr($result['head'],0,8).'.':'Already up to date.';
    if($result['backup']!=='')$message.=' Upstream history reconciled; previous version backed up.';
    if(($result['scan']['status']??'')==='no-threats-detected')$message.=' ClamAV: no threats detected.';
    Updates\save_operation($id,['status'=>'done','message'=>$message,'backup'=>$result['backup'],'scan'=>$result['scan']]);
    if($result['changed'])try{run(['omarchy-shell','shell','rescanPlugins']);}catch(\Throwable){$message.=' Refresh the shell to reload the plugin.';}
    return ['plugins'=>inventory(),'message'=>$message];
}
function about_url(array $plugin): string {
    $directory=home().'/.config/omarchy/plugins/'.$plugin['id'];
    if(is_dir($directory)){
        $manifest=json_file($directory.'/manifest.json');foreach(['homepage','website','repository','repo']as$key){$value=$manifest[$key]??null;if(is_array($value))$value=$value['url']??null;if(is_string($value)&&str_starts_with($value,'https://'))return $value;}
        if(file_exists($directory.'/.git')){$value=run(['git','-C',$directory,'remote','get-url','origin']);if(str_starts_with($value,'https://'))return preg_replace('/\.git\z/','',$value);if(str_starts_with($value,'git@github.com:'))return 'https://github.com/'.preg_replace('/\.git\z/','',explode(':',$value,2)[1]);}
    }
    if(!empty($plugin['firstParty'])||str_starts_with($plugin['clonedFrom']??'','omarchy.'))return builtin_about_url($plugin['clonedFrom']??$plugin['id']);
    [$catalog]=Marketplace\load();foreach($catalog['entries']as$entry)if($entry['id']===$plugin['id']&&$entry['repo']!=='')return $entry['repo'];
    throw new \RuntimeException('No source page found for this plugin.');
}
function execute(string $action,?string $id,?string $section=null,?string $source=null,?int $index=null,bool $confirmed=false): array {
    validate_id($id);$before=inventory();$p=null;foreach($before as$row)if($row['id']===$id){$p=$row;break;}if(!$p)throw new \InvalidArgumentException('Unknown bar plugin.');
    if(!empty($p['isSelf'])&&in_array($action,['disable','remove'],true))throw new \InvalidArgumentException('OmaPlugCtl must remain enabled to manage plugins.');
    if($action==='about'){run(['xdg-open',about_url($p)]);return ['plugins'=>$before,'message'=>'Opened source page.'];}
    if($action==='remove'){if(empty($p['canRemove'])||!$confirmed)throw new \InvalidArgumentException('Uninstall requires confirmation and an installed third-party plugin.');run(['omarchy-plugin-remove',$id,'--yes']);}
    elseif(in_array($action,['enable','disable'],true))run(['omarchy-plugin-'.$action,$id]);
    elseif($action==='move'){
        if(!in_array($section,SECTIONS,true)||!in_array($source,SECTIONS,true)||$index===null)throw new \InvalidArgumentException('Move requires destination and source instance.');
        if(!in_array(['section'=>$source,'index'=>$index],$p['instances'],true))throw new \InvalidArgumentException('Widget layout changed; refresh and select again.');
        $output=run(['omarchy-shell','shell','moveBarWidget',$id,json_encode(['section'=>$section,'fromSection'=>$source,'fromIndex'=>$index],JSON_THROW_ON_ERROR)]);if($output!=='ok')throw new \RuntimeException($output);
    }else throw new \InvalidArgumentException('Unsupported action.');
    $read=function()use($id){$rows=inventory();$found=null;foreach($rows as$row)if($row['id']===$id){$found=$row;break;}return [$rows,$found];};
    [$after,$q]=$read();
    if($action==='remove'){$deadline=microtime(true)+5;while($q!==null&&microtime(true)<$deadline){usleep(200000);[$after,$q]=$read();}if($q!==null)throw new \RuntimeException('Plugin removal was not confirmed by the registry; try Refresh.');}
    if(in_array($action,['enable','disable'],true)&&($q===null||$q['enabled']!==($action==='enable')))throw new \RuntimeException('Plugin state was not confirmed by the registry.');
    if($action==='move'){$count=fn($plugin,$region)=>count(array_filter($plugin['instances'],fn($position)=>$position['section']===$region));if($q===null||$count($q,$section)!==$count($p,$section)+(int)($source!==$section))throw new \RuntimeException('New widget placement was not confirmed.');}
    return ['plugins'=>$after,'message'=>'Change confirmed.'];
}
function response(array $data): array {
    $data['barPosition']=$data['barPosition']??bar_position();$data['sortOrder']=configured_sort();$data['barIconScale']=configured_bar_icon_scale();$data['workspaceSettings']=workspace_settings();$data['scanBeforeUpdate']=scan_before_update();$data['scannerStatus']=Malware\status();$data['plugins']=sort_plugins($data['plugins'],$data['sortOrder']);return $data;
}
