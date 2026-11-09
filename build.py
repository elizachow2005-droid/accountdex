#!/usr/bin/env python3
# 帳靈圖鑑建置腳本：讀 data/creatures/*.json -> 驗證 -> 產生 docs/
# 規則請見 AGENTS.md。只用標準函式庫。
import html, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "creatures"
STATIC = ROOT / "static"
OUT = ROOT / "docs"
SITE_TITLE = "帳靈圖鑑 AccountDex"

# 類型 -> (常態餘額, CSS class)
TYPES = {
    "資產": ("借", "asset"),
    "負債": ("貸", "liab"),
    "權益": ("貸", "equity"),
    "收入": ("貸", "revenue"),
    "費用": ("借", "expense"),
}
REQUIRED = ["id", "no", "name", "account", "english", "type", "emoji",
            "normal_balance", "personality", "skill", "weakness",
            "partners", "journal", "tip"]


def esc(s):
    return html.escape(str(s))


def validate(d, path, errors):
    n = path.name
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        errors.append(f"{n}: 缺少欄位 {missing}")
        return
    if d["id"] != path.stem:
        errors.append(f"{n}: id「{d['id']}」必須等於檔名「{path.stem}」")
    if d["type"] not in TYPES:
        errors.append(f"{n}: type 只能是 {list(TYPES)}，目前是「{d['type']}」")
        return
    expected = TYPES[d["type"]][0]
    if d.get("contra"):
        expected = "貸" if expected == "借" else "借"
    if d["normal_balance"] != expected:
        errors.append(f"{n}: {d['type']}{'（備抵）' if d.get('contra') else ''}"
                      f"的常態餘額應為「{expected}」，目前是「{d['normal_balance']}」")
    lines = d["journal"].get("lines", [])
    if not lines or any(l[0] not in ("借", "貸") or not isinstance(l[2], int) or l[2] <= 0 for l in lines):
        errors.append(f"{n}: journal.lines 格式錯誤（需為 [借/貸, 科目, 正整數]）")
        return
    dr = sum(l[2] for l in lines if l[0] == "借")
    cr = sum(l[2] for l in lines if l[0] == "貸")
    if dr != cr:
        errors.append(f"{n}: 分錄借貸不平衡（借 {dr:,} / 貸 {cr:,}）")


def load():
    items, errors = [], []
    for p in sorted(DATA.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{p.name}: JSON 格式錯誤 {e}")
            continue
        before = len(errors)
        validate(d, p, errors)
        if len(errors) == before:
            items.append(d)
    ids = {d["id"] for d in items}
    for d in items:
        for pid in d["partners"]:
            if pid not in ids:
                errors.append(f"{d['id']}.json: partners 裡的「{pid}」不存在")
    nos = [d["no"] for d in items]
    if len(nos) != len(set(nos)):
        errors.append("圖鑑編號 no 有重複")
    if errors:
        print("❌ 驗證失敗：")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    return items


def page(title, body, depth):
    prefix = "../" * depth
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{prefix}style.css">
</head><body>
<header class="top"><a href="{prefix}index.html">📖 {SITE_TITLE}</a></header>
<main>{body}</main>
<footer>以 AGENTS.md 驅動的會計科目圖鑑・僅供學習</footer>
</body></html>'''


FILTER_JS = '''<script>
const btns = document.querySelectorAll('.filters button');
btns.forEach(b => b.addEventListener('click', () => {
  btns.forEach(x => x.classList.remove('on')); b.classList.add('on');
  const f = b.dataset.f;
  document.querySelectorAll('.card').forEach(c => { c.hidden = !(f === 'all' || c.dataset.type === f); });
}));
</script>'''


def card(d):
    cls = TYPES[d["type"]][1]
    contra = " · 備抵" if d.get("contra") else ""
    return (f'<a class="card {cls}" data-type="{esc(d["type"])}" href="creatures/{esc(d["id"])}.html">'
            f'<span class="no">No.{d["no"]:03d}</span><span class="emoji">{esc(d["emoji"])}</span>'
            f'<h3>{esc(d["name"])}</h3><p class="acc">{esc(d["account"])}</p>'
            f'<span class="badge">{esc(d["type"])}{contra}</span></a>')


def index_page(items):
    buttons = '<button data-f="all" class="on">全部</button>' + "".join(
        f'<button data-f="{t}">{t}</button>' for t in TYPES)
    cards = "".join(card(d) for d in sorted(items, key=lambda x: x["no"]))
    body = (f'<section class="hero"><h1>帳靈圖鑑</h1>'
            f'<p>會計科目不是冷冰冰的名詞，它們是住在你試算表裡的精靈。已收錄 <b>{len(items)}</b> 隻。</p></section>'
            f'<nav class="filters">{buttons}</nav><section class="grid">{cards}</section>{FILTER_JS}')
    return page(SITE_TITLE, body, 0)


def detail_page(d, by_id):
    cls = TYPES[d["type"]][1]
    contra = " · 備抵科目" if d.get("contra") else ""
    partners = "".join(
        f'<a class="chip" href="{p}.html">{esc(by_id[p]["emoji"])} {esc(by_id[p]["name"])}</a>'
        for p in d["partners"]) or '<span class="muted">單打獨鬥型</span>'
    rows = ""
    for side, acct, amt in d["journal"]["lines"]:
        rc = "dr" if side == "借" else "cr"
        rows += f'<tr class="{rc}"><td>{side}</td><td>{esc(acct)}</td><td class="num">{amt:,}</td></tr>'
    body = f'''
<article class="detail {cls}">
  <div class="dex-head">
    <div class="big">{esc(d["emoji"])}</div>
    <div>
      <p class="no">No.{d["no"]:03d}</p>
      <h1>{esc(d["name"])}</h1>
      <p class="acc">{esc(d["account"])} ／ {esc(d["english"])}</p>
      <span class="badge">{esc(d["type"])}{contra}</span>
      <span class="badge ghost">常態餘額：{esc(d["normal_balance"])}方</span>
    </div>
  </div>
  <dl class="stats">
    <dt>🎭 性格</dt><dd>{esc(d["personality"])}</dd>
    <dt>⚔️ 招式</dt><dd>{esc(d["skill"])}</dd>
    <dt>💔 弱點</dt><dd>{esc(d["weakness"])}</dd>
  </dl>
  <h2>🤝 夥伴</h2><div class="chips">{partners}</div>
  <h2>📒 經典分錄：{esc(d["journal"]["desc"])}</h2>
  <table class="journal"><tr><th>方向</th><th>科目</th><th>金額</th></tr>{rows}</table>
  <p class="tip">💡 {esc(d["tip"])}</p>
  <p><a href="../index.html">← 回圖鑑</a></p>
</article>'''
    return page(f'{d["name"]}｜{SITE_TITLE}', body, 1)


def main():
    items = load()
    by_id = {d["id"]: d for d in items}
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "creatures").mkdir(parents=True)
    shutil.copy(STATIC / "style.css", OUT / "style.css")
    (OUT / ".nojekyll").write_text("")
    (OUT / "index.html").write_text(index_page(items), encoding="utf-8")
    for d in items:
        (OUT / "creatures" / f"{d['id']}.html").write_text(detail_page(d, by_id), encoding="utf-8")
    print(f"✅ 建置完成：{len(items)} 隻精靈 → docs/")


if __name__ == "__main__":
    main()
