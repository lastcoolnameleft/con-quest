const { test, expect } = require('@playwright/test');

test('join page loads and legal links are reachable', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Join A Quest' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible();

  await page.getByRole('link', { name: 'Terms of Service' }).first().click();
  await expect(page).toHaveURL(/\/terms\/?$/);
  await expect(page.getByRole('heading', { name: 'Terms of Service' })).toBeVisible();

  await page.goto('/');
  await page.getByRole('link', { name: 'Privacy Policy' }).first().click();
  await expect(page).toHaveURL(/\/privacy\/?$/);
  await expect(page.getByRole('heading', { name: 'Privacy Policy' })).toBeVisible();
});
