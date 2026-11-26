<?php
declare(strict_types=1);
namespace OmaPlugCtl;
use OmaPlugCtl\Updates as Updates;
use OmaPlugCtl\Malware as Malware;
use OmaPlugCtl\Marketplace as Marketplace;
use OmaPlugCtl\Sources as Sources;

const DEFAULT_BAR = 'omarchy.bar';

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
    return Updates\read_snapshot(fn()=>inventory_snapshot());
}
function registry_plugins(int $timeout=25): array {
    $plugins=json_decode(run(['omarchy-shell','shell','listPlugins'],$timeout),true,512,JSON_THROW_ON_ERROR);
    if(!is_array($plugins)||!array_is_list($plugins)||count($plugins)>10000)throw new \RuntimeException('Could not read the running plugins.');
    return $plugins;
}
function hidden_bar_widgets(): object {
    $visibility=[];
    try {
        $geometry=json_decode(run(['omarchy-shell','shell','debugBarGeometry'],2),true,512,JSON_THROW_ON_ERROR);
        if (!is_array($geometry) || !array_is_list($geometry) || count($geometry)>10000) return (object)[];
        foreach ($geometry as $slot) {
            if (!is_array($slot) || !valid_id($slot['id']??null) || !is_bool($slot['visible']??null)
                || !is_bool($slot['itemVisible']??null)) continue;
            $id=$slot['id'];
            // Geometry can contain multiple placements and one copy per screen.
            $visibility[$id]=($visibility[$id]??false)||($slot['visible']&&$slot['itemVisible']);
        }
    } catch (\RuntimeException|\JsonException) {
        return (object)[];
    }
    $hidden=[];
    foreach ($visibility as $id=>$visible) if (!$visible) $hidden[$id]=true;
    return (object)$hidden;
}
function has_openable_panel(array $kinds): bool {
    return (bool)array_intersect(['overlay','panel','menu'],$kinds);
}
function opens_without_bar(mixed $kinds): bool {
    return is_array($kinds) && has_openable_panel($kinds) && !array_intersect(['bar','bar-widget'],$kinds);
}
function inventory_snapshot(): array {
    $plugins=registry_plugins();
    $metadata=metadata_map();$updateCache=Updates\load_cache();$operations=Updates\operations();$history=author_cache();$previous=$history;$layout=config()['bar']['layout']??[];$result=[];
    foreach($plugins as$p){
        if(!is_array($p)||!valid_id($p['id']??null)||!is_array($p['kinds']??null))continue;$id=$p['id'];$instances=[];
        $p['isBarWidget']=in_array('bar-widget',$p['kinds'],true);
        $p['isDefaultBar']=$id===DEFAULT_BAR && in_array('bar',$p['kinds'],true);
        $p['canOpen']=has_openable_panel($p['kinds']);
        foreach(SECTIONS as$section)foreach($layout[$section]??[]as$index=>$entry){$eid=is_string($entry)?$entry:($entry['id']??'');if($eid===$id)$instances[]=['section'=>$section,'index'=>$index];}
        $p['instances']=$instances;$p['description']=plugin_description($metadata[$id]??[]);$p=[...$p,...plugin_details($metadata[$id]??[],$history)];
        $p['isSelf']=$id===SELF;$p['canDisable']=$p['canDisable']??true;$p['canRemove']=!$p['isSelf']&&empty($p['firstParty'])&&file_exists(home().'/.config/omarchy/plugins/'.$id);
        $p['update']=Updates\cached_status($p,$metadata[$id]??[],$updateCache);$p['operation']=$operations[$id]??(object)[];$result[]=$p;
    }
    if($history!==$previous)Updates\save_cache($history,state_root().'/authors.json');return UserServices\attach_states($result);
}
function check_updates(): array {
    Updates\check_all(inventory(),metadata_map());$plugins=inventory();$available=0;$failed=0;
    foreach($plugins as$p){if(in_array($p['update']['status'],['available','rewritten','diverged'],true))$available++;if($p['update']['status']==='error')$failed++;}
    return ['plugins'=>$plugins,'message'=>$available.' updates available. '.$failed.' source checks failed.'];
}
function update_target(?string $id): array {
    validate_id($id);$plugin=null;foreach(inventory()as$p)if($p['id']===$id){$plugin=$p;break;}
    if($plugin===null)throw new \InvalidArgumentException('Unknown plugin.');
    $source=Updates\source($plugin,metadata_map()[$id]??[]);
    if($source===null){if(!empty($plugin['firstParty'])&&empty($plugin['clonedFrom']))return [$plugin,null];throw new \RuntimeException('No independent Git update repository is configured for this plugin.');}
    return [$plugin,$source];
}
function launch_update(?string $id,?string $editAction=null,?string $review=null): array {
    [$plugin,$source]=update_target($id);
    if($source===null||$source['kind']!=='plugin')throw new \RuntimeException('Built-in plugins are updated with Omarchy.');
    if(!$source['tracking'])throw new \RuntimeException('Choose a branch tracking origin before updating this plugin.');
    if ($source['dirty'] && $editAction===null) {
        $edits=Updates\review_edits($source);
        return ['plugins'=>inventory(),'message'=>'','editReview'=>[
            'pluginId'=>$id,'name'=>$plugin['name']??$id,'token'=>$edits['token']
        ]];
    }
    return locked(state_root().'/operations/launcher.lock',function()use($id,$editAction,$review){
        $previous=Updates\operations()[$id]??[];$stamp=is_string($previous['changedAt']??null)?strtotime($previous['changedAt']):false;
        if(($previous['status']??'')==='working'&&$stamp!==false&&time()-$stamp<120)return ['plugins'=>inventory(),'message'=>'This plugin is already updating.'];
        Updates\save_operation($id,['status'=>'working','message'=>'Updating plugin…']);
        $command=['setsid','--fork',PHP_BINARY,'-n',__DIR__.'/controller.php','finish-update',$id];
        if ($editAction!==null) array_push($command,'--edits',$editAction,'--review',$review);
        try{$result=process_result($command,5);if($result['code']!==0)throw new \RuntimeException('Could not start the background update.');}
        catch(\Throwable $error){Updates\save_operation($id,['status'=>'error','message'=>shorten($error->getMessage(),1200)]);throw $error;}
        return ['plugins'=>inventory(),'message'=>'Updating plugin…'];
    },true);
}
function apply_update(?string $id,?string $editAction=null,?string $review=null): array {
    [$plugin]=update_target($id);$metadata=metadata_map();$result=Updates\apply_update($plugin,$metadata[$id],scan_before_update(),$editAction,$review);
    $message=$result['changed']?'Updated to '.substr($result['head'],0,8).'.':'Already up to date.';
    if($result['backup']!=='')$message.=' Upstream history reconciled; previous version backed up.';
    if(($result['scan']['status']??'')==='no-threats-detected')$message.=' ClamAV: no threats detected.';
    if(!empty($result['stash']))$message.=' Local edits are in Git stash '.substr($result['stash'],0,12).'.';
    elseif($editAction==='discard'&&$result['changed'])$message.=' Reviewed edits discarded.';
    elseif($editAction!==null&&!$result['changed'])$message.=' Local edits are still in the checkout.';
    Updates\save_operation($id,['status'=>'done','message'=>$message,'backup'=>$result['backup'],'scan'=>$result['scan']]);
    if($result['changed'])try{run(['omarchy-shell','shell','rescanPlugins']);}catch(\Throwable){$message.=' Refresh the shell to reload the plugin.';}
    return ['plugins'=>inventory(),'message'=>$message];
}
function source_web_url(mixed $value): string {
    if (is_array($value)) $value=$value['url']??null;
    if (!is_string($value) || strlen($value)>2048 || preg_match('/[\x00-\x20\x7f]/',$value) || str_contains($value,'\\')) return '';
    if (preg_match('~\A(?:ssh://)?git@(github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)[:/](.+)\z~iD',$value,$match)) {
        $value='https://'.$match[1].'/'.$match[2];
    } elseif (str_starts_with($value,'git+https://')) {
        $value=substr($value,4);
    }
    $url=parse_url($value);
    if (($url['scheme']??'')!=='https' || !preg_match('/\A[A-Za-z0-9.-]+\z/D',$url['host']??'')
        || isset($url['user']) || isset($url['pass'])) return '';
    return preg_replace('/\.git\z/D','',$value);
}

