import re
from urllib.parse import urljoin
import requests
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


def send(session, task):
    url = urljoin(BASE, task["path"])
    method = task["method"]

    if task["files"]:
        print(f"\n{method} {url} " + ", ".join(f"{n}={c}" for n, c in task["files"].items()))
    else:
        print(f"\n{method} {url}")
        for key in ("cookies", "headers", "params", "form"):
            if task[key]:
                print(f"  {key}: {task[key]}")

    kwargs = {
        "params": task["params"] or None,
        "headers": task["headers"] or None,
        "cookies": task["cookies"] or None,
        "timeout": 60,
    }
    if task["files"]:
        kwargs["files"] = [
            (name, (name, content.encode("utf-8")))
            for name, content in task["files"].items()
        ]
    elif task["form"]:
        kwargs["data"] = task["form"]

    return session.request(method, url, **kwargs)


def main():
    s = requests.Session()
    print(f"GET {BASE}\n  cookies: {{'user': '{TOKEN}'}}")

    def with_user():
        s.cookies.clear()
        s.cookies.set("user", TOKEN, domain="hw1.alexbers.com", path="/")

    with_user()
    resp = s.get(BASE, timeout=60)

    while True:
        resp.encoding = "utf-8"
        html = resp.text

        if "секрет" in html.lower():
            print("\n" + BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
            return

        task = parse_page(html)
        if not task:
            print("Ошибка")
            print(BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
            return

        m = re.search(r"Шаг\s*#?\s*(\d+)", html, re.I)
        print(f"\n[шаг {m.group(1)}]", end="")

        with_user()
        resp = send(s, task)


if __name__ == "__main__":
    main()
