<?php
declare(strict_types=1);
namespace OmaPlugCtl\UserServices;

use function OmaPlugCtl\{clean_text,process_result,run};

function valid_unit(mixed $value): bool {
    return is_string($value) && strlen($value)<=160
        && preg_match('/\A[A-Za-z0-9][A-Za-z0-9_.-]*(?:@[A-Za-z0-9_.-]+)?\.service\z/D',$value)===1;
}

function definitions(string $id,array $manifest): array {
    $services=match($id) {
        'io.github.mb-jambon.omapods'=>[['unit'=>'librepods.service','name'=>'LibrePods']],
        'moo.webcamtuner'=>[['unit'=>'webcamtuner-output.service','name'=>'Camera output',
            'ipc'=>['start'=>'outputStart','stop'=>'outputStop']]],
        default=>[],
    };
    $declared=$manifest['userServices']??[];
    if (!is_array($declared) || !array_is_list($declared)) return $services;
    $known=array_column($services,'unit');
    foreach (array_slice($declared,0,8) as $service) {
        if (!is_array($service) || !valid_unit($service['unit']??null) || in_array($service['unit'],$known,true)) continue;
        $name=clean_text($service['name']??'',100);
        $known[]=$service['unit'];
        $services[]=['unit'=>$service['unit'],'name'=>$name?:$service['unit']];
    }
    return $services;
}

function unit_states(array $units): array {
    if (!$units) return [];
    try {
        $reply=process_result(['systemctl','--user','show','--no-pager',
            '--property=Id,Names,LoadState,ActiveState,CanStart,CanStop','--',...$units],3,null,null,65536);
    } catch (\RuntimeException) { return []; }
    $states=[];
    foreach (preg_split('/\R\R+/',trim($reply['stdout'])) as $block) {
        $properties=[];
        foreach (preg_split('/\R/',$block) as $line) {
            if (str_contains($line,'=')) {
                [$key,$value]=explode('=',$line,2);
                $properties[$key]=$value;
            }
        }
        $names=explode(' ',$properties['Names']??'');
        $names[]=$properties['Id']??'';
        foreach (array_intersect($units,$names) as $unit) $states[$unit]=$properties;
    }
    return $states;
}

function status(array $service,array $unit,?array $ipc): array {
    $load=$unit['LoadState']??'';
    $active=$unit['ActiveState']??'';
    $managed=isset($service['ipc']);
    $state=match(true) {
        $active==='active'=>'running',
        in_array($active,['activating','deactivating','reloading','refreshing'],true)=>'working',
        $load==='not-found'&&!$managed=>'setup',
        $active==='failed'=>'failed',
        $load==='loaded'||($load==='not-found'&&$managed)=>'stopped',
        default=>'unavailable',
    };
    if (($ipc['outputBusy']??false)===true) $state='working';
    $canStart=$managed?($ipc['outputReady']??false)===true:($unit['CanStart']??'')==='yes';
    $canStop=$managed?$ipc!==null:($unit['CanStop']??'')==='yes';
    $action=match(true) {
        $state==='running'&&$canStop=>'stop',
        in_array($state,['stopped','failed'],true)&&$canStart=>'start',
        default=>'',
    };
    return [...$service,'state'=>$state,'action'=>$action];
}

function attach_states(array $plugins): array {
    $units=[];
    foreach ($plugins as $plugin) foreach ($plugin['services']??[] as $service) $units[$service['unit']]=true;
    $states=unit_states(array_keys($units));
    foreach ($plugins as &$plugin) {
        if (empty($plugin['services'])) continue;
        $ipc=null;
        if (!empty($plugin['enabled']) && array_filter($plugin['services'],fn($service)=>isset($service['ipc']))) {
            try {
                $value=json_decode(run(['omarchy-shell',$plugin['id'],'status'],2),true,32,JSON_THROW_ON_ERROR);
                if (is_array($value)) $ipc=$value;
            } catch (\RuntimeException|\JsonException) { /* Keep the unit's last readable state. */ }
        }
        $plugin['services']=array_map(fn($service)=>status($service,$states[$service['unit']]??[],$ipc),$plugin['services']);
    }
    unset($plugin);
    return $plugins;
}

function operate(array $plugin,?string $unit,string $action): string {
    if (!valid_unit($unit)) throw new \InvalidArgumentException('Choose a service listed under this plugin.');
    $service=null;
    foreach ($plugin['services']??[] as $candidate) if ($candidate['unit']===$unit) { $service=$candidate; break; }
    if ($service===null) throw new \InvalidArgumentException('Choose a service listed under this plugin.');
    $name=$service['name'];
    if ($service['action']!==$action) {
        if ($action==='start'&&$service['state']==='running') return $name.' is running.';
        if ($action==='stop'&&$service['state']==='stopped') return $name.' is stopped.';
        throw new \RuntimeException($name.' is unavailable for that action.');
    }
    if (isset($service['ipc'])) {
        run(['omarchy-shell',$plugin['id'],$service['ipc'][$action]],5);
        return $name.($action==='start'?' start requested.':' stop requested.');
    }
    run(['systemctl','--user',$action,'--',$unit],15);
    $active=unit_states([$unit])[$unit]['ActiveState']??'';
    if ($action==='start'&&$active==='active') return $name.' is running.';
    if ($action==='stop'&&$active==='inactive') return $name.' is stopped.';
    throw new \RuntimeException('Could not confirm that '.$name.($action==='start'?' started.':' stopped.'));
}
