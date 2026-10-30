import argparse
import csv
import sys
import time
from collections import deque
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

START_URL = "https://www.musashino-u.ac.jp/"
DOMAIN = "www.musashino-u.ac.jp"
OUTPUT_CSV = "musashino_u_sitemap.csv"
SLEEP_SEC = 1.0 
TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sitemap-checker/1.0)"}

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".css", ".js", ".json", ".xml", ".rss", ".txt", ".csv",
    ".zip", ".gz", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".mov", ".avi", ".wmv", ".woff", ".woff2", ".ttf",
)


def normalize_url(url):
    """URL を比較しやすい形にそろえる（フラグメント除去・https 固定など）."""
    parts = urlsplit(url)
    scheme = "https"  # http と https の重複を防ぐ
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    # 迷い込むだけのページネーション系クエリは残しつつ，utm_* は落とす
    query = "&".join(
        q for q in parts.query.split("&") if q and not q.startswith("utm_")
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def is_target_link(url):
    """巡回対象のリンクかどうかを判定する."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    if parts.netloc.lower() != DOMAIN:
        return False
    if parts.path.lower().endswith(SKIP_EXTENSIONS):
        return False
    return True


def fetch_title(session, url, sleep_sec=SLEEP_SEC):
    """1ページ取得して (title, 同一ドメインのリンク一覧) を返す.

    取得できなかった場合は (None, []) を返す。
    """
    time.sleep(sleep_sec)  # アクセス前に必ず待機して負荷を軽減
    try:
        res = session.get(url, timeout=TIMEOUT, headers=HEADERS)
    except requests.RequestException as exc:
        print(f"[ERROR] {url} : {exc}", file=sys.stderr)
        return None, []

    if res.status_code != 200:
        print(f"[WARN] {url} : HTTP {res.status_code}", file=sys.stderr)
        return None, []

    if "html" not in res.headers.get("Content-Type", ""):
        return None, []

    soup = BeautifulSoup(res.content, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = normalize_url(urljoin(url, href))
        if is_target_link(absolute):
            links.append(absolute)

    return title, links


def crawl(max_pages=None, sleep_sec=SLEEP_SEC):
    """トップページから巡回して {URL: title} の辞書を返す."""
    session = requests.Session()
    session.headers.update(HEADERS)

    sitemap = {}                    # key: URL, value: <title> の文字列
    visited = set()                 # 取得を試みた URL
    queue = deque([normalize_url(START_URL)])

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        title, links = fetch_title(session, url, sleep_sec)
        if title is None:
            continue

        sitemap[url] = title
        print(f"[{len(sitemap):>5}] {title} | {url}")

        for link in links:
            if link not in visited:
                queue.append(link)

        if max_pages is not None and len(sitemap) >= max_pages:
            print(f"上限 {max_pages} ページに達したので終了します。", file=sys.stderr)
            break

    return sitemap


def save_csv(sitemap, path):
    """辞書を CSV（url, title）として保存する."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title"])
        for url, title in sitemap.items():
            writer.writerow([url, title])
    print(f"{len(sitemap)} 件を {path} に保存しました。")


def main():
    parser = argparse.ArgumentParser(description="武蔵野大学サイトのサイトマップ作成")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="取得するページ数の上限（省略時は無制限）")
    parser.add_argument("--sleep", type=float, default=SLEEP_SEC,
                        help=f"1リクエストあたりの待機秒数（既定 {SLEEP_SEC}）")
    parser.add_argument("-o", "--output", default=OUTPUT_CSV,
                        help=f"出力 CSV ファイル名（既定 {OUTPUT_CSV}）")
    args = parser.parse_args()

    sitemap = crawl(max_pages=args.max_pages, sleep_sec=args.sleep)
    save_csv(sitemap, args.output)


if __name__ == "__main__":
    main()
