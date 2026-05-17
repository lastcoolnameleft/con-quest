// @ts-check
const { test, expect } = require('@playwright/test');
const {
  createStaffUser,
  loginAsStaff,
  createSeasonViaAdmin,
  createQuestTemplate,
  createSeasonQuest,
  transitionQuestStatus,
  uniqueSuffix,
} = require('./helpers');

test.describe('Admin quest lifecycle', () => {
  const suffix = uniqueSuffix();
  const seasonTitle = `Lifecycle Season ${suffix}`;
  const seasonSlug = `lifecycle-season-${suffix}`;
  const joinCode = `LC${suffix}`.toUpperCase().slice(0, 8);
  const questTitle = `Lifecycle Quest ${suffix}`;

  test.beforeAll(() => {
    createStaffUser();
  });

  test.describe.serial('Open quest full lifecycle', () => {
    const openSuffix = `o${suffix}`;
    const openSeasonTitle = `Open Season ${openSuffix}`;
    const openSeasonSlug = `open-season-${openSuffix}`;
    const openJoinCode = `OP${openSuffix}`.toUpperCase().slice(0, 8);
    const openQuestTitle = `Open Quest ${openSuffix}`;

    test('setup: create season and quest template', async ({ page }) => {
      await loginAsStaff(page);
      await createQuestTemplate(page, {
        title: openQuestTitle,
        description: 'An open quest for lifecycle testing',
        points: 5,
      });
      await createSeasonViaAdmin(page, {
        title: openSeasonTitle,
        slug: openSeasonSlug,
        joinCode: openJoinCode,
      });
    });

    test('create season quest — starts in draft', async ({ page }) => {
      await loginAsStaff(page);
      await createSeasonQuest(page, {
        seasonSlug: openSeasonSlug,
        questMode: 'open',
        titleOverride: openQuestTitle,
      });

      // Verify quest appears in control dashboard with Draft status
      await page.goto('/control/');
      const questRow = page.locator('.py-2').filter({ hasText: openQuestTitle });
      await expect(questRow).toBeVisible();
      await expect(questRow.getByText('Draft')).toBeVisible();
    });

    test('transition draft → pending (Publish)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: openQuestTitle,
        buttonName: 'Publish',
      });

      const questRow = page.locator('.py-2').filter({ hasText: openQuestTitle });
      await expect(questRow.getByText('Pending')).toBeVisible();
    });

    test('transition pending → active (Activate)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: openQuestTitle,
        buttonName: 'Activate',
      });

      const questRow = page.locator('.py-2').filter({ hasText: openQuestTitle });
      await expect(questRow.getByText('Active')).toBeVisible();
    });

    test('transition active → complete (Complete)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: openQuestTitle,
        buttonName: 'Complete',
      });

      const questRow = page.locator('.py-2').filter({ hasText: openQuestTitle });
      await expect(questRow.getByText('Closed')).toBeVisible();
    });

    test('transition complete → archived (Archive)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: openQuestTitle,
        buttonName: 'Archive',
      });

      const questRow = page.locator('.py-2').filter({ hasText: openQuestTitle });
      await expect(questRow.getByText('Archived')).toBeVisible();
    });
  });

  test.describe.serial('Scheduled quest lifecycle', () => {
    const schedSuffix = `s${suffix}`;
    const schedSeasonTitle = `Sched Season ${schedSuffix}`;
    const schedSeasonSlug = `sched-season-${schedSuffix}`;
    const schedJoinCode = `SC${schedSuffix}`.toUpperCase().slice(0, 8);
    const schedQuestTitle = `Sched Quest ${schedSuffix}`;

    test('setup: create season and quest template', async ({ page }) => {
      await loginAsStaff(page);
      await createQuestTemplate(page, {
        title: schedQuestTitle,
        description: 'A scheduled quest for lifecycle testing',
        points: 5,
      });
      await createSeasonViaAdmin(page, {
        title: schedSeasonTitle,
        slug: schedSeasonSlug,
        joinCode: schedJoinCode,
      });
    });

    test('create scheduled season quest — starts in draft', async ({ page }) => {
      await loginAsStaff(page);
      await createSeasonQuest(page, {
        seasonSlug: schedSeasonSlug,
        questMode: 'scheduled',
        titleOverride: schedQuestTitle,
      });

      await page.goto('/control/');
      const questRow = page.locator('.py-2').filter({ hasText: schedQuestTitle });
      await expect(questRow).toBeVisible();
      await expect(questRow.getByText('Draft')).toBeVisible();
    });

    test('transition draft → pending (Publish)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: schedQuestTitle,
        buttonName: 'Publish',
      });

      const questRow = page.locator('.py-2').filter({ hasText: schedQuestTitle });
      await expect(questRow.getByText('Pending')).toBeVisible();
    });

    test('transition pending → active (Start)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: schedQuestTitle,
        buttonName: 'Start',
      });

      const questRow = page.locator('.py-2').filter({ hasText: schedQuestTitle });
      await expect(questRow.getByText('Active')).toBeVisible();
    });

    test('transition active → complete (Complete)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: schedQuestTitle,
        buttonName: 'Complete',
      });

      const questRow = page.locator('.py-2').filter({ hasText: schedQuestTitle });
      await expect(questRow.getByText('Closed')).toBeVisible();
    });

    test('transition complete → archived (Archive)', async ({ page }) => {
      await loginAsStaff(page);
      await transitionQuestStatus(page, {
        questTitle: schedQuestTitle,
        buttonName: 'Archive',
      });

      const questRow = page.locator('.py-2').filter({ hasText: schedQuestTitle });
      await expect(questRow.getByText('Archived')).toBeVisible();
    });
  });

  test.describe('Early archive from each state', () => {
    const archiveSuffix = `a${suffix}`;
    const archiveSeasonTitle = `Archive Season ${archiveSuffix}`;
    const archiveSeasonSlug = `archive-season-${archiveSuffix}`;
    const archiveJoinCode = `AR${archiveSuffix}`.toUpperCase().slice(0, 8);

    test.beforeAll(async ({ browser }) => {
      const page = await browser.newPage();
      createStaffUser();
      await loginAsStaff(page);
      await createQuestTemplate(page, {
        title: `Archive Quest Draft ${archiveSuffix}`,
        description: 'Quest for archive-from-draft test',
        points: 5,
      });
      await createQuestTemplate(page, {
        title: `Archive Quest Pending ${archiveSuffix}`,
        description: 'Quest for archive-from-pending test',
        points: 5,
      });
      await createQuestTemplate(page, {
        title: `Archive Quest Active ${archiveSuffix}`,
        description: 'Quest for archive-from-active test',
        points: 5,
      });
      await createSeasonViaAdmin(page, {
        title: archiveSeasonTitle,
        slug: archiveSeasonSlug,
        joinCode: archiveJoinCode,
      });
      await page.close();
    });

    test('archive from draft', async ({ page }) => {
      const questTitle = `Archive Draft ${archiveSuffix}`;
      await loginAsStaff(page);
      await createSeasonQuest(page, {
        seasonSlug: archiveSeasonSlug,
        questMode: 'open',
        titleOverride: questTitle,
      });

      await transitionQuestStatus(page, { questTitle, buttonName: 'Archive' });

      const questRow = page.locator('.py-2').filter({ hasText: questTitle });
      await expect(questRow.getByText('Archived')).toBeVisible();
    });

    test('archive from pending', async ({ page }) => {
      const questTitle = `Archive Pending ${archiveSuffix}`;
      await loginAsStaff(page);
      await createSeasonQuest(page, {
        seasonSlug: archiveSeasonSlug,
        questMode: 'open',
        titleOverride: questTitle,
      });

      await transitionQuestStatus(page, { questTitle, buttonName: 'Publish' });
      await transitionQuestStatus(page, { questTitle, buttonName: 'Archive' });

      const questRow = page.locator('.py-2').filter({ hasText: questTitle });
      await expect(questRow.getByText('Archived')).toBeVisible();
    });

    test('archive from active', async ({ page }) => {
      const questTitle = `Archive Active ${archiveSuffix}`;
      await loginAsStaff(page);
      await createSeasonQuest(page, {
        seasonSlug: archiveSeasonSlug,
        questMode: 'open',
        titleOverride: questTitle,
      });

      await transitionQuestStatus(page, { questTitle, buttonName: 'Publish' });
      await transitionQuestStatus(page, { questTitle, buttonName: 'Activate' });
      await transitionQuestStatus(page, { questTitle, buttonName: 'Archive' });

      const questRow = page.locator('.py-2').filter({ hasText: questTitle });
      await expect(questRow.getByText('Archived')).toBeVisible();
    });
  });
});
