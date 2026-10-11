import {createHash} from 'node:crypto'

// These are display fixtures for the real React app, not backend acceptance
// evidence. They create no Git objects, accounts, releases or Cloud resources.
export const TOUR = Object.freeze({
  team: 'demo',
  repository: 'fieldnotes',
  username: 'mira',
  password: 'synthetic-tour-only',
  pullId: '17d5ec13-64cd-49a0-a706-6b0ff7b88fc1',
  releaseId: '3dca438e-f948-4944-8b25-ce1de02f94b6',
  assetId: '52369c67-1c11-4aa4-9cf5-7cdb72bb9035',
  mainSha: '8e605066c6fbc463f207be551303e6a2610b4093',
  featureSha: 'e419d4052fa8e1bfb779748086e72d7c2f54b6a9',
  previousSha: '1d393ae92c1b684aa8b594599a6e130836604d20',
  tagSha: 'dfdaaf433cae4477f97c53983025f8ee35573b85',
  observedAt: '2026-10-11T09:30:00Z'
})

const repositoryPath = `/repos/${TOUR.team}/${TOUR.repository}`
export const TOUR_PATHS = Object.freeze({
  home: '/',
  repository: repositoryPath,
  readme: `${repositoryPath}?sha=${TOUR.mainSha}&path=README.md`,
  pull: `${repositoryPath}/pulls/${TOUR.pullId}`,
  release: `${repositoryPath}#release-${TOUR.releaseId}`
})

const accessContext = 'g'.repeat(43)
const session = {
  user: {id: 1, username: TOUR.username},
  csrf: 'synthetic-tour-csrf',
  teams: [{team: TOUR.team, role: 'owner'}],
  access_context: accessContext
}

const repositories = [
  {id: 1, name: TOUR.repository},
  {id: 2, name: 'design-system'},
  {id: 3, name: 'handbook'}
].map(repository => ({
  ...repository,
  team: TOUR.team,
  status: 'ready',
  owner_id: 1,
  url: `/repos/${TOUR.team}/${repository.name}`,
  clone_url: `https://gitgood.example.invalid/${TOUR.team}/${repository.name}.git`,
  ssh_clone_url: `ssh://git@gitgood.example.invalid:2222/${TOUR.team}/${repository.name}.git`
}))

const history = [
  {sha: TOUR.mainSha, author: 'Mira Chen', date: '2026-10-11 09:15 +0000', subject: 'Add a clear release checklist'},
  {sha: TOUR.previousSha, author: 'Alex Rivera', date: '2026-10-10 16:40 +0000', subject: 'Document the daily team workflow'}
]

const readme = `# Fieldnotes

A small release-notes app for teams that care about clear communication.

## Getting started

1. Create a note for the change you are making.
2. Ask a teammate to review the wording.
3. Group approved notes into the next release.

## This repository

src/       Application components
docs/      Product notes and release checklist
README.md  You are here

This sample project is synthetic data for the Gitgood interface tour.
`

const diffText = `diff --git a/docs/release-checklist.md b/docs/release-checklist.md
index 31bd73a..b512a06 100644
--- a/docs/release-checklist.md
+++ b/docs/release-checklist.md
@@ -1,4 +1,8 @@
 # Release checklist
${' '}
-Prepare the release notes.
+## Before publishing
+
+- Group notes into Added, Changed and Fixed.
+- Link each note to its reviewed pull request.
+- Check that the release tag identifies the intended commit.
 Ask a teammate to review the final wording.
`

const policy = {
  version: 3,
  approvals: 1,
  required_checks: [{provider_id: 1, name: 'build'}, {provider_id: 1, name: 'tests'}]
}