function about_url(array $plugin): string {
    $directory=home().'/.config/omarchy/plugins/'.$plugin['id'];
    if(is_dir($directory)){
        $manifest=json_file($directory.'/manifest.json');
        foreach (['repository','repo'] as $key) {
            $url=source_web_url($manifest[$key]??null);
            if ($url!=='') return $url;
        }
        if (file_exists($directory.'/.git')) {
            try {
                $url=source_web_url(Updates\git($directory,['remote','get-url','origin'],5));
                if ($url!=='') return $url;
            } catch (\RuntimeException) {
                // A checkout without an origin may still declare a homepage.
            }
        }
        foreach (['homepage','website'] as $key) {
            $url=source_web_url($manifest[$key]??null);
            if ($url!=='') return $url;
        }
    }
    if(!empty($plugin['firstParty'])||str_starts_with($plugin['clonedFrom']??'','omarchy.'))return builtin_about_url($plugin['clonedFrom']??$plugin['id']);
    [$catalog]=Marketplace\load();foreach($catalog['entries']as$entry)if($entry['id']===$plugin['id']&&($url=source_web_url($entry['repo']))!=='')return $url;
    throw new \RuntimeException('No source page found for this plugin.');
}
function author_github_repository(array $plugin,array $metadata,array $manifest): string {
    if (!empty($plugin['firstParty']) || ($plugin['authorSource']??'')==='upstream-first-commit') {
        return 'https://github.com/omacom/omarchy';
    }
    $urls=[$manifest['repository']??null,$manifest['repo']??null];
    $directory=$metadata['sourceDir']??'';
    if (is_string($directory) && $directory!=='' && file_exists($directory.'/.git')) {
        try { array_unshift($urls,Updates\git($directory,['remote','get-url','origin'],5)); }
        catch (\RuntimeException) { /* A local checkout may have no origin. */ }
    }
    $urls[]=$manifest['homepage']??null;
    foreach (Marketplace\read_cache()['entries']??[] as $entry) {
        if ($entry['id']===$plugin['id']) $urls[]=$entry['repo'];
    }
    foreach ($urls as $url) {
        $repository=Sources\repository(source_web_url($url));
        if ($repository!==null) return $repository;
    }
    return '';
}

