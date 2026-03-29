import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cookiesApi } from '@dl/api/cookies'
import type { Cookie } from '@dl/types'
import type { User } from '@core/types/api'
import { toast } from '@core/components/ui/toast'

export interface UseAdminCookiesReturn {
  // Pool
  poolItems: Cookie[]
  poolLoading: boolean
  poolFetching: boolean
  poolByDomain: Map<string, Cookie[]>
  poolDomains: string[]
  expandedDomains: Set<string>
  toggleDomain: (domain: string) => void
  loadPool: (isInitial?: boolean) => void
  refreshLabels: () => Promise<void>
  removePool: (id: number, domain: string) => Promise<void>

  // Personal
  personalItems: Cookie[]
  personalLoading: boolean
  personalFetching: boolean
  loadPersonal: (isInitial?: boolean) => void
  removePersonal: (id: number, domain: string) => Promise<void>

  // Shared
  users: User[]
  userMap: Map<number, User>
  deleting: number | null
  validating: number | null
  refreshingLabels: boolean
  validate: (id: number) => Promise<void>

  // UI state
  addPoolOpen: boolean
  setAddPoolOpen: (open: boolean) => void
  uploadOpen: boolean
  setUploadOpen: (open: boolean) => void

  // Confirm dialog
  confirmMsg: string | null
  setConfirmMsg: (msg: string | null) => void
  confirmResolveRef: React.MutableRefObject<((val: boolean) => void) | null>
}

export function useAdminCookies(): UseAdminCookiesReturn {
  const { t } = useTranslation()

  const [confirmMsg, setConfirmMsg] = useState<string | null>(null)
  const confirmResolveRef = useRef<((val: boolean) => void) | null>(null)

  const askConfirm = useCallback((message: string): Promise<boolean> =>
    new Promise((resolve) => {
      confirmResolveRef.current = resolve
      setConfirmMsg(message)
    }), [])

  const [poolItems, setPoolItems] = useState<Cookie[]>([])
  const [poolLoading, setPoolLoading] = useState(true)
  const [poolFetching, setPoolFetching] = useState(false)
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set())

  const [personalItems, setPersonalItems] = useState<Cookie[]>([])
  const [personalLoading, setPersonalLoading] = useState(true)
  const [personalFetching, setPersonalFetching] = useState(false)

  const [deleting, setDeleting] = useState<number | null>(null)
  const [validating, setValidating] = useState<number | null>(null)
  const [refreshingLabels, setRefreshingLabels] = useState(false)
  const [addPoolOpen, setAddPoolOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [users, setUsers] = useState<User[]>([])

  const userMap = new Map(users.map((u) => [u.id, u]))

  const poolByDomain = poolItems.reduce<Map<string, Cookie[]>>((acc, c) => {
    const list = acc.get(c.domain) ?? []
    list.push(c)
    acc.set(c.domain, list)
    return acc
  }, new Map())

  const poolDomains = Array.from(poolByDomain.keys()).sort()

  const toggleDomain = (domain: string) =>
    setExpandedDomains(prev => {
      const next = new Set(prev)
      next.has(domain) ? next.delete(domain) : next.add(domain)
      return next
    })

  const loadPool = (isInitial = false) => {
    if (isInitial) setPoolLoading(true)
    else setPoolFetching(true)
    cookiesApi
      .listPool()
      .then((res) => setPoolItems(res.data))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => { setPoolLoading(false); setPoolFetching(false) })
  }

  const loadPersonal = (isInitial = false) => {
    if (isInitial) setPersonalLoading(true)
    else setPersonalFetching(true)
    cookiesApi
      .listAll()
      .then((res) => setPersonalItems(res.data.filter((c) => !c.is_pool)))
      .catch(() => toast.error(t('common.load_error')))
      .finally(() => { setPersonalLoading(false); setPersonalFetching(false) })
  }

  useEffect(() => {
    loadPool(true)
    loadPersonal(true)
    cookiesApi
      .listUsers()
      .then((res) => setUsers(res.data.items))
      .catch(() => {})
  }, [])

  const validate = async (id: number) => {
    setValidating(id)
    try {
      const r = await cookiesApi.validate(id)
      const updater = (prev: Cookie[]) => prev.map((c) => c.id === id ? { ...c, is_valid: r.data.is_valid } : c)
      setPoolItems(updater)
      setPersonalItems(updater)
      toast.success(
        r.data.is_valid
          ? t('cookies.valid_ok', { defaultValue: 'Cookie is valid' })
          : t('cookies.invalid_msg', { defaultValue: 'Cookie appears invalid' })
      )
    } catch {
      toast.error(t('cookies.validate_error', { defaultValue: 'Validation failed' }))
    } finally {
      setValidating(null)
    }
  }

  const refreshLabels = async () => {
    setRefreshingLabels(true)
    try {
      const r = await cookiesApi.refreshLabels()
      toast.success(t('cookies.labels_refreshed', { count: r.data.updated, defaultValue: `Updated ${r.data.updated} labels` }))
      loadPool()
    } catch {
      toast.error(t('common.error', { defaultValue: 'Error' }))
    } finally {
      setRefreshingLabels(false)
    }
  }

  const removePool = async (id: number, domain: string) => {
    const ok = await askConfirm(t('cookies.delete_confirm', { domain, defaultValue: `Delete cookie for ${domain}?` }))
    if (!ok) return
    setDeleting(id)
    try {
      await cookiesApi.deletePoolById(id)
      toast.success(t('cookies.deleted', { defaultValue: 'Cookie deleted' }))
      loadPool()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  const removePersonal = async (id: number, domain: string) => {
    const ok = await askConfirm(t('cookies.delete_confirm', { domain, defaultValue: `Delete cookie for ${domain}?` }))
    if (!ok) return
    setDeleting(id)
    try {
      await cookiesApi.deleteById(id)
      toast.success(t('cookies.deleted', { defaultValue: 'Cookie deleted' }))
      loadPersonal()
    } catch {
      toast.error(t('cookies.delete_error', { defaultValue: 'Failed to delete' }))
    } finally {
      setDeleting(null)
    }
  }

  return {
    poolItems,
    poolLoading,
    poolFetching,
    poolByDomain,
    poolDomains,
    expandedDomains,
    toggleDomain,
    loadPool,
    refreshLabels,
    removePool,
    personalItems,
    personalLoading,
    personalFetching,
    loadPersonal,
    removePersonal,
    users,
    userMap,
    deleting,
    validating,
    refreshingLabels,
    validate,
    addPoolOpen,
    setAddPoolOpen,
    uploadOpen,
    setUploadOpen,
    confirmMsg,
    setConfirmMsg,
    confirmResolveRef,
  }
}
