// @ts-check
const { test, expect } = require('@playwright/test');
const {
  createStaffUser,
  loginAsStaff,
  createSeasonViaAdmin,
  createQuestTemplate,
  createSeasonQuest,
  transitionQuestStatus,
  joinSeasonAsPlayer,
  uniqueSuffix,
} = require('./helpers');

test.describe('Moderation flow', () => {
  const suffix = uniqueSuffix();
  const seasonTitle = `Mod Season ${suffix}`;
  const seasonSlug = `mod-season-${suffix}`;
  const joinCode = `MD${suffix}`.toUpperCase().slice(0, 8);
  const questTitle = `Mod Quest ${suffix}`;
  const submitterHandle = `submitter-${suffix}`;
  const reporterHandle = `reporter-${suffix}`;

  test.beforeAll(async ({ browser }) => {
    createStaffUser();

    // Admin creates season + quest and activates it
    const adminPage = await browser.newPage();
    await loginAsStaff(adminPage);
    await createQuestTemplate(adminPage, {
      title: questTitle,
      description: 'A quest for moderation testing',
      points: 5,
    });
    await createSeasonViaAdmin(adminPage, {
      title: seasonTitle,
      slug: seasonSlug,
      joinCode,
    });
    await createSeasonQuest(adminPage, {
      seasonSlug,
      questMode: 'open',
      titleOverride: questTitle,
    });
    await transitionQuestStatus(adminPage, { questTitle, buttonName: 'Publish' });
    await transitionQuestStatus(adminPage, { questTitle, buttonName: 'Activate' });
    await adminPage.close();

    // Submitter joins and submits proof
    const submitterPage = await browser.newPage();
    await joinSeasonAsPlayer(submitterPage, { joinCode, handle: submitterHandle });
    await submitterPage.getByRole('link', { name: 'Start Quest' }).first().click();
    await submitterPage.waitForURL(/\/(quests|assignments)\/.+\/submit/);
    await submitterPage.fill('#id_text_response', 'Suspicious submission for moderation test');
    await submitterPage.getByRole('button', { name: 'Submit for scoring' }).click();
    await submitterPage.waitForURL(/\/seasons\//);
    await submitterPage.close();
  });

  test('report and resolve a submission', async ({ browser }) => {
    // Reporter joins the season
    const reporterPage = await browser.newPage();
    await joinSeasonAsPlayer(reporterPage, { joinCode, handle: reporterHandle });

    // Admin scores the submission first so the reporter can see it via scoring queue
    // Actually, reporters report via the scoring queue "Report" link
    // Let's navigate via the admin scoring queue
    await reporterPage.close();

    // Admin goes to scoring queue and clicks Report on the submission
    const adminPage = await browser.newPage();
    await loginAsStaff(adminPage);
    await adminPage.goto(`/seasons/${seasonSlug}/scoring/`);

    // Expand the pending submission
    const submissionRow = adminPage.locator('.list-group-item').filter({ hasText: submitterHandle });
    await submissionRow.getByText('Expand').click();
    const expandedSection = submissionRow.locator('.collapse');
    await expandedSection.waitFor({ state: 'visible' });

    // Click the Report link
    await expandedSection.getByRole('link', { name: 'Report' }).click();
    await adminPage.waitForURL(/\/submissions\/\d+\/report/);

    // Fill report form
    await expect(adminPage.getByRole('heading', { name: 'Report submission' })).toBeVisible();
    await adminPage.selectOption('#id_reason', 'cheating');
    await adminPage.fill('#id_details', 'This submission looks like cheating');
    await adminPage.getByRole('button', { name: 'Submit report' }).click();

    // Should redirect back after reporting
    await adminPage.waitForURL(/\/seasons\//);

    // Navigate to moderation queue
    await adminPage.goto(`/seasons/${seasonSlug}/moderation/`);
    await expect(adminPage.getByRole('heading', { name: /Moderation Queue/ })).toBeVisible();

    // Verify the report is visible
    const reportRow = adminPage.locator('.list-group-item').filter({ hasText: 'Cheating' });
    await expect(reportRow).toBeVisible();

    // Resolve as dismissed
    await reportRow.locator('select[name="status"]').selectOption('dismissed');
    await reportRow.locator('input[name="details"]').fill('Reviewed - no issue found');
    await reportRow.getByRole('button', { name: 'Resolve' }).click();

    // After resolving, the report should no longer be in the queue
    await adminPage.waitForURL(/\/seasons\/.+\/moderation/);
    await expect(adminPage.getByText('No open reports.')).toBeVisible();

    await adminPage.close();
  });
});
