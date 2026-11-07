#!/usr/bin/env python3
"""RULES.md の規則の書式と依拠関係を検査する。

使い方:
    python3 tools/check_rules.py [RULES.md] [--rule 番号] [--words]

    --rule 番号  その規則の直接の依拠先・直接の下位・兄弟・影響範囲を表示する
    --words      各規則の「依拠先（語）」に書くべき規則（照合の結果）を表示する

誤りがあれば終了コード 1 を返す。詳しくは tools/README.md を参照。
"""
import re
import sys
from collections import defaultdict

ID = r'[DXO]\d+'


def split_items(text):
    """「、」で区切る。全角括弧の中の「、」では区切らない。"""
    items, buf, depth = [], '', 0
    for ch in text:
        if ch == '（':
            depth += 1
        elif ch == '）':
            depth -= 1
        if ch == '、' and depth == 0:
            items.append(buf.strip())
            buf = ''
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return items


def parse(path):
    rules, order, errors = {}, [], []
    cur = None
    for line in open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^## (' + ID + r')', line)
        if m:
            cur = m.group(1)
            if cur in rules:
                errors.append(f'[番号の重複] {cur}')
            rules[cur] = {'body': '', 'defs': [], 'intro': [],
                          'real': [], 'word': [], 'other': [], 'reasons_missing': []}
            order.append(cur)
            continue
        if line.startswith('# ') or line.startswith('欠番') or line.startswith('旧番号'):
            cur = None
            continue
        if cur is None:
            continue
        r = rules[cur]
        m = re.match(r'^- (定義|導入)する語：(.*)$', line)
        if m:
            r['defs' if m.group(1) == '定義' else 'intro'] = split_items(m.group(2))
            continue
        m = re.match(r'^- 依拠先（(実現|語|その他)）：(.*)$', line)
        if m:
            kind = {'実現': 'real', '語': 'word', 'その他': 'other'}[m.group(1)]
            for item in split_items(m.group(2)):
                mm = re.match(r'^(' + ID + r')(（.+）)?$', item)
                if not mm:
                    errors.append(f'[依拠先の書式] {cur}：{item}')
                    continue
                r[kind].append(mm.group(1))
                if kind != 'word' and not mm.group(2):
                    r['reasons_missing'].append(mm.group(1))
            continue
        if line.startswith('- 依拠先：'):
            errors.append(f'[古い書式の依拠先] {cur}')
            continue
        if line.startswith('- '):
            continue
        r['body'] += line
    return rules, order, errors


def term_pattern(term):
    """1文字の英字・記号は、前後に英字などが続かないものだけを拾う。"""
    if re.fullmatch(r'[A-Za-zΣσ]', term):
        return r'(?<![A-Za-z_])' + re.escape(term) + r'(?![A-Za-z⁺_\[])'
    return re.escape(term)


def word_deps(rules):
    """定義する語・導入する語から、各規則の「依拠先（語）」を求める。"""
    defs, intro, errors = {}, {}, []
    for rid, r in rules.items():
        for t in r['defs']:
            if t in defs:
                errors.append(f'[定義する語の重複] {t}：{defs[t]}、{rid}')
            defs[t] = rid
        for t in r['intro']:
            intro[t] = rid
    terms = sorted(set(defs) | set(intro), key=len, reverse=True)
    result = {}
    for rid, r in rules.items():
        body, used = r['body'], defs.copy()
        need = defaultdict(list)
        for t in terms:  # 長い語から順に照合し、照合した部分は伏せる
            p = term_pattern(t)
            if re.search(p, body):
                if t in defs and defs[t] != rid and t not in r['intro']:
                    need[defs[t]].append(t)
                body = re.sub(p, '\0', body)
        for t in r['defs']:  # 導入された語を定義する規則は、導入した規則に依拠する
            if t in intro and intro[t] != rid:
                need[intro[t]].append('導入：' + t)
        result[rid] = dict(need)
    for t, rid in intro.items():
        if t not in defs:
            errors.append(f'[導入されたが定義されていない語] {t}（{rid}）')
    return result, errors


def main():
    args = sys.argv[1:]
    path = 'RULES.md'
    show_rule, show_words = None, False
    while args:
        a = args.pop(0)
        if a == '--rule':
            show_rule = args.pop(0)
        elif a == '--words':
            show_words = True
        else:
            path = a
    rules, order, errors = parse(path)
    words, werr = word_deps(rules)
    errors += werr
    deps = {rid: list(dict.fromkeys(r['real'] + r['word'] + r['other'])) for rid, r in rules.items()}

    for rid, r in rules.items():
        if rid == 'D1':
            if deps[rid]:
                errors.append('[D1 に依拠先がある]')
        elif not r['real']:
            errors.append(f'[実現の依拠先がない] {rid}')
        for p in r['reasons_missing']:
            errors.append(f'[理由がない] {rid} の {p}')
        for p in deps[rid]:
            if p not in rules:
                errors.append(f'[存在しない依拠先] {rid} → {p}')
            elif p == rid:
                errors.append(f'[自分自身への依拠] {rid}')
        if rid[0] == 'D':
            bad = [p for p in deps[rid] if p[0] != 'D']
            if bad:
                errors.append(f'[D の規則が D 以外に依拠] {rid} → {"、".join(bad)}')
        written, computed = set(r['word']), set(words[rid])
        for p in sorted(computed - written):
            errors.append(f'[依拠先（語）の不足] {rid} に {p} がない（{"、".join(words[rid][p])}）')
        for p in sorted(written - computed):
            errors.append(f'[依拠先（語）の余分] {rid} の {p} は語の照合に当たらない')

    state = {}

    def dfs(rid, path):
        state[rid] = 1
        for p in deps[rid]:
            if p not in rules:
                continue
            if state.get(p) == 1:
                errors.append('[循環] ' + ' → '.join(path + [p]))
            elif p not in state:
                dfs(p, path + [p])
        state[rid] = 2
    for rid in rules:
        if rid not in state:
            dfs(rid, [rid])

    child = defaultdict(list)
    for rid in rules:
        for p in deps[rid]:
            child[p].append(rid)

    def reach(rid):
        seen, stack = set(), [rid]
        while stack:
            for c in child[stack.pop()]:
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        return seen

    if show_words:
        for rid in order:
            w = words[rid]
            print(rid, '、'.join(f'{p}（{"・".join(ts)}）' for p, ts in sorted(w.items())) or '―')
        return 0
    if show_rule:
        r = show_rule
        sib = sorted({c for p in deps[r] if p[0] != 'D' for c in child[p]} - {r})
        leaves = sorted(x for x in reach(r) if not child[x])
        print(f'{r} の直接の依拠先：{"、".join(deps[r]) or "―"}')
        print(f'{r} の直接の下位：{"、".join(sorted(child[r])) or "―"}')
        print(f'{r} の兄弟（D 以外の依拠先を共有）：{"、".join(sib) or "―"}')
        print(f'{r} の影響範囲（到達できる末端の規則）：{"、".join(leaves) or "―"}')
        return 0

    pos = {rid: i for i, rid in enumerate(order)}
    notes = [f'{rid} の依拠先 {p}' for rid in order for p in deps[rid] if p in pos and pos[p] > pos[rid]]
    print(f'規則数：{len(rules)}')
    for e in errors:
        print(e)
    if notes:
        print('参考（依拠先がその規則より後に書かれている）：' + '、'.join(notes))
    print('誤りなし' if not errors else f'誤り：{len(errors)}件')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
