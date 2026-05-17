// @ts-check
const { execSync } = require('child_process');
const { expect } = require('@playwright/test');

const STAFF_USERNAME = 'e2e-admin';
const STAFF_EMAIL = 'admin@test.com';
const STAFF_PASSWORD = 'testpass123';

/**
 * Create a Django superuser via manage.py shell. Idempotent — handles race conditions.
 */
function createStaffUser() {
  const script = `
import django.db
from apps.accounts.models import Account
try:
    if not Account.objects.filter(username='${STAFF_USERNAME}').exists():
        Account.objects.create_superuser('${STAFF_USERNAME}', '${STAFF_EMAIL}', '${STAFF_PASSWORD}')
except django.db.IntegrityError:
    pass
`.trim();
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  execSync(`${pythonCmd} manage.py shell -c "${script}"`, {
    cwd: process.cwd(),
    stdio: 'pipe',
  });
}

/**
 * Log in as the staff user via the Django login form.
 */
async function loginAsStaff(page) {
  await page.goto('/auth/login/');
  await page.fill('#id_username', STAFF_USERNAME);
  await page.fill('#id_password', STAFF_PASSWORD);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForURL(/^[^?]*\/$/);
}

/**
 * Create a season via the admin control panel.
 * Returns the season slug.
 */
async function createSeasonViaAdmin(page, { title, slug, joinCode }) {
  await page.goto('/control/');
  await page.getByRole('link', { name: 'New Season' }).click();
  await page.waitForURL(/\/control\/seasons\/new/);

  await page.fill('#id_title', title);
  await page.fill('#id_slug', slug);
  if (joinCode) {
    await page.fill('#id_join_code', joinCode);
  }
  // Set season status to active
  await page.selectOption('#id_status', 'active');

  await page.getByRole('button', { name: 'Save season' }).click();
  await page.waitForURL(/\/control\/?/);
  return slug;
}

/**
 * Create a quest template in the quest library.
 * Returns to control dashboard after creation.
 */
async function createQuestTemplate(page, { title, description, points }) {
  await page.goto('/control/');
  await page.getByRole('link', { name: 'New Quest' }).click();
  await page.waitForURL(/\/quest-library\/new/);

  await page.fill('#id_title', title);
  if (description) {
    await page.fill('#id_description', description);
  }
  if (points) {
    await page.fill('#id_default_points_max', String(points));
  }

  await page.getByRole('button', { name: 'Save quest' }).click();
  // quest_create redirects to season-index (/)
  await page.waitForURL(/^[^?]*\/$/);
}

/**
 * Create a season quest (link a quest template to a season).
 * Navigates via the "Add Quest" link on the control dashboard.
 */
async function createSeasonQuest(page, { seasonSlug, questMode = 'open', titleOverride }) {
  await page.goto(`/seasons/${seasonSlug}/quests/new/`);

  // Select the first available quest template if one exists
  const questSelect = page.locator('#id_quest');
  const options = await questSelect.locator('option').all();
  if (options.length > 1) {
    // Select first non-empty option
    await questSelect.selectOption({ index: 1 });
  }

  // Set quest mode
  await page.selectOption('#id_quest_mode', questMode);

  if (titleOverride) {
    await page.fill('#id_title_override', titleOverride);
  }

  // For scheduled quests, set duration
  if (questMode === 'scheduled') {
    await page.fill('#id_duration_seconds', '3600');
  }

  await page.getByRole('button', { name: 'Save quest' }).click();
  // season_quest_create redirects to control-dashboard
  await page.waitForURL(/\/control\/?$/);
}

/**
 * Join a season as a player via the home page join form.
 */
async function joinSeasonAsPlayer(page, { joinCode, handle }) {
  await page.goto('/');
  await page.fill('#id_join_code', joinCode);
  await page.fill('#id_handle', handle);
  await page.getByRole('button', { name: 'Play' }).click();
  // Should redirect to the season detail page
  await page.waitForURL(/\/seasons\//);
}

/**
 * Transition a season quest status via the control dashboard buttons.
 * buttonName should match one of: Publish, Activate, Start, Complete, Archive
 */
async function transitionQuestStatus(page, { questTitle, buttonName }) {
  await page.goto('/control/');
  // Each quest is in a py-2 row within .border-start
  const questRow = page.locator('.py-2').filter({ hasText: questTitle });
  await questRow.getByRole('button', { name: buttonName }).click();
  await page.waitForURL(/\/control\/?$/);
}

/**
 * Extract CSRF token from a form on the page.
 */
async function getCSRFToken(page) {
  return page.locator('input[name="csrfmiddlewaretoken"]').first().getAttribute('value');
}

/**
 * Generate a unique suffix based on timestamp to avoid test collisions.
 */
function uniqueSuffix() {
  return Date.now().toString(36).slice(-6);
}

module.exports = {
  STAFF_USERNAME,
  STAFF_PASSWORD,
  createStaffUser,
  loginAsStaff,
  createSeasonViaAdmin,
  createQuestTemplate,
  createSeasonQuest,
  joinSeasonAsPlayer,
  transitionQuestStatus,
  getCSRFToken,
  uniqueSuffix,
};
