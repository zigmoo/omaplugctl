<?php
declare(strict_types=1);
namespace OmaPlugCtl;

const SELF = 'moo.omaplugctl';
const SECTIONS = ['left','centerBegin','center','centerEnd','right','tray'];
const EDGES = ['top','bottom','left','right'];
const SORT_ORDERS = ['name','screen','updates'];
function home(): string { return rtrim(getenv('HOME')?:throw new \RuntimeException('HOME is unset.'),'/'); }
function state_root(): string { return rtrim(getenv('XDG_STATE_HOME')?:home().'/.local/state','/').'/omarchy/omaplugctl'; }
function ensure_directory(string $path): void {
    if (!is_dir($path) && !@mkdir($path,0700,true) && !is_dir($path)) throw new \RuntimeException('Could not create runtime storage.');
}
function json_file(string $path, mixed $fallback=[], int $limit=33554432): mixed {
    clearstatcache(true,$path);
    if (!is_file($path) || filesize($path)>$limit) return $fallback;
    try { return json_decode(file_get_contents($path),true,512,JSON_THROW_ON_ERROR); } catch (\Throwable) { return $fallback; }
}
function save_json(mixed $value,string $path): void {
    ensure_directory(dirname($path));$temporary=dirname($path).'/.write-'.bin2hex(random_bytes(8));
    try {
        if (file_put_contents($temporary,json_encode($value,JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE))===false || !rename($temporary,$path)) throw new \RuntimeException('Could not save runtime state.');
    } finally { if (is_file($temporary)) @unlink($temporary); }
}
function locked(string $path,callable $operation,bool $blocking=false): mixed {
    ensure_directory(dirname($path));$handle=fopen($path,'c');
    if (!$handle || !flock($handle,LOCK_EX|($blocking?0:LOCK_NB))) { if (is_resource($handle)) fclose($handle);throw new \RuntimeException('This operation is already running.'); }
    try { return $operation(); } finally { flock($handle,LOCK_UN);fclose($handle); }
}
function fold(string $text): string {
    static $map=null;
    if ($map===null) $map=json_decode(file_get_contents(__DIR__.'/unicode-casefold.json'),true,512,JSON_THROW_ON_ERROR);
    return strtr($text,$map);
}
function shorten(string $text,int $characters): string {
    if(strlen($text)<=$characters)return $text;
    if($characters<=65535)return preg_match('/\A.{0,'.$characters.'}/us',$text,$match)?$match[0]:substr($text,0,$characters);
    $parts=preg_split('//u',$text,-1,PREG_SPLIT_NO_EMPTY);return $parts===false?substr($text,0,$characters):implode('',array_slice($parts,0,$characters));
}
function clean_text(mixed $text,int $limit): string { return is_string($text)?shorten(trim(preg_replace('/\s+/u',' ',$text)??''),$limit):''; }
function valid_id(mixed $id): bool { return is_string($id) && preg_match('/\A[A-Za-z0-9][A-Za-z0-9._-]{0,159}\z/D',$id)===1 && !str_contains($id,'..'); }
function validate_id(mixed $id): string { if (!valid_id($id)) throw new \InvalidArgumentException('Invalid plugin id.'); return $id; }
function now(): string { return gmdate('Y-m-d\TH:i:s').sprintf('.%06d',(int)((microtime(true)*1000000)%1000000)).'+00:00'; }
function executable(string $name): ?string {
    foreach (explode(PATH_SEPARATOR,getenv('PATH')?:'') as $directory) if (is_file($directory.'/'.$name) && is_executable($directory.'/'.$name)) return $directory.'/'.$name;
    return null;
}
/** Direct argv execution, bounded pipes/files, optional private stdin, deadline. */
function process_result(array $argv,int $timeout=25,?string $input=null,?array $environment=null,int $limit=8388608,?string $outputPath=null,?string $inputPath=null): array {
    $temporary=null;
    if ($input!==null) {
        ensure_directory(state_root());$temporary=state_root().'/.input-'.bin2hex(random_bytes(8));
        if (file_put_contents($temporary,$input)===false) throw new \RuntimeException('Could not prepare command input.');
        $inputPath=$temporary;
    }
    $descriptors=[0=>['file',$inputPath??'/dev/null','r'],1=>$outputPath===null?['pipe','w']:['file',$outputPath,'w'],2=>['pipe','w']];
    $pipes=[];$process=proc_open($argv,$descriptors,$pipes,null,$environment);
    if (!is_resource($process)) { if ($temporary) @unlink($temporary);throw new \RuntimeException('Could not start command.'); }
    foreach ($pipes as $pipe) stream_set_blocking($pipe,false);
    $output='';$error='';$exit=-1;$deadline=microtime(true)+$timeout;
    try {
        while (true) {
            $read=array_values(array_filter($pipes,fn($pipe)=>!feof($pipe)));
            if ($read) {
                $write=null;$except=null;
                if (@stream_select($read,$write,$except,0,20000)!==false) foreach ($read as $pipe) {
                    $chunk=fread($pipe,65536);
                    if ($pipe===($pipes[1]??null)) $output.=$chunk; else $error.=$chunk;
                }
            }
            if ($outputPath!==null) clearstatcache(true,$outputPath);
            if (strlen($output)+strlen($error)>$limit || ($outputPath!==null && is_file($outputPath) && filesize($outputPath)>$limit)) throw new \RuntimeException('Command output exceeds the supported limit.');
            $status=proc_get_status($process);
            if (!$status['running']) {
                $exit=$status['exitcode'];
                foreach ($pipes as $index=>$pipe) { $chunk=stream_get_contents($pipe);if ($index===1) $output.=$chunk;else $error.=$chunk; }
                if ($outputPath!==null) clearstatcache(true,$outputPath);
                if (($outputPath!==null && is_file($outputPath) && filesize($outputPath)>$limit) || strlen($output)+strlen($error)>$limit) throw new \RuntimeException('Command output exceeds the supported limit.');
                break;
            }
            if (microtime(true)>$deadline) throw new \RuntimeException('The command timed out. Refresh to check its actual state.');
        }
    } catch (\Throwable $exception) {
        proc_terminate($process);usleep(50000);
        if (proc_get_status($process)['running']) proc_terminate($process,9);
        throw $exception;
    } finally {
        foreach ($pipes as $pipe) fclose($pipe);proc_close($process);if ($temporary) @unlink($temporary);
    }
    return ['code'=>$exit,'stdout'=>$output,'stderr'=>$error];
}
function raw_run(array $argv,int $timeout=25,?string $input=null,?array $environment=null,int $limit=8388608): string {
    $result=process_result($argv,$timeout,$input,$environment,$limit);
    if ($result['code']!==0) throw new \RuntimeException(shorten(trim($result['stderr'])?:trim($result['stdout'])?:'The command failed.',1800));
    return $result['stdout'];
}
function run(array $argv,int $timeout=25): string { return trim(raw_run($argv,$timeout)); }
function relative_path(string $path,string $root): string {
    $path=realpath($path)?:$path;$root=rtrim(realpath($root)?:$root,'/');
    if (!str_starts_with($path,$root.'/')) throw new \RuntimeException('The plugin path is outside its source repository.');
    return substr($path,strlen($root)+1);
}
function config(): array {
    $value=json_file(home().'/.config/omarchy/shell.json',null);
    if (!is_array($value)) throw new \RuntimeException('Could not read Omarchy shell configuration.');
    return $value;
}
function catalog(): array {
    $value=json_decode(run(['omarchy-plugin-catalog']),true,512,JSON_THROW_ON_ERROR);
    if (!is_array($value) || !array_is_list($value) || count($value)>10000) throw new \RuntimeException('Could not read the plugin catalog.');
    return $value;
}
function metadata_map(): array { $result=[];foreach(catalog() as $row) if(is_array($row)&&is_string($row['id']??null))$result[$row['id']]=$row;return $result; }
// Match Python's local filesystem dates without requiring php.ini settings.
$zone=realpath('/etc/localtime');
if (getenv('TZ')) @date_default_timezone_set(getenv('TZ'));
elseif (is_string($zone) && str_contains($zone,'/zoneinfo/')) @date_default_timezone_set(explode('/zoneinfo/',$zone,2)[1]);
