import requests
from bs4 import BeautifulSoup
from datetime import datetime

OUTPUT_FILE = "proxies.txt"

def fetch_from_echolink():
    print(f"[{datetime.now()}] 🌐 Đang lấy proxy từ echolink.org...")
    try:
        url = "https://www.echolink.org/proxylist.jsp"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table")
        proxies = []
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxies.append(f"{ip}:{port}")
        return proxies
    except Exception as e:
        print(f"❌ Lỗi echolink: {e}")
        return []

def fetch_from_sslproxies():
    print(f"[{datetime.now()}] 🌐 Đang lấy proxy từ sslproxies.org...")
    try:
        url = "https://www.sslproxies.org"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", id="proxylisttable")
        if not table or not table.tbody:
            print("⚠️ Không tìm thấy bảng proxy trên sslproxies.org.")
            return []
        proxies = []
        for row in table.tbody.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 2:
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxies.append(f"{ip}:{port}")
        return proxies
    except Exception as e:
        print(f"❌ Lỗi sslproxies: {e}")
        return []

def fetch_from_proxydb():
    print(f"[{datetime.now()}] 🌐 Đang lấy proxy từ proxydb.net...")
    try:
        url = "https://proxydb.net/"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        proxies = []
        for a in soup.select("a[href^='/']"):
            text = a.text.strip()
            if ":" in text and text.count(".") == 3:
                proxies.append(text)
        return proxies
    except Exception as e:
        print(f"❌ Lỗi proxydb: {e}")
        return []

def fetch_from_geonode():
    print(f"[{datetime.now()}] 🌐 Đang lấy proxy từ geonode...")
    try:
        url = "https://proxylist.geonode.com/api/proxy-list?anonymityLevel=elite&protocols=https%2Chttp&speed=fast&limit=500&page=1&sort_by=lastChecked&sort_type=desc"
        res = requests.get(url, timeout=10)
        data = res.json()
        return [f"{item['ip']}:{item['port']}" for item in data['data']]
    except Exception as e:
        print(f"❌ Lỗi geonode: {e}")
        return []

def fetch_from_freeproxyworld():
    print(f"[{datetime.now()}] 🌐 Đang lấy proxy từ freeproxy.world...")
    proxies = []
    urls = []
    for page in range(1, 6):
        urls.append(f"https://www.freeproxy.world/?type=http&speed=500&page={page}")
        urls.append(f"https://www.freeproxy.world/?type=https&speed=500&page={page}")

    for url in urls:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="table-bordered")
            if not table:
                continue
            for row in table.find("tbody").find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 2:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxies.append(f"{ip}:{port}")
        except Exception as e:
            print(f"❌ Lỗi freeproxy.world ({url}): {e}")
    return proxies

def main():
    all_proxies = set()
    all_proxies.update(fetch_from_echolink())
    all_proxies.update(fetch_from_sslproxies())
    all_proxies.update(fetch_from_proxydb())
    all_proxies.update(fetch_from_geonode())
    all_proxies.update(fetch_from_freeproxyworld())

    try:
        with open(OUTPUT_FILE, "w") as f:
            for proxy in sorted(all_proxies):
                f.write(f"{proxy}\n")
        print(f"[{datetime.now()}] ✅ Đã lưu {len(all_proxies)} proxy vào {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ Lỗi ghi file: {e}")

main()
