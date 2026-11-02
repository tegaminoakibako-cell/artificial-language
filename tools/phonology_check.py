#!/usr/bin/env python3
"""音韻の誤り検出を総当たりで確かめる道具（SPECIFICATION_PHONOLOGY.md 1.4「保証の述べ方と確かめ方」）。

文字単位の集合（2.5）、語の形の規則（課題39の語の境目の候補）、誤りの規則（1.5.3の一覧を
音素列の書き換え規則として表したもの）を入力とし、正しい列の各所に誤りを1か所ずつ当てて、
結果を次の3つに分類する。

- 非文：どの文字単位にも分けられないか、語の形の規則に合わない（誤りとして検出できる）
- 同じ区切り：正しい列のままで、語の区切りは変わらない（別の語になる。文法・語彙の担当）
- 区切りの違い：正しい列のままで、語の区切りが変わる（検出できない）

使い方：python3 tools/phonology_check.py [--model alpha|alpha_prime|beta] [--final-stress] [--examples N]\n\n件数は、内側の2つの文字単位を総当たりし、前後の文脈を代表の文字単位で補って数えた値である。
"""

import argparse
import itertools
from collections import defaultdict

# ---------------------------------------------------------------- 音素と文字単位（2.3〜2.5）

VOWELS = ["a", "e", "o", "i", "u"]
HIGH = {"i", "u"}
OBSTRUENTS = ["p", "t", "k", "s", "h"]      # 無声の阻害音
SONORANTS = ["m", "n", "l", "j", "w"]       # 共鳴音
GAPS = {"ji", "wu", "wo"}                   # 空きマス（2.5）


def build_chunks():
    """文字単位の表（2.5）を規則から作る。狭い母音は共鳴音の後だけ（2.3）。"""
    chunks = []
    for c in OBSTRUENTS + SONORANTS:
        for v in VOWELS:
            if v in HIGH and c in OBSTRUENTS:
                continue
            if c + v in GAPS:
                continue
            chunks.append(c + v)
    return chunks


CHUNKS = build_chunks()
CHUNK_SET = set(CHUNKS)
assert len(CHUNKS) == 37, len(CHUNKS)


def is_vowel(ph):
    return ph in VOWELS


def decompose(phonemes):
    """音素列を文字単位に分ける。分けられなければ None。CV だけなので分け方は一通り。"""
    if len(phonemes) % 2:
        return None
    out = []
    for i in range(0, len(phonemes), 2):
        ch = phonemes[i] + phonemes[i + 1]
        if ch not in CHUNK_SET:
            return None
        out.append(ch)
    return out


# ---------------------------------------------------------------- 語の形の規則（課題39の候補）
#
# どの候補でも、区切りは各文字単位の種類だけで決まる。
#   boundary_before(ch)：その文字単位の前が語の境目か
#   boundary_after(ch) ：その文字単位の後が語の境目か
#   start_ok / end_ok   ：文章の先頭・末尾に置けるか


class Model:
    def __init__(self, name, before, after, start_ok, end_ok):
        self.name, self.before, self.after = name, before, after
        self.start_ok, self.end_ok = start_ok, end_ok


def _obs(ch):
    return ch[0] in OBSTRUENTS


MODELS = {
    # α：阻害音で始まる文字単位を語頭にだけ置く
    "alpha": Model("α（阻害音で始まる文字単位が語頭）",
                   before=_obs, after=lambda ch: False,
                   start_ok=_obs, end_ok=lambda ch: True),
    # α′：阻害音で始まる文字単位を語末にだけ置く
    "alpha_prime": Model("α′（阻害音で始まる文字単位が語末）",
                         before=lambda ch: False, after=_obs,
                         start_ok=lambda ch: True, end_ok=_obs),
    # β：語末の母音を /a/・/e/・/o/、語中の母音を /i/・/u/ とする
    "beta": Model("β（語末の母音が a・e・o、語中が i・u）",
                  before=lambda ch: False, after=lambda ch: ch[1] not in HIGH,
                  start_ok=lambda ch: True, end_ok=lambda ch: ch[1] not in HIGH),
}


