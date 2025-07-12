const { exec } = require("child_process");

const datain = [
    "sudo apt update",
    "npm install puppeteer chrome-remote-interface async",
    "sudo apt install ca-certificates fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 libgcc1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 lsb-release wget xdg-utils -y",
    "wget https://github.com/ungoogled-software/ungoogled-chromium-portablelinux/releases/download/131.0.6778.85-1/ungoogled-chromium_131.0.6778.85-1.AppImage",
    "chmod +x ungoogled-chromium_131.0.6778.85-1.AppImage"
];

async function runCommands() {
    for (let command of datain) {
        await new Promise((resolve, reject) => {
            exec(command, (error, stdout, stderr) => {
                if (error) {
                    console.error(`Error executing command: ${command}\n${error.message}`);
                    reject(error);
                }
                if (stderr) {
                    console.error(`stderr: ${stderr}`);
                }
                console.log(`stdout: ${stdout}`);
                resolve();
            });
        });
    }
}

runCommands().catch(err => {
    console.error("Execution failed:", err);
});