function installed_author_url(array $plugin,string $platform): string {
    $metadata=metadata_map()[$plugin['id']]??[];
    $manifest=json_file($metadata['manifestPath']??'');
    if (!is_array($manifest)) $manifest=[];
    $signature=author_data_signature($plugin,$metadata,$manifest);
    $cached=cached_author_link($plugin['id'],$platform,$signature);
    if ($cached!=='') return $cached;
    $profile=declared_author_profile($manifest,$platform) ?: readme_author_profile($metadata,$platform);
    if ($profile!=='') {
        cache_author_link($plugin,$platform,$signature,$profile);
        return $profile;
    }
    $cachedGithub=$platform==='x'?cached_author_link($plugin['id'],'github',$signature):'';
    $github=$cachedGithub ?: declared_author_profile($manifest,'github') ?: readme_author_profile($metadata,'github')
        ?: author_github_from_commit($plugin,$metadata);
    if ($github==='') $github=github_profile_from_repository($plugin,$metadata,author_github_repository($plugin,$metadata,$manifest));
    if ($github!=='' && $cachedGithub==='') cache_author_link($plugin,'github',$signature,$github);
    if ($github!=='' && $platform==='github') return $github;
    $account=github_profile_data($github);
    $profile=author_profile($account['twitter_username']??null,'x',true)
        ?: author_profile($account['blog']??null,'x');
    if ($profile!=='') {
        cache_author_link($plugin,'x',$signature,$profile);
        return $profile;
    }
    throw new \RuntimeException('No author '.($platform==='github'?'GitHub':'X').' profile found for this plugin.');
}
function active_bar_id(array $plugins): ?string {
    foreach ($plugins as $plugin) {
        if (is_array($plugin) && ($plugin['active'] ?? false) === true && valid_id($plugin['id'] ?? null)
            && is_array($plugin['kinds'] ?? null) && in_array('bar', $plugin['kinds'], true)) {
            return $plugin['id'];
        }
    }
    return null;
}
function switch_bar(string $action, array $plugin, array $before): array {
    if (!in_array('bar', $plugin['kinds'], true)) {
        throw new \InvalidArgumentException('Only a full-bar plugin can be used as the active bar.');
    }
    $current = active_bar_id($before);
    $id = $plugin['id'];
    if ($action === 'reset-bar' && ($current !== $id || $id === DEFAULT_BAR)) {
        throw new \InvalidArgumentException('The selected replacement bar is no longer active. Try Refresh.');
    }
    $target = $action === 'reset-bar' ? DEFAULT_BAR : $id;
    if ($current === $target) return ['plugins'=>$before, 'message'=>'Bar is already active.'];
    run($target === DEFAULT_BAR ? ['omarchy', 'bar', 'reset'] : ['omarchy', 'bar', 'use', $target]);
    $deadline = microtime(true) + 5;
    do {
        try {
            $active = active_bar_id(registry_plugins(2));
        } catch (\RuntimeException|\JsonException) {
            // The shell can be temporarily unavailable while the bar rebuilds.
            $active = null;
        }
        if ($active === $target) {
            $after = inventory();
            if (active_bar_id($after) === $target) return ['plugins'=>$after, 'message'=>'Bar switch confirmed.'];
            break;
        }
        usleep(200000);
    } while (microtime(true) < $deadline);
    throw new \RuntimeException('The requested bar did not become active. Try Refresh.');
}
function execute(string $action,?string $id,?string $section=null,?string $source=null,?int $index=null,bool $confirmed=false): array {
    validate_id($id);$before=inventory();$p=null;foreach($before as$row)if($row['id']===$id){$p=$row;break;}
    if ($action==='favorite' || $action==='unfavorite') {
        set_favorite($id,$p,$action==='favorite');
        return ['plugins'=>$before,'message'=>$action==='favorite'?'Added to favorites.':'Removed from favorites.'];
    }
    $copy=str_starts_with($action,'copy-');
    $linkAction=$copy?substr($action,5):$action;
    if (in_array($linkAction,['about','author-github','author-x'],true)) {
        if ($p===null) {
            $favorite=favorite_records()[$id]??null;
            if ($favorite===null) throw new \InvalidArgumentException('Unknown plugin.');
            $url=favorite_link($favorite,$linkAction);
        } else {
            $url=$linkAction==='about'?about_url($p):installed_author_url($p,$linkAction==='author-github'?'github':'x');
        }
        if ($copy) {
            run(['wl-copy','--type','text/plain;charset=utf-8','--',$url],5);
            return ['plugins'=>$before,'message'=>'Link copied.'];
        }
        run(['xdg-open',$url]);
        return ['plugins'=>$before,'message'=>$p===null?'Opened saved link.':
            ($linkAction==='about'?'Opened source page.':'Opened author profile.')];
    }
    if ($action==='reinstall') {
        $favorite=favorite_records()[$id]??null;
        if ($favorite!==null) {
            if ($p!==null) throw new \InvalidArgumentException('This plugin is already installed.');
            $repo=favorite_repository($favorite['repository']??null);
            if ($repo==='') throw new \RuntimeException('No installable repository is saved for this favorite.');
            $result=Sources\reinstall($repo,$id);
            $after=inventory();
            foreach ($after as $row) {
                if ($row['id']===$id && ($row['enabled']??null)===false) {
                    return ['plugins'=>$after,'message'=>$result['message']];
                }
            }
            throw new \RuntimeException('Reinstall was not confirmed in the Plugins list. Refresh and inspect the plugin.');
        }
    }
    if(!$p)throw new \InvalidArgumentException('Unknown plugin.');
    if ($action==='service-start'||$action==='service-stop') {
        $message=UserServices\operate($p,$source,substr($action,8));
        return ['plugins'=>inventory(),'message'=>$message];
    }
    if(!empty($p['isSelf'])&&$action==='remove')throw new \InvalidArgumentException('OmaPlugCtl cannot uninstall itself.');
    if(!empty($p['isSelf'])&&$action==='disable'&&!$confirmed)throw new \InvalidArgumentException('Confirm before pausing OmaPlugCtl.');
    if(in_array($action,['use-bar','reset-bar'],true))return switch_bar($action,$p,$before);
    if($action==='disable'&&($p['canDisable']??true)===false)throw new \InvalidArgumentException('This plugin must remain enabled.');
    if($action==='open'){
        if(empty($p['enabled'])||!$p['canOpen'])throw new \InvalidArgumentException('Enable a panel, overlay or menu plugin before opening it.');
        $output=run(['omarchy-shell','shell','summon',$id,'{}']);if($output!=='ok')throw new \RuntimeException('The shell did not accept the open request.');
        return ['plugins'=>$before,'message'=>'Open requested.'];
    }
    if($action==='remove'){if(empty($p['canRemove'])||!$confirmed)throw new \InvalidArgumentException('Uninstall requires confirmation and an installed third-party plugin.');run(['omarchy-plugin-remove',$id,'--yes']);}
    elseif(in_array($action,['enable','disable'],true))run(['omarchy-plugin-'.$action,$id]);
    elseif($action==='move'){
        if(!in_array('bar-widget',$p['kinds'],true))throw new \InvalidArgumentException('Only bar widgets can be moved on the bar.');
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
    $favorites=favorite_records();
    $installedIds=[];
    foreach ($data['plugins'] as &$plugin) {
        $installedIds[$plugin['id']]=true;
        $plugin['installed']=true;
        $plugin['favorite']=isset($favorites[$plugin['id']]);
    }
    unset($plugin);
    $data['barPosition']=$data['barPosition']??bar_position();$data['sortOrder']=configured_sort();$data['barIconScale']=configured_bar_icon_scale();$data['workspaceSettings']=workspace_settings();$data['scanBeforeUpdate']=scan_before_update();$data['scannerStatus']=Malware\status();$data['plugins']=sort_plugins($data['plugins'],$data['sortOrder']);
    $data['uninstalledFavorites']=sort_plugins(favorite_rows($favorites,$installedIds),$data['sortOrder']);
    $data['hiddenBarWidgets']=hidden_bar_widgets();
    return $data;
}
