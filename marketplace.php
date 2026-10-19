<?php
declare(strict_types=1);
namespace OmaPlugCtl\Marketplace;
use function OmaPlugCtl\{state_root,json_file,save_json,valid_id,clean_text,fold,run,process_result,locked,now};

const CATALOG_URL='https://plugins.omarchy.org/catalog.json';
const MAX_BYTES=33554432;
const MAX_PLUGINS=10000;
function cache_path(): string{return state_root().'/marketplace.json';}
function valid_repo(mixed $repo): bool{return is_string($repo)&&preg_match('~\Ahttps://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+(?:\.git)?\z~D',$repo)===1;}
function normalize(mixed $payload): array {
    if(!is_array($payload)||!isset($payload['plugins'])||!is_array($payload['plugins'])||!array_is_list($payload['plugins']))throw new \InvalidArgumentException('The marketplace returned an invalid catalog.');
    if(count($payload['plugins'])>MAX_PLUGINS)throw new \InvalidArgumentException('The marketplace catalog exceeds the plugin limit.');
    $entries=[];$seen=[];
    foreach($payload['plugins']as$item) {
        if(!is_array($item)||!valid_id($item['id']??null)||isset($seen[$item['id']]))continue;
        $id=$item['id'];$seen[$id]=true;
        if(!empty($item['builtIn'])||($item['sourceType']??'')==='builtin')continue;
        $repo=valid_repo($item['repo']??null)?preg_replace('/\.git\z/','',$item['repo']):'';
        $snapshot=is_string($item['verificationCommit']??null)&&preg_match('/\A[0-9a-f]{40}\z/D',$item['verificationCommit'])?$item['verificationCommit']:'';
        $verified=$snapshot!==''&&$snapshot===($item['listingValidatedCommit']??null)&&$snapshot===($item['upstreamObservedCommit']??null)&&($item['verificationStatus']??'')==='verified'&&($item['verificationSnapshotStatus']??'')==='verified'&&($item['verificationCoverage']??'')==='snapshot-verified';
        $coverage=$verified?'snapshot-verified':($snapshot!==''&&($item['verificationCoverage']??'')==='update-unverified'?'update-unverified':'unverified');
        $tags=is_array($item['tags']??null)?array_map(fn($tag)=>clean_text($tag,60),array_slice($item['tags'],0,20)):[];
        $entry=['id'=>$id,'name'=>clean_text($item['name']??'',160)?:$id,'description'=>clean_text($item['description']??'',1200),'author'=>clean_text($item['author']??'',160),'tags'=>$tags,'category'=>clean_text($item['category']??'',80),'repo'=>$repo,'verified'=>$verified,'coverage'=>$coverage,'verifiedCommit'=>$snapshot,'installable'=>$repo!==''&&($item['installAvailable']??null)===true&&($item['repositoryLayout']??'')==='root-plugin','installNote'=>clean_text($item['installNote']??'',500)];
        $entry['searchText']=fold(implode(' ',[$id,$entry['name'],$entry['description'],$entry['author'],$entry['category'],...$tags]));$entries[]=$entry;
    }
    if(!$entries)throw new \InvalidArgumentException('The marketplace catalog contains no community plugins.');
    usort($entries,fn($a,$b)=>[fold($a['name']),$a['id']]<=>[fold($b['name']),$b['id']]);return $entries;
}
function read_cache(): ?array {
    $value=json_file(cache_path(),null,MAX_BYTES);
    if(!is_array($value)||($value['schema']??null)!==1||!is_array($value['entries']??null)||!array_is_list($value['entries'])||count($value['entries'])>MAX_PLUGINS||!is_string($value['fetchedAt']??null)||strtotime($value['fetchedAt'])===false)return null;
    foreach($value['entries']as$row) {
        if(!is_array($row)||!valid_id($row['id']??null)||!is_bool($row['verified']??null)||!is_bool($row['installable']??null)||!in_array($row['coverage']??'',['snapshot-verified','update-unverified','unverified'],true))return null;
        foreach(['id','name','description','author','searchText','coverage','repo']as$key)if(!is_string($row[$key]??null))return null;
    }
    return $value;
}
function load(bool $refresh=false): array {
    $cached=read_cache();$warning='';
    if($cached===null||$refresh)try {
        // curl is already part of Omarchy. php -n needs no TLS/curl extension.
        $result=process_result(['curl','--fail','--silent','--show-error','--proto','=https','--max-time','25','--max-filesize',(string)MAX_BYTES,'--user-agent','OmaPlugCtl/0.16','--write-out',"\n%{http_code}",CATALOG_URL],30,null,null,MAX_BYTES+1024);
        $separator=strrpos($result['stdout'],"\n");
        if($result['code']!==0||$separator===false||substr($result['stdout'],$separator+1)!=='200'||$separator>MAX_BYTES)throw new \RuntimeException('Catalog download failed or redirected.');
        $entries=normalize(json_decode(substr($result['stdout'],0,$separator),true,512,JSON_THROW_ON_ERROR));
        $cached=['schema'=>1,'entries'=>$entries,'fetchedAt'=>now()];save_json($cached,cache_path());
    }catch(\Throwable $error) {
        if($cached===null)throw new \RuntimeException('Could not load the marketplace. Check your connection and try Refresh.',0,$error);
        $warning='Refresh failed; showing the saved catalog.';
    }
    return [$cached,$warning];
}
function installed_plugins(): array {
    $rows=json_decode(run(['omarchy-plugin-list','--json']),true,512,JSON_THROW_ON_ERROR);
    if(!is_array($rows)||!array_is_list($rows))throw new \RuntimeException('Could not read the installed plugins.');
    $result=[];foreach($rows as$row)if(is_array($row)&&is_string($row['id']??null))$result[$row['id']]=$row;return $result;
}
function state(bool $refresh=false): array {
    [$catalog,$warning]=load($refresh);$installed=installed_plugins();$entries=[];
    foreach($catalog['entries']as$row)$entries[]=[...$row,'installed'=>isset($installed[$row['id']]),'enabled'=>($installed[$row['id']]['enabled']??false)===true];
    return ['entries'=>$entries,'fetchedAt'=>$catalog['fetchedAt'],'message'=>$warning];
}
function entry(?string $id): array {
    if(!valid_id($id))throw new \InvalidArgumentException('Invalid marketplace plugin id.');
    [$catalog]=load();$found=null;foreach($catalog['entries']as$row)if($row['id']===$id){$found=$row;break;}
    if($found===null)throw new \InvalidArgumentException('This plugin is not in the saved marketplace catalog. Refresh and try again.');
    if(!valid_repo($found['repo']))throw new \InvalidArgumentException('No supported HTTPS source repository is available for this plugin.');
    return $found;
}
function install(?string $id): array {
    $plugin=entry($id);
    if(!$plugin['installable'])throw new \InvalidArgumentException('This plugin requires manual setup. Open its source page for instructions.');
    locked(state_root().'/marketplace.install.lock',function()use($id,$plugin){
        if(isset(installed_plugins()[$id]))throw new \InvalidArgumentException('This plugin is already installed. Refresh the list.');
        run(['omarchy','plugin','add',$plugin['repo'],'--yes'],180);$installed=installed_plugins()[$id]??null;
        if($installed===null)throw new \RuntimeException('Installation did not confirm the expected plugin id. Refresh and inspect the installed plugins.');
        if(!empty($installed['enabled']))throw new \RuntimeException('The plugin was installed but is already enabled. Inspect its state in Plugins.');
    });
    return [...state(),'message'=>$plugin['name'].' installed, disabled. Click Enable when ready.'];
}
function enable(?string $id): array {
    $plugin=entry($id);if(!isset(installed_plugins()[$id]))throw new \InvalidArgumentException('Install this plugin before enabling it.');
    run(['omarchy','plugin','enable',$id]);if((installed_plugins()[$id]['enabled']??null)!==true)throw new \RuntimeException('Enabling was not confirmed by Omarchy. Refresh and try again.');
    return [...state(),'message'=>$plugin['name'].' enabled.'];
}
function source(?string $id): array { $plugin=entry($id);run(['xdg-open',$plugin['repo']]);return ['message'=>'Opened source page.']; }
