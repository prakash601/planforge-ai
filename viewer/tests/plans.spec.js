import { test, expect } from "@playwright/test";

const root = process.env.PLANFORGE_PLAN_URL;
const captures = ["1a8384c3f6", "c00a170fe1", "c7d28f72c6"];

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`plan artifacts at ${viewport.width}px`, async ({ page }) => {
    test.skip(!root, "Requires generated Task 6 plan artifacts");
    await page.setViewportSize(viewport);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const capture of captures) {
      await page.goto(`${root}/${capture}/index.html`);
      await expect(
        page.getByRole("heading", { name: "PlanForge AI", exact: true }),
      ).toBeVisible();
      await expect(page.getByText(capture, { exact: true })).toBeVisible();
      const pixels = await page.locator("img").evaluate((img) => {
        if (!img.complete || !img.naturalWidth) return 0;
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const context = canvas.getContext("2d");
        context.drawImage(img, 0, 0);
        const data = context.getImageData(
          0,
          0,
          canvas.width,
          canvas.height,
        ).data;
        let count = 0;
        for (let index = 0; index < data.length; index += 4) {
          if (Math.min(data[index], data[index + 1], data[index + 2]) < 200)
            count++;
        }
        return count;
      });
      expect(pixels).toBeGreaterThan(5000);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const modelResponse = await page.request.get(
        `${root}/${capture}/measurements.json`,
      );
      expect(modelResponse.ok()).toBe(true);
      const model = await modelResponse.json();
      expect(model.scale.status).toBe("unverified");
      for (const link of [
        "Open SVG",
        "Download PNG",
        "Measurements JSON",
        "Run record",
      ]) {
        const url = await page
          .getByRole("link", { name: link, exact: true })
          .getAttribute("href");
        expect((await page.request.get(`${root}/${capture}/${url}`)).ok()).toBe(
          true,
        );
      }
      await page.screenshot({
        path: test.info().outputPath(`${capture}-${viewport.width}.png`),
        fullPage: true,
      });
      await page.getByRole("link", { name: "Open SVG", exact: true }).click();
      await expect(page.locator("svg")).toBeVisible();
      const bounds = await page.locator("svg").evaluate((svg) => {
        const box = svg.viewBox.baseVal;
        return [...svg.querySelectorAll("text")].every((text) => {
          const rect = text.getBBox();
          return (
            rect.x >= 0 &&
            rect.y >= 0 &&
            rect.x + rect.width <= box.width &&
            rect.y + rect.height <= box.height
          );
        });
      });
      expect(bounds).toBe(true);
    }
    expect(errors).toEqual([]);
  });
}
