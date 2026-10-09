import {createContext, useContext, useEffect, useRef, useSyncExternalStore, type ReactNode} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {api, type Session} from './api'
import {accessStore, type AccessState} from './access-state'
const initial: AccessState = {generation: 0, status: 'checking', context: null}
const Context = createContext<{state: AccessState; refetch: () => void}>({state: initial, refetch: () => {}})
export function useSession() {
  const {state, refetch} = useContext(Context)
  return {data: state.session, refetch, isPending: state.status === 'checking' || state.status === 'suspended',
    error: state.status === 'unavailable' ? new Error('Access check unavailable') : null}
}
export function AccessBoundary({children}: {children: ReactNode}) {
  const store = accessStore(), client = useQueryClient(), refresh = useRef<() => void>(() => {})
  const state = useSyncExternalStore(store?.subscribe ?? (() => () => {}), store?.snapshot ?? (() => initial), () => initial)
  useEffect(() => {
    if (!store) return
    let controller: AbortController | null = null
    const check = () => {
      if (document.visibilityState === 'hidden') return
      controller?.abort()
      controller = new AbortController()
      void api<Session>('/session', {signal: controller.signal}).catch(() => {})
    }
    refresh.current = check
    const removeNotice = store.onNotice(notice => {
      if (notice.reset) {
        controller?.abort()
        void client.cancelQueries()
        client.removeQueries()
      }
      if (notice.purgeDrafts) {
        try {
          for (let index = sessionStorage.length - 1; index >= 0; index--) {
            const key = sessionStorage.key(index)
            if (key?.startsWith('gitgood-comment:')) sessionStorage.removeItem(key)
          }
        } catch { /* Browser storage may be disabled; live draft state was unmounted. */ }
      }
      if (notice.refresh) check()
    })
    const visible = () => {
      if (document.visibilityState === 'visible') store.invalidate()
      else {controller?.abort(); store.suspend()}
    }
    const offline = () => {controller?.abort(); store.unavailable(store.ticket())}
    const interval = window.setInterval(check, 5000)
    const online = () => store.invalidate()
    window.addEventListener('focus', check); window.addEventListener('online', online)
    window.addEventListener('offline', offline); document.addEventListener('visibilitychange', visible)
    check()
    return () => {
      controller?.abort(); removeNotice(); window.clearInterval(interval); refresh.current = () => {}
      window.removeEventListener('focus', check); window.removeEventListener('online', online)
      window.removeEventListener('offline', offline); document.removeEventListener('visibilitychange', visible)
    }
  }, [store, client])
  return <Context.Provider value={{state, refetch: () => refresh.current()}}>
    {state.status === 'authorized' || state.status === 'anonymous' ? <div key={state.generation}>{children}</div> :
      <div className="shell"><header><a className="brand" href="/">gitgood<span className="dot">●</span></a></header><main>
        {state.status === 'unavailable' ? <p role="alert">Access check unavailable. <button onClick={() => refresh.current()}>Retry access check</button></p> : <p role="status">Checking access…</p>}
      </main></div>}
  </Context.Provider>
}
