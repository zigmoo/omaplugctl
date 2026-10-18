"""Publish review evidence at the reviewed commit using authenticated gh."""
import hashlib
import json
import re
import urllib.parse

COMMENT_BYTES = 55_000


def target(repository, commit):
    url = urllib.parse.urlsplit(repository)
    if (url.scheme != 'https' or url.netloc != 'github.com'
            or url.query or url.fragment
            or not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', url.path)
            or any(p in ('.', '..') for p in url.path.split('/'))
            or not re.fullmatch(r'[a-f0-9]{40,64}', commit)):
        raise RuntimeError('GitHub publication needs a GitHub source repository and an exact commit.')
    return url.path.lstrip('/'), commit


def api(command, endpoint, *, method='GET', body=None):
    argv = ['gh', 'api', '--hostname', 'github.com', '--method', method,
            '-H', 'Accept: application/vnd.github+json', endpoint]
    if body is not None:
        argv += ['--input', '-']
    return json.loads(command(argv, body=json.dumps(body) if body is not None else None, timeout=60))


def chunks(text):
    data = text.encode()
    while data:
        end = min(COMMENT_BYTES, len(data))
        if end < len(data):
            newline = data.rfind(b'\n', COMMENT_BYTES // 2, end)
            if newline >= 0:
                end = newline + 1
            while data[end] & 0xc0 == 0x80:
                end -= 1
        yield data[:end].decode()
        data = data[end:]


def comment_url(value, repository, commit):
    expected = f'https://github.com/{repository}/commit/{commit}#commitcomment-'
    url = value.get('html_url', '')
    if (not isinstance(url, str) or not url.startswith(expected)
            or not url[len(expected):].isdigit() or value.get('commit_id') != commit
            or not isinstance(value.get('id'), int)):
        raise RuntimeError('GitHub returned an unexpected review location.')
    return url


def publish(report, repository_url, commit, command):
    """Resume exact-body publication without duplicate comments after a timeout."""
    repository, commit = target(repository_url, commit)
    actor = api(command, 'user')['login']
    digest = hashlib.sha256((repository + commit + report).encode()).hexdigest()
    marker = f'<!-- omaplugctl-review:{digest}:'
    endpoint = f'repos/{repository}/commits/{commit}/comments'
    existing = {}
    for page in range(1, 21):
        values = api(command, endpoint + f'?per_page=100&page={page}')
        for value in values:
            body = value.get('body', '')
            if value.get('user', {}).get('login') == actor and body.startswith(marker):
                existing[body.split('\n', 1)[0]] = value
        if len(values) < 100:
            break
    else:
        raise RuntimeError('Too many commit comments to safely check publication history.')
    payloads = list(chunks(report))
    comments = []
    for index, payload in enumerate(payloads, 1):
        key = f'{marker}{index} -->'
        body = f'{key}\n## OmaPlugCtl agent review ({index}/{len(payloads)})\n\n{payload}'
        value = existing.get(key)
        if value is None:
            value = api(command, endpoint, method='POST', body={'body': body})
        comment_url(value, repository, commit)
        # Read back actual server state, including after an ambiguous POST timeout.
        value = api(command, f'repos/{repository}/comments/{value["id"]}')
        url = comment_url(value, repository, commit)
        if (value.get('user', {}).get('login') != actor
                or not (value.get('body') == body or
                        (index == 1 and value.get('body', '').startswith(body + '\n\nReview continuation:')))):
            raise RuntimeError('Published review did not match the saved findings.')
        comments.append((value, body, url))
    if len(comments) > 1:
        first, body, _ = comments[0]
        body += '\n\nReview continuation:\n' + '\n'.join(
            f'- [Part {i}]({entry[2]})' for i, entry in enumerate(comments[1:], 2))
        if first.get('body') != body:
            api(command, f'repos/{repository}/comments/{first["id"]}', method='PATCH', body={'body': body})
        checked = api(command, f'repos/{repository}/comments/{first["id"]}')
        if checked.get('body') != body:
            raise RuntimeError('GitHub did not confirm the complete report navigation.')
    return comments[0][2]
