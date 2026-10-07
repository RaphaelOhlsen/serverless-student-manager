import { expect, test } from '@playwright/test'

test('renders the public sign-in screen', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Acesse sua conta' })).toBeVisible()
  await expect(page.getByLabel('E-mail')).toBeVisible()
  await expect(page.getByLabel('Senha')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeEnabled()
})
