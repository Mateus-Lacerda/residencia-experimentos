/**
 * Captura de tela da aplicação com o Chrome instalado (playwright-core), para conferir a
 * cena sem abrir o navegador à mão. Requer o servidor rodando (npm run dev ou preview).
 *
 * Uso: node scripts/capturar.mjs [url] [site] [saida-dir] [granularidade] [passos] [metrica]
 * Gera: <saida>/<site>-geral.png, <site>-selecionado.png, <site>-historico.png
 * e imprime erros de console e as métricas da cena.
 */

import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const url = process.argv[2] ?? "http://localhost:5173/";
const site = process.argv[3] ?? "Lamb";
const out = process.argv[4] ?? "capturas";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  args: ["--use-angle=metal", "--enable-gpu"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 1 });
const erros = [];
page.on("console", (m) => {
  if (m.type() === "error" || m.type() === "warning") erros.push(`${m.type()}: ${m.text()}`);
});
page.on("pageerror", (e) => erros.push(`pageerror: ${e.message}`));

const t0 = Date.now();
await page.goto(url);
await page.waitForSelector(".cena canvas");
await page.waitForSelector(".ranking li", { timeout: 20000 });
if (site !== "Lamb") {
  await page.selectOption("#sel-site", site);
  await page.waitForFunction((s) => document.querySelector(".cena-status") == null && document.querySelector("#sel-site").value === s, site);
  await page.waitForTimeout(400);
}
// opcionais: [granularidade total|ano|mes|semana|dia] [passos à frente] [metrica]
const [gran, passos, metrica] = process.argv.slice(5);
const ROT = { total: "2016 a 2017", ano: "Ano", mes: "Mês", semana: "Semana", dia: "Dia" };
if (gran) await page.click(`.segmentado button:has-text("${ROT[gran]}")`);
for (let i = 0; i < Number(passos ?? 0); i++) await page.click('button:has-text("Próximo")');
if (metrica) await page.selectOption("#sel-metrica", metrica);
console.log(`pronto em ${Date.now() - t0} ms`);
await page.waitForTimeout(500);
await page.screenshot({ path: join(out, `${site}-geral.png`) });
console.log((await page.textContent(".cena-stats")) ?? "");

// seleciona o primeiro prédio do ranking
await page.click(".ranking li >> nth=0");
await page.waitForSelector(".abas");
await page.waitForTimeout(900);
await page.screenshot({ path: join(out, `${site}-selecionado.png`) });
await page.click(".abas button >> nth=1");
await page.waitForTimeout(500);
await page.screenshot({ path: join(out, `${site}-historico.png`) });
await page.click(".abas button >> nth=3");
await page.waitForTimeout(300);
await page.screenshot({ path: join(out, `${site}-construtivo.png`) });

// FPS aproximado: força renderizações contínuas girando a câmera por 2 s
const fps = await page.evaluate(async () => {
  const c = document.querySelector(".cena canvas");
  const r = c.getBoundingClientRect();
  const opts = (x, y, buttons) => ({ clientX: x, clientY: y, buttons, button: 0, bubbles: true, pointerId: 1, pointerType: "mouse", isPrimary: true });
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  c.dispatchEvent(new PointerEvent("pointerdown", opts(cx, cy, 1)));
  let frames = 0;
  const t = performance.now();
  await new Promise((res) => {
    const step = () => {
      frames++;
      c.ownerDocument.dispatchEvent(new PointerEvent("pointermove", opts(cx + frames * 2, cy, 1)));
      if (performance.now() - t < 2000) requestAnimationFrame(step);
      else res();
    };
    requestAnimationFrame(step);
  });
  c.ownerDocument.dispatchEvent(new PointerEvent("pointerup", opts(cx + frames * 2, cy, 0)));
  return frames / ((performance.now() - t) / 1000);
});
console.log(`fps aproximado durante rotação: ${fps.toFixed(0)}`);
await page.screenshot({ path: join(out, `${site}-rotacionado.png`) });

console.log(erros.length ? `console:\n  ${erros.join("\n  ")}` : "console: sem erros");
await browser.close();
