import {createFileRoute} from '@tanstack/react-router'
import {proxy} from '../../server/forge'
export const Route = createFileRoute('/api/$')({
  server: {handlers: {GET: ({request}) => proxy(request), POST: ({request}) => proxy(request),
    PUT: ({request}) => proxy(request), HEAD: ({request}) => proxy(request), DELETE: ({request}) => proxy(request), PATCH: ({request}) => proxy(request)}},
})
