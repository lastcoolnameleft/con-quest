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

test.describe('Player submission journey', () => {
  const suffix = uniqueSuffix();
  const seasonTitle = `Player Season ${suffix}`;
  const seasonSlug = `player-season-${suffix}`;
  const joinCode = `PL${suffix}`.toUpperCase().slice(0, 8);
  const questTitle = `Player Quest ${suffix}`;
  const playerHandle = `player-${suffix}`;

  test.beforeAll(async ({ browser }) => {
    createStaffUser();
    const page = await browser.newPage();
    await loginAsStaff(page);
    await createQuestTemplate(page, {
      title: questTitle,
      description: 'A quest for player submission testing',
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
    // Publish and activate the quest
    await transitionQuestStatus(page, { questTitle, buttonName: 'Publish' });
    await transitionQuestStatus(page, { questTitle, buttonName: 'Activate' });
    await page.close();
  });

  test('join season and submit to open quest', async ({ page }) => {
    // Player joins via home page
    await joinSeasonAsPlayer(page, { joinCode, handle: playerHandle });

    // Player should see the season detail page
    await expect(page.getByRole('heading', { name: seasonTitle })).toBeVisible();

    // Player should see the active quest with "Start Quest" button
    await expect(page.getByText(questTitle)).toBeVisible();
    await page.getByRole('link', { name: 'Start Quest' }).first().click();

    // Player fills submission form
    await page.waitForURL(/\/(quests|assignments)\/.+\/submit/);
    await page.fill('#id_text_response', 'This is my submission for the e2e test!');
    await page.getByRole('button', { name: 'Submit for scoring' }).click();

    // Player should see confirmation — redirected back to season detail
    await page.waitForURL(/\/seasons\//);

    // Verify the assignment shows as submitted
    await expect(page.getByText('You have submitted for this quest')).toBeVisible();
  });

  test('player views leaderboard after scoring', async ({ browser }) => {
    // Create a fresh player + submit in one context
    const playerPage = await browser.newPage();
    const scoreSuffix = uniqueSuffix();
    const scorePlayerHandle = `scorer-${scoreSuffix}`;

    await joinSeasonAsPlayer(playerPage, { joinCode, handle: scorePlayerHandle });
    await playerPage.getByRole('link', { name: 'Start Quest' }).first().click();
    await playerPage.waitForURL(/\/(quests|assignments)\/.+\/submit/);
    await playerPage.fill('#id_text_response', 'Submission to be scored');
    await playerPage.getByRole('button', { name: 'Submit for scoring' }).click();
    await playerPage.waitForURL(/\/seasons\//);

    // Admin scores the submission
    const adminPage = await browser.newPage();
    await loginAsStaff(adminPage);
    await adminPage.goto(`/seasons/${seasonSlug}/scoring/`);

    // Expand the pending submission
    const submissionRow = adminPage.locator('.list-group-item').filter({ hasText: scorePlayerHandle });
    await submissionRow.getByText('Expand').click();

    // Score it
    const expandedSection = submissionRow.locator('.collapse');
    await expandedSection.waitFor({ state: 'visible' });
    await expandedSection.locator('select[name="score"]').selectOption('4');
    await expandedSection.locator('input[name="judge_note"]').fill('Great work!');
    await expandedSection.getByRole('button', { name: 'Approve & score' }).click();
    await adminPage.waitForURL(/\/seasons\/.+\/scoring/);
    await adminPage.close();

    // Player views leaderboard
    await playerPage.goto(`/seasons/${seasonSlug}/leaderboard/`);
    await expect(playerPage.getByRole('cell', { name: scorePlayerHandle }).first()).toBeVisible();
    await expect(playerPage.getByRole('cell', { name: '4' }).first()).toBeVisible();
    await playerPage.close();
  });

  test('join with invalid code shows error', async ({ page }) => {
    await page.goto('/');
    await page.fill('#id_join_code', 'BADCODE1');
    await page.fill('#id_handle', 'ghost-player');
    await page.getByRole('button', { name: 'Play' }).click();

    // Should stay on the same page or redirect with an error message
    await expect(page.locator('.alert-error, .alert-danger, .invalid-feedback, .errorlist')).toBeVisible();
  });
});
