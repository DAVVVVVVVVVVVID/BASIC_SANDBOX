#!/usr/bin/env python3
"""小镇导播 BGM 同步（whale-ec 11-21）：按 run/data/town-bgm/manifest.json 把音频拷进 front_end/public/bgm/，生成页面用的 bgm/manifest.json。

- manifest 由会话 G 统一写（{tracks:[{id, file, title, author, license, group: day|night|sleep, kind: cc|instrumental}]}），本脚本只读。
- file：绝对路径，或相对 manifest 所在目录。
- manifest 还没出来时：在内存里从曲库 credits.json 拼一份（闲聊 → day、讲故事 → night，kind cc），不写回。
- public/bgm/ 不进 git（.gitignore）；构建时随 dist 发布。多余的旧文件会删掉。

用法：python3 tools/sync_bgm.py [--manifest PATH] [--dry-run]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

RUN_DATA = '/home/shan-dw/Project/run/data'
DEFAULT_MANIFEST = os.path.join(RUN_DATA, 'town-bgm/manifest.json')
LIBRARY = os.path.join(RUN_DATA, 'live-linux/plugins/bgm/library')
FALLBACK_GROUPS = {'闲聊': 'day', '讲故事': 'night'}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'bgm')
GROUPS = {'day', 'night', 'sleep'}
KINDS = {'cc', 'instrumental'}


def fallback_tracks():
    tracks = []
    for folder, group in FALLBACK_GROUPS.items():
        d = os.path.join(LIBRARY, folder)
        credits = json.load(open(os.path.join(d, 'credits.json'), encoding='utf-8'))
        for fn, c in sorted(credits.items()):
            tracks.append({'id': os.path.splitext(fn)[0], 'file': os.path.join(d, fn), 'title': c.get('title') or os.path.splitext(fn)[0],
                           'author': c.get('author', ''), 'license': c.get('license', ''), 'group': group, 'kind': 'cc'})
    return tracks


def load(manifest):
    if os.path.exists(manifest):
        m = json.load(open(manifest, encoding='utf-8'))
        base = os.path.dirname(manifest)
        tracks = m.get('tracks', [])
        for t in tracks:
            if not os.path.isabs(t['file']):
                t['file'] = os.path.normpath(os.path.join(base, t['file']))
        return tracks, 'manifest'
    return fallback_tracks(), 'fallback(credits.json)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default=DEFAULT_MANIFEST)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    tracks, src = load(a.manifest)
    out_tracks, seen, problems = [], set(), []
    for t in tracks:
        tid = str(t.get('id') or '')
        if not tid or tid in seen:
            problems.append(f'id 缺失或重复：{tid!r}'); continue
        if t.get('group') not in GROUPS or t.get('kind') not in KINDS:
            problems.append(f'{tid}: group/kind 不合法（{t.get("group")} / {t.get("kind")}）'); continue
        if not os.path.isfile(t['file']):
            problems.append(f'{tid}: 文件不存在 {t["file"]}'); continue
        seen.add(tid)
        ext = os.path.splitext(t['file'])[1].lower() or '.mp3'
        # 文件名用 id 的短哈希，避免中文 / 空格路径；内容变了换名，浏览器缓存不脏
        h = hashlib.sha1(open(t['file'], 'rb').read()).hexdigest()[:10]
        name = f'{h}{ext}'
        out_tracks.append({'id': tid, 'src': f'bgm/{name}', 'title': t.get('title') or tid, 'author': t.get('author', ''),
                           'license': t.get('license', ''), 'group': t['group'], 'kind': t['kind'], '_from': t['file'], '_name': name})
    print(f'来源 {src}：{len(tracks)} 首，可用 {len(out_tracks)} 首；' + '、'.join(f'{g} {sum(1 for t in out_tracks if t["group"] == g)}' for g in sorted(GROUPS)))
    for p in problems:
        print('  ⚠', p)
    if a.dry_run:
        return 0
    os.makedirs(OUT, exist_ok=True)
    keep = {'manifest.json'}
    for t in out_tracks:
        dst = os.path.join(OUT, t['_name']); keep.add(t['_name'])
        if not os.path.exists(dst):
            shutil.copyfile(t['_from'], dst)
    for fn in os.listdir(OUT):
        if fn not in keep:
            os.remove(os.path.join(OUT, fn))
    pub = [{k: v for k, v in t.items() if not k.startswith('_')} for t in out_tracks]
    json.dump({'source': src, 'tracks': pub}, open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'已同步到 {os.path.normpath(OUT)}')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
