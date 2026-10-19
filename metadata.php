<?php
declare(strict_types=1);
namespace OmaPlugCtl;
use OmaPlugCtl\Updates as Updates;

function omarchy_root(): string {return rtrim(getenv('OMARCHY_PATH')?:home().'/.local/share/omarchy','/');}
function builtin_metadata(string $id): array {
    if(preg_match('/\Aomarchy\.[A-Za-z0-9._-]+\z/D',$id)!==1)return [];
    $root=omarchy_root().'/shell/plugins';if(!is_dir($root))return [];
    $files=new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($root,\FilesystemIterator::SKIP_DOTS));
    foreach($files as$file)if($file->isFile()&&str_ends_with($file->getFilename(),'manifest.json')){
        $manifest=json_file($file->getPathname());if(is_array($manifest)&&($manifest['id']??'')===$id)return [...$manifest,'sourceDir'=>$file->getPath(),'manifestPath'=>$file->getPathname()];
    }
    return [];
}
function builtin_about_url(string $id): string {
    $base='https://github.com/omacom/omarchy';$metadata=builtin_metadata($id);
    if(!$metadata)return $base;$manifest=$metadata['manifestPath'];$path=basename($manifest)==='manifest.json'?dirname($manifest):$manifest;
    return $base.'/'.(basename($manifest)==='manifest.json'?'tree':'blob').'/HEAD/'.relative_path($path,omarchy_root());
}
function readme_description(array $metadata): string {
    $directory=$metadata['sourceDir']??null;
    if(!is_string($directory)||$directory===''||(isset($metadata['manifestPath'])&&basename($metadata['manifestPath'])!=='manifest.json'))return '';
    $file=$directory.'/README.md';clearstatcache(true,$file);
    if(!is_file($file)||is_link($file)||filesize($file)>262144)return '';
    try{$body=raw_run(['dd','if='.$file,'iflag=nonblock,nofollow','bs=262145','count=1','status=none'],5,null,null,262145);}catch(\Throwable){return '';}
    if(strlen($body)>262144||preg_match('//u',$body)!==1)return '';
    $body=preg_replace('/\A\xEF\xBB\xBF/','',$body);$fence=null;$sections=[];$collecting=false;$finished=false;$index=-1;
    foreach(preg_split('/\r\n|\r|\n/',$body)as$line) {
        $marker=preg_match('/^ {0,3}(`{3,}|~{3,})(.*)$/',$line,$m)?$m:null;
        if($fence!==null){if($marker&&$marker[1][0]===$fence[0]&&strlen($marker[1])>=strlen($fence)&&trim($marker[2])==='')$fence=null;continue;}
        if($marker){$fence=$marker[1];if($collecting)$finished=true;continue;}
        if(preg_match('/^ {0,3}(#{1,6})\s+(.+?)\s*$/',$line,$heading)) {
            $title=trim(preg_replace('/\s+#+$/','',$heading[2]));$collecting=$heading[1]==='##'&&fold($title)==='description for agents';
            if($collecting){$sections[]=[];$index=count($sections)-1;}$finished=false;continue;
        }
        if(!$collecting||$finished)continue;$text=trim($line);
        if($text===''){if($sections[$index])$finished=true;}
        elseif(str_starts_with($line,'    ')||str_starts_with($line,"\t")||preg_match('/^(?:>|[-*+]\s|\d+[.)]\s|!\[)/',$text))$finished=true;
        else $sections[$index][]=$text;
    }
    return count($sections)===1?clean_text(implode(' ',$sections[0]),262144):'';
}
function plugin_description(array $metadata): string {
    $widget=is_array($metadata['barWidget']??null)?$metadata['barWidget']:[];$descriptions=[];
    foreach([$metadata['description']??null,$widget['description']??null]as$value){
        if(!is_string($value))continue;$text=clean_text($value,100000);$duplicate=false;
        foreach($descriptions as$existing)if(str_contains(fold($existing),fold($text)))$duplicate=true;
        if($text!==''&&!$duplicate)$descriptions[]=$text;
    }
    $description=readme_description($metadata)?:implode("\n\n",$descriptions);
    return preg_match('/\A.{0,1200}\z/us',$description)?$description:shorten($description,1199).'…';
}
function plugin_author(array $manifest): string {
    $value=$manifest['author']??$manifest['authors']??null;
    // A declared author object is one person; only list arrays contain many.
    if(!is_array($value)||!array_is_list($value))$value=[$value];$names=[];
    foreach($value as$author){if(is_array($author))$author=$author['name']??null;if(is_string($author)&&trim($author)!=='')$names[]=clean_text($author,10000);}
    return shorten(implode(', ',$names),200);
}
function local_update_date(string $manifest,array $document): string {
    $files=[];
    if(basename($manifest)!=='manifest.json') {
        $files=[$manifest];foreach(($document['entryPoints']??[])as$entry)if(is_string($entry))$files[]=dirname($manifest).'/'.$entry;
    }else{
        $walk=function($path)use(&$walk,&$files){
            $entries=@scandir($path);if($entries===false)return;
            foreach($entries as$name){if(str_starts_with($name,'.'))continue;$file=$path.'/'.$name;
                if(is_dir($file)){if(!is_link($file)&&!in_array($name,['__pycache__','archive','node_modules','build'],true))$walk($file);}
                elseif(!str_ends_with($name,'.pyc')&&!str_ends_with($name,'.pyo'))$files[]=$file;
                if(count($files)>8192)return;
            }
        };$walk(dirname($manifest));if(count($files)>8192)return '';
    }
    $latest=null;foreach($files as$file)if(is_file($file)){$stamp=@filemtime($file);if($stamp!==false)$latest=max($latest??0,$stamp);}
    return $latest!==null?date('Y-m-d',$latest):'';
}
function author_cache(): array {$data=json_file(state_root().'/authors.json',[],1000000);return is_array($data)?$data:[];}
function first_commit_author(array $metadata,array &$cache): array {
    $directory=$metadata['sourceDir']??'';$manifest=$metadata['manifestPath']??'';if(!$directory||!$manifest)return [];
    try{
        $root=realpath(Updates\git($directory,['rev-parse','--show-toplevel']));if(!$root)return [];
        $head=Updates\git($root,['rev-parse','HEAD']);$paths=[$manifest];
        foreach(($metadata['entryPoints']??[])as$entry)if(is_string($entry))$paths[]=dirname($manifest).'/'.$entry;
        $paths=array_values(array_unique(array_map(fn($path)=>relative_path($path,$root),$paths)));sort($paths);
        $key=$root."\n".$head."\n".implode("\n",$paths);if(isset($cache[$key]))return $cache[$key];$candidates=[];
        foreach($paths as$path){$rows=trim(Updates\git($root,['log','--follow','--diff-filter=A','--format=%H%x1f%an%x1f%ct','--',$path],20));if($rows==='')continue;$lines=explode("\n",$rows);$parts=explode("\x1f",end($lines));if(count($parts)===3&&ctype_digit($parts[2]))$candidates[]=[(int)$parts[2],$parts[0],clean_text($parts[1],200)];}
        if(!$candidates)return $cache[$key]=[];sort($candidates);[$stamp,$commit,$author]=$candidates[0];
        return $cache[$key]=['author'=>$author,'authorSource'=>'first-commit','authorCommit'=>$commit,'authorDate'=>gmdate('Y-m-d',$stamp),'authorHistoryShallow'=>Updates\git($root,['rev-parse','--is-shallow-repository'])==='true'];
    }catch(\Throwable){return [];}
}
function plugin_details(array $metadata,array &$history): array {
    $path=$metadata['manifestPath']??null;$manifest=is_string($path)?json_file($path):[];if(!is_array($manifest))$manifest=[];
    $author=plugin_author($manifest);$result=['author'=>$author,'updatedDate'=>is_string($path)&&$manifest?local_update_date($path,$manifest):''];
    $provenance=is_array($manifest['omarchy']??null)?$manifest['omarchy']:[];
    if(is_string($provenance['clonedAtCommit']??null)&&preg_match('/\A[0-9a-f]{40}\z/D',$provenance['clonedAtCommit']))$result['sourceCommit']=$provenance['clonedAtCommit'];
    if(is_string($provenance['customizedBy']??null)&&trim($provenance['customizedBy'])!=='')$result['customizedBy']=clean_text($provenance['customizedBy'],200);
    if($author===''||in_array(fold($author),['omarchy','omarchy team','omacom'],true)){
        $inferred=first_commit_author($metadata,$history);
        if(!$inferred&&!empty($provenance['clonedFrom'])){$original=builtin_metadata($provenance['clonedFrom']);if($original)$inferred=first_commit_author($original,$history);if($inferred)$inferred['authorSource']='upstream-first-commit';}
        if($inferred)$result=[...$result,...$inferred];
    }
    return $result;
}
