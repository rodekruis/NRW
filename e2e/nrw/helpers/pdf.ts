import { BrowserContext, Download, Locator } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

// A made-up origin, so pdf.js can load as ES modules without a real server.
const pdfRendererOrigin = 'https://pdf-renderer.e2e';
const pdfJsBuildPath = path.dirname(
  require.resolve('pdfjs-dist/build/pdf.mjs'),
);
const renderScale = 1.5;

/**
 * Renders every page of a downloaded PDF to a canvas on a new page, with pdf.js
 * in the browser, so the pages can be asserted with `toHaveScreenshot()`.
 */
export async function renderPdfPages({
  context,
  download,
}: {
  context: BrowserContext;
  download: Download;
}): Promise<Locator> {
  const pdfPath = await download.path();
  const pdfBase64 = (await readFile(pdfPath)).toString('base64');

  const page = await context.newPage();
  await page.route(`${pdfRendererOrigin}/**`, async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/') {
      await route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><body style="margin:0;background:#fff"></body>',
      });
      return;
    }
    await route.fulfill({
      contentType: 'text/javascript',
      path: path.join(pdfJsBuildPath, path.basename(pathname)),
    });
  });
  await page.goto(`${pdfRendererOrigin}/`);
  await page.addScriptTag({
    type: 'module',
    content: `
      import * as pdfJs from '${pdfRendererOrigin}/pdf.mjs';
      pdfJs.GlobalWorkerOptions.workerSrc = '${pdfRendererOrigin}/pdf.worker.mjs';
      window.pdfJs = pdfJs;
    `,
  });
  await page.waitForFunction(() => 'pdfJs' in window);

  await page.evaluate(
    async ({ data, scale }) => {
      const { pdfJs } = window as unknown as Window & {
        pdfJs: typeof import('pdfjs-dist');
      };

      const pdf = await pdfJs.getDocument({
        data: Uint8Array.from(atob(data), (character) =>
          character.charCodeAt(0),
        ),
      }).promise;

      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
        const pdfPage = await pdf.getPage(pageNumber);
        const viewport = pdfPage.getViewport({ scale });
        const canvas = document.createElement('canvas');
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.display = 'block';
        document.body.append(canvas);
        await pdfPage.render({ canvas, viewport }).promise;
      }
    },
    { data: pdfBase64, scale: renderScale },
  );

  return page.locator('canvas');
}
