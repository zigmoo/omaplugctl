<?php
declare(strict_types=1);
namespace OmaPlugCtl\Sources;
use function OmaPlugCtl\{home,state_root,ensure_directory,save_json,json_file,run,raw_run,process_result,locked,valid_id,clean_text,now,opens_without_bar};

const MAX_POSTS=8;
const MAX_REPOS=5;
const MAX_SHORT_HOPS=5;
const MAX_PROJECT_PAGES=2;
const MAX_LINKS=256;
/** Accept repository pages and GitHub file/branch links, never arbitrary hosts. */
function repository(string $url): ?string {
    if(strlen($url)>2048)return null;
    if (!preg_match('~\Ahttps://(?:www\.)?github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)(?:/(?:tree|blob|issues|pull|releases|commit|archive|discussions|wiki|tags|branches)(?:/[^\s]*)?)?/?(?:[?#][^\s]*)?\z~iD',$url,$m)
        && !preg_match('~\Ahttps://raw\.githubusercontent\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)/[^\s]+\z~iD',$url,$m)) return null;
    $name=preg_replace('/\.git\z/','',$m[2]);
    if($name===''||$name==='.'||str_contains($name,'..'))return null;
    return 'https://github.com/'.$m[1].'/'.$name;
}
function post_id(string $url): ?string {
    return preg_match('~\Ahttps://(?:(?:www|mobile|m)\.)?(?:x\.com|twitter\.com)/(?:[A-Za-z0-9_]{1,15}|i/web)/status/([0-9]{1,25})(?:/(?:photo|video)/[0-9]+)?/?(?:[?#][^\s]*)?\z~iD',$url,$m)?$m[1]:null;
}
function short_url(string $url): bool {
    return strlen($url)<=2048
        && preg_match('~\Ahttps://(?:t\.co|bit\.ly|tinyurl\.com|git\.io|ow\.ly|buff\.ly)/[A-Za-z0-9_-]{1,80}(?:[?#][^\s]*)?\z~iD',$url)===1;
}
function expand_short_url(string $url,int &$remainingHops): string {
    $seen=[];
    while (short_url($url)) {
        if ($remainingHops===0 || isset($seen[$url])) throw new \RuntimeException('Too many redirects in this short link.');
        $seen[$url]=true;
        $remainingHops--;
        // Read one Location from each supported shortener.
        $result=process_result(['curl','--disable','--silent','--show-error','--proto','=https',
            '--connect-timeout','3','--max-time','5','--max-filesize','65536','--output','/dev/null',
            '--write-out',"%{http_code}\n%{redirect_url}",'--',$url],6,null,null,4096);
        [$status,$target]=array_pad(explode("\n",trim($result['stdout']),2),2,'');
        if ($result['code']!==0 || !in_array($status,['301','302','303','307','308'],true) || $target==='' || strlen($target)>2048) {
            throw new \RuntimeException('Could not expand this short link. Paste the original post or plugin link.');
        }
        $url=$target;
    }
    return $url;
}
function source_candidate(string $url): ?array {
    $repo=repository($url);
    if ($repo!==null) return ['repo'=>$repo];
    if (!preg_match('~\Ahttps://plugins\.omarchy\.org/plugin\.html\?id=([A-Za-z0-9._-]{1,160})(?:[&#][^\s]*)?\z~D',$url,$match)) return null;
    $entry=\OmaPlugCtl\Marketplace\entry($match[1]);
    $repo=repository($entry['repo']);
    if ($repo===null) throw new \RuntimeException('No supported HTTPS source repository is available for this plugin.');
    return ['repo'=>$repo,'id'=>$entry['id'],'installNote'=>$entry['installable']?'':($entry['installNote']??'')];
}
function project_page(string $url): bool {
    return strlen($url)<=2048
        && preg_match('~\Ahttps://(?:[A-Za-z0-9-]{1,63}\.github\.io|(?:www\.)?omarchy\.org)(?:/[^\s]*)?\z~iD',$url)===1;
}
function project_page_links(string $url): array {
    $document=raw_run(['curl','--disable','--fail','--silent','--show-error','--proto','=https',
        '--connect-timeout','3','--max-time','7','--max-filesize','524288','--',$url],8,null,null,524288);
    preg_match_all("~\bhref\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^>\s]+))~i",$document,$matches,PREG_SET_ORDER);
    $links=[];
    foreach ($matches as $match) {
        $link=html_entity_decode($match[1]?:($match[2]?:$match[3]),ENT_QUOTES|ENT_HTML5,'UTF-8');
        if (str_starts_with($link,'//')) $link='https:'.$link;
        if (str_starts_with($link,'https://') && !project_page($link)) $links[]=$link;
        if (count($links)>=MAX_LINKS) break;
    }
    return array_values(array_unique($links));
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
    $expanded=[];
    foreach(array_slice($post['entities']['urls']??[],0,100)as$link) {
        if(!is_array($link)||!is_string($link['expanded_url']??null)) continue;
        if (is_string($link['url']??null)) $expanded[$link['url']]=$link['expanded_url'];
        $text.=' '.$link['expanded_url'];
    }
    preg_match_all('~https://[^\s<>"\x27]+~',substr($text,0,131072),$matches);
    return array_values(array_unique(array_map(function($url)use($expanded) {
        $url=rtrim($url,').,;!');
        return $expanded[$url]??$url;
    },$matches[0])));
}
function discover(string $url,?callable $fetch=null): array {
    $shortHops=MAX_SHORT_HOPS;$pages=0;
    $fetch??=__NAMESPACE__.'\\download_post';
    $queue=[trim($url)];$seenPosts=[];$repos=[];$seenLinks=[];
    while ($queue && count($seenLinks)<MAX_LINKS) {
        $candidate=array_shift($queue);
        if (isset($seenLinks[$candidate])) continue;
        $initial=$seenLinks===[];
        $seenLinks[$candidate]=true;
        try {
            $link=expand_short_url($candidate,$shortHops);
            $source=source_candidate($link);
            $links=[];
            if ($source!==null) {
                $key=strtolower($source['repo']);
                if (!isset($repos[$key]['id'])) $repos[$key]=$source;
            } elseif (($id=post_id($link))!==null) {
                if (isset($seenPosts[$id]) || count($seenPosts)>=MAX_POSTS) continue;
                $seenPosts[$id]=true;
                $post=$fetch($id);
                $posts=[$post];
                foreach (['quoted_tweet','parent'] as $key) if (is_array($post[$key]??null)) $posts[]=$post[$key];
                foreach ($posts as $item) {
                    $links=array_merge($links,post_links($item));
                    $parent=$item['in_reply_to_status_id_str']??null;
                    if (is_string($parent) && ctype_digit($parent)) $links[]='https://x.com/i/web/status/'.$parent;
                }
            } elseif (project_page($link) && $pages<MAX_PROJECT_PAGES) {
                $pages++;
                $links=project_page_links($link);
            } elseif ($initial) {
                throw new \InvalidArgumentException('Use an HTTPS GitHub repository, X post, Omarchy Marketplace, or supported project link.');
            }
            $queue=array_merge($queue,array_slice($links,0,max(0,MAX_LINKS-count($seenLinks)-count($queue))));
        } catch (\RuntimeException|\InvalidArgumentException $error) {
            if ($initial) throw $error;
            continue;
        }
        if (count($repos)>MAX_REPOS) throw new \RuntimeException('This link leads to too many repositories. Paste the repository you want directly.');
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
function evaluate(string $repo,?string $expectedId=null,string $installNote=''): array {
    $token=bin2hex(random_bytes(16));$directory=stage_path($token);ensure_directory($directory);$root=$directory.'/tree';
    try {
        git($directory,['clone','--quiet','--depth=1','--single-branch','--no-checkout','--',$repo,$root],90);
        $commit=git($root,['rev-parse','HEAD']);$manifest=inspect_tree($root,$commit);
        if ($expectedId!==null && $manifest['id']!==$expectedId) {
            throw new \RuntimeException('The repository declares a different plugin id than the marketplace listing.');
        }
        $scan=\OmaPlugCtl\Malware\scan_commit($root,$commit);
        git($root,['checkout','--quiet','HEAD']);
        run(['omarchy-plugin-validate',$root]);
        $row=['id'=>$manifest['id'],'name'=>clean_text($manifest['name']??$manifest['id'],160),'description'=>clean_text($manifest['description']??'',1200),'author'=>clean_text(is_string($manifest['author']??null)?$manifest['author']:'',160),'version'=>clean_text($manifest['version']??'',120),'license'=>clean_text($manifest['license']??'',120),'repo'=>$repo,'verified'=>false,'coverage'=>'locally-validated','verifiedCommit'=>$commit,'installable'=>true,'directSource'=>true,'evaluation'=>$token,'validation'=>'Manifest valid; ClamAV found no threats. Commit '.substr($commit,0,12).'.','installed'=>false,'enabled'=>false];
        $row['kinds']=array_slice($manifest['kinds'],0,32);
        if ($installNote!=='') $row['installNote']=$installNote;
        save_json(['entry'=>$row,'commit'=>$commit,'scan'=>$scan,'checkedAt'=>time()],$directory.'/evaluation.json');
        return $row;
    }catch(\Throwable $error){remove_stage($directory);return ['id'=>$expectedId??$repo,'name'=>basename($repo),'repo'=>$repo,'description'=>$error->getMessage(),'author'=>'','verified'=>false,'coverage'=>'validation-failed','installable'=>false,'directSource'=>true,'installed'=>false,'enabled'=>false,'validation'=>'Installation blocked.','installNote'=>$installNote];}
}
function check(?string $url): array {
    if($url===null||strlen($url)>2048)throw new \InvalidArgumentException('Paste a URL of at most 2048 characters.');
    $repos=discover($url);
    return locked(state_root().'/marketplace.install.lock',function()use($repos){
        prune_stages(count($repos));
        $entries=[];
        foreach($repos as $source) $entries[]=evaluate($source['repo'],$source['id']??null,$source['installNote']??'');
        $passed=count(array_filter($entries,fn($row)=>$row['installable']));
        return ['sourceEntries'=>$entries,'message'=>$passed.' of '.count($entries).' repositories passed local validation. Checks do not execute plugin code or guarantee safety. X lookup covers public post content and linked/quoted posts, not every reply.'];
    });
}
function prune_stages(int $incoming): void {
    // Staged downloads are disposable runtime cache, bounded to 16 checks
    // and one day. Never touch installed plugins during cache eviction.
    $stages=array_filter(glob(state_root().'/sources/*')?:[],fn($path)=>preg_match('/\A[0-9a-f]{32}\z/D',basename($path))===1);
    usort($stages,fn($a,$b)=>filemtime($a)<=>filemtime($b));
    foreach($stages as$index=>$path)if(filemtime($path)<time()-86400||$index<count($stages)+$incoming-16)remove_stage($path);
}
function evaluated(string $token): array {
    $directory=stage_path($token);$value=json_file($directory.'/evaluation.json',null,16384);
    if(!is_array($value)||!is_int($value['checkedAt']??null)||time()-$value['checkedAt']>86400||empty($value['entry']['installable']))throw new \RuntimeException('Evaluation expired or unavailable. Evaluate the URL again.');
    return $value;
}
function install(?string $token): array {
    return locked(state_root().'/marketplace.install.lock',fn()=>install_evaluated($token??''));
}
function reinstall(string $repo,string $expectedId): array {
    return locked(state_root().'/marketplace.install.lock',function()use($repo,$expectedId) {
        if (isset(\OmaPlugCtl\Marketplace\installed_plugins()[$expectedId])) {
            throw new \InvalidArgumentException('This plugin is already installed.');
        }
        prune_stages(1);
        $entry=evaluate($repo);
        if (empty($entry['installable'])) throw new \RuntimeException($entry['description']??'Could not evaluate the favorite repository.');
        if ($entry['id']!==$expectedId) {
            remove_stage(stage_path($entry['evaluation']));
            throw new \RuntimeException('The saved repository now declares a different plugin id. No plugin was installed.');
        }
        return install_evaluated($entry['evaluation']);
    });
}
function install_evaluated(string $token): array {
        $value=evaluated($token);$row=$value['entry'];$id=$row['id'];$directory=stage_path($token);$root=$directory.'/tree';
    $plugins=home().'/.config/omarchy/plugins';$target=$plugins.'/'.$id;
    // A previous attempt may have moved the checked tree before the shell discovered it.
    if (!is_dir($root) && !is_link($target) && is_dir($target.'/.git') && git($target,['rev-parse','HEAD'])===$value['commit']) {
        return confirm_install($value,$directory);
    }
        if(isset(\OmaPlugCtl\Marketplace\installed_plugins()[$id]))throw new \RuntimeException('This plugin id is already installed. Your existing plugin was preserved.');
        if(git($root,['rev-parse','HEAD'])!==$value['commit']||git($root,['status','--porcelain','--untracked-files=all','--ignored=matching'])!=='')throw new \RuntimeException('Evaluated files changed. Evaluate the URL again.');
        inspect_tree($root,$value['commit']);run(['omarchy-plugin-validate',$root]);
        \OmaPlugCtl\Malware\scan_commit($root,$value['commit']);
        if(git($root,['rev-parse','HEAD'])!==$value['commit']||git($root,['status','--porcelain','--untracked-files=all','--ignored=matching'])!=='')throw new \RuntimeException('Evaluated files changed during scanning. Evaluate the URL again.');
    ensure_directory($plugins);
        if(file_exists($target)||is_link($target))throw new \RuntimeException('Plugin destination already exists. Your files were preserved.');
        if(!@rename($root,$target))throw new \RuntimeException('Could not move the evaluated plugin into place. No installation was confirmed.');
    return confirm_install($value,$directory);
}
function confirm_install(array $value,string $directory): array {
    $row=$value['entry'];
    run(['omarchy-shell','shell','rescanPlugins']);
    $installed=\OmaPlugCtl\Marketplace\wait_for_discovery($row['id']);
    if ($installed===null) throw new \RuntimeException($row['name'].' is on disk. Click Retry to check whether Omarchy has loaded it.');
    $row['installed']=true;$row['enabled']=($installed['enabled']??false)===true;
    $row['opensWithoutBar']=opens_without_bar($installed['kinds']??$row['kinds']);
    $value['entry']=$row;save_json($value,$directory.'/evaluation.json');
    $message=$row['name'].($row['enabled']?' is already enabled.':' installed at checked commit '.substr($value['commit'],0,12).'. Click Enable when ready.');
    return ['sourceEntries'=>[$row],'message'=>$message];
}
function enable(?string $token): array {
    $value=evaluated($token??'');$row=$value['entry'];
    if(empty($row['installed']))throw new \RuntimeException('Install this evaluated plugin before enabling it.');
    run(['omarchy','plugin','enable',$row['id']]);
    $installed=\OmaPlugCtl\Marketplace\installed_plugins()[$row['id']]??null;
    if(($installed['enabled']??null)!==true)throw new \RuntimeException('Enabling was not confirmed by Omarchy.');
    $row['enabled']=true;$row['opensWithoutBar']=opens_without_bar($installed['kinds']??$row['kinds']);
    $value['entry']=$row;save_json($value,stage_path($token).'/evaluation.json');
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
