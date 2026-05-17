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

test.describe('Admin scoring submissions', () => {
  const suffix = uniqueSuffix();
  const seasonTitle = `Scoring Season ${suffix}`;
  const seasonSlug = `scoring-season-${suffix}`;
  const joinCode = `SC${suffix}`.toUpperCase().slice(0, 8);
  const questTitle = `Scoring Quest ${suffix}`;
  const playerHandle = `score-player-${suffix}`;

  test.beforeAll(async ({ browser }) => {
    createStaffUser();
    const page = await browser.newPage();
    await loginAsStaff(page);
    await createQuestTemplate(page, {
      title: questTitle,
      description: 'A quest for scoring flow testing',
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

    // Player joins and submits
    const playerPage = await browser.newPage();
    await joinSeasonAsPlayer(playerPage, { joinCode, handle: playerHandle });
    await playerPage.getByRole('link', { name: 'Start Quest' }).first().click();
    await playerPage.waitForURL(/\/(quests|assignments)\/.+\/submit/);
    await playerPage.fill('#id_text_response', 'My proof for scoring test');
    await playerPage.getByRole('button', { name: 'Submit for scoring' }).click();
    await playerPage.waitForURL(/\/seasons\//);
    await playerPage.close();
  });

  test('score a submission', async ({ page }) => {
    await loginAsStaff(page);
    await page.goto(`/seasons/${seasonSlug}/scoring/`);

    // Verify scoring queue heading
    await expect(page.getByRole('heading', { name: /Scoring Queue/ })).toBeVisible();

    // Verify pending submission is visible
    await expect(page.getByText('Pending submissions')).toBeVisible();
    const submissionRow = page.locator('.list-group-item').filter({ hasText: playerHandle });
    await expect(submissionRow).toBeVisible();

    // Expand the submission
    await submissionRow.getByText('Expand').click();
    const expandedSection = submissionRow.locator('.collapse');
    await expandedSection.waitFor({ state: 'visible' });

    // Verify submission text is visible
    await expect(expandedSection.getByText('My proof for scoring test')).toBeVisible();

    // Score it
    await expandedSection.locator('select[name="score"]').selectOption('4');
    await expandedSection.locator('input[name="judge_note"]').fill('Excellent submission!');
    await expandedSection.getByRole('button', { name: 'Approve & score' }).click();

    // After scoring, should stay on scoring page
    await page.waitForURL(/\/seasons\/.+\/scoring/);

    // Verify submission now appears in scored section
    await expect(page.getByText('Scored submissions')).toBeVisible();
    const scoredRow = page.locator('.list-group-item').filter({ hasText: playerHandle });
    await expect(scoredRow.locator('.badge').filter({ hasText: '4' })).toBeVisible();
  });

  test('leaderboard updates after scoring', async ({ page }) => {
    await page.goto(`/seasons/${seasonSlug}/leaderboard/`);
    await expect(page.getByRole('heading', { name: /Leaderboard/ })).toBeVisible();

    // Verify the player appears with their score in overall standings
    const row = page.locator('.table-responsive').first().locator('tbody tr').filter({ hasText: playerHandle });
    await expect(row).toBeVisible();
    await expect(row.getByRole('cell', { name: '4' })).toBeVisible();
  });
});
