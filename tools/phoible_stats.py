#!/usr/bin/env python3
"""PHOIBLE の音素目録から、SPECIFICATION_PHONOLOGY.md 2.3・2.4 の百分率を集計する。

使い方：
  python3 tools/phoible_stats.py --download phoible.csv   # データを取得して集計
  python3 tools/phoible_stats.py phoible.csv              # 取得済みのデータで集計

データ：https://github.com/phoible/dev の data/phoible.csv（約26MB。リポジトリには含めない）

集計の方法（2.4に記したもの）：
- 1つの言語（Glottocode）につき、最初の音素目録を1つだけ用いる
- 周辺的（Marginal）と記された音素は除く
- 歯音・舌尖・舌端・後退の補助記号（U+032A・U+033A・U+033B・U+0320）を取り除いて統合する
- 母音の数は、単母音の音色の数で数える（長さ・鼻音化などの補助記号を除き、1文字になるもの）
"""

import argparse
import collections
import csv
import unicodedata
import urllib.request

URL = "https://raw.githubusercontent.com/phoible/dev/master/data/phoible.csv"
DIACRITICS = ["̪", "̺", "̻", "̠"]
CONSONANTS = ("m n k j t p w l s ŋ h b r ɲ f tʃ ʔ ʃ ɾ v z ts x ʒ c kʷ β ɸ ç θ ʎ "
              "pʲ kʲ mʲ nʲ lʲ tʲ sʲ").split()
HIGH_VOWELS = set("iɪyʏɨʉɯuʊ")


def norm(p):
    for d in DIACRITICS:
        p = p.replace(d, "")
    return p


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    first = {}
    for r in rows:
        first.setdefault(r["Glottocode"] or r["InventoryID"], r["InventoryID"])
    keep = set(first.values())
    segs = collections.defaultdict(set)
    vowels = collections.defaultdict(set)
    names = {}
    for r in rows:
        iid = r["InventoryID"]
        if iid not in keep or r["Marginal"] == "TRUE":
            continue
        segs[iid].add(norm(r["Phoneme"]))
        names[iid] = r["LanguageName"]
        if r["SegmentClass"] == "vowel":
            base = "".join(c for c in unicodedata.normalize("NFD", r["Phoneme"])
                           if not unicodedata.combining(c) and c not in "ːˑ")
            if len(base) == 1:
                vowels[iid].add(base)
    return keep, segs, vowels, names


def pct(n, total):
    return f"{100 * n / total:.1f}%"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", help="phoible.csv の場所")
    ap.add_argument("--download", action="store_true", help="データを取得してから集計する")
    args = ap.parse_args()
    if args.download:
        urllib.request.urlretrieve(URL, args.csv)

    keep, segs, vowels, names = load(args.csv)
    total = len(keep)
    count = collections.Counter(p for iid in keep for p in segs[iid])
    print(f"言語の数：{total}")
    print()
    print("子音を持つ言語の割合（2.4）")
    for c in CONSONANTS:
        print(f"  {c}\t{count[c]}\t{pct(count[c], total)}")
    pal = sum(1 for iid in keep if any(p.endswith("ʲ") for p in segs[iid]))
    print(f"  口蓋化した子音を1つでも持つ\t{pal}\t{pct(pal, total)}")
    print()
    print("母音（単母音の音色）の数の分布（2.3）")
    dist = collections.Counter(len(vowels[iid]) for iid in keep)
    for k in sorted(dist):
        print(f"  {k}\t{dist[k]}\t{pct(dist[k], total)}")
    for label, need in (("a・e・i・o・u をすべて持つ", set("aeiou")),
                        ("a・i・u をすべて持つ", set("aiu"))):
        n = sum(1 for iid in keep if vowels[iid] >= need)
        print(f"  {label}\t{n}\t{pct(n, total)}")
    nohigh = [iid for iid in keep if vowels[iid] and not (vowels[iid] & HIGH_VOWELS)]
    print(f"  狭い母音を持たない\t{len(nohigh)}\t{pct(len(nohigh), total)}")
    for iid in nohigh:
        print(f"    {names[iid]}：{'・'.join(sorted(vowels[iid]))}")


if __name__ == "__main__":
    main()
