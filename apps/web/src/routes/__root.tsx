import {HeadContent, Outlet, Scripts, createRootRouteWithContext} from '@tanstack/react-router'
import {QueryClientProvider, type QueryClient} from '@tanstack/react-query'
import css from '../styles.css?url'
import {AccessBoundary} from '../lib/access-boundary'
export const Route = createRootRouteWithContext<{queryClient: QueryClient}>()({
  head: () => ({meta: [{charSet: 'utf-8'}, {name: 'viewport', content: 'width=device-width, initial-scale=1'}, {title: 'Gitgood'}],
    links: [{rel: 'stylesheet', href: css}, {rel: 'icon', href: 'data:,'}]}),
  component: Root,
})
function Root() {
  const {queryClient} = Route.useRouteContext()
  return <html lang="en"><head><HeadContent /></head><body><QueryClientProvider client={queryClient}><AccessBoundary><Outlet /></AccessBoundary></QueryClientProvider><Scripts /></body></html>
}