const pull = {
  id: TOUR.pullId,
  title: 'Make release notes easier to scan',
  body: 'Group release notes by the kind of change and connect each item to its review. The checklist keeps the last step clear for everyone on the team.',
  state: 'open',
  author_id: 2,
  source_ref: 'refs/heads/clear-release-notes',
  target_ref: 'refs/heads/main',
  source_sha: TOUR.featureSha,
  target_sha: TOUR.mainSha,
  policy,
  events: [
    {
      id: 'ef756b3c-9da8-44aa-bb08-5d83d594a66b',
      actor: 'Alex Rivera', kind: 'comment',
      body: 'The draft is ready. I kept the checklist short and linked each step to the result it needs.',
      source_sha: TOUR.featureSha, target_sha: TOUR.mainSha,
      path: null, line: null, side: null, excerpt: null, outdated: false
    },
    {
      id: 'c4c6c6c7-c09c-4086-841c-5b8097bb03d6',
      actor: 'Mira Chen', kind: 'comment',
      body: 'This makes the release much easier to follow. The connection to the reviewed pull request is especially useful.',
      source_sha: TOUR.featureSha, target_sha: TOUR.mainSha,
      path: 'docs/release-checklist.md', line: 6, side: 'new',
      excerpt: '- Link each note to its reviewed pull request.', outdated: false
    }
  ],
  checks: [
    {id: 1, provider: 'Demo CI', name: 'build', sha: TOUR.featureSha, attempt: 1, sequence: 1, status: 'success'},
    {id: 2, provider: 'Demo CI', name: 'tests', sha: TOUR.featureSha, attempt: 1, sequence: 1, status: 'success'}
  ]
}

const assetBytes = Buffer.from('Fieldnotes interface-tour sample.\nThis is not a Gitgood application artifact.\n')
const sha256 = value => createHash('sha256').update(value).digest('hex')
const releaseNotes = `A clearer daily workflow for the Fieldnotes sample team.
Added
- A short checklist for preparing each release.
- Links between release notes and reviewed changes.
Changed
- Product notes now live together under docs/.

Synthetic sample release for the interface tour; not a Gitgood product release.`
const release = {
  id: TOUR.releaseId,
  tag: 'v0.3.0-demo',
  tag_object: TOUR.tagSha,
  commit_sha: TOUR.mainSha,
  base_sha: TOUR.previousSha,
  title: 'Fieldnotes v0.3.0 · demo',
  notes: releaseNotes,
  notes_digest: sha256(releaseNotes),
  state: 'published',
  version: 1,
  published_at: '2026-10-11T09:20:00Z',
  withdrawn_at: null,
  changes: {commits: history.map(({sha, subject}) => ({sha, subject}))},
  assets: [{id: TOUR.assetId, name: 'fieldnotes-demo.txt', sha256: sha256(assetBytes), size: assetBytes.length, state: 'ready'}]
}

const activity = {
  records: [
    {
      id: 'tour-release', kind: 'release', team: TOUR.team, name: TOUR.repository,
      title: release.title, snippet: 'A short checklist and a clearer path from reviewed change to release.',
      state: 'published', actor: 'Mira Chen', occurred_at: release.published_at, url: TOUR_PATHS.release
    },
    {
      id: 'tour-pull', kind: 'pull_request', team: TOUR.team, name: TOUR.repository,
      title: pull.title, snippet: 'A small, focused improvement to the team release checklist.',
      state: 'open', actor: 'Alex Rivera', occurred_at: '2026-10-11T09:10:00Z', url: TOUR_PATHS.pull
    }
  ],
  next_cursor: null,
  has_more: false,
  recorded_at: TOUR.observedAt,
  source: 'native',
  snapshot: 'synthetic-tour-snapshot'
}

function snapshot(url) {
  const sha = url.searchParams.get('sha') || TOUR.mainSha
  const path = url.searchParams.get('path') || ''
  if (![TOUR.mainSha, TOUR.featureSha, TOUR.previousSha].includes(sha)) return null
  if (path === 'README.md') return {sha, path, kind: 'text', content: readme, size: Buffer.byteLength(readme)}
  if (path === 'docs/release-checklist.md') {
    const content = '# Release checklist\n\nGroup notes, link the reviews, and verify the release tag.\n'
    return {sha, path, kind: 'text', content, size: Buffer.byteLength(content)}
  }
  const trees = {
    '': [['docs', 'tree'], ['src', 'tree'], ['README.md', 'blob'], ['package.json', 'blob']],
    docs: [['release-checklist.md', 'blob']],
    src: [['App.tsx', 'blob']]
  }
  if (!(path in trees)) return null
  return {
    sha, path, kind: 'tree', history,
    entries: trees[path].map(([name, kind]) => ({name, kind, sha: TOUR.mainSha, unsupported_encoding: false}))
  }
}

/**
 * Install before opening the first page. Use a fresh browser context with
 * serviceWorkers: 'block'. Only this exact loopback origin can reach the Vite
 * server. Every API request is handled here; none reaches a forge or Barkpark.
 */
