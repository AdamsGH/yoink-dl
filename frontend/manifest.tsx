import { Cookie, Download, Settings, ShieldAlert } from 'lucide-react'

import type { PluginManifest } from '@core/types/plugin'

import HistoryPage      from './src/pages/history'
import SettingsPage     from './src/pages/settings'
import CookiesPage      from './src/pages/cookies'
import AdminCookiesPage from './src/pages/admin/cookies'
import AdminNsfwPage    from './src/pages/admin/nsfw'
import DlStatsPage      from './src/pages/admin/stats/index'

export const dlPlugin: PluginManifest = {
  id: 'dl',
  name: 'Yoink DL',
  userStatsEndpoint: '/users/me/stats',

  routes: [
    { path: '/settings',      element: <SettingsPage /> },
    { path: '/history',       element: <HistoryPage /> },
    { path: '/cookies',       element: <CookiesPage /> },
    { path: '/admin/cookies', element: <AdminCookiesPage />, minRole: 'moderator' },
    { path: '/admin/nsfw',    element: <AdminNsfwPage />,    minRole: 'admin' },
    { path: '/admin/stats',   element: <DlStatsPage />,      minRole: 'admin' },
  ],

  navGroups: [
    {
      items: [
        { label: 'Settings', i18nKey: 'nav.settings', path: '/settings', icon: <Settings className="h-4 w-4" /> },
        { label: 'History',  i18nKey: 'nav.history',  path: '/history',  icon: <Download className="h-4 w-4" /> },
        { label: 'Cookies',  i18nKey: 'nav.cookies',  path: '/cookies',  icon: <Cookie   className="h-4 w-4" /> },
      ],
    },
    {
      label: 'Admin',
      collapsible: true,
      defaultOpen: true,
      minRole: ['owner', 'admin', 'moderator'],
      items: [
        { label: 'Cookies',         i18nKey: 'nav.cookies',     path: '/admin/cookies', icon: <Cookie      className="h-4 w-4" />, minRole: ['owner', 'admin', 'moderator'] },
        { label: 'NSFW',            i18nKey: 'nav.nsfw',        path: '/admin/nsfw',    icon: <ShieldAlert className="h-4 w-4" />, minRole: ['owner', 'admin'] },
      ],
    },
  ],

  // These items extend the core Admin group declared in corePlugin (same label merges in AppLayout)

  resources: [
    { name: 'settings',   list: '/settings' },
    { name: 'downloads',  list: '/history' },
    { name: 'my-cookies', list: '/cookies',      meta: { label: 'My Cookies' } },
    { name: 'cookies',    list: '/admin/cookies', meta: { label: 'Cookies' } },
    { name: 'nsfw',       list: '/admin/nsfw',    meta: { label: 'NSFW' } },
  ],
}
