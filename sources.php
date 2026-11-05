<?php
declare(strict_types=1);
namespace OmaPlugCtl\Sources;
use function OmaPlugCtl\{home,state_root,ensure_directory,save_json,json_file,run,raw_run,process_result,locked,valid_id,clean_text,now};

const MAX_POSTS=8;
const MAX_REPOS=5;
/** Accept repository pages and GitHub file/branch links, never arbitrary hosts. */
function repository(string $url): ?string {
    if(strlen($url)>2048)return null;
    if(!preg_match('~\Ahttps://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)(?:/(?:tree|blob|issues|pull|releases|commit)(?:/[^\s]*)?)?/?(?:[?#][^\s]*)?\z~D',$url,$m))return null;
    $name=preg_replace('/\.git\z/','',$m[2]);
    if($name===''||$name==='.'||str_contains($name,'..'))return null;
    return 'https://github.com/'.$m[1].'/'.$name;
}
function post_id(string $url): ?string {
    return preg_match('~\Ahttps://(?:www\.)?(?:x\.com|twitter\.com)/(?:[A-Za-z0-9_]{1,15}|i/web)/status/([0-9]{1,25})(?:/(?:photo|video)/[0-9]+)?/?(?:[?#][^\s]*)?\z~D',$url,$m)?$m[1]:null;
}
function download_post(string $id): array {
    $result=process_result(['curl','--fail','--silent','--show-error','--proto','=https','--max-time','15','--max-filesize','1048576','--write-out',"\n%{http_code}",'https://cdn.syndication.twimg.com/tweet-result?id='.$id.'&lang=en&token=0'],20,null,null,1049600);
    $split=strrpos($result['stdout'],"\n");
    if($result['code']!==0||$split===false||substr($result['stdout'],$split+1)!=='200')throw new \RuntimeException('Could not retrieve this public X post. Paste its GitHub repository URL instead.');
    $post=json_decode(substr($result['stdout'],0,$split),true,64,JSON_THROW_ON_ERROR);
    if(!is_array($post)||($post['id_str']??null)!==$id)throw new \RuntimeException('This X post is unavailable. Paste its GitHub repository URL instead.');
    return $post;
}
/** Extract links only from post content/entities, never profiles or media. */
function post_links(array $post): array {
    $text=is_string($post['text']??null)?$post['text']:'';
    foreach(array_slice($post['entities']['urls']??[],0,100)as$link)if(is_array($link)&&is_string($link['expanded_url']??null))$text.=' '.$link['expanded_url'];
    preg_match_all('~https://[^\s<>"\x27]+~',substr($text,0,131072),$matches);
    return array_values(array_unique(array_map(fn($url)=>rtrim($url,').,;!'),$matches[0])));
}
function discover(string $url,?callable $fetch=null): array {
    $url=trim($url);$repo=repository($url);if($repo!==null)return [$repo];
    $id=post_id($url);if($id===null)throw new \InvalidArgumentException('Paste an HTTPS GitHub repository URL or an X post URL.');
    $fetch??=__NAMESPACE__.'\\download_post';$queue=[$id];$seen=[];$repos=[];
    while($queue&&count($seen)<MAX_POSTS) {
        $id=array_shift($queue);if(isset($seen[$id]))continue;$seen[$id]=true;$post=$fetch($id);
        $posts=[$post];foreach(['quoted_tweet','parent']as$key)if(is_array($post[$key]??null))$posts[]=$post[$key];
        foreach($posts as$item) {
            foreach(post_links($item)as$link) {
                $repo=repository($link);if($repo!==null)$repos[strtolower($repo)]=$repo;
                elseif(($next=post_id($link))!==null&&!isset($seen[$next]))$queue[]=$next;
            }
            $parent=$item['in_reply_to_status_id_str']??null;if(is_string($parent)&&ctype_digit($parent)&&!isset($seen[$parent]))$queue[]=$parent;
        }
        if(count($repos)>MAX_REPOS)throw new \RuntimeException('This thread links too many repositories. Paste the repository you want directly.');
    }
    if(!$repos)throw new \RuntimeException('No GitHub repository link found in the accessible post or linked thread posts. Replies may be unavailable; paste the specific post containing the link or its GitHub URL.');
    return array_values($repos);
}
function git(string $root,array $args,int $timeout=30): string {
    // Inspection must not run user-configured Git hooks, filters or URL rewrites.
    $env=[...getenv(),'GIT_CONFIG_NOSYSTEM'=>'1','GIT_CONFIG_GLOBAL'=>'/dev/null','GIT_CONFIG_COUNT'=>'0','GIT_TERMINAL_PROMPT'=>'0','GIT_LFS_SKIP_SMUDGE'=>'1'];
    unset($env['GIT_DIR'],$env['GIT_WORK_TREE'],$env['GIT_INDEX_FILE'],$env['GIT_OBJECT_DIRECTORY'],$env['GIT_ALTERNATE_OBJECT_DIRECTORIES'],$env['GIT_CONFIG']);
    return trim(raw_run(['git','-c','core.hooksPath=/dev/null','-c','protocol.allow=never','-c','protocol.https.allow=always','-c','http.followRedirects=false','-C',$root,...$args],$timeout,null,$env));
}
function remove_stage(string $path): void {
    if(is_link($path)||!is_dir($path)){if(file_exists($path)||is_link($path))unlink($path);return;}
    foreach(new \FilesystemIterator($path,\FilesystemIterator::SKIP_DOTS)as$file)remove_stage($file->getPathname());
    rmdir($path);
}
function stage_path(string $token): string {
    if(!preg_match('/\A[0-9a-f]{32}\z/D',$token))throw new \InvalidArgumentException('Invalid evaluation. Evaluate the URL again.');
    return state_root().'/sources/'.$token;
}
function inspect_tree(string $root,string $commit): array {
    // Bound the complete tree before checkout. No submodule, LFS or symlink can
    // bypass coverage or pull files from outside the evaluated repository.
    $listing=git($root,['ls-tree','-rlz','--full-tree',$commit]);$bytes=0;$count=0;
    foreach(explode("\0",$listing)as$row) {
        if($row==='')continue;$parts=explode("\t",$row,2);$head=preg_split('/\s+/',trim($parts[0]));
        if(count($parts)!==2||count($head)!==4||!in_array($head[0],['100644','100755'],true)||$head[1]!=='blob'||!ctype_digit($head[3]))throw new \RuntimeException('Only regular files are supported; symlinks and submodules block installation.');
        $bytes+=(int)$head[3];$count++;
        if($bytes>\OmaPlugCtl\Malware\MAX_BYTES||$count>\OmaPlugCtl\Malware\MAX_FILES)throw new \RuntimeException('Repository exceeds the complete-scan limit.');
    }
    $manifest=json_decode(git($root,['show',$commit.':manifest.json']),true,64,JSON_THROW_ON_ERROR);
    if(!is_array($manifest)||!valid_id($manifest['id']??null)||str_starts_with($manifest['id'],'omarchy.'))throw new \RuntimeException('The repository needs a root Omarchy plugin manifest with a non-reserved id.');
    return $manifest;
}
function evaluate(string $repo): array {
    $token=bin2hex(random_bytes(16));$directory=stage_path($token);ensure_directory($directory);$root=$directory.'/tree';
    try {
        git($directory,['clone','--quiet','--depth=1','--single-branch','--no-checkout','--',$repo,$root],90);
        $commit=git($root,['rev-parse','HEAD']);$manifest=inspect_tree($root,$commit);
        $scan=\OmaPlugCtl\Malware\scan_commit($root,$commit);
        git($root,['checkout','--quiet','HEAD']);
        run(['omarchy-plugin-validate',$root]);
        $row=['id'=>$manifest['id'],'name'=>clean_text($manifest['name']??$manifest['id'],160),'description'=>clean_text($manifest['description']??'',1200),'author'=>clean_text(is_string($manifest['author']??null)?$manifest['author']:'',160),'version'=>clean_text($manifest['version']??'',120),'license'=>clean_text($manifest['license']??'',120),'repo'=>$repo,'verified'=>false,'coverage'=>'locally-validated','verifiedCommit'=>$commit,'installable'=>true,'directSource'=>true,'evaluation'=>$token,'validation'=>'Manifest valid; ClamAV found no threats. Commit '.substr($commit,0,12).'.','installed'=>false,'enabled'=>false];
        $row['kinds']=array_slice($manifest['kinds'],0,32);
        save_json(['entry'=>$row,'commit'=>$commit,'scan'=>$scan,'checkedAt'=>time()],$directory.'/evaluation.json');
        return $row;
    }catch(\Throwable $error){remove_stage($directory);return ['id'=>$repo,'name'=>basename($repo),'repo'=>$repo,'description'=>$error->getMessage(),'author'=>'','verified'=>false,'coverage'=>'validation-failed','installable'=>false,'directSource'=>true,'installed'=>false,'enabled'=>false,'validation'=>'Installation blocked.'];}
}
function check(?string $url): array {
    if($url===null||strlen($url)>2048)throw new \InvalidArgumentException('Paste a URL of at most 2048 characters.');
    $repos=discover($url);
    return locked(state_root().'/marketplace.install.lock',function()use($repos){
        // Staged downloads are disposable runtime cache, bounded to 16 checks
        // and one day. Never touch installed plugins during cache eviction.
        $stages=array_filter(glob(state_root().'/sources/*')?:[],fn($path)=>preg_match('/\A[0-9a-f]{32}\z/D',basename($path))===1);
        usort($stages,fn($a,$b)=>filemtime($a)<=>filemtime($b));
        foreach($stages as$index=>$path)if(filemtime($path)<time()-86400||$index<count($stages)+count($repos)-16)remove_stage($path);
        $entries=[];foreach($repos as$repo)$entries[]=evaluate($repo);
        $passed=count(array_filter($entries,fn($row)=>$row['installable']));
        return ['sourceEntries'=>$entries,'message'=>$passed.' of '.count($entries).' repositories passed local validation. Checks do not execute plugin code or guarantee safety. X lookup covers public post content and linked/quoted posts, not every reply.'];
    });
}
function evaluated(string $token): array {
    $directory=stage_path($token);$value=json_file($directory.'/evaluation.json',null,16384);
    if(!is_array($value)||!is_int($value['checkedAt']??null)||time()-$value['checkedAt']>86400||empty($value['entry']['installable']))throw new \RuntimeException('Evaluation expired or unavailable. Evaluate the URL again.');
    return $value;
}
function install(?string $token): array {
    $token??='';
    return locked(state_root().'/marketplace.install.lock',function()use($token){
        $value=evaluated($token);$row=$value['entry'];$id=$row['id'];$directory=stage_path($token);$root=$directory.'/tree';
        if(isset(\OmaPlugCtl\Marketplace\installed_plugins()[$id]))throw new \RuntimeException('This plugin id is already installed. Your existing plugin was preserved.');
        if(git($root,['rev-parse','HEAD'])!==$value['commit']||git($root,['status','--porcelain','--untracked-files=all','--ignored=matching'])!=='')throw new \RuntimeException('Evaluated files changed. Evaluate the URL again.');
        inspect_tree($root,$value['commit']);run(['omarchy-plugin-validate',$root]);
        \OmaPlugCtl\Malware\scan_commit($root,$value['commit']);
        if(git($root,['rev-parse','HEAD'])!==$value['commit']||git($root,['status','--porcelain','--untracked-files=all','--ignored=matching'])!=='')throw new \RuntimeException('Evaluated files changed during scanning. Evaluate the URL again.');
        $plugins=home().'/.config/omarchy/plugins';ensure_directory($plugins);$target=$plugins.'/'.$id;
        if(file_exists($target)||is_link($target))throw new \RuntimeException('Plugin destination already exists. Your files were preserved.');
        if(!@rename($root,$target))throw new \RuntimeException('Could not move the evaluated plugin into place. No installation was confirmed.');
        run(['omarchy-shell','shell','rescanPlugins']);
        $installed=\OmaPlugCtl\Marketplace\installed_plugins()[$id]??null;
        if($installed===null||!empty($installed['enabled']))throw new \RuntimeException('Installation could not confirm the plugin is disabled. Inspect it in Plugins.');
        $row['installed']=true;$row['enabled']=false;$value['entry']=$row;save_json($value,$directory.'/evaluation.json');
        return ['sourceEntries'=>[$row],'message'=>$row['name'].' installed at evaluated commit '.substr($value['commit'],0,12).', disabled. Click Enable when ready.'];
    });
}
function enable(?string $token): array {
    $value=evaluated($token??'');$row=$value['entry'];
    if(empty($row['installed']))throw new \RuntimeException('Install this evaluated plugin before enabling it.');
    run(['omarchy','plugin','enable',$row['id']]);
    if((\OmaPlugCtl\Marketplace\installed_plugins()[$row['id']]['enabled']??null)!==true)throw new \RuntimeException('Enabling was not confirmed by Omarchy.');
    $row['enabled']=true;$value['entry']=$row;save_json($value,stage_path($token).'/evaluation.json');
    return ['sourceEntries'=>[$row],'message'=>$row['name'].' enabled.'];
}
function open(?string $url): array {
    $repo=repository($url??'');if($repo===null)throw new \InvalidArgumentException('Invalid GitHub repository URL.');
    run(['xdg-open',$repo]);return ['message'=>'Opened source page.'];
}
function commit_details(mixed $payload): array {
    $commit=is_array($payload)&&array_is_list($payload)?($payload[0]??null):null;
    if(!is_array($commit)||!preg_match('/\A[0-9a-f]{40}\z/D',$commit['sha']??'')||!is_string($commit['commit']['committer']['date']??null)||strtotime($commit['commit']['committer']['date'])===false)throw new \RuntimeException('Latest commit metadata is unavailable.');
    return ['commit'=>$commit['sha'],'lastCommitAt'=>$commit['commit']['committer']['date'],'commitAuthor'=>clean_text($commit['commit']['author']['name']??'',160),'commitSubject'=>clean_text(explode("\n",$commit['commit']['message']??'')[0],300),'error'=>''];
}
function details(?string $url): array {
    $repo=repository($url??'');if($repo===null)throw new \InvalidArgumentException('Invalid GitHub repository URL.');
    $path=state_root().'/repository-details/'.hash('sha256',strtolower($repo)).'.json';$cached=json_file($path,null,8192);
    if(is_array($cached)&&is_int($cached['checkedAt']??null)&&time()-$cached['checkedAt']<3600)return ['repo'=>$repo,'details'=>$cached];
    try {
        $api='https://api.github.com/repos/'.substr($repo,strlen('https://github.com/')).'/commits?per_page=1';
        $result=process_result(['curl','--fail','--silent','--show-error','--proto','=https','--max-time','10','--max-filesize','1048576','--user-agent','OmaPlugCtl','--write-out',"\n%{http_code}",$api],12,null,null,1049600);
        $split=strrpos($result['stdout'],"\n");
        if($result['code']!==0||$split===false||substr($result['stdout'],$split+1)!=='200')throw new \RuntimeException('Latest commit unavailable (connection or GitHub rate limit).');
        $value=commit_details(json_decode(substr($result['stdout'],0,$split),true,64,JSON_THROW_ON_ERROR));
    }catch(\Throwable){$value=is_array($cached)?$cached:[];$value['error']='Latest commit unavailable (connection or GitHub rate limit).';}
    $value['checkedAt']=time();save_json($value,$path);return ['repo'=>$repo,'details'=>$value];
}
