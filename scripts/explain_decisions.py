"""Turn the loop's open questions into a page the owner can actually decide from.

`OWNER_DECISIONS.md` is written for the loop: it names requirement ids, file paths
and failure modes. An owner should not have to read that to answer "which of these
two, and why". This script collects what is still unanswered, asks Hydrogen (via
the `agy` CLI) to restate it in plain Japanese, and writes one self-contained HTML
page.

Hydrogen rewrites; it does not decide and it does not add facts. Everything it is
allowed to say is in the text handed to it, and the output is checked before it
replaces the page.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "Gemini 4 Hydrogen (Medium)"
OUT = ROOT / "docs" / "report" / "OWNER_DECISIONS_PLAIN_GUIDE.html"
# Settled by the owner on 2026-11-17: no emoji anywhere in the product or its
# reports. The range check is cheap and catches a model that reaches for one.
EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️]")


@dataclass(frozen=True)
class Item:
    """One thing the owner has to answer, or one caveat raised against a decision."""

    kind: str  # "decision" | "caveat"
    phase: str
    heading: str
    body: str


def unanswered(text: str) -> list[tuple[str, str]]:
    """`## ` entries that pose a question and carry no `**Answer**`."""
    parts = re.split(r"(?m)^##\s+(.*)$", text.replace("\r\n", "\n"))
    pairs = zip(parts[1::2], parts[2::2], strict=True)
    return [
        (h.strip(), b.strip()) for h, b in pairs if "**Question**" in b and "**Answer**" not in b
    ]


def caveats(text: str) -> list[str]:
    """The 【申し送り】 blocks: where the implementation does not agree with a decision.

    These are not questions, but they are the ones an owner most needs to see —
    they say "we are doing what you asked, and here is what it costs".
    """
    found = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        if "【申し送り】" in block:
            found.append(block.strip())
    return found


def collect(root: Path) -> list[Item]:
    items: list[Item] = []
    for decisions in sorted(root.glob("progress/*/OWNER_DECISIONS.md")):
        phase = decisions.parent.name
        text = decisions.read_bytes().decode("utf-8")
        items += [Item("decision", phase, h, b) for h, b in unanswered(text)]
        items += [Item("caveat", phase, "申し送り", b) for b in caveats(text)]
    return items


def brief(items: list[Item]) -> str:
    """What Hydrogen is given, and the only thing it is allowed to say."""
    body = "\n\n".join(
        f"--- {'決めてほしいこと' if item.kind == 'decision' else '申し送り（決定への注意）'}"
        f" / phase={item.phase} / {item.heading} ---\n{item.body}"
        for item in items
    )
    return f"""あなたは、開発チームからオーナー（発注者）への説明文を書く担当です。
オーナーは研究室の運営者で、プログラムは書きません。

下に、いま開発が止まっている「決めてほしいこと」と、決定に対する「申し送り」を
そのまま貼ります。これを **中学生が読んでも分かる日本語** に書き直し、
**1 枚の HTML** として出力してください。

### 絶対の制約

- **書かれていない事実を足さないこと。** 数字・ファイル名・機能名を創作しない。
  元の文に無い結論を出さない。分からないことは「ここは分かりません」と書く。
- **あなたは決めない。** 選択肢と、それぞれを選んだときに起きることを並べるだけ。
  元の文に「開発側のおすすめ」が書いてあるときは、それを「開発側の意見」として紹介する。
- **絵文字を使わない。** 記号で飾らない。
- 専門用語を避ける。どうしても要るときは、すぐ後ろにかっこ書きで言い換えを添える。
- 外部のファイルを読み込まない。CSS は `<style>` に直接書く。画像・フォント・
  スクリプトを外から取ってこない。
- 出力は HTML だけ。前置きも後書きも、```html のような囲みも付けない。

### 各項目に必ず書くこと

1. **ひとことで言うと** — 何を決めてほしいのかを 1 文で。
2. **いまどうなっているの** — なぜ止まっているのか。
3. **決めないとどうなるの** — この決定を待っている作業は何か。
4. **選べるやり方** — 選択肢ごとに「よいところ」と「よくないところ」を並べる。
   選択肢が元の文に書かれていない場合は、無理に作らず「選択肢は示されていません」と書く。
5. **開発側の意見** — 元の文に推奨があればそれを紹介し、理由も書く。無ければ省く。
6. **決める前に知っておくこと** — 前提・制約・リスク。

「申し送り」の項目は、決めてもらうものではありません。
「オーナーの決定どおりに作るが、その代わりこういう弱点が残る」という報告として、
同じ分かりやすさで書いてください。

### 見た目

- 落ち着いた配色。明るい背景と暗い背景の両方で読めるようにする
  （`prefers-color-scheme` と `:root[data-theme]` の両方に対応させる）。
- 項目ごとにカード。先頭に全体の目次。
- 横に長い表は、その表だけが横スクロールするようにする。
- `<title>` は「オーナーに決めてほしいこと（やさしい説明）」。

### ここから下が、書き直す元の文です

{body}
"""


def rejected(html: str) -> str:
    """Why this output must not replace the page, or an empty string if it may."""
    lowered = html.lower()
    if "<html" not in lowered and "<!doctype" not in lowered:
        return "HTML ではありません"
    for pattern in ("<script src=", '<link rel="stylesheet"', 'src="http', "src='http"):
        if pattern in lowered:
            return f"外部リソースを読み込もうとしています: {pattern}"
    found = EMOJI.search(html)
    if found:
        return f"絵文字が含まれています: {found.group(0)!r}"
    return ""


def ask(prompt: str, *, model: str, timeout: float) -> str:
    executable = shutil.which("agy")
    if not executable:
        raise SystemExit("agy が見つかりません。PATH を確認してください。")
    result = subprocess.run(  # noqa: S603 — resolved CLI path, no shell
        [executable, "--model", model, f"--print={prompt}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"agy failed ({result.returncode}): {result.stderr.strip()[:500]}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true", help="print the brief and stop")
    arguments = parser.parse_args()

    items = collect(ROOT)
    if not items:
        print("未回答の判断も申し送りもありません。ページは更新しません。")
        return 0
    prompt = brief(items)
    if arguments.dry_run:
        print(prompt)
        return 0

    print(f"{len(items)} 件を {arguments.model} に渡します…")
    html = ask(prompt, model=arguments.model, timeout=arguments.timeout)
    html = re.sub(r"^```(?:html)?\s*|\s*```$", "", html.strip())
    problem = rejected(html)
    if problem:
        raise SystemExit(f"生成結果を破棄しました: {problem}")
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(html, encoding="utf-8", newline="")
    print(f"{arguments.out.relative_to(ROOT).as_posix()} を更新しました（{len(html)} 文字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