def boundaries(chunks, model, at_start, at_end):
    """語の境目の位置（音素の添字）の集合。窓の両端は、文章の端である場合だけ含める。"""
    b = set()
    for k, ch in enumerate(chunks):
        if model.before(ch):
            b.add(2 * k)
        if model.after(ch):
            b.add(2 * k + 2)
    if not at_start:
        b.discard(0)
    if not at_end:
        b.discard(2 * len(chunks))
    if at_start:
        b.add(0)
    if at_end:
        b.add(2 * len(chunks))
    return b


def valid(chunks, model, at_start, at_end):
    if chunks is None:
        return False
    if not chunks:
        return not (at_start and at_end)
    if at_start and not model.start_ok(chunks[0]):
        return False
    if at_end and not model.end_ok(chunks[-1]):
        return False
    return True


# ---------------------------------------------------------------- 誤りの規則（1.5.3）
#
# 各規則は、音素の列 ph と、正しい列の区切り情報 info を受け取り、
# (誤りの後の音素列, 変更の始まり, 変更前の終わり, 変更後の終わり) を列挙する。
# 担当（1.5.4）：「音韻」「境目の条件」「文法・語彙」

def _sub(ph, i, new):
    out = ph[:i] + new + ph[i + 1:]
    return out, i, i + 1, i + len(new)


def _del(ph, i, n=1):
    return ph[:i] + ph[i + n:], i, i + n, i


def rule_A2(ph, info):
    """A2の残り：共鳴音の後の狭い母音の脱落"""
    for i in range(1, len(ph)):
        if ph[i] in HIGH and ph[i - 1] in SONORANTS:
            yield _del(ph, i)


def rule_A3(ph, info):
    """A3：語末の母音の脱落"""
    for i in range(len(ph)):
        if is_vowel(ph[i]) and (i + 1) in info["bounds"]:
            yield _del(ph, i)


def rule_A3_asp(ph, info):
    """A3＋聞き取り：語末の母音が脱落し、閉鎖音＋/h/ が有気の閉鎖音1つに聞こえる"""
    for i in range(1, len(ph) - 1):
        if (is_vowel(ph[i]) and (i + 1) in info["bounds"]
                and ph[i - 1] in ("p", "t", "k") and ph[i + 1] == "h"):
            yield ph[:i] + ph[i + 2:], i, i + 2, i


def rule_del_gem(ph, info):
    """A2・A3＋E3：母音が脱落して同じ子音が2つ並び、長さを区別しない聞き手には子音1つに聞こえる"""
    for i in range(1, len(ph) - 1):
        if not is_vowel(ph[i]) or ph[i - 1] != ph[i + 1] or is_vowel(ph[i - 1]):
            continue
        high_after_son = ph[i] in HIGH and ph[i - 1] in SONORANTS
        word_final = (i + 1) in info["bounds"]
        if high_after_son or word_final:
            yield ph[:i] + ph[i + 2:], i, i + 2, i


def rule_del_inaudible(ph, info):
    """A2・A3＋E10：母音が脱落し、子音の前の /h/・/j/・/w/ が聞こえなくなる"""
    for i in range(1, len(ph) - 1):
        if not is_vowel(ph[i]) or ph[i - 1] not in ("h", "j", "w"):
            continue
        if not (i + 1 < len(ph) and not is_vowel(ph[i + 1])):
            continue
        high_after_son = ph[i] in HIGH and ph[i - 1] in SONORANTS
        word_final = (i + 1) in info["bounds"]
        if high_after_son or word_final:
            yield ph[:i - 1] + ph[i + 1:], i - 1, i + 1, i - 1


def rule_A4(ph, info):
    """A4：同じ文字単位が隣り合う所で、一方が落ちる"""
    for i in range(0, len(ph) - 3, 2):
        if ph[i:i + 2] == ph[i + 2:i + 4]:
            yield _del(ph, i, 2)


def rule_chunk_del(ph, info):
    """文字単位の脱落"""
    for i in range(0, len(ph), 2):
        yield _del(ph, i, 2)


def rule_chunk_ins(ph, info):
    """文字単位の挿入"""
    for i in range(0, len(ph) + 1, 2):
        for ch in CHUNKS:
            yield ph[:i] + list(ch) + ph[i:], i, i, i + 2


