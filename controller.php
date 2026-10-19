<?php
declare(strict_types=1);
namespace OmaPlugCtl;
ini_set('display_errors','stderr');
require_once __DIR__.'/runtime.php';
require_once __DIR__.'/updates.php';
require_once __DIR__.'/malware.php';
require_once __DIR__.'/marketplace.php';
require_once __DIR__.'/metadata.php';
require_once __DIR__.'/manager.php';

function main(array $argv): int {
    $action=$argv[1]??'list';$id=null;$options=['confirmed'=>false,'refresh'=>false];
    try{
        for($i=2;$i<count($argv);$i++){
            if(in_array($argv[$i],['--confirmed','--refresh'],true))$options[substr($argv[$i],2)]=true;
            elseif(in_array($argv[$i],['--edge','--section','--source','--index'],true)){if(!isset($argv[$i+1]))throw new \InvalidArgumentException('Missing option value.');$options[substr($argv[$i],2)]=$argv[++$i];}
            elseif($id===null)$id=$argv[$i];else throw new \InvalidArgumentException('Unexpected argument.');
        }
        if(isset($options['index'])&&!preg_match('/\A\d+\z/D',$options['index']))throw new \InvalidArgumentException('Invalid widget index.');
        if($action==='finish-update'){
            validate_id($id);
            try{apply_update($id);return 0;}catch(\Throwable $error){Updates\save_operation($id,['status'=>'error','message'=>shorten($error->getMessage(),1200)]);return 1;}
        }
        $data=match($action){
            'catalog'=>Marketplace\state($options['refresh']),
            'catalog-install'=>Marketplace\install($id),
            'catalog-enable'=>Marketplace\enable($id),
            'catalog-source'=>Marketplace\source($id),
            'settings'=>['barIconScale'=>configured_bar_icon_scale()],
            'update-status'=>['operations'=>(object)Updates\operations()],
            'list'=>response(['plugins'=>inventory(),'message'=>'']),
            'position'=>response(set_bar_position($options['edge']??null)),
            'icon-scale'=>response(set_bar_icon_scale($id)),
            'workspace-count'=>response(set_workspace_count($id)),
            'sort'=>response(set_sort($id)),
            'set-scan'=>response(set_scan_before_update($id)),
            'check-updates'=>response(check_updates()),
            'update'=>response(launch_update($id)),
            'enable','disable','move','remove','about'=>response(execute($action,$id,$options['section']??null,$options['source']??null,isset($options['index'])?(int)$options['index']:null,$options['confirmed'])),
            default=>throw new \InvalidArgumentException('Unknown action.'),
        };
        echo json_encode(['ok'=>true,...$data],JSON_THROW_ON_ERROR|JSON_INVALID_UTF8_SUBSTITUTE|JSON_UNESCAPED_UNICODE),PHP_EOL;return 0;
    }catch(\Throwable $error){echo json_encode(['ok'=>false,'message'=>shorten($error->getMessage(),1800)],JSON_INVALID_UTF8_SUBSTITUTE|JSON_UNESCAPED_UNICODE),PHP_EOL;return 1;}
}
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__)exit(main($argv));
