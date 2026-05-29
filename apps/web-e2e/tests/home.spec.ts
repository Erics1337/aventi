import { expect, test } from '@playwright/test';

test.describe('marketing home', () => {
  test('loads the public Aventi landing page', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('link', { name: /Aventi home/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Get App/i }).first()).toBeVisible();
  });
});