def rule_B1(ph, info):
    """B1：母音が別の母音に聞こえる（曖昧母音への弱化の近似）"""
    for i in range(len(ph)):
        if is_vowel(ph[i]):
            for v in VOWELS:
                if v != ph[i]:
                    yield _sub(ph, i, [v])


def rule_B2(ph, info):
    """B2：近い母音どうしの合流（e と i、o と u）"""
    pair = {"e": "i", "i": "e", "o": "u", "u": "o"}
    for i in range(len(ph)):
        if ph[i] in pair:
            yield _sub(ph, i, [pair[ph[i]]])


def rule_C2_t(ph, info):
    """C2：語中の強勢のない母音の前で /t/ が [ɾ] になり /l/ に聞こえる"""
    for i in range(1, len(ph) - 1):
        if ph[i] != "t" or not (is_vowel(ph[i - 1]) and is_vowel(ph[i + 1])):
            continue
        if i in info["bounds"]:          # 語頭の t は対象外
            continue
        if info["final_stress"] and (i + 2) in info["bounds"]:
            continue                     # 強勢のある語末の音節の t は対象外
        yield _sub(ph, i, ["l"])


def rule_C2_p(ph, info):
    """C2・E9：母音の間の /p/ が [β] まで弱まり /w/ に聞こえる（推測。課題38で確認）"""
    for i in range(1, len(ph) - 1):
        if ph[i] == "p" and is_vowel(ph[i - 1]) and is_vowel(ph[i + 1]):
            yield _sub(ph, i, ["w"])


def rule_C3(ph, info):
    """C3：半母音の脱落"""
    for i in range(len(ph)):
        if ph[i] in ("j", "w"):
            yield _del(ph, i)


def rule_C4(ph, info):
    """C4：/h/ の脱落"""
    for i in range(len(ph)):
        if ph[i] == "h":
            yield _del(ph, i)


def rule_E1(ph, info):
    """E1：調音位置の取り違え（/p/・/t/・/k/、/m/・/n/）"""
    groups = [("p", "t", "k"), ("m", "n")]
    for i in range(len(ph)):
        for g in groups:
            if ph[i] in g:
                for c in g:
                    if c != ph[i]:
                        yield _sub(ph, i, [c])


def rule_E2(ph, info):
    """E2：無声摩擦音どうしの取り違え（/s/ と /h/）"""
    for i in range(len(ph)):
        if ph[i] in ("s", "h"):
            yield _sub(ph, i, ["h" if ph[i] == "s" else "s"])


RULES = [
    ("A2", "音韻", rule_A2),
    ("A3", "音韻", rule_A3),
    ("A3+聞き取り", "音韻", rule_A3_asp),
    ("A2・A3+E3", "音韻", rule_del_gem),
    ("A2・A3+E10", "文法・語彙", rule_del_inaudible),
    ("A4", "文法・語彙", rule_A4),
    ("文字単位の脱落", "文法・語彙", rule_chunk_del),
    ("文字単位の挿入", "文法・語彙", rule_chunk_ins),
    ("B1", "文法・語彙", rule_B1),
    ("B2", "音韻（阻害音の後）・文法・語彙（共鳴音の後）", rule_B2),
    ("C2（t→l）", "境目の条件", rule_C2_t),
    ("C2・E9（p→w）", "境目の条件", rule_C2_p),
    ("C3", "音韻", rule_C3),
    ("C4", "音韻", rule_C4),
    ("E1", "文法・語彙", rule_E1),
    ("E2", "文法・語彙", rule_E2),
]


# ---------------------------------------------------------------- 総当たり

def map_bounds(bounds, start, end_old, end_new):
    """変更の外側にある境目を、変更後の列の位置に写す。内側の境目は数だけ返す。"""
    delta = end_new - end_old
    outside, inside = set(), 0
    for b in bounds:
        if b <= start:
            outside.add(b)
        elif b >= end_old:
            outside.add(b + delta)
        else:
            inside += 1
    return outside, inside


