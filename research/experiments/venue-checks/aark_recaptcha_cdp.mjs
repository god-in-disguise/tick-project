import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const CHROME =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const DEBUG_PORT = 9223;
const SITE_KEY = "6LdHPmYsAAAAABliA8ARgLuSI8rlBWkZeqxXSKNP";
const PAGE_URL = "https://app.aark.digital";
const HEADLESS = process.env.AARK_CHROME_HEADLESS !== "0";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getJson(url, attempts = 40) {
  let last;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
      last = new Error(`HTTP ${response.status}`);
    } catch (error) {
      last = error;
    }
    await sleep(250);
  }
  throw last ?? new Error(`Could not load ${url}`);
}

async function main() {
  const startedAt = performance.now();
  const profile =
    process.env.AARK_CHROME_PROFILE ??
    `/tmp/tick-aark-cdp-profile-${randomUUID()}`;
  const chromeArgs = [
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-allow-origins=*",
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profile}`,
    PAGE_URL,
  ];
  if (HEADLESS) chromeArgs.unshift("--headless=new");
  const chrome = spawn(
    CHROME,
    chromeArgs,
    { stdio: "ignore" },
  );

  try {
    const pages = await getJson(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
    const page =
      pages.find((item) => item.type === "page" && item.url.includes("app.aark.digital")) ??
      pages.find((item) => item.type === "page");
    if (!page?.webSocketDebuggerUrl) throw new Error("Chrome page target not found");

    const socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });

    let requestId = 0;
    const pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id) return;
      const waiter = pending.get(message.id);
      if (!waiter) return;
      pending.delete(message.id);
      if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
      else waiter.resolve(message.result);
    });

    const command = (method, params = {}) =>
      new Promise((resolve, reject) => {
        requestId += 1;
        pending.set(requestId, { resolve, reject });
        socket.send(JSON.stringify({ id: requestId, method, params }));
      });

    await command("Runtime.enable");
    await sleep(6_000);
    await command("Runtime.evaluate", {
      expression: `(() => {
        if (document.querySelector('script[data-tick-aark-recaptcha]')) return;
        const script = document.createElement('script');
        script.dataset.tickAarkRecaptcha = 'true';
        script.src = 'https://www.google.com/recaptcha/enterprise.js?render=${SITE_KEY}';
        document.head.appendChild(script);
      })()`,
    });
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const ready = await command("Runtime.evaluate", {
        expression:
          "document.readyState === 'complete' && typeof grecaptcha !== 'undefined' && !!grecaptcha.enterprise",
        returnByValue: true,
      });
      if (ready?.result?.value) break;
      if (attempt === 39) throw new Error("reCAPTCHA did not load on app.aark.digital");
      await sleep(500);
    }

    const evaluated = await command("Runtime.evaluate", {
      expression: `new Promise((resolve, reject) => {
        grecaptcha.enterprise.ready(async () => {
          try {
            resolve(await grecaptcha.enterprise.execute(
              "${SITE_KEY}",
              { action: "TRADE" }
            ));
          } catch (error) {
            reject(error);
          }
        });
      })`,
      awaitPromise: true,
      returnByValue: true,
    });
    const token = evaluated?.result?.value;
    if (!token) throw new Error(JSON.stringify(evaluated));
    let openResponse = null;
    if (process.env.AARK_OPEN_REQUEST_B64) {
      const request = JSON.parse(
        Buffer.from(process.env.AARK_OPEN_REQUEST_B64, "base64").toString("utf8"),
      );
      const submitted = await command("Runtime.evaluate", {
        expression: `(async () => {
          const response = await fetch(${JSON.stringify(request.url)}, {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "version": ${JSON.stringify(request.headers.version)},
              "signature": ${JSON.stringify(request.headers.signature)},
              "recaptcha-response": ${JSON.stringify(token)}
            },
            body: JSON.stringify(${JSON.stringify(request.body)})
          });
          let body;
          try {
            body = await response.json();
          } catch {
            body = await response.text();
          }
          return { status: response.status, ok: response.ok, body };
        })()`,
        awaitPromise: true,
        returnByValue: true,
      });
      openResponse = submitted?.result?.value ?? submitted;
    }
    console.log(
      JSON.stringify(
        {
          origin: PAGE_URL,
          headless: HEADLESS,
          elapsedMs: Math.round((performance.now() - startedAt) * 10) / 10,
          issued: true,
          token: openResponse ? undefined : token,
          openResponse,
        },
        null,
        2,
      ),
    );
    socket.close();
  } finally {
    chrome.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ issued: false, error: String(error) }, null, 2));
  process.exitCode = 1;
});
