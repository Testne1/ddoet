import requests
import re
from bs4 import BeautifulSoup
def get_proxies_from_github_txt_list(repo_url_template='https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt'):
    """Lấy proxies từ các file .txt trực tiếp trên GitHub"""
    proxies = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
    try:
        response = requests.get(repo_url_template, timeout=10, headers=headers)
        if response.status_code == 200:
            for line in response.text.splitlines():
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$", line.strip()):
                    proxies.append(line.strip())
        else:
            print(f"[!] Không thể truy cập {repo_url_template}. Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[!] Lỗi khi lấy proxies từ {repo_url_template}: {e}")
    return proxies
def get_ssl_proxies():
    url = "https://free-proxy-list.net/vi/ssl-proxy.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Request failed: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table", class_="table")
    proxies = []

    if not table:
        print("⚠️ Table not found")
        return []

    for row in table.tbody.find_all("tr"):
        cols = row.find_all("td")
        ip = cols[0].text.strip()
        port = cols[1].text.strip()
        https = cols[6].text.strip().lower()
        if https == 'yes':  # Chỉ lấy proxy hỗ trợ HTTPS
            proxies.append(f"{ip}:{port}")

    return proxies

if __name__ == "__main__":
    proxies = get_ssl_proxies() and get_proxies_from_github_txt_list()
    if proxies:
        print(f"✅ Lấy được {len(proxies)} proxy:")
        for proxy in proxies:
            print(proxy)
        with open("ssl_proxies.txt", "w") as f:
            f.write("\n".join(proxies))
        print("📁 Đã lưu vào ssl_proxies.txt")
    else:
        print("❌ Không lấy được proxy nào.")
