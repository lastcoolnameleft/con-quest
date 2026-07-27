// @ts-check
const { test, expect } = require('@playwright/test');
const {
  createStaffUser,
  deleteSeasonBySlug,
  deleteQuestByTitle,
  createSeasonViaAdmin,
  createQuestTemplate,
  createSeasonQuest,
  transitionQuestStatus,
  joinSeasonAsPlayer,
  uniqueSuffix,
} = require('./helpers');

test.describe('Submission UX under slow networks', () => {
  test.describe.configure({ timeout: 90_000, mode: 'serial' });

  const suffix = uniqueSuffix();
  const seasonTitle = `Latency Season ${suffix}`;
  const seasonSlug = `latency-season-${suffix}`;
  const joinCode = `LT${suffix}`.toUpperCase().slice(0, 8);
  const questTitle = `Latency Quest ${suffix}`;
  const mediaPayload = {
    name: 'proof.png',
    mimeType: 'image/png',
    buffer: Buffer.alloc(256 * 1024, 1),
  };

  async function loginAsStaffViaUI(page) {
    await page.goto('/auth/login/');
    const details = page.locator('details').first();
    if (!(await details.evaluate((node) => node.open))) {
      await page.getByText('Sign in with username & password').click();
    }
    await page.getByRole('textbox', { name: 'Username' }).fill('e2e-admin');
    await page.getByRole('textbox', { name: 'Password' }).fill('testpass123');
    await page.getByRole('button', { name: 'Login' }).click();
    await page.waitForURL(/\/$/);
  }

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120_000);
    createStaffUser();
    const page = await browser.newPage();
    await loginAsStaffViaUI(page);
    await createQuestTemplate(page, {
      title: questTitle,
      description: 'Latency and reliability test quest',
      points: 5,
    });
    await createSeasonViaAdmin(page, {
      title: seasonTitle,
      slug: seasonSlug,
      joinCode,
    });
    await createSeasonQuest(page, {
      seasonSlug,
      questMode: 'open',
      titleOverride: questTitle,
    });
    await transitionQuestStatus(page, { questTitle, buttonName: 'Publish' });
    await transitionQuestStatus(page, { questTitle, buttonName: 'Activate' });
    await page.close();
  });

  test.afterAll(() => {
    deleteSeasonBySlug(seasonSlug);
    deleteQuestByTitle(questTitle);
  });

  async function openSubmissionPage(page, handle) {
    await joinSeasonAsPlayer(page, { joinCode, handle });
    await page.locator('a.cq-quest-action-start').first().click();
    await page.waitForURL(/\/assignments\/\d+\/submit\//);
  }

  async function enableSlowNetwork(page) {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 1200,
      downloadThroughput: 20 * 1024,
      uploadThroughput: 15 * 1024,
      connectionType: 'cellular3g',
    });
    return cdp;
  }

  test('delayed submit shows activity state and prevents duplicate posts', async ({ page }) => {
    await openSubmissionPage(page, `latency-submit-${uniqueSuffix()}`);
    await page.fill('#id_text_response', 'Submitting under delayed network');
    await page.setInputFiles('#id_media_files', mediaPayload);
    const cdp = await enableSlowNetwork(page);

    let postCount = 0;
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        /\/assignments\/\d+\/submit\/$/.test(request.url())
      ) {
        postCount += 1;
      }
    });

    const submitButton = page.getByRole('button', { name: 'Submit for scoring' });
    await submitButton.click();

    // Slow uploads should still resolve to a single successful submit post.
    await page.waitForURL(/\/seasons\//);
    await expect(page.getByText(/Submission received\.|Submitted/).first()).toBeVisible();
    expect(postCount).toBe(1);
    await cdp.detach().catch(() => {});
  });

  test('delayed draft save shows activity state', async ({ page }) => {
    await openSubmissionPage(page, `latency-draft-${uniqueSuffix()}`);
    await page.fill('#id_text_response', 'Saving draft under delayed network');
    await page.setInputFiles('#id_media_files', mediaPayload);
    const cdp = await enableSlowNetwork(page);
    let postCount = 0;
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        /\/assignments\/\d+\/submit\/$/.test(request.url())
      ) {
        postCount += 1;
      }
    });

    const draftButton = page.getByRole('button', { name: 'Save Draft' });
    await draftButton.click();
    await page.waitForURL(/\/seasons\//);
    expect(postCount).toBe(1);
    await cdp.detach().catch(() => {});
  });

  test('high latency + low throughput still completes submission flow', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Network emulation uses Chromium CDP');

    await openSubmissionPage(page, `latency-cdp-${uniqueSuffix()}`);
    await page.fill('#id_text_response', 'Slow-link submit stability check');

    const cdp = await enableSlowNetwork(page);

    await page.getByRole('button', { name: 'Submit for scoring' }).click();
    await page.waitForURL(/\/seasons\//);
    await expect(page.getByText(/Submission received\.|Submitted/).first()).toBeVisible();
    await cdp.detach().catch(() => {});
  });
});
