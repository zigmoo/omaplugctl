<?php
declare(strict_types=1);
require __DIR__.'/../controller.php';
try {
    $request=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
    $name='OmaPlugCtl\\'.$request['function'];
    if(!function_exists($name))throw new InvalidArgumentException('Unknown test function.');
    $arguments=$request['args']??[];$refs=[];foreach($arguments as&$argument)$refs[]=&$argument;unset($argument);
    $result=$name(...$refs);
    echo json_encode(['ok'=>true,'result'=>$result,'args'=>$arguments],JSON_THROW_ON_ERROR|JSON_UNESCAPED_UNICODE);
}catch(Throwable $error){echo json_encode(['ok'=>false,'invalid'=>$error instanceof InvalidArgumentException,'message'=>$error->getMessage()]);exit(1);}
