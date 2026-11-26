<?php
declare(strict_types=1);
namespace OmaPlugCtl;
use OmaPlugCtl\Marketplace as Marketplace;
use OmaPlugCtl\Sources as Sources;
use OmaPlugCtl\Updates as Updates;

function favorite_records(): array {
    $path=state_root().'/favorites.json';
    if (!file_exists($path)) return [];
    $rows=json_file($path,null,4194304);
    if (!is_array($rows) || !array_is_list($rows) || count($rows)>1000) {
        throw new \RuntimeException('The saved favorites could not be read.');
    }
    $favorites=[];
    foreach ($rows as $row) {
        if (!is_array($row) || !valid_id($row['id']??null)) {
            throw new \RuntimeException('A saved favorite has an invalid plugin id.');
        }
        $favorites[$row['id']]=$row;
    }
    return $favorites;
}

function favorite_repository(mixed $value): string {
    $url=source_web_url($value);
    if ($url==='') return '';
    if (parse_url($url,PHP_URL_HOST)==='github.com') return Sources\repository($url)??'';
    return preg_match('~\Ahttps://[A-Za-z0-9.-]+(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*){2,}/?\z~D',$url)
        && !str_contains(parse_url($url,PHP_URL_PATH),'..') ? rtrim($url,'/') : '';
}

function favorite_snapshot(array $plugin): array {
    $id=$plugin['id'];
    $metadata=metadata_map()[$id]??[];
    $manifest=json_file($metadata['manifestPath']??'');
    if (!is_array($manifest)) $manifest=[];
    $repository='';
    $directory=$metadata['sourceDir']??'';
    if (is_string($directory) && file_exists($directory.'/.git') && empty($plugin['firstParty'])) {
        try {
            $repository=favorite_repository(Updates\git($directory,['remote','get-url','origin'],5));
        } catch (\RuntimeException) {
            // A local plugin may have no origin.
        }
    }
    if ($repository==='') {
        foreach (['repository','repo'] as $key) {
            $repository=favorite_repository($manifest[$key]??null);
            if ($repository!=='') break;
        }
    }
    if ($repository==='') {
        foreach (Marketplace\read_cache()['entries']??[] as $entry) {
            if ($entry['id']===$id && $entry['installable']) $repository=favorite_repository($entry['repo']);
        }
    }
    return [
        'id'=>$id, 'name'=>clean_text($plugin['name']??$id,160)?:$id,
        'description'=>clean_text($plugin['description']??'',1200), 'author'=>clean_text($plugin['author']??'',200),
        'kinds'=>array_values(array_filter(array_slice($plugin['kinds'],0,32),'is_string')),
        'keywords'=>$plugin['keywords']??[], 'repository'=>$repository,
        'sourceUrl'=>$repository ?: source_web_url($manifest['homepage']??$manifest['website']??null),
        'authorGithub'=>declared_author_profile($manifest,'github') ?: readme_author_profile($metadata,'github')
            ?: author_github_from_commit($plugin,$metadata),
        'authorX'=>declared_author_profile($manifest,'x') ?: readme_author_profile($metadata,'x'),
    ];
}

function set_favorite(string $id,?array $plugin,bool $wanted): void {
    locked(state_root().'/favorites.lock',function()use($id,$plugin,$wanted) {
        $favorites=favorite_records();
        if ($wanted && !isset($favorites[$id])) {
            if ($plugin===null) throw new \InvalidArgumentException('Install the plugin before starring it.');
            if (count($favorites)>=1000) throw new \RuntimeException('Favorite limit reached. Unstar a plugin first.');
            $favorites[$id]=favorite_snapshot($plugin);
        } elseif (!$wanted) {
            unset($favorites[$id]);
        }
        save_json(array_values($favorites),state_root().'/favorites.json');
        if (favorite_records()!==$favorites) throw new \RuntimeException('The favorite change was not confirmed.');
    });
}

function favorite_rows(array $favorites,array $installedIds): array {
    $rows=[];
    foreach ($favorites as $id=>$favorite) {
        if (isset($installedIds[$id])) continue;
        $kinds=is_array($favorite['kinds']??null)?$favorite['kinds']:[];
        $rows[]=[...$favorite,'installed'=>false,'favorite'=>true,'enabled'=>false,'instances'=>[],
            'canOpen'=>false,'canDisable'=>false,'canRemove'=>false,'isSelf'=>false,'firstParty'=>false,
            'isBarWidget'=>in_array('bar-widget',$kinds,true),'canReinstall'=>favorite_repository($favorite['repository']??null)!==''];
    }
    return $rows;
}

function favorite_link(array $favorite,string $action): string {
    $url=match($action) {
        'about'=>source_web_url($favorite['sourceUrl']??null),
        'author-github'=>author_profile($favorite['authorGithub']??null,'github'),
        'author-x'=>author_profile($favorite['authorX']??null,'x')
    };
    if ($url==='') throw new \RuntimeException('No saved link found for this favorite.');
    return $url;
}
