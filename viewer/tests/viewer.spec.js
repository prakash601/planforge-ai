import { test, expect } from "@playwright/test";

async function visiblePixels(page) {
  return page.locator("canvas").evaluate((canvas) => {
    const context = canvas.getContext("webgl2");
    const pixels = new Uint8Array(canvas.width * canvas.height * 4);
    context.readPixels(
      0,
      0,
      canvas.width,
      canvas.height,
      context.RGBA,
      context.UNSIGNED_BYTE,
      pixels,
    );
    let changed = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (
        Math.abs(pixels[i] - 237) +
          Math.abs(pixels[i + 1] - 242) +
          Math.abs(pixels[i + 2] - 239) >
        50
      )
        changed++;
    }
    return changed;
  });
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`viewer renders and responds at ${viewport.width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await page.waitForFunction(
      () => window.planforgeDiagnostics?.pointCount > 0,
    );
    await expect(page.locator("#scale-status")).toHaveText("Scale unverified");
    expect(await visiblePixels(page)).toBeGreaterThan(1000);
    const sequenceCount = await page.evaluate(
      () => window.planforgeDiagnostics.pointCount,
    );
    await page.screenshot({
      path: testInfo.outputPath("sequence.png"),
      fullPage: true,
    });
    const reconstruction = await page.locator("#layer").isVisible();
    if (!reconstruction) {
      await page.locator("#single").click();
      expect(
        await page.evaluate(() => window.planforgeDiagnostics.pointCount),
      ).toBeLessThan(sequenceCount);
      await page.locator("#frame").evaluate((input) => {
        input.value = "10";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await expect(page.locator("#frame-label")).toHaveText("000300");
    } else {
      await page.locator("#layer").selectOption("raw");
      await expect(page.locator("#download")).toHaveAttribute(
        "href",
        /raw\.ply$/,
      );
      await page.waitForFunction(
        () => window.planforgeDiagnostics?.pointCount > 0,
      );
      expect(await visiblePixels(page)).toBeGreaterThan(1000);
      await page.screenshot({
        path: testInfo.outputPath("raw.png"),
        fullPage: true,
      });
      await page.locator("#layer").selectOption("filtered");
      await expect(page.locator("#download")).toHaveAttribute(
        "href",
        /cloud\.ply$/,
      );
      await expect(page.locator("#single")).toBeHidden();
    }
    await page.locator("#confidence").selectOption("0");
    const allCount = await page.evaluate(
      () => window.planforgeDiagnostics.pointCount,
    );
    await page.locator("#confidence").selectOption("2");
    expect(
      await page.evaluate(() => window.planforgeDiagnostics.pointCount),
    ).toBeLessThanOrEqual(allCount);
    if (!reconstruction) await page.locator("#all").click();
    await page.locator("#fit").click();
    await page.locator("#trajectory").uncheck();
    await page.locator("#trajectory").check();
    await page.locator("#rotate").click();
    await expect(page.locator("#rotate")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const before = await page.locator("canvas").screenshot();
    await page.waitForTimeout(600);
    const after = await page.locator("canvas").screenshot();
    expect(before.equals(after)).toBe(false);
    await page.locator("#rotate").click();
    for (const capture of ["1", "2"]) {
      await page.locator("#capture").selectOption(capture);
      await page.waitForFunction(
        (id) => window.planforgeDiagnostics?.capture === id,
        capture === "1" ? "c00a170fe1" : "c7d28f72c6",
      );
      expect(await visiblePixels(page)).toBeGreaterThan(1000);
      await page.screenshot({
        path: testInfo.outputPath(`capture-${capture}.png`),
        fullPage: true,
      });
    }
    const bounds = await page.evaluate(() => {
      const content = document.querySelector("main").getBoundingClientRect();
      return {
        width: document.documentElement.scrollWidth,
        viewport: innerWidth,
        bottom: content.bottom,
        height: innerHeight,
      };
    });
    expect(bounds.width).toBeLessThanOrEqual(bounds.viewport);
    expect(bounds.bottom).toBeLessThanOrEqual(bounds.height + 1);
    expect(errors).toEqual([]);
  });
}
