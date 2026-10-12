import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlencode
from bs4 import BeautifulSoup

BASE = "http://hw1.alexbers.com/"
TOKEN = "277785ab3043164a12c4446e2bc85371"


def parse_table(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text().strip() for c in tr.find_all(["td", "th"])]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    if not rows:
        return None, {}
    title = rows[0][0].lower()
    if title in ("ключ", "имя файла"):
        return title, dict(rows[1:])
    return None, dict(rows)


def table_kind(text):
    t = text.lower()
    if "cookie" in t:
        return "cookies"
    if "заголов" in t:
        return "headers"
    if "формы" in t:
        return "form"
    return "params"


def text_before(table):
    parts = []
    for sib in table.previous_siblings:
        if getattr(sib, "name", None) == "table":
            break
        if hasattr(sib, "get_text"):
            chunk = sib.get_text(" ", strip=True)
        else:
            chunk = str(sib).strip()
        if chunk:
            parts.append(chunk)
    return " ".join(reversed(parts))


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    text = body.get_text(" ", strip=True)

    task = {"params": {}, "cookies": {}, "headers": {}, "form": {}, "files": {}}
    for table in body.find_all("table"):
        title, data = parse_table(table)
        if title and "файл" in title:
            task["files"].update(data)
        else:
            task[table_kind(text_before(table))].update(data)

    m = re.search(r"\b(GET|POST)\b", text)
    task["method"] = m.group(1) if m else ("POST" if task["files"] else "GET")

    mp = re.search(r"адресу\s+(\S+)", text)
    if mp:
        task["path"] = mp.group(1).rstrip(".,;:")
    else:
        a = body.find("a", href=True)
        task["path"] = a["href"] if a else None

    return task if task["path"] else None


def curl_request(method, url, *, headers=None, cookies=None, params=None,
                 form=None, files=None):
    if params:
        url = f"{url}?{urlencode(params)}" if "?" not in url else f"{url}&{urlencode(params)}"

    cmd = ["curl", "-sS", "--http1.1", "-X", method, url]

    cookie_hdr = {"user": TOKEN, **(cookies or {})}
    cmd += ["-b", "; ".join(f"{k}={v}" for k, v in cookie_hdr.items())]

    for key, value in (headers or {}).items():
        cmd += ["-H", f"{key}: {value}"]

    tmpdir = None
    try:
        if files:
            tmpdir = tempfile.TemporaryDirectory()
            root = Path(tmpdir.name)
            for name, content in files.items():
                path = root / name
                path.write_text(content, encoding="utf-8")
                cmd += ["-F", f"{name}=@{path};filename={name}"]
        elif form:
            for key, value in form.items():
                cmd += ["--data-urlencode", f"{key}={value}"]
        elif method == "POST":
            cmd += ["-d", ""]

        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Ошибка ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace')}"
            )
        return proc.stdout.decode("utf-8")
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


def send(task):
    url = urljoin(BASE, task["path"])
    method = task["method"]

    if task["files"]:
        print(f"\n{method} {url} " + ", ".join(f"{n}={c}" for n, c in task["files"].items()))
    else:
        print(f"\n{method} {url}")
        for key in ("cookies", "headers", "params", "form"):
            if task[key]:
                print(f"  {key}: {task[key]}")

    return curl_request(
        method, url,
        headers=task["headers"] or None,
        cookies=task["cookies"] or None,
        params=task["params"] or None,
        form=task["form"] or None,
        files=task["files"] or None,
    )


def main():
    print(f"GET {BASE}\n  cookies: {{'user': '{TOKEN}'}}")
    html = curl_request("GET", BASE)

    while True:
        if "секрет" in html.lower():
            print("\n" + BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
            return

        task = parse_page(html)
        if not task:
            print("Ошибка")
            print(BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
            return

        m = re.search(r"Шаг\s*#?\s*(\d+)", html, re.I)
        print(f"\n[шаг {m.group(1) if m else '?'}]", end="")

        html = send(task)


if __name__ == "__main__":
    main()
