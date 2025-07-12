import asyncio
import aiofiles
import os
from datetime import datetime

INPUT_FILE = "proxies.txt"
OUTPUT_FILE = "proxy.txt"
TEST_URL = "https://www.google.com"
TIMEOUT = 10
MAX_CONCURRENCY = 500 

if os.path.exists(OUTPUT_FILE):
    open(OUTPUT_FILE, "w").close()

async def append_valid_proxy(proxy):
    async with aiofiles.open(OUTPUT_FILE, "a") as f:
        await f.write(f"{proxy}\n")
        await f.flush()
    print(f"[{datetime.now()}] ✅ Proxy hợp lệ: {proxy}")

async def check_proxy(proxy):
    curl_command = [
        "curl",
        "-x", f"http://{proxy}",          
        "-A", "Mozilla/5.0",                
        "-k",                              
        "-L",                               
        "-s",                              
        "--connect-timeout", str(TIMEOUT),  
        "--max-time", str(TIMEOUT + 5),     
        "-o", "/dev/null",                
        "-w", "%{http_code}",               
        TEST_URL
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *curl_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT + 10)
        http_code = stdout.decode().strip()

        if http_code == "200":
            await append_valid_proxy(proxy)
        else:
            print(f"[{datetime.now()}] ❌ Proxy {proxy} trả về HTTP {http_code}")
    except asyncio.TimeoutError:
        print(f"[{datetime.now()}] ⏰ Proxy {proxy} bị timeout")
    except Exception as e:
        print(f"[{datetime.now()}] ⚠️ Proxy {proxy} lỗi: {e}")

async def main():
    try:
        with open(INPUT_FILE, "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Lỗi đọc file proxy: {e}")
        return

    print(f"[{datetime.now()}] 🔍 Bắt đầu kiểm tra {len(proxies)} proxy bằng curl...")

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def sem_task(proxy):
        async with sem:
            await check_proxy(proxy)

    await asyncio.gather(*(sem_task(proxy) for proxy in proxies))

    print(f"[{datetime.now()}] ✅ Kiểm tra hoàn tất.")

if __name__ == "__main__":
    asyncio.run(main())
