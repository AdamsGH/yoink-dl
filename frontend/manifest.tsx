import {
  Cookie, Download, Settings,
  Settings2, ShieldAlert, Users, UsersRound,
} from 'lucide-react'

import type { PluginManifest } from '@core/types/plugin'

import HistoryPage          from './src/pages/history'
import SettingsPage         from './src/pages/settings'
import CookiesPage          from './src/pages/cookies'
import AdminUsersPage       from './src/pages/admin/users'
import AdminGroupsPage      from './src/pages/admin/groups'
import AdminCookiesPage     from './src/pages/admin/cookies'
import AdminNsfwPage        from './src/pages/admin/nsfw'
import AdminBotSettingsPage from './src/pages/admin/bot-settings'

export const dlPlugin: PluginManifest = {
  id: 'dl',
  name: 'Yoink DL',
  userStatsEndpoint: '/users/me/stats',

  routes: [
    { path: '/settings',           element: <SettingsPage /> },
    { path: '/history',            element: <HistoryPage /> },
    { path: '/cookies',            element: <CookiesPage /> },
    { path: '/admin/users',        element: <AdminUsersPage />,        minRole: 'admin' },
    { path: '/admin/groups',       element: <AdminGroupsPage />,       minRole: 'admin' },
    { path: '/admin/cookies',      element: <AdminCookiesPage />,      minRole: 'moderator' },
    { path: '/admin/nsfw',         element: <AdminNsfwPage />,         minRole: 'admin' },
    { path: '/admin/bot-settings', element: <AdminBotSettingsPage />,  minRole: 'admin' },
  ],

  navGroups: [
    {
      items: [
        { label: 'Settings', path: '/settings', icon: <Settings  className="h-4 w-4" /> },
        { label: 'History',  path: '/history',  icon: <Download  className="h-4 w-4" /> },
        { label: 'Cookies',  path: '/cookies',  icon: <Cookie    className="h-4 w-4" /> },
      ],
    },
    {
      label: 'Admin',
      collapsible: true,
      defaultOpen: true,
      minRole: ['owner', 'admin', 'moderator'],
      items: [
        { label: 'Users',        path: '/admin/users',        icon: <Users       className="h-4 w-4" />, minRole: ['owner', 'admin'] },
        { label: 'Groups',       path: '/admin/groups',       icon: <UsersRound  className="h-4 w-4" />, minRole: ['owner', 'admin'] },
        { label: 'Cookies',      path: '/admin/cookies',      icon: <Cookie      className="h-4 w-4" />, minRole: ['owner', 'admin', 'moderator'] },
        { label: 'NSFW',         path: '/admin/nsfw',         icon: <ShieldAlert className="h-4 w-4" />, minRole: ['owner', 'admin'] },
        { label: 'Bot Settings', path: '/admin/bot-settings', icon: <Settings2   className="h-4 w-4" />, minRole: ['owner', 'admin'] },
      ],
    },
  ],

  resources: [
    { name: 'settings',     list: '/settings' },
    { name: 'downloads',    list: '/history' },
    { name: 'my-cookies',   list: '/cookies',      meta: { label: 'My Cookies' } },
    { name: 'users',        list: '/admin/users',        meta: { label: 'Users' } },
    { name: 'groups',       list: '/admin/groups',       meta: { label: 'Groups' } },
    { name: 'cookies',      list: '/admin/cookies',      meta: { label: 'Cookies' } },
    { name: 'nsfw',         list: '/admin/nsfw',         meta: { label: 'NSFW' } },
    { name: 'bot-settings', list: '/admin/bot-settings', meta: { label: 'Bot Settings' } },
  ],
}