def classify(orig_bounds, new_ph, edit, model, at_start, at_end):
    new_chunks = decompose(new_ph)
    if not valid(new_chunks, model, at_start, at_end):
        return "非文"
    start, end_old, end_new = edit
    nb = boundaries(new_chunks, model, at_start, at_end)
    o_out, o_in = map_bounds(orig_bounds, start, end_old, end_new)
    n_out = {b for b in nb if b <= start or b >= end_new}
    n_in = len(nb) - len(n_out)
    return "同じ区切り" if (o_out == n_out and o_in == n_in) else "区切りの違い"


# 前後の文脈の代表。区切りと文字単位への分け方に効くのは、文脈の文字単位の種類
# （阻害音で始まるか、狭い母音を含むか）だけであるため（README の論証）。
CONTEXT_REPS = ["ka", "ma", "mi"]


def windows(model):
    """誤りを当てる2つの文字単位（内側）と、その前後の文脈からなる窓を列挙する。

    返す値：(文字単位の列, 文章の先頭か, 文章の末尾か, 誤りを当ててよい範囲)
    """
    for i1, i2 in itertools.product(CHUNKS, repeat=2):
        for left, right in itertools.product(CONTEXT_REPS, repeat=2):
            yield (left, i1, i2, right), False, False, (2, 6)
        for right in CONTEXT_REPS:
            if model.start_ok(i1):
                yield (i1, i2, right), True, False, (0, 4)
        for left in CONTEXT_REPS:
            if model.end_ok(i2):
                yield (left, i1, i2), False, True, (2, 6)


def run(model_key, final_stress, n_examples):
    model = MODELS[model_key]
    stats = {name: defaultdict(int) for name, _, _ in RULES}
    examples = {name: [] for name, _, _ in RULES}
    for combo, at_start, at_end, (lo, hi) in windows(model):
        ph = list("".join(combo))
        bounds = boundaries(list(combo), model, at_start, at_end)
        info = {"bounds": bounds, "final_stress": final_stress}
        for name, _, rule in RULES:
            for new_ph, start, end_old, end_new in rule(ph, info):
                if start < lo or end_old > hi:
                    continue
                cat = classify(bounds, new_ph, (start, end_old, end_new),
                               model, at_start, at_end)
                stats[name][cat] += 1
                if cat == "区切りの違い" and len(examples[name]) < n_examples:
                    examples[name].append(("".join(ph), "".join(new_ph), at_start, at_end))
    return model, stats, examples


def fmt(ph_str, model, at_start, at_end):
    chunks = decompose(list(ph_str))
    if chunks is None:
        return ph_str
    b = boundaries(chunks, model, at_start, at_end)
    out = []
    for i, c in enumerate(ph_str):
        if i in b and i != 0:
            out.append("|")
        out.append(c)
    return ("|" if at_start else "…") + "".join(out) + ("|" if at_end else "…")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", choices=sorted(MODELS), default="alpha")
    ap.add_argument("--final-stress", action="store_true",
                    help="強勢を語末の音節に置く（C2（t→l）の適用範囲に影響）")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()

    model, stats, examples = run(args.model, args.final_stress, args.examples)
    print(f"文字単位：{len(CHUNKS)}　語の形：{model.name}　強勢を語末に置く：{'はい' if args.final_stress else 'いいえ'}")
    print()
    print("| 誤り | 担当（1.5.4） | 非文 | 同じ区切り | 区切りの違い | 判定 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, tier, _ in RULES:
        s = stats[name]
        diff = s["区切りの違い"]
        if tier.startswith("音韻") or tier == "境目の条件":
            verdict = "要件を満たす" if diff == 0 else "要件に反する"
        else:
            verdict = "報告のみ"
        print(f"| {name} | {tier} | {s['非文']} | {s['同じ区切り']} | {diff} | {verdict} |")
    print()
    for name, tier, _ in RULES:
        if examples[name] and (tier.startswith("音韻") or tier == "境目の条件"):
            print(f"{name} の区切りの違いの例：")
            for o, n, a, b in examples[name]:
                print(f"  {fmt(o, model, a, b)} → {fmt(n, model, a, b)}")


if __name__ == "__main__":
    main()