export async function installTourFixtures(context, {origin = 'http://127.0.0.1:47840'} = {}) {
  const local = new URL(origin)
  if (local.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(local.hostname) ||
      local.username || local.password || local.pathname !== '/' || local.search || local.hash) {
    throw new Error('The interface tour requires an explicit loopback HTTP origin.')
  }

  let signedIn = false
  const diagnostics = {apiRequests: 0, rejectedMutations: [], unknownApiPaths: [], blockedExternalRequests: []}
  const apiBase = '/api' + repositoryPath

  await context.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    if (url.origin !== local.origin) {
      diagnostics.blockedExternalRequests.push({method, origin: url.origin, path: url.pathname})
      await route.abort('blockedbyclient')
      return
    }
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    diagnostics.apiRequests++
    const headers = {'x-gitgood-access-context': accessContext, 'cache-control': 'no-store'}
    const json = (body, status = 200) => route.fulfill({status, headers, contentType: 'application/json', body: JSON.stringify(body)})

    if (url.pathname === '/api/session' && method === 'POST') {
      let credentials
      try { credentials = request.postDataJSON() } catch { return json({error: 'invalid_tour_sign_in'}, 400) }
      if (credentials?.username !== TOUR.username || credentials?.password !== TOUR.password) {
        return json({error: 'invalid_tour_sign_in'}, 401)
      }
      signedIn = true
      return json(session)
    }
    if (method !== 'GET') {
      diagnostics.rejectedMutations.push({method, path: url.pathname})
      return json({error: 'synthetic_tour_is_read_only'}, 405)
    }
    if (url.pathname === '/api/session') return signedIn ? json(session) : json({error: 'unauthenticated'}, 401)
    if (!signedIn) return json({error: 'unauthenticated'}, 401)

    switch (url.pathname) {
      case '/api/repos': return json({repositories})
      case '/api/activity':
      case '/api/search':
      case apiBase + '/activity': return json(activity)
      case '/api/teams/' + TOUR.team + '/members':
        return json({members: [{username: TOUR.username, role: 'owner'}, {username: 'alex', role: 'writer'}, {username: 'sam', role: 'reader'}], events: []})
      case '/api/ssh-keys': return json({keys: [], transport: {enabled: false}})
      case '/api/connections/barkpark': return json({state: 'unconfigured', generation: 'absent'})
      case apiBase: return json(repositories[0])
      case apiBase + '/branches': return json({branches: [{name: 'main', sha: TOUR.mainSha}, {name: 'clear-release-notes', sha: TOUR.featureSha}]})
      case apiBase + '/snapshot': {
        const result = snapshot(url)
        return result ? json(result) : json({error: 'synthetic_tour_path_unavailable'}, 404)
      }
      case apiBase + '/diff': return json({text: diffText, base: TOUR.previousSha})
      case apiBase + '/operations': return json({operations: []})
      case apiBase + '/pulls': return json({pull_requests: [{id: pull.id, title: pull.title, state: pull.state}]})
      case apiBase + '/pulls/' + TOUR.pullId: return json(pull)
      case apiBase + '/pulls/' + TOUR.pullId + '/diff': return json({text: diffText, sha: TOUR.featureSha, base: TOUR.mainSha})
      case apiBase + '/pulls/' + TOUR.pullId + '/links': return json({links: []})
      case apiBase + '/policy': return json({policy, providers: [{id: 1, name: 'Demo CI', credential_id: 1}]})
      case apiBase + '/tags': return json({tags: [{tag: release.tag, object: TOUR.tagSha, commit_sha: TOUR.mainSha}]})
      case apiBase + '/releases': return json({releases: [release]})
      case apiBase + '/releases/' + TOUR.releaseId: return json({release, events: []})
      case apiBase + '/releases/' + TOUR.releaseId + '/assets/' + TOUR.assetId + '/download':
        return route.fulfill({status: 200, headers, contentType: 'text/plain', body: assetBytes})
      case '/api/changes/' + TOUR.pullId: return json({id: pull.id, title: pull.title, url: TOUR_PATHS.pull})
      default:
        diagnostics.unknownApiPaths.push({method, path: url.pathname})
        return json({error: 'synthetic_tour_route_not_defined'}, 501)
    }
  })

  return Object.freeze({
    origin: local.origin,
    diagnostics: () => structuredClone(diagnostics)
  })
}
